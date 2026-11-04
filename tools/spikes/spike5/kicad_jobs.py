#!/usr/bin/env python3
"""Spike 5: role-measure jobs for the KiCad corpus siblings, from tools/bench/data/corpus-class-index.jsonl.

  python3 -I tools/spikes/spike5/kicad_jobs.py --work /tmp/spike5-corpus/kicad --out JOBS.json [--classes imu6,hbridge]

One job per (row key, ref) whose board matched. Dedupe by (repo, part, ref) happens in the analysis, as in spike 2.
"""
import argparse, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--work", default="/tmp/spike5-corpus/kicad")
ap.add_argument("--out", required=True)
ap.add_argument("--classes", default="imu6,hbridge")
a = ap.parse_args()
tab = json.load(open(ROOT / "tools/bench/data/class-table.json"))["classes"]
cls = {p: c for c, v in tab.items() for p in v if c in a.classes.split(",")}
rows = [json.loads(l) for l in open(ROOT / "tools/bench/data/corpus-class-index.jsonl")]
jobs, seen = [], set()
n = {"hits": 0, "matched": 0}
for r in rows:
    if r["part"] not in cls:
        continue
    n["hits"] += 1
    if not (r.get("board") or {}).get("match"):
        continue
    n["matched"] += 1
    pcb = Path(a.work) / "pcb" / f"{r['key']}.kicad_pcb"
    if not pcb.exists():
        continue
    for ref in r["refs"]:
        k = (r["key"], ref, r["part"])
        if k in seen:
            continue
        seen.add(k)
        jobs.append({"key": f"{r['key']}:{r['part']}", "ref": ref, "part": r["part"], "cls": cls[r["part"]], "fmt": "kicad", "board": str(pcb), "repo": r["repo"], "org": "kicad",
                     "rx": tab[cls[r["part"]]][r["part"]], "licence": r.get("licence"), "sch_version": r.get("sch_version"), "path": r["file"]})
json.dump(jobs, open(a.out, "w"))
print(n, len(jobs), "jobs")
