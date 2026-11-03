#!/usr/bin/env python3
"""Route bench: the autorouters measured against the designers' own copper on the archived rung-2 boards (phase 6).

For each board (examples/rung2-zener-a1-{sonnet,opus,fable}/board/) and variant, the copper is stripped with placement
kept (`pcb route strip`; `tracks` keeps the zones, `all` deletes them too), each router runs on the stripped board, the
zones are refilled and the result is measured with `pcb route measure --drc`:

  airwires        connections still open after the run (pad clusters, P6-T1); clean = 0 airwires and 0 plain DRC errors
  errors          plain / packed DRC errors (`pcb drc --pack jlcpcb`, the headline is errors_total); errors_start is the
                  same on the stripped input, so errors the placement and pours carry are not charged to the router
  vias, length    via count and total track length in mm; `part` is the same for the DRV8874's nets (R2-T2)
  signal_vias     vias on nets with no filled zone on an inner layer: the router's layer changes, without the plane
                  stitching that `vias` also counts (spike #4)
  wall_s          router wall time (export/import and refill are `overhead_s`)
  setup_changed   the board-setup minimums differ from the input's (a router that loosened the rules to read 0, R1-A2-T5)
  inner_mm        track length on the inner layers, which are planes on every rung-2 board (R2A2-T1: signals on the planes)
  narrow          nets in a wide net class (track width above Default's) with a track under the class width (R2A2-T1:
                  0.2 mm stubs on the 4 A rails; KRT reads only the Default class unless --power-nets says otherwise)
  feeds, currents the board's archived checks.json rows of those two families, run on the routed copper (R2A2-O-1, O-2)

Routers (env paths): freerouting 2.5.0 jar (`FREEROUTING_JAR`, `JAVA`; DSN out of pcbnew, SES back in), KiCadRoutingTools
(`KRT_DIR`, `KRT_PY`; reads and writes the .kicad_pcb), kct (`KCT`), and `designer` = the archived copper as handed in.

  python3 -I tools/bench/route_bench.py                        # every board, variant, router at its configs (about 25 min)
  python3 -I tools/bench/route_bench.py --boards opus --variants tracks --routers krt,freerouting --configs default
  python3 -I tools/bench/route_bench.py --reps 3               # repeat each run (spread of a nondeterministic router)
  python3 -I tools/bench/route_bench.py table [--results F]    # one line per (board, variant, router, config, rep)
Scratch: /tmp/alexpcb-route/run-<pid>. Results append to tools/bench/results/route.jsonl. Plain python3, standard library.
"""
from __future__ import annotations

