"""pcb irdrop BOARD --net NET --source REF.PAD[,REF.PAD] [--sink REF.PAD=AMPS ...] [--config checks.json] [--grid 0.1]
                [--out DIR] [--json]

DC voltage drop and current density on one net's real copper (IRDROP-1). KiCad's own hit tests rasterise the net on
every copper layer (tracks, pads, vias, the zone fill as poured, so thermal spokes and pour necks are what the fab
gets) at --grid mm; vias and plated holes link the layers through their barrels; `pcbir_solve.py` solves the network
under `uv run --with numpy --with scipy` (KiCad's Python, run isolated, has neither). The source pads are 0 V; each
sink draws its current. Without --sink the sinks are the config's `feeds` rows on this net (pad, amps), capacitors left
out (their feeds rows are ripple current, a capacitor draws no DC; the report lists what was left out). Copper weight
from the config's `copper_oz` (outer 1.0, inner 0.5 by default), plating 25 um (JLC's minimum).

Report (irdrop.json in --out, default /tmp/pcb-irdrop/<board>-<net>): drop at every sink in mV, the worst
current-density cells outside the pads with coordinates (A/mm^2: a neck or a spoke shows up here long before a width
rule does; inside a pad the density is set by the pad, 2.5 A into a 0.3 mm pad is ~240 A/mm^2), total I^2 R, and
irdrop.svg, the current-density map per layer. `judge` (spike #3, C1): the solved current rated against the copper it
crosses by the `feeds` arithmetic, so the verdict is per neck, not per cell: necks (a cut across the copper at the hottest
cells, width x thickness against IPC-2221 at the config's rise_c; a neck as wide as the pad beside it and under 1 mm long
is that pad's own exit, status `pad`), every via and plated-hole barrel against IPC-2221 on its plating, and sinks the
source does not reach (`unreached`). `pcb check` reads it as the `irdrop` row. Solver selftest: `uv run --with numpy --with scipy python3
pcbir_solve.py --selftest` (a 10 x 1 mm strip against rho L / (w t)).
"""
import base64, json, math, os, subprocess, sys, time, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pcbnew  # noqa: E402
from pcbnew import ToMM, FromMM  # noqa: E402
import pcbq  # noqa: E402

PLATING_UM = 25.0
RHO = 1.72e-8


def opt(args, name, default=None, multi=False):
    vals = []
    while name in args:
        i = args.index(name)
        vals.append(args[i + 1]); del args[i:i + 2]
    return vals if multi else (vals[-1] if vals else default)


