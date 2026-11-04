#!/usr/bin/env python3
"""Spike #1 (B, D): the rank test from the committed rows, no routing.

  .venv/bin/python3 -I tools/spikes/spike1/rank.py [--out tools/bench/results/spike1_rank.json] [--check] [--md]
  .venv/bin/python3 -I tools/spikes/spike1/rank.py fit --out /tmp/spike1/model.pkl     (the search arm's model: all rung-2 rows)

Models (surrogate.py): hpwl (no fit), hpwl+conflicts (logistic for clean, linear for signal vias), linear (logistic and
ridge on the 18 hand features), gbt (HistGradientBoosting on the same). Protocols: `board` (train on three rung-2
boards, test on the fourth, all four folds), `random` (5-fold, stratified by board, out-of-fold predictions scored
within each board), `r1` (train on the four rung-2 boards, test on the rung-1 board). Per board and model: Spearman of
the predicted signal vias against the router's, AUC on clean, pair accuracy on same-sigma pairs (signal vias, clean) and
at the clean boundary (one clean, one not, HPWL within 5 %); gain = model minus hpwl, with a 90 % bootstrap interval for
gbt and hpwl+conflicts. Pool replay: the search boards' rows routed in a model's order, router calls to the first clean
placement at or under a signal-via target, against the expectation for a random order. GBT permutation importances.
--check recomputes and compares with the committed JSON (verify_all 32).
"""
import argparse, json, math, pickle, sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import surrogate as S  # noqa: E402

ROOT = HERE.parents[2]
OUT = ROOT / "tools/bench/results/spike1_rank.json"
# the decision rule's target per search board: the designer's own signal vias (opus2: attempt 2 as handed in), and the
# router's on the archived placement (k = 0) as the looser second target
TARGETS = {"opus2": {"designer": 27}, "opus": {"designer": 11}}


def ensure_feats(rows):
    missing = [r for r in rows if "feat" not in r]
    if missing:
        import dataset as D
        cache = {}
        for r in missing:
            if r["board"] not in cache:
                cache[r["board"]] = (D.static(r["board"]), D.decoupling(r["board"]))
            r["feat"] = D.feat_of(r, *cache[r["board"]])
    return rows


def rnd(x, n=3):
    if isinstance(x, float):
        return None if math.isnan(x) else round(x, n)
    if isinstance(x, dict):
        return {k: rnd(v, n) for k, v in x.items()}
    if isinstance(x, list):
        return [rnd(v, n) for v in x]
    return x


def score_protocol(name, preds, rows):
    """preds: model -> (pc, ps) aligned with rows. Per board metrics and gains."""
    out = {}
    for b in sorted({r["board"] for r in rows}):
        idx = [i for i, r in enumerate(rows) if r["board"] == b]
        rs = [rows[i] for i in idx]
        per = {}
        for m, (pc, ps) in preds.items():
            per[m] = S.board_metrics(rs, pc[idx], ps[idx])
        for m in ("gbt", "hpwl+conflicts", "linear"):
            per[m]["gain"] = {k: (per[m][k] - per["hpwl"][k]) if not (math.isnan(per[m][k]) or math.isnan(per["hpwl"][k])) else float("nan")
                              for k in ("sv_same_sigma", "clean_same_sigma", "clean_boundary", "spearman_sv", "auc_clean")}
        for m in ("gbt", "hpwl+conflicts"):
            per[m]["gain_ci90"] = S.boot_gain(rs, preds[m][0][idx], preds[m][1][idx], preds["hpwl"][0][idx], preds["hpwl"][1][idx])
        out[b] = per
    return out


def pool_replay(rows, preds, board, target):
    """Route the board's pool in the model's order (p_clean high first, then predicted vias low): calls to the first
    row that is clean at or under `target` signal vias. Random order: (N + 1) / (m + 1) expected calls."""
    idx = [i for i, r in enumerate(rows) if r["board"] == board and r["k"] > 0]
    ok = np.array([bool(rows[i].get("clean")) and rows[i]["signal_vias"] <= target for i in idx])
    res = {"pool": len(idx), "hits": int(ok.sum()), "random_expected": round((len(idx) + 1) / (ok.sum() + 1), 1)}
    for m, (pc, ps) in preds.items():
        order = sorted(range(len(idx)), key=lambda j: (-pc[idx[j]], ps[idx[j]]))
        hit = next((n + 1 for n, j in enumerate(order) if ok[j]), None)
        res[m] = hit
    return res


def importances(rows, p0, folds):
    from sklearn.inspection import permutation_importance
    acc = {"clean": np.zeros(len(S.FEATS)), "signal_vias": np.zeros(len(S.FEATS))}
    for tr, te in folds:
        m = S.Model("gbt").fit([rows[i] for i in tr], p0)
        Xte = S.matrix([rows[i] for i in te], p0)
        yc = np.array([bool(rows[i].get("clean")) for i in te])
        ys = S.sv_target([rows[i] for i in te])
        acc["clean"] += permutation_importance(m.c, Xte, yc, scoring="roc_auc", n_repeats=5, random_state=0).importances_mean
        acc["signal_vias"] += permutation_importance(m.r, Xte, ys, scoring="r2", n_repeats=5, random_state=0).importances_mean
    return {k: dict(sorted(((f, round(float(v / len(folds)), 4)) for f, v in zip(S.FEATS, a)), key=lambda kv: -kv[1])) for k, a in acc.items()}


