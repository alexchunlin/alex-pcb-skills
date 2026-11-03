#!/usr/bin/env python3
"""Spike 2 rev-diff mining: commits that touch a KiCad board or schematic with a fix-like message, read through the API.

  python3 -I tools/corpus/revdiff.py repos   [--n 200]      # code search on .kicad_pcb, split by file size (10/min)
  python3 -I tools/corpus/revdiff.py commits                # commits?path= on each board and its sibling schematics
  python3 -I tools/corpus/revdiff.py fetch   [--max 150]    # the keyword commits' diffs (files[].patch), one call each
  python3 -I tools/corpus/revdiff.py digest                 # one short text per commit for the triage
  python3 -I tools/corpus/revdiff.py summary                # counts and the kinds table from revdiff-triage.jsonl

API responses are untrusted data and stay under --work (default /tmp/spike2-corpus/revdiff); nothing in them is run.
The committed output is tools/bench/data/revdiff-triage.jsonl (one judgement per commit read, no diff text).
Code search indexes only default branches and files under 384 KB, so large boards are invisible to step 1.
"""
from __future__ import annotations

import argparse, json, random, re, subprocess, sys, time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRIAGE = ROOT / "tools/bench/data/revdiff-triage.jsonl"
KEYWORDS = re.compile(r"\b(fix|rev|errata|bodge|rework|wrong|swap|reversed)", re.I)
SLICES = ["1..20000", "20000..40000", "40000..80000", "80000..120000", "120000..160000", "160000..240000", "240000..384000"]


def gh(path: str, params=(), accept=None, tries=4):
    cmd = ["gh", "api", "-X", "GET", path] + [x for k, v in params for x in ("-f", f"{k}={v}")]
    if accept:
        cmd += ["-H", f"Accept: {accept}"]
    for k in range(tries):
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode == 0:
            return json.loads(p.stdout) if not accept or "json" in accept else p.stdout
        if "rate limit" in (p.stdout + p.stderr).lower() or "403" in p.stderr or "429" in p.stderr:
            time.sleep(65)
            continue
        if "404" in p.stderr or "409" in p.stderr or "422" in p.stderr:
            return None
        time.sleep(5)
    return None


def cmd_repos(a, work):
    out = work / "repos.json"
    found = {r["repo"]: r for r in json.load(open(out))} if out.exists() else {}   # extending keeps the first set, in order
    per_slice = {}
    for sl in SLICES:
        lst = []
        for page in range(a.page_from, a.page_from + a.pages):
            d = gh("search/code", [("q", f"footprint extension:kicad_pcb size:{sl}"), ("per_page", "100"), ("page", str(page))])
            time.sleep(6.5)   # code search: 10 requests per minute
            if not d:
                break
            for it in d.get("items", []):
                repo = it["repository"]
                if repo.get("fork"):
                    continue
                lst.append((repo["full_name"], it["path"], sl, d.get("total_count")))
        per_slice[sl] = lst
        print(f"slice {sl}: {len(lst)} board files", flush=True)
    # round-robin over the slices so every board size is represented
    i = 0
    while len(found) < a.n and any(per_slice.values()):
        sl = SLICES[i % len(SLICES)]; i += 1
        while per_slice[sl]:
            name, path, s, tot = per_slice[sl].pop(0)
            if name not in found:
                found[name] = {"repo": name, "board": path, "slice": s, "slice_total": tot, "batch": a.page_from}
                break
    json.dump(list(found.values()), open(out, "w"), indent=1)
    print(f"{len(found)} repos -> {out}")


def cmd_commits(a, work):
    repos = json.load(open(work / "repos.json"))
    out = work / "commits.jsonl"
    done = {json.loads(l)["repo"] for l in open(out)} if out.exists() else set()
    with open(out, "a") as f:
        for r in repos:
            if r["repo"] in done:
                continue
            stem = r["board"][:-len(".kicad_pcb")]
            paths = [r["board"], stem + ".kicad_sch", stem + ".sch"]
            commits = {}
            for p in paths:
                d = gh(f"repos/{r['repo']}/commits", [("path", p), ("per_page", "100")]) or []
                for c in d:
                    x = commits.setdefault(c["sha"], {"sha": c["sha"], "message": c["commit"]["message"][:500],
                                                      "date": c["commit"]["author"]["date"], "paths": [],
                                                      "parents": len(c.get("parents", []))})
                    x["paths"].append(p)
            rec = {"repo": r["repo"], "board": r["board"], "n_commits": len(commits), "commits": list(commits.values())}
            f.write(json.dumps(rec) + "\n"); f.flush()
    rows = [json.loads(l) for l in open(out)]
    n = sum(x["n_commits"] for x in rows)
    kw = sum(1 for x in rows for c in x["commits"] if KEYWORDS.search(c["message"]) and c["parents"] == 1)
    print(f"{len(rows)} repos, {n} commits on the board or its schematic, {kw} keyword matches (non-merge)")


