#!/usr/bin/env python3
"""Spike 6 charts from results.json: uv run --with matplotlib python3 -I tools/spikes/spike6/charts.py"""
import json, pathlib, statistics, sys
sys.path.insert(0, "/Users/alxchunlin/code-stuff/alex-style-guide/matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import alex_style as ax
HERE = pathlib.Path(__file__).resolve().parent
IMG = HERE.parents[2] / "docs/img/spikes"
d = json.load(open(HERE / "results.json"))
p = ax.use("dark")
cols = p.get("series") or p.get("categorical") or list(plt.rcParams["axes.prop_cycle"].by_key()["color"])
A, B = cols[0], cols[1]
panels = [("vin_mw", "VIN LOSS", "mW, lower is better"), ("layout", "BLIND LAYOUT SCORE", "1-10, higher is better"),
          ("coh", "COHESION", "by Zener module"), ("tok", "TOKENS", "thousands"), ("min", "WALL TIME", "minutes")]
fig, axs = plt.subplots(1, 5, figsize=(13, 3.8))
for a, (k, t, sub) in zip(axs, panels):
    for i, (arm, c) in enumerate((("a", A), ("b", B))):
        v = [r[k] / (1000 if k == "tok" else 1) for r in d["ab"] if r["arm"] == arm]
        a.scatter([i + o for o in (-0.08, 0, 0.08)], v, color=c, s=46, zorder=3)
        m = statistics.median(v)
        a.plot([i - 0.25, i + 0.25], [m, m], color=c, lw=2)
        a.annotate(f"{m:g}", (i + 0.28, m), va="center", fontsize=9, color=c)
    a.set_xlim(-0.6, 1.8); a.set_xticks([0, 1]); a.set_xticklabels(["ONE PASS", "BLOCKS"], fontsize=8)
    a.set_title(t, fontsize=10, loc="left"); a.set_ylabel(sub, fontsize=8); a.set_xlabel("Arm", fontsize=8)
    a.margins(y=0.2)
fig.tight_layout()
ax.save(fig, IMG / "6-ab-judges.png", dpi=150)

br = d["breakouts"]
fig, a = plt.subplots(figsize=(9, 3.8))
keys = ["electrical", "manufacturability", "documentation", "layout"]
w = 0.19
for j, k in enumerate(keys):
    a.bar([i + (j - 1.5) * w for i in range(len(br))], [b[k] for b in br], w, label=k.upper(), color=cols[j % len(cols)])
a.set_xticks(range(len(br))); a.set_xticklabels([b["board"] for b in br]); a.set_ylim(0, 10); a.set_ylabel("Review score"); a.set_xlabel("Board")
a.legend(ncol=4, fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.14))
fig.tight_layout()
ax.save(fig, IMG / "6-breakouts.png", dpi=150)
