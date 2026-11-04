#!/usr/bin/env python3
"""Spike 5: Eagle boards for the class priors. The file is XML, so this is lookup, not a board parser: KiCad's importer reads the
board in boardmeasure.py; this reads what the importer drops (the pin map in the .sch, `contactref` for the net guard).

  python3 -I tools/corpus/eagle.py fetch --hits HITS.jsonl --work /tmp/spike5-corpus/eagle     # blobs and sibling .sch through `gh api`
  python3 -I tools/corpus/eagle.py jobs  --work /tmp/spike5-corpus/eagle --out JOBS.json       # role-measure jobs for boardmeasure --roles
  python3 -I tools/corpus/eagle.py licences --work /tmp/spike5-corpus/eagle                    # a licence string per repo, README + LICENSE

Files are untrusted data, kept under --work, parsed by ElementTree and never run. Silk art (an element with no value), panels and
SparkFun `Production/` files are out. Modules are dropped later by pad extent, where the pads are known.
"""
from __future__ import annotations

import argparse, base64, concurrent.futures as cf, hashlib, json, os, re, subprocess, sys, time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TAB = ROOT / "tools/bench/data/class-table.json"
PANEL = re.compile(r"panel|(^|/)production/", re.I)


def norm(s):
    """A net or pin name with overbars and bus suffixes gone, so `!CS` and `~{CS}` compare equal."""
    return re.sub(r"[~{}!]", "", (s or "")).upper()


def pin_name(s):
    return re.sub(r"[!~{}]", "", re.sub(r"@\d+$", "", s or "")).upper()


def elements(brd):
    """[(name, value, package)] of a board's parts, and {(element, pad): signal} from `contactref`."""
    root = ET.parse(brd).getroot()
    els = [(e.get("name"), e.get("value") or "", e.get("package") or "") for e in root.iter("element")]
    cref = {}
    for s in root.iter("signal"):
        for c in s.findall("contactref"):
            cref[(c.get("element"), c.get("pad"))] = s.get("name")
    return els, cref


def pinmap(sch, ref):
    """{pad: pin name} of one part, from the schematic's device `connects`; None if the part is not there."""
    root = ET.parse(sch).getroot()
    parts = {p.get("name").upper(): p for p in root.iter("part")}
    p = parts.get(ref.upper())
    if p is None:
        return None
    lib = [l for l in root.iter("library") if l.get("name") == p.get("library")]
    if not lib:
        return None
    ds = [d for d in lib[0].iter("deviceset") if d.get("name") == p.get("deviceset")]
    if not ds:
        return None
    dev = [d for d in ds[0].iter("device") if d.get("name") == p.get("device", "")]
    cs = dev[0].find("connects") if dev else None
    pins = {}
    for c in (cs if cs is not None else []):
        for pad in c.get("pad").split():
            pins[pad] = pin_name(c.get("pin"))
    return pins or None


def class_rx():
    tab = json.load(open(TAB))
    return {c: {p: re.compile(r, re.I) for p, r in v.items()} for c, v in tab["classes"].items()}


def part_of(value, rxs):
    for cls in ("imu6", "hbridge"):
        for part, rx in rxs[cls].items():
            if rx.search(value):
                return cls, part
    return None


def gh_raw(path, tries=4):
    for k in range(tries):
        p = subprocess.run(["gh", "api", path], capture_output=True)
        if p.returncode == 0:
            return p.stdout
        if b"404" in p.stderr or b"Not Found" in p.stdout + p.stderr:
            return None
        time.sleep(4 * (k + 1))
    return None


def fetch_one(work, repo, path, sha):
    h = hashlib.sha1(f"{repo}:{path}".encode()).hexdigest()[:12]
    brd, sch = work / f"{h}.brd", work / f"{h}.sch"
    rec = {"repo": repo, "path": path, "id": h}
    if not brd.exists():
        raw = gh_raw(f"repos/{repo}/git/blobs/{sha}")
        if raw is None:
            return {**rec, "brd": None, "why": "blob gone"}
        j = json.loads(raw)
        if j.get("size", 0) > 2_000_000:
            return {**rec, "brd": None, "why": "over 2 MB"}
        brd.write_bytes(base64.b64decode(j["content"]))
    rec["brd"] = str(brd)
    if not sch.exists():
        q = re.sub(r" ", "%20", path[:-4] + ".sch")
        raw = gh_raw(f"repos/{repo}/contents/{q}")
        if raw is not None:
            try:
                j = json.loads(raw)
                if j.get("content"):
                    sch.write_bytes(base64.b64decode(j["content"]))
            except ValueError:
                pass
    rec["sch"] = str(sch) if sch.exists() else None
    return rec


