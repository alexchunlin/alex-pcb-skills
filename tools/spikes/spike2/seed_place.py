"""Spike 2 placement seeds (KiCad's Python, `pcb py`): move the IC's satellites from a corpus prior or uniformly.

  pcb py tools/spikes/spike2/seed_place.py STRIPPED.kicad_pcb OUT.kicad_pcb --ic U1 --part LSM6DS3 --move C1,C2,C3
        --mode prior|uniform|class|perturb|gate --seed N [--priors priors.json] [--pool pool.json] [--sigma MM] [--dry]

prior:   each moved part gets its role from the board (the IC pin whose net it shares, its value band), then the offset and
         relative rotation of a random corpus satellite with the same role (priors.json from placement_test.py; roles with
         fewer than 5 samples fall back to every capacitor on a power pin of the part), in the IC's own frame.
uniform: x, y uniform over the board outline's bounding box (inset 1 mm), rotation from 0/90/180/270.
class:   spike 5. pool.json holds, per moved ref, its target pad and samples [du, dv, ang, repo], the satellite's centre
         in the frame of the IC pin that serves it (u = out of the package at that pin, v = u turned a quarter, so the
         sample carries across packages and pinouts) and the direction of its pin-side pad, in degrees from u. One draw: a
         level by the pool's mixture weights, a repo uniformly in the level, a row uniformly in the repo.
perturb: spike 5. The designer's x, y plus N(0, sigma) per axis, the rotation kept.
gate:    spike 5, no draw: report whether a placed board's moved parts pass this same courtyard-box gate (the KRT arms).
--dry prints the poses and writes no board (the templates arm feeds them to KRT). --nogate keeps the first draw, legal or not.
--keep-stuck leaves a part with no legal draw at the designer's pose instead of rejecting the seed.
All reject a draw whose courtyard box overlaps another footprint's or leaves the outline box (up to 500 draws per part).
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


def pad_of(fp, num):
    return next(p for p in fp.Pads() if p.GetNumber() == str(num))


def pin_axes(ic, pad):
    """The unit outward normal at an IC pad on the board, and the tangent: the pad's long side when it has one (edge pads run
    out of the package), else the nearest side of the pad extent. The same rule as boardmeasure.pin_frame."""
    b = pad.GetBoundingBox()
    w, h = ToMM(b.GetWidth()), ToMM(b.GetHeight())
    c = (ToMM(pad.GetPosition().x), ToMM(pad.GetPosition().y))
    xs = [ToMM(p.GetPosition().x) for p in ic.Pads()]
    ys = [ToMM(p.GetPosition().y) for p in ic.Pads()]
    mid = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
    dx, dy = c[0] - mid[0], c[1] - mid[1]
    ex, ey = (max(xs) - min(xs)) / 2, (max(ys) - min(ys)) / 2
    if w > h * 1.15:
        u = (1 if dx > 0 else -1, 0)
    elif h > w * 1.15:
        u = (0, 1 if dy > 0 else -1)
    elif ex - abs(dx) <= ey - abs(dy):
        u = (1 if dx > 0 else -1, 0)
    else:
        u = (0, 1 if dy > 0 else -1)
    return u, (-u[1], u[0])


def turned(fp, pin_pad, other_pad, want):
    """The orientation, degrees, that points the part's other-pad -> pin-pad vector along `want` on the board."""
    fp.SetOrientationDegrees(0)
    a, b = pad_of(fp, pin_pad).GetPosition(), pad_of(fp, other_pad).GetPosition()
    th0 = math.degrees(math.atan2(ToMM(a.y - b.y), ToMM(a.x - b.x)))
    tw = math.degrees(math.atan2(want[1], want[0]))
    # KiCad's positive orientation turns the part counter-clockwise on a y-down board, so a vector's atan2 angle falls by it
    return round((th0 - tw) % 360, 1)


def draw_class(rng, spec, ic, fp):
    lv = spec["levels"]
    lk = rng.choices([x["level"] for x in lv], [x["weight"] for x in lv])[0]
    rows = next(x["rows"] for x in lv if x["level"] == lk)
    repo = rng.choice(sorted({r[3] for r in rows}))
    du, dv, ang, _ = rng.choice([r for r in rows if r[3] == repo])
    u, v = pin_axes(ic, pad_of(ic, spec["pin"]))
    p = pad_of(ic, spec["pin"]).GetPosition()
    x = ToMM(p.x) + du * u[0] + dv * v[0]
    y = ToMM(p.y) + du * u[1] + dv * v[1]
    t = math.radians(ang)
    want = (math.cos(t) * u[0] + math.sin(t) * v[0], math.cos(t) * u[1] + math.sin(t) * v[1])
    return x, y, turned(fp, spec["sat_pin_pad"], spec["sat_other_pad"], want), lk


