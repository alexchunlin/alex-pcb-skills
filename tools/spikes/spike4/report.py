"""Spike #4 tables and charts from the bench rows (no routing).

  .venv/bin/python3 tools/spikes/spike4/report.py            # markdown tables on stdout, charts in docs/img/spikes/4-*.png

Reads tools/bench/results/route.jsonl (tag spike4-h2: the ordering arms on the route bench), plan.jsonl (tag
spike4-h2-waves: the same arms inside the rules wave plan, with the SIG judges) and placements.jsonl (tag spike4-h1:
perturbed placements, MPS conflicts and HPWL against signal vias). Spearman by average ranks, p by 5000 permutations.
"""
import json, random, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RES = ROOT / "tools/bench/results"
IMG = ROOT / "docs/img/spikes"
BOARDS = ["opus", "sonnet", "fable", "opus2"]
ARMS = ["outer", "outer_original", "outer_gp_planar", "outer_gp_share", "outer_gp_contended"] + [f"outer_rand{i}" for i in range(1, 6)]
ARM_NAME = {"outer": "mps (default)", "outer_original": "original", "outer_gp_planar": "global plan: planar",
            "outer_gp_share": "global plan: share", "outer_gp_contended": "global plan: contended",
            **{f"outer_rand{i}": f"random {i}" for i in range(1, 6)}}