def cmd_fetch(a):
    work = Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    man = work / "manifest.jsonl"
    done = {json.loads(l)["id"] for l in open(man)} if man.exists() else set()
    hits = {}
    for l in open(a.hits):
        x = json.loads(l)
        if x.get("scope"):      # the vendor org queries; those boards come from the review's inventory
            continue
        for repo, path, sha in x["items"]:
            org = repo.split("/")[0].lower()
            if org in ("adafruit", "sparkfun") or PANEL.search(path):
                continue
            hits[(repo, path)] = sha
    todo = [(r, p, s) for (r, p), s in sorted(hits.items()) if hashlib.sha1(f"{r}:{p}".encode()).hexdigest()[:12] not in done]
    print(f"{len(hits)} third-party files, {len(todo)} to fetch", flush=True)
    with cf.ThreadPoolExecutor(a.jobs) as ex, open(man, "a") as f:
        for n, fu in enumerate(cf.as_completed([ex.submit(fetch_one, work, *t) for t in todo])):
            f.write(json.dumps(fu.result()) + "\n"); f.flush()
            if n % 50 == 0:
                print(n, flush=True)


def eagle_jobs(rec, rxs, org):
    """Role-measure jobs for one board; (jobs, drop reasons)."""
    if not rec.get("brd"):
        return [], [rec.get("why", "no board")]
    try:
        els, cref = elements(rec["brd"])
    except (ET.ParseError, OSError):
        return [], ["not Eagle XML"]
    jobs, why = [], []
    for name, value, pkg in els:
        if not value.strip():
            continue        # silk art: an element with no value
        hit = part_of(value, rxs)
        if hit is None:
            continue
        cls, part = hit
        if not rec.get("sch"):
            why.append("no .sch")
            continue
        try:
            pins = pinmap(rec["sch"], name)
        except (ET.ParseError, OSError):
            pins = None
        if not pins:
            why.append("no pin map")
            continue
        jobs.append({"key": rec["id"], "ref": name, "part": part, "cls": cls, "fmt": "eagle", "board": rec["brd"], "repo": rec["repo"], "path": rec["path"], "org": org,
                     "value": value[:30], "rx": re.escape(value[:6]), "pin_names": pins, "cref": rec.get("cref")})
    return jobs, why


def cmd_jobs(a):
    rxs = class_rx()
    work = Path(a.work)
    jobs, why = [], {}
    recs = [json.loads(l) for l in open(work / "manifest.jsonl")] if (work / "manifest.jsonl").exists() else []
    vendor = json.load(open(a.vendor)) if a.vendor else []
    for r in vendor:
        recs.append({"repo": r["repo"], "path": r["path"], "id": hashlib.sha1(f"{r['repo']}:{r['path']}".encode()).hexdigest()[:12], "brd": r.get("brd"), "sch": r.get("sch")})
    seen = set()
    for r in recs:
        org = r["repo"].split("/")[0].lower()
        org = org if org in ("adafruit", "sparkfun") else "third-party"
        js, wh = eagle_jobs(r, rxs, org)
        for w in wh:
            why[w] = why.get(w, 0) + 1
        for j in js:
            k = (j["repo"], j["path"], j["ref"])
            if k not in seen:
                seen.add(k)
                jobs.append(j)
    json.dump(jobs, open(a.out, "w"))
    print(f"{len(recs)} boards, {len(jobs)} jobs; dropped {why}")


LIC = [("CC-BY-SA", r"(CC[- ]?BY[- ]?SA|Attribution[-/ ]Share[- ]?Alike)"), ("CC-BY", r"Creative\s+Commons\s+Attribution(?![-/ ]Share)"), ("CERN-OHL", r"CERN[- ]OHL|CERN Open Hardware"),
       ("TAPR", r"TAPR"), ("MIT", r"\bMIT License\b|Permission is hereby granted, free of charge"), ("Apache-2.0", r"Apache License"), ("GPL-3.0", r"GNU GENERAL PUBLIC LICENSE\s+Version 3"),
       ("GPL-2.0", r"GNU GENERAL PUBLIC LICENSE\s+Version 2"), ("BSD", r"Redistribution and use in source and binary forms"), ("beerware", r"beerware"), ("Unlicense", r"unlicense\.org")]


def lic_of(repo):
    t = ""
    for q in ("readme", "license"):
        raw = gh_raw(f"repos/{repo}/{q}", tries=2)
        if raw:
            try:
                t += base64.b64decode(json.loads(raw).get("content", "")).decode("utf8", "replace") + "\n"
            except ValueError:
                pass
    return "+".join(n for n, x in LIC if re.search(x, t, re.I)) or ("no licence words" if t else "no readme or licence")


def cmd_licences(a):
    work = Path(a.work)
    p = work / "licences.json"
    got = json.load(open(p)) if p.exists() else {}
    repos = sorted({j["repo"] for j in json.load(open(a.jobs))} - set(got))
    with cf.ThreadPoolExecutor(a.jobs_n) as ex:
        for r, v in zip(repos, ex.map(lic_of, repos)):
            got[r] = v
    json.dump(got, open(p, "w"), indent=0)
    print(f"{len(got)} repos")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["fetch", "jobs", "licences"])
    ap.add_argument("--hits")
    ap.add_argument("--vendor", help="JSON [{repo, path, brd, sch}] of the vendor boards")
    ap.add_argument("--work", default="/tmp/spike5-corpus/eagle")
    ap.add_argument("--out")
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    if a.cmd == "licences":
        a.jobs, a.jobs_n = a.out, 4
    {"fetch": cmd_fetch, "jobs": cmd_jobs, "licences": cmd_licences}[a.cmd](a)


if __name__ == "__main__":
    main()
