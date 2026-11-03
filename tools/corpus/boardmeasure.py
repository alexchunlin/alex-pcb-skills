"""Spike 2 board measurements over corpus boards (KiCad's Python, through `pcb py`; boards are untrusted data, loaded only).

  pcb py tools/corpus/boardmeasure.py JOBS.json OUT.jsonl

JOBS: [{key, part, ref, board, pins: {canonical pin: pin number}}] from `refstat.py features`. Per job, one line:
  pins   {canonical pin: {ref: mm}}  centre-to-centre distance from the IC pad to the nearest pad of each other footprint
         on the same net (what the refstat PCB statistic and pcbcheck's decoupling rows measure)
  sats   [{ref, pin, dx, dy, rot, back, other_gnd, value}] each footprint with a two-pad net to an IC pin, its centre in the
         IC's own frame (mm, the IC's pad pattern fitted to its board pads, so rotation and mirroring are undone) and its
         rotation relative to the IC modulo 180 (the placement priors)
  ic     {w, h} the IC's courtyard-free pad extent, for scale
Run from the repo (never from inside the download tree); the board path is an argument.
"""
import json, math, re, sys

import pcbnew

ToMM = pcbnew.ToMM


def frame(fp):
    """Least-squares 2x2 map from footprint-relative to board offsets over the pads; its inverse undoes rotation and mirror."""
    sxx = sxy = syx = syy = rxx = rxy = ryy = 0.0
    p0 = fp.GetPosition()
    n = 0
    for p in fp.Pads():
        r = p.GetFPRelativePosition()
        a = p.GetPosition()
        rx, ry = ToMM(r.x), ToMM(r.y)
        ax, ay = ToMM(a.x - p0.x), ToMM(a.y - p0.y)
        sxx += ax * rx; sxy += ax * ry; syx += ay * rx; syy += ay * ry
        rxx += rx * rx; rxy += rx * ry; ryy += ry * ry
        n += 1
    det = rxx * ryy - rxy * rxy
    if n < 2 or abs(det) < 1e-9:
        th = math.radians(fp.GetOrientationDegrees())
        c, s = math.cos(th), math.sin(th)
        return (c, s, -s, c)   # fallback: orientation only (KiCad's y-down, positive = counter-clockwise on screen)
    inv = (ryy / det, -rxy / det, -rxy / det, rxx / det)
    m = (sxx * inv[0] + sxy * inv[2], sxx * inv[1] + sxy * inv[3], syx * inv[0] + syy * inv[2], syx * inv[1] + syy * inv[3])
    return m


def to_local(m, dx, dy):
    a, b, c, d = m
    det = a * d - b * c
    if abs(det) < 1e-9:
        return dx, dy
    return ((d * dx - b * dy) / det, (-c * dx + a * dy) / det)


def gnd_like(name):
    n = (name or "").upper().lstrip("/")
    return n.startswith(("GND", "VSS", "AGND", "DGND", "PGND", "0V")) or n in ("0", "EARTH")


def measure(job):
    b = pcbnew.LoadBoard(job["board"])
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    ic = fps.get(job["ref"])
    rx = re.compile(job["rx"], re.I)
    if ic is None or not (rx.search(ic.GetValue()) or rx.search(str(ic.GetFPID().GetLibItemName()))):
        cand = [f for f in b.GetFootprints() if rx.search(f.GetValue())]
        if len(cand) != 1:
            return {"ok": False, "why": f"ref {job['ref']} not the part on the board; {len(cand)} value matches"}
        ic = cand[0]
    m = frame(ic)
    flipped = ic.IsFlipped()
    pos = ic.GetPosition()
    num_to_cpin = {}
    for cp, num in job["pins"].items():
        num_to_cpin.setdefault(str(num), cp)
    pins, sats = {}, []
    pads = list(ic.Pads())
    xs = [ToMM(p.GetPosition().x) for p in pads] or [0]
    ys = [ToMM(p.GetPosition().y) for p in pads] or [0]
    for pad in pads:
        cp = num_to_cpin.get(pad.GetNumber())
        net = pad.GetNetname()
        if not cp or not net or gnd_like(net):
            continue
        near = pins.setdefault(cp, {})
        for f in b.GetFootprints():
            if f is ic:
                continue
            on = [q for q in f.Pads() if q.GetNetname() == net]
            if not on:
                continue
            d = min(math.hypot(ToMM(q.GetPosition().x - pad.GetPosition().x), ToMM(q.GetPosition().y - pad.GetPosition().y)) for q in on)
            ref = f.GetReference()
            if ref not in near or d < near[ref]:
                near[ref] = round(d, 3)
            fpads = list(f.Pads())
            if len(fpads) == 2 and not any(s["ref"] == ref for s in sats):
                other = [q.GetNetname() for q in fpads if q.GetNetname() != net]
                c = f.GetPosition()
                lx, ly = to_local(m, ToMM(c.x - pos.x), ToMM(c.y - pos.y))
                rot = (f.GetOrientationDegrees() - ic.GetOrientationDegrees()) * (-1 if flipped else 1)
                sats.append({"ref": ref, "pin": cp, "dx": round(lx, 3), "dy": round(ly, 3), "rot": round(rot % 180, 1),
                             "back": f.IsFlipped() != flipped, "other_gnd": bool(other and gnd_like(other[0])),
                             "value": f.GetValue()[:24]})
    return {"ok": True, "ic_ref": ic.GetReference(), "ic_fpid": str(ic.GetFPID().GetLibItemName())[:60], "pins": pins, "sats": sats,
            "ic": {"w": round(max(xs) - min(xs), 2), "h": round(max(ys) - min(ys), 2), "flipped": flipped},
            "n_footprints": len(fps)}


def main():
    jobs = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    done = set()
    try:
        for l in open(out):
            x = json.loads(l)
            done.add((x["key"], x["ref"]))
    except OSError:
        pass
    started = set()
    try:
        started = {tuple(l.split()) for l in open(out + ".started")}
    except OSError:
        pass
    with open(out, "a") as f, open(out + ".started", "a") as st:
        for j in jobs:
            if (j["key"], j["ref"]) in done:
                continue
            if (j["key"], j["ref"]) in started:   # this board took the process down last time (a loader crash)
                f.write(json.dumps({"ok": False, "why": "the board crashed KiCad's loader", "key": j["key"], "ref": j["ref"], "part": j["part"]}) + "\n")
                f.flush()
                continue
            st.write(f"{j['key']} {j['ref']}\n")
            st.flush()
            try:
                r = measure(j)
            except Exception as e:   # one unreadable board must not stop the pass
                r = {"ok": False, "why": f"{type(e).__name__}: {e}"[:200]}
            r.update({"key": j["key"], "ref": j["ref"], "part": j["part"]})
            f.write(json.dumps(r) + "\n"); f.flush()


if __name__ == "__main__":
    main()
