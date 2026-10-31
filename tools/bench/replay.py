#!/usr/bin/env python3
"""Replay bench: score a tools commit against what the reviewers and the fab history found on the archived boards.

No LLM. For each archived board (tools/bench/corpus.json) it makes the pcb runs (drc, check, fab) with the chosen
commit's tools, turns every report into lines, and scores them against tools/bench/labels.json:

  recall_fail / recall_fw   labels whose best matching line is a fail / a fail or warn (severity-weighted: *_w)
  caught_partial            labels only a partial locator matched
  false_fails               fail lines matching no label, known_true_positive or that a `negatives` entry forbids
  noise_warns               warn lines matching no locator
  label_errors              uncaught labels whose report comes from a run that crashed (an error, never a miss)
  not_run                   labels whose report was not made in this scope (regen is verify-only; review-kind runs
                            are out of the designer scope): out of the denominator
  not_catchable             labels marked tool_catchable: false (in the denominator of recall_*; out of *_catchable)

Scopes: `designer` (runs of kind designer) and `rows` (all runs). One JSON row per (commit, attempt) plus ALL.

  python3 -I tools/bench/replay.py                       # HEAD's tools, every attempt (about 2 min)
  python3 -I tools/bench/replay.py --commit <ref>        # another commit's skills/ (git archive into the scratch dir)
  python3 -I tools/bench/replay.py --attempts plink-v1,rung1-zener-a1
  python3 -I tools/bench/replay.py --from-verify /tmp/alexpcb-verify/run-<pid>   # score a verify_all run's reports
  python3 -I tools/bench/replay.py --from-run /tmp/alexpcb-bench/run-<pid>       # rescore (after a label edit)
  python3 -I tools/bench/replay.py table [--results F] [--commit C]
  python3 -I tools/bench/replay.py compare BASE NEW      # the gate: recall not down, false fails and noise not up
  python3 -I tools/bench/replay.py lint                  # labels and corpus consistency

Lines (what locators match; `LINES` below):
  drc    `drc fail|warn plain|packed TYPE N`, `drc fail unconnected N`, `drc info sentinel ...`, `drc info masked N`,
         `drc info capped TYPE`, `drc info errors_total N`
  check  `check STATUS ID: MSG` (status fail, warn, pass, accepted)
  regen  `regen fail|pass verdict V`, `regen fail|pass passN exit RC`, `regen fail ref-vs-pass1 DIFF`,
         `regen fail pass1-vs-pass2 DIFF`, `regen info passN drc KEY N`
  fab    `fab warn cpl_offset REF MM`, `fab fail missing_lcsc REF`, `fab info bom_header H`, `fab info plot explicit-layers N`,
         `fab info files N`
Scratch: /tmp/alexpcb-bench/run-<pid>. Plain python3, standard library.
"""
from __future__ import annotations

import argparse, csv, datetime as dt, json, os, re, shutil, subprocess, sys, tarfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = Path(__file__).resolve().parent
SCRATCH_BASE = Path("/tmp/alexpcb-bench")
SEV_W = {"blocker": 3, "major": 2, "minor": 1}
RANK = {"fail": 3, "warn": 2, "accepted": 1, "pass": 0, "info": 0, None: -1}


def git(*a: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *a], check=True, capture_output=True, text=True).stdout.strip()


def tools_for(ref: str, scratch: Path):
    sha = git("rev-parse", "--short=9", ref + "^{commit}")
    head = git("rev-parse", "--short=9", "HEAD")
    info = {"ref": ref, "commit": sha, "subject": git("log", "-1", "--format=%s", sha)[:100],
            "skills_tree": git("rev-parse", "--short=9", sha + ":skills")}
    if sha == head:
        if git("status", "--porcelain", "--", "skills"):
            info["dirty"] = True
        return ROOT / "skills/kicad-design/scripts/pcb", info
    dest = scratch / ("tools-" + sha)
    dest.mkdir(parents=True, exist_ok=True)
    arc = subprocess.run(["git", "-C", str(ROOT), "archive", sha, "skills"], check=True, capture_output=True).stdout
    p = dest / "skills.tar"
    p.write_bytes(arc)
    with tarfile.open(p) as t:
        try:
            t.extractall(dest, filter="data")
        except TypeError:
            t.extractall(dest)
    p.unlink()
    return dest / "skills/kicad-design/scripts/pcb", info


