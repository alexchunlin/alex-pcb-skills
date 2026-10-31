"""pcb check BOARD.kicad_pcb [checks.json] [--out pcbcheck.json] [--only a,b] [--netlist x.xml] [--bringup BRINGUP.md]

Intent checks over the board (SWIG pcbnew) and the schematic netlist (kicadxml): the rows ERC and DRC cannot see
(P0-T2). checks.json declares the intent; anything the netlist shows that the config does not declare is a fail
(cadcheck's rule). Every row carries the measured number and the FINDINGS ID that motivated it.

Checks (v0):
  rails        every net with a power_in/power_out pin (or GND-like name) is declared; declared rails exist; test point per rail
  decoupling   every IC power_in pin has a capacitor to a GND-like net within max_mm, measured pad to pin (R1-Z1-F3, R1-S1-F2)
  pullups      each bus line has a pull-up to the rail (through default-closed jumpers), sink current per line and
               with chain_boards in parallel against max_sink_ma (R1-S1-F2 "up to four boards")
  addresses    declared addresses unique per bus; an address strap resolves high/low through the jumpers to the declared address
  connectors   declared pin map vs the netlist, undeclared connectors fail (Qwiic order)
  pinmaps      declared pin -> net for any reference (an IC's bus pins against the bus nets): the Plink v1.0 IMU had
               SCL on the SDA net and SDA on SCL until the rework (P0-T2, P1-T18)
  jumpers      declared pad nets and default position; undeclared JP* fail
  test_points  declared net per TP, undeclared TP* fail, each TP named in the bring-up doc
  silk         every refdes the bring-up doc names is readable on silk (R1-Z1-F4)
  margin       min track width, via drill/diameter, setup clearance and hole clearance vs the fab pack floor, as ratios
               against min_ratio (R1-S1-F2 "every feature 2x the floor")
Config keys: rails, decoupling, decoupling_max_mm, gnd_via_max_mm, buses, connectors, pinmaps, jumpers, test_points, bringup,
margin, accepted_warns, _notes.
Report: pcbcheck.json {summary: {fails, warns, passes, accepted}, rows: [...], coverage, not_checked}; exit 1 on fails.
"""
import json, os, re, subprocess, sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pcbnew  # noqa: E402
import pcbq  # noqa: E402