def extract(b, net, source, sinks, h, oz, rise_c=20.0):
    stack = list(b.GetEnabledLayers().CuStack())
    names = [b.GetLayerName(l) for l in stack]
    nL = len(stack)
    outer = (pcbnew.F_Cu, pcbnew.B_Cu)
    t_um = [35.0 * float(oz.get("outer", 1.0) if l in outer else oz.get("inner", 0.5)) for l in stack]
    tracks = [t for t in b.GetTracks() if t.GetNetname() == net]
    pads = [p for f in b.GetFootprints() for p in f.Pads() if p.GetNetname() == net]
    zones = [z for z in b.Zones() if not z.GetIsRuleArea() and z.GetNetname() == net]
    # extent of the net's copper from item positions (BOX2I is a broken SWIG type in this build)
    xs, ys = [], []
    for t in tracks:
        if t.GetClass() == "PCB_VIA":
            w = ToMM(t.GetWidth(pcbnew.F_Cu)); pts = (t.GetPosition(),)
        else:
            w = ToMM(t.GetWidth()); pts = (t.GetStart(), t.GetEnd())
        for v in pts:
            xs += [ToMM(v.x) - w, ToMM(v.x) + w]; ys += [ToMM(v.y) - w, ToMM(v.y) + w]
    for p in pads:
        r = ToMM(p.GetBoundingRadius()); c = p.GetPosition()
        xs += [ToMM(c.x) - r, ToMM(c.x) + r]; ys += [ToMM(c.y) - r, ToMM(c.y) + r]
    zc = []
    for z in zones:
        cs = [(ToMM(z.GetCornerPosition(i).x), ToMM(z.GetCornerPosition(i).y)) for i in range(z.GetNumCorners())]
        zc.append(cs); xs += [c[0] for c in cs]; ys += [c[1] for c in cs]
    x0, y0 = min(xs) - 0.5, min(ys) - 0.5
    nx, ny = int(math.ceil((max(xs) + 0.5 - x0) / h)), int(math.ceil((max(ys) + 0.5 - y0) / h))
    plane = nx * ny
    cu = bytearray(nL * plane)
    cx = [x0 + (i + 0.5) * h for i in range(nx)]; cy = [y0 + (j + 0.5) * h for j in range(ny)]

    def window(xa, xb, ya, yb):
        return (max(0, int((ya - y0) / h)), min(ny, int(math.ceil((yb - y0) / h)) + 1),
                max(0, int((xa - x0) / h)), min(nx, int(math.ceil((xb - x0) / h)) + 1))

    def capsule(l, ax, ay, bx, by, r):
        j0, j1, i0, i1 = window(min(ax, bx) - r, max(ax, bx) + r, min(ay, by) - r, max(ay, by) + r)
        dx, dy = bx - ax, by - ay; L2 = dx * dx + dy * dy; r2 = r * r; base = l * plane
        for j in range(j0, j1):
            py = cy[j]
            for i in range(i0, i1):
                px = cx[i]
                u = min(1.0, max(0.0, ((px - ax) * dx + (py - ay) * dy) / L2)) if L2 > 0 else 0.0
                if (px - ax - u * dx) ** 2 + (py - ay - u * dy) ** 2 <= r2:
                    cu[base + j * nx + i] = 1

    vlinks, vinfo = [], []   # vinfo[k]: (drill mm, x, y, what) for vlinks[k], so the solve can rate each barrel
    gap_m = ToMM(b.GetDesignSettings().GetBoardThickness()) * 1e-3 / max(1, nL - 1)

    ties = []   # (layer, iy, ix, iy2, ix2): the barrel's cell tied to every cell under its ring, so a via is not a point
    #            contact (kicad-irdrop does the same; without it the drop through a via read 6 to 21 % high, spike #3)

    def barrel(x, y, drill_mm, la, lb, what="via", ring_mm=None):
        G = (math.pi * drill_mm * 1e-3 * PLATING_UM * 1e-6) / (RHO * gap_m)
        ix, iy = int((x - x0) / h), int((y - y0) / h)
        for l in range(la, lb):
            vlinks.append([l, l + 1, iy, ix, G]); vinfo.append([round(drill_mm, 3), round(x, 3), round(y, 3), what])
        r = max(ring_mm or 0.0, drill_mm / 2 + PLATING_UM * 1e-3)
        k = int(r / h) + 1
        for l in range(la, lb + 1):
            for j in range(max(0, iy - k), min(ny, iy + k + 1)):
                for i in range(max(0, ix - k), min(nx, ix + k + 1)):
                    if (i, j) != (ix, iy) and (cx[i] - x) ** 2 + (cy[j] - y) ** 2 <= r * r:
                        ties.append([l, iy, ix, j, i])

    for t in tracks:
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition(); x, y = ToMM(p.x), ToMM(p.y)
            la, lb = sorted((stack.index(t.TopLayer()), stack.index(t.BottomLayer())))
            for l in range(la, lb + 1):
                capsule(l, x, y, x, y, ToMM(t.GetWidth(pcbnew.F_Cu)) / 2)
            barrel(x, y, ToMM(t.GetDrillValue()), la, lb, ring_mm=ToMM(t.GetWidth(pcbnew.F_Cu)) / 2)
            continue
        if t.GetLayer() not in stack:
            continue
        l = stack.index(t.GetLayer()); r = ToMM(t.GetWidth()) / 2
        s, e = t.GetStart(), t.GetEnd()
        if t.GetClass() == "PCB_ARC":
            m = t.GetMid()
            capsule(l, ToMM(s.x), ToMM(s.y), ToMM(m.x), ToMM(m.y), r); capsule(l, ToMM(m.x), ToMM(m.y), ToMM(e.x), ToMM(e.y), r)
        else:
            capsule(l, ToMM(s.x), ToMM(s.y), ToMM(e.x), ToMM(e.y), r)

    pad_cells, pad_minor = {}, {}
    for p in pads:
        name = f"{p.GetParentFootprint().GetReference()}.{p.GetNumber()}"
        pad_minor[name] = round(min(ToMM(p.GetSize().x), ToMM(p.GetSize().y)), 3)
        c = p.GetPosition(); r = ToMM(p.GetBoundingRadius()); px, py = ToMM(c.x), ToMM(c.y)
        j0, j1, i0, i1 = window(px - r, px + r, py - r, py + r)
        cells = pad_cells.setdefault(name, set())
        for l_i, l in enumerate(stack):
            if not p.IsOnLayer(l):
                continue
            for j in range(j0, j1):
                for i in range(i0, i1):
                    if p.HitTest(pcbnew.VECTOR2I(FromMM(cx[i]), FromMM(cy[j])), 0):
                        k = l_i * plane + j * nx + i
                        cu[k] = 1; cells.add(k)
        if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and p.GetDrillSize().x > 0:
            barrel(px, py, ToMM(p.GetDrillSize().x), 0, nL - 1, name, ring_mm=min(ToMM(p.GetSize().x), ToMM(p.GetSize().y)) / 2)
    for z, cs in zip(zones, zc):
        j0, j1, i0, i1 = window(min(c[0] for c in cs), max(c[0] for c in cs), min(c[1] for c in cs), max(c[1] for c in cs))
        for l_i, l in enumerate(stack):
            if not z.IsOnLayer(l) or not z.HasFilledPolysForLayer(l):
                continue
            base = l_i * plane
            for j in range(j0, j1):
                yy = FromMM(cy[j])
                for i in range(i0, i1):
                    k = base + j * nx + i
                    if not cu[k] and z.HitTestFilledArea(l, pcbnew.VECTOR2I(FromMM(cx[i]), yy)):
                        cu[k] = 1
    src = set()
    for s_ in source.split(","):
        if s_ not in pad_cells:
            sys.exit(f"pcb irdrop: source {s_} is not a pad on {net} (pads: {', '.join(sorted(pad_cells))})")
        src |= pad_cells[s_]
    for name, _ in sinks:
        if name not in pad_cells:
            sys.exit(f"pcb irdrop: sink {name} is not a pad on {net}")
    return {"net": net, "source": source, "h_mm": h, "shape": [nL, ny, nx], "layers": names, "t_um": t_um, "origin": [x0, y0],
            "cu_z": base64.b64encode(zlib.compress(bytes(cu))).decode(), "vlinks": vlinks, "source_cells": sorted(src),
            "sinks": [{"pad": n, "amps": a, "cells": sorted(pad_cells[n])} for n, a in sinks],
            "pad_cells": sorted(set().union(*pad_cells.values())) if pad_cells else [],
            "vinfo": vinfo, "ties": ties, "plating_um": PLATING_UM, "rise_c": float(rise_c), "outer": [0, nL - 1],
            "pads": [{"pad": n, "minor_mm": pad_minor[n], "cells": sorted(c)} for n, c in pad_cells.items() if c]}


