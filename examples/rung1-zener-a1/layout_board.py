#!/usr/bin/env python3
"""The R1-Z1 designer's tools/layout_board.py (242 lines, 14 KB) rebuilt on pcblib.board: the same placement,
routes, zones and silk as data; the pcbnew boilerplate and its SWIG traps are gone. Run with
    pcb py examples/rung1-zener-a1/layout_board.py layout/qwiic_imu/qwiic_imu.kicad_pcb
after `pcb layout --no-open qwiic_imu.zen`. Produces the same copper as the original (verify_all section 17).
"""
import sys
from pcblib.board import Board

PCB = sys.argv[1]
X0, Y0, W, H, R = 100.0, 100.0, 25.4, 25.4, 2.0
CX, CY = X0 + W / 2, Y0 + H / 2
PLACEMENT = {
    "U1": (CX, CY, 0), "H1": (CX, Y0 + 2.54, 0), "H2": (CX, Y0 + 22.86, 0),
    "J1": (103.2, 109.0, 0), "J2": (122.2, 109.0, 0), "J3": (101.8, 117.9, 0),
    "C1": (116.3, 114.0, 0), "C2": (112.2, 115.9, 270), "C3": (116.3, 111.4, 0),
    "JP1": (104.2, 114.5, 0), "JP2": (120.0, 118.6, 0), "R1": (118.7, 115.6, 90), "R2": (121.3, 115.6, 90),
    "TP1": (121.6, 103.0, 0), "TP2": (118.4, 103.0, 0),
}

b = Board.load(PCB)
b.setup(clearance=0.2, track=0.2, via=(0.6, 0.3), hole_clearance=0.3, edge=0.4, silk=0.15, netclass_track=0.25)
b.clear()
b.place_many(PLACEMENT)
# Qwiic connectors: pin row 2 mm toward the board interior, opening at the edge
for ref, interior in (("J1", +1), ("J2", -1)):
    cx = PLACEMENT[ref][0]
    b.orient_pads(ref, lambda P: all(abs(P(n)[0] - (cx + 2.0 * interior)) < 0.01 for n in "1234"))
b.orient_pads("J3", lambda P: P("4")[0] > P("1")[0] + 7 and abs(P("4")[1] - P("1")[1]) < 0.01)
assert b.pad_xy("C2", "1")[1] < b.pad_xy("C2", "2")[1]
for ref in b.fps:
    b.fields(ref, {})                      # upper-case Lcsc/Mpn, hide every field on F.Fab
b.hide_refdes()
b.refdes("U1", at=(108.2, 112.0))
b.outline_rect(X0, Y0, W, H, r=R)

