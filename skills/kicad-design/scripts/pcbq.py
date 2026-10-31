"""pcb q BOARD.kicad_pcb <command> [args] [--json]: one measurement over SWIG pcbnew (KiCad's bundled Python).
  fps                          every footprint: ref, value, footprint id, position, rotation, layer, DNP/BOM/POS flags
  pads REF                     pads of one footprint: number, net, position, size, drill
  dist REF.PAD REF.PAD         centre-to-centre and copper edge-to-edge distance, mm
  decoupling [IC ...]          every C* with a pad on an IC power net: distance from that pad to the nearest IC pad on
                               the same net, centre and edge, plus the GND pad's nearest via (R1-S1-F2, R1-Z1-F3)
  net NAME                     widths per layer, total length, via count, pads on the net
  nets                         every net: pads, track length, via count, min width
  vias                         via count, sizes, per net
  coverage REF [LAYER]         % of REF's courtyard box covered by filled zones, per copper layer (plane under an IC)
  zones                        zones: net, layer, filled area, min thickness, clearance
  holes                        every hole: ref, pad, PTH/NPTH, drill, position
  silk                         board text and footprint reference visibility per side (R1-Z1-F4)
  settings                     board design-settings minimums (what the plain DRC run enforces)
  edge                         board bbox from Edge.Cuts, size, corner arcs, copper layer count
  fabdata                      footprint fields (MPN/Manufacturer/LCSC/Datasheet, any case), DNP/exclusion flags,
                               origin-to-fab-outline-centre offset (feeds `pcb fab`; R1-S1-F4)
Output lines start with `PCBQ`; --json prints one JSON object instead.
Footguns handled here so callers never meet them: FindNet (not GetNetsByName), Delete (not Remove), no
GetFieldByName in 10.0.1 (R1-S1-T5, R1-Z1-T4).
"""
import json, math, sys
import pcbnew
from pcbnew import ToMM, FromMM

OUT = []
JSON = "--json" in sys.argv
if JSON:
    sys.argv.remove("--json")


def say(*a):
    OUT.append(" ".join(str(x) for x in a))


def P(v):
    return (round(ToMM(v.x), 4), round(ToMM(v.y), 4))


def fp_map(b):
    return {f.GetReference(): f for f in b.GetFootprints()}


def pad_of(fps, token):
    ref, _, num = token.partition(".")
    f = fps.get(ref)
    if f is None:
        sys.exit(f"pcbq: no footprint {ref}")
    for p in f.Pads():
        if p.GetNumber() == num:
            return p
    sys.exit(f"pcbq: {ref} has no pad {num}")


def cc(a, b):
    pa, pb = a.GetPosition(), b.GetPosition()
    return round(math.hypot(ToMM(pa.x - pb.x), ToMM(pa.y - pb.y)), 4)


def edge_dist(s1, s2, maxd=50.0):
    """Copper edge-to-edge gap between two shapes by bisection on Collide(clearance)."""
    if s1.Collide(s2, 0):
        return 0.0
    lo, hi = 0.0, maxd
    if not s1.Collide(s2, FromMM(maxd)):
        return None
    for _ in range(28):
        mid = (lo + hi) / 2
        if s1.Collide(s2, FromMM(mid)):
            hi = mid
        else:
            lo = mid
    return round(hi, 4)


def pad_edge(a, b):
    la = a.GetLayer() if a.GetLayer() in (pcbnew.F_Cu, pcbnew.B_Cu) else pcbnew.F_Cu
    return edge_dist(a.GetEffectiveShape(la), b.GetEffectiveShape(la))


def field(f, name):
    name = name.lower()
    for fl in f.GetFields():
        if fl.GetName().lower() == name:
            return fl.GetText()
    return ""


def is_power_net(name):
    n = name.upper()
    return n in ("GND", "GNDA", "GNDD", "AGND", "DGND", "PGND", "VSS") or n.startswith(("GND", "VSS"))


def fab_bbox(f, b):
    layer = pcbnew.F_Fab if f.GetLayer() == pcbnew.F_Cu else pcbnew.B_Fab
    bb = None
    for g in f.GraphicalItems():
        if g.GetLayer() == layer and g.GetClass() == "PCB_SHAPE":
            r = g.GetBoundingBox()
            if bb is None:
                bb = pcbnew.BOX2I(r.GetOrigin(), r.GetSize())   # own copy: merging into the temporary aborts (P1-T3)
            else:
                bb.Merge(r)
    return bb


