"""docs/img/results.png: review score and designer wall time per archived attempt.
Numbers from docs/FINDINGS.md (rung 1 attempts 1 and 2, rung 2 attempts 1 and 2).
Run: .venv/bin/python3 tools/readme/results_chart.py
"""
import sys
sys.path.insert(0, "/Users/alxchunlin/code-stuff/alex-style-guide/matplotlib")
import matplotlib.pyplot as plt
import alex_style as ax

# label, (elec, manuf, doc), designer wall min, with the skill?
rows = [
    ("R1 SKiDL, no tools",        (9, 8, 8), 48.7),
    ("R1 Zener, no tools",        (8, 8, 8), 57.0),
    ("R1 Sonnet + skill",         (9, 9, 8), 42.9),
    ("R1 Fable + skill",          (9, 8, 8), 43.9),
    ("R2 Sonnet + skill",         (7, 8, 8), 56.6),
    ("R2 Opus + skill",           (8, 6, 7), 38.7),
    ("R2 Fable + skill (unfinished)", (4, 4, 6), 70.8),
    ("R2 Opus + skill + router",  (8, 8, 7), 71.3),
]
labels = [r[0] for r in rows]
score = [sum(r[1]) for r in rows]
wall = [r[2] for r in rows]

ax.use("dark")
fig, (a, b) = plt.subplots(1, 2, figsize=(12, 4.2), gridspec_kw={"width_ratios": [1.25, 1]})
ax.bars(a, labels, score, highlight="R2 Opus + skill + router", xlabel="Review score, sum of 3 metrics out of 27", ylabel="Attempt")
for i, r in enumerate(rows):
    a.text(1.0, i, "%d / %d / %d" % r[1], va="center", ha="left", fontsize=9, family="Roboto Mono", color="#141516")
ax.title(a, "Reviewer score per attempt", "Electrical / manufacturability / documentation, independent reviewer; red is the latest")
ax.bars(b, labels, wall, highlight="R2 Opus + skill + router", xlabel="Designer wall time, min", ylabel="Attempt")
b.set_yticklabels([""] * len(labels))
b.set_ylabel("Attempt, as left")
ax.title(b, "Designer wall time", "Same attempts; rung 2 is a 4-layer motor channel, rung 1 a Qwiic breakout")
fig.tight_layout()
ax.save(fig, "docs/img/results.png", dpi=160)
print("ok")
