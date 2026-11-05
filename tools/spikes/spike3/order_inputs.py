"""Spike #3, C2: the quote inputs of a board for docs/spikes/ORDER.md (KiCad's Python: `pcb py` this file BOARD CACHE N...).

Per board: outline, copper layers, thickness, smallest track / via / drill / clearance on the copper, SMD and
through-hole joints of the BOM parts, BOM lines and parts, extended types, and an assembled-cost estimate at each N
from JLC's published Economic PCBA fees (https://jlcpcb.com/help/article/pcb-assembly-price, read 2026-11-03: setup
$8.18, stencil $1.53, $0.0016 a SMD joint, $3.07 a extended type, hand solder $3.58 an order + $0.0164 a joint) and the
cached unit prices. Bare-board price is not published as a number (JLC's quote page is JS), so it is an input left blank.
"""
import json, sys
import pcbnew
import pcbq

FEE = {"setup": 8.18, "stencil": 1.53, "joint": 0.0016, "extended": 3.07, "hand_order": 3.58, "hand_joint": 0.0164}


def main(board, cache, *ns):
    b = pcbnew.LoadBoard(board)
    c = json.load(open(cache))
    M = pcbnew.ToMM
    ds = b.GetDesignSettings()
    tracks = [t for t in b.GetTracks() if t.GetClass() != "PCB_VIA"]
    vias = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
    smd = tht = 0
    lines = {}
    for f in b.GetFootprints():
        if f.IsDNP() or (f.GetAttributes() & pcbnew.FP_EXCLUDE_FROM_BOM):
            continue
        code = pcbq.field(f, "LCSC").strip()
        lines.setdefault(code, []).append(f.GetReference())
        for p in f.Pads():
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
                smd += 1
            elif p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                tht += 1
    ext = [k for k in lines if c["parts"].get(k, {}).get("library") == "extended" and not c["parts"][k].get("preferred")]
    unit = sum(len(r) * (c["parts"].get(k, {}).get("price_1") or 0) for k, r in lines.items())
    stock = min(((c["parts"].get(k, {}).get("stock") or 0), k) for k in lines)
    bb = b.GetBoardEdgesBoundingBox()
    out = {"board": board, "w_mm": round(M(bb.GetWidth()), 2), "h_mm": round(M(bb.GetHeight()), 2),
           "copper_layers": b.GetCopperLayerCount(), "thickness_mm": round(M(ds.GetBoardThickness()), 2),
           "min_track_mm": round(min(M(t.GetWidth()) for t in tracks), 3) if tracks else None,
           "min_via_mm": round(min(M(v.GetWidth(pcbnew.F_Cu)) for v in vias), 3) if vias else None,
           "min_via_drill_mm": round(min(M(v.GetDrillValue()) for v in vias), 3) if vias else None,
           "setup_clearance_mm": round(M(ds.m_MinClearance), 3), "vias": len(vias),
           "bom_lines": len(lines), "parts": sum(len(r) for r in lines.values()), "smd_joints": smd, "tht_joints": tht,
           "extended_types": len(ext), "parts_per_board_usd": round(unit, 2), "thinnest_stock": {"lcsc": stock[1], "stock": stock[0]},
           "cache_fetched": c.get("fetched"), "estimate": {}}
    for n in map(int, ns):
        fixed = FEE["setup"] + FEE["stencil"] + FEE["extended"] * len(ext) + (FEE["hand_order"] if tht else 0)
        per = smd * FEE["joint"] + tht * FEE["hand_joint"] + unit
        out["estimate"][n] = {"assembly_fixed_usd": round(fixed, 2), "per_board_usd": round(per, 2),
                              "assembly_and_parts_usd": round(fixed + n * per, 2), "bare_boards_usd": None, "shipping_usd": None}
    print(json.dumps(out))


if __name__ == "__main__":
    main(*sys.argv[1:])