KICAD_CLI = os.environ.get("KICAD_CLI", "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
KICAD_DRUID = os.environ.get("KICAD_DRUID", "/tmp/pcb-ref/kicad-druid")
KNOWN = {"rails", "decoupling", "buses", "connectors", "pinmaps", "jumpers", "test_points", "bringup", "margin", "accepted_warns",
         "decoupling_max_mm", "gnd_via_max_mm", "project"}
ROWS, COVERAGE, NOT_CHECKED, CONFIG_WARNS = [], [], [], []


def row(check, status, rid, msg, value=None, limit=None, objects=(), finding=""):
    ROWS.append({"check": check, "status": status, "id": rid, "msg": msg, "value": value, "limit": limit,
                 "objects": list(objects), "finding": finding})


def arg(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        v = sys.argv[i + 1]
        del sys.argv[i:i + 2]
        return v
    return default


# ------------------------------------------------------------------------------------------------ netlist
def parse_netlist(path):
    r = ET.parse(path).getroot()
    comps, libparts, nets, padnet = {}, {}, {}, {}
    for c in r.find("components"):
        ls = c.find("libsource")
        comps[c.get("ref")] = {"value": (c.findtext("value") or ""), "footprint": (c.findtext("footprint") or ""),
                               "lib": (ls.get("lib"), ls.get("part")) if ls is not None else ("", ""),
                               "fields": {f.get("name"): f.text or "" for f in (c.find("fields") or [])}}
    lp = r.find("libparts")
    for p in (lp if lp is not None else []):
        pins = {pin.get("num"): (pin.get("name") or "", pin.get("type") or "") for pin in (p.find("pins") or [])}
        libparts[(p.get("lib"), p.get("part"))] = pins
    for n in r.find("nets"):
        nodes = [(x.get("ref"), x.get("pin")) for x in n]
        nets[n.get("name")] = nodes
        for ref, pin in nodes:
            padnet[(ref, pin)] = n.get("name")
    return comps, libparts, nets, padnet


def pin_type(NL, ref, pin):
    comps, libparts = NL[0], NL[1]
    return libparts.get(comps.get(ref, {}).get("lib"), {}).get(pin, ("", ""))[1]


def gnd_like(name):
    n = name.upper()
    return n.startswith(("GND", "VSS", "AGND", "DGND", "PGND")) or n in ("0", "EARTH")


def parse_ohms(s):
    m = re.match(r"^\s*([\d.]+)\s*([kKmMrR]?)\s*([\d]*)\s*(?:ohm|Ω|R)?\s*$", s.strip())
    if not m:
        return None
    whole, unit, frac = m.groups()
    val = float(whole + ("." + frac if frac else ""))
    return val * {"k": 1e3, "K": 1e3, "m": 1e6, "M": 1e6, "r": 1, "R": 1, "": 1}[unit]


def jumper_links(NL):
    """Nets joined by default-closed solder jumpers, from the footprint name (SolderJumper-3_..._Bridged12): one set
    of pad numbers per jumper that are bridged as shipped."""
    comps, _, _, padnet = NL
    links = []
    for ref, c in comps.items():
        if not ref.startswith("JP"):
            continue
        m = re.search(r"Bridged(\d+)", c["footprint"] + " " + c["value"])
        if m:
            pads = list(m.group(1))
            nets = {padnet.get((ref, p)) for p in pads} - {None}
            links.append((ref, pads, nets))
    return links


def reach(NL, start, links):
    """Nets reachable from start through default-closed jumpers."""
    seen = {start}
    grow = True
    while grow:
        grow = False
        for _, _, nets in links:
            if nets & seen and not nets <= seen:
                seen |= nets; grow = True
    return seen


# ------------------------------------------------------------------------------------------------ checks
def check_rails(CFG, NL, B):
    comps, libparts, nets, padnet = NL
    declared = CFG.get("rails", {})
    power = {}
    for name, nodes in nets.items():
        types = {pin_type(NL, r, p) for r, p in nodes}
        if types & {"power_in", "power_out"} or gnd_like(name):
            power[name] = sorted(types - {""})
    for name in sorted(power):
        if name not in declared:
            row("rails", "fail", f"rails:{name}", f"net {name} carries power pins {power[name]} but is not declared in rails",
                objects=[name], finding="P0-T2")
        else:
            row("rails", "pass", f"rails:{name}", f"{name}: {len(nets[name])} pads, pin types {power[name]}", value=len(nets[name]), objects=[name])
    for name in declared:
        if name not in nets:
            row("rails", "fail", f"rails:{name}", f"declared rail {name} is not a net in the netlist", objects=[name])
    COVERAGE.append(f"rails: {len(power)} power nets by pin type or GND-like name, {len(declared)} declared")


def check_decoupling(CFG, NL, B):
    comps, libparts, nets, padnet = NL
    fps = pcbq.fp_map(B)
    max_mm = float(CFG.get("decoupling_max_mm", 2.0))
    via_max = CFG.get("gnd_via_max_mm")   # the designer's "GND vias within 1 mm" claim becomes a limit (R1-S1-F2)
    declared = {(d["ic"], d["pin"], d["cap"]): d for d in CFG.get("decoupling", [])}
    vias = [t for t in B.GetTracks() if t.GetClass() == "PCB_VIA"]
    via_rows = set()   # one GND-via row per cap, whichever pins it serves
    n_pins = 0
    for ref, c in sorted(comps.items()):
        pins = libparts.get(c["lib"], {})
        for pin, (pname, ptype) in sorted(pins.items()):
            if ptype != "power_in":
                continue
            net = padnet.get((ref, pin))
            if net is None or gnd_like(net):
                continue
            n_pins += 1
            caps = []
            for cref, cc in comps.items():
                if not cref.startswith("C") or cref == ref:
                    continue
                cpins = [p for (r, p) in padnet if r == cref]
                onnet = [p for p in cpins if padnet[(cref, p)] == net]
                ongnd = [p for p in cpins if gnd_like(padnet[(cref, p)])]
                if onnet and ongnd and cref in fps and ref in fps:
                    cp = pcbq.pad_of(fps, f"{cref}.{onnet[0]}"); ip = pcbq.pad_of(fps, f"{ref}.{pin}")
                    gp = pcbq.pad_of(fps, f"{cref}.{ongnd[0]}")
                    gv = min((pcbq.cc(gp, v) for v in vias if v.GetNetname() == gp.GetNetname()), default=None)
                    caps.append((cref, cc["value"], pcbq.cc(cp, ip), pcbq.pad_edge(cp, ip), gv))
            if not caps:
                row("decoupling", "fail", f"decoupling:{ref}.{pin}", f"{ref}.{pin} {pname} on {net}: no capacitor between {net} and a GND net",
                    objects=[ref, net], finding="R1-S1-F2")
                continue
            caps.sort(key=lambda x: x[2])
            near = caps[0]
            st = "pass" if near[2] <= max_mm else "fail"
            row("decoupling", st, f"decoupling:{ref}.{pin}",
                f"{ref}.{pin} {pname} on {net}: nearest cap {near[0]} ({near[1]}) at {near[2]:.3f} mm centre, {near[3]} mm edge"
                + ("" if len(caps) == 1 else "; others " + ", ".join(f"{c[0]} {c[2]:.3f}" for c in caps[1:])),
                value=round(near[2], 3), limit=max_mm, objects=[ref, near[0]], finding="R1-Z1-F3")
            for cref, val, d, e, gv in caps:
                key = (ref, pin, cref)
                if key in declared:
                    lim = float(declared[key].get("max_mm", max_mm))
                    row("decoupling", "pass" if d <= lim else "fail", f"decoupling:{ref}.{pin}:{cref}",
                        f"declared {cref} ({val}) to {ref}.{pin}: {d:.3f} mm centre, {e} mm edge", value=round(d, 3), limit=lim,
                        objects=[ref, cref], finding="R1-Z1-F3")
                    declared[key]["_seen"] = True
                vlim = (declared.get(key) or {}).get("gnd_via_max_mm", via_max)
                if gv is not None and (vlim is not None or key in declared) and cref not in via_rows:
                    via_rows.add(cref)
                    st = "pass" if vlim is None or gv <= float(vlim) else "fail"
                    row("decoupling", st, f"decoupling:{cref}:gnd_via",
                        f"{cref} GND pad to nearest GND via {gv:.3f} mm" + (f" (limit {vlim})" if vlim is not None else ""),
                        value=round(gv, 3), limit=vlim, objects=[cref], finding="R1-S1-F2")
    for key, d in declared.items():
        if not d.get("_seen"):
            row("decoupling", "fail", f"decoupling:{key[0]}.{key[1]}:{key[2]}", f"declared row {d} matches no cap on that pin's net", objects=list(key))
    COVERAGE.append(f"decoupling: {n_pins} power_in pins on non-ground nets, {len(declared)} declared rows, limit {max_mm} mm")


def check_pullups(CFG, NL, B):
    comps, libparts, nets, padnet = NL
    links = jumper_links(NL)
    for bus, b in CFG.get("buses", {}).items():
        rail = b.get("rail", "3V3")
        v = float(CFG.get("rails", {}).get(rail, {}).get("v", 3.3))
        max_ma = float(b.get("max_sink_ma", 3.0))
        chain = int(b.get("chain_boards", 1))
        rail_nets = reach(NL, rail, links)
        for line in ("sda", "scl"):
            net = b.get(line)
            if not net or net not in nets:
                row("pullups", "fail", f"pullups:{bus}:{line}", f"bus {bus} {line} net {net!r} not in the netlist", objects=[bus])
                continue
            rs = []
            for ref, c in comps.items():
                if not ref.startswith("R"):
                    continue
                pins = [p for (r, p) in padnet if r == ref]
                on = [p for p in pins if padnet[(ref, p)] == net]
                other = [padnet[(ref, p)] for p in pins if padnet[(ref, p)] != net]
                if on and other and reach(NL, other[0], links) & rail_nets:
                    rs.append((ref, c["value"], parse_ohms(c["value"]), other[0]))
            if not rs:
                row("pullups", "fail", f"pullups:{bus}:{line}", f"{net}: no pull-up resistor to {rail} (through default-closed jumpers)",
                    objects=[net], finding="R1-S1-F2")
                continue
            ref, val, ohm, via = rs[0]
            if ohm is None:
                row("pullups", "fail", f"pullups:{bus}:{line}", f"{net}: {ref} value {val!r} is not a resistance", objects=[ref])
                continue
            i1 = v / ohm * 1e3
            ic = i1 * chain
            st = "pass" if ic <= max_ma else "fail"
            row("pullups", st, f"pullups:{bus}:{line}",
                f"{net}: {ref} {val} to {rail}" + (f" via {via} (jumper)" if via != rail else "") +
                f": {i1:.2f} mA per line at {v} V; {chain} board(s) in parallel = {ohm / chain:.0f} ohm, {ic:.2f} mA (limit {max_ma})",
                value=round(ic, 2), limit=max_ma, objects=[ref, net], finding="R1-S1-F2")
    COVERAGE.append(f"pullups: {len(CFG.get('buses', {}))} buses, jumpers treated as shipped (bridged pads from the footprint name)")


def check_addresses(CFG, NL, B):
    comps, libparts, nets, padnet = NL
    links = jumper_links(NL)
    for bus, b in CFG.get("buses", {}).items():
        rail = b.get("rail", "3V3")
        devs = b.get("devices", {})
        seen = {}
        for ref, d in devs.items():
            addr = str(d.get("address", "")).lower()
            if addr in seen:
                row("addresses", "fail", f"addresses:{bus}:{ref}", f"{ref} and {seen[addr]} both declare {addr} on {bus}", objects=[ref, seen[addr]], finding="P0-T2")
            seen.setdefault(addr, ref)
            strap = d.get("strap")
            if strap:
                net = padnet.get((ref, str(strap["pin"])))
                if net is None:
                    row("addresses", "fail", f"addresses:{bus}:{ref}", f"{ref} strap pin {strap['pin']} is not in the netlist", objects=[ref]); continue
                r = reach(NL, net, links)
                hi = bool(r & reach(NL, rail, links))
                lo = any(gnd_like(n) for n in r)
                level = "high" if hi and not lo else "low" if lo and not hi else "floating" if not (hi or lo) else "SHORT"
                got = str(strap.get(level, "")).lower()
                st = "pass" if got == addr else "fail"
                row("addresses", st, f"addresses:{bus}:{ref}",
                    f"{ref} strap pin {strap['pin']} ({net}) resolves {level} through {[l[0] for l in links if net in l[2]]} -> {got or '?'}; declared {addr}",
                    value=got, limit=addr, objects=[ref, net], finding="P0-T2")
            else:
                row("addresses", "pass", f"addresses:{bus}:{ref}", f"{ref} declared {addr} (no strap declared, not resolved)", value=addr, objects=[ref])
    COVERAGE.append("addresses: uniqueness per bus; straps resolved through default-closed jumpers to the rail or a GND net")


def check_connectors(CFG, NL, B):
    comps, libparts, nets, padnet = NL
    declared = CFG.get("connectors", {})
    for ref in sorted(comps):
        if not ref.startswith("J") or ref.startswith("JP"):
            continue
        if ref not in declared:
            row("connectors", "fail", f"connectors:{ref}", f"{ref} ({comps[ref]['value']}) has no declared pin map", objects=[ref], finding="P0-T2")
            continue
        pm = declared[ref]
        bad = []
        for pin, want in pm.items():
            got = padnet.get((ref, str(pin)))
            if got != want:
                bad.append(f"pin {pin}: declared {want}, netlist {got}")
        unlisted = sorted(p for (r, p) in padnet if r == ref and p not in pm)
        if bad:
            row("connectors", "fail", f"connectors:{ref}", f"{ref}: " + "; ".join(bad), objects=[ref], finding="P0-T2")
        else:
            row("connectors", "pass", f"connectors:{ref}", f"{ref}: {len(pm)} pins match " + ", ".join(f"{p}={n}" for p, n in pm.items())
                + (f"; unlisted pads {unlisted}" if unlisted else ""), value=len(pm), objects=[ref])
    for ref in declared:
        if ref not in comps:
            row("connectors", "fail", f"connectors:{ref}", f"declared connector {ref} is not in the netlist", objects=[ref])
    COVERAGE.append(f"connectors: {len(declared)} declared pin maps checked against the netlist")


def check_pinmaps(CFG, NL, B):
    comps, libparts, nets, padnet = NL
    declared = CFG.get("pinmaps", {})
    for ref, pm in declared.items():
        if ref not in comps:
            row("pinmaps", "fail", f"pinmaps:{ref}", f"declared {ref} is not in the netlist", objects=[ref]); continue
        pins = libparts.get(comps[ref]["lib"], {})
        bad = []
        for pin, want in pm.items():
            got = padnet.get((ref, str(pin)))
            name = pins.get(str(pin), ("", ""))[0]
            if got != want:
                bad.append(f"pin {pin} {name}: declared {want}, netlist {got}")
        if bad:
            row("pinmaps", "fail", f"pinmaps:{ref}", f"{ref} ({comps[ref]['value']}): " + "; ".join(bad), objects=[ref], finding="P1-T18")
        else:
            row("pinmaps", "pass", f"pinmaps:{ref}", f"{ref}: {len(pm)} pins on the declared nets "
                + ", ".join(f"{p} {pins.get(str(p), ('', ''))[0]}={n}" for p, n in pm.items()), value=len(pm), objects=[ref])
    COVERAGE.append(f"pinmaps: {len(declared)} references with declared pin nets")


def check_jumpers(CFG, NL, B):
    comps, libparts, nets, padnet = NL
    declared = CFG.get("jumpers", {})
    links = {l[0]: l for l in jumper_links(NL)}
    for ref in sorted(comps):
        if not ref.startswith("JP"):
            continue
        if ref not in declared:
            row("jumpers", "fail", f"jumpers:{ref}", f"{ref} ({comps[ref]['value']}) is not declared", objects=[ref])
            continue
        d = declared[ref]
        bad = []
        for pin, want in d.get("pads", {}).items():
            got = padnet.get((ref, str(pin)))
            if got != want:
                bad.append(f"pad {pin}: declared {want}, netlist {got}")
        shipped = "".join(links[ref][1]) if ref in links else "open"
        want = str(d.get("default", "")).replace("-", "")
        if want and shipped != want:
            bad.append(f"shipped bridge {shipped} (footprint {comps[ref]['footprint'].split(':')[-1]}), declared default {d.get('default')}")
        row("jumpers", "fail" if bad else "pass", f"jumpers:{ref}",
            f"{ref}: " + ("; ".join(bad) if bad else f"pads {d.get('pads')} match, shipped bridge {shipped}"), objects=[ref])
    for ref in declared:
        if ref not in comps:
            row("jumpers", "fail", f"jumpers:{ref}", f"declared jumper {ref} is not in the netlist", objects=[ref])
    COVERAGE.append(f"jumpers: {len(declared)} declared; bridged-as-shipped read from the footprint name")


def read_bringup(CFG, cfg_dir, board):
    p = arg("--bringup") or CFG.get("bringup")
    cands = [p] if p else []
    for up in range(4):
        d = os.path.abspath(os.path.join(os.path.dirname(board), *([".."] * up)))
        cands.append(os.path.join(d, "BRINGUP.md"))
    for c in cands:
        if c and os.path.exists(os.path.join(cfg_dir, c) if not os.path.isabs(c) else c):
            c = os.path.join(cfg_dir, c) if not os.path.isabs(c) else c
            return c, open(c).read()
    return None, ""


def check_test_points(CFG, NL, B, bringup):
    comps, libparts, nets, padnet = NL
    declared = CFG.get("test_points", {})
    for ref in sorted(comps):
        if not ref.startswith("TP"):
            continue
        if ref not in declared:
            row("test_points", "fail", f"test_points:{ref}", f"{ref} is not declared", objects=[ref]); continue
        got = padnet.get((ref, "1"))
        st = "pass" if got == declared[ref] else "fail"
        named = bool(re.search(rf"\b{ref}\b", bringup[1]))
        if st == "pass" and bringup[0] and not named:
            st = "fail"
        row("test_points", st, f"test_points:{ref}", f"{ref} on {got} (declared {declared[ref]}); "
            + ("named in the bring-up doc" if named else "NOT named in the bring-up doc" if bringup[0] else "no bring-up doc found"),
            value=got, limit=declared[ref], objects=[ref])
    for ref in declared:
        if ref not in comps:
            row("test_points", "fail", f"test_points:{ref}", f"declared test point {ref} is not in the netlist", objects=[ref])
    tp_nets = {padnet.get((r, "1")) for r in declared}
    for rail in CFG.get("rails", {}):
        if rail not in tp_nets:
            row("test_points", "warn", f"test_points:rail:{rail}", f"rail {rail} has no test point", objects=[rail])
    COVERAGE.append(f"test_points: {len(declared)} declared, bring-up doc {'found: ' + os.path.basename(bringup[0]) if bringup[0] else 'not found'}")


def check_silk(CFG, NL, B, bringup):
    comps = NL[0]
    if not bringup[0]:
        NOT_CHECKED.append("silk: no bring-up doc (declare bringup: path) so refdes readability was not checked")
        return
    fps = pcbq.fp_map(B)
    silk_texts = {d.GetText().strip() for d in B.GetDrawings() if d.GetClass() == "PCB_TEXT" and d.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS)}
    named = sorted({m for m in re.findall(r"\b([A-Z]{1,3}\d{1,3})\b", bringup[1]) if m in comps})
    hidden = []
    for ref in named:
        f = fps.get(ref)
        vis = f is not None and f.Reference().IsVisible() and f.Reference().GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS)
        if not vis and ref not in silk_texts:
            hidden.append(ref)
    if hidden:
        row("silk", "fail", "silk:refdes", f"bring-up doc names {len(named)} parts; {len(hidden)} have no readable refdes on silk: {', '.join(hidden)}",
            value=len(hidden), limit=0, objects=hidden, finding="R1-Z1-F4")
    else:
        row("silk", "pass", "silk:refdes", f"all {len(named)} parts named in the bring-up doc have a refdes on silk", value=0, limit=0)
    COVERAGE.append(f"silk: {len(named)} refdes named in {os.path.basename(bringup[0])} checked for a visible Reference or silk text")