import argparse, datetime as dt, fnmatch, glob, json, os, re, shutil, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "tools/bench/results/route.jsonl"
SCRATCH = Path("/tmp/alexpcb-route")
PCB = os.environ.get("PCB", str(ROOT / "skills/kicad-design/scripts/pcb"))
FR_JAR = os.environ.get("FREEROUTING_JAR", "/tmp/pcb-ref/freerouting/freerouting-2.5.0.jar")
JAVA = os.environ.get("JAVA", "/opt/homebrew/opt/openjdk/bin/java")
KRT_DIR = os.environ.get("KRT_DIR", "/tmp/pcb-ref/KiCadRoutingTools")
KRT_PY = os.environ.get("KRT_PY", os.path.join(KRT_DIR, ".venv/bin/python"))
KCT = os.environ.get("KCT", "kct")
BOARDS = {**{a: f"examples/rung2-zener-a1-{a}/board" for a in ("sonnet", "opus", "fable")}, "opus2": "examples/rung2-zener-a2-opus/board"}
VARIANTS = {"tracks": [], "all": ["--zones"]}
# router -> config name -> extra arguments. KRT: --no-fix-drc-settings keeps the board setup as the designer set it (its
# default rewrites the .kicad_pro floors to the routed values, R1-A2-T5 as a feature); --escalation off keeps the net-class
# widths and clearances exact. freerouting: the optimizer threshold is the only documented quality knob.
CONFIGS = {
    "freerouting": {"default": [], "precision": ["--router.optimizer.improvement_threshold=0.5"]},
    "krt": {"default": ["--no-fix-drc-settings", "--escalation", "off"], "board": ["--no-fix-drc-settings", "--escalation", "board"],
            "raw": [],
            # @OUTER: tracks on F.Cu/B.Cu only, the inner layers obstacle-only with vias through them (KRT's own recipe for
            # --layer-costs -1); @POWER: every wide-class net at its class width (R2A2-T1). Both expand per board.
            "outer": ["--no-fix-drc-settings", "--escalation", "off", "@OUTER"],
            "power": ["--no-fix-drc-settings", "--escalation", "off", "@POWER"],
            "outer_power": ["--no-fix-drc-settings", "--escalation", "off", "@OUTER", "@POWER"],
            "outer_noneck": ["--no-fix-drc-settings", "--escalation", "off", "@OUTER", "--no-power-tap-neckdown"],
            # spike #4 (H2): net-order arms on the outer config. outer = KRT's default --ordering mps; original = the '*'
            # expansion in name order; gp_* = KRT's global plan (#589) reordering from probe-routed conflicts
            # (KICAD_GLOBAL_PLAN=1 plus KICAD_GLOBAL_PLAN_ORDER in KRT 0.23.7); rand<N> = KRT's own routed-net list
            # (pcbkrt.py nets) shuffled with seed N, passed as --nets under --ordering original
            "outer_original": ["--no-fix-drc-settings", "--escalation", "off", "@OUTER", "--ordering", "original"],
            **{f"outer_gp_{o}": ["--no-fix-drc-settings", "--escalation", "off", "@OUTER", "@ENV:KICAD_GLOBAL_PLAN=1",
                                 f"@ENV:KICAD_GLOBAL_PLAN_ORDER={o}"] for o in ("planar", "share", "contended")},
            **{f"outer_rand{n}": ["--no-fix-drc-settings", "--escalation", "off", "@OUTER", f"@SHUFFLE:{n}"] for n in range(1, 6)}},
    "kct": {"default": [], "negotiated": ["--strategy", "negotiated"]},
}


def sh(cmd, cwd=None, timeout=None, log=None, env=None):
    t = time.time()
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
        rc, out, err, to = p.returncode, p.stdout, p.stderr, False
    except subprocess.TimeoutExpired as e:
        rc, out, err, to = -1, (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or ""), \
            (e.stderr or b"").decode(errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or ""), True
    wall = time.time() - t
    if log:
        Path(log).write_text("$ " + " ".join(map(str, cmd)) + f"\nrc={rc} wall={wall:.1f}s timeout={to}\n--- stdout\n{out}\n--- stderr\n{err}")
    return rc, out, err, wall, to


def pcb_json(*args, cwd=None):
    rc, out, err, _, _ = sh([PCB, *args, "--json"], cwd=cwd)
    if rc != 0:
        raise RuntimeError(f"pcb {' '.join(map(str, args))}: rc {rc}\n{out[-500:]}\n{err[-500:]}")
    return json.loads(out.strip().splitlines()[-1])


def cu_layers(pcb: Path) -> list[str]:
    ls = re.findall(r'\(\d+ "((?:F|B|In\d+)\.Cu)" (?:signal|power|mixed|jumper)', pcb.read_text())
    return sorted(set(ls), key=lambda l: (l != "F.Cu", l == "B.Cu", l))   # F.Cu, In1..n, B.Cu


def wide_classes(pro: Path) -> list[tuple[str, float]]:
    """(net pattern, class track width) for every class wider than Default, from the .kicad_pro (the designer's intent)."""
    ns = json.loads(pro.read_text()).get("net_settings", {})
    w = {c["name"]: float(c.get("track_width") or 0) for c in ns.get("classes", [])}
    base = w.get("Default", 0.0)
    return [(x["pattern"], w[x["netclass"]]) for x in ns.get("netclass_patterns", []) if w.get(x.get("netclass"), 0) > base + 1e-9]


def krt_nets(pcb: Path) -> list[str]:
    """The nets KRT routes on this board by default, in its order (its own functions, under its venv)."""
    p = subprocess.run([KRT_PY, "-I", str(ROOT / "skills/kicad-design/scripts/pcbkrt.py"), "nets", str(pcb)], capture_output=True, text=True,
                       env={**os.environ, "KRT_DIR": KRT_DIR})
    if p.returncode:
        raise RuntimeError(f"pcbkrt nets: {p.stderr[-400:]}")
    return json.loads(p.stdout.strip().splitlines()[-1])