# ------------------------------------------------------------------------------------------------ commands
def q_fps(b, fps, args):
    rows = []
    for r, f in sorted(fps.items()):
        at = f.GetAttributes()
        rows.append({"ref": r, "value": f.GetValue(), "fpid": f.GetFPIDAsString(), "pos": P(f.GetPosition()),
                     "rot": f.GetOrientationDegrees(), "layer": b.GetLayerName(f.GetLayer()), "dnp": f.IsDNP(),
                     "exclude_bom": bool(at & pcbnew.FP_EXCLUDE_FROM_BOM), "exclude_pos": bool(at & pcbnew.FP_EXCLUDE_FROM_POS_FILES),
                     "pads": len(list(f.Pads()))})
        say("PCBQ fp", r, f.GetValue(), f.GetFPIDAsString(), rows[-1]["pos"], rows[-1]["rot"], rows[-1]["layer"],
            "DNP" if f.IsDNP() else "", "noBOM" if rows[-1]["exclude_bom"] else "", "noPOS" if rows[-1]["exclude_pos"] else "")
    return {"footprints": rows}


def q_pads(b, fps, args):
    f = fps[args[0]]
    rows = []
    for p in f.Pads():
        d = p.GetDrillSize()
        rows.append({"pad": p.GetNumber(), "net": p.GetNetname(), "pos": P(p.GetPosition()), "size": P(p.GetSize()),
                     "drill": round(ToMM(d.x), 4) if d.x else 0, "layers": [b.GetLayerName(l) for l in p.GetLayerSet().Seq()][:4]})
        say("PCBQ pad", args[0], rows[-1]["pad"], rows[-1]["net"], rows[-1]["pos"], "size", rows[-1]["size"], "drill", rows[-1]["drill"])
    return {"ref": args[0], "pads": rows}


def q_dist(b, fps, args):
    a, c = pad_of(fps, args[0]), pad_of(fps, args[1])
    r = {"a": args[0], "b": args[1], "net_a": a.GetNetname(), "net_b": c.GetNetname(), "centre_mm": cc(a, c), "edge_mm": pad_edge(a, c)}
    say("PCBQ dist", args[0], args[1], "centre", r["centre_mm"], "edge", r["edge_mm"], "nets", r["net_a"], r["net_b"])
    return r


def q_decoupling(b, fps, args):
    ics = args or [r for r in fps if r.startswith("U")]
    vias = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
    rows = []
    for cref in sorted(r for r in fps if r.startswith("C")):
        cap = fps[cref]
        pads = list(cap.Pads())
        for cp in pads:
            net = cp.GetNetname()
            if not net or is_power_net(net):
                continue
            other = next((p for p in pads if p is not cp), None)
            for ic in ics:
                icp = [p for p in fps[ic].Pads() if p.GetNetname() == net]
                if not icp:
                    continue
                near = min(icp, key=lambda p: cc(cp, p))
                gv = [v for v in vias if other is not None and v.GetNetname() == other.GetNetname()]
                gvd = min((cc(other, v) for v in gv), default=None)
                # pcbnew has no pin types: the nearest pad on the net may be a strap (CS tied high), not the supply
                # pin, so every IC pad on the net is listed and pcbcheck's row names the pin it means
                row = {"cap": cref, "value": cap.GetValue(), "net": net, "ic": ic, "ic_pad": near.GetNumber(),
                       "centre_mm": cc(cp, near), "edge_mm": pad_edge(cp, near),
                       "ic_pads_mm": {p.GetNumber(): cc(cp, p) for p in icp},
                       "gnd_net": other.GetNetname() if other is not None else None,
                       "gnd_via_mm": round(gvd, 4) if gvd is not None else None}
                rows.append(row)
                say("PCBQ decoupling", f"{cref}({cap.GetValue()}) {net} -> {ic}.{near.GetNumber()}: centre {row['centre_mm']} edge {row['edge_mm']}",
                    f"| {row['gnd_net']} via {row['gnd_via_mm']} | all {ic} pads on {net}: {row['ic_pads_mm']}")
    if not rows:
        say("PCBQ decoupling: no capacitor shares a non-ground net with", ics)
    return {"ics": ics, "rows": rows}


def net_stats(b, name):
    widths, length, vias, layers = set(), 0.0, 0, set()
    for t in b.GetTracks():
        if t.GetNetname() != name:
            continue
        if t.GetClass() == "PCB_VIA":
            vias += 1
        else:
            widths.add(round(ToMM(t.GetWidth()), 4)); length += ToMM(t.GetLength()); layers.add(b.GetLayerName(t.GetLayer()))
    pads = [f"{f.GetReference()}.{p.GetNumber()}" for f in b.GetFootprints() for p in f.Pads() if p.GetNetname() == name]
    return {"net": name, "widths_mm": sorted(widths), "min_width_mm": min(widths) if widths else None,
            "length_mm": round(length, 3), "vias": vias, "layers": sorted(layers), "pads": pads}


