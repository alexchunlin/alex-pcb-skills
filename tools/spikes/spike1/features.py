"""Spike #1: hand features of a placement, from a board's static geometry (board_kpy.py) and (ref, x, y, rot).

Pure Python plus numpy and matplotlib.path (the repo's .venv); no KiCad, so the search can score a candidate in
milliseconds and verify_all 32 can recompute from the committed rows.

  features(static, placement, decoupling, conflicts=None) -> dict
    hpwl, hpwl_signal         pad-centre half perimeter over all nets / the non-plane nets (pcbq.hpwl's definition)
    hpwl_by_class             per net class of the .kicad_pro (patterns), plane nets as their own class "plane"
    hpwl_wide, hpwl_default   signal nets in a class wider than Default / in Default
    mst_signal                Manhattan minimum spanning trees over the signal nets' pads (KRT place_simple's wire term)
    foreign_pad_cross         signal MST edges over another net's pad box (KRT's pad term)
    cong_max, cong_p90, cong_cells_ge6   pads per 2 mm cell on a grid from the Edge.Cuts origin (pin-pitch congestion)
    halo_intrusions           other parts' pads within 1.0 mm of a fine-pitch IC's pads (pitch <= 0.8 mm; KRT's halo)
    tight_pairs, min_gap      pad pairs of different parts and nets under 0.5 mm apart (box to box), and the smallest gap
    decap_mean_mm, decap_excess_mm, decap_by_row   each declared decoupling row: the cap's pad on the IC pin's net to
                              that pin, mean, and the sum past each row's max_mm
    pour_foreign_mm2, pour_overlap   courtyard box over another net's outer-layer pour outline on the part's side, total
                              and per part (mm2, parts with any); ground floods left out (they flow round every part)
    pads_off_pour             pads of a net that pours on that layer lying outside every own-net outline there
    conflicts, signal_conflicts   KRT's MPS counts when given (`pcb q conflicts`, from the row)
"""
import fnmatch, math

import numpy as np
from matplotlib.path import Path as MPath

GRID = 2.0
RASTER = 0.25
SCALARS = ["hpwl", "hpwl_signal", "hpwl_wide", "hpwl_default", "mst_signal", "foreign_pad_cross", "cong_max", "cong_p90",
           "cong_cells_ge6", "halo_intrusions", "tight_pairs", "min_gap", "decap_mean_mm", "decap_excess_mm",
           "pour_foreign_mm2", "pads_off_pour", "conflicts", "signal_conflicts"]


def net_class(static, net):
    if net in static["plane_nets"]:
        return "plane"
    for pat, cls in static["class_patterns"]:
        if fnmatch.fnmatchcase(net, pat):
            return cls
    return "Default"


def pads_world(static, placement):
    """[(ref, num, net, x, y, w, h, th, side)] with each footprint at its placed pose."""
    pose = {r: (x, y, rot) for r, x, y, rot in placement}
    out = []
    for f in static["footprints"]:
        x, y, rot = pose.get(f["ref"], (f["x"], f["y"], f["rot"]))
        t = math.radians(rot - f["rot"])
        c, s = math.cos(t), math.sin(t)
        quarter = round(((rot - f["rot"]) % 180) / 90) % 2 == 1
        for p in f["pads"]:
            dx, dy = p["dx"], p["dy"]
            w, h = (p["h"], p["w"]) if quarter else (p["w"], p["h"])
            out.append((f["ref"], p["num"], p["net"], x + dx * c + dy * s, y - dx * s + dy * c, w, h, p["th"], f["side"]))
    return out


def court_box(static, f, x, y, rot):
    t = math.radians(rot - f["rot"])
    c, s = math.cos(t), math.sin(t)
    xs = [x + dx * c + dy * s for dx, dy in f["court"]]
    ys = [y - dx * s + dy * c for dx, dy in f["court"]]
    return min(xs), min(ys), max(xs), max(ys)


def mst(pts):
    n = len(pts)
    if n < 2:
        return 0.0, []
    a = np.array(pts)
    d = np.abs(a[:, None, :] - a[None, :, :]).sum(-1)
    used = np.zeros(n, bool); used[0] = True
    best = d[0].copy(); par = np.zeros(n, int)
    total, edges = 0.0, []
    for _ in range(n - 1):
        b = np.where(used, np.inf, best)
        j = int(np.argmin(b))
        total += float(b[j]); edges.append((int(par[j]), j)); used[j] = True
        upd = d[j] < best
        best = np.where(upd, d[j], best); par = np.where(upd, j, par)
    return total, edges


