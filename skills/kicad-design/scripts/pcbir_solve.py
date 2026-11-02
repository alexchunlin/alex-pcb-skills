"""DC solve for `pcb irdrop` (numpy + scipy, run under `uv run --with numpy --with scipy`; KiCad's Python has no scipy).

Input: the JSON `pcbir.py` writes (raster as zlib bytes, cells as flat indices). One resistor network per net: every copper cell is a node, same-layer neighbours are
joined by the sheet conductance of the layer (square cells, so G = t / rho), vias and plated holes join a cell to the
same cell on the next layer by the barrel conductance. The source pad's cells are held at 0 V and each sink pad draws
its current spread evenly over its cells. Output (JSON on stdout): the drop at every sink, the current density per
cell, the worst cells per layer, total I^2 R.

  python3 pcbir_solve.py IN.json [--svg OUT.svg]
  python3 pcbir_solve.py --selftest      a 10 x 1 mm strip of 1 oz copper carrying 1 A: R = rho L / (w t)
"""
import base64, json, sys, zlib

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

RHO = 1.72e-8   # ohm m, annealed copper at 20 degC


def solve(cu, h_mm, t_um, vlinks, source_mask, sinks):
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
    free = np.ones(n, bool); free[fixed] = False
    V = np.zeros(n)
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
    p = float((gx * (Vz[:, :, :-1] - Vz[:, :, 1:]) ** 2).sum() + (gy * (Vz[:, :-1, :] - Vz[:, 1:, :]) ** 2).sum())
    for la, lb, iy, ix, G in vlinks:
        if cu[la, iy, ix] and cu[lb, iy, ix]:
            p += G * (Vz[la, iy, ix] - Vz[lb, iy, ix]) ** 2
    return out, I, p


def report(d, cu, sink_masks, out, I, p, pads=None):
    h = float(d["h_mm"]); t = d["t_um"]; layers = d["layers"]
    x0, y0 = d["origin"]
    J = np.zeros_like(I)
    for l in range(I.shape[0]):
        J[l] = I[l] / (h * t[l] * 1e-3)                        # A per mm^2 of copper cross-section
    sinks = []
    for sk, m in zip(d["sinks"], sink_masks):
        m = m & cu
        sinks.append({"pad": sk["pad"], "amps": sk["amps"], "drop_mV": round(-float(np.nanmean(out[m])) * 1e3, 2) if m.any() else None})
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
            "max_J_A_mm2": worst[0]["J_A_mm2"] if worst else 0.0, "worst": worst[:8], "power_mW": round(p * 1e3, 2)}, J


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
    print(json.dumps({"selftest": "PASS" if ok else "FAIL", "drop_mV": round(drop, 4), "want_mV": round(want, 4),
                      "J_mid_A_mm2": round(float(J), 2), "want_J": round(1 / 0.035, 2), "power_mW": round(p * 1e3, 4)}))
    return ok


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
    out, I, p = solve(cu, float(d["h_mm"]), [float(x) for x in d["t_um"]], vl, src,
                      [(sk["pad"], float(sk["amps"]), m) for sk, m in zip(d["sinks"], sink_masks)])
    rep, J = report(d, cu, sink_masks, out, I, p, mask(d.get("pad_cells", [])))
    if "--svg" in sys.argv:
        path = sys.argv[sys.argv.index("--svg") + 1]
        svg_map(d, cu, J, rep, sink_masks, src, path)
        np.savez_compressed(path[:-4] + "-map.npz", J=J.astype(np.float32), cu=cu, V=np.nan_to_num(out).astype(np.float32))
    print(json.dumps(rep))


if __name__ == "__main__":
    main()
