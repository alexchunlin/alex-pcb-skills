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

  pcb py tools/corpus/boardmeasure.py --roles JOBS.json OUT.jsonl

Spike 5, role-keyed: JOBS [{key, ref, part, cls, fmt: kicad|eagle, board, rx, pin_names?, ...}]. Each IC pad gets a role from its
pin name (`pinfunction`/`pintype` on KiCad 6+ boards, the job's `pin_names`, read from the Eagle .sch, otherwise), so nothing is
keyed by pin number and one cap on VDD and VDDIO counts once, at the nearer pin. Per job, one line: `pkg` (a key from the pad
extent, the perimeter pad count and a thermal pad found by size), `tht` (through-hole, so a module or a DIP, not an SMD package),
`pad1` (pad 1 in the canonical frame) and `rows` [{role, pin, ref, value, d_pad, du, dv, ang, cx, cy, rot, back}], the nearest
satellite per (role, pin): `d_pad` pad to pad, (du, dv) its centre in the pin's frame (u out of the package at the pin, v a
quarter turn on), `ang` the direction of its pin-side pad from u, degrees, (cx, cy, rot) centre and rotation in the canonical frame.
Canonical frame: `frame()` undoes rotation and mirror, the origin moves to the pad extent's centre, and a quarter turn puts the
outward normal at pad 1 on -x (pad 1 at top left, numbering downward), because `frame()` alone leaves each library's zero
orientation (HTSSOP-16 is a quarter turn apart between Adafruit's Eagle library and KiCad's). Eagle jobs load with the format
passed (one-argument LoadBoard returns None on .brd), are measured in-process and never saved (127 of 146 conversions do not
reload), and go through a net guard against `contactref` (one board in 146 shifts its net names on import).
"""
import json, math, os, re, sys

import pcbnew

ToMM = pcbnew.ToMM
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


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


SUPPLY = {"imu6": re.compile(r"^(VDD[AD]?(_?IO)?\d?|VCC(IO)?\d?|VLOGIC|VIO|AVDD|DVDD|VDDH)$")}
MOTOR = re.compile(r"^(VM\d?|VMA|VMB|VMOT(OR)?|VBB\d?|VS\d?|VSA|VSB|VPWR|PVDD|PVCC|VP|VIN)$")
LOGIC = re.compile(r"^(VCC\d?|VDD\d?|VIO|V3P3(OUT)?|VINT|VREG|DVDD)$")
FLY = re.compile(r"^(CPH|CPL|CP\d|CPA|CPB|C[12][HL+-])$")
VCP = re.compile(r"^(VCP|CPOUT|VGD|VCPOUT)$")
MIRROR = re.compile(r"^(IPROPI?\d?|IPROP[AB12]|ISOA|ISOUT|IMON\d?)$")
LIMIT = re.compile(r"^(ILIM|VREF\d?|ISET|IREF|RCL)$")
SHUNT = re.compile(r"^(A?B?ISENS?E?[AB12]?|[AB]ISEN|SENS?E?[AB12]?|RSENS?E?[AB12]?|LSS[AB12]?|RS[AB12]?|AISEN|BISEN)$")


def pin_role(cls, name):
    if cls == "imu6":
        return "supply" if SUPPLY["imu6"].match(name) else None
    if MOTOR.match(name):
        return "vm"
    if LOGIC.match(name):
        return "vcc"
    if FLY.match(name):
        return "cp_fly"
    if VCP.match(name):
        return "cp_res"
    if MIRROR.match(name):
        return "current_mirror"
    if LIMIT.match(name):
        return "limit_setting"
    if SHUNT.match(name):
        return "shunt"
    return None


def clean_pin(s):
    s = re.sub(r"[~{}!/ ]", "", s or "").upper()
    return re.sub(r"_(\d+)$", "", re.sub(r"@\d+$", "", s))


def canon_turn(pad1, size1, ex, ey):
    """Quarter turns k (each (x, y) -> (-y, x)) that put pad 1 on the left edge, its outward normal on -x: the IC convention of pad 1
    at top left, numbering downward. Unique on every package with an edge pad 1, near-square two-row packages included."""
    u = pin_uv(pad1[0], pad1[1], size1[0], size1[1], ex, ey)
    for k in range(4):
        if rotk(u[0], u[1], k) == (-1, 0):
            return k
    return 0


def rotk(x, y, k):
    for _ in range(k):
        x, y = -y, x
    return x, y


def pin_uv(px, py, sx, sy, ex, ey):
    """Unit outward normal at a pad at (px, py) in the centred canonical frame: along the pad's long side, else to the nearest side."""
    if sx > sy * 1.15:
        return (1 if px > 0 else -1, 0)
    if sy > sx * 1.15:
        return (0, 1 if py > 0 else -1)
    return (1 if px > 0 else -1, 0) if ex - abs(px) <= ey - abs(py) else (0, 1 if py > 0 else -1)


