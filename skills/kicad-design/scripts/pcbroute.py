"""pcb route <command> ...: autorouting primitives and the router drivers, over SWIG pcbnew (KiCad's bundled Python).

  strip BOARD [--out F] [--zones] [--drawings]       delete tracks and vias (and zones / drawings on request); footprints and
                                                    their placement stay (pcblib Board.clear). Writes F or overwrites BOARD
  export-dsn BOARD [--out F.dsn]                    Specctra DSN via pcbnew.ExportSpecctraDSN (the freerouting input)
  import-ses BOARD F.ses [--out F]                  Specctra session back onto BOARD via pcbnew.ImportSpecctraSES, saved
  fill BOARD                                        save, reload, build connectivity, fill twice (pcblib Board.fill, P1-T10)
  canon BOARD [--out F]                             sort the footprint blocks by reference so the router sees the same
                                                    order on every regeneration (`auto` does this first, P6-T6)
  auto BOARD [--engine krt|freerouting] [--out F] [--pack jlcpcb] [--max-pass 2] [--work DIR] [--inner-tracks]
                                                    route what is unrouted with placement and existing copper kept; KRT
                                                    puts tracks on F.Cu/B.Cu only, the inner layers are ground planes that
                                                    vias pass through (--inner-tracks lifts that, ROUTE-T1); engine
                                                    pass, refill, dual DRC, a second engine pass on what is still open;
                                                    errors the input already had are inherited, not the router's. Writes
                                                    route.json beside the output; exit 1 unless clean (P6-T4)
  measure BOARD [--json] [--drc] [--pack jlcpcb] [--ref-value DRV8874]
                                                    copper as numbers: tracks, vias, signal_vias (vias on nets with no
                                                    filled inner-layer zone, spike #4), length, widths, airwires left
                                                    (pcb q ratsnest), setup minimums, the nets of the footprint whose value
                                                    matches --ref-value (the 0.65 mm pitch part, R2-T2) and with --drc the
                                                    dual DRC of `pcb drc` (plain, packed, errors_total)
  waves BOARD --search [--plan base.json] [--config checks.json] [--netlist x.xml] [--vin NET --source PADS [--sink PAD=A]]
                                       [--jobs 3] [--fast-max 0] [--out F] [--work DIR]
                                                    the six plans of the search (rules, zones, rail-first, motor-first,
                                                    both, zones-esc) routed in parallel and judged (refplane by bucket,
                                                    return_via, exposure, currents, irdrop); the plan that meets the hard
                                                    limits at the lowest weighted cost is written (SIG-4); search.json
  waves BOARD [--plan plan.json] [--out F] [--work DIR] [--pack jlcpcb] [--return-vias --config checks.json [--netlist x.xml]]
  classes BOARD --config checks.json [--round 0.05] [--min MM] [--dry]
                                                    net classes from the config's currents (IPC-2221 widths, W<mm>) and
                                                    victims (Sense) into the .kicad_pro, for a board that has none
  return-vias BOARD --config checks.json [--netlist x.xml] [--max-mm 2] [--buckets 3,4] [--dry]
                                                    a ground via beside every bucket-3/4 via without one within max_mm
                                                    (SIG-2); `waves --return-vias` runs it after the finish, before the
                                                    verdict; the search runs it unless --no-return-vias
                                                    route in waves (WAVES-1): wave 0 is code (pcblib pad_feed_search on the
                                                    plan's feeds, thermal_vias), then one KRT call per wave with its own
                                                    nets, layers and keepout polygons (User.2), each wave's copper locked
                                                    so later waves and the finishing `auto` cannot rip it, unlocked at the
                                                    end. No plan: wide classes (>= 0.5 mm), then Sense classes, then the
                                                    rest. waves.json beside the output; the verdict is against the input
Output lines start with `PCBROUTE`; --json prints one JSON object instead. Evidence: P6-T1 (measurement), P6-T2 onwards
(the routers measured on the rung-2 boards).
"""
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pcbnew  # noqa: E402
from pcbnew import ToMM  # noqa: E402
from pcblib.board import Board, unfill_and_save  # noqa: E402
import pcbq  # noqa: E402

OUT = []
PCB = os.path.join(HERE, "pcb")


def say(*a):
    OUT.append(" ".join(str(x) for x in a))


def opt(args, name, default=None, flag=False):
    if name in args:
        i = args.index(name)
        if flag:
            del args[i]
            return True
        v = args[i + 1]
        del args[i:i + 2]
        return v
    return default


def c_strip(args):
    out = opt(args, "--out")
    zones = opt(args, "--zones", flag=True)
    drawings = opt(args, "--drawings", flag=True)
    bd = Board.load(args[0])
    before = bd.summary()
    bd.clear(tracks=True, zones=zones, drawings=drawings)
    path = bd.save(out)
    after = bd.summary()
    say("PCBROUTE strip", path, "tracks", before["tracks"], "->", after["tracks"], "vias", before["vias"], "->", after["vias"],
        "zones", before["zones"], "->", after["zones"], "drawings", before["drawings"], "->", after["drawings"])
    return {"path": path, "before": before, "after": after}


def c_export_dsn(args):
    out = opt(args, "--out") or os.path.splitext(args[0])[0] + ".dsn"
    b = pcbnew.LoadBoard(args[0])
    ok = pcbnew.ExportSpecctraDSN(b, out)
    if not ok:
        sys.exit(f"pcbroute: ExportSpecctraDSN failed for {args[0]}")
    say("PCBROUTE export-dsn", out, os.path.getsize(out), "bytes")
    return {"dsn": out, "bytes": os.path.getsize(out)}


def c_import_ses(args):
    out = opt(args, "--out") or args[0]
    b = pcbnew.LoadBoard(args[0])
    ok = pcbnew.ImportSpecctraSES(b, args[1])
    if not ok:
        sys.exit(f"pcbroute: ImportSpecctraSES failed for {args[1]}")
    pcbnew.SaveBoard(out, b)
    bd = Board.load(out)
    say("PCBROUTE import-ses", out, "tracks", bd.summary()["tracks"], "vias", bd.summary()["vias"])
    return {"path": out, **bd.summary()}


def c_fill(args):
    bd = Board.load(args[0])
    bd.fill()
    say("PCBROUTE fill", args[0], bd.summary())
    return bd.summary()


def plane_nets(b):
    """Nets with a filled zone on an inner copper layer: their vias are plane taps (stitch, fan-out), not layer changes."""
    inner = {l for l in b.GetEnabledLayers().CuStack() if l not in (pcbnew.F_Cu, pcbnew.B_Cu)}
    return {z.GetNetname() for z in b.Zones() if z.GetNetname() and z.IsFilled()
            and any(z.GetFilledPolysList(l).OutlineCount() for l in z.GetLayerSet().CuStack() if l in inner)}


def copper(b):
    tracks, vias, length, widths, per_layer = 0, 0, 0.0, {}, {}
    via_sizes, net_minw = {}, {}
    planes, sig_vias = plane_nets(b), {}
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            vias += 1
            if t.GetNetname() not in planes:
                sig_vias[t.GetNetname()] = sig_vias.get(t.GetNetname(), 0) + 1
            k = f"{ToMM(t.GetWidth()):.2f}/{ToMM(t.GetDrillValue()):.2f}"
            via_sizes[k] = via_sizes.get(k, 0) + 1
        else:
            tracks += 1
            l = ToMM(t.GetLength())
            length += l
            w = round(ToMM(t.GetWidth()), 4)
            widths[w] = widths.get(w, 0) + 1
            nw = net_minw.setdefault(t.GetNetname(), {})
            nw[str(w)] = round(nw.get(str(w), 0.0) + l, 3)
            ln = b.GetLayerName(t.GetLayer())
            per_layer[ln] = round(per_layer.get(ln, 0.0) + l, 3)
    # signal_vias: vias on nets with no filled inner-layer zone, the layer changes a router chose (spike #4: `vias` also
    # counts plane stitching, which the P6-T4 stitch pass adds and the designers placed by hand)
    return {"tracks": tracks, "vias": vias, "signal_vias": sum(sig_vias.values()), "signal_vias_by_net": dict(sorted(sig_vias.items())),
            "plane_nets": sorted(planes), "length_mm": round(length, 3), "min_width_mm": min(widths) if widths else None,
            "widths": {str(k): v for k, v in sorted(widths.items())}, "via_sizes": via_sizes, "length_per_layer_mm": per_layer,
            "net_width_mm": dict(sorted(net_minw.items()))}   # net -> {track width: length mm}


