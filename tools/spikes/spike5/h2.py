#!/usr/bin/env python3
"""Spike 5, H2: distance rows per (source org, package, role), repo as the unit of n, from the role measurements.

  python3 -I tools/spikes/spike5/h2.py merge --in A.jsonl B.jsonl ... --out /tmp/spike5/h2/roles.jsonl
  python3 -I tools/spikes/spike5/h2.py table --roles /tmp/spike5/h2/roles.jsonl --out tools/spikes/spike5/h2-summary.json
  python3 -I tools/spikes/spike5/h2.py check     # the medians, IQRs, pooling pairs and the designer-package split, from the committed repo medians

merge: one instance per (repo, part, ref), modules, through-hole parts and silk out, counts per drop reason. table: per repo a
median of its rows, then the median and IQR of the repo medians; rows published only at n >= 5 instances-with-a-row and 3 repos
(the licence floor); two rows pool when each median sits inside the other's IQR. Designer against package: within a package and
role, the spread of org medians; within an org and role, the spread of package medians. Counts and quantiles only; poses stay in /tmp.
"""
import argparse, json, statistics as st, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MAX_EXT = {"imu6": 6.5, "hbridge": 16.0}


def family(pkg):
    """A package family from the key: the importers' pad-extent noise (LGA-14 reads 2.32 to 2.72 mm by library) must not split a package."""
    import re
    m = re.match(r"(\d+)p-([\d.]+)x([\d.]+)", pkg)
    n, w, h = int(m.group(1)), float(m.group(2)), float(m.group(3))
    if n == 14 and w <= 3.0 and h <= 2.5:
        return "LGA-14"
    if n == 16 and w <= 3.0 and h <= 3.0:
        return "16-pad 3x3"
    if n == 16 and 3.5 <= w <= 4.5 and 2.0 <= h <= 3.0:
        return "LGA-16 3x4.5"
    if n == 16 and 5.0 <= w <= 6.5 and 4.0 <= h <= 5.0:
        return "HTSSOP-16"
    if n == 24 and w <= 3.5:
        return "QFN-24 3x3"
    if n == 24 and 3.5 < w <= 4.5:
        return "QFN-24 4x4"
    if n == 24 and 6.5 <= w <= 8.5:
        return "SSOP-24"
    if n == 12 and w <= 3.5:
        return "WSON-12"
    if n == 8 and "-ep" in pkg and 5.0 <= w <= 6.5:
        return "HSOP-8"
    if n == 8 and 2.0 <= w <= 3.5 and h <= 2.5:
        return "SON-8"
    return pkg


