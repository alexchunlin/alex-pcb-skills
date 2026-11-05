#!/usr/bin/env python3
"""Spike #1: the report's tables and charts from the committed results (no routing).

  .venv/bin/python3 -I tools/spikes/spike1/report.py [--charts]

Reads tools/bench/results/spike1_rank.json (rank.py), placements.jsonl (dataset, noise, arm (i)) and search.jsonl (arms
ii, iii, kct, the dev judges). Prints markdown; --charts writes docs/img/spikes/1-*.png with the alex-style helper.
"""
import argparse, json, math, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import surrogate as S  # noqa: E402

ROOT = HERE.parents[2]
RES = ROOT / "tools/bench/results"
IMG = ROOT / "docs/img/spikes"
TARGET = {"opus2": 27, "opus": 11}
BUDGET = 3600.0


def jl(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()] if Path(p).exists() else []


def arm1(board):
    """The generator's rows for the board in generation order (spike 4's then spike 1's): arm (i)'s trajectory."""
    rows = [r for r in S.load() if r["board"] == board and r["k"] > 0 and r["tag"] in ("spike4-h1", "spike1")]
    rows.sort(key=lambda r: (r["tag"] != "spike4-h1", r["k"]))
    return [{"kind": "full", "clean": r.get("clean"), "signal_vias": r["signal_vias"], "length_mm": r["length_mm"], "wall_s": r["wall_s"],
             "placement": r["placement"]} for r in rows]


def arm_calls(board, arm):
    return [r for r in jl(RES / "search.jsonl") if r.get("tag") == "spike1-search" and r["board"] == board and r["arm"] == arm
            and r.get("kind") in ("quick", "full")]


def trajectory(calls, budget=None):
    """(router calls, best clean signal vias so far) per call; the hour cut by cumulative router wall for arm (i)."""
    out, best, wall = [], None, 0.0
    for n, c in enumerate(calls, 1):
        if budget is not None:
            wall += c.get("wall_s") or 0
            if wall > budget:
                break
        if c["kind"] == "full" and c.get("clean") and (best is None or c["signal_vias"] < best):
            best = c["signal_vias"]
        out.append((n, best))
    return out


def summary(board, arm, calls, budget=None):
    tr = trajectory(calls, budget)
    used = calls[:len(tr)]
    full = [c for c in used if c["kind"] == "full"]
    clean = [c for c in full if c.get("clean")]
    k0 = next((r for r in S.load() if r["board"] == board and r["k"] == 0), {})
    def first(t):
        return next((n for n, c in enumerate(used, 1) if c["kind"] == "full" and c.get("clean") and c["signal_vias"] <= t), None)
    best = min(clean, key=lambda c: (c["signal_vias"], c["length_mm"])) if clean else None
    return {"board": board, "arm": arm, "calls": len(used), "full": len(full), "quick": len(used) - len(full), "clean": len(clean),
            "best_sv": best and best["signal_vias"], "best_len": best and round(best["length_mm"], 1),
            "first_clean": next((n for n, c in enumerate(used, 1) if c["kind"] == "full" and c.get("clean")), None),
            "first_le_router": first(k0.get("signal_vias", 0)), "router_k0": k0.get("signal_vias"),
            "first_le_designer": first(TARGET[board]), "designer": TARGET[board], "best": best}


def search_tables():
    out = []
    for b in TARGET:
        out.append(summary(b, "arm1 random (replayed)", arm1(b), BUDGET))
        for arm, name in (("arm2", "arm2 KRT place_simple + judge_seeds"), ("arm3", "arm3 GBT filter in place_simple"), ("kct", "kct CMA-ES --route-check")):
            c = arm_calls(b, arm)
            if c:
                out.append(summary(b, name, c))
    return out


def md_search(rows):
    print("| board | arm | router calls in the hour (quick + full) | full routes clean | best clean: signal vias, mm | calls to first clean | "
          "calls to clean <= router on start | calls to clean <= designer |")
    print("|---|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['board']} | {r['arm']} | {r['calls']} ({r['quick']} + {r['full']}) | {r['clean']} of {r['full']} | "
              f"{'' if r['best_sv'] is None else f'{r['best_sv']}, {r['best_len']}'} | {r['first_clean'] or 'none'} | "
              f"{r['first_le_router'] or 'none'} (<= {r['router_k0']}) | {r['first_le_designer'] or 'none'} (<= {r['designer']}) |")


