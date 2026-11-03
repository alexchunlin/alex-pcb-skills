#!/usr/bin/env python3
"""Spike 2 statistical reference circuits: the sub-netlist within two hops of each pin of a part, counted over the corpus.

  python3 -I tools/corpus/refstat.py netlists [--parts ...] [--jobs 6]   # kicad-cli sch export netlist per hit (WORK/net/)
  python3 -I tools/corpus/refstat.py features                            # per instance, per canonical pin: hop-1/hop-2 features
  pcb py tools/corpus/boardmeasure.py WORK/board-jobs.json WORK/board-measure.jsonl   # KiCad's Python: pad distances, offsets
  python3 -I tools/corpus/refstat.py emit [--min-support 0.7]            # dominant patterns -> tools/bench/data/refstat-rows.json
  python3 -I tools/corpus/refstat.py report                              # the per-pin table

A feature is `CLASS:BAND:OTHER` for each part on the pin's net (hop 1): class from the reference prefix (C, R, L, FB, D,
...), value band (caps 10n/100n/1u/10u/22u/100u+, resistors by decade), and what its other pin lands on (GND, another
pin of the same IC as IC:<pin>, a power-looking net PWR, or SIG). Hop 2 is `via:CLS1>CLASS:BAND:OTHER` through a
two-pin series part. Support = share of instances (pin connected) with at least one part showing the feature. Where a
board exists, the distance from the IC pad to the nearest pad of a part realising the feature is the PCB statistic.
Plain python3 except boardmeasure.py (KiCad's Python, through `pcb py`). Downloads stay under WORK; nothing there is run.
"""
from __future__ import annotations

