#!/usr/bin/env python3
"""Spike 5, H2: distance rows per (source org, package, role), repo as the unit of n, from the role measurements.

  python3 -I tools/spikes/spike5/h2.py merge --in A.jsonl B.jsonl ... --out /tmp/spike5/h2/roles.jsonl
  python3 -I tools/spikes/spike5/h2.py table --roles /tmp/spike5/h2/roles.jsonl --out tools/spikes/spike5/h2-summary.json

merge: one instance per (repo, part, ref), modules, through-hole parts and silk out, counts per drop reason. table: per repo a
median of its rows, then the median and IQR of the repo medians; rows published only at n >= 5 instances-with-a-row and 3 repos
(the licence floor); two rows pool when each median sits inside the other's IQR. Designer against package: within a package and
role, the spread of org medians; within an org and role, the spread of package medians. Counts and quantiles only; poses stay in /tmp.
"""
import argparse, json, statistics as st, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PKG_NAME = {"14p-2.5x2.0": "LGA-14 (3x2.5)", "16p-2.5x2.5": "LGA-16 (3x3)", "24p-4.0x4.0-ep": "QFN-24 (4x4)", "24p-3.0x3.0-ep": "QFN-24 (3x3)", "16p-5.5x4.5-ep": "HTSSOP-16",
            "12p-2.5x2.0-ep": "WSON-12", "24p-7.0x7.0": "SSOP-24", "24p-7.5x7.0": "SSOP-24", "8p-5.5x4.0-ep": "HSOP-8", "16p-2.5x2.0": "LGA-16 (2.5x3)"}
MAX_EXT = {"imu6": 6.5, "hbridge": 16.0}


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
    med = [st.median(v) for v in by.values()]
    return {"n": len(items), "repos": len(by), "median": round(st.median(med), 2), "q25": round(q(med, .25), 2), "q75": round(q(med, .75), 2), "p90": round(q(med, .9), 2)}


def pools(a, b):
    return a["q25"] <= b["median"] <= a["q75"] and b["q25"] <= a["median"] <= b["q75"]


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
            cells[(r["cls"], org, r["pkg"], x["role"])].append((r["repo"], x["d_pad"]))
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
    keys = list(published)
    n_pool = n_pairs = 0
    org_spread, pkg_spread = [], []
    for i, ka in enumerate(keys):
        for kb in keys[i + 1:]:
            if ka[0] != kb[0] or ka[3] != kb[3]:
                continue
            A, B = published[ka], published[kb]
            same_pkg, same_org = ka[2] == kb[2], ka[1] == kb[1]
            if same_pkg and not same_org:
                org_spread.append(abs(A["median"] - B["median"]))
            if same_org and not same_pkg:
                pkg_spread.append(abs(A["median"] - B["median"]))
            if same_pkg or same_org:
                n_pairs += 1
                p = pools(A, B)
                n_pool += p
                out["pairs"].append({"a": "|".join(ka), "b": "|".join(kb), "ma": A["median"], "mb": B["median"], "pool": p, "axis": "designer" if same_pkg else "package"})
    out["designer_vs_package"] = {"org_diffs_n": len(org_spread), "org_median_diff_mm": round(st.median(org_spread), 2) if org_spread else None,
                                  "pkg_diffs_n": len(pkg_spread), "pkg_median_diff_mm": round(st.median(pkg_spread), 2) if pkg_spread else None,
                                  "pairs_pooling": n_pool, "pairs": n_pairs,
                                  "designer_pooling": sum(p["pool"] for p in out["pairs"] if p["axis"] == "designer"), "designer_pairs": sum(p["axis"] == "designer" for p in out["pairs"]),
                                  "package_pooling": sum(p["pool"] for p in out["pairs"] if p["axis"] == "package"), "package_pairs": sum(p["axis"] == "package" for p in out["pairs"])}
    json.dump(out, open(a.out, "w"), indent=1)
    print(json.dumps(out["designer_vs_package"]), json.dumps(out["instances"]))
    for k, s in out["rows"].items():
        print(k, s)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["merge", "table"])
    ap.add_argument("--in", dest="inputs", nargs="*")
    ap.add_argument("--out")
    ap.add_argument("--roles")
    a = ap.parse_args()
    {"merge": merge, "table": table}[a.cmd](a)


if __name__ == "__main__":
    main()
