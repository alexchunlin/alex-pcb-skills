#!/usr/bin/env python3
"""Deterministic placement + routing + planes + silkscreen for layout/qwiic_imu/qwiic_imu.kicad_pcb.

Run with KiCad's bundled python (it has pcbnew) after `pcb layout --no-open qwiic_imu.zen`:
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 tools/layout_board.py

Everything this script places is rebuilt on every run (all board-level drawings, zones, tracks and vias are
deleted first; footprints are moved to PLACEMENT), so after Zener regenerates the .kicad_pcb one run restores
exactly this layout. The netlist is owned by qwiic_imu.zen: the script never assigns nets to pads, it only draws
copper between pads that already carry them, and KiCad DRC (connectivity + schematic parity) is the check.
"""
import math, os
import pcbnew
from pcbnew import VECTOR2I, FromMM, ToMM

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "..", "layout", "qwiic_imu", "qwiic_imu.kicad_pcb")

# Board frame: 25.4 x 25.4 mm, top-left corner at (X0, Y0), corner radius R
X0, Y0, W, H, R = 100.0, 100.0, 25.4, 25.4, 2.0
CX, CY = X0 + W / 2, Y0 + H / 2            # 112.7, 112.7

TRACK = 0.25        # default track width (design-margin policy: >= 0.2 mm everywhere)
VIA_D, VIA_H = 0.6, 0.3

# ref: (x, y, rotation). J1/J2/J3 rotations are resolved below from pad geometry.
PLACEMENT = {
    "U1":  (CX, CY, 0),            # sensor at the board centre, pin 1 top-left: +X right, +Y up (datasheet Fig. 1)
    "H1":  (CX, Y0 + 2.54, 0),     # mounting holes on the vertical centre line, 20.32 mm (0.8 in) apart
    "H2":  (CX, Y0 + 22.86, 0),
    "J1":  (103.2, 109.0, 0),      # Qwiic, left edge, opening toward -X (retention tabs 0.43 mm from the edge)
    "J2":  (122.2, 109.0, 0),      # Qwiic, right edge, opening toward +X
    "J3":  (101.8, 117.9, 0),      # 0.1 in header, pin 1 at the left, runs along +X (DNP)
    "C1":  (116.3, 114.0, 0),      # 100 nF at VDD (pin 8): pad centre 1.75 mm from the pin
    "C2":  (112.2, 115.9, 270),    # 100 nF at VDDIO (pin 5): pad centre 1.5 mm from the pin
    "C3":  (116.3, 111.4, 0),      # 10 uF bulk at VDD
    "JP1": (104.2, 114.5, 0),      # SA0 address jumper: pad1 3V3 (0x6B, bridged), pad2 SA0, pad3 GND (0x6A)
    "JP2": (120.0, 118.6, 0),      # pull-up jumper: pad1 PU_SDA, pad2 3V3, pad3 PU_SCL (both bridged)
    "R1":  (118.7, 115.6, 90),     # SDA pull-up 2.2k
    "R2":  (121.3, 115.6, 90),     # SCL pull-up 2.2k
    "TP1": (121.6, 103.0, 0),      # GND test point
    "TP2": (118.4, 103.0, 0),      # 3V3 test point
}
SHOW_REF = {"U1": (108.2, 112.0, 0)}   # every other reference designator is hidden; function labels carry the silk

board = pcbnew.LoadBoard(PCB)

def mm(x, y):
    return VECTOR2I(FromMM(x), FromMM(y))

def net(name):
    n = board.FindNet(name)   # (GetNetsByName() returns an unmanaged map that breaks the SWIG runtime afterwards)
    if n is None:
        raise SystemExit("no net " + name)
    return n

# ------------------------------------------------------------------ clean slate (Delete, not Remove: Remove leaks the
# item back to Python without type info and poisons the SWIG runtime)
for t in [t for t in board.Tracks()]:
    board.Delete(t)