# ------------------------------------------------------------------ lines
def lines_drc(d: dict) -> list[str]:
    out = []
    for scope in ("plain", "packed"):
        c = d.get(scope)
        if not c:
            continue
        for sev, st in (("error", "fail"), ("warning", "warn")):
            for t, n in sorted(c.get("by_type", {}).get(sev, {}).items()):
                out.append(f"drc {st} {scope} {t} {n}")
    p = d.get("plain", {})
    if p.get("unconnected"):
        out.append(f"drc fail unconnected {p['unconnected']}")
    out.append(f"drc info sentinel {d.get('sentinel')}")
    out.append(f"drc info masked {len(d.get('masked_by_raw_pack', []))}")
    for t in d.get("capped_types", []):
        out.append(f"drc info capped {t}")
    out.append(f"drc info errors_total {d.get('errors_total')}")
    return out


def lines_check(d: dict) -> list[str]:
    return [f"check {r['status']} {r['id']}: {r['msg']}" for r in d.get("rows", [])]


def lines_regen(d: dict) -> list[str]:
    out = [f"regen {'pass' if d.get('verdict') == 'REGENERATES' else 'fail'} verdict {d.get('verdict')}"]
    for n in (1, 2):
        p = d.get(f"pass{n}", {})
        rc = p.get("cmd_exit")
        out.append(f"regen {'pass' if rc == 0 else 'fail'} pass{n} exit {rc}")
        for k, v in (p.get("drc") or {}).items():
            if isinstance(v, (int, float)):
                out.append(f"regen info pass{n} drc {k} {v}")
    for x in d.get("diff_ref_pass1", []):
        out.append(f"regen fail ref-vs-pass1 {x}")
    for x in d.get("diff_pass1_pass2", []):
        out.append(f"regen fail pass1-vs-pass2 {x}")
    return out


def lines_fab(d: dict) -> list[str]:
    out = []
    for ref, mm in sorted(d.get("cpl_origin_offsets_mm", {}).items()):
        out.append(f"fab warn cpl_offset {ref} {mm:.2f}")
    for ref in d.get("bom_missing_lcsc", []):
        out.append(f"fab fail missing_lcsc {ref}")
    bom = d.get("files", {}).get("bom")
    if bom and os.path.exists(bom):
        out.append("fab info bom_header " + open(bom).readline().strip())
    out.append(f"fab info plot explicit-layers {len(d.get('layers', []))}")
    out.append(f"fab info files {len(d.get('files', {}).get('gerbers', {}))}")
    return out


LINES = {"drc": lines_drc, "check": lines_check, "verify-only": lines_regen, "regen": lines_regen, "fab": lines_fab}
REPORT_OF = {"drc": "drc", "check": "check", "verify-only": "regen", "regen": "regen", "fab": "fab"}


# ------------------------------------------------------------------ runs
def unpack(spec: dict, w: Path) -> Path:
    src = ROOT / spec["dir"]
    if spec.get("tar"):
        with tarfile.open(src / spec["tar"]) as t:
            try:
                t.extractall(w, filter="data")
            except TypeError:
                t.extractall(w)
        return w
    shutil.copytree(src, w, dirs_exist_ok=True)
    return w