def seg_box(x0, y0, x1, y1, bx0, by0, bx1, by1):
    """Liang-Barsky: does the segment cross the box?"""
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - bx0), (dx, bx1 - x0), (-dy, y0 - by0), (dy, by1 - y0)):
        if p == 0:
            if q < 0:
                return False
        else:
            r = q / p
            if p < 0:
                t0 = max(t0, r)
            else:
                t1 = min(t1, r)
            if t0 > t1:
                return False
    return True


_RASTERS = {}


def pour_rasters(static):
    """Per (layer, net): a boolean raster of the outer-layer zone outlines at RASTER mm, cached per board."""
    key = static["board"]
    if key in _RASTERS:
        return _RASTERS[key]
    x0, y0, x1, y1 = static["edge"]
    xs = np.arange(x0 + RASTER / 2, x1, RASTER); ys = np.arange(y0 + RASTER / 2, y1, RASTER)
    gx, gy = np.meshgrid(xs, ys)
    pts = np.column_stack([gx.ravel(), gy.ravel()])
    masks = {}
    for z in static["zones"]:
        for layer in z["layers"]:
            if layer not in ("F.Cu", "B.Cu") or not z["net"] or len(z["outline"]) < 3:
                continue
            m = MPath(z["outline"]).contains_points(pts).reshape(gx.shape)
            k = (layer, z["net"])
            masks[k] = masks[k] | m if k in masks else m
    paths = {}
    for z in static["zones"]:
        for layer in z["layers"]:
            if layer in ("F.Cu", "B.Cu") and z["net"] and len(z["outline"]) >= 3:
                paths.setdefault((layer, z["net"]), []).append(MPath(z["outline"]))
    _RASTERS[key] = (masks, paths, (x0, y0, len(xs), len(ys)))
    return _RASTERS[key]