def expand(extra: list[str], pcb: Path, env: dict | None = None) -> list[str]:
    """Config tokens to KRT arguments; @ENV:K=V tokens go into `env` (the caller's dict) instead."""
    out, tail = [], []
    for a in extra:
        if a.startswith("@ENV:"):
            k, _, v = a[5:].partition("=")
            if env is not None:
                env[k] = v
            continue
        if a.startswith("@SHUFFLE:"):
            import random
            nets = krt_nets(pcb)
            random.Random(int(a.split(":", 1)[1])).shuffle(nets)
            out += ["--ordering", "original"]
            tail += ["--nets", *nets]   # literal names keep their order (net_queries.expand_net_patterns)
            continue
        if a == "@OUTER":
            ls = cu_layers(pcb)
            out += ["--layers", *ls, "--layer-costs", *["1.0" if l in ("F.Cu", "B.Cu") else "-1" for l in ls]]
        elif a == "@POWER":
            wc = wide_classes(pcb.with_suffix(".kicad_pro"))
            if wc:
                out += ["--power-nets", *[p for p, _ in wc], "--power-nets-widths", *[str(x) for _, x in wc]]
        else:
            out.append(a)
    return out + tail


def rules(routed: str, m: dict, board: str, out_dir: Path) -> dict:
    """The H-tool measurements: inner-layer track length, wide-class nets under their class width, and the archived
    checks.json feeds/currents rows run on this copper."""
    pcb = Path(routed)
    r = {"inner_mm": round(sum(v for k, v in (m.get("length_per_layer_mm") or {}).items() if k.startswith("In")), 1)}
    nw = m.get("net_width_mm") or {}
    narrow = {}   # net -> [narrowest width, class width, mm of track under the class width]
    for pat, w in wide_classes(pcb.with_suffix(".kicad_pro")):
        for net, by_w in nw.items():
            under = {float(k): v for k, v in by_w.items() if float(k) + 1e-6 < w}
            if fnmatch.fnmatchcase(net, pat) and under:
                narrow[net] = [min(under), w, round(sum(under.values()), 2)]
    r["narrow"] = narrow
    r["narrow_mm"] = round(sum(v[2] for v in narrow.values()), 2)
    src = ROOT / BOARDS[board]
    cfg, xml = src.parent / "checks.json", next(src.glob("*.xml"), None)
    if cfg.exists():
        out = out_dir / "pcbcheck.json"
        cmd = [PCB, "check", routed, str(cfg), "--only", "feeds,currents", "--out", str(out)] + (["--netlist", str(xml)] if xml else [])
        sh(cmd, cwd=out_dir, log=str(out_dir / "pcbcheck.log"))
        try:
            rows = json.load(open(out))["rows"]
            for fam in ("feeds", "currents"):
                fr = [x for x in rows if x["check"] == fam]
                r[fam] = {"n": len(fr), "fail": [x["id"].split(":", 1)[1] for x in fr if x["status"] == "fail"]}
        except Exception as e:  # noqa: BLE001
            r["rules_error"] = f"{type(e).__name__}: {e}"[:200]
    return r


def prep(board: str, variant: str, run: Path) -> tuple[Path, dict]:
    """Copy the archived project, strip its copper, measure the start state."""
    src = ROOT / BOARDS[board]
    d = run / board / variant / "input"
    d.mkdir(parents=True, exist_ok=True)
    pcb = None
    for f in src.iterdir():
        if f.suffix in (".kicad_pcb", ".kicad_pro", ".kicad_prl"):
            shutil.copy(f, d / f.name)
            if f.suffix == ".kicad_pcb":
                pcb = d / f.name
    pcb_json("route", "canon", str(pcb))   # KRT routes in footprint-file order; `pcb route auto` sorts first (P6-T6)
    strip = pcb_json("route", "strip", str(pcb), *VARIANTS[variant])
    start = pcb_json("route", "measure", str(pcb), "--drc")
    d = start.get("drc", {})
    return pcb, {"strip": {k: strip[k] for k in ("before", "after")}, "airwires_start": start["ratsnest"]["airwires"],
                 "settings": start["settings"], "errors_start": (d.get("plain_errors"), d.get("packed_errors")),
                 "plain_by_type_start": d.get("plain_by_type")}


