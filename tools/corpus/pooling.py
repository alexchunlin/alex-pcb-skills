"""Spike 5: hierarchical pooling of a satellite statistic over part, package and class. Plain python3, no library.

A part with n >= k keeps its own estimate; below that it keeps n / (n + k) and hands the rest down, the package level
splits that remainder the same way, and the class takes what is left. Three levels, because `imu6` medians run 1.7 to 5.5 mm
by package: shrinking a part straight to the class pulls it toward a mixture. A held-out level has n = 0 and weight 0.
"""

K = 30


def weights(ns, k=K):
    """Mixture weights for levels ordered specific to general, [n_part, n_package, n_class]. Sum 1; empty levels get 0."""
    if not any(ns):
        raise ValueError("no level has data")
    out, rest = [], 1.0
    last = max(i for i, n in enumerate(ns) if n)
    for i, n in enumerate(ns):
        if i == last:
            out.append(rest)
            rest = 0.0
        else:
            w = 1.0 if n >= k else n / (n + k)
            out.append(rest * w)
            rest -= rest * w
    return out


def shrink(levels, k=K):
    """The pooled estimate from [(n, estimate)] ordered specific to general."""
    ws = weights([n for n, _ in levels], k)
    return sum(w * e for w, (n, e) in zip(ws, levels) if w > 0)


def quantile(xs, p):
    xs = sorted(xs)
    if not xs:
        raise ValueError("no data")
    i = p * (len(xs) - 1)
    lo = int(i)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def pooled_quantiles(levels, ps=(0.25, 0.5, 0.75, 0.9), k=K):
    """{p: estimate} from levels [xs] ordered specific to general, each quantile shrunk by the same weights."""
    ns = [len(x) for x in levels]
    return {p: shrink([(n, quantile(x, p) if n else 0.0) for n, x in zip(ns, levels)], k) for p in ps}


def usable(rows, min_n=5, min_repos=3, repo=lambda r: r[-1]):
    """A level counts only at n >= 5 rows from 3 repos: the licence floor, and below it a level is one board's layout."""
    return len(rows) >= min_n and len({repo(r) for r in rows}) >= min_repos
