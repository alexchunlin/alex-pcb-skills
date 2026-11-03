#!/usr/bin/env python3
"""Spike #3, C2: the pogo-pin points of a board from `pcb q`, for build_jig.py.

  python3 -I tools/spikes/spike3/jig/jig_points.py BOARD.kicad_pcb OUT.json [--probe TP1,TP2,J3] [--align H1,H2]

Probe points: every pad of the --probe references (default: every TP* footprint and every through-hole pin of a DNP
header, the points BRINGUP.md probes); alignment holes: --align (default every NPTH mounting hole). Coordinates go into
the jig's world frame: origin at the board outline's centre, X right, Y up (KiCad's Y points down), seen from above,
so a pin plate held over the face-up board has its holes straight above the pads. Plain python3, standard library.
"""
import json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PCB = str(ROOT / "skills/kicad-design/scripts/pcb")


def q(board, *a):
    p = subprocess.run([PCB, "q", board, *a, "--json"], capture_output=True, text=True)
    return json.loads(p.stdout.strip().splitlines()[-1])


def main(argv):
    board, out = argv[0], argv[1]
    opt = lambda k: argv[argv.index(k) + 1].split(",") if k in argv else None
    edge = q(board, "edge")
    cx = (edge["origin"][0] + edge["end"][0]) / 2
    cy = (edge["origin"][1] + edge["end"][1]) / 2
    fps = q(board, "fps")["footprints"] if "footprints" in q(board, "fps") else q(board, "fps")
    holes = q(board, "holes")["holes"]
    refs = opt("--probe")
    if refs is None:
        refs = sorted({f["ref"] for f in fps if f["ref"].startswith("TP")} |
                      {h["ref"] for h in holes if h["plated"] and any(f["ref"] == h["ref"] and f.get("dnp") for f in fps)})
    pins = []
    for r in refs:
        for p in q(board, "pads", r)["pads"]:
            x, y = p["pos"]
            pins.append({"ref": f"{r}.{p['pad']}", "net": p["net"], "board_xy": [x, y], "xy": [round(x - cx, 3), round(cy - y, 3)],
                         "pad_mm": p["size"], "drill_mm": p["drill"], "side": "F" if "F.Cu" in p["layers"] else "B"})
    align = [{"ref": h["ref"], "d_mm": h["drill_mm"], "xy": [round(h["pos"][0] - cx, 3), round(cy - h["pos"][1], 3)]}
             for h in holes if not h["plated"] and (opt("--align") is None or h["ref"] in opt("--align"))]
    d = {"board": board, "outline_mm": [edge["w_mm"], edge["h_mm"]], "corner_r_mm": max(edge["corner_arcs"] or [0]),
         "centre_board_xy": [cx, cy], "pins": pins, "align": align}
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(d, open(out, "w"), indent=1)
    for p in pins:
        print(f"pin {p['ref']:6} {p['net']:10} board {p['board_xy']} jig {p['xy']} side {p['side']}")
    for a in align:
        print(f"align {a['ref']} {a['d_mm']} mm at jig {a['xy']}")


if __name__ == "__main__":
    main(sys.argv[1:])
