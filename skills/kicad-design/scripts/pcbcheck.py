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
  currents     declared amps per net -> required width by IPC-2221 (20 degC rise by default, outer and inner copper
               weight from `copper_oz`) against the narrowest track on that net per layer; a net carried only by a
               pour passes with the pour noted (rung 2: VIN 4 A, 5V 3 A, motor 2.5 A)
  feeds        {pad, amps, within_mm}: the ampacity of what feeds a high-current pad, vias within the radius (IPC-2221
               internal on the barrel) plus tracks touching it; a pour-only feed fails with its neck unsized (rung 2: the
               DRV8874 VM pin fed by one 0.3 mm via or a 0.34 mm pour finger on two of three boards, R2-T5)
  irdrop       every net with `feeds` rows solved on its real copper (`pcb irdrop`): sinks are the feeds pads (a
               capacitor's ripple amps solved on its own and rated as rms heating), the source from irdrop.sources
               {NET: "REF.PAD,..."} or the part the rails block names first. Fails a neck (a cut across the copper at the
               hottest cells) or a via/plated-hole barrel carrying more than IPC-2221 allows for its cross-section at
               rise_c, and a sink with no path; a neck as wide as its pad and under 1 mm is the pad's exit, reported.
               Opt-in: {"sources": {}, "grid_mm": 0.1} (spike #3, C1; R2-O-2, R2A2-O-1 from physics)
  basic_parts  every BOM line's LCSC code as JLC basic or extended from a dated cache (tools/bench/jlc_parts.py fetch),
               extended types warn with the feeder fee and any basic alternative the cache lists, stock under
               boards x quantity fails, a total row sums the fees. Opt-in: {"cache": path, "assembly": "economic",
               "boards": 5, "max_extended": null} (spike #3, C2: 17 extended types, $52 of a $125-150 order)
  via_in_pad   no via touches an SMD pad of any net (Alex, spike #6): the via's copper must clear the pad, so a mask web
               keeps solder on the pad. Exposed pads named in `thermal_vias` are exempt, and any pad in {"allow": ["U2.21"]}
               with the footprint's unnumbered copper. Opt-in: {} or {"allow": [...]}, on in the template
  edge_margin  tracks, vias and parts stay off the outline (Alex, spike #6): {"tracks_mm": 1.0, "vias_mm": 1.0, "parts_mm": 1.0,
               "connector_mm": 1.5, "skip_refs": []}; connectors (J*) and holes (H*, MH*) are exempt as parts and a track
               end within connector_mm of a pad on its own net on a J* footprint is the connector's exit. Opt-in, on in the template
  gnd_islands  the ground fill refilled with island removal off, on a copy: every piece with no ground copper over
               warn_mm2 (0.5) warns, over max_mm2 (2.0) fails (Alex, spike #6: tie islands to ground with a via, `pcb route
               ground-islands`, which `pcb route auto` runs). Opt-in: {"ground": "GND"}, on in the template
  thermal_vias declared minimum stitching vias on a pad's net within `within_mm` of the pad (thermal pad to pour)
  feed_room    placement-stage: every SMD `feeds` pad gets a trial pcblib plan_feeds on an in-memory copy (biggest
               current first, neighbours splayed apart, each feed reserved for the next), so a pad whose feed cannot fit
               fails at placement with the parts in the way, before any routing (FEED-2). Opt-in: {} or {"skip": [pads]}
  refplane     every track off the ground net runs over solid ground fill on the copper layer next to it in the stack
               (In1 under F.Cu, the last inner layer under B.Cu): sampled every step_mm, points next to the net's own
               vias and through-hole pads skipped (the plane's antipad), per net the mm and the count of gaps crossed.
               Opt-in: {"ground": "GND", "step_mm": 0.25, "max_gap_mm": 0, "mid_max_mm": 5, "antipad_mm": 0.5,
               "connector_mm": 1.5, "skip_nets": []}; points within connector_mm of a through-hole pad of a footprint the net
               lands on are skipped too (a track entering its own connector crosses the pin field's voids). Alex's
               stackup: two solid ground planes, rails routed, signals only over unbroken ground (REFPLANE-1). The limit
               follows the net's bucket from `signals` (SIG-1): 3 and 4 fail above max_gap_mm, 2 warns above mid_max_mm,
               1 and the rails carry the mm as a cost only; each row has `bucket` and `gaps`
  return_via   a via on a fast net moves its return from one ground plane to the other: the nearest ground via or
               through-hole ground pad must be within max_mm_4 1.0 / max_mm_3 2.0 (fail) / max_mm_2 5.0 mm (warn);
               bucket 1 is reported, rails skipped. Opt-in: {"ground": "GND"} (SIG-2)
  exposure     same-layer exposure to an aggressor's copper (default: the switch node, an inductor net that reaches an
               IC pin): track of every non-local signal net sampled every step_mm, samples within within_mm of the
               aggressor's tracks, pads or zone fill on the same layer summed per net, times victim_weight for `signals`
               victims; nets local to the aggressor (every pad on a footprint that also carries it) and rails left out.
               Opt-in: {"aggressors": [], "within_mm": 1.0, "step_mm": 0.25, "victim_weight": 3, "max_mm": null} (SIG-3)
  refstat      corpus reference-circuit rows (spike 2, tools/corpus/refstat.py over bshada/open-schematics): {part, pin,
               pattern: {class, band, to, max_mm}, support, n}. Every instance of the part (value or symbol name) needs a
               part of `class` in value `band` on the canonical `pin`'s net whose other pin lands on `to` (GND, IC:<pin>,
               PWR), within max_mm pad to pad on the board when given; the message quotes the corpus support
  calcs        formula rows: {id, expr, vars, min, max}; `R("R5")`, `C("C3")`, `L("L1")` read values from the
               netlist, earlier ids are variables; the brief's buck ripple, LDO dissipation and sense scaling
  fields       every BOM part (not DNP, not excluded from BOM) carries the required fields, default MPN, Manufacturer,
               LCSC, Datasheet (the brief's list; R1-A2S-1: Datasheet empty on 5 of 8 parts while the log said "every symbol")
  policy       the brief's numbers as a floor the board setup and the measured minima must meet: clearance, track,
               via drill and diameter, hole clearance, silk text height. Both attempt-2 designers lowered a board
               setting until plain DRC read 0 (clearance 0.14/0.15, silk text 0.8); the policy block makes that a
               fail instead of a silent relaxation (R1-A2-T5, R1-A2-T6)
Config keys: rails, decoupling, decoupling_max_mm, gnd_via_max_mm, buses, connectors, pinmaps, jumpers, test_points, bringup,
margin, policy, fields, currents, copper_oz, rise_c, thermal_vias, refplane, return_via, exposure, feed_room, calcs, feeds,
irdrop, basic_parts, refstat, signals, accepted_warns, _notes.
Report: pcbcheck.json {summary: {fails, warns, passes, accepted}, rows: [...], coverage, not_checked}; exit 1 on fails.
"""
import json, math, os, re, subprocess, sys, zlib
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pcbnew  # noqa: E402
import pcbq  # noqa: E402
import pcbrefstat  # noqa: E402

KICAD_CLI = os.environ.get("KICAD_CLI", "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
KICAD_DRUID = os.environ.get("KICAD_DRUID", "/tmp/pcb-ref/kicad-druid")
KNOWN = {"rails", "decoupling", "buses", "connectors", "pinmaps", "jumpers", "test_points", "bringup", "margin", "policy", "fields", "currents", "copper_oz", "rise_c", "thermal_vias", "via_in_pad", "edge_margin", "gnd_islands", "refplane", "feed_room", "return_via", "exposure", "calcs", "feeds", "signals", "irdrop", "basic_parts", "refstat", "accepted_warns",
         "decoupling_max_mm", "gnd_via_max_mm", "project"}
ROWS, COVERAGE, NOT_CHECKED, CONFIG_WARNS = [], [], [], []


def row(check, status, rid, msg, value=None, limit=None, objects=(), finding="", **extra):
    ROWS.append({"check": check, "status": status, "id": rid, "msg": msg, "value": value, "limit": limit,
                 "objects": list(objects), "finding": finding, **extra})


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
        if d.get("_seen"):
            continue
        ref, pin, cref = key
        net = padnet.get((ref, pin))
        cpins = [p for (r, p) in padnet if r == cref]
        onnet = [p for p in cpins if padnet[(cref, p)] == net]
        if net and onnet and ref in fps and cref in fps:
            cp = pcbq.pad_of(fps, f"{cref}.{onnet[0]}"); ip = pcbq.pad_of(fps, f"{ref}.{pin}")
            dmm, e = pcbq.cc(cp, ip), pcbq.pad_edge(cp, ip)
            lim = float(d.get("max_mm", max_mm))
            ptype = pin_type(NL, ref, pin) or "untyped"
            row("decoupling", "pass" if dmm <= lim else "fail", f"decoupling:{ref}.{pin}:{cref}",
                f"declared {cref} ({comps[cref]['value']}) to {ref}.{pin} ({ptype} pin, measured anyway): {dmm:.3f} mm centre, {e} mm edge",
                value=round(dmm, 3), limit=lim, objects=[ref, cref], finding="R2-T5")
        else:
            row("decoupling", "fail", f"decoupling:{ref}.{pin}:{cref}", f"declared row {d}: {cref} has no pad on {ref}.{pin}'s net ({net})", objects=list(key))
    untyped = sorted({r for r, c in comps.items() if r.startswith("U") and not any(v[1] == "power_in" for v in libparts.get(c["lib"], {}).values())})
    if untyped:
        NOT_CHECKED.append(f"decoupling: {', '.join(untyped)} have no power_in pins in the netlist (vendored symbols typed input?): only declared rows cover them")
    COVERAGE.append(f"decoupling: {n_pins} power_in pins on non-ground nets, {len(declared)} declared rows (measured whatever the pin type), limit {max_mm} mm")


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


def parse_value(s):
    """'4.7k' -> 4700, '2k2' -> 2200, '100nF' -> 1e-7, '4.7uH' -> 4.7e-6, '10R' -> 10, '0.01' -> 0.01."""
    m = re.match(r"^\s*([\d.]+)\s*([pnumkKMGrR]?)\s*([\d]*)\s*(?:ohm|Ohm|OHM|Ω|R|F|H|V|A|W)?(?:\s|$|,|/)", s.strip() + " ")
    if not m:
        return None
    whole, unit, frac = m.groups()
    val = float(whole + ("." + frac if frac else "")) if whole.replace(".", "", 1).isdigit() else None
    if val is None:
        return None
    return val * {"p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9, "r": 1, "R": 1, "": 1}[unit]


def ipc2221_width_mm(i_a, rise_c=20.0, oz=1.0, internal=False):
    """IPC-2221 trace width for a current and temperature rise: A[mil^2] = (I / (k * dT^0.44))^(1/0.725),
    k = 0.048 external, 0.024 internal; width = A / (1.378 * oz) mil."""
    k = 0.024 if internal else 0.048
    area = (i_a / (k * rise_c ** 0.44)) ** (1 / 0.725)
    return area / (1.378 * oz) * 0.0254


def check_currents(CFG, NL, B):
    cur = CFG.get("currents", {})
    if not cur:
        NOT_CHECKED.append("currents: no currents block (amps per net) so trace widths were not checked against IPC-2221")
        return
    oz = CFG.get("copper_oz", {"outer": 1.0, "inner": 0.5})
    rise = float(CFG.get("rise_c", 20.0))
    outer = {pcbnew.F_Cu, pcbnew.B_Cu}
    for net, amps in cur.items():
        if B.FindNet(net) is None:
            row("currents", "fail", f"currents:{net}", f"declared net {net} is not on the board", objects=[net]); continue
        amps = float(amps)
        need_o = ipc2221_width_mm(amps, rise, float(oz.get("outer", 1.0)), False)
        need_i = ipc2221_width_mm(amps, rise, float(oz.get("inner", 0.5)), True)
        tracks = [t for t in B.GetTracks() if t.GetClass() != "PCB_VIA" and t.GetNetname() == net]
        zones = [z for z in B.Zones() if z.GetNetname() == net and z.IsFilled()]
        wo = min((pcbnew.ToMM(t.GetWidth()) for t in tracks if t.GetLayer() in outer), default=None)
        wi = min((pcbnew.ToMM(t.GetWidth()) for t in tracks if t.GetLayer() not in outer), default=None)
        bad = []
        if wo is not None and wo + 1e-6 < need_o:
            bad.append(f"outer {wo:.3f} < {need_o:.3f}")
        if wi is not None and wi + 1e-6 < need_i:
            bad.append(f"inner {wi:.3f} < {need_i:.3f}")
        if not tracks and not zones:
            row("currents", "fail", f"currents:{net}", f"{net} {amps} A: no tracks and no filled zone on the net", objects=[net], finding="R2"); continue
        msg = (f"{net} {amps} A at {rise} degC rise: needs {need_o:.3f} mm outer ({oz.get('outer', 1.0)} oz), {need_i:.3f} mm inner "
               f"({oz.get('inner', 0.5)} oz); narrowest outer {wo if wo is None else round(wo, 3)}, inner {wi if wi is None else round(wi, 3)}"
               + (f"; pour on {', '.join(B.GetLayerName(z.GetFirstLayer()) for z in zones)}" if zones else ""))
        st = "fail" if bad else ("warn" if not tracks else "pass")
        if not tracks:
            msg += "; no tracks: carried by pours only, which this row does not size (declare a feeds row per pin)"
        row("currents", st, f"currents:{net}", msg + ("; " + "; ".join(bad) if bad else ""),
            value=wo if wo is not None else wi, limit=round(need_o, 3), objects=[net], finding="R2")
    COVERAGE.append(f"currents: {len(cur)} nets by IPC-2221 external/internal formulas against the narrowest track per layer; pours noted, not sized")


def via_ampacity_a(drill_mm, rise_c=20.0, plating_mm=0.025):
    """IPC-2221 internal formula on the via barrel cross-section (pi * d * plating); 25 um plating is JLC's minimum."""
    area_mil2 = 3.14159 * (drill_mm / 0.0254) * (plating_mm / 0.0254)
    return 0.024 * rise_c ** 0.44 * area_mil2 ** 0.725


def check_feeds(CFG, NL, B):
    feeds = CFG.get("feeds", [])
    if not feeds:
        NOT_CHECKED.append("feeds: no feeds rows (pad, amps, within_mm) so what feeds the high-current pins (vias, tracks; pours are not sized) was not measured")
        return
    fps = pcbq.fp_map(B)
    rise = float(CFG.get("rise_c", 20.0))
    oz = CFG.get("copper_oz", {"outer": 1.0, "inner": 0.5})
    vias = [t for t in B.GetTracks() if t.GetClass() == "PCB_VIA"]
    tracks = [t for t in B.GetTracks() if t.GetClass() != "PCB_VIA"]
    for f in feeds:
        try:
            pad = pcbq.pad_of(fps, f["pad"])
        except SystemExit:
            row("feeds", "fail", f"feeds:{f.get('pad')}", f"no pad {f.get('pad')}"); continue
        net = pad.GetNetname()
        amps = float(f["amps"]); within = float(f.get("within_mm", 2.0))
        near = [v for v in vias if v.GetNetname() == net and pcbq.cc(pad, v) <= within]
        via_a = sum(via_ampacity_a(pcbnew.ToMM(v.GetDrillValue()), rise) for v in near)
        pos = pad.GetPosition()
        touching = [tr for tr in tracks if tr.GetNetname() == net and (tr.GetStart() == pos or tr.GetEnd() == pos or pad.HitTest(tr.GetStart()) or pad.HitTest(tr.GetEnd()))]
        outer = {pcbnew.F_Cu, pcbnew.B_Cu}
        trk_a = 0.0
        for tr in touching:
            w = pcbnew.ToMM(tr.GetWidth())
            internal = tr.GetLayer() not in outer
            k = 0.024 if internal else 0.048
            area = w / 0.0254 * 1.378 * float(oz.get("inner" if internal else "outer", 1.0))
            trk_a += k * rise ** 0.44 * area ** 0.725
        total = via_a + trk_a
        zones = [z for z in B.Zones() if z.GetNetname() == net and z.IsFilled()]
        msg = (f"{f['pad']} ({net}) needs {amps} A: {len(near)} via(s) within {within} mm = {via_a:.2f} A"
               f" ({', '.join(str(round(pcbnew.ToMM(v.GetDrillValue()), 2)) for v in near) or 'none'}), {len(touching)} track(s) touching = {trk_a:.2f} A; total {total:.2f} A"
               + ("; a pour also reaches the pad, its neck is NOT sized" if zones else ""))
        row("feeds", "pass" if total + 1e-9 >= amps else "fail", f"feeds:{f['pad']}", msg, value=round(total, 2), limit=amps, objects=[f["pad"].split(".")[0]], finding="R2-T5")
    COVERAGE.append(f"feeds: {len(feeds)} pads; via ampacity by IPC-2221 internal on the barrel (25 um plating), tracks by width; pour fingers are not measured")


def check_thermal_vias(CFG, NL, B):
    tv = CFG.get("thermal_vias", {})
    if not tv:
        NOT_CHECKED.append("thermal_vias: no thermal_vias block (ref, pad, min, within_mm) so stitching vias were not counted")
        return
    fps = pcbq.fp_map(B)
    vias = [t for t in B.GetTracks() if t.GetClass() == "PCB_VIA"]
    for ref, d in tv.items():
        if ref not in fps:
            row("thermal_vias", "fail", f"thermal_vias:{ref}", f"{ref} not on the board", objects=[ref]); continue
        padnum = str(d.get("pad", "EP"))
        pads = [p for p in fps[ref].Pads() if p.GetNumber() == padnum]
        if not pads:
            row("thermal_vias", "fail", f"thermal_vias:{ref}", f"{ref} has no pad {padnum}", objects=[ref]); continue
        pad = pads[0]
        within = float(d.get("within_mm", max(pcbnew.ToMM(pad.GetSize().x), pcbnew.ToMM(pad.GetSize().y)) / 2 + 0.3))
        n = sum(1 for v in vias if v.GetNetname() == pad.GetNetname() and pcbq.cc(pad, v) <= within)
        need = int(d.get("min", 1))
        drills = sorted({round(pcbnew.ToMM(v.GetDrillValue()), 2) for v in vias if v.GetNetname() == pad.GetNetname() and pcbq.cc(pad, v) <= within})
        row("thermal_vias", "pass" if n >= need else "fail", f"thermal_vias:{ref}",
            f"{ref} pad {padnum} ({pad.GetNetname()}): {n} vias within {within:.2f} mm (min {need}), drills {drills}", value=n, limit=need, objects=[ref], finding="R2")
    COVERAGE.append(f"thermal_vias: {len(tv)} pads; vias on the pad's net within within_mm of the pad centre")


def check_via_in_pad(CFG, NL, B):
    c = CFG.get("via_in_pad")
    if c is None:
        NOT_CHECKED.append("via_in_pad: no via_in_pad block, so vias standing in SMD pads were not looked for")
        return
    allow = set(c.get("allow", [])) | {f"{r}.{d.get('pad', 'EP')}" for r, d in CFG.get("thermal_vias", {}).items()}
    refs = {a.split(".")[0] for a in allow}
    pads = [(f.GetReference(), q) for f in B.GetFootprints() for q in f.Pads() if q.GetAttribute() == pcbnew.PAD_ATTRIB_SMD]
    vias = [t for t in B.GetTracks() if t.GetClass() == "PCB_VIA"]
    bad = exempt = 0
    for v in vias:
        for ref, q in pads:
            if not q.HitTest(v.GetPosition(), v.GetWidth(pcbnew.F_Cu) // 2):
                continue
            num = q.GetNumber()
            if f"{ref}.{num}" in allow or (not num and ref in refs):   # unnumbered copper is an exposed pad's split
                exempt += 1
                continue
            bad += 1
            x, y = pcbnew.ToMM(v.GetPosition().x), pcbnew.ToMM(v.GetPosition().y)
            row("via_in_pad", "fail", f"via_in_pad:{ref}.{num}:{x:.2f},{y:.2f}", f"{v.GetNetname()} via at ({x:.2f}, {y:.2f}) touches "
                f"{ref}.{num}: move it off the pad on a short neck", objects=[ref], finding="SPIKE-6")
    if not bad:
        row("via_in_pad", "pass", "via_in_pad:all", f"{len(vias)} vias, none in an SMD pad; {exempt} in declared exposed pads", value=0, limit=0)
    COVERAGE.append(f"via_in_pad: {len(vias)} vias against {len(pads)} SMD pads, {exempt} exempt in declared exposed pads")


def check_edge_margin(CFG, NL, B):
    c = CFG.get("edge_margin")
    if c is None:
        NOT_CHECKED.append("edge_margin: no edge_margin block, so copper and parts near the outline were not measured")
        return
    tr, vi, pa = float(c.get("tracks_mm", 1.0)), float(c.get("vias_mm", 1.0)), float(c.get("parts_mm", 1.0))
    conn, skip = float(c.get("connector_mm", 1.5)), set(c.get("skip_refs", []))
    bb = B.GetBoardEdgesBoundingBox()
    x0, y0, x1, y1 = (pcbnew.ToMM(v) for v in (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()))
    dist = lambda v: min(pcbnew.ToMM(v.x) - x0, x1 - pcbnew.ToMM(v.x), pcbnew.ToMM(v.y) - y0, y1 - pcbnew.ToMM(v.y))
    conn_pads = {}
    for f in B.GetFootprints():
        if re.match(r"J\d", f.GetReference()):
            for q in f.Pads():
                conn_pads.setdefault(q.GetNetname(), []).append(q)
    worst = {}
    for t in B.GetTracks():
        if t.GetClass() == "PCB_VIA":
            d = dist(t.GetPosition()) - pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) / 2
            if d < vi:
                worst[f"via {t.GetNetname()}"] = min(d, worst.get(f"via {t.GetNetname()}", 99))
            continue
        for pt in (t.GetStart(), t.GetEnd()):
            d = dist(pt) - pcbnew.ToMM(t.GetWidth()) / 2
            if d < tr and not any(q.HitTest(pt, pcbnew.FromMM(conn)) for q in conn_pads.get(t.GetNetname(), [])):
                worst[f"track {t.GetNetname()}"] = min(d, worst.get(f"track {t.GetNetname()}", 99))
    for f in B.GetFootprints():
        ref = f.GetReference()
        if ref in skip or re.match(r"(J|H|MH|FID)\d", ref):
            continue
        ds = [min(pcbnew.ToMM(b.GetLeft()) - x0, x1 - pcbnew.ToMM(b.GetRight()), pcbnew.ToMM(b.GetTop()) - y0, y1 - pcbnew.ToMM(b.GetBottom()))
              for b in (q.GetBoundingBox() for q in f.Pads())]
        if ds and min(ds) < pa:
            worst[f"part {ref}"] = min(ds)
    for k, d in sorted(worst.items(), key=lambda kv: kv[1]):
        row("edge_margin", "fail", f"edge_margin:{k}", f"{k} {d:.2f} mm from the outline", value=round(d, 2), objects=k.split()[1:], finding="SPIKE-6")
    if not worst:
        row("edge_margin", "pass", "edge_margin:all", f"tracks {tr}, vias {vi}, parts {pa} mm off the outline")
    COVERAGE.append(f"edge_margin: tracks {tr}, vias {vi}, parts {pa} mm off the outline bounding box, connector exits within {conn} mm exempt")


def check_gnd_islands(CFG, NL, B, board_path):
    c = CFG.get("gnd_islands")
    if c is None:
        NOT_CHECKED.append("gnd_islands: no gnd_islands block, so ground fill KiCad rips up was not looked for")
        return
    import shutil, tempfile
    from pcblib.board import Board
    gnd, warn, mx = c.get("ground", "GND"), float(c.get("warn_mm2", 0.5)), float(c.get("max_mm2", 2.0))
    d = tempfile.mkdtemp(prefix="pcbcheck-isl-")
    for ext in (".kicad_pcb", ".kicad_pro"):
        src = os.path.splitext(board_path)[0] + ext
        if os.path.exists(src):
            shutil.copy(src, d)
    isl = Board.load(os.path.join(d, os.path.basename(board_path))).fill_islands(gnd)
    shutil.rmtree(d, ignore_errors=True)
    big = [i for i in isl if i["area_mm2"] >= warn]
    for i in sorted(big, key=lambda i: -i["area_mm2"]):
        x0, y0, x1, y1 = i["bbox"]
        row("gnd_islands", "fail" if i["area_mm2"] >= mx else "warn", f"gnd_islands:{i['layer']}:{(x0 + x1) / 2:.1f},{(y0 + y1) / 2:.1f}",
            f"{i['area_mm2']} mm^2 of {gnd} on {i['layer']} around ({(x0 + x1) / 2:.1f}, {(y0 + y1) / 2:.1f}) has no ground copper: "
            f"`pcb route ground-islands`, or move what cuts it off", value=i["area_mm2"], limit=mx, finding="SPIKE-6")
    if not big:
        row("gnd_islands", "pass", "gnd_islands:all", f"no {gnd} fill island over {warn} mm^2 ({len(isl)} slivers under it)", value=0)
    COVERAGE.append(f"gnd_islands: {len(isl)} unfed pieces of {gnd} with island removal off, {len(big)} over {warn} mm^2")


def check_feed_room(CFG, NL, B, board_path):
    fr = CFG.get("feed_room")
    if fr is None:
        NOT_CHECKED.append("feed_room: no feed_room block, so whether each feeds pad has room for its pour and vias was not tried")
        return
    fr = fr if isinstance(fr, dict) else {}
    from pcblib.board import Board
    bd = Board(pcbnew.LoadBoard(board_path), board_path)   # a second copy: the trial copper never reaches the other rows
    bd.clearance = pcbnew.ToMM(bd.b.GetDesignSettings().m_MinClearance) or 0.2
    skip = set(fr.get("skip", []))
    fps = pcbq.fp_map(bd.b)
    rows = []
    for f in CFG.get("feeds", []):
        pad = f.get("pad", "")
        if pad in skip:
            continue
        try:
            pd = pcbq.pad_of(fps, pad.split(",")[0] if "," in pad else pad)
        except SystemExit:
            continue
        if pd.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
            continue   # through-hole pins reach the planes through their barrel
        rows.append((float(f["amps"]), pad, f))
    res = bd.plan_feeds([(pad, amps) for amps, pad, _ in rows])
    for amps, pad, f in sorted(rows, key=lambda r: -r[0]):
        ref = pad.split(".")[0]
        r = res[pad]
        if "error" not in r:
            row("feed_room", "pass", f"feed_room:{pad}", f"{pad} {amps} A: {r['vias']} vias fit (splay {r['splay']}, length {r['length']} mm, "
                f"{r['across']} across), reserved for the pins after it", value=r["vias"], objects=[ref], finding="FEED-2")
        else:
            msg = r["error"]
            blockers = sorted(set(re.findall(r"on ([A-Z]+[0-9]+)\.", msg)) | set(re.findall(r"inside feed_([A-Z]+[0-9]+_[0-9_]+)", msg)) - {ref})
            row("feed_room", "fail", f"feed_room:{pad}", f"{pad} {amps} A: no room for a pour and vias; in the way: "
                f"{', '.join(blockers) or 'see message'} ({msg[-160:]})", objects=[ref] + [b for b in blockers if not b.startswith(ref + "_")], finding="FEED-2")
    COVERAGE.append(f"feed_room: {len(rows)} SMD feeds pads tried with pcblib pad_feed_search, biggest current first, each reserved")


def check_refplane(CFG, NL, B):
    rp = CFG.get("refplane")
    if not rp:
        NOT_CHECKED.append("refplane: no refplane block, so whether signals run over solid ground was not measured")
        return
    rp = rp if isinstance(rp, dict) else {}
    gnd = rp.get("ground", "GND")
    step = float(rp.get("step_mm", 0.25))
    max_gap = float(rp.get("max_gap_mm", 0.0))
    skip = set(rp.get("skip_nets", [])) | {gnd}
    stack = list(B.GetEnabledLayers().CuStack())
    if len(stack) < 3:
        NOT_CHECKED.append(f"refplane: {len(stack)} copper layers, no inner reference plane to check")
        return
    zones = {}
    unfilled = []
    for z in B.Zones():
        if z.GetIsRuleArea() or z.GetNetname() != gnd:
            continue
        for L in z.GetLayerSet().CuStack():
            if z.HasFilledPolysForLayer(L) and z.GetFilledPolysList(L).OutlineCount():
                zones.setdefault(L, []).append(z)
            else:
                unfilled.append(B.GetLayerName(L))
    if unfilled:
        CONFIG_WARNS.append(f"refplane: {gnd} zones with no fill on {sorted(set(unfilled))}; run `pcb route fill` first")
    # the net's own vias and through-hole pads punch an antipad in every plane: skip points that close to them
    # ... and the through-hole pads of every footprint the net lands on: a track entering its own connector crosses the
    # antipads of the neighbouring pins on both planes alike, which no plan can avoid (SIG-4: 1.6 mm of nSLEEP under J3's
    # pin field decided the opus board's hard limit)
    holes = {}
    for t in B.GetTracks():
        if t.GetClass() == "PCB_VIA":
            holes.setdefault(t.GetNetname(), []).append((t.GetPosition(), t.GetWidth(pcbnew.F_Cu) / 2))
    fp_nets = {}
    for f in B.GetFootprints():
        for pd in f.Pads():
            if pd.GetNetname():
                fp_nets.setdefault(f.GetReference(), set()).add(pd.GetNetname())
    conn = pcbnew.FromMM(float(rp.get("connector_mm", 1.5))) - pcbnew.FromMM(float(rp.get("antipad_mm", 0.5)))
    for f in B.GetFootprints():
        # a 2.54 mm pin field with the plane's clearance leaves no web between pins, so the halo here is connector_mm
        pth = [(pd.GetPosition(), max(pd.GetSize().x, pd.GetSize().y) / 2 + conn) for pd in f.Pads() if pd.GetAttribute() == pcbnew.PAD_ATTRIB_PTH]
        for n in fp_nets.get(f.GetReference(), ()):
            holes.setdefault(n, []).extend(pth)
    halo = pcbnew.FromMM(float(rp.get("antipad_mm", 0.5)))
    per = {}
    for t in B.GetTracks():
        if t.GetClass() == "PCB_VIA" or t.GetNetname() in skip:
            continue
        L = t.GetLayer()
        if L not in stack:
            continue
        i = stack.index(L)
        refs = [stack[j] for j in (i - 1, i + 1) if 0 <= j < len(stack)]
        a, b = t.GetStart(), t.GetEnd()
        length = pcbnew.ToMM(t.GetLength())
        n = max(1, int(length / step))
        own = holes.get(t.GetNetname(), [])
        d = per.setdefault(t.GetNetname(), {"mm": 0.0, "bad_mm": 0.0, "gaps": 0, "layers": {}, "where": []})
        d["mm"] += length
        prev_bad = False
        for k in range(n + 1):
            x = a.x + (b.x - a.x) * k / n; y = a.y + (b.y - a.y) * k / n
            pt = pcbnew.VECTOR2I(int(x), int(y))
            if any((pt.x - c.x) ** 2 + (pt.y - c.y) ** 2 <= (r + halo) ** 2 for c, r in own):
                prev_bad = False
                continue
            ok = any(z.HitTestFilledArea(R, pt) for R in refs for z in zones.get(R, []))
            if not ok:
                d["bad_mm"] += length / (n + 1)
                ln = B.GetLayerName(L)
                d["layers"][ln] = d["layers"].get(ln, 0.0) + length / (n + 1)
                if not prev_bad:
                    d["gaps"] += 1
                    if len(d["where"]) < 3:
                        d["where"].append(f"({pcbnew.ToMM(pt.x):.1f}, {pcbnew.ToMM(pt.y):.1f}) {B.GetLayerName(L)}")
            prev_bad = not ok
    # SIG-1: the limit depends on the net's bucket. 3 and 4 are hard (max_gap_mm, 0 by default); 2 is a cost that warns
    # above mid_max_mm; 1 and the rails are a cost only (the row carries the mm for the routing search to weigh).
    buckets = signal_buckets(CFG, NL)
    mid_max = float(rp.get("mid_max_mm", 5.0))
    bad_total, by_layer, by_bucket = 0.0, {}, {}
    for net, d in sorted(per.items()):
        for k, v in d["layers"].items():
            by_layer[k] = by_layer.get(k, 0.0) + v
        bk = buckets.get(net, 1)
        by_bucket[bk] = by_bucket.get(bk, 0.0) + d["bad_mm"]
        if bk in (3, 4):
            st, lim = ("fail" if d["bad_mm"] > max_gap + 1e-6 else "pass"), max_gap
        elif bk == 2:
            st, lim = ("warn" if d["bad_mm"] > mid_max + 1e-6 else "pass"), mid_max
        else:
            st, lim = "pass", None
        bad_total += d["bad_mm"]
        msg = (f"{net} [bucket {bk}]: {d['bad_mm']:.1f} of {d['mm']:.1f} mm not over solid {gnd} on the next layer, {d['gaps']} gap(s)"
               + (f" ({', '.join(f'{k} {v:.1f} mm' for k, v in sorted(d['layers'].items()))}), first at {'; '.join(d['where'])}" if d["gaps"] else ""))
        row("refplane", st, f"refplane:{net}", msg, value=round(d["bad_mm"], 2), limit=lim, objects=[net], finding="REFPLANE-1",
            bucket=bk, gaps=d["gaps"])
    COVERAGE.append(f"refplane: {len(per)} nets, tracks sampled every {step} mm against {gnd} fill on the adjacent layer(s); "
                    f"{bad_total:.1f} mm unreferenced in total ({', '.join(f'{k} {v:.1f}' for k, v in sorted(by_layer.items()))}); "
                    f"by bucket {', '.join(f'{k}: {v:.1f}' for k, v in sorted(by_bucket.items(), key=lambda kv: str(kv[0])))}")


def signal_buckets(CFG, NL):
    """net -> bucket from the `signals` block (SIG-1); nets the block does not name are bucket 1, rails P, GND skipped."""
    import pcbsig
    nets = {n: [(r, p, "") for r, p in nodes] for n, nodes in NL[2].items()}
    if not CFG.get("signals"):
        CONFIG_WARNS.append("signals: no signals block, so every net is bucket 1 (best effort over ground); see `pcb signals`")
    return pcbsig.buckets(CFG, nets)


def gnd_returns(B, gnd):
    """Positions of the ground vias and through-hole pads: where a return current can move between In1 and In2."""
    pts = [t.GetPosition() for t in B.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetname() == gnd]
    for f in B.GetFootprints():
        for pd in f.Pads():
            if pd.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and pd.GetNetname() == gnd:
                pts.append(pd.GetPosition())
    return pts


def check_return_via(CFG, NL, B):
    """SIG-2: a via on a fast net moves its return from one ground plane to the other, so a ground via (or through-hole
    ground pad) has to sit within max_mm of it. Hard for buckets 3 and 4, a warned cost for 2, cost only for 1."""
    rv = CFG.get("return_via")
    if rv is None:
        NOT_CHECKED.append("return_via: no return_via block, so ground vias beside the fast nets' layer changes were not measured")
        return
    rv = rv if isinstance(rv, dict) else {}
    gnd = rv.get("ground", "GND")
    lim = {4: float(rv.get("max_mm_4", 1.0)), 3: float(rv.get("max_mm_3", 2.0)), 2: float(rv.get("max_mm_2", 5.0))}
    stack = list(B.GetEnabledLayers().CuStack())
    if len(stack) < 4:
        NOT_CHECKED.append(f"return_via: {len(stack)} copper layers, one reference plane at most, no plane change to check")
        return
    buckets = signal_buckets(CFG, NL)
    pts = gnd_returns(B, gnd)
    per = {}
    for t in B.GetTracks():
        if t.GetClass() != "PCB_VIA" or t.GetNetname() in ("", gnd):
            continue
        n = t.GetNetname()
        bk = buckets.get(n, 1)
        if bk == "P":
            continue
        q = t.GetPosition()
        d = min((pcbnew.ToMM(int(((q.x - g.x) ** 2 + (q.y - g.y) ** 2) ** 0.5)) for g in pts), default=999.0)
        per.setdefault(n, []).append((round(d, 2), round(pcbnew.ToMM(q.x), 1), round(pcbnew.ToMM(q.y), 1)))
    for n, vs in sorted(per.items()):
        bk = buckets.get(n, 1)
        worst = max(v[0] for v in vs)
        bad = [v for v in vs if bk in lim and v[0] > lim[bk] + 1e-6]
        st = "pass" if not bad else ("fail" if bk in (3, 4) else "warn")
        where = "; ".join(f"({x}, {y}) {d} mm" for d, x, y in bad[:3])
        msg = (f"{n} [bucket {bk}]: {len(vs)} via(s), nearest {gnd} via or through-hole pad {min(v[0] for v in vs)}-{worst} mm"
               + (f"; {len(bad)} beyond {lim[bk]} mm: {where}" if bad else ""))
        row("return_via", st, f"return_via:{n}", msg, value=worst, limit=lim.get(bk), objects=[n], finding="SIG-2",
            bucket=bk, vias=len(vs), bad=len(bad))
    COVERAGE.append(f"return_via: {sum(len(v) for v in per.values())} signal vias on {len(per)} nets against {len(pts)} {gnd} vias and "
                    f"through-hole pads; limits bucket 4 {lim[4]}, 3 {lim[3]}, 2 {lim[2]} mm")


def check_exposure(CFG, NL, B):
    """SIG-3: same-layer exposure to an aggressor's copper. Every track of a non-local signal net sampled every step_mm;
    a sample within within_mm of the aggressor's copper on the same layer (tracks, pads, zone fill) counts. Per net the
    exposed mm, weighted by victim_weight for victims; nets local to the aggressor (every pad on a footprint that also
    carries the aggressor) and the rails are left out. Aggressors default to the switch node: the inductor net that
    also reaches an IC pin."""
    ex = CFG.get("exposure")
    if ex is None:
        NOT_CHECKED.append("exposure: no exposure block, so signal copper beside the switch node on the same layer was not measured")
        return
    ex = ex if isinstance(ex, dict) else {}
    within = pcbnew.FromMM(float(ex.get("within_mm", 1.0)))
    step = float(ex.get("step_mm", 0.25))
    vw = float(ex.get("victim_weight", 3.0))
    max_mm = ex.get("max_mm")
    buckets = signal_buckets(CFG, NL)
    import pcbsig
    victims = pcbsig.victims(CFG)
    aggr = list(ex.get("aggressors") or [])
    if not aggr:
        rails = set((CFG.get("rails") or {}).keys())
        for f in B.GetFootprints():
            if not f.GetReference().startswith("L"):
                continue
            for pd in f.Pads():
                n = pd.GetNetname()
                if n and n not in rails and any(q.GetParentFootprint().GetReference().startswith("U") for g in B.GetFootprints() for q in g.Pads() if q.GetNetname() == n):
                    aggr.append(n)
        aggr = sorted(set(aggr))
    if not aggr:
        NOT_CHECKED.append("exposure: no aggressor named and no switch node found (an inductor net that reaches an IC pin)")
        return
    # the aggressor's copper per layer: effective shapes of its tracks and pads, filled polys of its zones
    shapes, polys = {}, {}
    carriers = set()
    for t in B.GetTracks():
        if t.GetNetname() in aggr:
            if t.GetClass() == "PCB_VIA":
                for L in B.GetEnabledLayers().CuStack():
                    shapes.setdefault(L, []).append(t.GetEffectiveShape(L))
            else:
                shapes.setdefault(t.GetLayer(), []).append(t.GetEffectiveShape(t.GetLayer()))
    for f in B.GetFootprints():
        for pd in f.Pads():
            if pd.GetNetname() in aggr:
                carriers.add(f.GetReference())
                for L in pd.GetLayerSet().CuStack():
                    shapes.setdefault(L, []).append(pd.GetEffectiveShape(L))
    for z in B.Zones():
        if z.GetNetname() in aggr and not z.GetIsRuleArea():
            for L in z.GetLayerSet().CuStack():
                if z.HasFilledPolysForLayer(L):
                    polys.setdefault(L, []).append(z.GetFilledPolysList(L))
    local = {n for n, nodes in NL[2].items() if nodes and all(r in carriers for r, _ in nodes)}
    per = {}
    for t in B.GetTracks():
        n = t.GetNetname()
        if t.GetClass() == "PCB_VIA" or n in aggr or n in local or buckets.get(n, 1) == "P" or gnd_like(n) or not n:
            continue
        L = t.GetLayer()
        if L not in shapes and L not in polys:
            continue
        a, b = t.GetStart(), t.GetEnd()
        length = pcbnew.ToMM(t.GetLength())
        k = max(1, int(length / step))
        hit = 0
        for i in range(k):
            pt = pcbnew.VECTOR2I(int(a.x + (b.x - a.x) * (i + 0.5) / k), int(a.y + (b.y - a.y) * (i + 0.5) / k))
            if any(sh.Collide(pt, within) for sh in shapes.get(L, [])) or any(pl.Collide(pt, within) for pl in polys.get(L, [])):
                hit += 1
        if hit:
            d = per.setdefault(n, {"mm": 0.0, "layers": {}})
            d["mm"] += length * hit / k
            ln = B.GetLayerName(L)
            d["layers"][ln] = d["layers"].get(ln, 0.0) + length * hit / k
    total = 0.0
    for n, d in sorted(per.items(), key=lambda kv: -kv[1]["mm"]):
        w = vw if n in victims else 1.0
        cost = d["mm"] * w
        total += cost
        st = "pass" if max_mm is None or cost <= float(max_mm) + 1e-6 else ("fail" if n in victims else "warn")
        msg = (f"{n} [bucket {buckets.get(n, 1)}{', victim' if n in victims else ''}]: {d['mm']:.1f} mm within {pcbnew.ToMM(within):g} mm of "
               f"{'/'.join(aggr)} copper on the same layer ({', '.join(f'{k} {v:.1f}' for k, v in sorted(d['layers'].items()))}), weighted {cost:.1f}")
        row("exposure", st, f"exposure:{n}", msg, value=round(cost, 2), limit=max_mm, objects=[n], finding="SIG-3",
            bucket=buckets.get(n, 1), victim=n in victims, mm=round(d["mm"], 2))
    COVERAGE.append(f"exposure: aggressors {', '.join(aggr)}, local nets left out {', '.join(sorted(local))}; "
                    f"{len(per)} nets exposed, {total:.1f} mm weighted in total")


def check_refstat(CFG, NL, B):
    rows = CFG.get("refstat", [])
    if not rows:
        NOT_CHECKED.append("refstat: no refstat rows (corpus reference circuits, tools/bench/data/refstat-rows.json) declared")
        return
    comps, libparts, nets, padnet = NL
    fps = pcbq.fp_map(B)
    n_inst = 0
    for r in rows:
        part, cpin, pat = r["part"], r["pin"], r.get("pattern", {})
        if "class" not in pat:
            NOT_CHECKED.append(f"refstat: {part} {cpin} {pat.get('feature')}: two-hop patterns are counted, not checked"); continue
        rx = pcbrefstat.part_regex(part)
        cls, band, to = pat["class"], pat["band"], pat["to"]
        lim = pat.get("max_mm")
        corpus = f"corpus: {r.get('support', 0) * 100:.0f} % of {r.get('n', '?')} designs" + (f", p90 {lim} mm on {r.get('n_board')} boards" if lim else "")
        for ref, c in sorted(comps.items()):
            if not (rx.search(c["value"]) or rx.search(c["lib"][1] or "")):
                continue
            pins = libparts.get(c["lib"], {})
            canon = {num: pcbrefstat.canon_pin(part, num, nm) for num, (nm, _t) in pins.items()}
            for (rr, num), _net in padnet.items():
                if rr == ref and num not in canon:
                    canon[num] = pcbrefstat.canon_pin(part, num, "")
            nums = sorted(n for n, cp in canon.items() if cp == cpin and (ref, n) in padnet)
            rid = f"refstat:{ref}.{cpin}:{pat['feature']}"
            if not nums:
                row("refstat", "warn", rid, f"{ref} ({c['value']}): no {cpin} pin connected in the netlist; {corpus}", objects=[ref], finding="SPIKE2")
                continue
            n_inst += 1
            net = padnet[(ref, nums[0])]
            ic_nets = {}
            for (rr, num), nn in padnet.items():
                if rr == ref:
                    ic_nets.setdefault(nn, canon.get(num))
            found = []
            for cref, cc_ in comps.items():
                if cref == ref or pcbrefstat.comp_class(cref, cc_["lib"][1]) != cls or not pcbrefstat.band_matches(cls, band, cc_["value"]):
                    continue
                cp = [(p, n) for (x, p), n in padnet.items() if x == cref]
                if len(cp) != 2 or net not in [n for _, n in cp]:
                    continue
                other = [n for _, n in cp if n != net]
                if not other:
                    continue
                o = other[0]
                side = "GND" if gnd_like(o) else ("IC:" + ic_nets[o]) if o in ic_nets else "PWR" if pcbrefstat.power_like(o) else "SIG"
                if side == to:
                    found.append((cref, cc_["value"], [p for p, n in cp if n == net][0]))
            want = f"{cls} {band} from {cpin} ({net}) to {to}"
            if not found:
                row("refstat", "fail", rid, f"{ref} ({c['value']}): no {want}; {corpus}", objects=[ref, net], finding="SPIKE2",
                    support=r.get("support"))
                continue
            dist = []
            if ref in fps:
                for cref, val, pnum in found:
                    if cref in fps:
                        try:
                            dist.append((pcbq.cc(pcbq.pad_of(fps, f"{ref}.{nums[0]}"), pcbq.pad_of(fps, f"{cref}.{pnum}")), cref, val))
                        except SystemExit:
                            pass
            dist.sort()
            if lim is not None and dist:
                d, cref, val = dist[0]
                row("refstat", "pass" if d <= float(lim) else "fail", rid,
                    f"{ref} ({c['value']}): {want}: nearest {cref} ({val}) at {d:.2f} mm pad to pad (corpus p90 {lim}); {corpus}",
                    value=round(d, 3), limit=lim, objects=[ref, cref], finding="SPIKE2", support=r.get("support"))
            else:
                row("refstat", "pass", rid, f"{ref} ({c['value']}): {want}: {', '.join(f[0] + ' ' + f[1] for f in found)}"
                    + (f"; nearest {dist[0][1]} at {dist[0][0]:.2f} mm" if dist else "") + f"; {corpus}",
                    value=round(dist[0][0], 3) if dist else None, objects=[ref] + [f[0] for f in found], finding="SPIKE2", support=r.get("support"))
    COVERAGE.append(f"refstat: {len(rows)} corpus rows over {n_inst} part pins found in the netlist")


def check_irdrop(CFG, NL, B):
    """Solve every net that has `feeds` rows on its copper (`pcb irdrop`, pcbir.py) and fail what the current crosses
    above its IPC-2221 rating: necks, via and plated-hole barrels, sinks with no path (spike #3, C1)."""
    ir = CFG.get("irdrop")
    if ir is None:
        NOT_CHECKED.append("irdrop: no irdrop block, so the feeds currents were not solved on the copper (necks, spokes, barrels)")
        return
    ir = ir if isinstance(ir, dict) else {}
    import pcbir
    fps = pcbq.fp_map(B)
    sources = {k: v for k, v in ir.get("sources", {}).items() if not k.startswith("_")}
    def expand(tok, amps):   # "U6.4,5,6" (a feeds row over a pin group) -> each pad its share
        ref, _, nums = tok.partition(".")
        ps = [f"{ref}.{x}" for x in nums.split(",")]
        return [(q, amps / len(ps)) for q in ps]
    by_net = {}
    for f in CFG.get("feeds", []):
        try:
            pad = pcbq.pad_of(fps, expand(f["pad"], 1)[0][0])
        except SystemExit:
            continue
        by_net.setdefault(pad.GetNetname(), []).append((f["pad"], float(f["amps"])))
    for net in by_net:      # no declared source: the part the rails block names first, if it has pads on the net
        m = re.match(r"\s*([A-Z]+[0-9]+)\b", str(CFG.get("rails", {}).get(net, {}).get("source", "")))
        if net not in sources and m and m.group(1) in fps:
            pads = [f"{m.group(1)}.{p.GetNumber()}" for p in fps[m.group(1)].Pads() if p.GetNetname() == net]
            if pads:
                sources[net] = ",".join(pads)
    h = float(ir.get("grid_mm", 0.1))
    rise = float(CFG.get("rise_c", 20.0))
    bf = os.path.abspath(B.GetFileName())   # one scratch dir per board file: two boards share a stem (motor_channel)
    base = ir.get("out") or os.path.join("/tmp/pcb-irdrop", f"check-{os.path.splitext(os.path.basename(bf))[0]}-{zlib.crc32(bf.encode()):08x}")
    n = 0
    cur = {k: float(v) for k, v in CFG.get("currents", {}).items() if not str(k).startswith("_")}
    for net, feeds in by_net.items():
        src = sources.get(net)
        if not src:
            NOT_CHECKED.append(f"irdrop: {net} has feeds rows but no source (irdrop.sources, or a rails source that names a part on the net)")
            continue
        sinks = [(p, a) for p, a in feeds if p not in src.split(",")]
        # each feeds pad alone at its own amps (the feeds rows are per-pin worst cases at different conditions, so their
        # sum is not a load: rung 2's VIN rows add to 5.3 A on a 4 A rail); a capacitor's amps are ripple, which heats
        # copper as a DC current of the same rms does, so it is rated, its drop not reported. With a `currents` entry for
        # the net and two or more DC pads, one more solve puts the net's declared current through all of them in
        # proportion to their rows (the trunk at the rail current)
        solves = [(p, expand(p, a)) for p, a in sinks]
        dc = [(p, a) for p, a in sinks if not re.match(r"C[0-9]", p)]
        if net in cur and len(dc) > 1:
            tot = sum(a for _, a in dc)
            solves.append((f"{net} {cur[net]:g} A", [(q, round(b * cur[net] / tot, 3)) for p, a in dc for q, b in expand(p, a)]))
        if not solves:   # the only feeds pad is the source: nothing draws current, so nothing was solved (not a pass)
            NOT_CHECKED.append(f"irdrop: {net} has no feeds pad besides its source {src}, so no current was solved on it")
            continue
        found, drops, tsum, worst = [], [], 0.0, {"neck": 0.0, "via": 0.0}
        pad_exit = {}
        for tag, sk in solves:
            try:
                rep = pcbir.run(B, net, src, sk, h, CFG, os.path.join(base, re.sub(r"[^A-Za-z0-9_.-]", "_", f"{net}-{tag}")))
            except (RuntimeError, SystemExit) as e:
                row("irdrop", "fail", f"irdrop:{net}:crash:{tag}", f"solve for {tag} failed: {e}", objects=[net]); continue
            n += 1
            tsum += float(rep.get("extract_s") or 0) + float(rep.get("solve_s") or 0)
            jd = rep.get("judge", {})
            worst["neck"] = max(worst["neck"], jd.get("worst_neck_ratio") or 0.0)
            worst["via"] = max(worst["via"], jd.get("worst_barrel_ratio") or 0.0)
            if not tag.startswith(f"{net} ") and not re.match(r"C[0-9]", tag):
                dv = [x["drop_mV"] for x in rep["sinks"] if x["drop_mV"] is not None]
                drops.append(f"{tag} {sum(b for _, b in sk):g} A {max(dv) if dv else None} mV")
            for u in rep.get("unreached", []):
                found.append(("open", u, 0, 0, 9.9, tag, f"{u} has no copper path from {src} on {net}", [u.split(".")[0]]))
            for k in jd.get("necks", []):
                if k["status"] == "pad":
                    pad_exit[", ".join(k["near_pads"])] = max(k["ratio"], pad_exit.get(", ".join(k["near_pads"]), 0))
                if k["status"] != "fail":
                    continue
                found.append(("neck", k["layer"], k["x"], k["y"], k["ratio"], tag,
                              f"{k['width_mm']} mm wide x {k['length_mm']} mm neck on {k['layer']}{' by ' + ', '.join(k['near_pads']) if k['near_pads'] else ''}: "
                              f"{k['I_A']} A across it against IPC-2221 {k['ipc_A']} A at {rise:g} degC (x{k['ratio']}), {k['J_A_mm2']} A/mm2",
                              [p.split(".")[0] for p in k["near_pads"]]))
            for v in jd.get("barrels", []):
                if v["status"] != "fail":
                    continue
                found.append(("via" if v["what"] == "via" else f"pth:{v['what']}", "", v["x"], v["y"], v["ratio"], tag,
                              (f"{v['n']} x {v['drill_mm']} mm via field" if v["what"] == "via" else f"{v['drill_mm']} mm plated hole {v['what']}")
                              + f": {v['I_A']} A through the barrels against IPC-2221 internal {v['ipc_A']} A on 25 um plating (x{v['ratio']}; "
                              f"busiest barrel {v['max_one_A']} A)", []))
        # one row per place: the same neck or via field failing in several solves is reported once, at its worst
        kept = []
        for f in sorted(found, key=lambda f: -f[4]):
            if any(f[0] == k[0] and f[1] == k[1] and math.hypot(f[2] - k[2], f[3] - k[3]) < 1.0 for k in kept):
                continue
            kept.append(f)
        for kind, lay, x, y, ratio, tag, msg, objs in kept:
            rid = f"irdrop:{net}:open:{lay}" if kind == "open" else f"irdrop:{net}:{kind}{':' + lay if lay else ''}@{x},{y}"
            row("irdrop", "fail", rid, msg + ("" if kind == "open" else f" (solve: {tag})"), value=ratio, limit=1.0, objects=objs, finding="C1")
        row("irdrop", "pass" if not kept else "info", f"irdrop:{net}",
            f"{net} from {src}, {len(solves)} solves: {'; '.join(drops) or 'no DC sink'}; worst neck x{worst['neck']}, worst via field x{worst['via']}, "
            f"{len(kept)} places over"
            + ("; pad exits over IPC, not failed: " + ", ".join(f"{k} x{v}" for k, v in pad_exit.items()) if pad_exit else "")
            + f"; {tsum:.1f} s", value=worst["neck"], limit=1.0, objects=[net], finding="C1")
    COVERAGE.append(f"irdrop: {n} solves at {h} mm on {len(by_net)} nets with feeds rows; necks and barrels by IPC-2221 at {rise:g} degC")


def check_basic_parts(CFG, NL, B, cfg_dir):
    """Every BOM line's LCSC part as JLC basic or extended from a dated cache (tools/bench/jlc_parts.py), with the
    extended-part feeder fee (spike #3, C2: 17 extended types x $3.07 was the largest line of the rung-2 quote)."""
    bp = CFG.get("basic_parts")
    if bp is None:
        NOT_CHECKED.append("basic_parts: no basic_parts block, so JLC basic/extended and the feeder fee were not counted")
        return
    bp = bp if isinstance(bp, dict) else {}
    if bp.get("cache"):   # relative to the config's directory
        path = os.path.join(cfg_dir, bp["cache"])
    else:                 # this repo's cache (the skill is linked from it)
        path = os.environ.get("PCB_JLC_CACHE") or os.path.join(os.path.realpath(HERE), "..", "..", "..", "tools", "bench", "data", "jlc_parts.json")
    if not os.path.exists(path):
        row("basic_parts", "fail", "basic_parts:cache", f"no JLC parts cache at {path} (python3 -I tools/bench/jlc_parts.py fetch BOARD)"); return
    cache = json.load(open(path))
    fee = float(bp.get("fee_usd", cache.get("fee_usd", {}).get(bp.get("assembly", "economic"), 3.07)))
    lines = {}
    for f in sorted(B.GetFootprints(), key=lambda f: f.GetReference()):
        if f.IsDNP() or (f.GetAttributes() & pcbnew.FP_EXCLUDE_FROM_BOM):
            continue
        code = pcbq.field(f, "LCSC").strip()
        if code:
            lines.setdefault(code, []).append(f.GetReference())
    ext, fees = [], 0.0
    for code, refs in sorted(lines.items(), key=lambda kv: kv[1][0]):
        p = cache.get("parts", {}).get(code)
        alt = cache.get("alternatives", {}).get(code, {}).get("basic", [])
        if p is None or p.get("library") == "not found":
            row("basic_parts", "warn", f"basic_parts:{code}", f"{code} ({', '.join(refs)}): not in the cache fetched {cache.get('fetched')}"
                " (run tools/bench/jlc_parts.py fetch)", objects=refs); continue
        stock = p.get("stock") or 0
        msg = f"{code} {p.get('mpn')} ({', '.join(refs)}): {p.get('library')}{' (preferred, no feeder fee)' if p.get('preferred') else ''}, stock {stock}"
        if stock < len(refs) * int(bp.get("boards", 5)):
            row("basic_parts", "fail", f"basic_parts:{code}", msg + f" < {len(refs)} x {bp.get('boards', 5)} boards", objects=refs, finding="C2"); continue
        if p.get("library") == "extended" and not p.get("preferred"):
            ext.append(code); fees += fee
            row("basic_parts", "warn", f"basic_parts:{code}", msg + f": ${fee:.2f} feeder fee"
                + (f"; basic: " + ", ".join(f"{a['lcsc']} {a['value']} {a['package']}" for a in alt[:3]) if alt else ""), objects=refs, finding="C2")
        else:
            row("basic_parts", "pass", f"basic_parts:{code}", msg, objects=refs)
    lim = bp.get("max_extended")
    st = "fail" if lim is not None and len(ext) > int(lim) else "pass"
    row("basic_parts", st, "basic_parts:total", f"{len(lines)} LCSC lines, {len(ext)} extended types: ${fees:.2f} in feeder fees at ${fee:.2f} a type"
        f" (cache fetched {cache.get('fetched')})" + (f"; limit {lim}" if lim is not None else ""), value=len(ext), limit=lim, finding="C2")
    COVERAGE.append(f"basic_parts: {len(lines)} LCSC lines against the JLC cache fetched {cache.get('fetched')}")


def check_calcs(CFG, NL, B):
    rows = CFG.get("calcs", [])
    if not rows:
        NOT_CHECKED.append("calcs: no calcs rows (buck ripple, LDO dissipation, sense scaling) so the log's arithmetic was not re-done")
        return
    import math
    comps = NL[0]
    def val(ref):
        if ref not in comps:
            raise KeyError(f"no component {ref}")
        v = parse_value(comps[ref]["value"])
        if v is None:
            raise ValueError(f"{ref} value {comps[ref]['value']!r} is not a number")
        return v
    ns = {k: getattr(math, k) for k in ("sqrt", "log", "log10", "exp", "pi", "floor", "ceil", "fabs")}
    ns.update({"R": val, "C": val, "L": val, "min": min, "max": max, "abs": abs})
    for r in rows:
        rid = r.get("id") or r.get("expr", "?")[:20]
        local = dict(ns); local.update(r.get("vars", {}))
        try:
            v = eval(r["expr"], {"__builtins__": {}}, local)
        except Exception as e:
            row("calcs", "fail", f"calcs:{rid}", f"{r.get('expr')}: {type(e).__name__}: {e}", finding=r.get("finding", "")); continue
        ns[rid] = v
        lo, hi = r.get("min"), r.get("max")
        ok = (lo is None or v >= float(lo) - 1e-9) and (hi is None or v <= float(hi) + 1e-9)
        unit = r.get("unit", "")
        row("calcs", "pass" if ok else "fail", f"calcs:{rid}",
            f"{rid} = {r['expr']} = {v:.4g} {unit}" + (f" (min {lo})" if lo is not None else "") + (f" (max {hi})" if hi is not None else "")
            + (f"; {r['note']}" if r.get("note") else ""), value=round(v, 6) if isinstance(v, (int, float)) else v,
            limit=hi if hi is not None else lo, finding=r.get("finding", ""))
    COVERAGE.append(f"calcs: {len(rows)} formula rows evaluated in order with R()/C()/L() from the netlist values")


def check_fields(CFG, NL, B):
    req = CFG.get("fields", ["MPN", "Manufacturer", "LCSC", "Datasheet"])
    if not req:
        NOT_CHECKED.append("fields: disabled (fields: [])"); return
    n = 0
    for f in sorted(B.GetFootprints(), key=lambda f: f.GetReference()):
        if f.IsDNP() or (f.GetAttributes() & pcbnew.FP_EXCLUDE_FROM_BOM):
            continue
        n += 1
        ref = f.GetReference()
        missing = [k for k in req if not pcbq.field(f, k).strip()]
        if missing:
            row("fields", "fail", f"fields:{ref}", f"{ref} ({f.GetValue()}): missing {', '.join(missing)}", objects=[ref], finding="R1-A2S-1")
        else:
            row("fields", "pass", f"fields:{ref}", f"{ref}: {', '.join(req)} present", objects=[ref])
    COVERAGE.append(f"fields: {n} BOM parts checked for {', '.join(req)} on the footprint (what pcb fab and parity read)")


def check_policy(CFG, NL, B):
    pol = CFG.get("policy")
    if not pol:
        NOT_CHECKED.append("policy: no policy block (the brief's clearance/track/via/silk numbers) so board-setup relaxations were not checked")
        return
    ds = B.GetDesignSettings()
    tracks = [t for t in B.GetTracks() if t.GetClass() != "PCB_VIA"]
    vias = [t for t in B.GetTracks() if t.GetClass() == "PCB_VIA"]
    silk = [d for d in B.GetDrawings() if d.GetClass() == "PCB_TEXT" and d.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS)]
    refs = [f.Reference() for f in B.GetFootprints() if f.Reference().IsVisible() and f.Reference().GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS)]
    mm = pcbnew.ToMM
    actual = {
        "clearance_mm": [("setup", mm(ds.m_MinClearance)), ("default netclass", mm(ds.m_NetSettings.GetDefaultNetclass().GetClearance()))],
        "track_mm": [("setup", mm(ds.m_TrackMinWidth))] + ([("narrowest track", min(mm(t.GetWidth()) for t in tracks))] if tracks else []),
        "via_drill_mm": [("setup", mm(ds.m_MinThroughDrill))] + ([("smallest via drill", min(mm(v.GetDrillValue()) for v in vias))] if vias else []),
        "via_dia_mm": [("setup", mm(ds.m_ViasMinSize))] + ([("smallest via", min(mm(v.GetWidth()) for v in vias))] if vias else []),
        "hole_clearance_mm": [("setup", mm(ds.m_HoleClearance))],
        "edge_clearance_mm": [("setup", mm(ds.m_CopperEdgeClearance))],
        "silk_text_mm": [("setup", mm(ds.m_MinSilkTextHeight))] + ([("smallest silk text", min(mm(x.GetTextHeight()) for x in silk + refs))] if silk or refs else []),
    }
    for key, want in pol.items():
        if key.startswith("_"):
            continue
        if key not in actual:
            CONFIG_WARNS.append(f"policy key {key!r} unknown (known: {', '.join(actual)})"); continue
        want = float(want)
        low = [(src, round(v, 4)) for src, v in actual[key] if v + 1e-6 < want]
        if low:
            row("policy", "fail", f"policy:{key}", f"{key} policy {want} mm; below it: " + ", ".join(f"{s} {v}" for s, v in low),
                value=min(v for _, v in low), limit=want, finding="R1-A2-T5")
        else:
            row("policy", "pass", f"policy:{key}", f"{key} policy {want} mm met: " + ", ".join(f"{s} {round(v, 4)}" for s, v in actual[key]),
                value=min(v for _, v in actual[key]), limit=want)
    COVERAGE.append(f"policy: {sum(1 for k in pol if not k.startswith('_'))} brief numbers against the board setup, the default net class and the measured minima")


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
    sch = stem + ".kicad_sch"
    stale = os.path.exists(netlist) and os.path.exists(sch) and os.path.getmtime(sch) > os.path.getmtime(netlist) and netlist == stem + ".xml"
    if not os.path.exists(netlist) or stale:
        if os.path.exists(sch):
            if stale:
                CONFIG_WARNS.append(f"netlist {os.path.basename(netlist)} was older than the schematic: re-exported (R2-T4)")
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
              ("margin", lambda: check_margin(CFG, NL, B)), ("policy", lambda: check_policy(CFG, NL, B)),
              ("fields", lambda: check_fields(CFG, NL, B)), ("currents", lambda: check_currents(CFG, NL, B)),
              ("thermal_vias", lambda: check_thermal_vias(CFG, NL, B)), ("via_in_pad", lambda: check_via_in_pad(CFG, NL, B)),
              ("edge_margin", lambda: check_edge_margin(CFG, NL, B)), ("gnd_islands", lambda: check_gnd_islands(CFG, NL, B, board)),
              ("refplane", lambda: check_refplane(CFG, NL, B)),
              ("return_via", lambda: check_return_via(CFG, NL, B)), ("exposure", lambda: check_exposure(CFG, NL, B)),
              ("feed_room", lambda: check_feed_room(CFG, NL, B, board)),
              ("calcs", lambda: check_calcs(CFG, NL, B)), ("refstat", lambda: check_refstat(CFG, NL, B)),
              ("feeds", lambda: check_feeds(CFG, NL, B)), ("irdrop", lambda: check_irdrop(CFG, NL, B)),
              ("basic_parts", lambda: check_basic_parts(CFG, NL, B, cfg_dir))]
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