def c_measure(args):
    drc = opt(args, "--drc", flag=True)
    pack = opt(args, "--pack", "jlcpcb")
    ref_value = opt(args, "--ref-value", "DRV8874")
    path = args[0]
    b = pcbnew.LoadBoard(path)
    fps = pcbq.fp_map(b)
    r = {"board": path, **copper(b)}
    rn = pcbq.ratsnest(b)
    r["ratsnest"] = {k: rn[k] for k in ("multi_pad_nets", "open_nets", "airwires", "kicad_unconnected")}
    r["open"] = {x["net"]: x["airwires"] for x in rn["nets"] if x["airwires"]}
    r["clusters"] = {x["net"]: x["clusters"] for x in rn["nets"] if x["airwires"]}
    r["settings"] = pcbq.q_settings(b, fps, [])
    # the fine-pitch part: its nets, how many are still open, the vias and length those nets carry
    part = next((f for f in b.GetFootprints() if ref_value.lower() in f.GetValue().lower()), None)
    if part is not None:
        nets = sorted({p.GetNetname() for p in part.Pads() if p.GetNetname()})
        rows = {x["net"]: x for x in rn["nets"]}
        open_nets = {n: rows[n]["airwires"] for n in nets if n in rows and rows[n]["airwires"]}
        vias = sum(1 for t in b.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetname() in nets)
        length = sum(ToMM(t.GetLength()) for t in b.GetTracks() if t.GetClass() != "PCB_VIA" and t.GetNetname() in nets)
        r["part"] = {"ref": part.GetReference(), "value": part.GetValue(), "nets": len(nets), "open_nets": open_nets,
                     "airwires": sum(open_nets.values()), "vias": vias, "length_mm": round(length, 3)}
    if drc:
        out = os.path.join(os.path.dirname(os.path.abspath(path)), "drc")
        cmd = ["python3", "-I", os.path.join(HERE, "pcbcli.py"), "drc", path, "--pack", pack, "--out", out]
        p = subprocess.run(cmd, capture_output=True, text=True)
        try:
            d = json.load(open(os.path.join(out, "drc.json")))
            r["drc"] = {"plain_errors": d["plain"]["errors"], "packed_errors": d["packed"]["errors"], "errors_total": d["errors_total"],
                        "unconnected": d["plain"]["unconnected"], "plain_by_type": d["plain"]["by_type"].get("error", {}),
                        "packed_by_type": d["packed"]["by_type"].get("error", {}), "sentinel": d.get("sentinel"), "rc": p.returncode}
        except Exception as e:  # noqa: BLE001
            r["drc"] = {"error": f"{e}: {p.stdout[-300:]} {p.stderr[-300:]}", "rc": p.returncode}
    say("PCBROUTE measure", path, "tracks", r["tracks"], "vias", r["vias"], "signal_vias", r["signal_vias"], "length", r["length_mm"], "minw", r["min_width_mm"],
        "airwires", r["ratsnest"]["airwires"], "open", r["open"])
    if "part" in r:
        say("PCBROUTE part", r["part"]["ref"], r["part"]["value"], "nets", r["part"]["nets"], "airwires", r["part"]["airwires"],
            "vias", r["part"]["vias"], "length", r["part"]["length_mm"])
    if "drc" in r:
        say("PCBROUTE drc", json.dumps(r["drc"]))
    return r


# ---------------------------------------------------------------------------------------------------- the driver
REF = os.environ.get("PCB_REF", "/tmp/pcb-ref")
KRT_DIR = os.environ.get("KRT_DIR", os.path.join(REF, "KiCadRoutingTools"))
KRT_PY = os.environ.get("KRT_PY", os.path.join(KRT_DIR, ".venv/bin/python"))
FR_JAR = os.environ.get("FREEROUTING_JAR", os.path.join(REF, "freerouting/freerouting-2.5.0.jar"))
JAVA = os.environ.get("JAVA", "/opt/homebrew/opt/openjdk/bin/java")
# KRT: the board setup is never rewritten and sizes stay exact on the first pass; the second pass may neck a net that
# did not fit down to the board's own minimums (P6-T3: 'board' closed the last VIN airwire on the Opus board)
KRT_PASSES = [["--no-fix-drc-settings", "--escalation", "off"], ["--no-fix-drc-settings", "--escalation", "board"]]
FR_ARGS = ["-mt", "4", "-da", "--gui.enabled=false", "--logging.file.enabled=false"]


def outer_only_args(board):
    """KRT's own recipe for 'tracks on the outer layers, inner layers obstacle-only': every copper layer listed, the inner
    ones at cost -1 (no track copper, vias may span them). On the four rung-2 placements this took inner-layer track
    from 138-200 mm to 0 with the same clean/open result and equal or fewer vias (ROUTE-T1)."""
    b = pcbnew.LoadBoard(board)
    ls = [b.GetLayerName(l) for l in b.GetEnabledLayers().CuStack()]
    if len(ls) <= 2:
        return []
    return ["--layers", *ls, "--layer-costs", *["1.0" if l in ("F.Cu", "B.Cu") else "-1" for l in ls]]


