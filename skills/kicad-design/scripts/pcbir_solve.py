"""DC solve for `pcb irdrop` (numpy + scipy, run under `uv run --with numpy --with scipy`; KiCad's Python has no scipy).

Input: the JSON `pcbir.py` writes (raster as zlib bytes, cells as flat indices). One resistor network per net: every copper cell is a node, same-layer neighbours are
joined by the sheet conductance of the layer (square cells, so G = t / rho), vias and plated holes join a cell to the
same cell on the next layer by the barrel conductance. The source pad's cells are held at 0 V and each sink pad draws
its current spread evenly over its cells. Output (JSON on stdout): the drop at every sink, the current density per
cell, the worst cells per layer, total I^2 R.

  python3 pcbir_solve.py IN.json [--svg OUT.svg]
  python3 pcbir_solve.py --selftest      a 10 x 1 mm strip of 1 oz copper carrying 1 A: R = rho L / (w t)
"""
import base64, json, math, sys, zlib

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from scipy.sparse import csgraph

RHO = 1.72e-8   # ohm m, annealed copper at 20 degC


def solve(cu, h_mm, t_um, vlinks, source_mask, sinks, vec=False, ties=()):
    """cu: bool [L, ny, nx]; t_um: thickness per layer; vlinks: [(layer_a, layer_b, iy, ix, G)]; source_mask: bool like
    cu; sinks: [(name, amps, bool mask)]. Returns (V [L, ny, nx] in volts, NaN off-copper; per-cell |I| in A)."""
    L, ny, nx = cu.shape
    idx = -np.ones(cu.shape, dtype=np.int64)
    n = int(cu.sum())
    idx[cu] = np.arange(n)
    rows, cols, vals = [], [], []
    gx = np.zeros((L, ny, nx - 1)); gy = np.zeros((L, ny - 1, nx))
    for l in range(L):
        g = (t_um[l] * 1e-6) / RHO   # siemens between two square cells of any size
        a = cu[l, :, :-1] & cu[l, :, 1:]
        gx[l][a] = g
        rows += [idx[l, :, :-1][a], idx[l, :, 1:][a]]; cols += [idx[l, :, 1:][a], idx[l, :, :-1][a]]; vals += [np.full(a.sum(), -g)] * 2
        a = cu[l, :-1, :] & cu[l, 1:, :]
        gy[l][a] = g
        rows += [idx[l, :-1, :][a], idx[l, 1:, :][a]]; cols += [idx[l, 1:, :][a], idx[l, :-1, :][a]]; vals += [np.full(a.sum(), -g)] * 2
    for la, lb, iy, ix, G in vlinks:
        i, j = idx[la, iy, ix], idx[lb, iy, ix]
        if i >= 0 and j >= 0:
            rows += [np.array([i, j])]; cols += [np.array([j, i])]; vals += [np.array([-G, -G])]
    if len(ties):
        tv = np.asarray(ties, dtype=np.int64)
        i, j = idx[tv[:, 0], tv[:, 1], tv[:, 2]], idx[tv[:, 0], tv[:, 3], tv[:, 4]]
        ok = (i >= 0) & (j >= 0)
        rows += [i[ok], j[ok]]; cols += [j[ok], i[ok]]; vals += [np.full(ok.sum(), -1e4)] * 2   # the ring is one node
    r = np.concatenate(rows) if rows else np.zeros(0, int); c = np.concatenate(cols) if cols else np.zeros(0, int)
    v = np.concatenate(vals) if vals else np.zeros(0)
    A = sp.coo_matrix((v, (r, c)), shape=(n, n)).tocsr()
    A = A - sp.diags(np.asarray(A.sum(axis=1)).ravel())     # Laplacian: diagonal = sum of conductances
    b = np.zeros(n)
    for _, amps, m in sinks:
        k = idx[m & cu]
        if len(k):
            b[k] -= amps / len(k)                             # current leaves the network at the sink
    fixed = idx[source_mask & cu]
    if not len(fixed):
        raise SystemExit("pcbir_solve: the source pad has no copper cells on this net")
    # copper not connected to the source (a dead island, an open pin) has no defined voltage: it is left NaN and a sink
    # there reads drop None instead of making the whole matrix singular (PLINK-0: +5V came back NaN for one open pin)
    _, lab = csgraph.connected_components(A, directed=False)
    live = np.isin(lab, np.unique(lab[fixed]))
    b[~live] = 0.0
    free = live.copy(); free[fixed] = False
    V = np.full(n, np.nan); V[live] = 0.0
    Aff = A[free][:, free]
    V[free] = spla.spsolve(Aff.tocsc(), b[free])               # V = 0 on the source
    out = np.full(cu.shape, np.nan); out[cu] = V[idx[cu]]
    # current magnitude per cell from the edge currents either side (A)
    Vz = np.nan_to_num(out)
    ix_ = np.zeros(cu.shape); iy_ = np.zeros(cu.shape)
    ex = gx * (Vz[:, :, :-1] - Vz[:, :, 1:]); ey = gy * (Vz[:, :-1, :] - Vz[:, 1:, :])
    ix_[:, :, :-1] += ex / 2; ix_[:, :, 1:] += ex / 2
    iy_[:, :-1, :] += ey / 2; iy_[:, 1:, :] += ey / 2
    I = np.hypot(ix_, iy_); I[~cu] = 0
    ix_[~cu] = 0; iy_[~cu] = 0
    p = float((gx * (Vz[:, :, :-1] - Vz[:, :, 1:]) ** 2).sum() + (gy * (Vz[:, :-1, :] - Vz[:, 1:, :]) ** 2).sum())
    for la, lb, iy, ix, G in vlinks:
        if cu[la, iy, ix] and cu[lb, iy, ix]:
            p += G * (Vz[la, iy, ix] - Vz[lb, iy, ix]) ** 2
    return (out, I, p, (ix_, iy_)) if vec else (out, I, p)   # vec: the per-cell current vector, for judge()