def package_key(pts, areas, n_tht):
    """(key, extent, thermal pad?): perimeter pads and the pad extent rounded to 0.5 mm. Pad count alone misleads: thermal-via pads
    (DRV8871 HSOP-8 imports with 13) sit inside the extent, so they do not count, and a pad far bigger than the median is the thermal pad."""
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    med = sorted(areas)[len(areas) // 2]
    ex, ey = w / 2, h / 2
    mx, my = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    perim = sum(1 for x, y in pts if abs(abs(x - mx) - ex) < 0.2 or abs(abs(y - my) - ey) < 0.2)
    ep = any(a > 6 * med for a in areas)
    w, h = max(w, h), min(w, h)
    return f"{perim}p-{round(w * 2) / 2:.1f}x{round(h * 2) / 2:.1f}{'-ep' if ep else ''}", (round(w, 2), round(h, 2)), ep


def net_guard(job, fp_by_ref):
    """Share of Eagle `contactref` pads whose imported net differs, overbars normalised."""
    import eagle
    els, cref = eagle.elements(job["board"])
    bad = tot = 0
    for (el, pad), sig in cref.items():
        f = fp_by_ref.get(el)
        if f is None:
            continue
        for p in f.Pads():
            if p.GetNumber() == pad:
                tot += 1
                bad += eagle.norm(p.GetNetname()) != eagle.norm(sig)
                break
    return bad, tot


def load(job):
    if job.get("fmt") == "eagle":
        return pcbnew.LoadBoard(job["board"], pcbnew.PCB_IO_MGR.EAGLE)
    return pcbnew.LoadBoard(job["board"])


def measure_roles(job, b=None):
    from pcbrefstat import parse_value
    b = b or load(job)
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    ic = fps.get(job["ref"])
    rx = re.compile(job["rx"], re.I)
    if ic is None or not (rx.search(ic.GetValue()) or rx.search(str(ic.GetFPID().GetLibItemName()))):
        cand = [f for f in b.GetFootprints() if rx.search(f.GetValue())]
        if len(cand) != 1:
            return {"ok": False, "why": f"ref {job['ref']} not the part on the board; {len(cand)} value matches"}
        ic = cand[0]
    if job.get("fmt") == "eagle":
        bad, tot = net_guard(job, fps)
        if tot and bad / tot > 0.02:
            return {"ok": False, "why": f"net guard: {bad} of {tot} pads differ from contactref"}
    m = frame(ic)
    flipped = ic.IsFlipped()
    pos = ic.GetPosition()
    pads = list(ic.Pads())
    if len(pads) < 3:
        return {"ok": False, "why": "fewer than 3 pads"}
    raw = {id(p): to_local(m, ToMM(p.GetPosition().x - pos.x), ToMM(p.GetPosition().y - pos.y)) for p in pads}
    pts = list(raw.values())
    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
    mx, my = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    p1 = next((p for p in pads if p.GetNumber() in ("1", "A1", "P$1", "P1")), None)
    if p1 is None:
        return {"ok": False, "why": "no pad 1"}
    c0 = {i: (q[0] - mx, q[1] - my) for i, q in raw.items()}
    qr = abs(ic.GetOrientationDegrees() % 90) < 1e-3
    swap0 = qr and abs(ic.GetOrientationDegrees() % 180 - 90) < 1e-3

    def local_size(p):
        """The pad's sides in the library frame: the bounding box is the board's, so a quarter-turned part swaps them."""
        bb = p.GetBoundingBox()
        w, h = ToMM(bb.GetWidth()), ToMM(bb.GetHeight())
        return (h, w) if swap0 else (w, h)

    hx, hy = (max(xs) - min(xs)) / 2, (max(ys) - min(ys)) / 2
    pad1_central = abs(c0[id(p1)][0]) < 0.25 * hx and abs(c0[id(p1)][1]) < 0.25 * hy    # a library that numbers the thermal pad 1
    k = 0 if pad1_central else canon_turn(c0[id(p1)], local_size(p1), hx, hy)
    canon = {i: rotk(q[0], q[1], k) for i, q in c0.items()}

    def to_canon(pt):
        x, y = to_local(m, ToMM(pt.x - pos.x), ToMM(pt.y - pos.y))
        return rotk(x - mx, y - my, k)

    areas, tht = [], 0
    for p in pads:
        s = p.GetSize(pcbnew.F_Cu) if hasattr(p, "GetSize") else None
        areas.append(ToMM(s.x) * ToMM(s.y))
        tht += p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
    key, ext, ep = package_key(list(canon.values()), areas, tht)
    cxs, cys = [q[0] for q in canon.values()], [q[1] for q in canon.values()]
    cx_half, cy_half = (max(cxs) - min(cxs)) / 2, (max(cys) - min(cys)) / 2
    names = job.get("pin_names") or {}
    roles = {}
    no_fn = 0
    for p in pads:
        net = p.GetNetname()
        if not net or gnd_like(net):
            continue
        nm = clean_pin(names.get(p.GetNumber()) or p.GetPinFunction())
        if not nm:
            no_fn += 1
        r = pin_role(job["cls"], nm)
        if r is None and p.GetPinType() == "power_in":
            r = "supply" if job["cls"] == "imu6" else "vcc"
        if r:
            roles[id(p)] = (r, nm or "#" + p.GetNumber())
    rows = {}
    others = [(f, list(f.Pads())) for f in b.GetFootprints() if f is not ic]
    units = []
    for p in pads:
        if id(p) not in roles:
            continue
        role, nm = roles[id(p)]
        net = p.GetNetname()
        pc = canon[id(p)]
        sx, sy = local_size(p) if qr else (1, 1)
        if k % 2:
            sx, sy = sy, sx
        u = pin_uv(pc[0], pc[1], sx, sy, cx_half, cy_half)
        v = (-u[1], u[0])
        for f, fp in others:
            on = [q for q in fp if q.GetNetname() == net]
            if not on or len(fp) != 2:
                continue
            q = min(on, key=lambda q: math.hypot(ToMM(q.GetPosition().x - p.GetPosition().x), ToMM(q.GetPosition().y - p.GetPosition().y)))
            d = math.hypot(ToMM(q.GetPosition().x - p.GetPosition().x), ToMM(q.GetPosition().y - p.GetPosition().y))
            far = fp[0] if fp[1] is q else fp[1]
            ref = f.GetReference()
            kind = ref[:1].upper()
            val = f.GetValue()
            sat_role = None
            other_gnd = gnd_like(far.GetNetname())
            if kind == "C":
                cv = parse_value(val)
                if cv is not None and cv >= 1e-3:   # a bare "0.1" or "10" on a cap is in uF
                    cv *= 1e-6
                if role in ("supply", "vm", "vcc"):
                    if other_gnd and cv is not None:
                        band = "bulk" if cv >= 0.95e-6 else "bypass"
                        sat_role = {"supply": band, "vm": "vm_" + band, "vcc": "vcc_" + band}[role]
                elif role == "cp_fly" and FLY.match(clean_pin(far_pin_name(ic, far, names)) or ""):
                    sat_role = "cp_fly"
                elif role == "cp_res" and not other_gnd:
                    sat_role = "cp_res"
                elif role == "cp_res" and other_gnd:
                    sat_role = "cp_res_gnd"
            elif kind == "R" and other_gnd and role in ("current_mirror", "limit_setting", "shunt"):
                sat_role = role
            if sat_role is None:
                continue
            c = to_canon(f.GetPosition())
            off = (c[0] - pc[0], c[1] - pc[1])
            a, bq = to_canon(q.GetPosition()), to_canon(far.GetPosition())
            vec = (a[0] - bq[0], a[1] - bq[1])
            ang = math.degrees(math.atan2(vec[0] * v[0] + vec[1] * v[1], vec[0] * u[0] + vec[1] * u[1]))
            rot = (f.GetOrientationDegrees() - ic.GetOrientationDegrees()) * (-1 if flipped else 1) + 90 * k
            units.append({"role": sat_role, "pin": nm, "ref": ref, "value": val[:24], "d_pad": round(d, 3), "du": round(off[0] * u[0] + off[1] * u[1], 3),
                          "dv": round(off[0] * v[0] + off[1] * v[1], 3), "ang": round(ang % 360, 1), "cx": round(c[0], 3), "cy": round(c[1], 3),
                          "rot": round(rot % 180, 1), "back": f.IsFlipped() != flipped})
    # the nearest satellite per (role, pin); a cap that serves two pins counts once, at the nearer
    units.sort(key=lambda r: r["d_pad"])
    seen_ref, seen_key = set(), set()
    out = []
    for r in units:
        if (r["role"], r["pin"]) in seen_key or (r["role"], r["ref"]) in seen_ref:
            continue
        seen_key.add((r["role"], r["pin"]))
        seen_ref.add((r["role"], r["ref"]))
        out.append(r)
    return {"ok": True, "ic_ref": ic.GetReference(), "ic_fpid": str(ic.GetFPID().GetLibItemName())[:60], "pkg": key, "ext": ext, "ep": ep, "n_pads": len(pads), "tht": tht,
            "turn": k, "pad1": [round(x, 2) for x in canon[id(p1)]], "pad1_central": pad1_central, "flipped": flipped, "rows": out, "roles_seen": sorted({v[0] for v in roles.values()}),
            "no_pin_name": no_fn, "n_footprints": len(fps)}


def far_pin_name(ic, far, names):
    """The IC pin on the satellite's other pad, if it lands on the IC."""
    for p in ic.Pads():
        if p.GetNetname() == far.GetNetname():
            return names.get(p.GetNumber()) or p.GetPinFunction()
    return ""


def main_roles(argv):
    jobs = json.load(open(argv[0]))
    out = argv[1]
    done, started = set(), set()
    try:
        done = {(x["key"], x["ref"]) for x in map(json.loads, open(out))}
    except OSError:
        pass
    try:
        started = {tuple(l.rstrip("\n").split("\t")) for l in open(out + ".started")}
    except OSError:
        pass
    # one board can serve several jobs, in-process: a conversion is never cached on disk, only this load
    cur, bd = None, None
    with open(out, "a") as f, open(out + ".started", "a") as st:
        for j in jobs:
            k = (j["key"], j["ref"])
            if k in done:
                continue
            base = {x: j.get(x) for x in ("key", "ref", "part", "cls", "repo", "path", "org", "fmt", "value", "licence", "sch_version")}
            if k in started:
                f.write(json.dumps({"ok": False, "why": "the board crashed KiCad's loader", **base}) + "\n"); f.flush()
                continue
            st.write(f"{j['key']}\t{j['ref']}\n"); st.flush()
            try:
                if j["board"] != cur:
                    cur, bd = j["board"], load(j)
                r = measure_roles(j, bd)
            except Exception as e:   # one unreadable board must not stop the pass
                r = {"ok": False, "why": f"{type(e).__name__}: {e}"[:200]}
            f.write(json.dumps({**r, **base}) + "\n"); f.flush()


def main():
    if sys.argv[1] == "--roles":
        return main_roles(sys.argv[2:])
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
