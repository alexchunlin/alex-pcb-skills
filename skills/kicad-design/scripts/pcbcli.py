#!/usr/bin/env python3
"""kicad-cli side of the `pcb` wrapper: erc, drc (plain + packed), netlist, diff, render, svg, stats, fab.

Plain python3 (no pcbnew); measurements that need pcbnew go through pcbq.py under KiCad's Python (KICAD_PY).
Every command writes only under its --out directory (or next to the input when no --out is given) and never
touches the project in place: `drc` works on a temporary mirror of the project directory.
"""
import argparse, csv, hashlib, json, os, re, shutil, subprocess, sys, tempfile, zipfile
import xml.etree.ElementTree as ET
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
KICAD_CLI = os.environ.get("KICAD_CLI", "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
KICAD_PY = os.environ.get("KICAD_PY", "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3")
KICAD_DRUID = os.environ.get("KICAD_DRUID", "/tmp/pcb-ref/kicad-druid")
NOISE = re.compile(r"wxApp|Fontconfig|assert \"\"|memory leak|^\s*$")


def kicad(*args, cwd=None):
    """Run kicad-cli; return (rc, filtered output). kicad-cli exits 0 on most failures, so callers check files."""
    p = subprocess.run([KICAD_CLI, *args], capture_output=True, text=True, cwd=cwd)
    out = "\n".join(l for l in (p.stdout + p.stderr).splitlines() if not NOISE.search(l))
    return p.returncode, out


def kpy_json(board, *args):
    """pcbq.py under KiCad's Python with --json; stdout is the JSON, stderr carries the wx noise."""
    p = subprocess.run([KICAD_PY, "-I", os.path.join(HERE, "pcbq.py"), board, *args, "--json"],
                       capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit("pcbq failed: " + "\n".join(l for l in p.stderr.splitlines() if not NOISE.search(l)))
    return json.loads(p.stdout)


def rel(path):
    r = os.path.relpath(path)
    return path if r.startswith("..") else r


def stem(path):
    return os.path.splitext(os.path.basename(path))[0]


def sibling(path, ext):
    p = os.path.join(os.path.dirname(os.path.abspath(path)), stem(path) + ext)
    return p if os.path.exists(p) else None


def copper_layers(board):
    """Copper layer names in stackup order from the (layers ...) block of a .kicad_pcb."""
    names = []
    with open(board, errors="replace") as f:
        head = f.read(200000)
    m = re.search(r"\(layers\s*\n(.*?)\n\s*\)", head, re.S)
    for mm in re.finditer(r'\(\d+\s+"([A-Za-z0-9_]+\.Cu)"', m.group(1) if m else head):
        names.append(mm.group(1))
    return names


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ----------------------------------------------------------------------------------------------------- erc
def cmd_erc(a):
    out = a.out or sibling_path(a.sch, "-erc.json")
    rc, log = kicad("sch", "erc", "--format", "json", "--severity-all", "-o", out, a.sch)
    if not os.path.exists(out):
        sys.exit(f"erc: no report written (rc {rc}):\n{log}")
    d = json.load(open(out))
    viol = [v for s in d.get("sheets", []) for v in s.get("violations", [])]
    sev = Counter(v["severity"] for v in viol)
    types = Counter((v["severity"], v["type"]) for v in viol)
    print(f"ERC {os.path.basename(a.sch)}: {sev.get('error', 0)} errors, {sev.get('warning', 0)} warnings, "
          f"{sev.get('exclusion', 0)} excluded -> {out}")
    for (s, t), n in sorted(types.items(), key=lambda x: (x[0][0] != "error", -x[1])):
        print(f"  {s:8} {t:28} {n}")
    if a.list:
        for v in viol:
            print(f"  - {v['severity']} {v['type']}: {v['description'][:120]} "
                  f"{[i.get('description', '')[:60] for i in v.get('items', [])]}")
    return 1 if sev.get("error", 0) else 0


def sibling_path(path, suffix):
    return os.path.join(os.path.dirname(os.path.abspath(path)), stem(path) + suffix)


# ----------------------------------------------------------------------------------------------------- drc
# pack constraint kind -> board setup key in <project>.kicad_pro board.design_settings.rules
SETUP_KEY = {
    "clearance": "min_clearance", "track_width": "min_track_width", "hole_clearance": "min_hole_clearance",
    "edge_clearance": "min_copper_edge_clearance", "hole_to_hole": "min_hole_to_hole",
    "silk_clearance": "min_silk_clearance", "text_height": "min_text_height", "text_thickness": "min_text_thickness",
    # via-only setup values: applied to rules that are unconditional or whose condition names a Via
    "via_diameter": "min_via_diameter", "annular_width": "min_via_annular_width", "hole_size": "min_through_hole_diameter",
}
VIA_ONLY = {"via_diameter", "annular_width", "hole_size"}
UNIT = {"mm": 1.0, "mil": 0.0254, "in": 25.4, "": 1.0}
CONSTRAINT_RE = re.compile(r"\(constraint\s+(\w+)\s+\(min\s+([\d.]+)\s*(mm|mil|in)?\)")
SENTINEL = '\n# appended by pcb drc: must fire on every track, or the whole file was rejected (P0-T5)\n' \
           '(rule "pcb-drc-sentinel" (constraint track_width (min 99mm)) (severity warning))\n'


def setup_rules(board):
    pro = sibling(board, ".kicad_pro")
    if not pro:
        return {}, None
    try:
        return json.load(open(pro))["board"]["design_settings"]["rules"], pro
    except (KeyError, ValueError):
        return {}, pro


def resolve_pack(spec, board):
    """--pack FILE | jlcpcb | pcbway | generic (variant by copper count from kicad-druid) | None (project's own)."""
    if spec is None:
        own = sibling(board, ".kicad_dru")
        return own
    if os.path.exists(spec):
        return os.path.abspath(spec)
    fab = {"jlcpcb": "JLCPCB", "pcbway": "PCBWay", "generic": "Generic"}.get(spec.lower())
    if not fab:
        sys.exit(f"drc: pack '{spec}' is neither a file nor one of jlcpcb/pcbway/generic")
    n = len(copper_layers(board))
    variant = {1: "-2L-1oz", 2: "-2L-1oz", 4: "", 6: "-6L-1oz"}.get(n)
    if variant is None:
        sys.exit(f"drc: no kicad-druid {fab} pack for {n} copper layers")
    p = os.path.join(KICAD_DRUID, fab, f"{fab}{variant}.kicad_dru")
    if not os.path.exists(p):
        sys.exit(f"drc: {p} not found (clone kicad-druid to $KICAD_DRUID)")
    return p


def rule_name_at(text, pos):
    m = None
    for m in re.finditer(r'\(rule\s+"([^"]+)"', text[:pos]):
        pass
    return m.group(1) if m else "?"


def condition_at(text, pos):
    """The (condition "...") of the rule enclosing pos, or ''."""
    start = text.rfind("(rule", 0, pos)
    end = text.find("\n(rule", pos)
    body = text[start:end if end > 0 else len(text)]
    m = re.search(r'\(condition\s+"((?:[^"\\]|\\.)*)"', body)
    return m.group(1) if m else ""


def floor_pack(text, setup, do_floor):
    """Compare every (constraint KIND (min X)) with the board setup. Returns (new_text, relaxed, raised)."""
    relaxed, raised = [], []

    def sub(m):
        kind, val, unit = m.group(1), float(m.group(2)), m.group(3) or "mm"
        key = SETUP_KEY.get(kind)
        if not key or key not in setup:
            return m.group(0)
        cond = condition_at(text, m.start())
        if kind in VIA_ONLY and cond and "Via" not in cond:
            return m.group(0)
        mm = val * UNIT[unit]
        if mm + 1e-9 >= setup[key]:
            return m.group(0)
        row = {"rule": rule_name_at(text, m.start()), "constraint": kind, "pack_min_mm": round(mm, 4),
               "setup_min_mm": setup[key], "condition": cond}
        relaxed.append(row)
        if not do_floor:
            return m.group(0)
        raised.append(row)
        return f"(constraint {kind} (min {setup[key]}mm)"
    new = CONSTRAINT_RE.sub(sub, text)
    return new, relaxed, raised


def mirror_project(board, depth=2):
    """Copy the project directory into a temp tree that keeps `depth` ancestor names, with every sibling at each
    level symlinked, so ${KIPRJMOD}/../x and ${KIPRJMOD}/../../x library paths still resolve (P1-T1)."""
    src = os.path.dirname(os.path.abspath(board))
    root = tempfile.mkdtemp(prefix="pcbdrc-")
    cur = root
    chain = []
    d = src
    for _ in range(depth):
        d = os.path.dirname(d)
        chain.append(d)
    chain.reverse()  # outermost first
    for real in chain:
        name = os.path.basename(real) or "root"
        cur = os.path.join(cur, name)
        os.makedirs(cur, exist_ok=True)
        child_on_path = (chain[chain.index(real) + 1] if chain.index(real) + 1 < len(chain) else src)
        for e in os.listdir(real):
            if os.path.join(real, e) == child_on_path:
                continue
            try:
                os.symlink(os.path.join(real, e), os.path.join(cur, e))
            except OSError:
                pass
    dst = os.path.join(cur, os.path.basename(src))
    ignore = shutil.ignore_patterns("*-backups", ".git", "drc", "pcbdrc-*")
    shutil.copytree(src, dst, ignore=ignore, symlinks=True)
    return root, os.path.join(dst, os.path.basename(board))


def drc_counts(path, sentinel=False):
    d = json.load(open(path))
    viol = d.get("violations", [])
    sent = [v for v in viol if v.get("type") == "track_width" and "99." in v.get("description", "")]
    viol = [v for v in viol if v not in sent]
    sev = Counter(v["severity"] for v in viol)
    by_type = {}
    for v in viol:
        by_type.setdefault(v["severity"], Counter())[v["type"]] += 1
    unc = d.get("unconnected_items", [])
    par = d.get("schematic_parity", [])
    keys = {(v["type"], tuple(sorted(i.get("uuid", "") for i in v.get("items", [])))) for v in viol if v["severity"] == "error"}
    return {"errors": sev.get("error", 0), "warnings": sev.get("warning", 0), "excluded": sev.get("exclusion", 0),
            "unconnected": len(unc), "unconnected_errors": sum(1 for u in unc if u.get("severity") == "error"),
            "parity": len(par), "parity_errors": sum(1 for p in par if p.get("severity") == "error"),
            "by_type": {s: dict(c) for s, c in by_type.items()}, "sentinel_hits": len(sent), "file": path}, keys


def cmd_drc(a):
    board = os.path.abspath(a.pcb)
    out = os.path.abspath(a.out or os.path.join(os.path.dirname(board), "drc"))
    os.makedirs(out, exist_ok=True)
    setup, pro = setup_rules(board)
    pack = resolve_pack(a.pack, board)
    parity = not a.no_parity and sibling(board, ".kicad_sch") is not None
    segs = sum(1 for _ in re.finditer(r"\(segment\b", open(board, errors="replace").read()))
    root, b_plain = mirror_project(board)
    result = {"board": board, "project": pro, "pack": pack, "parity": parity, "floor": not a.no_floor,
              "board_segments": segs, "setup": setup}
    try:
        # plain: the project's own board-setup constraints, no custom rule file at all
        own = os.path.join(os.path.dirname(b_plain), stem(board) + ".kicad_dru")
        if os.path.exists(own):
            os.remove(own)
        common = ["pcb", "drc", "--format", "json", "--severity-all"] + (["--schematic-parity"] if parity else [])
        rc, log = kicad(*common, "-o", os.path.join(out, "drc-plain.json"), b_plain)
        if not os.path.exists(os.path.join(out, "drc-plain.json")):
            sys.exit(f"drc: plain run wrote no report (rc {rc}):\n{log}")
        result["plain"], plain_keys = drc_counts(os.path.join(out, "drc-plain.json"))
        if pack:
            text = open(pack).read()
            if not text.lstrip().startswith("(version"):
                sys.exit(f"drc: {pack} does not start with (version 1); KiCad would reject it silently")
            new, relaxed, raised = floor_pack(text, setup, not a.no_floor)
            with open(own, "w") as f:
                f.write(new + SENTINEL)
            shutil.copy(own, os.path.join(out, "pack-used.kicad_dru"))
            rc, log = kicad(*common, "-o", os.path.join(out, "drc-packed.json"), b_plain)
            if not os.path.exists(os.path.join(out, "drc-packed.json")):
                sys.exit(f"drc: packed run wrote no report (rc {rc}):\n{log}")
            result["packed"], packed_keys = drc_counts(os.path.join(out, "drc-packed.json"))
            hits = result["packed"]["sentinel_hits"]
            result["sentinel"] = "fired" if hits else ("untestable: no tracks" if segs == 0 else "NOT FIRED: rule file rejected")
            result["pack_relaxes_setup"] = relaxed
            result["pack_raised_to_setup"] = raised
            result["masked_by_raw_pack"] = sorted(f"{t} {u[0][:8] if u else ''}" for t, u in plain_keys - packed_keys)
            result["fab_only_errors"] = sorted(f"{t} {u[0][:8] if u else ''}" for t, u in packed_keys - plain_keys)
        else:
            result["packed"] = None
            result["sentinel"] = "no pack"
    finally:
        if a.keep:
            result["mirror"] = root
        else:
            shutil.rmtree(root, ignore_errors=True)
    tot_plain = result["plain"]["errors"] + result["plain"]["unconnected_errors"] + result["plain"]["parity_errors"]
    tot_packed = (result["packed"]["errors"] + result["packed"]["unconnected_errors"] + result["packed"]["parity_errors"]) if result["packed"] else None
    rejected = pack and result["sentinel"].startswith("NOT")
    result["exit"] = 2 if rejected else (1 if (tot_plain or tot_packed) else 0)
    result["errors_total"] = max(tot_plain, tot_packed or 0)
    # kicad-cli stops at 199 reports per violation type (P1-T2: Plink sentinel 199 of 1,613 tracks); flag any such count
    capped = sorted({t for tag in ("plain", "packed") for c in [result.get(tag)] if c
                     for s in c["by_type"].values() for t, n in s.items() if n == 199})
    if result["packed"] and result["packed"]["sentinel_hits"] == 199:
        capped.append("track_width(sentinel)")
    result["capped_types"] = capped
    json.dump(result, open(os.path.join(out, "drc.json"), "w"), indent=1)
    # summary
    def line(tag, c):
        return (f"  {tag:7} {c['errors']:4} errors {c['warnings']:4} warnings  unconnected {c['unconnected']}"
                f"  parity {c['parity']}  -> {rel(c['file'])}")
    print(f"DRC {os.path.basename(board)}  parity={'on' if parity else 'off'}  setup={'yes' if setup else 'none'}")
    print(line("plain", result["plain"]) + "   (board setup only)")
    if result["packed"]:
        print(line("packed", result["packed"]) + f"   ({os.path.basename(pack)}, "
              f"{'floored to setup' if not a.no_floor else 'raw'}, sentinel {result['sentinel']} x{result['packed']['sentinel_hits']})")
        relaxed = result["pack_relaxes_setup"]
        if relaxed:
            ex = ", ".join(f"{r['constraint']} {r['pack_min_mm']}<{r['setup_min_mm']}" for r in relaxed[:4])
            print(f"  pack minimums below the board setup: {len(relaxed)} ({ex}{", ..." if len(relaxed) > 4 else ""}) "
                  f"{'raised to the setup value' if not a.no_floor else 'LEFT AS IS: packed count can mask setup errors'}")
        if result["masked_by_raw_pack"]:
            print(f"  plain errors absent from the packed run: {len(result['masked_by_raw_pack'])}")
        if result["fab_only_errors"]:
            print(f"  errors only the pack finds: {len(result['fab_only_errors'])}")
    else:
        print("  packed: no rule pack (pass --pack FILE|jlcpcb|pcbway|generic, or put <name>.kicad_dru next to the board)")
    for tag in ("plain", "packed"):
        c = result.get(tag)
        if c and c["by_type"].get("error"):
            print(f"  {tag} errors by type: " + ", ".join(f"{t} {n}" for t, n in sorted(c["by_type"]["error"].items(), key=lambda x: -x[1])))
    if capped:
        print(f"  counts of 199 are kicad-cli's per-type cap, the true number is higher: {', '.join(capped)} (P1-T2)")
    if rejected:
        print("  RULE PACK REJECTED by KiCad (sentinel did not fire): the packed numbers are meaningless")
    print(f"  errors total {result['errors_total']}  -> {rel(os.path.join(out, 'drc.json'))}")
    return result["exit"]


# ----------------------------------------------------------------------------------------------------- netlist / diff
def export_netlist(sch, out):
    rc, log = kicad("sch", "export", "netlist", "--format", "kicadxml", "-o", out, sch)
    if not os.path.exists(out):
        sys.exit(f"netlist: nothing written (rc {rc}):\n{log}")
    return out


def cmd_netlist(a):
    out = a.out or sibling_path(a.sch, ".xml")
    export_netlist(a.sch, out)
    r = ET.parse(out).getroot()
    nets = r.find("nets")
    comps = r.find("components")
    print(f"netlist {os.path.basename(a.sch)}: {len(nets) if nets is not None else 0} nets, "
          f"{len(comps) if comps is not None else 0} components -> {out}")
    return 0


def nodes(path):
    """Connectivity as {frozenset((ref, pin)): netname}; prior art pace-racer tools/verify_netlist.py (P0-T3)."""
    r = ET.parse(path).getroot()
    out = {}
    for n in r.find("nets"):
        key = frozenset((x.get("ref"), x.get("pin")) for x in n)
        if key:
            out[key] = n.get("name")
    return out


def as_xml(path, tmp):
    if path.endswith(".kicad_sch"):
        out = os.path.join(tmp, stem(path) + "-" + str(abs(hash(path)) % 10000) + ".xml")
        return export_netlist(path, out)
    return path


def cmd_diff(a):
    tmp = tempfile.mkdtemp(prefix="pcbdiff-")
    try:
        A, B = nodes(as_xml(a.a, tmp)), nodes(as_xml(a.b, tmp))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    only_a = sorted(A[k] for k in A if k not in B)
    only_b = sorted(B[k] for k in B if k not in A)
    renamed = sorted((A[k], B[k]) for k in A if k in B and A[k] != B[k])
    changed = bool(only_a or only_b)
    res = {"a": a.a, "b": a.b, "nets_a": len(A), "nets_b": len(B), "changed": changed,
           "only_in_a": only_a, "only_in_b": only_b, "renamed": renamed}
    if a.json:
        json.dump(res, open(a.json, "w"), indent=1)
    if changed:
        print(f"CONNECTIVITY CHANGED: {len(only_a)} nets only in A, {len(only_b)} only in B")
        for n in only_a:
            print(f"  only in A: {n}  {sorted(next(k for k in A if A[k] == n))}")
        for n in only_b:
            print(f"  only in B: {n}  {sorted(next(k for k in B if B[k] == n))}")
        return 1
    print(f"OK: {len(A)} nets, identical connectivity, {len(renamed)} renamed")
    for o, n in renamed:
        print(f"  {o:40} -> {n}")
    return 0


# ----------------------------------------------------------------------------------------------------- render / svg / stats
def cmd_render(a):
    out = a.out or os.path.dirname(os.path.abspath(a.pcb))
    os.makedirs(out, exist_ok=True)
    rc = 0
    for side in a.side.split(","):
        f = os.path.join(out, f"{stem(a.pcb)}_{side}.png")
        kicad("pcb", "render", "--side", side, "--width", str(a.size), "--height", str(a.size), "--zoom", str(a.zoom),
              "--quality", "high", "--background", "opaque", "-o", f, a.pcb)
        ok = os.path.exists(f)
        rc |= 0 if ok else 1
        print(f"render {side}: {'ok' if ok else 'FAILED'} {f}")
    return rc


def cmd_svg(a):
    src = a.src
    out = a.out or os.path.dirname(os.path.abspath(src))
    os.makedirs(out, exist_ok=True)
    if src.endswith(".kicad_sch"):
        rc, log = kicad("sch", "export", "svg", "-o", out, src)
        files = [f for f in os.listdir(out) if f.endswith(".svg")]
        print(f"svg: {len(files)} sheet(s) in {out}")
        return 0 if files else 1
    cu = copper_layers(src)
    sets = {"F": ["F.Cu", "F.SilkS", "F.Mask", "Edge.Cuts"], "B": ["B.Cu", "B.SilkS", "B.Mask", "Edge.Cuts"]}
    for l in cu[1:-1]:
        sets[l.split(".")[0]] = [l, "Edge.Cuts"]
    rc = 0
    for tag, layers in sets.items():
        f = os.path.join(out, f"{stem(src)}_{tag}.svg")
        kicad("pcb", "export", "svg", "--layers", ",".join(layers), "--page-size-mode", "2", "--exclude-drawing-sheet",
              "-o", f, src)
        ok = os.path.exists(f)
        rc |= 0 if ok else 1
        print(f"svg {tag}: {'ok' if ok else 'FAILED'} {f}  layers {','.join(layers)}")
    return rc


def cmd_stats(a):
    tmp = tempfile.mkdtemp(prefix="pcbstats-")
    try:
        f = os.path.join(tmp, "stats.json")
        rc, log = kicad("pcb", "export", "stats", "--format", "json", "--subtract-holes-from-board", "-o", f, a.pcb)
        if not os.path.exists(f):
            sys.exit(f"stats: nothing written:\n{log}")
        d = json.load(open(f))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if a.json:
        json.dump(d, open(a.json, "w"), indent=1)
    if a.raw:
        print(json.dumps(d, indent=1))
        return 0
    cu = copper_layers(a.pcb)
    print(f"stats {os.path.basename(a.pcb)}: {len(cu)} copper layers ({', '.join(cu)})")
    for k, v in d.items():
        if isinstance(v, (int, float, str)):
            print(f"  {k}: {v}")
        elif isinstance(v, dict):
            flat = {kk: vv for kk, vv in v.items() if isinstance(vv, (int, float, str))}
            if flat:
                print(f"  {k}: " + ", ".join(f"{kk} {vv}" for kk, vv in flat.items()))
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            print(f"  {k}: {len(v)} rows")
    return 0


# ----------------------------------------------------------------------------------------------------- fab
def cmd_fab(a):
    board = os.path.abspath(a.pcb)
    name = a.name or stem(board)
    out = os.path.abspath(a.out or os.path.join(os.path.dirname(board), "fab"))
    gd = os.path.join(out, "gerbers")
    if os.path.isdir(gd):
        shutil.rmtree(gd)
    os.makedirs(gd, exist_ok=True)
    cu = copper_layers(board)
    layers = cu + ["F.Paste", "B.Paste", "F.SilkS", "B.SilkS", "F.Mask", "B.Mask", "Edge.Cuts"]
    man = {"board": board, "name": name, "copper_layers": cu, "layers": layers, "files": {}, "notes": []}
    # gerbers: explicit layer list, never --board-plot-params (R1-S1-F3: stored plot params put drill-mark flashes on copper)
    rc, log = kicad("pcb", "export", "gerbers", "--layers", ",".join(layers), "--subtract-soldermask", "-o", gd + "/", board)
    rc, log2 = kicad("pcb", "export", "drill", "--format", "excellon", "--excellon-units", "mm", "--generate-map",
                     "--map-format", "gerberx2", "-o", gd + "/", board)
    gfiles = sorted(os.listdir(gd))
    if len([f for f in gfiles if not f.endswith((".drl", ".gbrjob")) and "drl_map" not in f]) < len(layers):
        sys.exit(f"fab: expected {len(layers)} gerber layers, got {gfiles}\n{log}\n{log2}")
    zpath = os.path.join(out, f"{name}_gerbers.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in gfiles:
            z.write(os.path.join(gd, f), f)
    man["files"]["gerbers"] = {f: sha256(os.path.join(gd, f)) for f in gfiles}
    man["files"]["zip"] = zpath
    # footprint data from pcbnew: fields, DNP/exclusion flags, origin vs fab-outline centre (R1-S1-F4)
    fd = kpy_json(board, "fabdata")
    rows = [r for r in fd["footprints"] if not r["dnp"] and not r["exclude_bom"]]
    # JLC BOM: Comment, Designator, Footprint, LCSC Part #; grouped by (value, lcsc, footprint)
    groups = {}
    for r in rows:
        key = (r["value"], r["lcsc"], r["footprint"])
        groups.setdefault(key, []).append(r["ref"])
    missing = sorted(r["ref"] for r in rows if not r["lcsc"])
    bom_full = os.path.join(out, f"{name}_bom.csv")
    with open(bom_full, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designators", "Qty", "Value", "Footprint", "Manufacturer", "MPN", "LCSC", "Datasheet"])
        for (val, lcsc, fp), refs in sorted(groups.items(), key=lambda kv: kv[1][0]):
            r0 = next(r for r in rows if r["ref"] == refs[0])
            w.writerow([",".join(refs), len(refs), val, fp, r0["manufacturer"], r0["mpn"], lcsc, r0["datasheet"]])
    bom_jlc = os.path.join(out, f"{name}_bom_jlcpcb.csv")
    with open(bom_jlc, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (val, lcsc, fp), refs in sorted(groups.items(), key=lambda kv: kv[1][0]):
            if lcsc:
                w.writerow([val, ",".join(refs), fp.split(":")[-1], lcsc])
    # CPL: Designator, Mid X, Mid Y, Layer, Rotation, from the KiCad position export (board origin, mm, DNP excluded)
    pos_raw = os.path.join(out, f"{name}_pos_kicad.csv")
    kicad("pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both", "--exclude-dnp", "-o", pos_raw, board)
    if not os.path.exists(pos_raw):
        sys.exit("fab: position export failed")
    cpl = os.path.join(out, f"{name}_cpl_jlcpcb.csv")
    n_cpl = 0
    with open(pos_raw, newline="") as f, open(cpl, "w", newline="") as g:
        w = csv.writer(g)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for row in csv.DictReader(f):
            w.writerow([row["Ref"], f"{float(row['PosX']):.4f}mm", f"{float(row['PosY']):.4f}mm",
                        "Top" if row["Side"] == "top" else "Bottom", f"{float(row['Rot']):.1f}"])
            n_cpl += 1
    offsets = {r["ref"]: r["origin_to_fab_centre_mm"] for r in fd["footprints"]
               if r["origin_to_fab_centre_mm"] is not None and r["origin_to_fab_centre_mm"] > 0.1 and not r["dnp"]}
    # renders
    for side in ("top", "bottom"):
        kicad("pcb", "render", "--side", side, "--width", "1400", "--height", "1400", "--zoom", "0.9", "--quality", "high",
              "--background", "opaque", "-o", os.path.join(out, f"{name}_{side}.png"), board)
    man["files"].update({"bom": bom_full, "bom_jlcpcb": bom_jlc, "cpl_jlcpcb": cpl, "pos_kicad": pos_raw,
                         "renders": [os.path.join(out, f"{name}_{s}.png") for s in ("top", "bottom")]})
    man["hashes"] = {os.path.basename(p): sha256(p) for p in (bom_full, bom_jlc, cpl)}
    man["bom_lines"] = len(groups)
    man["bom_missing_lcsc"] = missing
    man["cpl_lines"] = n_cpl
    man["cpl_origin_offsets_mm"] = offsets
    man["dnp"] = sorted(r["ref"] for r in fd["footprints"] if r["dnp"])
    if offsets:
        man["notes"].append("CPL Mid X/Y is the KiCad footprint origin; for these parts it sits away from the fab-outline "
                            "centre, so check JLC's preview or re-origin the footprint (R1-S1-F4)")
    json.dump(man, open(os.path.join(out, "fab.json"), "w"), indent=1)
    print(f"fab {name}: {len(gfiles)} files in {rel(zpath)}; BOM {len(groups)} lines "
          f"({len(missing)} without LCSC{': ' + ','.join(missing) if missing else ''}); CPL {n_cpl} parts; "
          f"DNP {','.join(man['dnp']) or 'none'}")
    if offsets:
        print("  CPL origin vs fab-outline centre > 0.1 mm: " + ", ".join(f"{k} {v:.2f}" for k, v in sorted(offsets.items())))
    print(f"  manifest {rel(os.path.join(out, 'fab.json'))}")
    return 0


# ----------------------------------------------------------------------------------------------------- main
def main(argv):
    p = argparse.ArgumentParser(prog="pcb")
    sp = p.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("erc"); s.add_argument("sch"); s.add_argument("--out"); s.add_argument("--list", action="store_true")
    s = sp.add_parser("drc"); s.add_argument("pcb"); s.add_argument("--pack"); s.add_argument("--out")
    s.add_argument("--no-parity", action="store_true"); s.add_argument("--no-floor", action="store_true")
    s.add_argument("--keep", action="store_true")
    s = sp.add_parser("netlist"); s.add_argument("sch"); s.add_argument("out", nargs="?")
    s = sp.add_parser("diff"); s.add_argument("a"); s.add_argument("b"); s.add_argument("--json")
    s = sp.add_parser("render"); s.add_argument("pcb"); s.add_argument("--out"); s.add_argument("--side", default="top,bottom")
    s.add_argument("--size", type=int, default=1400); s.add_argument("--zoom", default="0.9")
    s = sp.add_parser("svg"); s.add_argument("src"); s.add_argument("--out")
    s = sp.add_parser("stats"); s.add_argument("pcb"); s.add_argument("--json"); s.add_argument("--raw", action="store_true")
    s = sp.add_parser("fab"); s.add_argument("pcb"); s.add_argument("--out"); s.add_argument("--name")
    a = p.parse_args(argv)
    if not os.path.exists(KICAD_CLI):
        sys.exit(f"kicad-cli not found at {KICAD_CLI} (set KICAD_CLI)")
    return globals()["cmd_" + a.cmd](a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
