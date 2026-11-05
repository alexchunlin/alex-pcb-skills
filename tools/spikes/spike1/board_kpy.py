"""Spike #1: a board's placement-independent geometry as JSON, for the pure-Python features (run with `pcb py`).

  pcb py tools/spikes/spike1/board_kpy.py BOARD.kicad_pcb OUT.json
  pcb py tools/spikes/spike1/board_kpy.py BOARD.kicad_pcb OUT.json --check-rot REF   (self-test of the rotation sign)

Per footprint: its pose as found (x, y, rot, side), the courtyard outline and every pad relative to that pose (world
minus position, in the board's frame at that rotation), so a placement (ref, x, y, rot) puts a pad at
(x, y) + R(rot - rot0) (dx, dy) with KiCad's sign (y down, positive angle counter-clockwise on screen). Per pad: number,
net, size as an axis-aligned box at rot0, through-hole flag. Zones (not rule areas): net, copper layers, outline. Plane
nets as `pcb q conflicts` defines them, the Edge.Cuts box, the net-class patterns from the .kicad_pro.
"""
import json, math, os, sys

import pcbnew  # noqa: E402
from pcbnew import ToMM, FromMM, VECTOR2I  # noqa: E402


def rel_pts(poly, ox, oy):
    pts = []
    if poly.OutlineCount():
        o = poly.Outline(0)
        for i in range(o.PointCount()):
            p = o.CPoint(i)
            pts.append([round(ToMM(p.x) - ox, 4), round(ToMM(p.y) - oy, 4)])
    return pts


def main():
    a = sys.argv[1:]
    src, dst = a[0], a[1]
    b = pcbnew.LoadBoard(src)
    if "--check-rot" in a:   # rotate one footprint by +90 and compare KiCad's pad positions with the formula
        ref = a[a.index("--check-rot") + 1]
        f = b.FindFootprintByReference(ref)
        x0, y0 = ToMM(f.GetPosition().x), ToMM(f.GetPosition().y)
        before = [(ToMM(p.GetPosition().x) - x0, ToMM(p.GetPosition().y) - y0) for p in f.Pads()]
        f.SetOrientationDegrees(f.GetOrientationDegrees() + 90)
        after = [(ToMM(p.GetPosition().x) - x0, ToMM(p.GetPosition().y) - y0) for p in f.Pads()]
        t = math.radians(90)
        pred = [(dx * math.cos(t) + dy * math.sin(t), -dx * math.sin(t) + dy * math.cos(t)) for dx, dy in before]
        err = max(abs(p[0] - q[0]) + abs(p[1] - q[1]) for p, q in zip(pred, after))
        print(json.dumps({"ref": ref, "max_err_mm": round(err, 6)}))
        return
    inner = {l for l in b.GetEnabledLayers().CuStack() if l not in (pcbnew.F_Cu, pcbnew.B_Cu)}
    planes = sorted({z.GetNetname() for z in b.Zones() if z.GetNetname() and z.IsFilled()
                     and any(z.GetFilledPolysList(l).OutlineCount() for l in z.GetLayerSet().CuStack() if l in inner)})
    fps = []
    for f in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
        x, y = ToMM(f.GetPosition().x), ToMM(f.GetPosition().y)
        side = "B" if f.GetLayer() == pcbnew.B_Cu else "F"
        cy = f.GetCourtyard(pcbnew.B_CrtYd if side == "B" else pcbnew.F_CrtYd)
        court = rel_pts(cy, x, y)
        if not court:
            bb = f.GetBoundingBox(False)
            court = [[ToMM(bb.GetX()) - x, ToMM(bb.GetY()) - y], [ToMM(bb.GetRight()) - x, ToMM(bb.GetY()) - y],
                     [ToMM(bb.GetRight()) - x, ToMM(bb.GetBottom()) - y], [ToMM(bb.GetX()) - x, ToMM(bb.GetBottom()) - y]]
        pads = []
        for p in f.Pads():
            bb = p.GetBoundingBox()
            pads.append({"num": p.GetNumber(), "net": p.GetNetname(), "dx": round(ToMM(p.GetPosition().x) - x, 4),
                         "dy": round(ToMM(p.GetPosition().y) - y, 4), "w": round(ToMM(bb.GetWidth()), 4), "h": round(ToMM(bb.GetHeight()), 4),
                         "th": p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH)})
        fps.append({"ref": f.GetReference(), "x": round(x, 4), "y": round(y, 4), "rot": round(f.GetOrientationDegrees(), 2), "side": side,
                    "locked": bool(f.IsLocked()), "value": f.GetValue(), "court": court, "pads": pads})
    zones = []
    for z in b.Zones():
        if z.GetIsRuleArea():
            continue
        layers = [b.GetLayerName(l) for l in z.GetLayerSet().CuStack()]
        zones.append({"net": z.GetNetname(), "layers": layers, "outline": rel_pts(z.Outline(), 0.0, 0.0),
                      "priority": z.GetAssignedPriority()})
    eb = b.GetBoardEdgesBoundingBox()
    pro = os.path.splitext(src)[0] + ".kicad_pro"
    ns = json.load(open(pro)).get("net_settings", {}) if os.path.exists(pro) else {}
    out = {"board": os.path.abspath(src), "edge": [ToMM(eb.GetX()), ToMM(eb.GetY()), ToMM(eb.GetRight()), ToMM(eb.GetBottom())],
           "copper_layers": [b.GetLayerName(l) for l in b.GetEnabledLayers().CuStack()], "plane_nets": planes,
           "class_patterns": [[x["pattern"], x["netclass"]] for x in ns.get("netclass_patterns", [])],
           "class_widths": {c["name"]: c.get("track_width") for c in ns.get("classes", [])},
           "footprints": fps, "zones": zones}
    json.dump(out, open(dst, "w"))
    print(json.dumps({"out": dst, "footprints": len(fps), "pads": sum(len(f["pads"]) for f in fps), "zones": len(zones), "plane_nets": planes}))


if __name__ == "__main__":
    main()
