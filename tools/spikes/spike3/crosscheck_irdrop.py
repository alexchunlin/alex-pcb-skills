#!/usr/bin/env python3
"""Spike #3, C1: the repo's `pcb irdrop` against firedanceio/kicad-irdrop (b508349) on the same rails.

Six single-sink rails on the four rung-2 boards. `pcb irdrop` at 0.1 mm (its default) and 0.05 mm; kicad-irdrop at
0.05 mm (its default) with 25 um plating (ours) instead of its 20 um. Compared: drop at the sink, the hottest density and
where, wall time. kicad-irdrop runs only through its own venv (KiCad's Python 3.9 + scipy + shapely, built with
--system-site-packages so pcbnew imports), by explicit path:

  /tmp/pcb-ref/kicad-irdrop/.venv/bin/python3   (install: tools/spikes/spike3/README in the report, docs/spikes/spike-3-conventions.md)

  python3 -I tools/spikes/spike3/crosscheck_irdrop.py      -> tools/spikes/spike3/results/crosscheck.json
"""
import json, shutil, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PCB = str(ROOT / "skills/kicad-design/scripts/pcb")
KIR = Path("/tmp/pcb-ref/kicad-irdrop")
KPY = KIR / ".venv/bin/python3"
OUT = Path("/tmp/spike3/crosscheck")
RES = Path(__file__).resolve().parent / "results" / "crosscheck.json"
# (board, net, our source pads, kicad-irdrop source ref, sink pad, amps); every sink part has one pad on the net, so
# kicad-irdrop's "equal share over the load part's pads" is the same single sink
RAILS = [
    ("rung2-zener-a2-opus", "VIN", "Q1.1,Q1.2,Q1.3", "Q1", "U2.11", 2.5),
    ("rung2-zener-a2-opus", "5V", "L1.2", "L1", "J3.1", 3.0),
    ("rung2-zener-a2-opus", "MOTOR_A", "J1.1", "J1", "U2.8", 2.5),
    ("rung2-zener-a1-opus", "VIN", "Q1.1,Q1.2,Q1.3", "Q1", "U2.11", 2.5),
    ("rung2-zener-a1-sonnet", "VIN", "Q1.1,Q1.2,Q1.3", "Q1", "U2.11", 2.5),
    ("rung2-zener-a1-fable", "VIN", "Q1.1,Q1.2,Q1.3", "Q1", "U1.11", 2.5),
]
KIR_RUN = ("import sys; sys.path.insert(0, sys.argv[1]); from kicad_irdrop.cli import main; "
           "sys.argv = ['kicad-irdrop'] + sys.argv[2:]; sys.exit(main(sys.argv[1:]))")


def board_copy(name):
    corpus = json.load(open(ROOT / "tools/bench/corpus.json"))["attempts"][name]
    w = OUT / name
    if not w.exists():
        shutil.copytree(ROOT / corpus["dir"] / Path(corpus["pcb"]).parent, w / Path(corpus["pcb"]).parent)
        shutil.copy(ROOT / corpus["dir"] / "checks.json", w / "checks.json")
    return w / corpus["pcb"], w / "checks.json"


def ours(board, cfg, net, src, sink, amps, grid, tag):
    t = time.time()
    p = subprocess.run([PCB, "irdrop", str(board), "--net", net, "--source", src, "--sink", f"{sink}={amps}", "--config", str(cfg),
                        "--grid", str(grid), "--out", str(OUT / f"ours-{tag}-{grid}"), "--json"], capture_output=True, text=True)
    d = json.loads(p.stdout.strip().splitlines()[-1])
    jd = d.get("judge", {})
    nk = max(jd.get("necks", []) or [{}], key=lambda n: n.get("ratio", 0))
    return {"drop_mV": d["sinks"][0]["drop_mV"], "worst_J_outside_pads": d["max_J_A_mm2"],
            "worst_at": [d["worst"][0]["layer"], d["worst"][0]["x"], d["worst"][0]["y"]] if d["worst"] else None,
            "worst_neck": {k: nk.get(k) for k in ("layer", "x", "y", "width_mm", "I_A", "ratio", "status")},
            "worst_via_field": (jd.get("barrels") or [{}])[0], "power_mW": d["power_mW"], "wall_s": round(time.time() - t, 1)}


def theirs(board, net, src, sink, amps, tag):
    ref = sink.split(".")[0]
    js = OUT / f"kir-{tag}.json"
    t = time.time()
    p = subprocess.run([str(KPY), "-I", "-c", KIR_RUN, str(KIR / "src"), str(board), "--rail", f"{net}:{src}:{amps}:{ref}",
                        "--grid", "0.05", "--plating", "0.025", "--json", str(js)], capture_output=True, text=True)
    if not js.exists():
        return {"error": (p.stdout + p.stderr)[-400:]}
    r = json.load(open(js))["rails"][0]
    return {"drop_mV": r["worst_drop_mv"], "peak_J_incl_pads": r["peak_density_a_per_mm2"], "peak_at": r["peak_where"],
            "barrels_over_10C": r["barrels_over_rating"], "busiest_barrel": (r["busiest_barrels"] or [{}])[0],
            "unreached": r["unreached"], "wall_s": round(time.time() - t, 1), "stdout": p.stdout.strip().splitlines()[:2]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, net, src, ksrc, sink, amps in RAILS:
        board, cfg = board_copy(name)
        tag = f"{name}-{net}"
        r = {"board": name, "net": net, "sink": sink, "amps": amps,
             "ours_0.1": ours(board, cfg, net, src, sink, amps, 0.1, tag),
             "ours_0.05": ours(board, cfg, net, src, sink, amps, 0.05, tag),
             "kicad_irdrop_0.05": theirs(board, net, ksrc, sink, amps, tag)}
        k = r["kicad_irdrop_0.05"].get("drop_mV")
        if k:
            r["drop_diff_pct_0.05"] = round(100 * (r["ours_0.05"]["drop_mV"] - k) / k, 1)
            r["drop_diff_pct_0.1"] = round(100 * (r["ours_0.1"]["drop_mV"] - k) / k, 1)
        rows.append(r)
        print(f"{name:22} {net:8} {sink:6} ours 0.1 {r['ours_0.1']['drop_mV']:7} mV ({r['ours_0.1']['wall_s']} s)  ours 0.05 "
              f"{r['ours_0.05']['drop_mV']:7} mV ({r['ours_0.05']['wall_s']} s)  kicad-irdrop {k} mV ({r['kicad_irdrop_0.05'].get('wall_s')} s)  "
              f"diff {r.get('drop_diff_pct_0.05')} % / {r.get('drop_diff_pct_0.1')} %  neck 0.1 {r['ours_0.1']['worst_neck'].get('width_mm')} mm "
              f"x{r['ours_0.1']['worst_neck'].get('ratio')}, 0.05 {r['ours_0.05']['worst_neck'].get('width_mm')} mm x{r['ours_0.05']['worst_neck'].get('ratio')}")
    RES.parent.mkdir(parents=True, exist_ok=True)
    json.dump(rows, open(RES, "w"), indent=1)
    print("->", RES)


if __name__ == "__main__":
    main()