def q_net(b, fps, args):
    if b.FindNet(args[0]) is None:
        sys.exit(f"pcbq: no net {args[0]}")
    r = net_stats(b, args[0])
    say("PCBQ net", r["net"], "widths", r["widths_mm"], "length", r["length_mm"], "vias", r["vias"], "layers", r["layers"], "pads", len(r["pads"]), r["pads"])
    return r


def q_nets(b, fps, args):
    names = sorted(n.GetNetname() for n in b.GetNetInfo().NetsByNetcode().values() if n.GetNetname())
    rows = [net_stats(b, n) for n in names]
    for r in rows:
        say("PCBQ net", r["net"], "pads", len(r["pads"]), "len", r["length_mm"], "vias", r["vias"], "minw", r["min_width_mm"])
    return {"nets": rows}


def q_vias(b, fps, args):
    vs = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
    sizes = sorted({(round(ToMM(v.GetWidth()), 4), round(ToMM(v.GetDrillValue()), 4)) for v in vs})
    per = {}
    for v in vs:
        per[v.GetNetname()] = per.get(v.GetNetname(), 0) + 1
    say("PCBQ vias", len(vs), "sizes(dia,drill)", sizes, "per net", per)
    return {"count": len(vs), "sizes": sizes, "per_net": per}


def q_coverage(b, fps, args):
    f = fps[args[0]]
    bb = f.GetCourtyard(pcbnew.F_CrtYd if f.GetLayer() == pcbnew.F_Cu else pcbnew.B_CrtYd).BBox()
    if bb.GetWidth() == 0:
        bb = f.GetBoundingBox(False, False)
    rect = pcbnew.SHAPE_POLY_SET(); rect.NewOutline()
    for x, y in ((bb.GetLeft(), bb.GetTop()), (bb.GetRight(), bb.GetTop()), (bb.GetRight(), bb.GetBottom()), (bb.GetLeft(), bb.GetBottom())):
        rect.Append(x, y)
    area = ToMM(bb.GetWidth()) * ToMM(bb.GetHeight())
    want = args[1] if len(args) > 1 else None
    rows = []
    for z in b.Zones():
        for L in z.GetLayerSet().Seq():
            ln = b.GetLayerName(L)
            if want and ln != want:
                continue
            poly = z.GetFilledPolysList(L)
            if poly is None or poly.OutlineCount() == 0:
                continue
            inter = pcbnew.SHAPE_POLY_SET(poly); inter.BooleanIntersection(rect)
            ia = inter.Area() / 1e12
            rows.append({"zone": z.GetZoneName(), "net": z.GetNetname(), "layer": ln, "under_mm2": round(ia, 3),
                         "pct": round(100 * ia / area, 1) if area else None, "filled": z.IsFilled()})
            say("PCBQ coverage", args[0], ln, z.GetNetname(), f"{rows[-1]['pct']}%", f"{rows[-1]['under_mm2']} of {round(area, 3)} mm2", "filled" if z.IsFilled() else "UNFILLED")
    if not rows:
        say("PCBQ coverage", args[0], "no filled zone on", want or "any layer")
    return {"ref": args[0], "box_mm2": round(area, 3), "rows": rows}


def q_zones(b, fps, args):
    rows = []
    for z in b.Zones():
        for L in z.GetLayerSet().Seq():
            poly = z.GetFilledPolysList(L)
            rows.append({"zone": z.GetZoneName(), "net": z.GetNetname(), "layer": b.GetLayerName(L), "filled": z.IsFilled(),
                         "area_mm2": round(poly.Area() / 1e12, 3) if poly else 0, "min_thickness_mm": round(ToMM(z.GetMinThickness()), 4),
                         "clearance_mm": round(ToMM(z.GetLocalClearance()), 4), "priority": z.GetAssignedPriority()})
            say("PCBQ zone", rows[-1]["zone"] or "-", rows[-1]["net"], rows[-1]["layer"], "area", rows[-1]["area_mm2"], "filled" if z.IsFilled() else "UNFILLED")
    return {"zones": rows}


def q_holes(b, fps, args):
    rows = []
    for r, f in sorted(fps.items()):
        for p in f.Pads():
            d = p.GetDrillSize()
            if d.x:
                rows.append({"ref": r, "pad": p.GetNumber(), "plated": p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH, "drill_mm": round(ToMM(d.x), 4), "pos": P(p.GetPosition())})
                say("PCBQ hole", r, p.GetNumber(), "PTH" if rows[-1]["plated"] else "NPTH", rows[-1]["drill_mm"], rows[-1]["pos"])
    vs = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
    say("PCBQ holes", len(rows), "pad holes,", len(vs), "vias")
    return {"holes": rows, "vias": len(vs)}


