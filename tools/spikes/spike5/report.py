#!/usr/bin/env python3
"""Spike 5: the routing tables, tests and pass rules from the per-seed rows (no routing, plain python3).

  python3 -I tools/spikes/spike5/report.py            # prints the tables, writes route-summary.json
  python3 -I tools/spikes/spike5/report.py --check    # recompute and compare against the committed route-summary.json

Fisher exact two-sided on clean /50 (a rejected seed is not clean); rank-sum with the normal approximation, tie-corrected, on
signal vias of clean routes, both arms needing at least 5 clean. See the Method section of docs/spikes/spike-5-class-priors.md.
"""
import json, math, statistics as st, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "route-results.jsonl"
SUMMARY = HERE / "route-summary.json"
N = 50
ARMS = {"r1": ["uniform", "part", "krt", "class_part", "class_pkg", "krt_tpl"], "r2": ["uniform", "krt", "class", "krt_tpl", "perturb"]}
PAIRS = {"r1": [("class_part", "uniform"), ("class_part", "part"), ("class_part", "krt"), ("class_part", "krt_tpl"), ("class_pkg", "uniform"), ("class_pkg", "part"), ("class_pkg", "krt"),
                ("class_pkg", "krt_tpl"), ("krt", "uniform"), ("krt", "part"), ("krt_tpl", "krt")],
         "r2": [("class", "uniform"), ("class", "krt"), ("class", "krt_tpl"), ("class", "perturb"), ("krt", "uniform"), ("krt_tpl", "krt"), ("perturb", "uniform")]}


def fisher(a, b, n1=N, n2=N):
    """Two-sided Fisher exact on a/n1 against b/n2."""
    tot = a + b
    den = math.comb(n1 + n2, tot)
    pm = lambda k: math.comb(n1, k) * math.comb(n2, tot - k) / den
    p0 = pm(a)
    return min(1.0, sum(pm(k) for k in range(max(0, tot - n2), min(n1, tot) + 1) if pm(k) <= p0 * (1 + 1e-9)))


def ranksum(x, y):
    """Two-sided p of the rank-sum test, normal approximation with tie correction and continuity."""
    n1, n2 = len(x), len(y)
    allv = sorted(x + y)
    rank = {}
    i = 0
    while i < len(allv):
        j = i
        while j + 1 < len(allv) and allv[j + 1] == allv[i]:
            j += 1
        rank[allv[i]] = (i + j) / 2 + 1
        i = j + 1
    r1 = sum(rank[v] for v in x)
    u = r1 - n1 * (n1 + 1) / 2
    n = n1 + n2
    tie = sum(c ** 3 - c for c in (allv.count(v) for v in set(allv)))
    var = n1 * n2 / 12 * (n + 1 - tie / (n * (n - 1)))
    if var <= 0:
        return 1.0
    z = (abs(u - n1 * n2 / 2) - 0.5) / math.sqrt(var)
    return min(1.0, math.erfc(max(z, 0) / math.sqrt(2)))


def load():
    rows = {}
    if RESULTS.exists():
        for l in open(RESULTS):
            x = json.loads(l)
            if x["tag"] == "h1":
                rows[(x["board"], x["arm"], x["seed"])] = x
    return rows


def arm_stats(rs):
    ok = [r for r in rs if r["seed_ok"]]
    clean = [r for r in ok if r.get("auto", {}).get("clean")]
    sv = sorted(r["auto"]["signal_vias"] for r in clean if r["auto"].get("signal_vias") is not None)
    vias = [r["auto"]["vias"] for r in clean]
    ln = [r["auto"]["length_mm"] for r in clean]
    rowfail = lambda r, fam: len((r.get(fam) or {}).get("fail", []))
    dec = [rowfail(r, "decoupling") for r in clean]
    fee = [rowfail(r, "feeds") for r in clean]
    return {"seeds": len(rs), "rejected": len(rs) - len(ok), "emitted": len(ok), "clean": len(clean), "clean_of_emitted": round(len(clean) / max(1, len(ok)), 3),
            "signal_vias_median": st.median(sv) if sv else None, "signal_vias_min": sv[0] if sv else None, "signal_vias_max": sv[-1] if sv else None,
            "vias_median": st.median(vias) if vias else None, "length_median_mm": round(st.median(ln), 1) if ln else None,
            "decoupling_fail_mean": round(st.mean(dec), 2) if dec else None, "feeds_fail_mean": round(st.mean(fee), 2) if fee else None,
            "rows_n": [(clean[0].get("decoupling") or {}).get("n"), (clean[0].get("feeds") or {}).get("n")] if clean else None,
            "_sv": sv, "_rows": [a + b for a, b in zip(dec, fee)]}


