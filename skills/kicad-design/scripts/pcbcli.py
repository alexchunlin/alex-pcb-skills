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


DATE_LINE = re.compile(rb"CreationDate|DRILL file .* date |G04 Created by KiCad .* date ")


def sha256(path):
    """sha256 of the file with its timestamp lines dropped (gerber %TF.CreationDate, drill '; ... date', gbrjob
    "CreationDate"), so two regenerations of the same board hash the same (P1-T9)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        data = f.read()
    if path.endswith((".png", ".zip")):
        h.update(data)
    else:
        for line in data.splitlines(True):
            if not DATE_LINE.search(line):
                h.update(line)
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
    # renders (18 of fab's 21 s; --no-render for regen-check and other comparisons)
    for side in (() if a.no_render else ("top", "bottom")):
        kicad("pcb", "render", "--side", side, "--width", "1400", "--height", "1400", "--zoom", "0.9", "--quality", "high",
              "--background", "opaque", "-o", os.path.join(out, f"{name}_{side}.png"), board)
    man["files"].update({"bom": bom_full, "bom_jlcpcb": bom_jlc, "cpl_jlcpcb": cpl, "pos_kicad": pos_raw,
                         "renders": [] if a.no_render else [os.path.join(out, f"{name}_{s}.png") for s in ("top", "bottom")]})
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


# ----------------------------------------------------------------------------------------------------- regen-check
def self_cmd(*args):
    p = subprocess.run([sys.executable, "-I", os.path.abspath(__file__), *args], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def gui_pids():
    p = subprocess.run(["pgrep", "-fl", r"MacOS/(pcbnew|eeschema|kicad)$"], capture_output=True, text=True)
    return [l for l in p.stdout.splitlines() if l.strip()]


def measure_tree(root, cfg, out):
    """Netlist nodes, DRC counts, fab hashes and placement of the project under root. Missing files are reported,
    not fatal: a regeneration that produced nothing is the finding."""
    os.makedirs(out, exist_ok=True)
    m = {"root": root, "missing": []}
    board = os.path.join(root, cfg["board"])
    sch = os.path.join(root, cfg["sch"]) if cfg.get("sch") else sibling(board, ".kicad_sch")
    if sch and os.path.exists(sch):
        try:
            xml = export_netlist(sch, os.path.join(out, "netlist.xml"))
            m["nets"] = {",".join(sorted(f"{r}.{p}" for r, p in k)): v for k, v in nodes(xml).items()}
        except SystemExit as e:
            m["missing"].append(f"netlist: {e}")
    else:
        m["missing"].append("schematic")
    if os.path.exists(board):
        rc, log = self_cmd("drc", board, "--out", os.path.join(out, "drc"), *(["--pack", cfg["pack"]] if cfg.get("pack") else []))
        try:
            d = json.load(open(os.path.join(out, "drc", "drc.json")))
            m["drc"] = {"plain_errors": d["plain"]["errors"], "plain_warnings": d["plain"]["warnings"],
                        "packed_errors": d["packed"]["errors"] if d["packed"] else None,
                        "packed_warnings": d["packed"]["warnings"] if d["packed"] else None,
                        "unconnected": d["plain"]["unconnected"], "sentinel": d["sentinel"],
                        "plain_by_type": d["plain"]["by_type"], "exit": d["exit"]}
        except (OSError, ValueError, KeyError):
            m["missing"].append(f"drc: {log[-300:]}")
        rc, log = self_cmd("fab", board, "--out", os.path.join(out, "fab"), "--no-render")
        try:
            f = json.load(open(os.path.join(out, "fab", "fab.json")))
            m["fab"] = {"gerbers": f["files"]["gerbers"], "csv": f["hashes"], "bom_lines": f["bom_lines"],
                        "missing_lcsc": f["bom_missing_lcsc"], "cpl_lines": f["cpl_lines"]}
        except (OSError, ValueError, KeyError):
            m["missing"].append(f"fab: {log[-300:]}")
        try:
            fps = kpy_json(board, "fps")["footprints"]
            m["placement"] = {r["ref"]: [r["pos"], r["rot"], r["layer"]] for r in fps}
            nets = kpy_json(board, "nets")["nets"]
            m["copper"] = {n["net"]: [n["length_mm"], n["vias"], n["min_width_mm"]] for n in nets}
        except SystemExit as e:
            m["missing"].append(f"pcbq: {e}")
    else:
        m["missing"].append("board")
    return m


def compare(a, b):
    """What differs between two measure_tree results; empty list = identical in every measured respect."""
    diffs = []
    for key in ("nets", "placement", "copper"):
        if key in a and key in b:
            ka, kb = set(a[key]), set(b[key])
            if key == "nets":
                if ka != kb:
                    diffs.append(f"{key}: {len(ka - kb)} only in first, {len(kb - ka)} only in second")
            else:
                ch = [k for k in ka & kb if a[key][k] != b[key][k]]
                if ka != kb or ch:
                    diffs.append(f"{key}: {len(ka ^ kb)} items added/removed, {len(ch)} changed ({', '.join(sorted(ch)[:6])})")
        elif (key in a) != (key in b):
            diffs.append(f"{key}: present in only one")
    if "drc" in a and "drc" in b:
        for k in ("plain_errors", "plain_warnings", "packed_errors", "packed_warnings", "unconnected"):
            if a["drc"][k] != b["drc"][k]:
                diffs.append(f"drc {k}: {a['drc'][k]} vs {b['drc'][k]}")
    elif (("drc" in a) != ("drc" in b)):
        diffs.append("drc: present in only one")
    if "fab" in a and "fab" in b:
        ga, gb = a["fab"]["gerbers"], b["fab"]["gerbers"]
        bad = sorted(f for f in set(ga) | set(gb) if ga.get(f) != gb.get(f))
        if bad:
            diffs.append(f"fab gerbers differ: {', '.join(bad)}")
        bad = sorted(f for f in set(a["fab"]["csv"]) | set(b["fab"]["csv"]) if a["fab"]["csv"].get(f) != b["fab"]["csv"].get(f))
        if bad:
            diffs.append(f"fab csv differ: {', '.join(bad)}")
    elif (("fab" in a) != ("fab" in b)):
        diffs.append("fab: present in only one")
    return diffs


def cmd_regen_check(a):
    """Code is the source of truth only if the project regenerates from a clean tree (R1-Z1-F2): copy the project,
    delete its generated outputs, run its regeneration command twice, and compare netlist, DRC, fab package and
    placement against the tree as handed in and between the two passes."""
    proj = os.path.abspath(a.project)
    cfg = {}
    cfg_path = os.path.join(proj, "regen.json")
    if os.path.exists(cfg_path):
        cfg = json.load(open(cfg_path))
    for k in ("cmd", "board", "sch", "pack"):
        if getattr(a, k, None):
            cfg[k] = getattr(a, k)
    if a.generated:
        cfg["generated"] = a.generated
    for k in ("cmd", "board"):
        if not cfg.get(k):
            sys.exit(f"regen-check: --{k} is required (or put it in {cfg_path})")
    cfg.setdefault("generated", [])
    out = os.path.abspath(a.out or os.path.join(proj, "regen-check"))
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    res = {"project": proj, "config": cfg, "out": out, "gui_before": gui_pids()}
    if res["gui_before"] and not os.environ.get("PCB_ALLOW_GUI"):
        sys.exit("regen-check: a KiCad GUI is running; close it first (P0-T6):\n" + "\n".join(res["gui_before"]))
    print(f"regen-check {os.path.basename(proj)}: measuring the tree as handed in")
    res["ref"] = measure_tree(proj, cfg, os.path.join(out, "ref"))
    fresh = os.path.join(out, "fresh")
    shutil.copytree(proj, fresh, symlinks=True, ignore=shutil.ignore_patterns("regen-check", "review", ".git"))
    removed = []
    for g in cfg["generated"]:
        p = os.path.join(fresh, g)
        if os.path.isdir(p):
            shutil.rmtree(p); removed.append(g + "/")
        elif os.path.exists(p):
            os.remove(p); removed.append(g)
    res["removed"] = removed
    passes = []
    for n in (1, 2):
        print(f"  pass {n}: {cfg['cmd']}")
        log = os.path.join(out, f"pass{n}.log")
        try:
            with open(log, "w") as lf:
                p = subprocess.run(cfg["cmd"], shell=True, cwd=fresh, stdout=lf, stderr=subprocess.STDOUT, timeout=a.timeout,
                                   env={**os.environ, "PCB_ALLOW_GUI": ""})
            rc = p.returncode
        except subprocess.TimeoutExpired:
            rc = "timeout"
        gui = [g for g in gui_pids() if g not in res["gui_before"]]
        m = measure_tree(fresh, cfg, os.path.join(out, f"pass{n}"))
        m["cmd_exit"] = rc
        m["gui_appeared"] = gui
        m["log"] = log
        passes.append(m)
        print(f"    exit {rc}; missing {m['missing'] or 'nothing'}; " + (f"GUI APPEARED {gui}" if gui else ""))
    res["pass1"], res["pass2"] = passes
    res["diff_ref_pass1"] = compare(res["ref"], passes[0])
    res["diff_pass1_pass2"] = compare(passes[0], passes[1])
    ok = (passes[0]["cmd_exit"] == 0 and passes[1]["cmd_exit"] == 0 and not passes[0]["missing"]
          and not res["diff_ref_pass1"] and not res["diff_pass1_pass2"] and not passes[0]["gui_appeared"])
    res["verdict"] = "REGENERATES" if ok else "FAILS"
    json.dump(res, open(os.path.join(out, "regen.json"), "w"), indent=1)
    print(f"  removed before pass 1: {', '.join(removed) or 'nothing (no --generated list)'}")
    print(f"  pass 1 vs handed-in tree: {'identical' if not res['diff_ref_pass1'] else '; '.join(res['diff_ref_pass1'])}")
    print(f"  pass 2 vs pass 1:         {'identical' if not res['diff_pass1_pass2'] else '; '.join(res['diff_pass1_pass2'])}")
    for n, m in ((1, passes[0]), (2, passes[1])):
        d = m.get("drc", {})
        print(f"  pass {n}: exit {m['cmd_exit']}, DRC plain {d.get('plain_errors', '?')} err / {d.get('plain_warnings', '?')} warn, "
              f"packed {d.get('packed_errors', '?')} err, fab {'ok' if 'fab' in m else 'MISSING'}")
    print(f"  {res['verdict']} -> {rel(os.path.join(out, 'regen.json'))}")
    return 0 if ok else 1


# ----------------------------------------------------------------------------------------------------- main
def main(argv):
    p = argparse.ArgumentParser(prog="pcb")
    sp = p.add_subparsers(dest="subcmd", required=True)
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
    s.add_argument("--no-render", action="store_true")
    s = sp.add_parser("regen-check"); s.add_argument("project"); s.add_argument("--cmd"); s.add_argument("--board")
    s.add_argument("--sch"); s.add_argument("--pack"); s.add_argument("--generated", nargs="*")
    s.add_argument("--out"); s.add_argument("--timeout", type=int, default=1200)
    a = p.parse_args(argv)
    if not os.path.exists(KICAD_CLI):
        sys.exit(f"kicad-cli not found at {KICAD_CLI} (set KICAD_CLI)")
    return globals()["cmd_" + a.subcmd.replace("-", "_")](a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