def run_router(router: str, cfg: str, pcb: Path, out_dir: Path, timeout: int) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in pcb.parent.iterdir():
        if f.suffix in (".kicad_pro", ".kicad_prl"):
            shutil.copy(f, out_dir / f.name)
    routed = out_dir / pcb.name
    env = {**os.environ, "PYTHONHASHSEED": "0"}   # ROUTE-T3
    extra = expand(CONFIGS[router][cfg], pcb, env)
    r = {"rc": None, "wall_s": None, "overhead_s": 0.0, "timeout": False, "log": str(out_dir / "router.log")}
    if router == "freerouting":
        t = time.time()
        dsn = out_dir / (pcb.stem + ".dsn")
        pcb_json("route", "export-dsn", str(pcb), "--out", str(dsn))
        r["overhead_s"] += time.time() - t
        ses = out_dir / (pcb.stem + ".ses")
        cmd = [JAVA, "-Djava.awt.headless=true", "-jar", FR_JAR, "-de", str(dsn), "-do", str(ses), "-mt", "4", "-da",
               "--gui.enabled=false", "--logging.file.enabled=false", *extra]
        rc, out, err, wall, to = sh(cmd, cwd=out_dir, timeout=timeout, log=r["log"])
        r.update(rc=rc, wall_s=round(wall, 1), timeout=to)
        for line in out.splitlines():
            if "Auto-routing stage completed" in line or "Stopping the auto-router" in line:
                r["router_says"] = line.split("INFO", 1)[-1].strip()[:200]
        if ses.exists():
            t = time.time()
            pcb_json("route", "import-ses", str(pcb), str(ses), "--out", str(routed))
            r["overhead_s"] += time.time() - t
        else:
            r["error"] = "no .ses written"
    elif router == "krt":
        cmd = [KRT_PY, os.path.join(KRT_DIR, "py_router/route.py"), str(pcb), str(routed), "--json-out", str(out_dir / "krt.json"), *extra]
        rc, out, err, wall, to = sh(cmd, cwd=KRT_DIR, timeout=timeout, log=r["log"], env=env)
        r.update(rc=rc, wall_s=round(wall, 1), timeout=to)
        r["krt_env"] = {k: v for k, v in env.items() if k.startswith("KICAD_")}
        r["mps"] = next((l.strip() for l in out.splitlines() if " crossing conflicts" in l), None)
        r["order"] = [l.split("Routing ", 1)[1].split(" (id=")[0] for l in out.splitlines() if l.startswith("[") and "] Routing " in l and " (id=" in l]
        try:
            j = json.load(open(out_dir / "krt.json"))
            r["router_says"] = {k: j.get(k) for k in ("successful", "failed", "total_vias", "pad_pairs_connected", "pad_pairs_total", "min_clearance_used")}
            r["router_says"]["design_rules_narrowed"] = len((j.get("design_rules") or {}).get("narrowed") or [])
        except Exception:  # noqa: BLE001
            pass
        if not routed.exists():
            r["error"] = "no board written"
    elif router == "kct":
        cmd = [KCT, "route", str(pcb), "-o", str(routed), *extra]
        rc, out, err, wall, to = sh(cmd, cwd=out_dir, timeout=timeout, log=r["log"])
        r.update(rc=rc, wall_s=round(wall, 1), timeout=to)
        for line in out.splitlines()[-30:]:
            if "routed" in line.lower() and ("/" in line or "%" in line):
                r["router_says"] = line.strip()[:200]
        if not routed.exists():
            r["error"] = "no board written"
    else:
        raise ValueError(router)
    r["board"] = str(routed) if routed.exists() else None
    return r


def measure(routed: str, settings_before: dict) -> dict:
    t = time.time()
    try:
        pcb_json("route", "fill", routed)
    except RuntimeError as e:
        return {"error": f"fill: {e}"[:400]}
    m = pcb_json("route", "measure", routed, "--drc")
    m["overhead_s"] = round(time.time() - t, 1)
    m["setup_changed"] = {k: (settings_before.get(k), v) for k, v in m["settings"].items() if settings_before.get(k) != v} or False
    return m


