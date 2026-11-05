"""Spike #4: one perturbed placement of a stripped board (run with `pcb py`).

  pcb py tools/spikes/spike4/perturb_kpy.py IN.kicad_pcb OUT.kicad_pcb --seed N --sigma MM
  pcb py tools/spikes/spike4/perturb_kpy.py IN.kicad_pcb OUT.kicad_pcb --apply placement.json   (spike #1: [[ref, x, y, rot]])

Every footprint that is not locked, not a connector (J*) and not a mounting hole is moved by (dx, dy) ~ N(0, sigma) mm, rotation kept, in a
seeded random order; a draw is rejected when the moved courtyard box leaves the Edge.Cuts box or overlaps a same-side
courtyard polygon by more than it did in the input (0.001 mm2 slack), up to 30 draws, else
the part stays. Then the zones are refilled. Prints one JSON line: moved count, rejected draws, the placement as
(ref, x, y, rot).
"""
import json, os, random, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "../../../skills/kicad-design/scripts"))
import pcbnew  # noqa: E402
from pcbnew import FromMM, ToMM, VECTOR2I  # noqa: E402
from pcblib.board import Board  # noqa: E402


def box(f):
    side = pcbnew.B_CrtYd if f.GetLayer() == pcbnew.B_Cu else pcbnew.F_CrtYd
    cy = f.GetCourtyard(side)
    if cy.OutlineCount():
        bb = cy.BBox()
        x0, y0, x1, y1 = ToMM(bb.GetX()), ToMM(bb.GetY()), ToMM(bb.GetRight()), ToMM(bb.GetBottom())
    else:
        bb = f.GetBoundingBox(False)
        x0, y0, x1, y1 = ToMM(bb.GetX()), ToMM(bb.GetY()), ToMM(bb.GetRight()), ToMM(bb.GetBottom())
    return (x0, y0, x1, y1, f.GetLayer() == pcbnew.B_Cu)


def overlap(a, b):
    return a[4] == b[4] and a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def poly(f):
    side = pcbnew.B_CrtYd if f.GetLayer() == pcbnew.B_Cu else pcbnew.F_CrtYd
    return pcbnew.SHAPE_POLY_SET(f.GetCourtyard(side))


def pads(f):
    """Every pad's box grown by 0.1 mm (so two pads closer than 0.2 mm touch): some vendored footprints' courtyards hug
    the body and leave the pins outside (a first version let C7 slide onto the DRV8874's pins)."""
    ps = pcbnew.SHAPE_POLY_SET()
    g = FromMM(0.1)
    for pd in f.Pads():
        bb = pd.GetBoundingBox()
        r = pcbnew.SHAPE_POLY_SET()
        r.NewOutline()
        for x, y in ((bb.GetX() - g, bb.GetY() - g), (bb.GetRight() + g, bb.GetY() - g), (bb.GetRight() + g, bb.GetBottom() + g), (bb.GetX() - g, bb.GetBottom() + g)):
            r.Append(int(x), int(y))
        ps.BooleanAdd(r)
    return ps


def poly_area(pa, pb, empty=1e9):
    """Overlap, mm2 (a footprint without a courtyard counts as overlapping; without pads, as not)."""
    if not pa.OutlineCount() or not pb.OutlineCount():
        return empty
    i = pcbnew.SHAPE_POLY_SET(pa)
    i.BooleanIntersection(pb)
    return i.Area() / 1e12


def apply(src, dst, placement):
    """Spike #1: put every listed footprint at its (x, y, rot), save, refill (a search arm's placement onto another base)."""
    bd = Board.load(src)
    pose = {r: (x, y, rot) for r, x, y, rot in json.load(open(placement))}
    n = 0
    for f in bd.b.GetFootprints():
        p = pose.get(f.GetReference())
        if p:
            f.SetPosition(VECTOR2I(FromMM(p[0]), FromMM(p[1])))
            f.SetOrientationDegrees(p[2])
            n += 1
    bd.save(dst)
    out = Board.load(dst)
    out.fill()
    print(json.dumps({"out": dst, "applied": n, "of": len(pose)}))


