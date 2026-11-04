#!/usr/bin/env python3
"""Spike 5: the class-prior pools each seeded arm draws from, and the counts behind them. Raw poses stay under /tmp/spike5/pools.

  python3 -I tools/spikes/spike5/pool.py --roles /tmp/spike5/h2/roles.jsonl       # writes the pools and tools/spikes/spike5/pool-summary.json

Target satellites come from the board's own nets and its `decoupling` rows (TARGET below). Levels: part, package, class, each kept at
n >= 5 rows from 3 repos; a role empty at every level falls back to its family (FAMILY). Held out: `class_part` drops the LSM6DS3
everywhere, `class_pkg` all of LGA-14 everywhere, `class` the DRV8874 everywhere. Front-side satellites only.
"""
import argparse, json, statistics as st, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools/corpus"))
sys.path.insert(0, str(HERE))
import pooling as P  # noqa: E402
from h2 import family  # noqa: E402

TARGET = {"r1": {"part": "LSM6DS3", "family": "LGA-14", "cls": "imu6",
                 "sats": {"C1": {"pin": "8", "role": "bypass", "sat_pin_pad": "1", "sat_other_pad": "2"},
                          "C2": {"pin": "5", "role": "bypass", "sat_pin_pad": "1", "sat_other_pad": "2"},
                          "C3": {"pin": "8", "role": "bulk", "sat_pin_pad": "1", "sat_other_pad": "2"}}},
          "r2": {"part": "DRV8874", "family": "HTSSOP-16", "cls": "hbridge",
                 "sats": {"C10": {"pin": "11", "role": "vm_bypass", "sat_pin_pad": "1", "sat_other_pad": "2"},
                          "C11": {"pin": "11", "role": "vm_bulk", "sat_pin_pad": "1", "sat_other_pad": "2"},
                          "R10": {"pin": "6", "role": "current_mirror", "sat_pin_pad": "1", "sat_other_pad": "2"},
                          "C12": {"pin": "12", "role": "cp_res", "sat_pin_pad": "1", "sat_other_pad": "2"},
                          "C13": {"pin": "13", "role": "cp_fly", "sat_pin_pad": "1", "sat_other_pad": "2"}}}}
FAMILY = {"current_mirror": ["current_mirror", "limit_setting", "shunt"], "limit_setting": ["limit_setting", "current_mirror", "shunt"], "shunt": ["shunt", "current_mirror", "limit_setting"]}
ARMS = {"r1-class_part": ("r1", "part"), "r1-class_pkg": ("r1", "family"), "r2-class": ("r2", "part")}


def rows_of(insts, cls, roles):
    out = []
    for r in insts:
        if r["cls"] != cls:
            continue
        for x in r["rows"]:
            if x["back"] or x["role"] not in roles or abs(x["du"]) > 40 or abs(x["dv"]) > 40:
                continue
            out.append({"du": x["du"], "dv": x["dv"], "ang": x["ang"], "repo": r["repo"], "part": r["part"], "fam": family(r["pkg"]), "d": x["d_pad"], "org": r.get("org") or "kicad"})
    return out


def build(insts, board, hold, moved):
    t = TARGET[board]
    spec, info = {}, {}
    for ref, sat in t["sats"].items():
        if ref not in moved:
            continue
        got = None
        for role in FAMILY.get(sat["role"], [sat["role"]]):
            rs = rows_of(insts, t["cls"], {role})
            rs = [r for r in rs if r["part"] != t["part"]] if hold == "part" else [r for r in rs if r["fam"] != t["family"]]
            lv = [("package", [r for r in rs if r["fam"] == t["family"]]), ("class", rs)]
            lv = [(k, v if P.usable(v, repo=lambda r: r["repo"]) else []) for k, v in lv]
            if any(v for _, v in lv):
                got = role, lv
                break
        if got is None:
            info[ref] = {"role": sat["role"], "n": 0}
            continue
        role, lv = got
        ws = P.weights([0] + [len(v) for _, v in lv])[1:]
        spec[ref] = {"pin": sat["pin"], "role": role, "sat_pin_pad": sat["sat_pin_pad"], "sat_other_pad": sat["sat_other_pad"],
                     "levels": [{"level": k, "weight": w, "rows": [[r["du"], r["dv"], r["ang"], r["repo"]] for r in v]} for (k, v), w in zip(lv, ws) if w > 0]}
        q = P.pooled_quantiles([[]] + [[r["d"] for r in v] for _, v in lv])
        info[ref] = {"role": sat["role"], "used_role": role, "levels": {k: {"n": len(v), "repos": len({r["repo"] for r in v}), "weight": round(w, 3)} for (k, v), w in zip(lv, ws)},
                     "d_median": round(q[0.5], 2), "d_q25": round(q[0.25], 2), "d_q75": round(q[0.75], 2)}
    return spec, info


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--roles", default="/tmp/spike5/h2/roles.jsonl")
    ap.add_argument("--r2-moved", default="C10,C11,R10")
    ap.add_argument("--out", default="/tmp/spike5/pools")
    a = ap.parse_args()
    insts = [json.loads(l) for l in open(a.roles)]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    moved = {"r1": ["C1", "C2", "C3"], "r2": a.r2_moved.split(",")}
    summ = {}
    for name, (board, hold) in ARMS.items():
        spec, info = build(insts, board, hold, moved[board])
        json.dump(spec, open(out / f"{name}.json", "w"))
        summ[name] = info
    # the moved-set rule on r2: a charge-pump role joins at n >= 5 from 3 repos with the DRV8874 held out
    rule = {}
    for role in ("cp_res", "cp_fly"):
        rs = [r for r in rows_of(insts, "hbridge", {role}) if r["part"] != "DRV8874"]
        parts = {}
        for r in rs:
            parts[r["part"]] = parts.get(r["part"], 0) + 1
        rule[role] = {"n": len(rs), "repos": len({r["repo"] for r in rs}), "parts": parts, "joins": P.usable(rs, repo=lambda r: r["repo"])}
    summ["r2_moved_rule"] = rule
    json.dump(summ, open(HERE / "pool-summary.json", "w"), indent=1)
    print(json.dumps(summ, indent=0)[:2600])


if __name__ == "__main__":
    main()