for z in [z for z in board.Zones()]:
    board.Delete(z)
for d in [d for d in board.GetDrawings()]:
    board.Delete(d)

# ------------------------------------------------------------------ placement
fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
for ref, (x, y, rot) in PLACEMENT.items():
    fps[ref].SetOrientationDegrees(rot)
    fps[ref].SetPosition(mm(x, y))

def pad(ref, num):
    for p in fps[ref].Pads():
        if p.GetNumber() == num:
            return p
    raise KeyError((ref, num))

def pxy(ref, num):
    p = pad(ref, num).GetPosition()
    return round(ToMM(p.x), 3), round(ToMM(p.y), 3)

# Qwiic connectors: the JST SH horizontal footprint has its pin row at local y=-2 and the cable opening at local +y.
# Choose the rotation that puts the pin row 2 mm toward the board interior (opening at the edge).
for ref, interior in (("J1", +1), ("J2", -1)):
    cx = PLACEMENT[ref][0]
    for rot in (0, 90, 180, 270):
        fps[ref].SetOrientationDegrees(rot)
        if all(abs(pxy(ref, n)[0] - (cx + 2.0 * interior)) < 0.01 for n in "1234"):
            break
    else:
        raise SystemExit(ref + ": no rotation satisfies the orientation rule")
# Header: pin 1 at PLACEMENT, pins 2..4 along +X
for rot in (0, 90, 180, 270):
    fps["J3"].SetOrientationDegrees(rot)
    fps["J3"].SetPosition(mm(*PLACEMENT["J3"][:2]))
    (x1, y1), (x4, y4) = pxy("J3", "1"), pxy("J3", "4")
    if x4 > x1 + 7 and abs(y4 - y1) < 0.01:
        break
assert pxy("C2", "1")[1] < pxy("C2", "2")[1], "C2 pad1 (3V3) must face pin 5"
assert pxy("R1", "1")[1] > pxy("R1", "2")[1] and pxy("R2", "1")[1] > pxy("R2", "2")[1], "R pad1 must face JP2"

for ref, fp in fps.items():
    # Zener writes the LCSC number as a footprint field named "Lcsc"; KiCad's schematic-parity check wants the
    # footprint field name to match the symbol field ("LCSC"), so rename it here (idempotent).
    for f in fp.GetFields():
        if f.GetName() in ("Lcsc", "Mpn"):
            f.SetName(f.GetName().upper())
    r = fp.Reference()
    if ref in SHOW_REF:
        x, y, rot = SHOW_REF[ref]
        r.SetVisible(True); r.SetPosition(mm(x, y)); r.SetTextAngleDegrees(rot)
        r.SetTextSize(VECTOR2I(FromMM(1.0), FromMM(1.0))); r.SetTextThickness(FromMM(0.15))
    else:
        r.SetVisible(False)
    fp.Value().SetVisible(False)

# ------------------------------------------------------------------ outline: rounded rectangle on Edge.Cuts
def add_seg(a, b, layer=pcbnew.Edge_Cuts, width=0.1):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(mm(*a)); s.SetEnd(mm(*b))
    s.SetLayer(layer); s.SetWidth(FromMM(width))
    board.Add(s); return s

def add_arc(start, mid, end, layer=pcbnew.Edge_Cuts, width=0.1):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_ARC)
    s.SetArcGeometry(mm(*start), mm(*mid), mm(*end))
    s.SetLayer(layer); s.SetWidth(FromMM(width))
    board.Add(s); return s

k = R * (1 - math.sqrt(0.5))
x1, y1, x2, y2 = X0, Y0, X0 + W, Y0 + H
add_seg((x1 + R, y1), (x2 - R, y1)); add_seg((x2, y1 + R), (x2, y2 - R))
add_seg((x2 - R, y2), (x1 + R, y2)); add_seg((x1, y2 - R), (x1, y1 + R))
add_arc((x2 - R, y1), (x2 - k, y1 + k), (x2, y1 + R)); add_arc((x2, y2 - R), (x2 - k, y2 - k), (x2 - R, y2))
add_arc((x1 + R, y2), (x1 + k, y2 - k), (x1, y2 - R)); add_arc((x1, y1 + R), (x1 + k, y1 + k), (x1 + R, y1))