def row_of(board, variant, router, cfg, rep, start, rr, m):
    r = {"ts": dt.datetime.now().isoformat(timespec="seconds"), "board": board, "variant": variant, "router": router, "config": cfg,
         "rep": rep, "airwires_start": start.get("airwires_start"), "errors_start": start.get("errors_start"),
         "plain_by_type_start": start.get("plain_by_type_start"),
         **{k: rr.get(k) for k in ("rc", "wall_s", "timeout", "error", "router_says", "log", "krt_env", "mps", "order")}}
    r["overhead_s"] = round((rr.get("overhead_s") or 0) + (m.get("overhead_s") or 0), 1)
    if "error" in m:
        r["error"] = (r.get("error") or "") + " " + m["error"]
        return r
    d = m.get("drc", {})
    r.update(airwires=m["ratsnest"]["airwires"], open_nets=m["open"], vias=m["vias"], signal_vias=m.get("signal_vias"),
             signal_vias_by_net=m.get("signal_vias_by_net"), tracks=m["tracks"], length_mm=m["length_mm"],
             min_width_mm=m["min_width_mm"], via_sizes=m["via_sizes"], plain_errors=d.get("plain_errors"), packed_errors=d.get("packed_errors"),
             errors_total=d.get("errors_total"), plain_by_type=d.get("plain_by_type"), setup_changed=m.get("setup_changed", False),
             part=m.get("part"), board_file=m["board"])
    r.update(rules(m["board"], m, board, Path(m["board"]).parent))
    r["clean"] = bool(r["airwires"] == 0 and r["plain_errors"] == 0 and r["packed_errors"] == 0)
    return r


def fmt_row(r):
    p = r.get("part") or {}
    say = r.get("router_says")
    say = (json.dumps(say) if isinstance(say, dict) else str(say or ""))[:60]
    if r.get("error") and "airwires" not in r:
        return f"{r['board']:7} {r['variant']:7} {r['router']:11} {r['config']:10} {r.get('rep', 0):>2}  ERROR {r['error'][:80]}"
    return (f"{r['board']:7} {r['variant']:7} {r['router']:11} {r['config']:10} {r.get('rep', 0):>2}  "
            f"{'CLEAN' if r.get('clean') else 'open ' if r.get('airwires') else 'drc  ':5} "
            f"air {r.get('airwires_start', '?'):>3}->{r.get('airwires', '?'):<3} err {str(r.get('plain_errors')):>3}/{str(r.get('packed_errors')):<3} "
            f"vias {str(r.get('vias')):>3} sig {str(r.get('signal_vias')):>3} len {str(r.get('length_mm')):>7} minw {str(r.get('min_width_mm')):<6} "
            f"part air {p.get('airwires', '?')} vias {p.get('vias', '?')} len {p.get('length_mm', '?')}  "
            f"wall {str(r.get('wall_s')):>6}s +{r.get('overhead_s', 0)}s  setup {'CHANGED' if r.get('setup_changed') else 'kept'}  "
            f"inner {r.get('inner_mm', '?')}mm narrow {len(r.get('narrow') or {})}/{r.get('narrow_mm', '?')}mm "
            f"feeds fail {len((r.get('feeds') or {}).get('fail', []))}/{(r.get('feeds') or {}).get('n', '?')} "
            f"currents fail {len((r.get('currents') or {}).get('fail', []))}/{(r.get('currents') or {}).get('n', '?')}  {say}")


