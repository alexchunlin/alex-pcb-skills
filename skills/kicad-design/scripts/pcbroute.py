"""pcb route <command> ...: autorouting primitives and the router drivers, over SWIG pcbnew (KiCad's bundled Python).

  strip BOARD [--out F] [--zones] [--drawings]       delete tracks and vias (and zones / drawings on request); footprints and
                                                    their placement stay (pcblib Board.clear). Writes F or overwrites BOARD
  export-dsn BOARD [--out F.dsn]                    Specctra DSN via pcbnew.ExportSpecctraDSN (the freerouting input)
  import-ses BOARD F.ses [--out F]                  Specctra session back onto BOARD via pcbnew.ImportSpecctraSES, saved
  fill BOARD                                        save, reload, build connectivity, fill twice (pcblib Board.fill, P1-T10)
  auto BOARD [--engine krt|freerouting] [--out F] [--pack jlcpcb] [--max-pass 2] [--work DIR]
                                                    route what is unrouted with placement and existing copper kept: engine
                                                    pass, refill, dual DRC, a second engine pass on what is still open;
                                                    errors the input already had are inherited, not the router's. Writes
                                                    route.json beside the output; exit 1 unless clean (P6-T4)
  measure BOARD [--json] [--drc] [--pack jlcpcb] [--ref-value DRV8874]
                                                    copper as numbers: tracks, vias, length, widths, airwires left
                                                    (pcb q ratsnest), setup minimums, the nets of the footprint whose value
                                                    matches --ref-value (the 0.65 mm pitch part, R2-T2) and with --drc the
                                                    dual DRC of `pcb drc` (plain, packed, errors_total)
Output lines start with `PCBROUTE`; --json prints one JSON object instead. Evidence: P6-T1 (measurement), P6-T2 onwards
(the routers measured on the rung-2 boards).
"""
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pcbnew  # noqa: E402
from pcbnew import ToMM  # noqa: E402
from pcblib.board import Board  # noqa: E402
import pcbq  # noqa: E402

OUT = []


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


def copper(b):
    tracks, vias, length, widths, per_layer = 0, 0, 0.0, {}, {}
    via_sizes = {}
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            vias += 1
            k = f"{ToMM(t.GetWidth()):.2f}/{ToMM(t.GetDrillValue()):.2f}"
            via_sizes[k] = via_sizes.get(k, 0) + 1
        else:
            tracks += 1
            l = ToMM(t.GetLength())
            length += l
            w = round(ToMM(t.GetWidth()), 4)
            widths[w] = widths.get(w, 0) + 1
            ln = b.GetLayerName(t.GetLayer())
            per_layer[ln] = round(per_layer.get(ln, 0.0) + l, 3)
    return {"tracks": tracks, "vias": vias, "length_mm": round(length, 3), "min_width_mm": min(widths) if widths else None,
            "widths": {str(k): v for k, v in sorted(widths.items())}, "via_sizes": via_sizes, "length_per_layer_mm": per_layer}


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
    say("PCBROUTE measure", path, "tracks", r["tracks"], "vias", r["vias"], "length", r["length_mm"], "minw", r["min_width_mm"],
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


def run_engine(engine, board, out_dir, pass_no, log):
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
        extra = KRT_PASSES[min(pass_no, len(KRT_PASSES)) - 1]
        cmd = [KRT_PY, os.path.join(KRT_DIR, "py_router/route.py"), board, routed, "--json-out", os.path.join(out_dir, "krt.json"), *extra]
        p = subprocess.run(cmd, cwd=KRT_DIR, capture_output=True, text=True)
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
            pcbnew.SaveBoard(routed, b)
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
    """'Pad 2 [GND] of U1 on F.Cu' -> the PAD."""
    import re
    m = re.match(r"Pad (\S+) \[.*\] of (\S+) on", desc or "")
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
        pcbnew.SaveBoard(path, b)
    return actions


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
    keep = len(OUT)
    start = c_measure([cur, "--drc", "--pack", pack])
    del OUT[keep:]
    inherited = (start.get("drc") or {}).get("plain_by_type", {})
    inherited_packed = (start.get("drc") or {}).get("packed_errors", 0)
    passes = []
    final = start
    say("PCBROUTE auto", board, "engine", engine, "airwires", start["ratsnest"]["airwires"], "inherited plain errors", inherited,
        "packed", inherited_packed, "setup", start["settings"])
    for n in range(1, max_pass + 1):
        if final["ratsnest"]["airwires"] == 0 and n > 1:
            break
        routed, wall, rc = run_engine(engine, cur, os.path.join(work, f"pass{n}"), n, log)
        if routed is None:
            say("PCBROUTE pass", n, "FAILED rc", rc, "see", log)
            passes.append({"pass": n, "rc": rc, "wall_s": wall, "error": "no board written"})
            break
        widened = widen_under_min(routed, start["settings"]["track_width"]) if engine == "freerouting" else 0
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


CMDS = {"strip": c_strip, "export-dsn": c_export_dsn, "import-ses": c_import_ses, "fill": c_fill, "measure": c_measure, "auto": c_auto}


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
