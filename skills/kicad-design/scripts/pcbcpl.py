"""pcb cpl BOARD [--json F] [--cache DIR] [--offline]
JLC places a part by the EasyEDA footprint of its LCSC number, not by the KiCad footprint, so a KiCad rotation can be wrong
in the CPL with every check clean (spike #6: wrong on 3 of 3 boards examined). For each placed part with an LCSC field this
aligns the KiCad pads with the EasyEDA pads (vendored kicad-jlcpcb-tools `jlcfootprint`, closed-form rigid fit, pads paired
by number) and reports the correction that goes on the CPL. `pcb fab` applies the corrections it trusts and lists the rest.

status: ok         fit good, correction trusted
        symmetric  non-polar two-pad part: any half turn is the same part, correction 0
        check      a person looks at JLC's preview: polar two-pad part (pad numbers do not say which end is which), mirrored
                   or poor fit, or too few pads in common
        missing    no EasyEDA footprint for this LCSC number
Answers are cached per part in ~/.cache/pcb-easyeda, because a footprint for a part number rarely changes and the host refuses
bursts. Run under plain python3; nothing here needs pcbnew.
"""
import json, os, re, sys, time, urllib.request
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
from jlcfootprint import boardfile, easyeda_parse, geometry, naming, solver  # noqa: E402

DEVICES = "https://pro.easyeda.com/api/devices/searchByCodes"
COMPONENT = "https://pro.easyeda.com/api/components/{}"
COMPANY = "0819f05c4eef4c71ace90d822a990e87"   # EasyEDA's path for the LCSC library, as the plugin asks
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
           "Accept": "application/json, text/plain, */*", "Content-Type": "application/json"}
NONPOLAR = re.compile(r"^(R|C|L|FB|F)\d")
MAX_RESIDUAL_MM = 0.4


def get(url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def fetch(codes, cache, offline=False):
    """{lcsc: {"package", "pads"} or None}: EasyEDA's footprint per part, cached. Pro host: one batch lookup, one call per footprint."""
    os.makedirs(cache, exist_ok=True)
    out, need = {}, []
    for c in codes:
        p = os.path.join(cache, c + ".json")
        if os.path.exists(p):
            out[c] = json.load(open(p))
        else:
            need.append(c)
    if not need or offline:
        return {**out, **{c: None for c in need}}
    for i in range(0, len(need), 200):
        chunk = need[i:i + 200]
        res = easyeda_parse.parse_devices_response(get(DEVICES, {"codes": chunk, "path": COMPANY}), chunk)
        for c in chunk:
            hit = res.hits.get(c)
            rec = None
            if hit and hit.puuid:
                time.sleep(0.5)
                fp = easyeda_parse.parse_puuid_response(get(COMPONENT.format(hit.puuid)), hit.puuid)
                if fp.status == "ok" and fp.pads:
                    rec = {"package": hit.package_name or fp.package_name, "pads": fp.pads, "fetched": time.strftime("%Y-%m-%d")}
                    json.dump(rec, open(os.path.join(cache, c + ".json"), "w"))
            out[c] = rec
    return out


def judge(fp, rec):
    """One part: the correction on the CPL and how far to trust it."""
    r = {"ref": fp.reference, "lcsc": fp.lcsc, "kicad_rot": fp.placed_rotation, "side": "bottom" if fp.is_bottom else "top"}
    if rec is None:
        return {**r, "status": "missing", "correction": 0, "why": "no EasyEDA footprint"}
    r["package"] = rec.get("package", "")
    ki = boardfile.footprint_pads(fp)
    if fp.is_bottom:
        ki = geometry.mirror_y(ki)
    jl = geometry.easyeda_pads_to_mm(rec["pads"])
    a = {geometry.normal_number(p.number): (p.x, p.y) for p in geometry.named_pads(ki)}
    b = {geometry.normal_number(p.number): (p.x, p.y) for p in geometry.named_pads(jl)}
    two = len(a) <= 2 and len(b) <= 2
    if two and NONPOLAR.match(fp.reference):
        return {**r, "status": "symmetric", "correction": 0, "why": "non-polar two-pad part"}
    t = solver.solve_transform(a, b)
    corr = geometry.ccw_correction(t.rotation_deg)
    r.update(correction=corr, fit_mm=round(t.residual, 3), paired=t.matched_pad_count,
             offset_mm=[round(t.offset_x, 3), round(t.offset_y, 3)])
    if t.quality_flag != "ok":
        return {**r, "status": "check", "why": t.quality_flag}
    if t.residual > MAX_RESIDUAL_MM:
        return {**r, "status": "check", "why": f"pads fit to {t.residual:.2f} mm only"}
    if two:
        return {**r, "status": "check", "why": "polar two-pad part: pad numbers do not prove polarity, look at the preview"}
    return {**r, "status": "ok"}


def run(board, cache=None, offline=False):
    cache = cache or os.path.expanduser("~/.cache/pcb-easyeda")
    fps = [f for f in boardfile.parse_kicad_pcb_text(open(board, errors="ignore").read()) if f.lcsc and re.match(r"^C\d+$", f.lcsc)]
    recs = fetch(sorted({f.lcsc for f in fps}), cache, offline)
    return [judge(f, recs.get(f.lcsc)) for f in sorted(fps, key=lambda f: f.reference)]


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        sys.exit(__doc__)
    def opt(n):
        if n in a:
            i = a.index(n); a.pop(i)
            return a.pop(i)
    js, cache = opt("--json"), opt("--cache")
    offline = "--offline" in a
    rows = run([x for x in a if not x.startswith("--")][0], cache, offline)
    if js:
        json.dump(rows, open(js, "w"), indent=1)
    for r in rows:
        if r["status"] != "symmetric":
            print(f"  {r['ref']:6} {r['lcsc']:11} {r['status']:8} corr {r['correction']:3} fit {r.get('fit_mm', '-')} {r.get('package', '')[:34]} {r.get('why', '')}")
    bad = [r["ref"] for r in rows if r["status"] in ("check", "missing")]
    moved = [r["ref"] for r in rows if r["status"] == "ok" and r["correction"]]
    print(f"PCBCPL {len(rows)} parts: {sum(r['status'] == 'ok' for r in rows)} ok, {sum(r['status'] == 'symmetric' for r in rows)} symmetric, {len(moved)} corrected ({', '.join(moved)}); "
          f"{len(bad)} for a person at JLC's preview ({', '.join(bad)})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