def report(d, cu, sink_masks, out, I, p, pads=None):
    h = float(d["h_mm"]); t = d["t_um"]; layers = d["layers"]
    x0, y0 = d["origin"]
    J = np.zeros_like(I)
    for l in range(I.shape[0]):
        J[l] = I[l] / (h * t[l] * 1e-3)                        # A per mm^2 of copper cross-section
    sinks = []
    for sk, m in zip(d["sinks"], sink_masks):
        m = m & cu
        live = m.any() and not np.isnan(out[m]).all()
        sinks.append({"pad": sk["pad"], "amps": sk["amps"], "drop_mV": round(-float(np.nanmean(out[m])) * 1e3, 2) if live else None})
    worst = []
    Jr = J.copy()
    if pads is not None:
        Jr[pads] = 0                                           # inside a pad the density is the pad's, not the layout's
    for l in range(J.shape[0]):
        for f in np.argsort(Jr[l].ravel())[::-1][:5]:
            iy, ix = divmod(int(f), J.shape[2])
            if Jr[l, iy, ix] > 0:
                worst.append({"layer": layers[l], "x": round(x0 + (ix + 0.5) * h, 2), "y": round(y0 + (iy + 0.5) * h, 2),
                              "J_A_mm2": round(float(J[l, iy, ix]), 1), "I_A": round(float(I[l, iy, ix]), 3)})
    worst.sort(key=lambda w: -w["J_A_mm2"])
    return {"net": d["net"], "source": d["source"], "h_mm": h, "cells": int(cu.sum()), "sinks": sinks,
            "max_drop_mV": max((s["drop_mV"] or 0) for s in sinks) if sinks else 0.0,
            "unreached": [s["pad"] for s in sinks if s["drop_mV"] is None],
            "max_J_A_mm2": worst[0]["J_A_mm2"] if worst else 0.0, "worst": worst[:8], "power_mW": round(p * 1e3, 2)}, J