def q(xs, p):
    xs = sorted(xs)
    i = p * (len(xs) - 1)
    lo, hi = int(i), min(int(i) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def merge(a):
    seen, keep, drop = set(), [], Counter()
    for fn in a.inputs:
        for l in open(fn):
            r = json.loads(l)
            if not r.get("ok"):
                drop[(r.get("org"), (r.get("why") or "")[:32])] += 1
                continue
            if r.get("tht") or r["ext"][0] > MAX_EXT.get(r["cls"], 99):
                drop[(r.get("org"), "module or through-hole by pad extent")] += 1
                continue
            k = (r["repo"], r["part"], r["ref"])
            if k in seen:
                drop[(r.get("org"), "same (repo, part, ref)")] += 1
                continue
            seen.add(k)
            keep.append(r)
    with open(a.out, "w") as f:
        for r in keep:
            f.write(json.dumps(r) + "\n")
    print(len(keep), "instances")
    for k, v in sorted(drop.items(), key=lambda kv: -kv[1])[:14]:
        print(" ", k, v)
    json.dump({f"{k[0]}|{k[1]}": v for k, v in drop.items()}, open(str(a.out) + ".drops.json", "w"), indent=0)


def row_stats(items):
    """items: [(repo, d)]. Repo medians, then their quantiles."""
    by = defaultdict(list)
    for repo, d in items:
        by[repo].append(d)
    med = sorted(round(st.median(v), 3) for v in by.values())
    return {"n": len(items), "repos": len(by), "repo_medians": med, **quant(med)}


def quant(med):
    return {"median": round(st.median(med), 2), "q25": round(q(med, .25), 2), "q75": round(q(med, .75), 2), "p90": round(q(med, .9), 2)}


def pools(a, b):
    return a["q25"] <= b["median"] <= a["q75"] and b["q25"] <= a["median"] <= b["q75"]


def compare(published):
    """Pairs in one class and role that share a package (designer axis) or a source (package axis); which pool; the median gaps."""
    keys = sorted(published)
    pairs, org_gap, pkg_gap = [], [], []
    for i, ka in enumerate(keys):
        for kb in keys[i + 1:]:
            if ka[0] != kb[0] or ka[3] != kb[3] or (ka[2] != kb[2] and ka[1] != kb[1]):
                continue
            A, B = published[ka], published[kb]
            same_pkg = ka[2] == kb[2]
            (org_gap if same_pkg else pkg_gap).append(abs(A["median"] - B["median"]))
            pairs.append({"a": "|".join(ka), "b": "|".join(kb), "ma": A["median"], "mb": B["median"], "pool": pools(A, B), "axis": "designer" if same_pkg else "package"})
    dv = {"designer_pairs": len(org_gap), "designer_pooling": sum(p["pool"] for p in pairs if p["axis"] == "designer"), "designer_median_gap_mm": round(st.median(org_gap), 2),
          "package_pairs": len(pkg_gap), "package_pooling": sum(p["pool"] for p in pairs if p["axis"] == "package"), "package_median_gap_mm": round(st.median(pkg_gap), 2)}
    return pairs, dv


def check(a):
    s = json.load(open(ROOT / "tools/spikes/spike5/h2-summary.json"))
    pub = {}
    for k, v in s["rows"].items():
        assert v["n"] >= 5 and v["repos"] >= 3, k
        got = quant(v["repo_medians"])
        assert all(got[x] == v[x] for x in got), (k, got)
        pub[tuple(k.split("|"))] = v
    pairs, dv = compare(pub)
    assert pairs == s["pairs"] and dv == s["designer_vs_package"], dv
    print(f"{len(pub)} rows, {len(pairs)} pairs; designer gap {dv['designer_median_gap_mm']} mm, {dv['designer_pooling']} of {dv['designer_pairs']} pool; "
          f"package gap {dv['package_median_gap_mm']} mm, {dv['package_pooling']} of {dv['package_pairs']} pool")


def table(a):
    rows = [json.loads(l) for l in open(a.roles)]
    insts = Counter()
    cells = defaultdict(list)
    fams = defaultdict(list)
    for r in rows:
        org = r.get("org") or "kicad"
        insts[(r["cls"], org)] += 1
        for x in r["rows"]:
            if x["back"]:
                continue
            cells[(r["cls"], org, family(r["pkg"]), x["role"])].append((r["repo"], x["d_pad"]))
            fams[(r["cls"], x["role"], "class")].append((r["repo"], x["d_pad"]))
    out = {"instances": {f"{c}|{o}": v for (c, o), v in sorted(insts.items())}, "rows": {}, "pairs": [], "class_rows": {}}
    published = {}
    for k, v in sorted(cells.items()):
        s = row_stats(v)
        if s["n"] >= 5 and s["repos"] >= 3:
            published[k] = s
            out["rows"]["|".join(k)] = s
    for k, v in sorted(fams.items()):
        s = row_stats(v)
        if s["n"] >= 5 and s["repos"] >= 3:
            out["class_rows"][f"{k[0]}|{k[1]}"] = s
    out["pairs"], out["designer_vs_package"] = compare(published)
    json.dump(out, open(a.out, "w"), indent=1)
    print(json.dumps(out["designer_vs_package"]), json.dumps(out["instances"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["merge", "table", "check"])
    ap.add_argument("--in", dest="inputs", nargs="*")
    ap.add_argument("--out")
    ap.add_argument("--roles")
    a = ap.parse_args()
    {"merge": merge, "table": table, "check": check}[a.cmd](a)


if __name__ == "__main__":
    main()
