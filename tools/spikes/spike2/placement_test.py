#!/usr/bin/env python3
"""Spike 2 placement priors: corpus satellite offsets, and prior-seeded vs uniform placements routed with KRT.

  python3 -I tools/spikes/spike2/placement_test.py priors [--work /tmp/spike2-corpus]     # distributions -> priors-*.json
  python3 -I tools/spikes/spike2/placement_test.py route [--n 50] [--jobs 3]              # 2 x n seeds on the rung-1 board
  python3 -I tools/spikes/spike2/placement_test.py summary

Satellites come from boardmeasure.py: every two-pad footprint on a net of an IC pin, its centre in the IC's frame and its
rotation relative to the IC (mod 180). Classes: bypass cap (< 1 uF), bulk cap (>= 1 uF), inductor or ferrite, resistor.
The routing test moves C1, C2, C3 of examples/rung1-zener-a2-sonnet (the LSM6DS3's capacitors; the IC, connectors,
jumpers and pull-ups stay), stripped of copper with the zones kept, then per seed: KRT `--quick 2` (the seed judge) and
`pcb route auto` (the production route: engine pass, refill, dual DRC, second pass). At most `--jobs` KRT processes.
"""
from __future__ import annotations

import argparse, concurrent.futures as cf, json, math, os, random, shutil, statistics, subprocess, sys, time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "skills/kicad-design/scripts"))
from pcbrefstat import coarse_band, value_band  # noqa: E402

PCB = ROOT / "skills/kicad-design/scripts/pcb"
HERE = Path(__file__).resolve().parent
BOARD = ROOT / "examples/rung1-zener-a2-sonnet/board/qwiic_imu.kicad_pcb"
PLACE = Path("/tmp/spike2-place")
KRT_DIR = os.environ.get("KRT_DIR", "/tmp/pcb-ref/KiCadRoutingTools")
KRT_PY = os.environ.get("KRT_PY", os.path.join(KRT_DIR, ".venv/bin/python"))
DESIGNER_VIAS = 26
RESULTS = HERE / "placement-results.jsonl"


def sat_class(s):
    r = s["ref"].upper()
    if r.startswith("C"):
        return "bulk cap" if coarse_band("C", value_band("C", s["value"])) == "bulk" else "bypass cap"
    if r.startswith(("L", "FB")):
        return "inductor"
    if r.startswith("R"):
        return "resistor"
    return None


