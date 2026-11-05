#!/usr/bin/env python3
"""Spike 5 charts, in the house style, from the committed summaries: docs/img/spikes/5-*.png.

  <repo>/.venv/bin/python3 tools/spikes/spike5/charts.py
"""
import json, sys
from pathlib import Path

sys.path.insert(0, "/Users/alxchunlin/code-stuff/alex-style-guide/matplotlib")
import alex_style as ax  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
IMG = ROOT / "docs/img/spikes"
LABEL = {"uniform": "uniform", "part": "part prior (spike 2)", "krt": "KRT decap cost", "class_part": "class prior, part held out", "class_pkg": "class prior, LGA-14 held out",
         "class": "class prior, DRV8874 held out", "krt_tpl": "KRT + class prior as templates", "perturb": "designer perturbed, 1 mm"}
S1, S2 = "#2f62e8", "#e03a2f"


def clean_bars(board, title, sub, name, callout, bar=None):
    s = json.load(open(HERE / "route-summary.json"))[board]["arms"]
    arms = [a for a in reversed(list(s))]
    fig, a = plt.subplots(figsize=(8, 0.62 * len(arms) + 1.4))
    vals = [s[x]["clean"] for x in arms]
    a.barh([LABEL[x] for x in arms], vals, color=[S2 if x in callout else S1 for x in arms], height=0.62)
    for i, v in enumerate(vals):
        a.text(v + 0.5, i, f"{v}", va="center", family="Roboto Mono", fontsize=10)
    if bar:
        a.axvline(bar, color="#e6c229", linestyle="--", linewidth=1.5)
        a.text(bar + 0.4, len(arms) - 0.5, f"pass bar {bar}", fontsize=9, va="bottom")
    a.set_xlim(0, 50)
    a.set_xlabel("Seeds clean after pcb route auto, of 50")
    a.set_ylabel("Arm")
    a.grid(axis="x", linestyle=(0, (2, 4)))
    a.grid(axis="y", visible=False)
    ax.title(a, title, sub)
    ax.save(fig, str(IMG / name))


def h2_rows():
    s = json.load(open(HERE / "h2-summary.json"))["rows"]
    keep = [(k.split("|"), v) for k, v in s.items() if k.split("|")[3] in ("bypass", "vm_bypass") and "p-" not in k.split("|")[2]]
    keep.sort(key=lambda kv: (kv[0][0], kv[0][3], kv[0][2], kv[0][1]))
    fig, a = plt.subplots(figsize=(9, 0.34 * len(keep) + 1.6))
    orgs = sorted({k[1] for k, _ in keep})
    pal = ax_pal(len(orgs))
    for i, (k, v) in enumerate(reversed(keep)):
        c = pal[orgs.index(k[1])]
        a.plot([v["q25"], v["q75"]], [i, i], color=c, linewidth=2.0)
        a.plot([v["median"]], [i], marker="s", color=c, markersize=6)
    a.set_yticks(range(len(keep)))
    a.set_yticklabels([f"{k[3]}  {k[2]}  {k[1]}  {v['repos']} repos" for k, v in reversed(keep)], fontsize=8)
    a.set_xlabel("Pad-to-pad distance to the pin, mm (repo medians: median and IQR)")
    a.set_ylabel("Role, package, source")
    a.grid(axis="x", linestyle=(0, (2, 4)))
    a.grid(axis="y", visible=False)
    for o, c in zip(orgs, pal):
        a.plot([], [], color=c, marker="s", label=o)
    a.legend(loc="lower right", frameon=False, fontsize=8)
    ax.title(a, "Designer and package", "Medians inside each other's IQR pool")
    ax.save(fig, str(IMG / "5-h2-rows.png"))


def ax_pal(n):
    return ["#2f62e8", "#e03a2f", "#0f9a66", "#a45ee0", "#1a9cc0", "#d9539a"][:n]


def judges():
    p = HERE / "judges-summary.json"
    if not p.exists():
        return
    s = json.load(open(p))
    arms = list(s)
    metrics = [("signal_vias", "Signal vias"), ("return_via_bad", "Return-via bad"), ("exposure_mm", "Exposure, mm"), ("feeds_fails", "Feeds fails"), ("decoupling_fails", "Decoupling fails")]
    fig, axs = plt.subplots(1, len(metrics), figsize=(13, 3.6), sharey=True)
    for a, (k, lab) in zip(axs, metrics):
        names = [LABEL.get(x, "designer start") for x in reversed(arms)]
        vals = [s[x][k] for x in reversed(arms)]
        a.barh(names, vals, color=[S2 if x == "designer" else S1 for x in reversed(arms)], height=0.62)
        for i, v in enumerate(vals):
            a.text(v, i, f" {v}", va="center", family="Roboto Mono", fontsize=8)
        a.set_xlabel(lab + ", median")
        a.set_ylabel("Arm")
        a.grid(axis="x", linestyle=(0, (2, 4)))
        a.grid(axis="y", visible=False)
    axs[0].set_ylabel("Arm")
    fig.suptitle("")
    ax.title(axs[0], "Waves judges, r2", "Best 5 clean per arm, Alex's stackup")
    ax.save(fig, str(IMG / "5-r2-judges.png"))


if __name__ == "__main__":
    ax.use("dark")
    clean_bars("r1", "H1 on the rung-1 board", "LSM6DS3 caps C1 to C3, 50 seeds per arm", "5-r1-clean.png", {"class_part", "class_pkg"}, 28)
    clean_bars("r2", "H1 on the rung-2 board", "DRV8874 satellites, 50 seeds per arm", "5-r2-clean.png", {"class"})
    h2_rows()
    judges()
