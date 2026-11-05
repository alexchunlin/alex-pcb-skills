#!/usr/bin/env python3
"""Spike #3, item B: does ShrinathN/kicad-analysis-suite (bb52bef, GPL-3, own .kicad_pcb parser) give a number for the LDO
and the DRV8874 pad of the rung-2 attempt-2 board? Not scored: no open solver claims measurement validation (issue #3).

The suite is used as a library from its clone, by explicit path, never vendored (GPL-3):

  uv run --no-project --with numpy --with scipy --with matplotlib python3 tools/spikes/spike3/thermal_kas.py \
      /tmp/pcb-ref/kicad-analysis-suite examples/rung2-zener-a2-opus/board/motor1.kicad_pcb

Heat sources, the designer's own calcs rows: U3 AMS1117 as the suite's LDO model (5.0 V in at U3.3, 3.3 V out, 0.5 A
load at U3.2, so (5.0 - 3.3) x 0.5 = 0.85 W, p_ldo); U2 DRV8874 as the suite's linear model from VM (U2.11) to OUT1
(U2.8), GND its exposed pad (U2.17), 2 A with a 0.72 V drop = 1.44 W (p_drv_2a: 2 A, 2 x 120 mOhm, x1.5 hot), the 2 A
through the VIN and MOTOR_A copper. Ambient 40 degC (the calcs' ambient). A third argument `U3` or `U2` heats that part
alone. Output: the board temperature at each part's pads, next to the calcs rows' theta-based junction claims.
"""
import json, sys, time
from pathlib import Path


def main(suite, board_path, only="", out="/tmp/spike3/thermal"):
    sys.path.insert(0, suite)
    from pcb_current_sim import board as B, solver as S, elements as EL
    Path(out).mkdir(parents=True, exist_ok=True)
    t = time.time()
    board = B.load(board_path)
    # U2 as the suite's linear-regulator model from VM to OUT1 so that its loss (12 - 11.28) V x 2 A = 1.44 W heats its
    # pads by area (the exposed pad takes 93 %) and the 2 A runs through the real VIN and MOTOR_A copper; a plain
    # resistor element heats its two pads equally and put half the watts on the 0.4 mm VM pin (first try: 113 degC there)
    rows = [S.Row("5V_at_U3", ["U3.3"], ["U3.1"], 5.0, "V"), S.Row("3V3_load", ["U3.2"], ["U3.1"], 0.5, "load"),
            S.Row("VIN_at_Q1", ["Q1.1", "Q1.2", "Q1.3"], ["U2.17"], 12.0, "V"), S.Row("motor", ["J1.1"], ["U2.17"], 2.0, "load")]
    els = [EL.Element("U3", "U3.3", "U3.2", 0.5, model="LDO", g="U3.1", Vout=3.3, Vf=1.1, Iq=0.005),
           EL.Element("U2", "U2.11", "U2.8", 0.1, model="LDO", g="U2.17", Vout=12.0 - 1.44 / 2.0, Vf=0.1, Iq=0.0)]
    if only:
        keep = {"U3": ("5V_at_U3", "3V3_load"), "U2": ("VIN_at_Q1", "motor")}[only]
        rows = [r for r in rows if r.name in keep]
        els = [e for e in els if e.name == only]
        out = f"{out}-{only}"
        Path(out).mkdir(parents=True, exist_ok=True)
    s = S.Settings()
    s.T_amb = 40.0
    s.magnetic = False
    s.error_estimate = False
    res = S.simulate(board, rows, s, progress=lambda m: print(m, file=sys.stderr), elements=els)
    wall = time.time() - t
    txt = res.summary_text()
    (Path(out) / "summary.txt").write_text(txt)
    rep = {"wall_s": round(wall, 1), "regulators": res.regulators,
           "elements": [{k: e.get(k) for k in e if not isinstance(e.get(k), (list, dict))} for e in res.elements] if res.elements and isinstance(res.elements[0], dict) else str(res.elements)[:2000],
           "summary": res.summary if isinstance(res.summary, dict) else str(res.summary)[:2000], "warnings": res.warnings[:20]}
    # board temperature under each part's pads, from the fine temperature map
    try:
        import numpy as np
        pads = {}
        for ref in ("U3", "U2"):
            pads[ref] = res.pad_temperatures(ref) if hasattr(res, "pad_temperatures") else None
        rep["pad_T"] = pads
    except Exception as e:   # noqa: BLE001
        rep["pad_T_error"] = repr(e)
    json.dump(rep, open(Path(out) / "thermal.json", "w"), indent=1, default=str)
    print(txt)
    print(f"wall {wall:.1f} s -> {out}/thermal.json")


if __name__ == "__main__":
    main(*sys.argv[1:])