def md_judges():
    js = [r for r in jl(RES / "search.jsonl") if r.get("tag") == "spike1-judge"]
    if not js:
        return
    print("\n| board | placement | clean | signal vias | length mm | VIN mW | bucket-3 off ground mm | return-via bad | exposure mm | currents fails | feeds fails | decoupling fails |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in js:
        print(f"| {r['board']} | {r['arm']} | {'yes' if r.get('clean') else 'no'} | {r.get('signal_vias')} | {r.get('length_mm')} | {r.get('vin_mW')} | "
              f"{r.get('fast_off_mm')} | {r.get('return_via_bad')} | {r.get('exposure_mm')} | {len(r.get('currents_fails') or [])} | "
              f"{len(r['feeds']['fail'])} of {r['feeds']['n']} | {len(r['decoupling']['fail'])} of {r['decoupling']['n']} |")


def md_noise():
    rs = [r for r in jl(RES / "placements.jsonl") if r.get("tag") == "spike1-noise"]
    if rs:
        print(f"\nnoise: {rs[0]['board']} k {rs[0]['k']}, {len(rs)} routes: clean {[r['clean'] for r in rs]}, signal vias "
              f"{sorted({r['signal_vias'] for r in rs})}, vias {sorted({r['vias'] for r in rs})}, length {sorted({r['length_mm'] for r in rs})}, "
              f"wall {min(r['wall_s'] for r in rs)}-{max(r['wall_s'] for r in rs)} s")


def charts(rank, srows):
    sys.path.insert(0, "/Users/alxchunlin/code-stuff/alex-style-guide/matplotlib")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import alex_style as ax
    p = ax.use("dark")
    s = p["series"]
    IMG.mkdir(parents=True, exist_ok=True)
    models = ["hpwl", "hpwl+conflicts", "gbt"]
    names = {"hpwl": "HPWL", "hpwl+conflicts": "HPWL + conflicts", "gbt": "GBT, 18 features"}
    # 1: rank per fold (held out by board), three panels
    fig, axs = plt.subplots(1, 3, figsize=(13, 4.2))
    for a, (metric, lab) in zip(axs, (("spearman_sv", "Spearman, predicted vs routed signal vias"), ("auc_clean", "AUC on clean"),
                                      ("sv_same_sigma", "Same-sigma pair accuracy, signal vias"))):
        boards = list(rank["board"])
        y = np.arange(len(boards))
        for i, m in enumerate(models):
            v = [rank["board"][b][m][metric] for b in boards]
            v = [np.nan if x is None else x for x in v]
            a.barh(y + (i - 1) * 0.26, v, height=0.24, color=s[i] if s else None, label=names[m])
        a.set_yticks(y, [f"test on {b}" for b in boards])
        a.set_xlabel(lab + ", unitless")
        a.set_ylabel("Held-out board")
        a.grid(axis="y", visible=False)
        if metric != "spearman_sv":
            a.axvline(0.5, ls="--", color=p.get("muted", "#888"), lw=1)
    axs[0].legend(loc="upper left", bbox_to_anchor=(0, 1.22), ncol=3, frameon=False)
    ax.title(axs[1], "Rank per fold", "train on three rung-2 boards, test on the fourth; dashed = chance")
    fig.tight_layout()
    ax.save(fig, IMG / "1-rank-folds.png", dpi=150)
    # 2: clean-boundary gain over HPWL with the 90 % interval, both protocols
    fig, a = plt.subplots(figsize=(8, 4.2))
    labels, vals, lo, hi = [], [], [], []
    for proto in ("board", "random"):
        for b in rank[proto]:
            for m in ("hpwl+conflicts", "gbt"):
                g = rank[proto][b][m]["gain"]["clean_boundary"]
                ci = (rank[proto][b][m].get("gain_ci90") or {}).get("clean_boundary")
                labels.append(f"{b}, {names[m]}, {'by board' if proto == 'board' else 'random'}")
                vals.append(np.nan if g is None else g)
                lo.append(np.nan if not ci else ci[0]); hi.append(np.nan if not ci else ci[1])
    y = np.arange(len(labels))
    a.barh(y, vals, color=[s[1] if "GBT" in l else s[0] for l in labels] if s else None, height=0.6)
    a.errorbar(vals, y, xerr=[np.array(vals) - np.array(lo), np.array(hi) - np.array(vals)], fmt="none", ecolor=p.get("ink", "#ddd"), lw=1)
    a.axvline(0, color=p.get("muted", "#888"), lw=1)
    a.set_yticks(y, labels, fontsize=7)
    a.set_xlabel("Gain over HPWL at the clean boundary, pair accuracy points")
    a.set_ylabel("Board, model, protocol")
    a.grid(axis="y", visible=False)
    ax.title(a, "Clean-boundary gain", "pairs one clean one not, HPWL within 5 %; whisker = 90 % bootstrap interval")
    fig.tight_layout()
    ax.save(fig, IMG / "1-boundary-gain.png", dpi=150)
    # 3: search arms over router calls
    fig, axs = plt.subplots(1, len(TARGET), figsize=(12, 4.2))
    for a, b in zip(np.atleast_1d(axs), TARGET):
        i = 0
        for r in [x for x in srows if x["board"] == b]:
            arm = r["arm"]
            calls = arm1(b) if arm.startswith("arm1") else arm_calls(b, arm.split()[0])
            tr = trajectory(calls, BUDGET if arm.startswith("arm1") else None)
            xs = [n for n, v in tr if v is not None]; ys = [v for n, v in tr if v is not None]
            if xs:
                xs = [xs[0]] + xs + [len(tr)]; ys = [ys[0]] + ys + [ys[-1]]
                a.step(xs, ys, where="post", color=s[i] if s else None, label=arm.split()[0])
            i += 1
        a.axhline(TARGET[b], ls="--", color=p.get("warning", "#e0a030"), lw=1)
        a.text(1, TARGET[b] - 0.6, f"designer {TARGET[b]}", fontsize=8, color=p.get("warning", "#e0a030"))
        a.set_xlabel("Router calls in the hour, count")
        a.set_ylabel("Best clean placement so far, signal vias")
        ax.label_lines(a)
        ax.title(a, f"Search arms on {b}", "one router slot, one hour per arm; a line starts at the arm's first clean route")
    fig.tight_layout()
    ax.save(fig, IMG / "1-search-arms.png", dpi=150)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--charts", action="store_true")
    a = ap.parse_args()
    rank = json.load(open(RES / "spike1_rank.json"))
    import rank as R
    print(R.md(rank))
    print("\nimportance (GBT permutation, random folds):", json.dumps(rank["importance"]))
    print("\npool replay:", json.dumps(rank["pool_replay"], indent=1))
    srows = search_tables()
    print()
    md_search(srows)
    md_judges()
    md_noise()
    if a.charts:
        charts(rank, srows)


if __name__ == "__main__":
    main()