import argparse, concurrent.futures as cf, json, os, re, statistics, subprocess, sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "tools/bench/data/corpus-index.jsonl"
ROWS_OUT = ROOT / "tools/bench/data/refstat-rows.json"
KICAD_CLI = os.environ.get("KICAD_CLI", "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
sys.path.insert(0, str(ROOT / "skills/kicad-design/scripts"))
from pcbrefstat import PART_RX, PASSIVE, canon_pin, coarse_band, part_regex, value_band, comp_class, gnd_like, power_like  # noqa: E402


def load_index():
    return [json.loads(l) for l in open(INDEX)]


def export(sch: Path, out: Path):
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        return True, "cached"
    try:
        p = subprocess.run([KICAD_CLI, "sch", "export", "netlist", "--format", "kicadxml", "-o", str(out), str(sch)],
                           capture_output=True, text=True, timeout=120, cwd="/tmp")
    except subprocess.TimeoutExpired:
        return False, "timeout"
    return out.exists(), (p.stderr or p.stdout)[-300:]


def cmd_netlists(a, work):
    rows = [r for r in load_index() if r["part"] in a.parts.split(",")]
    keys = sorted({r["key"] for r in rows})
    res = {}

    def one(k):
        sch = next((work / "sch" / f"{k}.{e}" for e in ("kicad_sch", "sch") if (work / "sch" / f"{k}.{e}").exists()), None)
        if sch is None:
            return k, (False, "no schematic text")
        return k, export(sch, work / "net" / f"{k}.xml")

    with cf.ThreadPoolExecutor(a.jobs) as ex:
        for k, (ok, msg) in ex.map(one, keys):
            res[k] = {"ok": ok, "msg": msg}
    json.dump(res, open(work / "netlists.json", "w"), indent=0)
    print(f"netlists: {sum(v['ok'] for v in res.values())} of {len(res)} exported")


def kids(e, tag):
    x = e.find(tag)
    return list(x) if x is not None else []


def parse_netlist(path):
    r = ET.parse(path).getroot()
    comps, libparts, padnet, nets = {}, {}, {}, {}
    for c in kids(r, "components"):
        ls = c.find("libsource")
        comps[c.get("ref")] = {"value": c.findtext("value") or "", "lib": (ls.get("lib"), ls.get("part")) if ls is not None else ("", ""),
                               "footprint": c.findtext("footprint") or ""}
    for p in kids(r, "libparts"):
        libparts[(p.get("lib"), p.get("part"))] = {pin.get("num"): pin.get("name") or "" for pin in kids(p, "pins")}
    for n in kids(r, "nets"):
        nodes = []
        for x in n:
            nodes.append((x.get("ref"), x.get("pin"), x.get("pinfunction") or ""))
            padnet[(x.get("ref"), x.get("pin"))] = n.get("name")
        nets[n.get("name")] = nodes
    return comps, libparts, padnet, nets


def instance_features(part, NL, ref):
    comps, libparts, padnet, nets = NL
    pins = {}
    names = dict(libparts.get(comps[ref]["lib"], {}))
    for (r, p), net in padnet.items():
        if r == ref:
            fn = next((f for (rr, pp, f) in nets[net] if rr == ref and pp == p), "")
            names.setdefault(p, fn)
            if not names.get(p):
                names[p] = fn
    ic_pin_of_net = {}
    for (r, p), net in padnet.items():
        if r == ref:
            ic_pin_of_net.setdefault(net, canon_pin(part, p, names.get(p, "")))

    def other_side(cref, net):
        cp = [(p, n) for (r, p), n in padnet.items() if r == cref]
        others = [n for p, n in cp if n != net]
        if len(cp) != 2:
            return None, "MULTI"
        if not others:
            return None, "SAME"
        o = others[0]
        if gnd_like(o):
            return o, "GND"
        if o in ic_pin_of_net:
            return o, "IC:" + ic_pin_of_net[o]
        if power_like(o):
            return o, "PWR"
        return o, "SIG"

    out = {}
    for (r, p), net in padnet.items():
        if r != ref:
            continue
        cpin = canon_pin(part, p, names.get(p, ""))
        if gnd_like(net) or cpin in out:
            continue
        nodes = [(rr, pp) for (rr, pp, _) in nets[net] if rr != ref]
        f1, f2, real = set(), set(), defaultdict(list)
        for cref, _ in nodes:
            if cref not in comps:
                continue
            cls = comp_class(cref, comps[cref]["lib"][1])
            if cls not in PASSIVE:
                continue
            band = value_band(cls, comps[cref]["value"])
            o, side = other_side(cref, net)
            for b in {band, coarse_band(cls, band), "*"}:
                key = f"{cls}:{b}:{side}"
                f1.add(key); real[key].append(cref)
            if o and side in ("SIG", "PWR") and cls in ("R", "L", "FB", "D"):
                for (c2, _, _) in nets.get(o, []):
                    if c2 in (ref, cref) or c2 not in comps:
                        continue
                    cls2 = comp_class(c2, comps[c2]["lib"][1])
                    if cls2 not in PASSIVE:
                        continue
                    b2 = coarse_band(cls2, value_band(cls2, comps[c2]["value"]))
                    _, s2 = other_side(c2, o)
                    k2 = f"via:{cls}>{cls2}:{b2}:{s2}"
                    f2.add(k2); real[k2].append(c2)
        out[cpin] = {"pin": p, "net": net, "power_net": power_like(net), "n_nodes": len(nodes), "f1": sorted(f1), "f2": sorted(f2),
                     "real": {k: sorted(set(v)) for k, v in real.items()}}
    return out


def cmd_features(a, work):
    rows = [r for r in load_index() if r["part"] in a.parts.split(",")]
    nl = json.load(open(work / "netlists.json"))
    out, stats = [], Counter()
    for r in rows:
        k = r["key"]
        if not nl.get(k, {}).get("ok"):
            stats[(r["part"], "export_failed")] += 1; continue
        try:
            NL = parse_netlist(work / "net" / f"{k}.xml")
        except ET.ParseError:
            stats[(r["part"], "unparseable")] += 1; continue
        rx = part_regex(r["part"])
        refs = [ref for ref, c in NL[0].items() if rx.search(c["value"]) or rx.search(c["lib"][1] or "")]
        if not refs:
            stats[(r["part"], "part_not_in_netlist")] += 1; continue
        got = False
        for ref in refs[:4]:
            feats = instance_features(r["part"], NL, ref)
            if not any(v["n_nodes"] for v in feats.values()):
                continue
            got = True
            out.append({"key": k, "repo": r["repo"], "part": r["part"], "ref": ref, "sch_version": r["sch_version"],
                        "sch_format": r["sch_format"], "pins": feats})
        stats[(r["part"], "ok" if got else "no_connected_pins")] += 1
    with open(work / "features.jsonl", "w") as f:
        for x in out:
            f.write(json.dumps(x) + "\n")
    json.dump({f"{p}|{s}": n for (p, s), n in sorted(stats.items())}, open(work / "features-stats.json", "w"), indent=1)
    for (p, s), n in sorted(stats.items()):
        print(f"{p:18} {s:22} {n}")
    # board jobs for boardmeasure.py: instances whose hit has a matched board
    idx = {(r["key"], r["part"]): r for r in rows}
    jobs = []
    for x in out:
        r = idx[(x["key"], x["part"])]
        if r.get("board") and r["board"].get("match"):
            jobs.append({"key": x["key"], "part": x["part"], "ref": x["ref"], "rx": PART_RX[x["part"]], "board": str(work / "pcb" / f"{x['key']}.kicad_pcb"),
                         "pins": {cp: v["pin"] for cp, v in x["pins"].items()}, "all_pins": None})
    json.dump(jobs, open(work / "board-jobs.json", "w"))
    print(f"{len(out)} instances with features, {len(jobs)} with a board -> {work / 'board-jobs.json'}")


def dedupe(instances):
    """One instance per (repo, part, ref): the dataset carries forks and copies of the same project."""
    seen, out = set(), []
    for x in instances:
        k = (x["repo"], x["part"], x["ref"])
        if k in seen:
            continue
        seen.add(k); out.append(x)
    return out


def board_measures(work):
    p = work / "board-measure.jsonl"
    if not p.exists():
        return {}
    out = {}
    for l in open(p):
        m = json.loads(l)
        out[(m["key"], m["ref"])] = m
    return out


def pin_stats(part, inst, bm):
    per_pin = defaultdict(lambda: {"n": 0, "f": Counter(), "dist": defaultdict(list), "n_board": 0})
    for x in inst:
        m = bm.get((x["key"], x["ref"]))
        for cp, v in x["pins"].items():
            if not v["n_nodes"]:
                continue
            s = per_pin[cp]
            s["n"] += 1
            for f in set(v["f1"]) | set(v["f2"]):
                s["f"][f] += 1
            if m and m.get("ok") and cp in m["pins"]:
                s["n_board"] += 1
                near = m["pins"][cp]   # {ref: mm} pad-to-pad, same net
                for f, refs in v["real"].items():
                    ds = [near[rf] for rf in refs if rf in near]
                    if ds:
                        s["dist"][f].append(min(ds))
    return per_pin


def pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    i = min(len(xs) - 1, max(0, int(round(q * (len(xs) - 1)))))
    return round(xs[i], 2)


def cmd_emit(a, work):
    inst = dedupe([json.loads(l) for l in open(work / "features.jsonl")])
    bm = board_measures(work)
    rows, table = [], []
    for part in a.parts.split(","):
        pi = [x for x in inst if x["part"] == part]
        if len({x["repo"] for x in pi}) < 30:
            print(f"{part}: {len(pi)} instances, under 30: no rows"); continue
        for cp, s in sorted(pin_stats(part, pi, bm).items(), key=lambda kv: -kv[1]["n"]):
            if s["n"] < 30:
                continue
            ranked = sorted(s["f"].items(), key=lambda kv: (-kv[1], kv[0]))
            strong = {f for f, n in ranked if n / s["n"] >= a.min_support}
            for f, n in ranked:
                sup = n / s["n"]
                d = s["dist"].get(f, [])
                table.append({"part": part, "pin": cp, "feature": f, "support": round(sup, 3), "n": s["n"], "n_board": len(d),
                              "dist_median_mm": pct(d, 0.5), "dist_p80_mm": pct(d, 0.8), "dist_p90_mm": pct(d, 0.9)})
                if f not in strong:
                    continue
                if f.startswith("via:"):
                    pattern = {"feature": f}
                else:
                    cls, band, side = f.split(":", 2)
                    if side in ("SIG", "SAME", "MULTI"):
                        continue   # design-specific (an LED resistor, a pull-up to an MCU pin): counted, not a row
                    # the most specific dominant band only: exact, then >=1u/<1u, then any value
                    rank = {"*": 0, "bulk": 1, "bypass": 1}.get(band, 2)
                    if any(g != f and g.startswith(cls + ":") and g.endswith(":" + side) and
                           {"*": 0, "bulk": 1, "bypass": 1}.get(g.split(":")[1], 2) > rank for g in strong):
                        continue
                    pattern = {"feature": f, "class": cls, "band": band, "to": side}
                if len(d) >= 20:
                    pattern["max_mm"] = pct(d, 0.9)
                rows.append({"kind": "refstat", "part": part, "pin": cp, "pattern": pattern, "support": round(sup, 3),
                             "n": s["n"], "n_board": len(d), "dist_median_mm": pct(d, 0.5)})
    # one row per two-pin part seen from both of its IC pins (EN -> IC:3V3 and 3V3 -> IC:EN are the same resistor)
    keep = []
    for r in rows:
        to = r["pattern"].get("to", "")
        twin = next((x for x in rows if x is not r and x["part"] == r["part"] and to == "IC:" + x["pin"]
                     and x["pattern"].get("to") == "IC:" + r["pin"] and x["pattern"].get("class") == r["pattern"].get("class")), None)
        if twin is None or (r["support"], r["pin"]) > (twin["support"], twin["pin"]):
            keep.append(r)
    rows = keep
    json.dump({"_doc": "refstat rows from tools/corpus/refstat.py emit over bshada/open-schematics (spike 2); one row per "
                       "(part, pin, feature) with support >= %.2f; max_mm = the corpus p90 pad-to-pad distance where 20+ boards "
                       "measured it" % a.min_support, "rows": rows}, open(ROWS_OUT, "w"), indent=1)
    json.dump(table, open(work / "refstat-table.json", "w"), indent=0)
    print(f"{len(rows)} rows -> {ROWS_OUT}")
    for r in rows:
        print(f"  {r['part']:18} {r['pin']:6} {r['pattern']['feature']:26} support {r['support']:.2f} n {r['n']:4} boards {r['n_board']:4} "
              f"median {r['dist_median_mm']} max {r['pattern'].get('max_mm')}")


def cmd_report(a, work):
    table = json.load(open(work / "refstat-table.json"))
    for part in a.parts.split(","):
        print(f"== {part}")
        for t in table:
            if t["part"] == part and t["support"] >= a.show:
                print(f"  {t['pin']:7} {t['feature']:28} {t['support']:.2f} of {t['n']:4}  boards {t['n_board']:4} median {t['dist_median_mm']} p90 {t['dist_p90_mm']}")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["netlists", "features", "emit", "report"])
    ap.add_argument("--work", default="/tmp/spike2-corpus")
    ap.add_argument("--parts", default="AMS1117-3.3,LSM6DS3,ESP32-WROOM-32,ESP32-S3-WROOM-1")
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--min-support", type=float, default=0.7)
    ap.add_argument("--show", type=float, default=0.3)
    a = ap.parse_args(argv)
    work = Path(a.work)
    {"netlists": cmd_netlists, "features": cmd_features, "emit": cmd_emit, "report": cmd_report}[a.mode](a, work)


if __name__ == "__main__":
    main(sys.argv[1:])