def cmd_fetch(a, work):
    rows = [json.loads(l) for l in open(work / "commits.jsonl")]
    cands = [(x["repo"], c) for x in rows for c in x["commits"] if KEYWORDS.search(c["message"]) and c["parents"] == 1]
    random.Random(2).shuffle(cands)
    # at most 3 per repo so one busy repo does not fill the sample
    per, pick = Counter(), []
    for repo, c in cands:
        if per[repo] < 3:
            pick.append((repo, c)); per[repo] += 1
    pick = pick[:a.max]
    d = work / "commits"
    d.mkdir(exist_ok=True)
    for repo, c in pick:
        p = d / f"{repo.replace('/', '__')}__{c['sha'][:12]}.json"
        if p.exists():
            continue
        j = gh(f"repos/{repo}/commits/{c['sha']}")
        if not j:
            continue
        files = [{"filename": f["filename"], "status": f["status"], "additions": f["additions"], "deletions": f["deletions"],
                  "patch": (f.get("patch") or "")[:60000], "patch_missing": "patch" not in f} for f in j.get("files", [])]
        json.dump({"repo": repo, "sha": c["sha"], "message": j["commit"]["message"], "date": c["date"],
                   "url": j.get("html_url"), "files": files}, open(p, "w"))
    print(f"{len(cands)} keyword commits, {len(pick)} sampled (<= 3 per repo), fetched under {d}")


SCH_KEYS = re.compile(r'\(property "(Reference|Value|Footprint)" "([^"]*)"|\(lib_id "([^"]*)"|\((global_label|label|hierarchical_label) "([^"]*)"|'
                      r'^F [0-3] "([^"]*)"|^L (\S+ \S+)|\(footprint "([^"]*)"|\(net \d+ "([^"]*)"|\(fp_text (reference|value) "?([^"\s]*)')


def condense(patch: str, limit=2500):
    """The semantic lines of a KiCad diff: references, values, footprints, lib_ids, labels, nets, plus counts."""
    add, rem = Counter(), Counter()
    seg = 0; trk = Counter()
    for line in patch.splitlines():
        if line.startswith("@@"):
            seg += 1; continue
        if not line or line[0] not in "+-":
            continue
        body = line[1:].strip()
        for kind in ("segment", "via", "zone", "arc", "gr_line", "fp_line", "wire", "junction", "pad"):
            if body.startswith(f"({kind}"):
                trk[(line[0], kind)] += 1
        m = SCH_KEYS.search(body)
        if m:
            txt = body[:140]
            (add if line[0] == "+" else rem)[txt] += 1
    out = [f"hunks {seg}; " + ", ".join(f"{s}{k} x{n}" for (s, k), n in sorted(trk.items()))]
    for t in rem:
        if t not in add:
            out.append(f"- {t}")
    for t in add:
        if t not in rem:
            out.append(f"+ {t}")
    s = "\n".join(out)
    return s[:limit] + ("\n[...]" if len(s) > limit else "")


def cmd_digest(a, work):
    d = work / "commits"
    outd = work / "digests"
    outd.mkdir(exist_ok=True)
    n = 0
    for p in sorted(d.glob("*.json")):
        j = json.load(open(p))
        lines = [f"REPO {j['repo']}", f"URL {j['url']}", f"DATE {j['date']}", "MESSAGE:", j["message"][:1500], "FILES:"]
        for f in j["files"][:40]:
            lines.append(f"  {f['status']:8} +{f['additions']} -{f['deletions']} {f['filename']}" + (" (patch not returned)" if f["patch_missing"] else ""))
        for f in j["files"]:
            if re.search(r"\.(kicad_sch|sch|kicad_pcb)$", f["filename"]) and f["patch"]:
                lines.append(f"DIFF {f['filename']} (condensed: semantic lines only)")
                lines.append(condense(f["patch"]))
            elif re.search(r"\.(md|txt|rst)$", f["filename"], re.I) and f["patch"]:
                lines.append(f"DIFF {f['filename']}")
                lines.append(f["patch"][:1500])
        (outd / (p.stem + ".txt")).write_text("\n".join(lines))
        n += 1
    print(f"{n} digests in {outd}")


def cmd_summary(a, work):
    rows = [json.loads(l) for l in open(TRIAGE)]
    real = [r for r in rows if r["real_fix"]]
    print(f"{len(rows)} read, {len(real)} real post-build fixes ({len(real) / max(1, len(rows)):.2f})")
    for k, n in Counter(r["kind"] for r in real).most_common():
        ex = [r for r in real if r["kind"] == k]
        print(f"  {k:28} {n:3}  catchable {sum(r['tool_catchable'] for r in ex)}  rows: {Counter(r['row'] for r in ex).most_common(3)}")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["repos", "commits", "fetch", "digest", "summary"])
    ap.add_argument("--work", default="/tmp/spike2-corpus/revdiff")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--max", type=int, default=150)
    ap.add_argument("--pages", type=int, default=2, help="code search pages per size slice")
    ap.add_argument("--page-from", type=int, default=1, help="first page (3 to extend a first run of 2 pages)")
    a = ap.parse_args(argv)
    work = Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    {"repos": cmd_repos, "commits": cmd_commits, "fetch": cmd_fetch, "digest": cmd_digest, "summary": cmd_summary}[a.mode](a, work)


if __name__ == "__main__":
    main(sys.argv[1:])