def pack_floor(spec, B):
    import importlib.util
    specf = importlib.util.spec_from_file_location("pcbcli", os.path.join(HERE, "pcbcli.py"))
    cli = importlib.util.module_from_spec(specf); specf.loader.exec_module(cli)
    board = B.GetFileName()
    path = cli.resolve_pack(spec, board)
    if not path:
        return None, None
    text = open(path).read()
    floor = {}
    for m in cli.CONSTRAINT_RE.finditer(text):
        kind, val, unit = m.group(1), float(m.group(2)), m.group(3) or "mm"
        cond = cli.condition_at(text, m.start())
        mm = val * cli.UNIT[unit]
        key = kind
        if kind == "hole_size":
            if "Via" not in cond:
                continue
            key = "via_drill"
        floor[key] = min(floor.get(key, 1e9), mm)
    return path, floor


def check_margin(CFG, NL, B):
    m = CFG.get("margin")
    if not m:
        NOT_CHECKED.append("margin: no margin block (declare pack and min_ratio) so feature-vs-floor ratios were not computed")
        return
    path, floor = pack_floor(m.get("pack", "jlcpcb"), B)
    if not floor:
        row("margin", "fail", "margin:pack", f"fab pack {m.get('pack')} not found", finding="R1-S1-F2"); return
    ds = B.GetDesignSettings()
    tracks = [t for t in B.GetTracks() if t.GetClass() != "PCB_VIA"]
    vias = [t for t in B.GetTracks() if t.GetClass() == "PCB_VIA"]
    actual = {
        "track_width": min((pcbnew.ToMM(t.GetWidth()) for t in tracks), default=None),
        "clearance": pcbnew.ToMM(ds.m_MinClearance),
        "via_drill": min((pcbnew.ToMM(v.GetDrillValue()) for v in vias), default=None),
        "via_diameter": min((pcbnew.ToMM(v.GetWidth()) for v in vias), default=None),
        "hole_clearance": pcbnew.ToMM(ds.m_HoleClearance),
        "edge_clearance": pcbnew.ToMM(ds.m_CopperEdgeClearance),
    }
    ratios = m.get("min_ratio", {})
    default_ratio = float(m.get("default_ratio", 1.0))
    for k, a in actual.items():
        f = floor.get(k)
        if a is None or f is None:
            NOT_CHECKED.append(f"margin: {k} (no {'board feature' if a is None else 'pack floor'})"); continue
        want = float(ratios.get(k, default_ratio))
        r = a / f
        src = "setup" if k in ("clearance", "hole_clearance", "edge_clearance") else "measured"
        row("margin", "pass" if r + 1e-9 >= want else "fail", f"margin:{k}",
            f"{k}: {a:.3f} mm ({src}) vs fab floor {f:.3f} mm = {r:.2f}x (min {want}x)", value=round(r, 2), limit=want, finding="R1-S1-F2")
    COVERAGE.append(f"margin: floor from {os.path.basename(path)} (loosest min per constraint kind); clearances are the board-setup values the plain DRC enforces, not measured gaps")