# ------------------------------------------------------------------ copper helpers
F, B = pcbnew.F_Cu, pcbnew.B_Cu
vias = []

def via(x, y, netname):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(mm(x, y))
    v.SetDrill(FromMM(VIA_H)); v.SetWidth(FromMM(VIA_D))
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(F, B)
    v.SetNet(net(netname))
    board.Add(v); vias.append((x, y, netname)); return v

def route(netname, pts, layer=F, width=TRACK):
    for a, b in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(mm(*a)); t.SetEnd(mm(*b))
        t.SetWidth(FromMM(width)); t.SetLayer(layer)
        t.SetNet(net(netname))
        board.Add(t)

P = pxy
U = {n: P("U1", n) for n in [str(i) for i in range(1, 15)]}
J1 = {n: P("J1", n) for n in "1234"}; J2 = {n: P("J2", n) for n in "1234"}; J3 = {n: P("J3", n) for n in "1234"}
C1 = {n: P("C1", n) for n in "12"}; C2 = {n: P("C2", n) for n in "12"}; C3 = {n: P("C3", n) for n in "12"}
R1 = {n: P("R1", n) for n in "12"}; R2 = {n: P("R2", n) for n in "12"}
JP1 = {n: P("JP1", n) for n in "123"}; JP2 = {n: P("JP2", n) for n in "123"}
TP1, TP2 = P("TP1", "1"), P("TP2", "1")
# geometry the routing below relies on
assert abs(J1["3"][1] - 109.5) < 0.01 and J1["4"][1] > J1["3"][1], J1       # J1: pin 1 top ... pin 4 bottom
assert abs(J2["3"][1] - 108.5) < 0.01 and J2["4"][1] < J2["3"][1], J2       # J2: pin 4 top ... pin 1 bottom

# ================================================================== GND (plane In1.Cu + outer pours)
route("GND", [U["2"], (110.6, 112.7)]); route("GND", [U["3"], (110.6, 112.7)]); via(110.6, 112.7, "GND")   # SDx, SCx
route("GND", [U["6"], U["7"], (113.2, 114.8)]); via(113.2, 114.8, "GND")                                    # pins 6,7
route("GND", [C1["2"], (C1["2"][0], 115.0)]); via(C1["2"][0], 115.0, "GND")
route("GND", [C3["2"], (C3["2"][0], 112.45)]); via(C3["2"][0], 112.45, "GND")
route("GND", [C2["2"], (112.6, 117.7)]); via(112.6, 117.7, "GND")
route("GND", [JP1["3"], (JP1["3"][0], 113.2)]); via(JP1["3"][0], 113.2, "GND")
route("GND", [TP1, (123.0, 103.0)]); via(123.0, 103.0, "GND")
route("GND", [J1["1"], (106.1, J1["1"][1])]); via(106.1, J1["1"][1], "GND")
route("GND", [J2["1"], (119.3, J2["1"][1])]); via(119.3, J2["1"][1], "GND")