def summary():
    rows = load()
    out = {}
    for b, arms in ARMS.items():
        st_ = {}
        for a in arms:
            rs = [rows[k] for k in sorted(rows) if k[0] == b and k[1] == a]
            if rs:
                st_[a] = arm_stats(rs)
        cmp_ = []
        for x, y in PAIRS[b]:
            if x in st_ and y in st_:
                A, B = st_[x], st_[y]
                c = {"a": x, "b": y, "clean": [A["clean"], B["clean"]], "fisher_p": round(fisher(A["clean"], B["clean"], A["seeds"], B["seeds"]), 5)}
                if len(A["_sv"]) >= 5 and len(B["_sv"]) >= 5:
                    c["sv_medians"] = [A["signal_vias_median"], B["signal_vias_median"]]
                    c["sv_ranksum_p"] = round(ranksum(A["_sv"], B["_sv"]), 5)
                if len(A["_rows"]) >= 5 and len(B["_rows"]) >= 5:
                    c["rows_ranksum_p"] = round(ranksum(A["_rows"], B["_rows"]), 5)
                cmp_.append(c)
        out[b] = {"arms": {a: {k: v for k, v in s.items() if not k.startswith("_")} for a, s in st_.items()}, "comparisons": cmp_}
    r1 = out["r1"]["arms"]
    fp = {(c["a"], c["b"]): c for b in out for c in out[b]["comparisons"]}
    verdicts = {}
    if "krt" in r1:
        for arm in ("class_part", "class_pkg"):
            if arm not in r1:
                continue
            c, u, k = r1[arm]["clean"], r1["uniform"]["clean"], r1["krt"]["clean"]
            bu = c > u and fp[(arm, "uniform")]["fisher_p"] < 0.05
            kp = fp[(arm, "krt")]["fisher_p"]
            nl = (c > k and kp < 0.05) if k >= 33 else not (k > c and kp < 0.05)
            verdicts[arm] = {"clean": c, "at_28": c >= 28, "beats_uniform": bu, "not_lose_krt": nl, "pass": bool(c >= 28 and bu and nl)}
    out["r1_verdicts"] = verdicts
    return out


def table(s):
    for b in s:
        if b not in ARMS:
            continue
        print(f"\n### {b}\n\n| Arm | Rejected | Clean /50 | Clean of emitted | Signal vias of clean, median (range) | Vias, median | Length mm, median | Decoupling fails, mean | Feeds fails, mean |\n|---|---:|---:|---:|---|---:|---:|---:|---:|")
        for a, x in s[b]["arms"].items():
            print(f"| `{a}` | {x['rejected']} | {x['clean']} | {x['clean_of_emitted']} | {x['signal_vias_median']} ({x['signal_vias_min']}-{x['signal_vias_max']}) | {x['vias_median']} | {x['length_median_mm']} | {x['decoupling_fail_mean']} | {x['feeds_fail_mean']} |")
        print("\n| Comparison | Clean | Fisher p | Signal vias, medians | Rank-sum p | Rows rank-sum p |\n|---|---|---:|---|---:|---:|")
        for c in s[b]["comparisons"]:
            print(f"| `{c['a']}` vs `{c['b']}` | {c['clean'][0]} vs {c['clean'][1]} | {c['fisher_p']} | {c.get('sv_medians')} | {c.get('sv_ranksum_p')} | {c.get('rows_ranksum_p')} |")
    print("\nverdicts", json.dumps(s.get("r1_verdicts")))


def main():
    s = summary()
    if "--check" in sys.argv:
        saved = json.load(open(SUMMARY))
        if s != saved:
            print("route-summary.json differs from the rows"); sys.exit(1)
        print("ok")
        return
    json.dump(s, open(SUMMARY, "w"), indent=1)
    table(s)


if __name__ == "__main__":
    main()
