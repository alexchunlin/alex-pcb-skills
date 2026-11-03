"""Spike 2 charts under docs/img/spikes/2-*.png, from the committed results (no corpus files needed).

  ~/code-stuff/alex-pcb-skills/.venv/bin/python3 tools/spikes/spike2/charts.py

Inputs: tools/bench/data/corpus-index.jsonl (instances per part), tools/spikes/spike2/refstat-bench.json (refstat recall
against the existing rows), tools/bench/data/revdiff-triage.jsonl (triage kinds), tools/spikes/spike2/placement-results.jsonl
and priors-summary.json (placement). Style: alex-style matplotlib helper, dark mode.
"""
import json, os, sys
from collections import Counter

sys.path.insert(0, "/Users/alxchunlin/code-stuff/alex-style-guide/matplotlib")
import matplotlib.pyplot as plt  # noqa: E402
import alex_style as ax  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OUT = os.path.join(ROOT, "docs/img/spikes")
os.makedirs(OUT, exist_ok=True)
ax.use("dark")


def jl(p):
    return [json.loads(l) for l in open(os.path.join(ROOT, p))]


# 1. instances per part
idx = jl("tools/bench/data/corpus-index.jsonl")
parts = ["AMS1117-3.3", "ESP32-WROOM-32", "ESP32-S3-WROOM-1", "LSM6DS3", "DRV8874", "TPS54620"]
repos = [len({r["repo"] for r in idx if r["part"] == p}) for p in parts]
boards = [len({r["repo"] for r in idx if r["part"] == p and r.get("board") and r["board"].get("match")}) for p in parts]
fig, (a, b) = plt.subplots(1, 2, figsize=(12, 3.8))
ax.bars(a, parts, repos, xlabel="Repositories with the part placed in a schematic, count", ylabel="Part")
ax.ref_line(a, 30, "30 needed", status="warning")
summ = json.load(open(os.path.join(ROOT, "tools/spikes/spike2/corpus-summary.json")))
ax.title(a, "Instances per part", "bshada/open-schematics, %d of %d shards, %d rows; one count per owner/repo" % (summ["shards_read"], summ["shards"], summ["rows"]))
ax.bars(b, parts, boards, xlabel="Repositories with a matching .kicad_pcb, count", ylabel="Part")
ax.ref_line(b, 30, "30 needed", status="warning")
ax.title(b, "With a board", "A board file in the row names the part and its reference")
ax.save(fig, os.path.join(OUT, "2-instances.png"), dpi=160)
plt.close(fig)

# 2. refstat recall against the existing rows
rb = json.load(open(os.path.join(ROOT, "tools/spikes/spike2/refstat-bench.json")))
labs = [("existing rows", rb["all"]["base"]["recall_fail"]), ("existing + refstat", rb["all"]["refstat"]["recall_fail"])]
df = rb["decoupling_feed_majors"]
fig, (a, b) = plt.subplots(1, 2, figsize=(12, 3.2))
ax.bars(a, [l for l, _ in labs], [v for _, v in labs], xlabel="Labels caught as a fail, count of %d" % rb["all"]["base"]["labels"], ylabel="Config")
ax.title(a, "Replay recall, 10 boards", "pcb check with each board's checks.json, then with the %d refstat rows added" % rb["n_rows"])
cats = ["decoupling/feed majors caught by existing rows", "caught only by refstat", "refstat fails, no label"]
vals = [len(rb["all"]["df_majors_caught_base"]), len(rb["all"]["df_majors_caught_refstat_only"]),
        rb["all"]["refstat"]["false_fails"] - rb["all"]["base"]["false_fails"]]
ax.bars(b, cats, vals, highlight="refstat fails, no label", xlabel="Count", ylabel="Outcome")
ax.title(b, "The %d labelled decoupling and feed majors" % len(df), "Red: refstat fails that match no label (read in the report)")
ax.save(fig, os.path.join(OUT, "2-refstat-recall.png"), dpi=160)
plt.close(fig)

# 3. triage kinds
tri = jl("tools/bench/data/revdiff-triage.jsonl")
real = [t for t in tri if t["real_fix"]]
kinds = Counter(t["kind"] for t in real).most_common()
fig, a = plt.subplots(figsize=(9, 0.42 * len(kinds) + 1.4))
lab = [k for k, _ in kinds]
ax.bars(a, lab, [n for _, n in kinds], xlabel="Real post-build fixes, count", ylabel="Failure kind")
ax.title(a, "Rev-diff triage", "%d keyword commits read, %d real post-build hardware fixes" % (len(tri), len(real)))
ax.save(fig, os.path.join(OUT, "2-triage-kinds.png"), dpi=160)
plt.close(fig)

# 4. placement: prior vs uniform
pr = os.path.join(ROOT, "tools/spikes/spike2/placement-results.jsonl")
if os.path.exists(pr):
    rows = jl("tools/spikes/spike2/placement-results.jsonl")
    c = ax.colors()
    fig, a = plt.subplots(figsize=(8, 3.6))
    for i, mode in enumerate(("prior", "uniform")):
        v = sorted(r["auto"]["vias"] for r in rows if r["mode"] == mode and r.get("auto", {}).get("clean"))
        if v:
            a.plot(v, [k / len(v) for k in range(1, len(v) + 1)], drawstyle="steps-post", label=f"{mode} ({len(v)} clean)", lw=2.0, color=c[i])
    a.axvline(26, ls="--", color="#d9a21b", lw=1.2)
    a.text(26.3, 0.05, "designer 26 vias", color="#d9a21b", fontsize=8.5)
    a.set_xlabel("Vias after pcb route auto, count"); a.set_ylabel("Share of clean routes, fraction")
    ax.label_lines(a)
    ax.title(a, "Prior-seeded vs uniform", "rung-1 Sonnet board, C1-C3 re-placed 50 times each, routed with KRT")
    ax.save(fig, os.path.join(OUT, "2-placement.png"), dpi=160)
    plt.close(fig)
print("charts ->", OUT)