def main():
    a = sys.argv[1:]
    src, dst = a[0], a[1]
    if "--apply" in a:
        return apply(src, dst, a[a.index("--apply") + 1])
    seed = int(a[a.index("--seed") + 1])
    sigma = float(a[a.index("--sigma") + 1])
    bd = Board.load(src)
    b = bd.b
    eb = b.GetBoardEdgesBoundingBox()
    edge = (ToMM(eb.GetX()), ToMM(eb.GetY()), ToMM(eb.GetRight()), ToMM(eb.GetBottom()))
    fps = list(b.GetFootprints())
    polys = {f.GetReference(): poly(f) for f in fps}
    padp = {f.GetReference(): pads(f) for f in fps}
    boxes = {}
    for f in fps:   # the box covers courtyard and pads
        u = pcbnew.SHAPE_POLY_SET(polys[f.GetReference()]); u.BooleanAdd(padp[f.GetReference()])
        bb = u.BBox()
        boxes[f.GetReference()] = (ToMM(bb.GetX()), ToMM(bb.GetY()), ToMM(bb.GetRight()), ToMM(bb.GetBottom()), f.GetLayer() == pcbnew.B_Cu)
    start = dict(boxes)
    start_poly = {r: pcbnew.SHAPE_POLY_SET(p) for r, p in polys.items()}
    start_pads = {r: pcbnew.SHAPE_POLY_SET(p) for r, p in padp.items()}
    # pairs that overlap in the input may keep that overlap, never grow it (a first version let R6 slide onto U1's pins)
    base_area = {(r1, r2): poly_area(polys[r1], polys[r2]) for r1 in boxes for r2 in boxes if r1 < r2 and overlap(boxes[r1], boxes[r2])}
    base_pad = {(r1, r2): poly_area(padp[r1], padp[r2], 0.0) for r1, r2 in base_area}
    rng = random.Random(seed)
    order = sorted(fps, key=lambda f: f.GetReference())
    rng.shuffle(order)
    moved, rejected = 0, 0
    for f in order:
        ref = f.GetReference()
        if f.IsLocked() or ref.startswith(("H", "MH", "J")):   # connectors stay on their edges (spike #1 generator rule)
            continue
        pos = f.GetPosition()
        for _ in range(30):
            dx, dy = rng.gauss(0, sigma), rng.gauss(0, sigma)
            f.SetPosition(VECTOR2I(pos.x + FromMM(dx), pos.y + FromMM(dy)))
            o = start[ref]   # the courtyard cache is not rebuilt on SetPosition, so the box is the input's, translated
            bx = (o[0] + dx, o[1] + dy, o[2] + dx, o[3] + dy, o[4])
            m = 0.3   # pad boxes are grown 0.1 already: 0.4 mm copper to edge, the rung-2 setup
            inside = bx[0] >= edge[0] + m and bx[1] >= edge[1] + m and bx[2] <= edge[2] - m and bx[3] <= edge[3] - m
            pm = pcbnew.SHAPE_POLY_SET(start_poly[ref])
            pm.Move(VECTOR2I(FromMM(dx), FromMM(dy)))
            pp = pcbnew.SHAPE_POLY_SET(start_pads[ref])
            pp.Move(VECTOR2I(FromMM(dx), FromMM(dy)))
            key = lambda r: tuple(sorted((r, ref)))
            hits = [r for r, o in boxes.items() if r != ref and overlap(bx, o)
                    and (poly_area(pm, polys[r]) > base_area.get(key(r), 0.0) + 1e-3 or poly_area(pp, padp[r], 0.0) > base_pad.get(key(r), 0.0) + 1e-4)]
            if inside and not hits:
                boxes[ref], polys[ref], padp[ref] = bx, pm, pp
                moved += 1
                break
            rejected += 1
        else:
            f.SetPosition(pos)
    bd.save(dst)
    out = Board.load(dst)
    out.fill()
    pl = [[f.GetReference(), round(ToMM(f.GetPosition().x), 4), round(ToMM(f.GetPosition().y), 4), round(f.GetOrientationDegrees(), 2)]
          for f in sorted(out.b.GetFootprints(), key=lambda f: f.GetReference())]
    print(json.dumps({"out": dst, "seed": seed, "sigma": sigma, "moved": moved, "rejected_draws": rejected, "placement": pl}))


if __name__ == "__main__":
    main()
