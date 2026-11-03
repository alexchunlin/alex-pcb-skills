"""Spike #3 charts, from the results JSON in tools/spikes/spike3/results/:
  docs/img/spikes/3-irdrop-vs-feeds.png   the irdrop row's worst ratio at each feed/thermal label, and fails on the Plink as built
  docs/img/spikes/3-c8-catch.png          C8: fraction of planted bugs each kind's own row catches
Run: <repo>/.venv/bin/python3 tools/spikes/spike3/charts.py   (matplotlib; alex-style from ~/code-stuff/alex-style-guide)
"""
import json, re, sys
from pathlib import Path

sys.path.insert(0, "/Users/alxchunlin/code-stuff/alex-style-guide/matplotlib")
import matplotlib.pyplot as plt  # noqa: E402
import alex_style as ax  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / "docs/img/spikes"
OUT.mkdir(parents=True, exist_ok=True)
P = ax.use("dark")

# ---- 1: irdrop vs feeds per label
b = json.load(open(HERE / "results/irdrop_bench.json"))
ratio = {}
for t in b["triage"]:
    if t["row"] == "irdrop":
        m = re.search(r"\(x([\d.]+)", t["msg"])
        for lab in t["labels"]:
            ratio[lab] = max(ratio.get(lab, 0), float(m.group(1)) if m else 0)
labels = [f"{t['label']}  {t['what']}" for t in b["labels"]]
vals = [ratio.get(t["label"], 0.0) for t in b["labels"]]
feeds = ["feeds: fail" if t["feeds"] else "feeds: miss" for t in b["labels"]]
fig, (a1, a2) = plt.subplots(1, 2, figsize=(14.5, 4.4), gridspec_kw={"width_ratios": [2.0, 1]})
ax.bars(a1, labels, vals, xlabel="Current over its IPC-2221 rating at the worst neck or via field, x", ylabel="Label")
a1.axvline(1.0, color=P["warning"], linestyle=(0, (4, 3)), linewidth=1)
a1.annotate("fail above 1", xy=(1.0, 0.0), xycoords=("data", "axes fraction"), xytext=(4, 4), textcoords="offset points",
            color=P["muted"], fontsize=8)
for i, f in enumerate(feeds):
    a1.annotate(f, xy=(3.0, i), va="center", color=P["muted"], fontsize=8, fontfamily="Roboto Mono")
a1.set_xlim(0, 3.6)
ax.title(a1, "C1: the solve against the feeds row", "irdrop's worst ratio at each label; feeds' verdict at the right. 5 of 6 each")
pl = json.load(open(HERE / "results/plink_precision.json"))
ax.bars(a2, ["feeds (15 pads)", "irdrop (10 nets)"], [pl["feeds_fails"], pl["irdrop_fails"]], highlight="feeds (15 pads)",
        xlabel="Fail rows on the MotorGo Plink as built, count", ylabel="Row")
ax.title(a2, "Precision on a board that works", "Pour-fed, fabbed and running; red: fails by construction")
fig.tight_layout()
ax.save(fig, OUT / "3-irdrop-vs-feeds.png", dpi=160)

# ---- 2: C8 catch fraction per bug kind
m = json.load(open(HERE / "results/mutation.json"))
kinds = list(m["summary"])
on = [m["summary"][k]["caught_on_topic"] / m["summary"][k]["instances"] if m["summary"][k]["instances"] else 0 for k in kinds]
fig, a = plt.subplots(figsize=(12, 3.8))
ax.bars(a, kinds, [round(100 * v) for v in on], unit=" %", xlabel="Planted bugs failed by the row meant for them, %", ylabel="Bug kind")
for i, k in enumerate(kinds):
    s = m["summary"][k]
    a.annotate(f"{s['caught_on_topic']} of {s['instances']} by its row, {s['caught']} by any row" + (f", {s['n/a']} n/a" if s["n/a"] else ""),
               xy=(116, i), va="center", color=P["muted"], fontsize=8, fontfamily="Roboto Mono", annotation_clip=False)
a.set_xlim(0, 100)
t = m["total"]
ax.title(a, "C8: guardrail coverage on two boards",
         f"Rung-1 Sonnet a2 and rung-2 Opus a2, each board's own checks.json: {t['caught_on_topic']} of {t['instances']} by the row meant for the kind")
fig.tight_layout()
ax.save(fig, OUT / "3-c8-catch.png", dpi=160)
print("ok", OUT)
