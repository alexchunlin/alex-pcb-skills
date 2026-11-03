#!/usr/bin/env python3
"""Spike 2: replay-bench the corpus `refstat` rows on the archived boards.

  python3 -I tools/spikes/spike2/refstat_bench.py [--rows tools/bench/data/refstat-rows.json] [--out tools/spikes/spike2/refstat-bench.json]

For every attempt in tools/bench/corpus.json with a check run, `pcb check` runs twice with HEAD's tools: the board's own
checks.json, and the same config plus every refstat row. Both reports are scored with replay.py's `score` against
labels.json (scope `rows`), so the delta is recall gained and the refstat fail lines that match no label (false fails, or
true findings nobody labelled: listed for a reader to judge). Scratch under /tmp/alexpcb-bench/spike2-<pid>.
"""
from __future__ import annotations

import argparse, json, os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/bench"))
import replay  # noqa: E402

PCB = ROOT / "skills/kicad-design/scripts/pcb"
DECOUPLING_FEED = ("decoupling", "feeds")


def run_check(spec, run, base: Path, cfg: dict, out: Path, extra_only=None):
    cfg_p = out.with_suffix(".config.json")
    json.dump(cfg, open(cfg_p, "w"), indent=1)
    args = list(run.get("args", []))
    if extra_only and "--only" in args:   # the bench's --only scope (plink: pinmaps,addresses) plus the new kind
        i = args.index("--only") + 1
        args[i] += "," + extra_only
    cmd = [str(PCB), "check", str(base / spec["pcb"]), str(cfg_p), "--out", str(out), "--netlist", str(base / spec["netlist"]),
           *(["--bringup", str(base / spec["bringup"])] if spec.get("bringup") else []), *args]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return json.load(open(out)) if out.exists() else {"rows": [], "error": (p.stdout + p.stderr)[-400:]}


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", default=str(ROOT / "tools/bench/data/refstat-rows.json"))
    ap.add_argument("--out", default=str(ROOT / "tools/spikes/spike2/refstat-bench.json"))
    ap.add_argument("--attempts")
    a = ap.parse_args(argv)
    corpus = json.load(open(ROOT / "tools/bench/corpus.json"))
    labels = json.load(open(ROOT / "tools/bench/labels.json"))
    rows = json.load(open(a.rows))["rows"]
    scratch = Path(f"/tmp/alexpcb-bench/spike2-{os.getpid()}")
    scratch.mkdir(parents=True, exist_ok=True)
    wanted = set(a.attempts.split(",")) if a.attempts else set(corpus["attempts"])
    major_df = [l["id"] for l in labels["labels"] if l["severity"] in ("major", "blocker") and l.get("tool_catchable")
                and any(re.search(r"\^check fail (decoupling|feeds):", loc["pattern"]) for loc in l["locators"])]
    result = {"rows_file": os.path.relpath(a.rows, ROOT), "n_rows": len(rows), "decoupling_feed_majors": major_df, "attempts": {}}
    for name, spec in corpus["attempts"].items():
        if name not in wanted:
            continue
        runs = [r for r in spec["runs"] if r["type"] == "check"]
        if not runs:
            continue
        run = runs[0]
        w = scratch / name
        w.mkdir(exist_ok=True)
        base = replay.unpack(spec, w)
        cfg = json.load(open(ROOT / spec["dir"] / run["config"]))
        rep0 = run_check(spec, run, base, cfg, w / "base.json")
        rep1 = run_check(spec, run, base, {**cfg, "refstat": rows}, w / "refstat.json", extra_only="refstat")
        ent = {}
        for tag, rep in (("base", rep0), ("refstat", rep1)):
            lines = replay.lines_check(rep)
            runs_d = {"check": {"kind": "review", "report": "check", "lines": lines, "error": rep.get("error"), "skipped": None}}
            sc = replay.score(name, runs_d, labels, "rows")
            caught = [l["id"] for l in labels["labels"] if l["attempt"] == name and l["id"] not in sc["missed"] + sc["not_run"] + sc["caught_partial"] + sc["label_errors"]
                      and not l.get("process")]
            ent[tag] = {"recall_fail": sc["recall_fail"], "recall_fw": sc["recall_fw"], "labels": sc["labels"], "false_fails": sc["false_fails"],
                        "missed": sc["missed"], "caught": caught}
        rs = [r for r in rep1.get("rows", []) if r["check"] == "refstat"]
        ent["refstat_rows"] = [{"status": r["status"], "id": r["id"], "msg": r["msg"]} for r in rs]
        ent["refstat_fails"] = [r["id"] for r in rs if r["status"] == "fail"]
        ent["new_catches"] = sorted(set(ent["refstat"]["caught"]) - set(ent["base"]["caught"]))
        result["attempts"][name] = ent
        print(f"{name:24} refstat rows {len(rs):3} (fail {len(ent['refstat_fails'])}, pass {sum(r['status'] == 'pass' for r in rs)})  "
              f"recall fail {ent['base']['recall_fail']} -> {ent['refstat']['recall_fail']}  false fails {ent['base']['false_fails']} -> {ent['refstat']['false_fails']}"
              f"  new catches {ent['new_catches']}")
        for r in rs:
            if r["status"] != "pass":
                print(f"    {r['status']}: {r['id']}: {r['msg'][:160]}")
    agg = {}
    for t in ("base", "refstat"):
        agg[t] = {k: sum(e[t][k] for e in result["attempts"].values()) for k in ("recall_fail", "recall_fw", "labels", "false_fails")}
    agg["new_catches"] = sorted(c for e in result["attempts"].values() for c in e["new_catches"])
    agg["refstat_fails"] = sum(len(e["refstat_fails"]) for e in result["attempts"].values())
    agg["refstat_rows"] = sum(len(e["refstat_rows"]) for e in result["attempts"].values())
    agg["df_majors_caught_base"] = sorted(c for e in result["attempts"].values() for c in e["base"]["caught"] if c in major_df)
    agg["df_majors_caught_refstat_only"] = sorted(c for c in agg["new_catches"] if c in major_df)
    result["all"] = agg
    json.dump(result, open(a.out, "w"), indent=1)
    print(f"ALL: recall fail {agg['base']['recall_fail']} -> {agg['refstat']['recall_fail']} of {agg['base']['labels']}, false fails "
          f"{agg['base']['false_fails']} -> {agg['refstat']['false_fails']}, refstat rows {agg['refstat_rows']} (fail {agg['refstat_fails']}), "
          f"decoupling/feed majors {len(major_df)}: caught by existing rows {len(agg['df_majors_caught_base'])}, new by refstat {len(agg['df_majors_caught_refstat_only'])} -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
