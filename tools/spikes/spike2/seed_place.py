"""Spike 2 placement seeds (KiCad's Python, `pcb py`): move the IC's satellites from a corpus prior or uniformly.

  pcb py tools/spikes/spike2/seed_place.py STRIPPED.kicad_pcb OUT.kicad_pcb --ic U1 --part LSM6DS3 --move C1,C2,C3
        --mode prior|uniform --seed N [--priors priors.json]

prior:   each moved part gets its role from the board (the IC pin whose net it shares, its value band), then the offset and
         relative rotation of a random corpus satellite with the same role (priors.json from placement_test.py; roles with
         fewer than 5 samples fall back to every capacitor on a power pin of the part), in the IC's own frame.
uniform: x, y uniform over the board outline's bounding box (inset 1 mm), rotation from 0/90/180/270.
Both reject a draw whose courtyard box overlaps another footprint's or leaves the outline box (up to 500 draws per part).
Prints one JSON line: {ok, draws, moved: {ref: [x, y, rot]}}.
"""
import json, math, random, sys

import pcbnew

from pcbrefstat import BY_NUMBER, coarse_band, value_band  # noqa: E402

ToMM, FromMM = pcbnew.ToMM, pcbnew.FromMM


def arg(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        return sys.argv[i + 1]
    return default


def cy_box(fp):
    for layer in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
        poly = fp.GetCourtyard(layer)
        if poly.OutlineCount():
            b = poly.BBox()
            return (ToMM(b.GetLeft()), ToMM(b.GetTop()), ToMM(b.GetRight()), ToMM(b.GetBottom()))
    b = fp.GetBoundingBox(False)
    return (ToMM(b.GetLeft()), ToMM(b.GetTop()), ToMM(b.GetRight()), ToMM(b.GetBottom()))


def overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def main():
    src, out = sys.argv[1], sys.argv[2]
    ic_ref, part, mode = arg("--ic"), arg("--part"), arg("--mode")
    move = arg("--move").split(",")
    rng = random.Random(int(arg("--seed", "0")) * 7919 + (0 if mode == "prior" else 1))
    b = pcbnew.LoadBoard(src)
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    ic = fps[ic_ref]
    edge = b.GetBoardEdgesBoundingBox()
    ex = (ToMM(edge.GetLeft()) + 1, ToMM(edge.GetTop()) + 1, ToMM(edge.GetRight()) - 1, ToMM(edge.GetBottom()) - 1)
    priors = json.load(open(arg("--priors"))) if mode == "prior" else None
    num_cpin = BY_NUMBER.get(part, {})
    ic_nets = {p.GetNetname(): num_cpin.get(p.GetNumber(), "#" + p.GetNumber()) for p in ic.Pads()}
    th = math.radians(ic.GetOrientationDegrees())
    icx, icy = ToMM(ic.GetPosition().x), ToMM(ic.GetPosition().y)
    fixed = [cy_box(f) for r, f in fps.items() if r not in move]
    placed, draws = {}, 0
    for ref in move:
        f = fps[ref]
        nets = [p.GetNetname() for p in f.Pads()]
        pin = next((ic_nets[n] for n in nets if n in ic_nets and not n.upper().startswith("GND")), None)
        band = coarse_band("C", value_band("C", f.GetValue())) if ref.startswith("C") else "-"
        pool = None
        if priors is not None:
            pool = priors["roles"].get(f"{pin}|C|{band}") or []
            if len(pool) < 5:
                pool = priors["fallback"]
        for k in range(500):
            draws += 1
            if mode == "prior":
                dx, dy, rot = rng.choice(pool)
                # the IC frame back to the board: rotate by the IC's orientation (y down, positive counter-clockwise)
                x = icx + dx * math.cos(th) + dy * math.sin(th)
                y = icy - dx * math.sin(th) + dy * math.cos(th)
                ang = ic.GetOrientationDegrees() + rot
            else:
                x, y = rng.uniform(ex[0], ex[2]), rng.uniform(ex[1], ex[3])
                ang = rng.choice([0, 90, 180, 270])
            f.SetPosition(pcbnew.VECTOR2I(FromMM(x), FromMM(y)))
            f.SetOrientationDegrees(ang)
            bx = cy_box(f)
            if bx[0] < ex[0] - 1 or bx[1] < ex[1] - 1 or bx[2] > ex[2] + 1 or bx[3] > ex[3] + 1:
                continue
            if any(overlap(bx, o) for o in fixed):
                continue
            fixed.append(bx)
            placed[ref] = [round(x, 3), round(y, 3), ang]
            break
        else:
            print(json.dumps({"ok": False, "draws": draws, "why": f"{ref}: no legal draw in 500"}))
            return
    b.Save(out)
    print(json.dumps({"ok": True, "draws": draws, "moved": placed}))


if __name__ == "__main__":
    main()