def cmd_priors(a):
    work = Path(a.work)
    feats = {}
    for l in open(work / "features.jsonl"):
        x = json.loads(l)
        feats[(x["key"], x["ref"])] = x["repo"]
    out = {}
    for part in ("AMS1117-3.3", "LSM6DS3"):
        seen, rows = set(), []
        for l in open(work / "board-measure.jsonl"):
            m = json.loads(l)
            if m["part"] != part or not m.get("ok"):
                continue
            repo = feats.get((m["key"], m["ref"]))
            if (repo, m["ref"]) in seen:
                continue
            seen.add((repo, m["ref"]))
            rows.append(m)
        cls_stats = defaultdict(list)
        roles = defaultdict(list)
        fallback = []
        for m in rows:
            for s in m["sats"]:
                c = sat_class(s)
                if c is None or s["back"]:
                    continue
                d = math.hypot(s["dx"], s["dy"])
                if d > 30:   # a part on the same rail at the far end of the board is not a satellite
                    continue
                cls_stats[c].append((s["dx"], s["dy"], s["rot"], d, s["pin"]))
                if s["ref"].upper().startswith("C") and s["other_gnd"]:
                    band = "bulk" if c == "bulk cap" else "bypass"
                    roles[f"{s['pin']}|C|{band}"].append((s["dx"], s["dy"], s["rot"]))
                    if s["pin"] in ("VDD", "VDDIO", "VIN", "VOUT"):
                        fallback.append((s["dx"], s["dy"], s["rot"]))
        summ = {}
        for c, xs in sorted(cls_stats.items()):
            ds = sorted(x[3] for x in xs)
            rot = Counter(round(x[2]) % 180 for x in xs)
            summ[c] = {"n": len(xs), "dist_median_mm": round(statistics.median(ds), 2), "dist_p25_mm": round(ds[len(ds) // 4], 2),
                       "dist_p75_mm": round(ds[3 * len(ds) // 4], 2), "dist_p90_mm": round(ds[int(0.9 * (len(ds) - 1))], 2),
                       "rot_share_0": round(rot.get(0, 0) / len(xs), 2), "rot_share_90": round(rot.get(90, 0) / len(xs), 2),
                       "pins": Counter(x[4] for x in xs).most_common(4)}
        out[part] = {"instances_with_board": len(rows), "classes": summ}
        json.dump({"part": part, "n_instances": len(rows), "roles": roles, "fallback": fallback, "classes": summ},
                  open(work / f"priors-{part}.json", "w"))
        print(f"{part}: {len(rows)} instances with a measured board")
        for c, v in summ.items():
            print(f"  {c:11} n {v['n']:4} distance median {v['dist_median_mm']} mm (IQR {v['dist_p25_mm']}-{v['dist_p75_mm']}, p90 {v['dist_p90_mm']})"
                  f"  rot 0: {v['rot_share_0']}, 90: {v['rot_share_90']}  pins {v['pins']}")
        print(f"  roles: " + ", ".join(f"{k} {len(v)}" for k, v in sorted(roles.items(), key=lambda kv: -len(kv[1]))[:8]))
    json.dump(out, open(HERE / "priors-summary.json", "w"), indent=1)


def base_board():
    b = PLACE / "base"
    if (b / "stripped.kicad_pcb").exists():
        return b / "stripped.kicad_pcb"
    b.mkdir(parents=True, exist_ok=True)
    shutil.copy(BOARD, b / "src.kicad_pcb")
    shutil.copy(BOARD.with_suffix(".kicad_pro"), b / "src.kicad_pro")
    subprocess.run([str(PCB), "route", "strip", str(b / "src.kicad_pcb"), "--out", str(b / "stripped.kicad_pcb")], check=True, capture_output=True)
    shutil.copy(BOARD.with_suffix(".kicad_pro"), b / "stripped.kicad_pro")
    return b / "stripped.kicad_pcb"


def one(mode, seed, priors):
    d = PLACE / f"{mode}-{seed:02d}"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    src = base_board()
    seeded = d / "seed.kicad_pcb"
    shutil.copy(src.with_suffix(".kicad_pro"), d / "seed.kicad_pro")
    t0 = time.time()
    p = subprocess.run([str(PCB), "py", str(HERE / "seed_place.py"), str(src), str(seeded), "--ic", "U1", "--part", "LSM6DS3",
                        "--move", "C1,C2,C3", "--mode", mode, "--seed", str(seed), "--priors", str(priors)],
                       capture_output=True, text=True, cwd=str(ROOT))
    line = next((l for l in p.stdout.splitlines() if l.startswith("{")), "{}")
    sd = json.loads(line)
    rec = {"mode": mode, "seed": seed, "seed_ok": sd.get("ok", False), "draws": sd.get("draws"), "moved": sd.get("moved")}
    if not sd.get("ok"):
        rec["why"] = sd.get("why") or p.stderr[-300:]
        return rec
    q = subprocess.run([KRT_PY, os.path.join(KRT_DIR, "py_router/route.py"), str(seeded), str(d / "quick.kicad_pcb"), "--json-out",
                        str(d / "quick.json"), "--no-fix-drc-settings", "--escalation", "off", "--quick", "2"],
                       capture_output=True, text=True, cwd=KRT_DIR, env={**os.environ, "PYTHONHASHSEED": "0"})
    try:
        qj = json.load(open(d / "quick.json"))
        rec["quick"] = {"failed": qj.get("failed"), "vias": qj.get("vias"), "routed": qj.get("routed")}
    except (OSError, ValueError):
        rec["quick"] = {"error": q.stderr[-200:]}
    r = subprocess.run([str(PCB), "route", "auto", str(seeded), "--out", str(d / "auto.kicad_pcb"), "--work", str(d / "autowork")],
                       capture_output=True, text=True, cwd=str(ROOT))
    try:
        rj = json.load(open(d / "route.json"))
        f = rj["final"]
        rec["auto"] = {"clean": rj["clean"], "vias": f["vias"], "airwires": f["airwires"], "length_mm": f["length_mm"],
                       "plain_errors": f["plain_errors"], "packed_errors": f["packed_errors"], "wall_s": rj["wall_s"],
                       "passes": len(rj.get("passes", []))}
    except (OSError, ValueError, KeyError):
        rec["auto"] = {"clean": False, "error": (r.stdout + r.stderr)[-300:]}
    rec["wall_s"] = round(time.time() - t0, 1)
    # keep only the record: the routed boards are large and the seed can be rebuilt from (mode, seed)
    for name in ("quick.kicad_pcb", "auto.kicad_pcb"):
        x = d / name
        if x.exists():
            x.unlink()
    return rec


def cmd_route(a):
    priors = Path(a.work) / "priors-LSM6DS3.json"
    pj = json.load(open(priors))
    if pj["n_instances"] < 30:
        print(f"LSM6DS3 instances with a board: {pj['n_instances']} (< 30): routing test skipped"); return
    base_board()
    done = set()
    if RESULTS.exists():
        for l in open(RESULTS):
            x = json.loads(l); done.add((x["mode"], x["seed"]))
    todo = [(m, s) for s in range(a.n) for m in ("prior", "uniform") if (m, s) not in done]
    with cf.ThreadPoolExecutor(a.jobs) as ex, open(RESULTS, "a") as f:
        for fu in cf.as_completed([ex.submit(one, m, s, priors) for m, s in todo]):
            rec = fu.result()
            f.write(json.dumps(rec) + "\n"); f.flush()
            au = rec.get("auto", {})
            print(f"{rec['mode']:7} {rec['seed']:2} seed {rec['seed_ok']} quick {rec.get('quick')} auto clean {au.get('clean')} vias {au.get('vias')}", flush=True)


def summarize():
    rows = [json.loads(l) for l in open(RESULTS)]
    out = {}
    for mode in ("prior", "uniform"):
        rs = [r for r in rows if r["mode"] == mode]
        ok = [r for r in rs if r["seed_ok"]]
        clean = [r for r in ok if r.get("auto", {}).get("clean")]
        vias = [r["auto"]["vias"] for r in clean]
        good = [v for v in vias if v <= DESIGNER_VIAS]
        qf = [r["quick"]["failed"] for r in ok if isinstance(r.get("quick", {}).get("failed"), int)]
        lens = [r["auto"]["length_mm"] for r in clean]
        out[mode] = {"seeds": len(rs), "seeded": len(ok), "clean": len(clean), "clean_rate": round(len(clean) / max(1, len(ok)), 3),
                     "vias_median": statistics.median(vias) if vias else None, "vias_min": min(vias) if vias else None,
                     "vias_max": max(vias) if vias else None, "at_or_below_designer": len(good),
                     "p_good": round(len(good) / max(1, len(ok)), 3),
                     "router_calls_to_designer_vias": round(len(ok) / len(good), 2) if good else None,
                     "quick_failed_median": statistics.median(qf) if qf else None,
                     "quick_zero_failed": sum(1 for x in qf if x == 0), "length_median_mm": round(statistics.median(lens), 1) if lens else None,
                     "draws_median": statistics.median([r["draws"] for r in ok]) if ok else None}
    out["designer_vias"] = DESIGNER_VIAS
    return out


def cmd_summary(a):
    s = summarize()
    json.dump(s, open(HERE / "placement-summary.json", "w"), indent=1)
    print(json.dumps(s, indent=1))


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["priors", "route", "summary"])
    ap.add_argument("--work", default="/tmp/spike2-corpus")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--jobs", type=int, default=3)
    a = ap.parse_args(argv)
    {"priors": cmd_priors, "route": cmd_route, "summary": cmd_summary}[a.mode](a)


if __name__ == "__main__":
    main(sys.argv[1:])