# ================================================================== 3V3 (plane In2.Cu)
route("3V3", [U["8"], (114.1, 113.7), (C1["1"][0] - 0.3, 113.7), C1["1"], (C1["1"][0], 115.1)]); via(C1["1"][0], 115.1, "3V3")   # VDD <- C1 (100 nF)
route("3V3", [C3["1"], (115.9, 112.4)]); via(115.9, 112.4, "3V3")                  # C3 (10 uF) to the plane
route("3V3", [U["12"], (U["12"][0], 111.0), (C3["1"][0], 111.0), C3["1"]])         # CS tied high (I2C mode)
route("3V3", [U["5"], C2["1"]], width=0.2)                                         # VDDIO <- C2 (100 nF)
route("3V3", [C2["1"], (111.5, C2["1"][1]), (111.0, C2["1"][1] + 0.5), (111.0, 117.1)]); via(111.0, 117.1, "3V3")
route("3V3", [JP1["1"], (JP1["1"][0], 113.2)]); via(JP1["1"][0], 113.2, "3V3")
route("3V3", [JP2["2"], (JP2["2"][0], 121.9)]); via(JP2["2"][0], 121.9, "3V3")
route("3V3", [TP2, (117.0, 103.0)]); via(117.0, 103.0, "3V3")
route("3V3", [J1["2"], (106.1, J1["2"][1])]); via(106.1, J1["2"][1], "3V3")
route("3V3", [J2["2"], (119.3, J2["2"][1])]); via(119.3, J2["2"][1], "3V3")

# ================================================================== I2C
# SDA: U1 pin 14 up to the y=109.5 bus; left straight into J1 pin 3 (same row); right to x=118.3, then up to
# J2 pin 3 (y=108.5) and down to R1. The header's SDA pin is fed from J1 pin 3 on B.Cu.
ys = J1["3"][1]
route("SDA", [U["14"], (U["14"][0], ys), J1["3"]])
route("SDA", [(U["14"][0], ys), (118.3, ys), (118.3, J2["3"][1]), J2["3"]])
route("SDA", [(118.3, ys), (118.3, 114.0), (R1["2"][0], 114.4), R1["2"]])
route("SDA", [(107.9, ys), (107.9, 116.9), J3["3"]])                                   # header SDA
# SCL: U1 pin 13 up to y=110.2; via to B.Cu, which runs left to J1 pin 4 and right/up to J2 pin 4 (top row);
# R2 hangs off J2 pin 4 along the board's right side; the header's SCL pin is fed from J1 pin 4 on B.Cu.
yc = 110.2
route("SCL", [U["13"], (U["13"][0], yc), (113.6, yc)]); via(113.6, yc, "SCL")
via(106.2, 111.4, "SCL"); via(118.6, J2["4"][1], "SCL"); via(J3["4"][0], yc, "SCL")
route("SCL", [(113.6, yc), (107.0, yc), (106.2, 111.0), (106.2, 111.4)], layer=B)
route("SCL", [(J3["4"][0], yc), J3["4"]])                                                # header SCL
route("SCL", [(113.6, yc), (117.6, yc), (117.6, J2["4"][1] + 0.5), (118.1, J2["4"][1]), (118.6, J2["4"][1])], layer=B)
route("SCL", [(106.2, 111.4), (106.2, 111.1), (105.875, J1["4"][1] + 0.3), J1["4"]])
route("SCL", [(118.6, J2["4"][1]), J2["4"], (121.075, J2["4"][1]), (121.6, J2["4"][1] + 0.5), (121.6, R2["2"][1] - 0.4), R2["2"]])

# SA0: U1 pin 1 to JP1 centre pad, routed below the J1 body
route("SA0", [U["1"], (110.9, 111.6), (110.4, 111.6)]); via(110.4, 111.6, "SA0"); via(JP1["2"][0], 113.1, "SA0")
route("SA0", [(110.4, 111.6), (109.9, 112.1), (109.9, 112.5), (JP1["2"][0] + 0.6, 112.5), (JP1["2"][0], 113.1)], layer=B)
route("SA0", [(JP1["2"][0], 113.1), JP1["2"]])

# INT1 / INT2 to the header on B.Cu
route("INT1", [U["4"], (111.3, 113.7), (110.9, 114.3)]); via(110.9, 114.3, "INT1")
route("INT1", [(110.9, 114.3), (J3["1"][0], 114.3), J3["1"]], layer=B)
route("INT2", [U["9"], (114.4, 112.95), (114.75, 112.6)]); via(114.75, 112.6, "INT2")
route("INT2", [(114.75, 112.6), (114.75, 116.3), (J3["2"][0], 116.3), J3["2"]], layer=B)