def run_engine(engine, board, out_dir, pass_no, log, inner_tracks=False, extra_args=(), timeout=None):
    """Route `board` (a .kicad_pcb with its .kicad_pro beside it) into out_dir; returns (routed path, wall s, rc)."""
    import shutil, time
    os.makedirs(out_dir, exist_ok=True)
    for ext in (".kicad_pro", ".kicad_prl"):
        src = os.path.splitext(board)[0] + ext
        if os.path.exists(src):
            shutil.copy(src, os.path.join(out_dir, os.path.basename(src)))
    routed = os.path.join(out_dir, os.path.basename(board))
    t = time.time()
    if engine == "krt":
        if not os.path.exists(KRT_PY):
            sys.exit(f"pcbroute: KiCadRoutingTools not installed at {KRT_DIR} (KRT_DIR, KRT_PY; see tools/bench/README.md)")
        extra = KRT_PASSES[min(pass_no, len(KRT_PASSES)) - 1] + ([] if inner_tracks else outer_only_args(board)) + list(extra_args)
        cmd = [KRT_PY, os.path.join(KRT_DIR, "py_router/route.py"), board, routed, "--json-out", os.path.join(out_dir, "krt.json"), *extra]
        # KRT orders rip-up candidates by iterating a set of net names, so its second pass varied with Python's per-process
        # string hash seed (1 run in 4 on the rung-1 board, ROUTE-T3); a fixed seed makes every pass reproducible
        try:
            p = subprocess.run(cmd, cwd=KRT_DIR, capture_output=True, text=True, env={**os.environ, "PYTHONHASHSEED": "0"}, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            # an agent-written wave with an edge keepout ran 23 min, another 17 min in KRT's plane repair (PLAN-1); the
            # output so far goes to the log (spike #4: two guided power waves timed out with nothing to read)
            part = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            with open(log, "a") as f:
                f.write(f"$ {' '.join(cmd)}\nTIMEOUT after {timeout} s\n{part[-20000:]}\n")
            return None, round(time.time() - t, 1), "timeout"
    elif engine == "freerouting":
        if not os.path.exists(FR_JAR) or not os.path.exists(JAVA):
            sys.exit(f"pcbroute: freerouting jar or java missing ({FR_JAR}, {JAVA}); the native CLI crashes (P6-T2)")
        dsn, ses = os.path.join(out_dir, "board.dsn"), os.path.join(out_dir, "board.ses")
        b = pcbnew.LoadBoard(board)
        pcbnew.ExportSpecctraDSN(b, dsn)
        cmd = [JAVA, "-Djava.awt.headless=true", "-jar", FR_JAR, "-de", dsn, "-do", ses, *FR_ARGS]
        p = subprocess.run(cmd, cwd=out_dir, capture_output=True, text=True)
        if os.path.exists(ses):
            b = pcbnew.LoadBoard(board)
            pcbnew.ImportSpecctraSES(b, ses)
            unfill_and_save(b, routed)   # new copper in stale fills gets re-netted on save (ROUTE-T4); refilled after
    else:
        sys.exit(f"pcbroute: unknown engine {engine}")
    wall = round(time.time() - t, 1)
    with open(log, "a") as f:
        f.write(f"$ {' '.join(cmd)}\nrc={p.returncode} wall={wall}s\n{p.stdout}\n{p.stderr}\n")
    return (routed if os.path.exists(routed) else None), wall, p.returncode


def widen_under_min(path, min_mm):
    """Freerouting necks tracks down at fine-pitch pads below the board minimum (P6-T3, 0.1874 mm against 0.2): set every
    segment narrower than the minimum to the minimum. DRC decides afterwards whether the clearance survived."""
    b = pcbnew.LoadBoard(path)
    n = 0
    for t in b.GetTracks():
        if t.GetClass() != "PCB_VIA" and ToMM(t.GetWidth()) < min_mm - 1e-6:
            t.SetWidth(pcbnew.FromMM(min_mm))
            n += 1
    if n:
        pcbnew.SaveBoard(path, b)
    return n


def pad_by_desc(b, desc):
    """'Pad 2 [GND] of U1 on F.Cu' or 'PTH pad 1 [GND] of J4' (KiCad's wording for through-hole pads, no layer; the stitch
    pass never matched it, so a starved through-hole GND pad was never repaired, STARVE-1) -> the PAD."""
    import re
    m = re.match(r"(?:N?PTH )?[Pp]ad (\S+) \[.*?\] of (\S+)", desc or "")
    if not m:
        return None
    for f in b.GetFootprints():
        if f.GetReference() == m.group(2):
            for pd in f.Pads():
                if pd.GetNumber() == m.group(1):
                    return pd
    return None


def stitch(path, drc_plain_json, open_clusters, settings):
    """Pass 3 of the loop, in pcbnew: pads the router left unconnected or with a starved thermal get a plane
    connection. A pad in a footprint with room (pad pitch >= 0.8 mm) gets a via of the board's default size just outside
    the pad, away from the footprint centre, with a stub at the pad's width; a fine-pitch pad (the LGA-14's 0.5 mm) gets
    a solid zone connection instead, since no via fits beside it (P6-T4). Returns the list of actions."""
    import math
    b = pcbnew.LoadBoard(path)
    fps = pcbq.fp_map(b)
    todo = []
    try:
        for v in json.load(open(drc_plain_json))["violations"]:
            if v["type"] == "starved_thermal":
                pd = pad_by_desc(b, v["items"][1].get("description") if len(v["items"]) > 1 else "")
                if pd is not None:
                    todo.append(("starved_thermal", pd))
    except Exception:  # noqa: BLE001
        pass
    zone_nets = {z.GetNetname() for z in b.Zones() if z.IsFilled()}
    for net, clusters in open_clusters.items():
        if net not in zone_nets:
            continue
        for cl in clusters[1:]:
            pd = pcbq.pad_of(fps, cl[0]) if cl else None
            if pd is not None:
                todo.append(("open", pd))
    actions = []
    via_d, drill = settings.get("via_diameter", 0.6), settings.get("through_hole", 0.3)
    clearance = settings.get("clearance", 0.2)
    for why, pd in todo:
        f = pd.GetParentFootprint()
        pads = list(f.Pads())
        pitch = min((math.hypot(ToMM(a.GetPosition().x - c.GetPosition().x), ToMM(a.GetPosition().y - c.GetPosition().y))
                     for i, a in enumerate(pads) for c in pads[i + 1:]), default=9.9)
        name = f"{f.GetReference()}.{pd.GetNumber()}"
        if pitch < 0.8 or pd.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
            if why == "starved_thermal":
                pd.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
                actions.append({"pad": name, "net": pd.GetNetname(), "why": why, "action": "solid zone connection", "pitch_mm": round(pitch, 3)})
            else:
                actions.append({"pad": name, "net": pd.GetNetname(), "why": why, "action": "none: fine pitch, no via fits", "pitch_mm": round(pitch, 3)})
            continue
        px, py = ToMM(pd.GetPosition().x), ToMM(pd.GetPosition().y)
        cx, cy = ToMM(f.GetPosition().x), ToMM(f.GetPosition().y)
        dx, dy = px - cx, py - cy
        n = math.hypot(dx, dy) or 1.0
        dx, dy = dx / n, dy / n
        half = max(ToMM(pd.GetSize().x), ToMM(pd.GetSize().y)) / 2
        dist = half + clearance + via_d / 2 + 0.05
        vx, vy = px + dx * dist, py + dy * dist
        layer = b.GetLayerName(pd.GetLayer())
        width = min(ToMM(pd.GetSize().x), ToMM(pd.GetSize().y))
        bd = Board(b, path)
        bd.route(pd.GetNetname(), [(px, py), (vx, vy)], layer=layer, width=round(width, 3))
        bd.via(vx, vy, pd.GetNetname(), size=(via_d, drill))
        actions.append({"pad": name, "net": pd.GetNetname(), "why": why, "action": f"via {via_d}/{drill} at ({vx:.3f}, {vy:.3f}) with a {width:.2f} mm stub",
                        "pitch_mm": round(pitch, 3)})
    if actions:
        unfill_and_save(b, path)   # ROUTE-T4; c_auto refills right after
    return actions


def top_spans(text):
    """(start, end) of every top-level block inside (kicad_pcb ...), string-aware."""
    i = text.index("(kicad_pcb") + len("(kicad_pcb")
    spans, depth, start, instr, j = [], 0, None, False, i
    while j < len(text):
        c = text[j]
        if instr:
            if c == "\\":
                j += 1
            elif c == '"':
                instr = False
        elif c == '"':
            instr = True
        elif c == "(":
            if depth == 0:
                start = j
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0 and start is not None:
                spans.append((start, j + 1))
                start = None
            elif depth < 0:
                break
        j += 1
    return spans


def track_uuids(text):
    """Give every top-level segment, arc and via a UUID derived from its own text (uuid5 over the block with its uuid
    removed, plus a duplicate counter). KiCad sorts tracks by UUID when it saves, and KRT writes random UUIDs, so the
    same copper came back from a refill in a different order on every run, and KRT's second pass, which reads tracks
    in file order, then routed differently (ROUTE-T2). Track UUIDs are referenced by nothing else in the file."""
    import re, uuid
    ns = uuid.UUID("6f1c3a52-9d0e-4b8a-a1f2-7e5d3c2b1a09")
    seen, pieces, last = {}, [], 0
    for a, b in top_spans(text):
        if not text.startswith(("(segment", "(arc", "(via"), a):
            continue
        blk = text[a:b]
        body = re.sub(r'\(uuid "[^"]*"\)', "", blk)
        n = seen.get(body, 0); seen[body] = n + 1
        new = re.sub(r'\(uuid "[^"]*"\)', f'(uuid "{uuid.uuid5(ns, body + "#" + str(n))}")', blk, count=1)
        pieces += [text[last:a], new]; last = b
    pieces.append(text[last:])
    return "".join(pieces)


def canonical(path, out=None):
    """Sort the board file's top-level (footprint ...) blocks by reference, in place. KiCad 10 files carry nets by name
    inside pads, so a router that numbers nets in order of appearance (KRT) routes in footprint-file order, and Zener's
    `pcb layout` writes the footprints in a different order on every clean regeneration (R1-A2-T2): the same placement
    then routes differently and regen-check FAILS (P6-T6). With the footprints sorted the copper is identical. Track,
    arc and via UUIDs are then derived from content (track_uuids, ROUTE-T2). Text-level; placement and every other
    UUID stay byte-for-byte; pcbnew loads the result unchanged."""
    import re
    text = open(path).read()
    spans = top_spans(text)
    fps = [(a, b) for a, b in spans if text.startswith("(footprint", a)]
    if not fps:
        open(out or path, "w").write(track_uuids(text))
        return 0
    def key(span):
        m = re.search(r'\(property "Reference" "([^"]*)"', text[span[0]:span[1]])
        ref = m.group(1) if m else ""
        m2 = re.match(r"([A-Za-z_]*)(\d*)", ref)
        return (m2.group(1), int(m2.group(2) or 0), ref, text[span[0]:span[1]])
    ordered = sorted(fps, key=key)
    pieces, last = [], 0
    for (a, b), (oa, ob) in zip(fps, ordered):
        pieces.append(text[last:a])
        pieces.append(text[oa:ob])
        last = b
    pieces.append(text[last:])
    open(out or path, "w").write(track_uuids("".join(pieces)))
    return len(fps)


def c_canon(args):
    out = opt(args, "--out")
    n = canonical(args[0], out)
    say("PCBROUTE canon", out or args[0], "footprints sorted by reference", n)
    return {"path": out or args[0], "footprints": n}


def new_errors(by_type, inherited):
    return {k: v - inherited.get(k, 0) for k, v in by_type.items() if v > inherited.get(k, 0)}


def c_auto(args):
    """pcb route auto BOARD [--engine krt|freerouting] [--out F] [--pack jlcpcb] [--max-pass 2] [--work DIR]
    Route the unrouted connections of BOARD with placement and existing copper kept, refill, run the dual DRC, and
    repeat with the engine's second pass on what is still open; freerouting's under-width segments are widened to
    the board minimum first. Writes the routed board to --out (default: BOARD in place, the input saved as
    <stem>.prerouted.kicad_pcb in the work dir) and route.json beside it. Errors the input already had (placement,
    pours) are reported as inherited and not charged to the router. Exit 1 when connections or new errors remain."""
    import shutil, time
    engine = opt(args, "--engine", "krt")
    out = opt(args, "--out")
    pack = opt(args, "--pack", "jlcpcb")
    max_pass = int(opt(args, "--max-pass", "2"))
    work = opt(args, "--work")
    inner_tracks = opt(args, "--inner-tracks", flag=True)
    baseline = opt(args, "--baseline")   # judge inherited errors against this board instead (waves pass their input)
    board = os.path.abspath(args[0])
    stem = os.path.splitext(os.path.basename(board))[0]
    work = work or os.path.join("/tmp/pcb-route-auto", f"{stem}-{os.getpid()}")
    os.makedirs(work, exist_ok=True)
    log = os.path.join(work, "route.log")
    t0 = time.time()
    # the input, measured, in the work dir
    cur = os.path.join(work, "pass0", os.path.basename(board))
    os.makedirs(os.path.dirname(cur), exist_ok=True)
    for ext in (".kicad_pcb", ".kicad_pro", ".kicad_prl"):
        src = os.path.splitext(board)[0] + ext
        if os.path.exists(src):
            shutil.copy(src, os.path.join(os.path.dirname(cur), os.path.basename(src)))
    shutil.copy(board, os.path.join(work, f"{stem}.prerouted.kicad_pcb"))
    canonical(cur)
    keep = len(OUT)
    start = c_measure([cur, "--drc", "--pack", pack])
    del OUT[keep:]
    if baseline:
        keep = len(OUT)
        base_m = c_measure([baseline, "--drc", "--pack", pack])
        del OUT[keep:]
    else:
        base_m = start
    inherited = (base_m.get("drc") or {}).get("plain_by_type", {})
    inherited_packed = (base_m.get("drc") or {}).get("packed_errors", 0)
    passes = []
    final = start
    say("PCBROUTE auto", board, "engine", engine, "airwires", start["ratsnest"]["airwires"], "inherited plain errors", inherited,
        "packed", inherited_packed, "setup", start["settings"])
    for n in range(1, max_pass + 1):
        if final["ratsnest"]["airwires"] == 0 and n > 1:
            break
        routed, wall, rc = run_engine(engine, cur, os.path.join(work, f"pass{n}"), n, log, inner_tracks)
        if routed is None:
            say("PCBROUTE pass", n, "FAILED rc", rc, "see", log)
            passes.append({"pass": n, "rc": rc, "wall_s": wall, "error": "no board written"})
            break
        widened = widen_under_min(routed, start["settings"]["track_width"]) if engine == "freerouting" else 0
        canonical(routed)   # content-derived track UUIDs, so the refill's save order and the next pass are reproducible
        Board.load(routed).fill()
        keep = len(OUT)
        m = c_measure([routed, "--drc", "--pack", pack])
        del OUT[keep:]
        d = m.get("drc", {})
        rec = {"pass": n, "rc": rc, "wall_s": wall, "airwires": m["ratsnest"]["airwires"], "open": m["open"], "vias": m["vias"],
               "tracks": m["tracks"], "length_mm": m["length_mm"], "min_width_mm": m["min_width_mm"], "plain_errors": d.get("plain_errors"),
               "packed_errors": d.get("packed_errors"), "new_errors": new_errors(d.get("plain_by_type", {}), inherited),
               "widened": widened, "setup_changed": {k: (start["settings"][k], v) for k, v in m["settings"].items() if start["settings"].get(k) != v} or False}
        passes.append(rec)
        say("PCBROUTE pass", n, "wall", wall, "s airwires", rec["airwires"], "open", rec["open"], "vias", rec["vias"], "length", rec["length_mm"],
            "drc plain/packed", rec["plain_errors"], "/", rec["packed_errors"], "new", rec["new_errors"], "widened", widened,
            "setup", "CHANGED " + json.dumps(rec["setup_changed"]) if rec["setup_changed"] else "kept")
        final, cur = m, routed
        if rec["airwires"] == 0 and not rec["new_errors"] and (rec["packed_errors"] or 0) <= inherited_packed:
            break
    last = passes[-1] if passes else {}
    if passes and "airwires" in last and (last["airwires"] or last["new_errors"].get("starved_thermal")):
        import shutil as _sh
        fixed = os.path.join(work, "stitch", os.path.basename(board))
        os.makedirs(os.path.dirname(fixed), exist_ok=True)
        for ext in (".kicad_pcb", ".kicad_pro", ".kicad_prl"):
            src = os.path.splitext(cur)[0] + ext
            if os.path.exists(src):
                _sh.copy(src, os.path.join(os.path.dirname(fixed), os.path.basename(src)))
        actions = stitch(fixed, os.path.join(os.path.dirname(cur), "drc", "drc-plain.json"), final.get("clusters", {}), start["settings"])
        if actions:
            canonical(fixed)
            Board.load(fixed).fill()
            keep = len(OUT)
            m = c_measure([fixed, "--drc", "--pack", pack])
            del OUT[keep:]
            d = m.get("drc", {})
            rec = {"pass": "stitch", "actions": actions, "airwires": m["ratsnest"]["airwires"], "open": m["open"], "vias": m["vias"], "tracks": m["tracks"],
                   "length_mm": m["length_mm"], "min_width_mm": m["min_width_mm"], "plain_errors": d.get("plain_errors"), "packed_errors": d.get("packed_errors"),
                   "new_errors": new_errors(d.get("plain_by_type", {}), inherited), "setup_changed": False}
            better = (rec["airwires"], sum(rec["new_errors"].values())) <= (last["airwires"], sum(last["new_errors"].values()))
            say("PCBROUTE stitch", len(actions), "actions", [a["action"] for a in actions], "-> airwires", rec["airwires"], "new", rec["new_errors"],
                "kept" if better else "DISCARDED (worse)")
            passes.append(rec if better else {**rec, "discarded": True})
            if better:
                final, cur, last = m, fixed, rec
    clean = bool(passes and last.get("airwires") == 0 and not last.get("new_errors") and (last.get("packed_errors") or 0) <= inherited_packed
                 and not last.get("setup_changed"))
    dest = out or board
    if cur != os.path.join(work, "pass0", os.path.basename(board)):
        shutil.copy(cur, dest)
        pro = os.path.splitext(cur)[0] + ".kicad_pro"
        if out and os.path.exists(pro):
            shutil.copy(pro, os.path.splitext(dest)[0] + ".kicad_pro")
    r = {"board": board, "out": dest, "engine": engine, "work": work, "wall_s": round(time.time() - t0, 1), "clean": clean,
         "inner_tracks": inner_tracks or engine != "krt", "inner_mm": round(sum(v for k, v in (final.get("length_per_layer_mm") or {}).items() if k.startswith("In")), 1),
         "start": {"airwires": start["ratsnest"]["airwires"], "open": start["open"], "plain_errors": (start.get("drc") or {}).get("plain_errors"),
                   "packed_errors": inherited_packed, "inherited_by_type": inherited, "vias": start["vias"], "tracks": start["tracks"]},
         "passes": passes, "final": {k: last.get(k) for k in ("airwires", "open", "vias", "tracks", "length_mm", "min_width_mm", "plain_errors",
                                                              "packed_errors", "new_errors", "setup_changed")},
         "part": final.get("part"), "sentinel": (final.get("drc") or {}).get("sentinel")}
    json.dump(r, open(os.path.join(os.path.dirname(dest), "route.json"), "w"), indent=1)
    say("PCBROUTE verdict", "CLEAN" if clean else "NOT CLEAN", "airwires", last.get("airwires"), "new errors", last.get("new_errors"),
        "inherited", inherited, "->", dest, f"({r['wall_s']} s, work {work})")
    if not clean:
        r["exit"] = 1
    return r


# ---------------------------------------------------------------------------------------------------- waves (WAVES-1)
def default_plan(board):
    """Waves from the net classes: classes wider than Default (the power and motor rails), then classes named *sense*,
    then everything else."""
    pro = os.path.splitext(board)[0] + ".kicad_pro"
    ns = json.load(open(pro)).get("net_settings", {}) if os.path.exists(pro) else {}
    w = {c["name"]: float(c.get("track_width") or 0) for c in ns.get("classes", [])}
    pats = ns.get("netclass_patterns", [])
    dflt = w.get("Default", 0.2)
    # power: every class wider than Default that is not a sense class (rung 2: Motor 0.8, VIN 1.4; a 1.5 A motor net at
    # 0.35 mm from `classes` counts too); sense: classes named *sense*
    power = [x["pattern"] for x in pats if w.get(x.get("netclass"), 0) > dflt + 1e-9 and "sense" not in (x.get("netclass") or "").lower()]
    sense = [x["pattern"] for x in pats if "sense" in (x.get("netclass") or "").lower() and x["pattern"] not in power]
    waves = []
    if power:
        waves.append({"name": "power", "nets": power})
    if sense:
        waves.append({"name": "sense", "nets": sense})
    waves.append({"name": "rest", "nets": ["*"]})
    return {"waves": waves}


def keepout_blocks(polys, tag):
    """gr_poly blocks on User.2 (KRT's keepout layer, read with --keepout), uuids from the tag so they can be removed."""
    import uuid
    ns = uuid.UUID("2b7e1f0c-5a3d-4c6e-9f81-0d2c4b6a8e13")
    out = []
    for i, poly in enumerate(polys):
        pts = " ".join(f"(xy {x} {y})" for x, y in poly)
        out.append(f'\t(gr_poly\n\t\t(pts {pts})\n\t\t(stroke (width 0.1) (type solid))\n\t\t(fill no)\n\t\t(layer "User.2")\n'
                   f'\t\t(uuid "{uuid.uuid5(ns, tag + "#" + str(i))}")\n\t)\n')
    return out


def guide_blocks(lines, tag):
    """gr_line chains on User.1 (KRT's --guide-corridor layer; gr_poly would close the path), uuids from the tag."""
    import uuid
    ns = uuid.UUID("7c1d0e2a-3b4f-4a5e-8d6c-1f2e3a4b5c6d")
    out = []
    for i, line in enumerate(lines):
        for j, ((x1, y1), (x2, y2)) in enumerate(zip(line, line[1:])):
            out.append(f'\t(gr_line\n\t\t(start {x1} {y1})\n\t\t(end {x2} {y2})\n\t\t(stroke (width 0.1) (type solid))\n'
                       f'\t\t(layer "User.1")\n\t\t(uuid "{uuid.uuid5(ns, tag + "#" + str(i) + "." + str(j))}")\n\t)\n')
    return out


def put_guides(path, lines, tag):
    if not lines:
        return
    t = open(path).read().rstrip()
    assert t.endswith(")")
    open(path, "w").write(t[:-1] + "".join(guide_blocks(lines, tag)) + ")\n")


def drop_guides(path, lines, tag):
    if not lines:
        return
    import re
    ids = set(re.findall(r'\(uuid "([^"]+)"\)', "".join(guide_blocks(lines, tag))))
    text = open(path).read()
    pieces, last = [], 0
    for a, b in top_spans(text):
        blk = text[a:b]
        if blk.startswith("(gr_line") and any(i in blk for i in ids):
            pieces.append(text[last:a].rstrip("\t")); last = b
            if text[last:last + 1] == "\n":
                last += 1
    pieces.append(text[last:])
    open(path, "w").write("".join(pieces))


def put_keepouts(path, polys, tag):
    if not polys:
        return
    t = open(path).read().rstrip()
    assert t.endswith(")")
    open(path, "w").write(t[:-1] + "".join(keepout_blocks(polys, tag)) + ")\n")


def drop_keepouts(path, polys, tag):
    if not polys:
        return
    import re
    ids = set(re.findall(r'\(uuid "([^"]+)"\)', "".join(keepout_blocks(polys, tag))))
    text = open(path).read()
    pieces, last = [], 0
    for a, b in top_spans(text):
        blk = text[a:b]
        if blk.startswith("(gr_poly") and any(i in blk for i in ids):
            pieces.append(text[last:a].rstrip("\t")); last = b
            if text[last:last + 1] == "\n":
                last += 1
    pieces.append(text[last:])
    open(path, "w").write("".join(pieces))


def lock_nets(path, patterns, lock=True):
    import fnmatch
    b = pcbnew.LoadBoard(path)
    n = 0
    for t in b.GetTracks():
        if any(fnmatch.fnmatchcase(t.GetNetname(), p) for p in patterns) and t.IsLocked() != lock:
            t.SetLocked(lock); n += 1
    pcbnew.SaveBoard(path, b)   # no copper added, so no stale-fill re-net (ROUTE-T4)
    return n


def c_waves(args):
    """pcb route waves BOARD [--plan plan.json] [--out F] [--work DIR] [--pack jlcpcb]
    plan.json: {"feeds": [{"pad": "U2.11", "amps": 2.5}, {"pad": "U1.4,5,6", "amps": 2.8}], "thermal_vias": ["U1"], "timeout_s": 300,
                "waves": [{"name": "power", "nets": ["VIN", "5V"], "layers": "outer"|"all"|["F.Cu", ...],
                           "keepouts": [[[x, y], ...], ...], "guides": [[[x, y], ...], ...], "args": ["--ordering", "bus"]}, ...]}
    Wave 0 (feeds, thermal vias) is pcblib code; each later wave is one KRT call on its nets, its copper locked after;
    then `auto` finishes the board (second pass, stitch, dual DRC, verdict). Writes waves.json and route.json."""
    import shutil, time, fnmatch
    if "--search" in args:
        return c_search(args)
    plan_path = opt(args, "--plan"); out = opt(args, "--out"); work = opt(args, "--work"); pack = opt(args, "--pack", "jlcpcb")
    board = os.path.abspath(args[0]); base = os.path.basename(board); stem = os.path.splitext(base)[0]
    work = work or os.path.join("/tmp/pcb-route-waves", f"{stem}-{os.getpid()}")
    plan = json.load(open(plan_path)) if plan_path else default_plan(board)
    if "waves" not in plan:
        plan = {**plan, **default_plan(board)}
    t0 = time.time()
    def stage(name, src):
        d = os.path.join(work, name); os.makedirs(d, exist_ok=True)
        for ext in (".kicad_pcb", ".kicad_pro", ".kicad_prl"):
            f = os.path.splitext(src)[0] + ext
            if os.path.exists(f):
                shutil.copy(f, os.path.join(d, stem + ext))
        return os.path.join(d, base)
    orig = stage("input", board)
    canonical(orig)
    cur = stage("w0", orig)
    keep = len(OUT)
    start = c_measure([orig, "--drc", "--pack", pack])   # errors the input carries; the verdict compares against these,
    del OUT[keep:]                                       # not against the waves' own output
    inherited = (start.get("drc") or {}).get("plain_by_type", {})
    inherited_packed = (start.get("drc") or {}).get("packed_errors", 0)
    rec = {"board": board, "plan": plan, "work": work, "waves": [], "inherited_by_type": inherited}
    # wave 0: code, not router
    w0 = {"name": "feeds", "feeds": {}, "thermal_vias": {}}
    if plan.get("feeds") or plan.get("thermal_vias"):
        t = time.time()
        bd = Board.load(cur)
        res = bd.plan_feeds([(f["pad"], float(f["amps"])) for f in plan.get("feeds", [])])   # neighbours fan apart (FEED-2)
        for pad, r in res.items():
            w0["feeds"][pad] = {"error": r["error"][-300:]} if "error" in r else {k: r[k] for k in ("vias", "amps_capacity", "splay", "length", "across")}
        for ref in plan.get("thermal_vias", []):
            w0["thermal_vias"][ref] = {"vias": bd.thermal_vias(ref), "skipped": len(bd.thermal_skipped)}
        bd.save(); bd.fill()
        w0["wall_s"] = round(time.time() - t, 1)
        say("PCBROUTE wave 0 feeds", json.dumps(w0["feeds"]), "thermal", json.dumps(w0["thermal_vias"]), f"({w0['wall_s']} s)")
    rec["waves"].append(w0)
    log = os.path.join(work, "waves.log")
    locked = []
    for i, w in enumerate(plan["waves"], 1):
        name = w.get("name", f"wave{i}")
        inp = stage(f"w{i}-{name}-in", cur)
        polys = w.get("keepouts", [])
        put_keepouts(inp, polys, f"{name}{i}")
        guides = w.get("guides", [])   # spike #4 H3: polylines KRT steers this wave's nets through (--guide-corridor)
        put_guides(inp, guides, f"{name}{i}")
        lay = w.get("layers", "outer")
        extra = ["--nets", *w["nets"]]
        if polys:
            extra += ["--keepout", "--keepout-layer", "User.2"]
        if guides:
            extra += ["--guide-corridor", "--guide-corridor-layer", "User.1"]
        if isinstance(lay, list):
            b = pcbnew.LoadBoard(inp); cu = [b.GetLayerName(l) for l in b.GetEnabledLayers().CuStack()]
            extra += ["--layers", *cu, "--layer-costs", *["1.0" if l in lay else "-1" for l in cu]]
        extra += [str(x) for x in w.get("args", [])]
        routed, wall, rc = run_engine("krt", inp, os.path.join(work, f"w{i}-{name}"), 1, log, inner_tracks=(lay != "outer"), extra_args=extra,
                                      timeout=float(w.get("timeout_s", plan.get("timeout_s", 300))))
        if routed is None:   # a wave that times out or fails leaves its nets to the later waves and the finish
            say("PCBROUTE wave", i, name, "FAILED rc", rc, "after", wall, "s; its nets go to the later waves, see", log)
            rec["waves"].append({"name": name, "rc": rc, "wall_s": wall, "error": "timeout" if rc == "timeout" else "no board written"})
            continue
        drop_keepouts(routed, polys, f"{name}{i}")
        drop_guides(routed, guides, f"{name}{i}")
        canonical(routed)
        Board.load(routed).fill()
        keep = len(OUT)
        m = c_measure([routed])
        del OUT[keep:]
        pats = w["nets"] if w["nets"] != ["*"] else ["*"]
        open_here = {n: k for n, k in m["open"].items() if any(fnmatch.fnmatchcase(n, p) for p in pats)}
        n_locked = lock_nets(routed, pats)
        locked += pats
        wr = {"name": name, "nets": w["nets"], "layers": lay, "keepouts": len(polys), "wall_s": wall, "rc": rc,
              "airwires_left": m["ratsnest"]["airwires"], "open_in_wave": open_here, "vias": m["vias"], "length_mm": m["length_mm"],
              "locked": n_locked}
        rec["waves"].append(wr)
        say("PCBROUTE wave", i, name, "nets", w["nets"], "wall", wall, "s; open in wave", open_here, "airwires left", m["ratsnest"]["airwires"],
            "vias", m["vias"], "locked", n_locked)
        cur = routed
    dest = out or board
    keep = len(OUT)
    fin = c_auto([cur, "--work", os.path.join(work, "finish"), "--out", dest, "--pack", pack, "--baseline", orig])
    del OUT[keep:]
    rec["finish"] = {k: fin.get(k) for k in ("clean", "final", "inner_mm", "wall_s")}
    lock_nets(dest, ["*"], lock=False)   # locked only while routing; the handed-in board is ordinary copper
    Board.load(dest).fill()
    cfg_path = opt(args, "--config")
    if "--return-vias" in args and cfg_path:   # SIG-2: ground vias beside the fast nets' layer changes, before the verdict
        keep = len(OUT)
        rv = c_return_vias([dest, "--config", cfg_path] + (["--netlist", opt(args, "--netlist")] if opt(args, "--netlist") else []))
        del OUT[keep:]
        rec["return_vias"] = {k: rv[k] for k in ("placed", "covered", "skipped")}
    keep = len(OUT)
    end = c_measure([dest, "--drc", "--pack", pack])
    del OUT[keep:]
    d = end.get("drc") or {}
    rec["new_errors"] = new_errors(d.get("plain_by_type", {}), inherited)   # anything wave 0 or the waves added
    rec["clean"] = bool(end["ratsnest"]["airwires"] == 0 and not rec["new_errors"] and (d.get("packed_errors") or 0) <= inherited_packed)
    rec["wall_s"] = round(time.time() - t0, 1); rec["out"] = dest
    json.dump(rec, open(os.path.join(os.path.dirname(os.path.abspath(dest)), "waves.json"), "w"), indent=1)
    say("PCBROUTE waves verdict", "CLEAN" if rec["clean"] else "NOT CLEAN", "new errors against the input", rec["new_errors"],
        "airwires", end["ratsnest"]["airwires"], "final", json.dumps(fin.get("final")), "->", dest,
        f"({rec['wall_s']} s, work {work})")
    if not rec["clean"]:
        rec["exit"] = 1
    return rec


# ---------------------------------------------------------------------------------------------------- plan search (SIG-4)
def power_nets(b):
    """Nets in a net class at least 0.5 mm wide (the board's own power and motor rails) plus GND."""
    import fnmatch
    pro = os.path.splitext(b.GetFileName())[0] + ".kicad_pro"
    ns = json.load(open(pro)).get("net_settings", {}) if os.path.exists(pro) else {}
    w = {c["name"]: float(c.get("track_width") or 0) for c in ns.get("classes", [])}
    pats = [x["pattern"] for x in ns.get("netclass_patterns", []) if w.get(x.get("netclass"), 0) >= 0.5]
    nets = {n.GetNetname() for n in b.GetNetInfo().NetsByNetcode().values()}
    return {n for n in nets if any(fnmatch.fnmatchcase(n, p) for p in pats)} | {"GND"}


def hot_loop(b):
    """The switch node: the inductor pad net that also reaches an IC pin (L1.1 = SW on the rung-2 boards); its pads'
    bounding box grown 0.8 mm. Returns (net, [x0, y0, x1, y1], owning IC) or (None, None, None)."""
    for f in b.GetFootprints():
        if not f.GetReference().startswith("L"):
            continue
        for p in f.Pads():
            n = p.GetNetname()
            pads = [q for g in b.GetFootprints() for q in g.Pads() if q.GetNetname() == n]
            ics = {q.GetParentFootprint().GetReference() for q in pads if q.GetParentFootprint().GetReference().startswith("U")}
            if ics and n and n != "GND":   # the first inductor pad that reaches an IC: SW (a board may class SW as power)
                xs, ys = [], []
                for q in pads:
                    x, y = ToMM(q.GetPosition().x), ToMM(q.GetPosition().y); r = ToMM(q.GetBoundingRadius())
                    xs += [x - r, x + r]; ys += [y - r, y + r]
                return n, [round(min(xs) - 0.8, 2), round(min(ys) - 0.8, 2), round(max(xs) + 0.8, 2), round(max(ys) + 0.8, 2)], sorted(ics)[0]
    return None, None, None


def subsystem(b, ic, power):
    """The IC plus every two-pad part with a pad on one of the IC's non-power nets; the subsystem's local nets are the
    nets whose every pad is on those parts."""
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    ic_nets = {p.GetNetname() for p in fps[ic].Pads() if p.GetNetname() and p.GetNetname() not in power}
    members = {ic}
    for r, f in fps.items():
        pads = [p for p in f.Pads() if p.GetNetname()]
        if r != ic and len(pads) <= 3 and r[0] in "CRLD" and any(p.GetNetname() in ic_nets for p in pads):
            members.add(r)
    by_net = {}
    for r, f in fps.items():
        for p in f.Pads():
            if p.GetNetname():
                by_net.setdefault(p.GetNetname(), set()).add(r)
    local = sorted(n for n, rs in by_net.items() if rs <= members and n != "GND")
    return members, local


def plan_variants(board, base_plan):
    """The six plans of the search (PLAN-1), from the board's own classes and the base plan's feeds and thermal vias:
    rules (power, sense, rest); zones (the switch node's own subsystem in a wave of its own, later waves kept out of its
    box); rail-first (the widest rail alone with --escalation board, which necks only the terminal); motor-first (the
    first non-rail wide net alone); both; zones with escalation on the whole power wave."""
    b = pcbnew.LoadBoard(board)
    rules = default_plan(board)
    waves = rules["waves"]
    power = next((w for w in waves if w["name"] == "power"), None)
    head = {k: v for k, v in base_plan.items() if k != "waves"}
    out = {"rules": {**head, "waves": waves}}
    sw, box, ic = hot_loop(b)
    local = []
    if sw:
        _, local = subsystem(b, ic, power_nets(b))
    def zoned(ws, esc=False):
        if not sw:
            return None
        poly = [[box[0], box[1]], [box[2], box[1]], [box[2], box[3]], [box[0], box[3]]]
        res = []
        for w in ws:
            if w["name"] in ("power", "rail", "motor"):
                res.append({**w, "args": (w.get("args") or []) + (["--escalation", "board"] if esc and w["name"] == "power" else [])})
        res.append({"name": f"{ic.lower()}-local", "nets": local})
        for w in ws:
            if w["name"] not in ("power", "rail", "motor"):
                res.append({**w, "keepouts": [poly]})
        return res
    if power and len(power["nets"]) > 1:
        rails = [n for n in power["nets"] if n in (base_plan.get("rails") or ["VIN"])] or [power["nets"][0]]
        rail = rails[0]
        motors = [n for n in power["nets"] if n != rail and not any(n.startswith(r) for r in rails) and "MOTOR" in n.upper()] or \
                 [n for n in power["nets"] if n != rail][:1]
        motor = motors[0] if motors else None
        rest = lambda drop: [n for n in power["nets"] if n not in drop]
        rail_first = [{"name": "rail", "nets": [rail], "args": ["--escalation", "board"]}, {**power, "nets": rest([rail])}] + [w for w in waves if w["name"] != "power"]
        out["rail-first"] = {**head, "waves": zoned(rail_first) or rail_first}
        if motor:
            motor_first = [{"name": "motor", "nets": [motor]}, {**power, "nets": rest([motor])}] + [w for w in waves if w["name"] != "power"]
            out["motor-first"] = {**head, "waves": zoned(motor_first) or motor_first}
            both = [{"name": "motor", "nets": [motor]}, {"name": "rail", "nets": [rail], "args": ["--escalation", "board"]},
                    {**power, "nets": rest([rail, motor])}] + [w for w in waves if w["name"] != "power"]
            out["both"] = {**head, "waves": zoned(both) or both}
    if sw:
        out["zones"] = {**head, "waves": zoned(waves)}
        out["zones-esc"] = {**head, "waves": zoned(waves, esc=True)}
    return out


def judge_plan(routed, cfg_path, netlist, vin, source, sinks, waves_rec, pack):
    """The SIG-4 judges on one routed board: pcbcheck refplane/return_via/exposure/currents, irdrop on the rail, the
    route measure. Returns the row the ranking reads (the bench's `judges` writes the same keys)."""
    d = os.path.dirname(routed)
    cfg = json.load(open(cfg_path)) if cfg_path else {}
    cfg.setdefault("refplane", {"ground": "GND"}); cfg.setdefault("return_via", {"ground": "GND"}); cfg.setdefault("exposure", {})
    jc = os.path.join(d, "judge_checks.json"); json.dump(cfg, open(jc, "w"))
    cmd = [PCB, "check", routed, jc, "--only", "currents,refplane,return_via,exposure", "--out", os.path.join(d, "judge.json")]
    if netlist:
        cmd += ["--netlist", netlist]
    subprocess.run(cmd, capture_output=True, text=True)
    j = json.load(open(os.path.join(d, "judge.json")))
    rp = [r for r in j["rows"] if r["check"] == "refplane"]
    rv = [r for r in j["rows"] if r["check"] == "return_via"]
    ex = [r for r in j["rows"] if r["check"] == "exposure"]
    off = {}
    for r in rp:
        k = str(r.get("bucket", 1)); off[k] = round(off.get(k, 0.0) + (r["value"] or 0), 1)
    ir = {}
    if vin and source:
        cmd = [PCB, "irdrop", routed, "--net", vin, "--source", source, "--out", os.path.join(d, "irdrop"), "--json"]
        for sk in sinks:
            cmd += ["--sink", sk]
        if cfg_path and not sinks:
            cmd += ["--config", cfg_path]
        p = subprocess.run(cmd, capture_output=True, text=True)
        for line in reversed(p.stdout.strip().splitlines()):
            if line.startswith("{"):
                ir = json.loads(line); break
    keep = len(OUT)
    m = c_measure([routed])
    del OUT[keep:]
    return {"clean": waves_rec.get("clean"), "new_errors": waves_rec.get("new_errors"), "airwires": m["ratsnest"]["airwires"],
            "vin_mW": ir.get("power_mW"), "vin_drop_mV": [s["drop_mV"] for s in ir.get("sinks", [])], "vin_J": ir.get("max_J_A_mm2"),
            "refplane_mm": round(sum(r["value"] or 0 for r in rp), 1), "off_by_bucket": off,
            "fast_off_mm": round(sum(r["value"] or 0 for r in rp if r.get("bucket") in (3, 4)), 1),
            "fast_gaps": sum(r.get("gaps", 0) for r in rp if r.get("bucket") in (3, 4)),
            "mid_off_mm": round(sum(r["value"] or 0 for r in rp if r.get("bucket") == 2), 1),
            "return_via_fails": [r["id"].split(":", 1)[1] for r in rv if r["status"] == "fail"],
            "return_via_bad": sum(r.get("bad", 0) for r in rv if r.get("bucket") in (3, 4)),
            "return_via_worst_mm": max([r["value"] for r in rv if r.get("bucket") in (3, 4)] or [0]),
            "exposure_mm": round(sum(r["value"] or 0 for r in ex), 1), "exposure_by_net": {r["id"].split(":", 1)[1]: r["value"] for r in ex},
            "currents_fails": [r["id"].split(":", 1)[1] for r in j["rows"] if r["check"] == "currents" and r["status"] == "fail"],
            "vias": m["vias"], "length_mm": m["length_mm"], "wall_s": waves_rec.get("wall_s")}


def c_search(args):
    """pcb route waves BOARD --search [--plan base.json] [--config checks.json] [--netlist x.xml] [--vin NET --source PADS
                                      [--sink PAD=A ...]] [--jobs N] [--fast-max MM] [--out F] [--work DIR] [--pack jlcpcb]
    The six plans of `plan_variants` routed in parallel (each its own `waves` run in --work/<plan>/), judged with the
    SIG-4 rows (refplane by bucket, return_via, exposure, currents, irdrop on --vin from --source), ranked by
    pcbsig.plan_rank (hard limits against the rules plan, then the weighted cost); the winner is copied to --out
    (default: the board). search.json beside the output lists every plan's row and the ranking. Exit 1 if no plan
    passes the hard limits (the best by cost is still written, flagged)."""
    import shutil, time, concurrent.futures as cf
    import pcbsig
    t0 = time.time()
    board = os.path.abspath(args[0]); base = os.path.basename(board); stem = os.path.splitext(base)[0]
    plan_path = opt(args, "--plan"); cfg_path = opt(args, "--config"); netlist = opt(args, "--netlist"); out = opt(args, "--out")
    work = opt(args, "--work") or os.path.join("/tmp/pcb-route-search", f"{stem}-{os.getpid()}"); pack = opt(args, "--pack", "jlcpcb")
    vin = opt(args, "--vin"); source = opt(args, "--source"); jobs = int(opt(args, "--jobs", "3")); fast_max = float(opt(args, "--fast-max", "0"))
    sinks = [args[i + 1] for i, a in enumerate(args) if a == "--sink"]
    base_plan = json.load(open(plan_path)) if plan_path else {}
    if cfg_path and "feeds" not in base_plan:   # wave 0 from the config: every feeds row whose pad is not a capacitor
        cfg = json.load(open(cfg_path))
        base_plan["feeds"] = [{"pad": f["pad"], "amps": float(f["amps"])} for f in cfg.get("feeds", []) if not f["pad"].startswith("C")]
        base_plan.setdefault("thermal_vias", list((cfg.get("thermal_vias") or {}).keys()))
    variants = plan_variants(board, base_plan)
    os.makedirs(work, exist_ok=True)
    say("PCBROUTE search", len(variants), "plans:", ", ".join(variants), "jobs", jobs, "work", work)
    if netlist:
        netlist = os.path.abspath(netlist)
    elif os.path.exists(os.path.splitext(board)[0] + ".xml"):
        netlist = os.path.splitext(board)[0] + ".xml"

    def run(name):
        d = os.path.join(work, name); os.makedirs(d, exist_ok=True)
        for f in os.listdir(os.path.dirname(board)):
            if f.startswith(stem + ".") and f.split(".")[-1] in ("kicad_pcb", "kicad_pro", "kicad_prl"):
                shutil.copy(os.path.join(os.path.dirname(board), f), os.path.join(d, f))
        pp = os.path.join(d, "plan.json"); json.dump(variants[name], open(pp, "w"), indent=1)
        pcb = os.path.join(d, base)
        extra = (["--return-vias", "--config", cfg_path] if cfg_path and "--no-return-vias" not in args else []) + (["--netlist", netlist] if netlist else [])
        p = subprocess.run([PCB, "route", "waves", pcb, "--plan", pp, "--work", os.path.join(d, "work"), "--pack", pack, *extra],
                           capture_output=True, text=True, env={**os.environ, "PYTHONHASHSEED": "0"})
        open(os.path.join(d, "waves.txt"), "w").write(p.stdout + p.stderr)
        wj = os.path.join(d, "waves.json")
        if not os.path.exists(wj):
            return name, {"error": (p.stdout + p.stderr)[-600:]}
        rec = json.load(open(wj))
        return name, {"arm": name, "run": d, **judge_plan(pcb, cfg_path, netlist, vin, source, sinks, rec, pack)}

    rows = {}
    with cf.ThreadPoolExecutor(max_workers=jobs) as ex:
        for name, row in ex.map(run, list(variants)):
            rows[name] = row
            say("PCBROUTE search plan", name, "ERROR " + row["error"][-200:] if "error" in row else
                f"clean {row['clean']} fast off {row['fast_off_mm']} mid {row['mid_off_mm']} return-via bad {row['return_via_bad']} "
                f"exposure {row['exposure_mm']} rail {row['vin_mW']} mW currents {len(row['currents_fails'])} vias {row['vias']} ({row['wall_s']} s)")
    good = [r for r in rows.values() if "error" not in r]
    rules = rows.get("rules") if "error" not in rows.get("rules", {"error": 1}) else None
    ranked, failed = pcbsig.plan_rank(good, rules, fast_max=fast_max)
    if ranked:
        win = ranked[0]; passed = True
    else:
        win = min(good, key=lambda r: pcbsig.plan_cost(r)) if good else None; passed = False
    dest = out or board
    if win:
        shutil.copy(os.path.join(win["run"], base), dest)
        for f in ("route.json", "waves.json"):
            if os.path.exists(os.path.join(win["run"], f)):
                shutil.copy(os.path.join(win["run"], f), os.path.join(os.path.dirname(os.path.abspath(dest)), f))
    rec = {"board": board, "work": work, "plans": rows, "weights": pcbsig.WEIGHTS, "fast_max": fast_max,
           "ranked": [(r["arm"], round(pcbsig.plan_cost(r), 1)) for r in ranked],
           "failed_hard": [(r["arm"], why) for r, why in failed], "winner": win["arm"] if win else None, "passed": passed,
           "wall_s": round(time.time() - t0, 1), "out": dest}
    json.dump(rec, open(os.path.join(os.path.dirname(os.path.abspath(dest)), "search.json"), "w"), indent=1)
    say("PCBROUTE search verdict", f"winner {rec['winner']}" + ("" if passed else " (NO plan met the hard limits; best by cost written)"),
        "ranked", rec["ranked"], "failed", rec["failed_hard"], "->", dest, f"({rec['wall_s']} s)")
    if not passed:
        rec["exit"] = 1
    return rec


def fast_nets(board, cfg_path, netlist=None, buckets_wanted=(3, 4)):
    """Nets in the wanted buckets from the config's `signals` block (SIG-1)."""
    import pcbsig
    cfg = json.load(open(cfg_path)) if cfg_path else {}
    nets = pcbsig.netlist_nets(netlist) if netlist else None
    return sorted(n for n, bk in pcbsig.buckets(cfg, nets).items() if bk in buckets_wanted)


def c_return_vias(args):
    """pcb route return-vias BOARD --config checks.json [--netlist x.xml] [--max-mm 2.0] [--buckets 3,4] [--dry]
    A ground via beside every via of a bucket-3/4 net that has none within max_mm (pcblib return_vias, SIG-2); the
    board is saved unfilled and refilled. Prints what was placed and what could not be."""
    board = os.path.abspath(args[0]); cfg_path = opt(args, "--config"); netlist = opt(args, "--netlist")
    max_mm = float(opt(args, "--max-mm", "2.0")); want = tuple(int(x) for x in opt(args, "--buckets", "3,4").split(","))
    if not cfg_path:
        sys.exit("pcbroute return-vias: --config checks.json with a signals block is required (which nets are fast)")
    nets = fast_nets(board, cfg_path, netlist, want)
    bd = Board.load(board)
    res = bd.return_vias(nets, max_mm=max_mm, dry="--dry" in args)
    if res["placed"] and "--dry" not in args:
        bd.save(); bd.fill()
    rec = {"board": board, "nets": nets, "placed": len(res["placed"]), "covered": res["covered"], "skipped": res["skipped"],
           "vias": res["placed"]}
    say("PCBROUTE return-vias", f"{len(res['placed'])} ground vias placed beside {', '.join(sorted({p[0] for p in res['placed']})) or 'nothing'};",
        res["covered"], "fast vias already covered;", len(res["skipped"]), "skipped", res["skipped"][:3])
    return rec


def c_classes(args):
    """pcb route classes BOARD --config checks.json [--round 0.05] [--min MM] [--dry]
    Net classes from the config, for a board that has none (a foreign board on the bench): one class per IPC-2221
    external width for the `currents` amps (copper_oz outer, rise_c), named W<width>; `signals` victims in class Sense
    at the default width so the default wave plan routes them alone. Written into the .kicad_pro net_settings
    (classes and netclass_patterns), the Default class kept. KRT reads the widths; `default_plan` reads the names."""
    import pcbcheck
    board = os.path.abspath(args[0]); cfg_path = opt(args, "--config"); rnd = float(opt(args, "--round", "0.05")); dry = "--dry" in args
    if not cfg_path:
        sys.exit("pcbroute classes: --config checks.json required")
    cfg = json.load(open(cfg_path))
    pro = os.path.splitext(board)[0] + ".kicad_pro"
    pj = json.load(open(pro))
    ns = pj.setdefault("net_settings", {})
    classes = {c["name"]: c for c in ns.get("classes", [])}
    default = classes.get("Default") or {"name": "Default", "track_width": 0.2, "clearance": 0.2, "via_diameter": 0.6, "via_drill": 0.3}
    oz = float((cfg.get("copper_oz") or {}).get("outer", 1.0)); rise = float(cfg.get("rise_c", 20))
    minw = float(opt(args, "--min", str(default.get("track_width", 0.2))))
    pats = [x for x in ns.get("netclass_patterns", []) if x.get("netclass") == "Default"]
    out = {}
    for net, amps in (cfg.get("currents") or {}).items():
        w = pcbcheck.ipc2221_width_mm(float(amps), rise, oz)
        w = max(minw, round((w + rnd - 1e-9) // rnd * rnd, 2))
        name = f"W{w:g}"
        classes.setdefault(name, {**default, "name": name, "track_width": w})
        pats.append({"netclass": name, "pattern": net}); out[net] = (name, w, amps)
    import pcbsig
    for net in sorted(pcbsig.victims(cfg)):
        if net in out:
            continue
        classes.setdefault("Sense", {**default, "name": "Sense"})
        pats.append({"netclass": "Sense", "pattern": net}); out[net] = ("Sense", default.get("track_width"), None)
    ns["classes"] = [classes[k] for k in sorted(classes, key=lambda k: (k != "Default", k))]
    ns["netclass_patterns"] = pats
    if not dry:
        json.dump(pj, open(pro, "w"), indent=2)
    say("PCBROUTE classes", len(ns["classes"]) - 1, "classes for", len(out), "nets:",
        ", ".join(f"{n} -> {c} ({w} mm{', ' + str(a) + ' A' if a else ''})" for n, (c, w, a) in out.items()), "->", pro if not dry else "(dry)")
    return {"board": board, "pro": pro, "classes": [c["name"] for c in ns["classes"]], "nets": out}


CMDS = {"waves": c_waves, "return-vias": c_return_vias, "classes": c_classes, "strip": c_strip, "export-dsn": c_export_dsn, "import-ses": c_import_ses, "fill": c_fill, "measure": c_measure, "auto": c_auto,
        "canon": c_canon}


def main():
    args = sys.argv[1:]
    as_json = "--json" in args
    if as_json:
        args.remove("--json")
    if not args or args[0] not in CMDS:
        sys.exit(__doc__)
    res = CMDS[args[0]](args[1:])
    if as_json:
        print(json.dumps(res))
    else:
        print("\n".join(OUT))
    sys.exit(res.get("exit", 0) if isinstance(res, dict) else 0)


if __name__ == "__main__":
    main()