def rows(name, tag):
    p = RES / name
    out = [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []
    return [r for r in out if r.get("tag") == tag]


def latest(rs, key):
    d = {}
    for r in rs:
        d[key(r)] = r
    return d


def ranks(v):
    o = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]:
            j += 1
        for k in range(i, j + 1):
            r[o[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def pearson(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x) ** 0.5
    syy = sum((b - my) ** 2 for b in y) ** 0.5
    return sxy / (sxx * syy) if sxx and syy else float("nan")


def spearman(x, y, perms=5000, seed=0):
    rx, ry = ranks(x), ranks(y)
    rho = pearson(rx, ry)
    rng = random.Random(seed)
    ry2 = list(ry)
    hits = 0
    for _ in range(perms):
        rng.shuffle(ry2)
        if abs(pearson(rx, ry2)) >= abs(rho) - 1e-12:
            hits += 1
    return rho, (hits + 1) / (perms + 1)


def new_err(r):
    st = (r.get("errors_start") or [0])[0] or 0
    return max(0, (r.get("plain_errors") or 0) - st)


def h2_route():
    rs = latest([r for r in rows("route.jsonl", "spike4-h2") if r.get("router") == "krt"], lambda r: (r["board"], r["config"]))
    print("### H2 on the route bench (stripped placement, pours kept, outer layers, one KRT pass)\n")
    print("| board | arm | airwires | new DRC errors | vias | signal vias | length mm | KRT wall s |")
    print("|---|---|---|---|---|---|---|---|")
    summary = {}
    for b in BOARDS:
        for a in ARMS:
            r = rs.get((b, a))
            if not r:
                continue
            if "airwires" not in r:
                print(f"| {b} | {ARM_NAME[a]} | ERROR {str(r.get('error'))[:50]} | | | | | |")
                continue
            print(f"| {b} | {ARM_NAME[a]} | {r['airwires']} | {new_err(r)} | {r['vias']} | {r['signal_vias']} | {r['length_mm']:.0f} | {r['wall_s']} |")
        got = {a: rs[(b, a)] for a in ARMS if (b, a) in rs and "signal_vias" in rs[(b, a)]}
        if "outer" in got:
            m = got["outer"]["signal_vias"]
            rnd = [got[a]["signal_vias"] for a in got if a.startswith("outer_rand")]
            allsv = [g["signal_vias"] for g in got.values()]
            clean = {a: g["airwires"] == 0 and new_err(g) == 0 for a, g in got.items()}
            summary[b] = {"mps": m, "rand": rnd, "rand_dev_max": max((abs(x - m) for x in rnd), default=None),
                          "rand_median": sorted(rnd)[len(rnd) // 2] if rnd else None, "min": min(allsv), "max": max(allsv),
                          "spread_pct": round(100 * (max(allsv) - min(allsv)) / max(1, min(allsv)), 1),
                          "clean": clean, "best_clean": min((g["signal_vias"], a) for a, g in got.items() if clean[a]) if any(clean.values()) else None}
    print("\n| board | MPS signal vias | random orders | max abs(random - MPS) | all arms min-max | spread (max-min)/min | best clean arm |")
    print("|---|---|---|---|---|---|---|")
    for b, s in summary.items():
        bc = f"{ARM_NAME[s['best_clean'][1]]} {s['best_clean'][0]}" if s["best_clean"] else "none"
        print(f"| {b} | {s['mps']} | {', '.join(map(str, s['rand']))} | {s['rand_dev_max']} | {s['min']}-{s['max']} | {s['spread_pct']} % | {bc} |")
    return rs, summary


def h2_waves():
    rs = latest(rows("plan.jsonl", "spike4-h2-waves"), lambda r: (r["board"], r["arm"]))
    if not rs:
        return rs
    print("\n### H2 inside the rules wave plan (Alex's stackup, feeds and thermal vias, `pcb route waves`), with the SIG judges\n")
    print("| board | arm | clean | vias | signal vias | length mm | VIN mW | fast off mm | mid off mm | return-via bad | exposure mm | currents fails | wall s |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for b in ("opus", "sonnet", "opus2"):
        for a in ["mps", "original", "gp_planar", "gp_share", "gp_contended"] + [f"rand{i}" for i in range(1, 6)]:
            r = rs.get((b, a))
            if not r:
                continue
            if "error" in r:
                print(f"| {b} | {a} | ERROR | | | | | | | | | | |")
                continue
            print(f"| {b} | {a} | {'yes' if r['clean'] else 'no'} | {r['vias']} | {r.get('signal_vias')} | {r['length_mm']:.0f} | {r['vin_mW']:.1f} | "
                  f"{r['fast_off_mm']} | {r['mid_off_mm']} | {r['return_via_bad']} | {r['exposure_mm']} | {len(r['currents_fails'])} | {r['wall_s']} |")
    return rs


def h3():
    rs = latest(rows("plan.jsonl", "spike4-h3"), lambda r: r["arm"])
    base = latest(rows("plan.jsonl", "spike4-h2-waves"), lambda r: (r["board"], r["arm"])).get(("opus2", "mps"))
    if not rs:
        return
    print("\n### H3: guide corridors on the attempt-2 placement (opus2, Alex's stackup, rules plan's feeds)\n")
    print("| arm | clean | vias | signal vias | length mm | VIN mW | VIN drop mV | VIN J A/mm2 | fast off mm | mid off mm | return-via bad | exposure mm | currents fails | wall s |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for name, r in [("rules plan (KRT alone)", base), ("split power wave, no guides", rs.get("h3-split")), ("guided, two chains a net (VIN, 5V waves timed out at 300 s)", rs.get("h3-guided")), ("guided, one chain a net, 900 s (VIN timed out, 5V 793 s)", rs.get("h3-guided1"))]:
        if not r or "error" in r:
            continue
        print(f"| {name} | {'yes' if r['clean'] else 'no ' + json.dumps(r['new_errors'])} | {r['vias']} | {r.get('signal_vias')} | {r['length_mm']:.0f} | "
              f"{r['vin_mW']:.1f} | {', '.join('%.1f' % x for x in r['vin_drop_mV'])} | {r['vin_J']:.0f} | {r['fast_off_mm']} | {r['mid_off_mm']} | "
              f"{r['return_via_bad']} | {r['exposure_mm']} | {len(r['currents_fails'])} | {r['wall_s']} |")


def h1():
    rs = [r for r in rows("placements.jsonl", "spike4-h1") if "signal_vias" in r]
    if not rs:
        return None
    rs = list(latest(rs, lambda r: (r["board"], r["k"])).values())
    print("\n### H1: MPS conflicts and HPWL against signal vias (placement 0 = archived, 1-20 perturbed)\n")
    print("| set | n | Spearman conflicts vs signal vias (p) | signal conflicts vs signal vias (p) | HPWL vs signal vias (p) | signal HPWL vs signal vias (p) |")
    print("|---|---|---|---|---|---|")
    out = {}
    for name, sub in [("all placements", rs), ("clean routes only", [r for r in rs if r.get("clean")])] + \
            [(f"{b} only", [r for r in rs if r["board"] == b]) for b in BOARDS]:
        if len(sub) < 4:
            continue
        sv = [r["signal_vias"] for r in sub]
        cols = []
        for k in ("conflicts", "signal_conflicts", "hpwl_mm", "hpwl_signal_mm"):
            rho, p = spearman([r[k] for r in sub], sv)
            cols.append(f"{rho:+.2f} ({p:.3f})")
            out[(name, k)] = (rho, p, len(sub))
        print(f"| {name} | {len(sub)} | " + " | ".join(cols) + " |")
    # within-board ranks pooled: each board's values ranked on their own, so board size does not drive the result
    def within(k):
        x, y = [], []
        for b in BOARDS:
            sub = [r for r in rs if r["board"] == b]
            if len(sub) < 3:
                continue
            x += [v / len(sub) for v in ranks([r[k] for r in sub])]
            y += [v / len(sub) for v in ranks([r["signal_vias"] for r in sub])]
        return spearman(x, y)
    print("| within-board ranks, pooled | " + str(len(rs)) + " | " + " | ".join(f"{a:+.2f} ({p:.3f})" for a, p in
          (within(k) for k in ("conflicts", "signal_conflicts", "hpwl_mm", "hpwl_signal_mm"))) + " |")
    # does the conflict count add anything once HPWL is known? partial Spearman of conflicts and signal vias given HPWL
    def partial(k, z):
        sv = [r["signal_vias"] for r in rs]
        rxy = pearson(ranks([r[k] for r in rs]), ranks(sv))
        rxz = pearson(ranks([r[k] for r in rs]), ranks([r[z] for r in rs]))
        ryz = pearson(ranks(sv), ranks([r[z] for r in rs]))
        return (rxy - rxz * ryz) / ((1 - rxz ** 2) * (1 - ryz ** 2)) ** 0.5, rxz
    for k, z in (("conflicts", "hpwl_mm"), ("signal_conflicts", "hpwl_signal_mm"), ("hpwl_mm", "conflicts"), ("hpwl_signal_mm", "signal_conflicts")):
        pr, rxz = partial(k, z)
        out[("partial", k)] = (pr, rxz)
        print(f"\npartial Spearman {k} vs signal vias given {z}: {pr:+.2f} (Spearman {k} vs {z}: {rxz:+.2f}, n {len(rs)})", end="")
    print()
    print("\n| board | placements | clean | signal vias min / median / max | conflicts min-max | signal conflicts min-max | HPWL mm min-max |")
    print("|---|---|---|---|---|---|---|")
    for b in BOARDS:
        sub = [r for r in rs if r["board"] == b]
        if not sub:
            continue
        sv = sorted(r["signal_vias"] for r in sub)
        rng = lambda k, f="%d": f"{f % min(r[k] for r in sub)}-{f % max(r[k] for r in sub)}"
        print(f"| {b} | {len(sub)} | {sum(1 for r in sub if r.get('clean'))} | {sv[0]} / {sv[len(sv) // 2]} / {sv[-1]} | {rng('conflicts')} | "
              f"{rng('signal_conflicts')} | {rng('hpwl_mm', '%.0f')} |")
    print("\n| board | k | sigma mm | moved | conflicts | signal conflicts | HPWL mm | airwires | new errors | vias | signal vias | length mm |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(rs, key=lambda r: (BOARDS.index(r["board"]), r["k"])):
        if r["k"] == 0:
            print(f"| {r['board']} | {r['k']} | {r['sigma']} | {r['moved']} | {r['conflicts']} | {r['signal_conflicts']} | {r['hpwl_mm']:.0f} | "
                  f"{r['airwires']} | {r['new_errors']} | {r['vias']} | {r['signal_vias']} | {r['length_mm']:.0f} |")
    return rs, out


def charts(rs2, summary, rs1):
    sys.path.insert(0, "/Users/alxchunlin/code-stuff/alex-style-guide/matplotlib")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import alex_style as ax
    p = ax.use("dark")
    IMG.mkdir(parents=True, exist_ok=True)
    boards = [b for b in BOARDS if b in summary]
    fig, axs = plt.subplots(2, (len(boards) + 1) // 2, figsize=(13, 8.5))
    axs = list(axs.flat)
    for a, b in zip(axs, boards):
        labels, vals = [], []
        for arm in ARMS:
            r = rs2.get((b, arm))
            if not r or "signal_vias" not in r:
                continue
            tag = "" if (r["airwires"] == 0 and new_err(r) == 0) else f" ({r['airwires']} open)" if r["airwires"] else f" (+{new_err(r)} err)"
            labels.append(ARM_NAME[arm] + tag)
            vals.append(r["signal_vias"])
        ax.bars(a, labels, vals, highlight=labels[0] if labels else None, xlabel="Signal vias, count", ylabel="Net order")
        a.axvline(summary[b]["mps"] - 2, color=p["muted"], linestyle=(0, (2, 4)), linewidth=1)
        a.axvline(summary[b]["mps"] + 2, color=p["muted"], linestyle=(0, (2, 4)), linewidth=1)
        ax.title(a, f"{b}", f"MPS {summary[b]['mps']} in red; dotted lines MPS +/- 2; spread {summary[b]['spread_pct']} %; (n open) = airwires left, (+n err) = new DRC errors")
    fig.suptitle("SIGNAL VIAS PER NET ORDER, FOUR RUNG-2 PLACEMENTS", x=0.01, ha="left", fontfamily="Roboto Condensed", fontweight="bold", color=p["ink"])
    fig.tight_layout()
    ax.save(fig, IMG / "4-ordering.png", dpi=150)
    plt.close(fig)
    if rs1:
        rows1 = rs1[0]
        fig, (a, c) = plt.subplots(1, 2, figsize=(11, 4.4), sharey=True)
        for i, b in enumerate(BOARDS):
            sub = [r for r in rows1 if r["board"] == b]
            if not sub:
                continue
            col = p["series"][i]
            for k, axx in (("conflicts", a), ("hpwl_signal_mm", c)):
                xs = [r[k] for r in sub]
                ys = [r["signal_vias"] for r in sub]
                axx.scatter(xs, ys, s=18, color=col, label=b, edgecolors="none", alpha=0.9)
                z = [r for r in sub if r["k"] == 0]
                if z:
                    axx.scatter([z[0][k]], [z[0]["signal_vias"]], s=70, facecolors="none", edgecolors=col, linewidths=1.5)
        o = rs1[1]
        a.set_xlabel("MPS crossing conflicts before routing (KRT), count"); a.set_ylabel("Signal vias after KRT, count")
        c.set_xlabel("Signal-net HPWL, mm"); c.set_ylabel("Signal vias after KRT, count")
        rc = o.get(("all placements", "conflicts")); rh = o.get(("all placements", "hpwl_signal_mm"))
        ax.title(a, "Conflicts vs signal vias", f"Spearman {rc[0]:+.2f} over {rc[2]} placements; ring = archived placement" if rc else "")
        ax.title(c, "HPWL vs signal vias", f"Spearman {rh[0]:+.2f} over {rh[2]} placements" if rh else "")
        a.legend(loc="lower left", bbox_to_anchor=(0, 1.12), ncol=4, frameon=False, handletextpad=0.3, markerscale=1.2)
        fig.tight_layout()
        ax.save(fig, IMG / "4-conflicts-hpwl.png", dpi=150)
        plt.close(fig)


def main():
    rs2, summary = h2_route()
    h2_waves()
    h3()
    rs1 = h1()
    charts(rs2, summary, rs1)


if __name__ == "__main__":
    main()