# pull-up tops to the jumper
route("PU_SDA", [R1["1"], JP2["1"]]); route("PU_SCL", [R2["1"], JP2["3"]])

# ================================================================== planes / pours
def zone(netname, layer, clearance=0.25, minw=0.25):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer); z.SetNet(net(netname))
    z.SetLocalClearance(FromMM(clearance)); z.SetMinThickness(FromMM(minw))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(FromMM(0.3)); z.SetThermalReliefSpokeWidth(FromMM(0.3))
    z.SetZoneName(f"{netname}_{board.GetLayerName(layer)}")
    o = z.Outline(); o.NewOutline()
    e = 0.5   # pour outline inset from the board edge (fab wants >= 0.371 mm copper-to-edge)
    for (x, y) in [(X0 + e, Y0 + e), (X0 + W - e, Y0 + e), (X0 + W - e, Y0 + H - e), (X0 + e, Y0 + H - e)]:
        o.Append(FromMM(x), FromMM(y))
    board.Add(z); return z

zone("GND", pcbnew.In1_Cu)      # layer 2: solid GND under the top-side signals
zone("3V3", pcbnew.In2_Cu)      # layer 3: 3V3 pour
zone("GND", F); zone("GND", B)  # outer-layer GND fills (also tie the Qwiic retention tabs)
pcbnew.ZONE_FILLER(board).Fill(board.Zones())

# ================================================================== silkscreen
def text(s, x, y, layer=pcbnew.F_SilkS, size=1.0, thick=0.15, rot=0, mirror=False):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s); t.SetPosition(mm(x, y)); t.SetLayer(layer)
    t.SetTextSize(VECTOR2I(FromMM(size), FromMM(size))); t.SetTextThickness(FromMM(thick))
    t.SetTextAngleDegrees(rot)
    if mirror:
        t.SetMirrored(True)
    board.Add(t); return t

def arrow(a, b, layer=pcbnew.F_SilkS, w=0.15, head=0.5):
    add_seg(a, b, layer, w)
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    for s in (+1, -1):
        add_seg(b, (b[0] - head * math.cos(ang + s * 0.5), b[1] - head * math.sin(ang + s * 0.5)), layer, w)

text("LSM6DS3TR-C", CX, 106.35)
text("Qwiic", 103.3, 103.2)
text("IMU", 103.3, 101.6)
text("rev A", 104.9, 124.2)
# datasheet axes (Fig. 1): with pin 1 at the top-left, +X is to the right and +Y is up
arrow((114.2, 108.3), (116.4, 108.3)); text("X", 117.1, 108.3)
arrow((110.4, 110.6), (110.4, 108.4)); text("Y", 111.3, 108.7)
for n, name in zip("1234", ["INT1", "INT2", "SDA", "SCL"]):        # header pin names, vertical under each pin
    text(name, J3[n][0], 121.4, rot=90)
text("6B", JP1["1"][0] - 1.6, JP1["1"][1], rot=90); text("6A", JP1["3"][0] + 2.0, JP1["3"][1])   # SA0 jumper: bridged side = 0x6B
text("SA0 ADDR 6B/6A", 108.0, 115.3, layer=pcbnew.B_SilkS, mirror=True)
text("I2C PU", JP2["2"][0], 121.0)
text("SDA", R1["1"][0] + 0.4, 113.0); text("SCL", R2["1"][0] + 0.9, 113.4)
text("GND", TP1[0], 104.85); text("3V3", TP2[0], 104.85)
text("Qwiic IMU LSM6DS3TR-C", CX, 108.0, layer=pcbnew.B_SilkS, mirror=True)
text("rung1-zener-a1 rev A", CX, 112.0, layer=pcbnew.B_SilkS, mirror=True)

board.Save(PCB)
print("layout written:", len(vias), "vias")