def q_silk(b, fps, args):
    texts = []
    for d in b.GetDrawings():
        if d.GetClass() == "PCB_TEXT" and d.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            texts.append({"layer": b.GetLayerName(d.GetLayer()), "text": d.GetText(), "pos": P(d.GetPosition()), "h_mm": round(ToMM(d.GetTextHeight()), 3), "w_mm": round(ToMM(d.GetTextThickness()), 3)})
    refs = {}
    for r, f in sorted(fps.items()):
        ref = f.Reference()
        refs[r] = {"visible": ref.IsVisible(), "layer": b.GetLayerName(ref.GetLayer()), "h_mm": round(ToMM(ref.GetTextHeight()), 3)}
    hidden = sorted(r for r, v in refs.items() if not v["visible"])
    say("PCBQ silk texts", len(texts), [t["text"] for t in texts])
    say("PCBQ silk refdes hidden", len(hidden), "of", len(refs), hidden)
    return {"texts": texts, "refdes": refs, "hidden_refdes": hidden}


def q_settings(b, fps, args):
    ds = b.GetDesignSettings()
    r = {"clearance": ds.m_MinClearance, "track_width": ds.m_TrackMinWidth, "via_diameter": ds.m_ViasMinSize,
         "through_hole": ds.m_MinThroughDrill, "hole_clearance": ds.m_HoleClearance, "copper_edge_clearance": ds.m_CopperEdgeClearance,
         "hole_to_hole": ds.m_HoleToHoleMin, "silk_clearance": ds.m_SilkClearance, "via_annular": ds.m_ViasMinAnnularWidth}
    r = {k: round(ToMM(v), 4) for k, v in r.items()}
    say("PCBQ settings", " ".join(f"{k}={v}" for k, v in r.items()))
    return r


def q_edge(b, fps, args):
    bb = b.GetBoardEdgesBoundingBox()
    arcs = [round(ToMM(d.GetRadius()), 3) for d in b.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts and d.GetShape() == pcbnew.SHAPE_T_ARC]
    r = {"origin": P(bb.GetOrigin()), "end": P(bb.GetEnd()), "w_mm": round(ToMM(bb.GetWidth()), 3), "h_mm": round(ToMM(bb.GetHeight()), 3),
         "corner_arcs": arcs, "copper_layers": b.GetCopperLayerCount(), "footprints": len(list(b.GetFootprints()))}
    say("PCBQ edge", r["w_mm"], "x", r["h_mm"], "mm at", r["origin"], "arcs", arcs, "copper layers", r["copper_layers"])
    return r


def q_fabdata(b, fps, args):
    rows = []
    for r, f in sorted(fps.items()):
        at = f.GetAttributes()
        fb = fab_bbox(f, b)
        off = None
        if fb is not None and fb.GetWidth() > 0:
            c = fb.GetCenter(); p = f.GetPosition()
            off = round(math.hypot(ToMM(c.x - p.x), ToMM(c.y - p.y)), 3)
        rows.append({"ref": r, "value": f.GetValue(), "footprint": f.GetFPIDAsString(), "layer": b.GetLayerName(f.GetLayer()),
                     "dnp": f.IsDNP(), "exclude_bom": bool(at & pcbnew.FP_EXCLUDE_FROM_BOM), "exclude_pos": bool(at & pcbnew.FP_EXCLUDE_FROM_POS_FILES),
                     "mpn": field(f, "MPN"), "manufacturer": field(f, "Manufacturer"), "lcsc": field(f, "LCSC"), "datasheet": field(f, "Datasheet"),
                     "pos": P(f.GetPosition()), "rot": f.GetOrientationDegrees(), "origin_to_fab_centre_mm": off})
        say("PCBQ fab", r, rows[-1]["value"], "LCSC", rows[-1]["lcsc"] or "-", "MPN", rows[-1]["mpn"] or "-", "DNP" if f.IsDNP() else "", "origin-offset", off)
    return {"footprints": rows}


CMDS = {k[2:]: v for k, v in globals().items() if k.startswith("q_")}


def main():
    if len(sys.argv) < 3 or sys.argv[2] not in CMDS:
        sys.exit(__doc__)
    board = pcbnew.LoadBoard(sys.argv[1])
    fps = fp_map(board)
    res = CMDS[sys.argv[2]](board, fps, sys.argv[3:])
    if JSON:
        print(json.dumps(res))
    else:
        print("\n".join(OUT))


if __name__ == "__main__":
    main()