F, B = "F.Cu", "B.Cu"
P = b.pad_xy
U = {n: P("U1", n) for n in [str(i) for i in range(1, 15)]}
J1 = {n: P("J1", n) for n in "1234"}; J2 = {n: P("J2", n) for n in "1234"}; J3 = {n: P("J3", n) for n in "1234"}
C1 = {n: P("C1", n) for n in "12"}; C2 = {n: P("C2", n) for n in "12"}; C3 = {n: P("C3", n) for n in "12"}
R1 = {n: P("R1", n) for n in "12"}; R2 = {n: P("R2", n) for n in "12"}
JP1 = {n: P("JP1", n) for n in "123"}; JP2 = {n: P("JP2", n) for n in "123"}
TP1, TP2 = P("TP1", "1"), P("TP2", "1")
route, via = b.route, b.via
# GND
route("GND", [U["2"], (110.6, 112.7)]); route("GND", [U["3"], (110.6, 112.7)]); via(110.6, 112.7, "GND")
route("GND", [U["6"], U["7"], (113.2, 114.8)]); via(113.2, 114.8, "GND")
route("GND", [C1["2"], (C1["2"][0], 115.0)]); via(C1["2"][0], 115.0, "GND")
route("GND", [C3["2"], (C3["2"][0], 112.45)]); via(C3["2"][0], 112.45, "GND")
route("GND", [C2["2"], (112.6, 117.7)]); via(112.6, 117.7, "GND")
route("GND", [JP1["3"], (JP1["3"][0], 113.2)]); via(JP1["3"][0], 113.2, "GND")
route("GND", [TP1, (123.0, 103.0)]); via(123.0, 103.0, "GND")
route("GND", [J1["1"], (106.1, J1["1"][1])]); via(106.1, J1["1"][1], "GND")
route("GND", [J2["1"], (119.3, J2["1"][1])]); via(119.3, J2["1"][1], "GND")
# 3V3
route("3V3", [U["8"], (114.1, 113.7), (C1["1"][0] - 0.3, 113.7), C1["1"], (C1["1"][0], 115.1)]); via(C1["1"][0], 115.1, "3V3")
route("3V3", [C3["1"], (115.9, 112.4)]); via(115.9, 112.4, "3V3")
route("3V3", [U["12"], (U["12"][0], 111.0), (C3["1"][0], 111.0), C3["1"]])
route("3V3", [U["5"], C2["1"]], width=0.2)
route("3V3", [C2["1"], (111.5, C2["1"][1]), (111.0, C2["1"][1] + 0.5), (111.0, 117.1)]); via(111.0, 117.1, "3V3")
route("3V3", [JP1["1"], (JP1["1"][0], 113.2)]); via(JP1["1"][0], 113.2, "3V3")
route("3V3", [JP2["2"], (JP2["2"][0], 121.9)]); via(JP2["2"][0], 121.9, "3V3")
route("3V3", [TP2, (117.0, 103.0)]); via(117.0, 103.0, "3V3")
route("3V3", [J1["2"], (106.1, J1["2"][1])]); via(106.1, J1["2"][1], "3V3")
route("3V3", [J2["2"], (119.3, J2["2"][1])]); via(119.3, J2["2"][1], "3V3")
# I2C
ys = J1["3"][1]
route("SDA", [U["14"], (U["14"][0], ys), J1["3"]])
route("SDA", [(U["14"][0], ys), (118.3, ys), (118.3, J2["3"][1]), J2["3"]])
route("SDA", [(118.3, ys), (118.3, 114.0), (R1["2"][0], 114.4), R1["2"]])
route("SDA", [(107.9, ys), (107.9, 116.9), J3["3"]])
yc = 110.2
route("SCL", [U["13"], (U["13"][0], yc), (113.6, yc)]); via(113.6, yc, "SCL")
via(106.2, 111.4, "SCL"); via(118.6, J2["4"][1], "SCL"); via(J3["4"][0], yc, "SCL")
route("SCL", [(113.6, yc), (107.0, yc), (106.2, 111.0), (106.2, 111.4)], layer=B)
route("SCL", [(J3["4"][0], yc), J3["4"]])
route("SCL", [(113.6, yc), (117.6, yc), (117.6, J2["4"][1] + 0.5), (118.1, J2["4"][1]), (118.6, J2["4"][1])], layer=B)
route("SCL", [(106.2, 111.4), (106.2, 111.1), (105.875, J1["4"][1] + 0.3), J1["4"]])
route("SCL", [(118.6, J2["4"][1]), J2["4"], (121.075, J2["4"][1]), (121.6, J2["4"][1] + 0.5), (121.6, R2["2"][1] - 0.4), R2["2"]])
# SA0
route("SA0", [U["1"], (110.9, 111.6), (110.4, 111.6)]); via(110.4, 111.6, "SA0"); via(JP1["2"][0], 113.1, "SA0")
route("SA0", [(110.4, 111.6), (109.9, 112.1), (109.9, 112.5), (JP1["2"][0] + 0.6, 112.5), (JP1["2"][0], 113.1)], layer=B)
route("SA0", [(JP1["2"][0], 113.1), JP1["2"]])
# INT1 / INT2
route("INT1", [U["4"], (111.3, 113.7), (110.9, 114.3)]); via(110.9, 114.3, "INT1")
route("INT1", [(110.9, 114.3), (J3["1"][0], 114.3), J3["1"]], layer=B)
route("INT2", [U["9"], (114.4, 112.95), (114.75, 112.6)]); via(114.75, 112.6, "INT2")
route("INT2", [(114.75, 112.6), (114.75, 116.3), (J3["2"][0], 116.3), J3["2"]], layer=B)
route("PU_SDA", [R1["1"], JP2["1"]]); route("PU_SCL", [R2["1"], JP2["3"]])
# planes / pours
b.zone("GND", "In1.Cu"); b.zone("3V3", "In2.Cu"); b.zone("GND", F); b.zone("GND", B)
# silk
text = b.text
text("LSM6DS3TR-C", CX, 106.35); text("Qwiic", 103.3, 103.2); text("IMU", 103.3, 101.6); text("rev A", 104.9, 124.2)
b.arrow((114.2, 108.3), (116.4, 108.3)); text("X", 117.1, 108.3)
b.arrow((110.4, 110.6), (110.4, 108.4)); text("Y", 111.3, 108.7)
for n, name in zip("1234", ["INT1", "INT2", "SDA", "SCL"]):
    text(name, J3[n][0], 121.4, rot=90)
text("6B", JP1["1"][0] - 1.6, JP1["1"][1], rot=90); text("6A", JP1["3"][0] + 2.0, JP1["3"][1])
text("SA0 ADDR 6B/6A", 108.0, 115.3, layer="B.SilkS")
text("I2C PU", JP2["2"][0], 121.0)
text("SDA", R1["1"][0] + 0.4, 113.0); text("SCL", R2["1"][0] + 0.9, 113.4)
text("GND", TP1[0], 104.85); text("3V3", TP2[0], 104.85)
text("Qwiic IMU LSM6DS3TR-C", CX, 108.0, layer="B.SilkS"); text("rung1-zener-a1 rev A", CX, 112.0, layer="B.SilkS")
b.fill()
print("layout written:", b.summary())