def run_attempt(name: str, spec: dict, pcb: Path, scratch: Path) -> dict:
    w = scratch / name
    w.mkdir(parents=True, exist_ok=True)
    base = unpack(spec, w)
    board = base / spec["pcb"]
    res = {}
    for r in spec["runs"]:
        if r["type"] == "verify-only":
            res[r["id"]] = {"out": None, "skipped": "verify-only (use --from-verify)"}
            continue
        out_dir = w / ("run-" + r["id"])
        out_dir.mkdir(exist_ok=True)
        t0 = time.time()
        if r["type"] == "drc":
            out = out_dir / "drc.json"
            cmd = [str(pcb), "drc", str(board), "--out", str(out_dir), *r.get("args", [])]
        elif r["type"] == "check":
            out = out_dir / "pcbcheck.json"
            cmd = [str(pcb), "check", str(board), str(ROOT / spec["dir"] / r["config"]), "--out", str(out),
                   "--netlist", str(base / spec["netlist"]), *(["--bringup", str(base / spec["bringup"])] if spec.get("bringup") else []),
                   *r.get("args", [])]
        elif r["type"] == "fab":
            out = out_dir / "fab.json"
            cmd = [str(pcb), "fab", str(board), "--out", str(out_dir), "--no-render", *r.get("args", [])]
        else:
            raise ValueError(r["type"])
        p = subprocess.run(cmd, capture_output=True, text=True)
        (out_dir / "log.txt").write_text(p.stdout + p.stderr)
        res[r["id"]] = {"out": str(out) if out.exists() else None, "rc": p.returncode, "runtime_s": round(time.time() - t0, 1),
                        "error": None if out.exists() else (p.stdout + p.stderr)[-400:]}
    return res


def collect(spec: dict, res: dict) -> dict:
    """{run_id: {"kind", "report", "lines", "error"}}"""
    out = {}
    for r in spec["runs"]:
        x = res.get(r["id"], {})
        rep = REPORT_OF[r["type"]]
        entry = {"kind": r["kind"], "report": rep, "lines": [], "error": None if x.get("skipped") else x.get("error"), "skipped": x.get("skipped")}
        if x.get("out"):
            try:
                entry["lines"] = LINES[r["type"]](json.load(open(x["out"])))
            except (OSError, ValueError, KeyError) as e:
                entry["error"] = f"unreadable report: {e}"
        out[r["id"]] = entry
    return out


# ------------------------------------------------------------------ scoring
def status_of(line: str) -> str:
    return line.split(" ", 2)[1]