# ------------------------------------------------------------------------------------------------ main
def main():
    out = arg("--out")
    only = set((arg("--only") or "").split(",")) - {""}
    netlist = arg("--netlist")
    bring = arg("--bringup")
    if bring:
        sys.argv += ["--bringup", bring]   # re-read by read_bringup
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    board = os.path.abspath(args[0])
    cfg_path = args[1] if len(args) > 1 else os.path.join(os.path.dirname(board), "checks.json")
    CFG = json.load(open(cfg_path)) if os.path.exists(cfg_path) else {}
    cfg_dir = os.path.dirname(os.path.abspath(cfg_path))
    for k in CFG:
        if k not in KNOWN and not k.startswith("_"):
            CONFIG_WARNS.append(f"unknown key {k!r} (known: {', '.join(sorted(KNOWN))})")
    out = out or os.path.join(os.path.dirname(board), "pcbcheck.json")
    stem = os.path.splitext(board)[0]
    netlist = netlist or (stem + ".xml")
    if not os.path.exists(netlist):
        sch = stem + ".kicad_sch"
        if os.path.exists(sch):
            subprocess.run([KICAD_CLI, "sch", "export", "netlist", "--format", "kicadxml", "-o", netlist, sch], capture_output=True)
    if not os.path.exists(netlist):
        sys.exit(f"pcbcheck: no netlist at {netlist} and no schematic to export it from (pass --netlist)")
    NL = parse_netlist(netlist)
    B = pcbnew.LoadBoard(board)
    bringup = read_bringup(CFG, cfg_dir, board)
    checks = [("rails", lambda: check_rails(CFG, NL, B)), ("decoupling", lambda: check_decoupling(CFG, NL, B)),
              ("pullups", lambda: check_pullups(CFG, NL, B)), ("addresses", lambda: check_addresses(CFG, NL, B)),
              ("connectors", lambda: check_connectors(CFG, NL, B)), ("pinmaps", lambda: check_pinmaps(CFG, NL, B)),
              ("jumpers", lambda: check_jumpers(CFG, NL, B)),
              ("test_points", lambda: check_test_points(CFG, NL, B, bringup)), ("silk", lambda: check_silk(CFG, NL, B, bringup)),
              ("margin", lambda: check_margin(CFG, NL, B))]
    for name, fn in checks:
        if only and name not in only:
            continue
        try:
            fn()
        except Exception as e:   # one broken check must not take the report down (3D V2A1-T3)
            row(name, "fail", f"{name}:crash", f"check crashed: {type(e).__name__}: {e}")
    acc = CFG.get("accepted_warns", [])
    n_acc = 0
    for r in ROWS:
        if r["status"] == "warn":
            for a in acc:
                if (not a.get("check") or a["check"] == r["check"]) and a.get("match", "") in (r["id"] + " " + r["msg"]):
                    r["status"] = "accepted"; r["reason"] = a.get("reason", ""); n_acc += 1; break
    summ = {"fails": sum(r["status"] == "fail" for r in ROWS), "warns": sum(r["status"] == "warn" for r in ROWS),
            "passes": sum(r["status"] == "pass" for r in ROWS), "accepted": n_acc, "config_warns": CONFIG_WARNS}
    rep = {"board": board, "netlist": netlist, "config": cfg_path, "bringup": bringup[0], "summary": summ, "rows": ROWS,
           "coverage": COVERAGE, "not_checked": NOT_CHECKED}
    json.dump(rep, open(out, "w"), indent=1)
    print(f"pcbcheck {os.path.basename(board)}: {summ['fails']} fails, {summ['warns']} warns, {summ['passes']} passes"
          f"{', ' + str(n_acc) + ' accepted' if n_acc else ''} -> {out}")
    for r in ROWS:
        if r["status"] in ("fail", "warn"):
            print(f"  {r['status'].upper():4} {r['id']}: {r['msg']}" + (f"  [{r['finding']}]" if r["finding"] else ""))
    for w in CONFIG_WARNS:
        print(f"  CONFIG {w}")
    for n in NOT_CHECKED:
        print(f"  not checked: {n}")
    sys.exit(1 if summ["fails"] else 0)


if __name__ == "__main__":
    main()