def features(static, placement, decoupling=(), conflicts=None):
    pads = pads_world(static, placement)
    planes = set(static["plane_nets"])
    by_net = {}
    for p in pads:
        if p[2] and not p[2].startswith("unconnected-"):
            by_net.setdefault(p[2], []).append(p)
    widths = static.get("class_widths") or {}
    base_w = widths.get("Default") or 0.0
    hp, hp_cls = {}, {}
    for n, ps in by_net.items():
        if len(ps) < 2:
            continue
        xs, ys = [p[3] for p in ps], [p[4] for p in ps]
        hp[n] = (max(xs) - min(xs)) + (max(ys) - min(ys))
        c = net_class(static, n)
        hp_cls[c] = hp_cls.get(c, 0.0) + hp[n]
    sig = [n for n in hp if n not in planes]
    wide = [n for n in sig if (widths.get(net_class(static, n)) or 0) > base_w + 1e-9]
    f = {"hpwl": sum(hp.values()), "hpwl_signal": sum(hp[n] for n in sig), "hpwl_wide": sum(hp[n] for n in wide),
         "hpwl_default": sum(hp[n] for n in sig if n not in wide), "hpwl_by_class": {k: round(v, 3) for k, v in sorted(hp_cls.items())}}
    # MST and foreign-pad crossings over the signal nets
    boxes = [(p[3] - p[5] / 2, p[4] - p[6] / 2, p[3] + p[5] / 2, p[4] + p[6] / 2) for p in pads]
    total, cross = 0.0, 0
    for n in sig:
        ps = by_net[n]
        L, edges = mst([(p[3], p[4]) for p in ps])
        total += L
        for i, j in edges:
            a, b = ps[i], ps[j]
            for q, bx in zip(pads, boxes):
                if q[2] == n or not q[2]:
                    continue
                if seg_box(a[3], a[4], b[3], b[4], *bx):
                    cross += 1
    f["mst_signal"], f["foreign_pad_cross"] = total, cross
    # pads per 2 mm cell
    ex0, ey0, ex1, ey1 = static["edge"]
    nx, ny = int(math.ceil((ex1 - ex0) / GRID)), int(math.ceil((ey1 - ey0) / GRID))
    grid = np.zeros((ny, nx), int)
    for p in pads:
        i, j = int((p[4] - ey0) // GRID), int((p[3] - ex0) // GRID)
        if 0 <= i < ny and 0 <= j < nx:
            grid[i, j] += 1
    occ = grid[grid > 0]
    f["cong_max"] = int(grid.max())
    f["cong_p90"] = float(np.percentile(occ, 90)) if occ.size else 0.0
    f["cong_cells_ge6"] = int((grid >= 6).sum())
    # pad-to-pad gaps between parts, and the halo in front of fine-pitch ICs
    P = np.array([[p[3], p[4], p[5] / 2, p[6] / 2] for p in pads])
    refs = np.array([p[0] for p in pads]); nets = np.array([p[2] for p in pads])
    gx = np.abs(P[:, None, 0] - P[None, :, 0]) - P[:, None, 2] - P[None, :, 2]
    gy = np.abs(P[:, None, 1] - P[None, :, 1]) - P[:, None, 3] - P[None, :, 3]
    gap = np.hypot(np.maximum(gx, 0), np.maximum(gy, 0))
    other = (refs[:, None] != refs[None, :]) & ((nets[:, None] != nets[None, :]) | (nets[:, None] == ""))
    iu = np.triu_indices(len(pads), 1)
    g = gap[iu][other[iu]]
    f["tight_pairs"] = int((g < 0.5).sum())
    f["min_gap"] = float(g.min()) if g.size else 10.0
    fine = set()
    for fp in static["footprints"]:
        ps = [(q["dx"], q["dy"]) for q in fp["pads"]]
        if len(ps) >= 8:
            d = min(math.hypot(a[0] - b[0], a[1] - b[1]) for i, a in enumerate(ps) for b in ps[i + 1:])
            if d <= 0.8:
                fine.add(fp["ref"])
    hal = 0
    for r in fine:
        mine = refs == r
        near = (gap[mine][:, ~mine] < 1.0).any(0)
        hal += int(near.sum())
    f["halo_intrusions"] = hal
    # declared decoupling rows: the cap's pad on the IC pin's net to that pin
    pin = {(p[0], p[1]): p for p in pads}
    rows, ds, ex = {}, [], 0.0
    for d in decoupling:
        ic = pin.get((d["ic"], str(d["pin"])))
        if not ic:
            continue
        cps = [p for p in pads if p[0] == d["cap"] and p[2] == ic[2]] or [p for p in pads if p[0] == d["cap"]]
        if not cps:
            continue
        dist = min(math.hypot(p[3] - ic[3], p[4] - ic[4]) for p in cps)
        rows[f"{d['ic']}.{d['pin']}:{d['cap']}"] = round(dist, 3)
        ds.append(dist)
        ex += max(0.0, dist - float(d.get("max_mm") or 99))
    f["decap_mean_mm"] = float(np.mean(ds)) if ds else 0.0
    f["decap_excess_mm"] = ex
    f["decap_by_row"] = rows
    # pours: courtyard boxes over foreign outer-layer outlines, pads outside their own net's outline on that layer
    masks, paths, (rx0, ry0, nrx, nry) = pour_rasters(static)
    pose = {r: (x, y, rot) for r, x, y, rot in placement}
    over = {}
    for fp in static["footprints"]:
        x, y, rot = pose.get(fp["ref"], (fp["x"], fp["y"], fp["rot"]))
        layer = "B.Cu" if fp["side"] == "B" else "F.Cu"
        bx0, by0, bx1, by1 = court_box(static, fp, x, y, rot)
        j0, j1 = max(0, int((bx0 - rx0) / RASTER)), min(nrx, int(math.ceil((bx1 - rx0) / RASTER)))
        i0, i1 = max(0, int((by0 - ry0) / RASTER)), min(nry, int(math.ceil((by1 - ry0) / RASTER)))
        own = {q["net"] for q in fp["pads"]}
        tot = 0.0
        if j1 > j0 and i1 > i0:
            acc = np.zeros((i1 - i0, j1 - j0), bool)
            for (lay, net), m in masks.items():
                if lay == layer and net not in own and "GND" not in net.upper():   # a ground flood is meant to flow round parts
                    acc |= m[i0:i1, j0:j1]
            tot = float(acc.sum()) * RASTER * RASTER
        if tot > 0:
            over[fp["ref"]] = round(tot, 3)
    f["pour_foreign_mm2"] = round(sum(over.values()), 3)
    f["pour_overlap"] = over
    off = 0
    for p in pads:
        for lay in (("F.Cu", "B.Cu") if p[7] else ("B.Cu" if p[8] == "B" else "F.Cu",)):
            ps = paths.get((lay, p[2]))
            if ps and not any(pp.contains_point((p[3], p[4])) for pp in ps):
                off += 1
                break
    f["pads_off_pour"] = off
    if conflicts:
        f["conflicts"], f["signal_conflicts"] = conflicts
    for k in ("hpwl", "hpwl_signal", "hpwl_wide", "hpwl_default", "mst_signal", "cong_p90", "min_gap", "decap_mean_mm", "decap_excess_mm"):
        f[k] = round(f[k], 3)
    return f
