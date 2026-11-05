#!/usr/bin/env python3
"""Spike 5: instances per class and part, KiCad and otherwise. Counts only.

  python3 -I tools/spikes/spike5/instances.py [--roles /tmp/spike5/h2/roles.jsonl]      # writes instances-summary.json, prints markdown
"""
import argparse, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from h2 import family  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--roles", default="/tmp/spike5/h2/roles.jsonl")
a = ap.parse_args()
tab = json.load(open(ROOT / "tools/bench/data/class-table.json"))
cls_of = {p: c for c, v in tab["classes"].items() for p in v}
rows = [json.loads(l) for l in open(ROOT / "tools/bench/data/corpus-class-index.jsonl")]
inst = [json.loads(l) for l in open(a.roles)]
out = {"classes": {}, "parts": {}, "labels": dict(Counter(f"{v['source']}" for v in tab["labels"].values()))}
for c in tab["classes"]:
    rs = [r for r in rows if cls_of[r["part"]] == c]
    ms = [r for r in inst if r["cls"] == c]
    out["classes"][c] = {"projects": len({r["key"] for r in rs}), "repos": len({r["repo"] for r in rs}), "with_kicad_pcb": sum(r["has_pcb_ext"] for r in rs),
                         "board_matched": sum(bool((r.get("board") or {}).get("match")) for r in rs),
                         "measured": dict(Counter(r.get("org") or "kicad" for r in ms)),
                         "measured_repos": len({r["repo"] for r in ms}), "packages": dict(Counter(family(r["pkg"]) for r in ms).most_common(8))}
    for p in tab["classes"][c]:
        x = [r for r in rs if r["part"] == p]
        m = [r for r in ms if r["part"] == p]
        if x or m:
            out["parts"][p] = {"class": c, "projects": len({r["key"] for r in x}), "repos": len({r["repo"] for r in x}), "kicad_measured": sum((r.get("org") or "kicad") == "kicad" for r in m),
                               "eagle_measured": sum((r.get("org") or "kicad") != "kicad" for r in m)}
# the frame check: pad 1 after the canonical turn, per package and source, before anything pools
import statistics as st  # noqa: E402
fr = {}
for r in inst:
    fam = family(r["pkg"])
    if fam in ("LGA-14", "HTSSOP-16") and not r.get("pad1_central"):
        fr.setdefault((fam, r.get("org") or "kicad"), []).append(r)
out["frame"] = {}
for (fam, org), rs in sorted(fr.items()):
    xs, ys = [r["pad1"][0] for r in rs], [r["pad1"][1] for r in rs]
    out["frame"][f"{fam}|{org}"] = {"n": len(rs), "pad1_x_median": st.median(xs), "pad1_y_median": st.median(ys), "pad1_top_left": sum(x < 0 and y < 0 for x, y in zip(xs, ys)), "turned": dict(Counter(str(r["turn"]) for r in rs))}
json.dump(out, open(HERE / "instances-summary.json", "w"), indent=1)
for k, v in out["frame"].items():
    print(k, v)
print("| Class | Projects | Repos | With a board file | Board matched | Measured: KiCad / Adafruit / SparkFun / third-party Eagle |\n|---|---:|---:|---:|---:|---|")
for c, v in out["classes"].items():
    m = v["measured"]
    print(f"| `{c}` | {v['projects']:,} | {v['repos']:,} | {v['with_kicad_pcb']:,} | {v['board_matched']:,} | {m.get('kicad', 0)} / {m.get('adafruit', 0)} / {m.get('sparkfun', 0)} / {m.get('third-party', 0)} |")
for c in ("imu6", "hbridge"):
    t = sorted(((p, v) for p, v in out["parts"].items() if v["class"] == c), key=lambda kv: -(kv[1]["kicad_measured"] + kv[1]["eagle_measured"]))
    print(c, ", ".join(f"{p} {v['kicad_measured']}+{v['eagle_measured']}" for p, v in t if v["kicad_measured"] + v["eagle_measured"]))
    print(out["classes"][c]["packages"])