def table(results: Path, md=False):
    rows = [json.loads(l) for l in results.read_text().splitlines() if l.strip()]
    if not md:
        for r in rows:
            print(fmt_row(r))
        return
    print("| board | variant | router / config | airwires start -> end | DRC plain / packed (start) | vias | signal vias | length mm | DRV8874 nets: open / vias / mm | min width | router wall s | setup |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        if r.get("error") and "airwires" not in r:
            print(f"| {r['board']} | {r['variant']} | {r['router']} / {r['config']} | ERROR {r['error'][:60]} | | | | | | | |")
            continue
        p = r.get("part") or {}
        st = r.get("errors_start")
        st = f" ({st[0]})" if st and st[0] else ""
        print(f"| {r['board']} | {r['variant']} | {r['router']} / {r['config']} | {r.get('airwires_start')} -> **{r.get('airwires')}** | "
              f"**{r.get('plain_errors')}** / {r.get('packed_errors')}{st} | {r.get('vias')} | {r.get('signal_vias', '')} | {r.get('length_mm'):.0f} | "
              f"{p.get('airwires', '')} / {p.get('vias', '')} / {p.get('length_mm', 0):.0f} | {r.get('min_width_mm')} | "
              f"{r.get('wall_s') if r.get('wall_s') is not None else ''} | {'changed' if r.get('setup_changed') else 'kept'} |")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", default="run", choices=["run", "table"])
    ap.add_argument("--boards", default="opus,sonnet,fable")
    ap.add_argument("--variants", default="tracks,all")
    ap.add_argument("--routers", default="designer,freerouting,krt", help="kct is available but off by default: it did not finish the Opus board in 20 min (P6-T3)")
    ap.add_argument("--configs", default="all", help="'all' or a comma list of config names applied to every router that has them")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=900, help="seconds per router run")
    ap.add_argument("--results", default=str(RESULTS))
    ap.add_argument("--tag", default="", help="free text stored with every row (which commit, which experiment)")
    ap.add_argument("--md", action="store_true", help="table: markdown for FINDINGS")
    a = ap.parse_args()
    if a.cmd == "table":
        table(Path(a.results), a.md)
        return
    run = SCRATCH / f"run-{os.getpid()}"
    run.mkdir(parents=True, exist_ok=True)
    results = Path(a.results)
    results.parent.mkdir(parents=True, exist_ok=True)
    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short=9", "HEAD"], capture_output=True, text=True).stdout.strip()
    print(f"route bench: scratch {run}, results {results}, tools {commit}")
    routers = a.routers.split(",")
    with results.open("a") as fh:
        for board in a.boards.split(","):
            if "designer" in routers:
                src = glob.glob(str(ROOT / BOARDS[board] / "*.kicad_pcb"))[0]
                d = run / board / "designer"
                d.mkdir(parents=True, exist_ok=True)
                for f in Path(src).parent.iterdir():
                    if f.suffix in (".kicad_pcb", ".kicad_pro", ".kicad_prl"):
                        shutil.copy(f, d / f.name)
                m = pcb_json("route", "measure", str(d / Path(src).name), "--drc")
                m["overhead_s"] = 0
                m["setup_changed"] = False
                r = row_of(board, "as-is", "designer", "designer", 0, {"airwires_start": m["ratsnest"]["airwires"]}, {"wall_s": None, "rc": 0}, m)
                r["tag"], r["commit"] = a.tag, commit
                fh.write(json.dumps(r) + "\n"); fh.flush()
                print(fmt_row(r), flush=True)
            for variant in a.variants.split(","):
                if not any(x in routers for x in CONFIGS):
                    continue
                pcb, start = prep(board, variant, run)
                print(f"-- {board} {variant}: stripped to {start['strip']['after']['tracks']} tracks, {start['strip']['after']['vias']} vias, "
                      f"{start['strip']['after']['zones']} zones; {start['airwires_start']} airwires to route; DRC errors before routing "
                      f"(placement and pours only) plain/packed {start['errors_start']} {start['plain_by_type_start']}", flush=True)
                for router in routers:
                    if router not in CONFIGS:
                        continue
                    cfgs = list(CONFIGS[router]) if a.configs == "all" else [c for c in a.configs.split(",") if c in CONFIGS[router]]
                    for cfg in cfgs:
                        for rep in range(1, a.reps + 1):
                            out_dir = run / board / variant / router / cfg / f"rep{rep}"
                            try:
                                rr = run_router(router, cfg, pcb, out_dir, a.timeout)
                                m = measure(rr["board"], start["settings"]) if rr.get("board") else {"error": rr.get("error", "no output")}
                            except Exception as e:  # noqa: BLE001
                                rr, m = {"error": f"{type(e).__name__}: {e}"[:400]}, {"error": "crashed"}
                            r = row_of(board, variant, router, cfg, rep, start, rr, m)
                            r["tag"], r["commit"] = a.tag, commit
                            fh.write(json.dumps(r) + "\n"); fh.flush()
                            print(fmt_row(r), flush=True)
    print(f"route bench: done, {results}")


if __name__ == "__main__":
    main()