def score(attempt: str, runs: dict, labels: dict, scope: str) -> dict:
    kinds = {"designer"} if scope == "designer" else {"designer", "review"}
    lines = [(rid, r["report"], l) for rid, r in runs.items() if r["kind"] in kinds for l in r["lines"]]
    errors = {r["report"] for r in runs.values() if r["kind"] in kinds and r["error"] and not r.get("skipped")}
    present = {r["report"] for r in runs.values() if r["kind"] in kinds and (r["lines"] or r["error"]) and not r.get("skipped")}
    # a label whose every report comes from a run not made in this scope (verify-only, or review-kind under the
    # designer scope) is out of the denominator: not_run, never a miss
    labs, not_run = [], []
    for l in labels["labels"]:
        if l["attempt"] != attempt or l.get("process"):
            continue
        reps = {loc["report"] for loc in l["locators"]}
        if reps and not reps & present:
            not_run.append(l["id"])
        else:
            labs.append(l)
    caught_fail = caught_fw = 0
    w_fail = w_fw = w_tot = 0
    partial, errs, catchable, miss = [], [], 0, []
    matched_lines = set()
    for lab in labs:
        w = SEV_W[lab["severity"]]
        w_tot += w
        if lab.get("tool_catchable"):
            catchable += 1
        best, best_partial = None, False
        for loc in lab["locators"]:
            rx = re.compile(loc["pattern"])
            for rid, rep, l in lines:
                if rep == loc["report"] and rx.search(l):
                    st = status_of(l)
                    matched_lines.add((rid, l))
                    if RANK[st] > RANK[best]:
                        best, best_partial = st, bool(loc.get("partial"))
        if best in ("fail", "warn", "accepted") and best_partial:
            partial.append(lab["id"])
            continue
        if best == "fail":
            caught_fail += 1; caught_fw += 1; w_fail += w; w_fw += w
        elif best in ("warn", "accepted"):
            caught_fw += 1; w_fw += w
        else:
            reps = {loc["report"] for loc in lab["locators"]}
            if reps & errors:
                errs.append(lab["id"])
            else:
                miss.append(lab["id"])
    ktp = [(k["report"], re.compile(k["pattern"])) for k in labels.get("known_true_positives", []) if k["attempt"] == attempt]
    neg = [(k["report"], re.compile(k["pattern"])) for k in labels.get("negatives", []) if k["attempt"] == attempt]
    false_fails, noise = [], []
    for rid, rep, l in lines:
        st = status_of(l)
        if st == "fail":
            if any(rep == nr and nrx.search(l) for nr, nrx in neg):
                false_fails.append(l); continue
            if (rid, l) in matched_lines or any(rep == kr and krx.search(l) for kr, krx in ktp):
                continue
            false_fails.append(l)
        elif st == "warn" and (rid, l) not in matched_lines and not any(rep == kr and krx.search(l) for kr, krx in ktp):
            noise.append(l)
    n = len(labs)
    return {"labels": n, "catchable": catchable, "recall_fail": caught_fail, "recall_fw": caught_fw,
            "recall_fail_w": w_fail, "recall_fw_w": w_fw, "weight_total": w_tot, "caught_partial": partial,
            "missed": miss, "not_run": not_run, "label_errors": errs, "false_fails": len(false_fails), "false_fail_list": false_fails,
            "noise_warns": len(noise), "noise_warn_list": noise, "lines": len(lines)}


def summarize(rows: list[dict]) -> dict:
    agg = {"attempt": "ALL"}
    for scope in ("designer", "rows"):
        s = {k: 0 for k in ("labels", "catchable", "recall_fail", "recall_fw", "recall_fail_w", "recall_fw_w", "weight_total", "false_fails", "noise_warns")}
        for r in rows:
            for k in s:
                s[k] += r[scope][k]
        s["label_errors"] = sum(len(r[scope]["label_errors"]) for r in rows)
        agg[scope] = s
    return agg