def ipc_amps(area_mm2, rise_c, internal):
    """IPC-2221 current for a conductor cross-section (mm^2) at rise_c: k * dT^0.44 * A[mil^2]^0.725, k 0.048 outer and
    0.024 inner; the same formula as pcbcheck's currents and feeds rows (and IPC-2152's conservative chart)."""
    return (0.024 if internal else 0.048) * rise_c ** 0.44 * (area_mm2 / 0.0254 ** 2) ** 0.725


def judge(d, cu, out, vec, J, seeds_per_layer=300, j_seed=10.0, pad_mm=1.0, pad_neck_mm=1.0, max_cut=800, field_mm=1.0):
    """Rate the solved current against the copper it crosses, the way `feeds` rates a via or a track, everywhere on the net.

    Necks: from the hottest cells outside pads (J >= j_seed), a cut across the copper perpendicular to the local current;
    the current crossing it against IPC-2221 for the cut's width x thickness (outer k 0.048, inner 0.024, rise from the
    config). One neck per 2 mm, worst ratio first. IPC rates a conductor, so allowed A/mm^2 falls as the neck widens and
    there is no fixed density limit (issue #3, correction 2). A neck at least 0.9x as wide as a pad within pad_mm and no
    longer than pad_neck_mm is the pad's own exit (a 0.4 mm pin feeds through a 0.4 mm pour by construction): reported as
    `pad`, not failed. Barrels: every via and plated hole, the current through each layer-to-layer segment against
    IPC-2221 internal on pi x drill x plating (the `feeds` via formula), vias within field_mm of each other summed as
    one field. A sink the source does not reach fails."""
    h = float(d["h_mm"]); t = d["t_um"]; rise = float(d.get("rise_c", 20.0)); layers = d["layers"]
    x0, y0 = d["origin"]
    L, ny, nx = cu.shape
    outer = set(d.get("outer", [0, L - 1]))
    ix_, iy_ = vec
    pmask = np.zeros(cu.size, bool)
    pads = []
    for pd in d.get("pads", []):
        c = np.array(pd["cells"], dtype=np.int64)
        pmask[c] = True
        l_, r_ = np.divmod(c, ny * nx)
        yy, xx = np.divmod(r_, nx)
        pads.append((pd["pad"], pd["minor_mm"], l_, yy, xx))
    pmask = pmask.reshape(cu.shape)

    def on(l, y, x):
        return 0 <= y < ny and 0 <= x < nx and cu[l, y, x]

    def cut(l, y, x, px, py):
        cells = [(y, x)]
        for sgn in (1, -1):
            k = 1
            while k < max_cut:
                yy, xx = int(round(y + sgn * k * py)), int(round(x + sgn * k * px))
                if not on(l, yy, xx):
                    break
                cells.append((yy, xx)); k += 1
        return cells

    cand = []
    for l in range(L):
        Jl = np.where(cu[l] & ~pmask[l], J[l], 0.0)
        flat = np.argsort(Jl.ravel())[::-1][:seeds_per_layer]
        for f in flat:
            y, x = divmod(int(f), nx)
            if Jl[y, x] < j_seed:
                break
            vx, vy = ix_[l, y, x], iy_[l, y, x]
            n_ = math.hypot(vx, vy)
            if n_ == 0:
                continue
            dx, dy = vx / n_, vy / n_
            cells = cut(l, y, x, -dy, dx)
            icut = abs(sum(ix_[l, a, b] * dx + iy_[l, a, b] * dy for a, b in cells))
            w = len(cells) * h
            rating = ipc_amps(w * t[l] * 1e-3, rise, l not in outer)
            cand.append((icut / rating, l, y, x, dx, dy, w, icut, rating, float(J[l, y, x])))
    cand.sort(key=lambda c: -c[0])
    necks = []
    for ratio, l, y, x, dx, dy, w, icut, rating, jj in cand:
        if any(n["_l"] == l and math.hypot(n["_x"] - x, n["_y"] - y) * h < 2.0 for n in necks):
            continue
        # length: along the current both ways while the copper stays within 1.5x this width and outside pads
        steps = 0
        for sgn in (1, -1):
            k = 1
            while k < max_cut:
                yy, xx = int(round(y + sgn * k * dy)), int(round(x + sgn * k * dx))
                if not on(l, yy, xx) or pmask[l, yy, xx] or len(cut(l, yy, xx, -dy, dx)) * h > 1.5 * w:
                    break
                k += 1; steps += 1
        length = (steps + 1) * h
        near = [(nm, mn) for nm, mn, pl, py_, px_ in pads
                if ((pl == l) & (np.hypot(px_ - x, py_ - y) * h <= pad_mm)).any()]
        minor = min((mn for _, mn in near), default=None)
        pad_exit = minor is not None and w >= 0.9 * minor and length <= pad_neck_mm
        st = "pass" if ratio <= 1 else ("pad" if pad_exit else "fail")
        necks.append({"layer": layers[l], "x": round(x0 + (x + 0.5) * h, 2), "y": round(y0 + (y + 0.5) * h, 2),
                      "width_mm": round(w, 2), "length_mm": round(length, 2), "I_A": round(icut, 3), "ipc_A": round(rating, 3),
                      "ratio": round(ratio, 2), "J_A_mm2": round(jj, 1), "near_pads": [nm for nm, _ in near][:4],
                      "status": st, "_l": l, "_x": x, "_y": y})
        if len(necks) >= 8:
            break
    for n in necks:
        for k in ("_l", "_x", "_y"):
            n.pop(k)
    tp = float(d.get("plating_um", 25.0)) * 1e-3
    bars = {}
    for (la, lb, iy, ix, G), (drill, x, y, what) in zip(d["vlinks"], d.get("vinfo", [])):
        va, vb = out[la, iy, ix], out[lb, iy, ix]
        if np.isnan(va) or np.isnan(vb):
            continue
        amps = abs(va - vb) * G
        key = (x, y, what)
        if amps > bars.get(key, (0, 0))[0]:
            bars[key] = (amps, drill)
    one = [(x, y, what, amps, drill, ipc_amps(math.pi * drill * tp, rise, True)) for (x, y, what), (amps, drill) in bars.items()]
    # vias within field_mm of each other are one field and rated together, as `feeds` sums the vias near a pad: the solve
    # shares current unevenly across a field (1.5 / 1.3 / 1.2 A over three vias of 1.22 A), and vias 0.6 to 1 mm apart
    # share their copper's heat (Brooks & Adam: a via runs at its trace's temperature); a lone via is a field of one
    grp = list(range(len(one)))

    def root(i):
        while grp[i] != i:
            grp[i] = grp[grp[i]]; i = grp[i]
        return i
    for i in range(len(one)):
        for j in range(i + 1, len(one)):
            if one[i][2] == one[j][2] == "via" and math.hypot(one[i][0] - one[j][0], one[i][1] - one[j][1]) <= field_mm:
                grp[root(i)] = root(j)
    fields = {}
    for i, b in enumerate(one):
        fields.setdefault(root(i), []).append(b)
    barrels = []
    for mem in fields.values():
        amps, rating = sum(b[3] for b in mem), sum(b[5] for b in mem)
        top = max(mem, key=lambda b: b[3])
        barrels.append({"what": top[2], "x": top[0], "y": top[1], "drill_mm": top[4], "n": len(mem), "I_A": round(amps, 3),
                        "ipc_A": round(rating, 3), "ratio": round(amps / rating, 2), "max_one_A": round(top[3], 3),
                        "status": "fail" if amps > rating else "pass"})
    barrels.sort(key=lambda b: -b["ratio"])
    return {"necks": necks, "barrels": barrels[:8], "barrels_over": sum(b["status"] == "fail" for b in barrels),
            "barrels_n": len(barrels), "vias_n": len(one), "rise_c": rise,
            "worst_neck_ratio": max((n["ratio"] for n in necks if n["status"] != "pad"), default=0.0),
            "worst_barrel_ratio": barrels[0]["ratio"] if barrels else 0.0}


