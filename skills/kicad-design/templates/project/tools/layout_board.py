#!/usr/bin/env python3
"""Placement, routing, zones and silk as data on pcblib.board. Run after `pcb layout`:
    pcb py tools/layout_board.py layout/PROJECT/PROJECT.kicad_pcb
Everything placed here is rebuilt on every run; the netlist is owned by the .zen. Worked example (15 parts, 107 lines):
<repo>/examples/rung1-zener-a1/layout_board.py
"""
import sys
from pcblib.board import Board

X0, Y0, W, H, R = 100.0, 100.0, 25.4, 25.4, 2.0          # board frame, mm
PLACEMENT = {                                            # ref: (x, y, rotation)
    # "U1": (X0 + W / 2, Y0 + H / 2, 0),
}
KEEP_REFDES = []                                         # every part BRINGUP.md names (R1-Z1-F4)

b = Board.load(sys.argv[1])
b.setup(clearance=0.2, track=0.2, via=(0.6, 0.3), hole_clearance=0.3, edge=0.4, silk=0.15, netclass_track=0.25)
b.clear()
b.place_many(PLACEMENT)
for ref in b.fps:
    b.fields(ref, {})                                    # hide fields on F.Fab, upper-case Mpn/Lcsc for parity
b.hide_refdes(keep=KEEP_REFDES)
b.outline_rect(X0, Y0, W, H, r=R)
# b.route("GND", ["U1.6", (x, y)]); b.via(x, y, "GND")
# b.zone("GND", "In1.Cu"); b.zone("3V3", "In2.Cu"); b.zone("GND", "F.Cu"); b.zone("GND", "B.Cu")
# b.text("rev A", x, y); b.arrow((x1, y), (x2, y)); b.text("X", x3, y)
b.fill()
print("layout written:", b.summary())