def run(b, net, source, sinks, h, cfg, out):
    """Extract the net (KiCad's Python), solve it under uv (numpy + scipy), return the report; raises RuntimeError.
    pcbcheck's `irdrop` row calls this on the board it already has open."""
    os.makedirs(out, exist_ok=True)
    t = time.time()
    d = extract(b, net, source, sinks, h, cfg.get("copper_oz", {}), float(cfg.get("rise_c", 20.0)))
    t_ex = time.time() - t
    inp = os.path.join(out, "irdrop-in.json")
    json.dump(d, open(inp, "w"))
    cmd = ["uv", "run", "--no-project", "--quiet", "--with", "numpy", "--with", "scipy", "python3",
           os.path.join(HERE, "pcbir_solve.py"), inp, "--svg", os.path.join(out, "irdrop.svg")]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, cwd=out)
    except FileNotFoundError:
        raise RuntimeError("`uv` not found; the solver needs it for numpy and scipy (brew install uv)")
    if p.returncode:
        raise RuntimeError(f"solver failed: {p.stderr[-800:]}")
    rep = json.loads(p.stdout.strip().splitlines()[-1])
    rep.update(extract_s=round(t_ex, 1), solve_s=round(time.time() - t - t_ex, 1), svg=os.path.join(out, "irdrop.svg"))
    return rep