def main():
    src, out = sys.argv[1], sys.argv[2]
    ic_ref, part, mode = arg("--ic"), arg("--part"), arg("--mode")
    move = arg("--move").split(",")
    rng = random.Random(int(arg("--seed", "0")) * 7919 + {"prior": 0, "uniform": 1, "class": 2, "perturb": 3, "gate": 4}[mode])
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
    if mode == "gate":   # the seed is already placed: the same box test, moved parts against everything else and each other
        boxes = {r: cy_box(fps[r]) for r in move}
        bad = [r for r in move if boxes[r][0] < ex[0] - 1 or boxes[r][1] < ex[1] - 1 or boxes[r][2] > ex[2] + 1 or boxes[r][3] > ex[3] + 1
               or any(overlap(boxes[r], o) for o in fixed) or any(overlap(boxes[r], boxes[q]) for q in move if q != r)]
        print(json.dumps({"ok": not bad, "bad": bad, "moved": {r: [round(ToMM(fps[r].GetPosition().x), 3), round(ToMM(fps[r].GetPosition().y), 3),
                                                                    fps[r].GetOrientationDegrees()] for r in move}}))
        return
    pool_spec = json.load(open(arg("--pool"))) if mode == "class" else None
    sigma = float(arg("--sigma", "1.0"))
    start = {r: (ToMM(fps[r].GetPosition().x), ToMM(fps[r].GetPosition().y), fps[r].GetOrientationDegrees()) for r in move}
    placed, draws, levels = {}, 0, {}
    n_locked = len(fixed)
    for ref in move:
        f = fps[ref]
        nets = [p.GetNetname() for p in f.Pads()]
        pin = next((ic_nets[n] for n in nets if n in ic_nets and not n.upper().startswith("GND")), None)
        pin = "VDDx" if pin in ("VDD", "VDDIO") else pin
        band = coarse_band("C", value_band("C", f.GetValue())) if ref.startswith("C") else "-"
        pool = None
        if priors is not None:
            pool = priors["roles"].get(f"{pin}|C|{band}") or []
            if len(pool) < 5:
                pool = priors["fallback"]
        for k in range(500):
            draws += 1
            if mode == "class":
                x, y, ang, lvl = draw_class(rng, pool_spec[ref], ic, f)
            elif mode == "perturb":
                x, y, ang = rng.gauss(start[ref][0], sigma), rng.gauss(start[ref][1], sigma), start[ref][2]
            elif mode == "prior":
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
            if "--nogate" in sys.argv:   # spike 5 sensitivity: the draw as it falls, KRT's template pass makes it legal
                fixed.append(bx)
                placed[ref] = [round(x, 3), round(y, 3), ang]
                levels[ref] = lvl
                break
            if bx[0] < ex[0] - 1 or bx[1] < ex[1] - 1 or bx[2] > ex[2] + 1 or bx[3] > ex[3] + 1:
                continue
            if any(overlap(bx, o) for o in fixed):
                continue
            fixed.append(bx)
            placed[ref] = [round(x, 3), round(y, 3), ang]
            if mode == "class":
                levels[ref] = lvl
            break
        else:
            if "--keep-stuck" in sys.argv:   # spike 5 sensitivity: a part with no legal draw keeps the designer's pose
                f.SetPosition(pcbnew.VECTOR2I(FromMM(start[ref][0]), FromMM(start[ref][1])))
                f.SetOrientationDegrees(start[ref][2])
                bx = cy_box(f)
                # against the parts this seed moved only: the designer's own pose may touch a neighbour's box, and that is hers
                if not any(overlap(bx, mb) for mb in fixed[n_locked:]):
                    fixed.append(bx)
                    placed[ref] = [round(start[ref][0], 3), round(start[ref][1], 3), start[ref][2]]
                    levels[ref] = "designer"
                    continue
            print(json.dumps({"ok": False, "draws": draws, "why": f"{ref}: no legal draw in 500"}))
            return
    if "--dry" not in sys.argv:
        b.Save(out)
    print(json.dumps({"ok": True, "draws": draws, "moved": placed, "levels": levels}))


if __name__ == "__main__":
    main()