def run():
    from sklearn.model_selection import StratifiedKFold
    rows = ensure_feats(S.load())
    p0 = S.p0_feats(rows)
    r2 = [r for r in rows if r["board"] in S.RUNG2]
    res = {"rows": {b: sum(r["board"] == b for r in rows) for b in sorted({r["board"] for r in rows})},
           "clean": {b: sum(bool(r.get("clean")) for r in rows if r["board"] == b) for b in sorted({r["board"] for r in rows})}}
    # held out by board
    preds = {m: (np.zeros(len(r2)), np.zeros(len(r2))) for m in S.MODELS}
    for b in S.RUNG2:
        tr = [r for r in r2 if r["board"] != b]
        te = [i for i, r in enumerate(r2) if r["board"] == b]
        for m in S.MODELS:
            pc, ps = S.Model(m).fit(tr, p0).predict([r2[i] for i in te], p0)
            preds[m][0][te], preds[m][1][te] = pc, ps
    res["board"] = score_protocol("board", preds, r2)
    board_preds = preds
    # held out at random within board
    skf = StratifiedKFold(5, shuffle=True, random_state=0)
    lab = [f"{r['board']}:{bool(r.get('clean'))}" for r in r2]
    folds = list(skf.split(np.zeros(len(r2)), lab))
    preds = {m: (np.zeros(len(r2)), np.zeros(len(r2))) for m in S.MODELS}
    for tr, te in folds:
        for m in S.MODELS:
            pc, ps = S.Model(m).fit([r2[i] for i in tr], p0).predict([r2[i] for i in te], p0)
            preds[m][0][te], preds[m][1][te] = pc, ps
    res["random"] = score_protocol("random", preds, r2)
    res["pool_replay"] = {}
    for b, t in TARGETS.items():
        k0 = next((r for r in r2 if r["board"] == b and r["k"] == 0), None)
        for tname, tv in [("designer", t["designer"])] + ([("router_k0", k0["signal_vias"])] if k0 else []):
            res["pool_replay"][f"{b}:{tname}<= {tv}"] = {"random_fold": pool_replay(r2, preds, b, tv), "board_fold": pool_replay(r2, board_preds, b, tv)}
    res["importance"] = importances(r2, p0, folds)
    # the rung-1 board
    r1 = [r for r in rows if r["board"] == "r1sonnet"]
    if r1 and "r1sonnet" in p0:
        preds = {m: S.Model(m).fit(r2, p0).predict(r1, p0) for m in S.MODELS}
        res["r1"] = score_protocol("r1", {m: (np.asarray(a), np.asarray(b)) for m, (a, b) in preds.items()}, r1)
    return rnd(res)


def md(res):
    lines = []
    for proto in ("board", "random", "r1"):
        if proto not in res:
            continue
        lines.append(f"\n### protocol {proto}\n")
        lines.append("| board | n (clean) | model | Spearman sv | AUC clean | same-sigma sv pairs | same-sigma clean pairs | clean-boundary pairs (n) | gain boundary (90 % CI) |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for b, per in res[proto].items():
            for m in S.MODELS:
                x = per[m]
                g = x.get("gain", {}).get("clean_boundary")
                ci = (x.get("gain_ci90") or {}).get("clean_boundary")
                lines.append(f"| {b} | {x['n']} ({x['clean_n']}) | {m} | {x['spearman_sv']} | {x['auc_clean']} | {x['sv_same_sigma']} | "
                             f"{x['clean_same_sigma']} | {x['clean_boundary']} ({x['clean_boundary_pairs']}) | "
                             f"{'' if g is None else f'{g:+.3f}'}{'' if not ci else f' [{ci[0]:+.3f}, {ci[1]:+.3f}]'} |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", default="rank", choices=["rank", "fit"])
    ap.add_argument("--out")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--md", action="store_true")
    a = ap.parse_args()
    if a.cmd == "fit":
        rows = ensure_feats(S.load())
        p0 = S.p0_feats(rows)
        r2 = [r for r in rows if r["board"] in S.RUNG2]
        m = S.Model("gbt").fit(r2, p0)
        pickle.dump({"model": m, "p0": p0, "rows": len(r2)}, open(a.out, "wb"))
        print(f"fit: gbt on {len(r2)} rung-2 rows -> {a.out}")
        return
    res = run()
    if a.check:
        old = json.load(open(a.out or OUT))
        same = json.dumps(old, sort_keys=True) == json.dumps(res, sort_keys=True)
        print(f"rank --check: {'same' if same else 'DIFFERS'} as {a.out or OUT}")
        if not same:
            for k in res:
                if json.dumps(res[k], sort_keys=True) != json.dumps(old.get(k), sort_keys=True):
                    print("  differs:", k)
        sys.exit(0 if same else 1)
    if a.md:
        print(md(res))
    path = Path(a.out or OUT)
    path.write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    print(f"rank: {path}")


if __name__ == "__main__":
    main()