def svg_map(d, cu, J, rep, sink_masks, src_mask, path):
    """Current density per layer on a log ramp (1 A/mm^2 to the worst cell outside pads), one rect per run of equal colour."""
    h = float(d["h_mm"]); L, ny, nx = cu.shape
    ramp = ["#1b2a4a", "#1f4fb0", "#2f62e8", "#1a9cc0", "#0f9a66", "#e6c229", "#e2683c", "#e03a2f"]
    top = max(2.0, float(rep["max_J_A_mm2"] or 2.0))
    lo = 1.0
    px = max(1.0, min(4.0, 900.0 / max(nx, 1)))
    layers = [l for l in range(L) if cu[l].any()]
    cols = 2 if len(layers) > 1 else 1
    W, H = nx * px, ny * px
    parts = []
    for k, l in enumerate(layers):
        ox, oy = (k % cols) * (W + 16), (k // cols) * (H + 28) + 18
        parts.append(f'<text x="{ox}" y="{oy - 5}" font-family="Roboto Mono" font-size="12" fill="#e4e1d8">{d["layers"][l]}</text>')
        frac = np.clip(np.log(np.maximum(J[l], lo) / lo) / np.log(top / lo), 0, 1)
        q = np.where(cu[l], np.minimum(len(ramp) - 1, (frac * (len(ramp) - 1) + 0.5).astype(int)), -1)
        for j in range(ny):
            i = 0
            while i < nx:
                c = q[j, i]; i2 = i
                while i2 + 1 < nx and q[j, i2 + 1] == c:
                    i2 += 1
                if c >= 0:
                    parts.append(f'<rect x="{ox + i * px:.1f}" y="{oy + j * px:.1f}" width="{(i2 - i + 1) * px:.1f}" height="{px:.1f}" fill="{ramp[c]}"/>')
                i = i2 + 1
        for m, col in [(src_mask, "#e4e1d8")] + [(sm, "#ffffff") for sm in sink_masks]:
            ys, xs = np.nonzero(m[l] & cu[l])
            if len(xs):
                parts.append(f'<rect x="{ox + xs.min() * px:.1f}" y="{oy + ys.min() * px:.1f}" width="{(xs.max() - xs.min() + 1) * px:.1f}" '
                             f'height="{(ys.max() - ys.min() + 1) * px:.1f}" fill="none" stroke="{col}" stroke-width="1" stroke-dasharray="{"3 2" if col == "#ffffff" else "0"}"/>')
    rows = (len(layers) + cols - 1) // cols
    w0 = rep["worst"][0] if rep["worst"] else {}
    legend = (f'<text x="0" y="{rows * (H + 28) + 22}" font-family="Roboto Mono" font-size="11" fill="#8a877e">'
              f'{d["net"]} current density, A/mm2, log scale: dark blue 1 or less to red {top:.0f} (the worst cell outside pads). Solid box = source {d["source"]}, dashed = sinks. '
              f'Worst {w0.get("J_A_mm2", "")} A/mm2 at ({w0.get("x", "")}, {w0.get("y", "")}) {w0.get("layer", "")}</text>')
    open(path, "w").write(f'<svg xmlns="http://www.w3.org/2000/svg" width="{cols * (W + 16):.0f}" height="{rows * (H + 28) + 32:.0f}" '
                          f'style="background:#0e0f10">' + "".join(parts) + legend + "</svg>")


def selftest():
    h = 0.1
    cu = np.zeros((1, 10, 100), bool); cu[:] = True                 # 10 mm x 1 mm
    src = np.zeros_like(cu); src[0, :, 0] = True
    snk = np.zeros_like(cu); snk[0, :, -1] = True
    out, I, p = solve(cu, h, [35.0], [], src, [("end", 1.0, snk)])
    drop = -np.nanmean(out[snk]) * 1e3
    want = RHO * (9.9e-3) / (1e-3 * 35e-6) * 1e3                    # centre to centre of the end columns: 9.9 mm
    J = I[0, 5, 50] / (h * 35e-3)
    ok = abs(drop - want) / want < 0.01 and abs(J - 1 / (1.0 * 0.035)) / (1 / 0.035) < 0.02 and abs(p - want * 1e-3) / (want * 1e-3) < 0.02
    # the judge: the same strip necked to 0.3 mm for its middle 3 mm, 2 A; IPC-2221 outer 1 oz at 20 degC rates a 0.3 mm
    # track 1.353 A, so the neck is 0.3 mm wide, ~3 mm long, 2 A across it, x1.48, a fail; the 1 mm ends are x0.62
    cu2 = cu.copy(); cu2[0, :, 35:65] = False; cu2[0, 4:7, 35:65] = True
    out2, I2, p2, vec = solve(cu2, h, [35.0], [], src, [("end", 2.0, snk)], vec=True)
    J2 = I2 / (h * 35e-3)
    d = {"h_mm": h, "t_um": [35.0], "rise_c": 20.0, "layers": ["F.Cu"], "origin": [0.0, 0.0], "outer": [0],
         "pads": [], "vlinks": [], "vinfo": []}
    jd = judge(d, cu2, out2, vec, J2)
    nk = jd["necks"][0]
    want_ipc = ipc_amps(0.3 * 0.035, 20.0, False)
    ok2 = (abs(nk["width_mm"] - 0.3) < 1e-6 and abs(nk["I_A"] - 2.0) < 0.02 and abs(nk["ipc_A"] - want_ipc) < 1e-3
           and nk["status"] == "fail" and 2.5 <= nk["length_mm"] <= 3.2)
    print(json.dumps({"selftest": "PASS" if ok and ok2 else "FAIL", "drop_mV": round(drop, 4), "want_mV": round(want, 4),
                      "J_mid_A_mm2": round(float(J), 2), "want_J": round(1 / 0.035, 2), "power_mW": round(p * 1e3, 4),
                      "neck": {k: nk[k] for k in ("width_mm", "length_mm", "I_A", "ipc_A", "ratio", "status")}, "want_ipc_A": round(want_ipc, 3)}))
    return ok and ok2


def main():
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    d = json.load(open(sys.argv[1]))
    shape = tuple(d["shape"])
    cu = np.frombuffer(zlib.decompress(base64.b64decode(d["cu_z"])), dtype=np.uint8).reshape(shape).astype(bool)
    def mask(cells):
        m = np.zeros(cu.size, bool); m[np.array(cells, dtype=np.int64)] = True if cells else False
        return m.reshape(shape)
    src = mask(d["source_cells"])
    sink_masks = [mask(sk["cells"]) for sk in d["sinks"]]
    vl = [(int(a), int(b), int(c), int(e), float(g)) for a, b, c, e, g in d["vlinks"]]
    out, I, p, vec = solve(cu, float(d["h_mm"]), [float(x) for x in d["t_um"]], vl, src,
                           [(sk["pad"], float(sk["amps"]), m) for sk, m in zip(d["sinks"], sink_masks)], vec=True,
                           ties=d.get("ties", ()))
    rep, J = report(d, cu, sink_masks, out, I, p, mask(d.get("pad_cells", [])))
    if "pads" in d:
        rep["judge"] = judge(d, cu, out, vec, J)
    if "--svg" in sys.argv:
        path = sys.argv[sys.argv.index("--svg") + 1]
        svg_map(d, cu, J, rep, sink_masks, src, path)
        np.savez_compressed(path[:-4] + "-map.npz", J=J.astype(np.float32), cu=cu, V=np.nan_to_num(out).astype(np.float32))
    print(json.dumps(rep))


if __name__ == "__main__":
    main()
