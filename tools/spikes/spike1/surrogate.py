"""Spike #1: the dataset, the per-board normalisation and the models (repo .venv: numpy, scikit-learn).

Rows: tools/bench/results/placements.jsonl, config `outer` (KRT full pass), tags spike4-h1 and spike1 (the four rung-2
boards) and spike1-r1 (the rung-1 board), each carrying `feat` (features.py, added by dataset.py annotate). Noise
repeats (tag spike1-noise) are not training rows.

Features enter the models relative to the board's archived placement (k = 0): (f - f0) / (|f0| + 1), so a model
trained on three boards reads a fourth on the same scale. Targets: clean (0 airwires and no new DRC error), and
signal_vias divided by the training board's median.
"""
import json, math, os
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")   # small fits: threads cost more than they save (2 min -> seconds)
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "tools/bench/results/placements.jsonl"
RUNG2 = ["opus", "sonnet", "fable", "opus2"]
TAGS = {"spike4-h1", "spike1", "spike1-r1"}
FEATS = ["hpwl", "hpwl_signal", "hpwl_wide", "hpwl_default", "mst_signal", "foreign_pad_cross", "cong_max", "cong_p90",
         "cong_cells_ge6", "halo_intrusions", "tight_pairs", "min_gap", "decap_mean_mm", "decap_excess_mm",
         "pour_foreign_mm2", "pads_off_pour", "conflicts", "signal_conflicts"]
BASE2 = ["hpwl", "conflicts"]


def load(path=DATA):
    rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
    rows = [r for r in rows if r.get("tag") in TAGS and r.get("config") == "outer" and "error" not in r and "rep" not in r]
    seen, out = set(), []
    for r in rows:   # one row per (board, k): the first
        key = (r["board"], r["k"])
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def p0_feats(rows):
    return {r["board"]: r["feat"] for r in rows if r["k"] == 0 and "feat" in r}


def rel(f, f0, names=FEATS):
    return [(float(f[n]) - float(f0[n])) / (abs(float(f0[n])) + 1.0) for n in names]


def matrix(rows, p0, names=FEATS):
    return np.array([rel(r["feat"], p0[r["board"]], names) for r in rows])


def sv_target(rows):
    med = {}
    for b in {r["board"] for r in rows}:
        med[b] = float(np.median([r["signal_vias"] for r in rows if r["board"] == b])) or 1.0
    return np.array([r["signal_vias"] / med[r["board"]] for r in rows])


MODELS = ["hpwl", "hpwl+conflicts", "linear", "gbt"]


class Model:
    """kind: hpwl (no fit), hpwl+conflicts (logistic / linear on the two), linear (logistic / ridge on all), gbt."""

    def __init__(self, kind):
        self.kind = kind

    def fit(self, rows, p0):
        from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
        from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        if self.kind == "hpwl":
            return self
        names = BASE2 if self.kind == "hpwl+conflicts" else FEATS
        self.names = names
        X = matrix(rows, p0, names)
        yc = np.array([bool(r.get("clean")) for r in rows])
        ys = sv_target(rows)
        if self.kind == "gbt":
            kw = dict(max_iter=200, learning_rate=0.05, max_depth=3, min_samples_leaf=10, l2_regularization=1.0, random_state=0)
            self.c = HistGradientBoostingClassifier(**kw).fit(X, yc)
            self.r = HistGradientBoostingRegressor(**kw).fit(X, ys)
        else:
            self.c = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000)).fit(X, yc)
            self.r = make_pipeline(StandardScaler(), LinearRegression() if self.kind == "hpwl+conflicts" else Ridge(alpha=1.0)).fit(X, ys)
        return self

    def predict(self, rows, p0):
        """(p_clean, predicted signal_vias on the training scale); for hpwl, -hpwl_rel and hpwl_rel."""
        if self.kind == "hpwl":
            h = matrix(rows, p0, ["hpwl"])[:, 0]
            return -h, h
        X = matrix(rows, p0, self.names)
        return self.c.predict_proba(X)[:, 1], self.r.predict(X)

    def predict_feats(self, feats, f0):
        """The same for raw feature dicts of one board (the search's candidates)."""
        rows = [{"board": "_", "feat": f} for f in feats]
        return self.predict(rows, {"_": f0})


# ---------------------------------------------------------------------------------------------------------- metrics
def spearman(a, b):
    from scipy.stats import spearmanr
    if len(a) < 3 or np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    return float(spearmanr(a, b).statistic)


def auc(y, s):
    from sklearn.metrics import roc_auc_score
    y = np.asarray(y, bool)
    if y.all() or not y.any():
        return float("nan")
    return float(roc_auc_score(y, s))


def pair_acc(score, label, mask):
    """Over the pairs in `mask` (i < j), the fraction ordered by `score` as `label` orders them (ties in score 0.5)."""
    i, j = np.nonzero(np.triu(mask, 1))
    if not len(i):
        return float("nan"), 0
    ds, dl = score[i] - score[j], label[i] - label[j]
    ok = np.where(ds == 0, 0.5, (np.sign(ds) == np.sign(dl)).astype(float))
    return float(ok.mean()), int(len(i))


def pair_masks(rows):
    sig = np.array([float(r.get("sigma") or 0) for r in rows])
    hp = np.array([float(r["feat"]["hpwl"]) for r in rows])
    cl = np.array([bool(r.get("clean")) for r in rows]).astype(float)
    sv = np.array([float(r["signal_vias"]) for r in rows])
    same_sig = (sig[:, None] == sig[None, :]) & (sig[:, None] > 0)
    diff_clean = cl[:, None] != cl[None, :]
    near = np.abs(hp[:, None] - hp[None, :]) / ((hp[:, None] + hp[None, :]) / 2) < 0.05
    return {"sv_same_sigma": (same_sig & (sv[:, None] != sv[None, :]), sv, -1.0),
            "clean_same_sigma": (same_sig & diff_clean, cl, 1.0),
            "clean_boundary": (near & diff_clean, cl, 1.0)}, hp


def board_metrics(rows, pc, ps):
    """One board's numbers for one model: Spearman of the predicted signal vias, AUC on clean, the three pair accuracies."""
    sv = np.array([float(r["signal_vias"]) for r in rows])
    cl = np.array([bool(r.get("clean")) for r in rows])
    out = {"n": len(rows), "clean_n": int(cl.sum()), "spearman_sv": spearman(ps, sv), "auc_clean": auc(cl, pc)}
    masks, _ = pair_masks(rows)
    for name, (m, lab, sgn) in masks.items():
        score = ps if name.startswith("sv") else pc
        out[name], out[name + "_pairs"] = pair_acc(np.asarray(score, float), lab, m)
    return out


def boot_gain(rows, pc_m, ps_m, pc_h, ps_h, reps=300, seed=0):
    """90 % bootstrap interval (rows resampled within the board) of model minus HPWL on each pair metric."""
    rng = np.random.default_rng(seed)
    masks, _ = pair_masks(rows)
    out = {}
    n = len(rows)
    for name, (m, lab, _) in masks.items():
        sm = np.asarray(ps_m if name.startswith("sv") else pc_m, float)
        sh = np.asarray(ps_h if name.startswith("sv") else pc_h, float)
        g = []
        for _ in range(reps):
            idx = rng.integers(0, n, n)
            mm = m[np.ix_(idx, idx)]
            a, k = pair_acc(sm[idx], lab[idx], mm)
            b, _ = pair_acc(sh[idx], lab[idx], mm)
            if k:
                g.append(a - b)
        out[name] = [round(float(np.percentile(g, 5)), 3), round(float(np.percentile(g, 95)), 3)] if g else None
    return out