def main():
    args = sys.argv[1:]
    as_json = "--json" in args
    if as_json:
        args.remove("--json")
    net = opt(args, "--net"); source = opt(args, "--source"); h = float(opt(args, "--grid", "0.1"))
    sink_args = opt(args, "--sink", multi=True)
    cfg_path = opt(args, "--config"); out = opt(args, "--out")
    if not args or not net or not source:
        sys.exit(__doc__)
    board = os.path.abspath(args[0])
    cfg = json.load(open(cfg_path)) if cfg_path else {}
    b = pcbnew.LoadBoard(board)
    left_out = []
    if sink_args:
        sinks = [(s.split("=")[0], float(s.split("=")[1])) for s in sink_args]
    else:
        fps = pcbq.fp_map(b)
        sinks = []
        for f in cfg.get("feeds", []):
            try:
                if pcbq.pad_of(fps, f["pad"]).GetNetname() == net and f["pad"] not in source.split(","):
                    (left_out if f["pad"].startswith("C") else sinks).append((f["pad"], float(f["amps"])))
            except SystemExit:
                pass
        if not sinks:
            sys.exit(f"pcb irdrop: no sinks: pass --sink REF.PAD=AMPS or a --config whose feeds rows name pads on {net}")
    out = out or os.path.join("/tmp/pcb-irdrop", f"{os.path.splitext(os.path.basename(board))[0]}-{net}")
    rep = run(b, net, source, sinks, h, cfg, out)
    rep.update(board=board, left_out=[f"{n} {a} A (capacitor: ripple current, no DC)" for n, a in left_out])
    json.dump(rep, open(os.path.join(out, "irdrop.json"), "w"), indent=1)
    if as_json:
        print(json.dumps(rep))
        return
    print(f"PCBIR {net} from {source}: {rep['cells']} cells at {h} mm, I2R {rep['power_mW']} mW, worst J {rep['max_J_A_mm2']} A/mm2 "
          f"({rep['extract_s']} s extract, {rep['solve_s']} s solve)")
    for s in rep["sinks"]:
        print(f"PCBIR sink {s['pad']} {s['amps']} A: drop {s['drop_mV']} mV")
    for n in rep["left_out"]:
        print(f"PCBIR left out {n}")
    for w in rep["worst"][:5]:
        print(f"PCBIR hot {w['layer']} ({w['x']}, {w['y']}): {w['J_A_mm2']} A/mm2, {w['I_A']} A through the cell")
    jd = rep.get("judge", {})
    for n in jd.get("necks", [])[:4]:
        print(f"PCBIR neck {n['status'].upper()} {n['layer']} ({n['x']}, {n['y']}): {n['width_mm']} mm wide, {n['length_mm']} mm long, "
              f"{n['I_A']} A against IPC {n['ipc_A']} A (x{n['ratio']}){' near ' + ', '.join(n['near_pads']) if n['near_pads'] else ''}")
    for v in jd.get("barrels", [])[:3]:
        print(f"PCBIR barrel {v['status'].upper()} {v['what']} ({v['x']}, {v['y']}) {v['drill_mm']} mm: {v['I_A']} A against IPC {v['ipc_A']} A (x{v['ratio']})")
    for u in rep.get("unreached", []):
        print(f"PCBIR OPEN sink {u}: no copper path from the source")
    print(f"PCBIR -> {os.path.join(out, 'irdrop.json')}, {rep['svg']}")


if __name__ == "__main__":
    main()