# ------------------------------------------------------------------ main modes
def lint(corpus: dict, labels: dict) -> list[str]:
    bad = []
    attempts = corpus["attempts"]
    for lab in labels["labels"]:
        if lab["attempt"] not in attempts:
            bad.append(f"{lab['id']}: attempt {lab['attempt']} not in corpus")
            continue
        reps = {REPORT_OF[r["type"]] for r in attempts[lab["attempt"]]["runs"]}
        if lab["severity"] not in SEV_W:
            bad.append(f"{lab['id']}: severity {lab['severity']}")
        if lab.get("tool_catchable") and not lab["locators"]:
            bad.append(f"{lab['id']}: tool_catchable but no locator")
        for loc in lab["locators"]:
            if loc["report"] not in reps:
                bad.append(f"{lab['id']}: report {loc['report']} has no run in {lab['attempt']}")
            try:
                re.compile(loc["pattern"])
            except re.error as e:
                bad.append(f"{lab['id']}: bad pattern {e}")
            if not re.match(r"\^?(drc|check|regen|fab) ", loc["pattern"]):
                bad.append(f"{lab['id']}: pattern does not start with the report name: {loc['pattern']}")
    ids = [l["id"] for l in labels["labels"]]
    if len(set(ids)) != len(ids):
        bad.append("duplicate label ids")
    for k in labels.get("known_true_positives", []) + labels.get("negatives", []):
        if k["attempt"] not in attempts:
            bad.append(f"ktp/negative: attempt {k['attempt']} not in corpus")
    for name, spec in attempts.items():
        if not (ROOT / spec["dir"]).exists():
            bad.append(f"{name}: dir {spec['dir']} missing")
        if spec.get("tar") and not (ROOT / spec["dir"] / spec["tar"]).exists():
            bad.append(f"{name}: tar {spec['tar']} missing")
    return bad


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", nargs="?", default="run", choices=["run", "table", "compare", "lint"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--commit", default="HEAD")
    ap.add_argument("--attempts")
    ap.add_argument("--from-verify")
    ap.add_argument("--from-run")
    ap.add_argument("--results", default=str(BENCH / "results/replay.jsonl"))
    ap.add_argument("--no-save", action="store_true")
    a = ap.parse_args(argv)
    corpus = json.load(open(BENCH / "corpus.json"))
    labels = json.load(open(BENCH / "labels.json"))
    if a.mode == "lint":
        bad = lint(corpus, labels)
        print("\n".join(bad) if bad else f"lint ok: {len(labels['labels'])} labels, {len(corpus['attempts'])} attempts")
        return 1 if bad else 0
    if a.mode == "table":
        rows = [json.loads(l) for l in open(a.results)] if os.path.exists(a.results) else []
        if a.commit != "HEAD":
            rows = [r for r in rows if r["commit"].startswith(a.commit)]
        print(f"{'commit':10} {'attempt':16} {'labels':>6} {'rf':>3} {'rfw':>4} {'ff':>3} {'noise':>5}  {'rf_rows':>7} {'ff_rows':>7}  when")
        for r in rows:
            d, w = r["designer"], r["rows"]
            print(f"{r['commit'][:9]:10} {r['attempt']:16} {d['labels']:6} {d['recall_fail']:3} {d['recall_fw']:4} {d['false_fails']:3} {d['noise_warns']:5}  "
                  f"{w['recall_fail']:7} {w['false_fails']:7}  {r['when'][:16]}")
        return 0
    if a.mode == "compare":
        if len(a.args) != 2:
            sys.exit("compare BASE NEW")
        rows = [json.loads(l) for l in open(a.results)]
        def pick(c):
            return {r["attempt"]: r for r in rows if r["commit"].startswith(c)}
        b, n = pick(a.args[0]), pick(a.args[1])
        worse = []
        for att in sorted(set(b) & set(n)):
            for scope in ("designer", "rows"):
                x, y = b[att][scope], n[att][scope]
                if x["labels"] != y["labels"]:
                    worse.append(f"{att} {scope}: label sets differ ({x['labels']} vs {y['labels']}); rescore with --from-run")
                if y["recall_fw"] < x["recall_fw"] or y["recall_fail"] < x["recall_fail"]:
                    worse.append(f"{att} {scope}: recall down {x['recall_fail']}/{x['recall_fw']} -> {y['recall_fail']}/{y['recall_fw']}")
                if y["false_fails"] > x["false_fails"]:
                    worse.append(f"{att} {scope}: false fails up {x['false_fails']} -> {y['false_fails']}")
                if y["noise_warns"] > x["noise_warns"]:
                    worse.append(f"{att} {scope}: noise up {x['noise_warns']} -> {y['noise_warns']}")
                if y["label_errors"]:
                    worse.append(f"{att} {scope}: label errors {y['label_errors']}")
        missing = sorted(set(b) ^ set(n))
        if missing:
            worse.append(f"attempts only in one run: {missing}")
        print("\n".join(worse) if worse else f"compare {a.args[0]} -> {a.args[1]}: no regression over {len(set(b) & set(n))} attempts")
        return 1 if worse else 0
    bad = lint(corpus, labels)
    if bad:
        sys.exit("lint:\n" + "\n".join(bad))
    scratch = SCRATCH_BASE / f"run-{os.getpid()}"
    scratch.mkdir(parents=True, exist_ok=True)
    wanted = set(a.attempts.split(",")) if a.attempts else set(corpus["attempts"])
    rows = []
    if a.from_verify:
        vd = Path(a.from_verify)
        meta = json.load(open(vd / "meta.json"))
        info = {"commit": meta.get("commit") or "unknown", "dirty": meta.get("dirty"), "ref": "verify"}
        for name, spec in corpus["attempts"].items():
            if name not in wanted:
                continue
            res = {}
            for r in spec["runs"]:
                vo = r.get("verify_out")
                p = vd / vo if vo else None
                res[r["id"]] = {"out": str(p) if p and p.exists() else None, "error": None if (p and p.exists()) else "not in this verify run", "skipped": None if vo else "no verify_out"}
            runs = collect(spec, res)
            rows.append({"attempt": name, "runs": {k: {"lines": len(v["lines"]), "error": v["error"], "skipped": v.get("skipped")} for k, v in runs.items()},
                         "designer": score(name, runs, labels, "designer"), "rows": score(name, runs, labels, "rows")})
    elif a.from_run:
        rd = Path(a.from_run)
        info = json.load(open(rd / "tools.json"))
        for name, spec in corpus["attempts"].items():
            if name not in wanted or not (rd / name / "runs.json").exists():
                continue
            res = json.load(open(rd / name / "runs.json"))
            runs = collect(spec, res)
            rows.append({"attempt": name, "runs": {k: {"lines": len(v["lines"]), "error": v["error"]} for k, v in runs.items()},
                         "designer": score(name, runs, labels, "designer"), "rows": score(name, runs, labels, "rows")})
    else:
        pcb, info = tools_for(a.commit, scratch)
        json.dump(info, open(scratch / "tools.json", "w"), indent=1)
        print(f"replay: tools {info['commit']} ({info['subject']}){' DIRTY' if info.get('dirty') else ''} -> {scratch}")
        for name, spec in corpus["attempts"].items():
            if name not in wanted:
                continue
            t0 = time.time()
            res = run_attempt(name, spec, pcb, scratch)
            json.dump(res, open(scratch / name / "runs.json", "w"), indent=1)
            runs = collect(spec, res)
            rows.append({"attempt": name, "runs": {k: {"lines": len(v["lines"]), "error": v["error"], "runtime_s": res[k].get("runtime_s")} for k, v in runs.items()},
                         "designer": score(name, runs, labels, "designer"), "rows": score(name, runs, labels, "rows")})
            print(f"  {name}: {time.time() - t0:.0f} s")
    when = dt.datetime.now().isoformat(timespec="seconds")
    out_rows = []
    for r in rows + [summarize(rows)]:
        r.update({"commit": info["commit"], "dirty": info.get("dirty", False), "when": when, "source": a.from_verify or a.from_run or "run"})
        out_rows.append(r)
        d, w = r["designer"], r["rows"]
        print(f"{r['attempt']:16} labels {d['labels']:2} (catchable {d['catchable']})  recall fail {d['recall_fail']} fw {d['recall_fw']}  "
              f"weighted {d['recall_fw_w']}/{d['weight_total']}  false fails {d['false_fails']}  noise {d['noise_warns']}"
              f"{'  errors ' + str(d['label_errors']) if d.get('label_errors') else ''}"
              f"{'  missed ' + str(d['missed']) if d.get('missed') else ''}"
              f"{'  not run ' + str(d['not_run']) if d.get('not_run') else ''}"
              f"{'  partial ' + str(d['caught_partial']) if d.get('caught_partial') else ''}  | rows: fail {w['recall_fail']} fw {w['recall_fw']} ff {w['false_fails']}")
        for l in d.get("false_fail_list", [])[:6]:
            print(f"    false fail: {l[:140]}")
        for l in d.get("noise_warn_list", [])[:6]:
            print(f"    noise: {l[:140]}")
    if not a.no_save:
        os.makedirs(os.path.dirname(a.results), exist_ok=True)
        with open(a.results, "a") as f:
            for r in out_rows:
                f.write(json.dumps(r) + "\n")
        print(f"appended {len(out_rows)} rows to {a.results}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
