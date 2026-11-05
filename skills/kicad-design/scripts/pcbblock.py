"""Block-by-block placement with gates (Alex, spike #6): floorplan first, then one schematic block at a time, each proven
before the next goes on the board, the connections between blocks last.

  pcb block init BOARD [--out blocks.json]     one group per Zener module (footprint Path), KRT's groups.json format plus
                                               `region` [x0, y0, x1, y1] per group and a top-level `order`: edit both
  pcb block plan BOARD blocks.json             every part in one group, regions inside the outline and apart, parts fit,
                                               KRT check_groups' link matrix printed. Run before any block is placed
  pcb block gate BOARD blocks.json NAME [--config checks.json]
                                               NAME is the next block or an earlier passed block to re-gate; later
                                               blocks parked off the board (pcblib `park`), no courtyard overlap among the
                                               placed, parts 1 mm off the outline, placed-part `decoupling` and `feed_room`
                                               rows pass. Re-gating revokes NAME and later gates; park later blocks first.
                                               Appends to blocks-log.jsonl beside blocks.json; exit 1 on a fail
  pcb block report BOARD blocks.json [--json]  cohesion (share of the 3 nearest parts in the same block, 0 = shuffled, 1 =
                                               all), intrusion, parts out of region, gates passed, moves after a gate.
                                               Exit 1 when a part is missing, moved, out of its region, or a gate is missing.

A gate is a scoped placement check, not proof of electrical, thermal or physical correctness.
Without --config, decoupling/feed_room are not checked. History is append-only by this tool,
not tamper-proof; externally deleting or editing the log is outside its guarantees.
"""
import json, os, random, re, statistics, subprocess, sys, tempfile, time
import pcbnew
from pcbnew import ToMM

MECH = re.compile(r"(H|MH|FID)\d")


def opt(args, name, default=None):
    if name in args:
        i = args.index(name); args.pop(i)
        return args.pop(i)
    return default


def fps(b):
    return {f.GetReference(): f for f in b.GetFootprints()}


def outline(b):
    bb = b.GetBoardEdgesBoundingBox()
    return ToMM(bb.GetLeft()), ToMM(bb.GetTop()), ToMM(bb.GetRight()), ToMM(bb.GetBottom())


def box(f):
    """Pad extents of a footprint: courtyard caches are not built on a loaded board's parked parts."""
    bs = [q.GetBoundingBox() for q in f.Pads()]
    if not bs:
        return (ToMM(f.GetPosition().x),) * 2 + (ToMM(f.GetPosition().y),) * 2
    return min(ToMM(x.GetLeft()) for x in bs), max(ToMM(x.GetRight()) for x in bs), min(ToMM(x.GetTop()) for x in bs), max(ToMM(x.GetBottom()) for x in bs)


def courtyard(f):
    """The courtyard polygon on the footprint's own side, or None."""
    f.BuildCourtyardCaches()
    c = f.GetCourtyard(pcbnew.F_CrtYd if f.GetLayer() == pcbnew.F_Cu else pcbnew.B_CrtYd)
    return c if c.OutlineCount() else None


def overlaps(a, b):
    if a.GetLayer() != b.GetLayer():
        return False
    ca, cb = courtyard(a), courtyard(b)
    if ca is None or cb is None:
        return False
    x = pcbnew.SHAPE_POLY_SET(ca)
    x.BooleanIntersection(cb)
    return x.OutlineCount() > 0 and x.Area() > 1e9   # 0.001 mm^2: touching courtyards are DRC's tolerance, not an overlap


def on_board(f, o):
    p = f.GetPosition()
    return o[0] <= ToMM(p.x) <= o[2] and o[1] <= ToMM(p.y) <= o[3]


def in_region(f, r):
    x0, x1, y0, y1 = box(f)
    return x0 >= r[0] and x1 <= r[2] and y0 >= r[1] and y1 <= r[3]


def load(path):
    d = json.load(open(path))
    d["by"] = {g["name"]: g for g in d["groups"]}
    d["order"] = d.get("order") or [g["name"] for g in d["groups"]]
    return d


def log_path(path):
    return os.path.join(os.path.dirname(os.path.abspath(path)), "blocks-log.jsonl")


def read_log(path):
    p = log_path(path)
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []


def write_log(path, rec):
    with open(log_path(path), "a") as f:
        f.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), **rec}) + "\n")


def gate_state(log, order):
    """Replay history: a plan resets gates; any gate attempt revokes its suffix."""
    plan_ok, gates = False, {}
    for entry in log:
        if entry.get("cmd") == "plan":
            plan_ok = entry.get("ok") is True
            gates.clear()
        elif entry.get("cmd") == "gate" and entry.get("block") in order:
            name = entry["block"]
            idx = order.index(name)
            for later in order[idx:]:
                gates.pop(later, None)
            if plan_ok and entry.get("ok") is True and all(n in gates for n in order[:idx]):
                gates[name] = entry
    return plan_ok, gates


def footprint_pose(f):
    return [round(ToMM(f.GetPosition().x), 3), round(ToMM(f.GetPosition().y), 3),
            round(f.GetOrientationDegrees(), 3), f.GetLayer()]


def changed_pose(entry, footprints):
    changed = []
    for ref, old in entry.get("pose", {}).items():
        if ref not in footprints:
            changed.append(ref)
            continue
        current = footprint_pose(footprints[ref])
        # Legacy records contain XY only; preserve their documented 0.5 mm tolerance.
        if max(abs(current[i] - old[i]) for i in (0, 1)) > 0.5 or (len(old) > 2 and current[2:] != old[2:]):
            changed.append(ref)
    return changed


def checker_failures(bp, cfg, path, placed, later):
    """Only a fresh, structurally valid checker report can establish a result.

    Exit 1 is normal for failed rows: defer only failures entirely on parked
    later blocks. Global, unknown-object, and cross-block failures remain fatal.
    """
    try:
        with tempfile.TemporaryDirectory(prefix="blocks-check-", dir=os.path.dirname(os.path.abspath(path))) as tmp:
            out = os.path.join(tmp, "report.json")
            result = subprocess.run([
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "pcb"),
                "check", bp, cfg, "--only", "decoupling,feed_room", "--out", out,
            ], capture_output=True, text=True)
            detail = (result.stderr or result.stdout or "").strip()[-1000:]
            if result.returncode not in (0, 1):
                return [f"checker exited {result.returncode}: {detail}; fix `pcb check` and re-gate"]
            if not os.path.isfile(out):
                return [f"checker produced no fresh report (exit {result.returncode}): {detail}; run `pcb check` and fix its inputs/netlist"]
            with open(out) as stream:
                report = json.load(stream)
            rows = report["rows"]
            if not isinstance(rows, list):
                raise ValueError("rows must be a list")
            for row in rows:
                if (not isinstance(row, dict) or row.get("status") not in ("pass", "fail", "warn", "accepted")
                        or not isinstance(row.get("id"), str) or not isinstance(row.get("msg"), str)
                        or not isinstance(row.get("objects", []), list)
                        or not all(isinstance(obj, str) for obj in row.get("objects", []))):
                    raise ValueError("invalid checker row")
            failures = [row for row in rows if row["status"] == "fail"]
            if report["summary"]["fails"] != len(failures) or result.returncode != bool(failures):
                raise ValueError("exit status, summary and failure rows disagree")
            pending = set(later) - set(placed)
            return [f"{row['id']}: {row['msg'][:120]}" for row in failures
                    if not row.get("objects") or not all(obj.split(".")[0] in pending for obj in row["objects"])]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [f"checker report unavailable or invalid: {exc}; run `pcb check` and re-gate"]


def c_init(args):
    out = opt(args, "--out", "blocks.json")
    b = pcbnew.LoadBoard(args[0])
    gs = {}
    for r, f in sorted(fps(b).items()):
        if MECH.match(r):
            continue
        path = next((x.GetText() for x in f.GetFields() if x.GetName() == "Path"), "")
        gs.setdefault(path.rsplit(".", 1)[0] if "." in path else "root", []).append(r)
    d = {"schema": 1, "order": sorted(gs), "groups": [{"name": n, "role": "", "refs": r, "anchor": None, "near": [], "why": "", "region": None} for n, r in sorted(gs.items())]}
    json.dump(d, open(out, "w"), indent=1)
    print(f"PCBBLOCK init {len(gs)} groups -> {out}: set `order` (connector-bound and power blocks first) and each `region` [x0, y0, x1, y1]")


def c_plan(args):
    bp, path = args[0], args[1]
    b, d = pcbnew.LoadBoard(bp), load(args[1])
    f, o, fails = fps(b), outline(b), []
    seen = {}
    for g in d["groups"]:
        for r in g["refs"]:
            if r not in f:
                fails.append(f"{g['name']}: {r} is not on the board")
            if r in seen:
                fails.append(f"{r} is in {seen[r]} and {g['name']}")
            seen[r] = g["name"]
    fails += [f"{r} is in no group" for r in f if r not in seen and not MECH.match(r)]
    if len(d["groups"]) != len(d["by"]):
        fails.append("group names must be unique")
    if set(d["order"]) != set(d["by"]) or len(d["order"]) != len(d["by"]):
        fails.append(f"order {d['order']} does not name each group once")
    regs = [(g["name"], g.get("region")) for g in d["groups"]]
    for n, r in regs:
        if not r:
            fails.append(f"{n} has no region")
        elif len(r) != 4 or r[0] >= r[2] or r[1] >= r[3]:
            fails.append(f"{n} region must have positive width and height")
        elif r[0] < o[0] or r[1] < o[1] or r[2] > o[2] or r[3] > o[3]:
            fails.append(f"{n} region {r} leaves the outline {o}")
    for i, (n, r) in enumerate(regs):
        for m, q in regs[i + 1:]:
            if r and q and len(r) == 4 and len(q) == 4 and r[0] < q[2] and q[0] < r[2] and r[1] < q[3] and q[1] < r[3]:
                fails.append(f"regions {n} and {m} overlap")
    for g in d["groups"]:
        r = g.get("region")
        if r and len(r) == 4 and r[2] > r[0] and r[3] > r[1]:
            by_layer = {}
            for ref in g["refs"]:
                if ref in f:
                    c = courtyard(f[ref])
                    layer = f[ref].GetLayer()
                    by_layer[layer] = by_layer.get(layer, 0) + (c.Area() / 1e12 if c else 0)
            have = (r[2] - r[0]) * (r[3] - r[1])
            for layer, need in sorted(by_layer.items()):
                print(f"  {g['name']}: layer {layer}, courtyards {need:.1f} mm^2 in a {have:.1f} mm^2 region ({100 * need / have:.0f} %)")
                if need > have:
                    fails.append(f"{g['name']}: layer {layer} courtyards {need:.1f} mm^2 do not fit {have:.1f} mm^2")
    krt_py, krt = os.environ.get("KRT_PY", "/tmp/pcb-ref/KiCadRoutingTools/.venv/bin/python"), os.environ.get("KRT_DIR", "/tmp/pcb-ref/KiCadRoutingTools")
    if os.path.exists(krt_py):
        tmp = os.path.join(os.path.dirname(os.path.abspath(path)), "blocks-krt.json")   # KRT refuses keys it does not know
        keys = ("name", "role", "refs", "anchor", "near", "why")
        json.dump({"schema": 1, "groups": [{k: g[k] for k in keys if g.get(k)} for g in d["groups"]]}, open(tmp, "w"))
        r = subprocess.run([krt_py, "-X", "utf8", "py_tools/check_groups.py", os.path.abspath(bp), "--groups", tmp], cwd=krt, capture_output=True, text=True)
        print((r.stdout + r.stderr)[-2500:])
    write_log(path, {"cmd": "plan", "ok": not fails, "fails": fails})
    print(f"PCBBLOCK plan {'OK' if not fails else 'FAIL'}")
    for x in fails:
        print("  FAIL", x)
    sys.exit(1 if fails else 0)


def c_gate(args):
    cfg = opt(args, "--config")
    bp, path, name = args[0], args[1], args[2]
    b, d = pcbnew.LoadBoard(bp), load(path)
    f, o, fails = fps(b), outline(b), []
    log = read_log(path)
    plan_ok, gates = gate_state(log, d["order"])
    if not plan_ok:
        fails.append("no passing `pcb block plan` yet")
    done = list(gates)
    nxt = next((n for n in d["order"] if n not in done), None)
    if name not in d["by"]:
        sys.exit(f"pcbblock: no block {name}")
    if name != nxt and name not in done:
        fails.append(f"out of order: the next block is {nxt}")
    idx = d["order"].index(name)
    placed = [r for n in d["order"][:idx + 1] for r in d["by"][n]["refs"]]
    later = [r for n in d["order"][idx + 1:] for r in d["by"][n]["refs"]]
    fails += [f"{r} of a later block is on the board" for r in later if r in f and on_board(f[r], o)]
    fails += [f"{r} is missing from the board; restore it and re-plan" for r in placed if r not in f]
    for block in d["order"][:idx + 1]:
        reg = d["by"][block]["region"]
        fails += [f"{ref} is outside region {reg}; re-gate from {block}"
                  for ref in d["by"][block]["refs"] if ref in f and not in_region(f[ref], reg)]
    for block in d["order"][:idx]:
        if block in gates and changed_pose(gates[block], f):
            fails.append(f"{block} moved after its gate; park later blocks and re-gate from {block}")
    fails += [f"{r} is not on the board" for r in placed if r in f and not on_board(f[r], o)]
    onb = list(dict.fromkeys([r for r in placed if r in f and on_board(f[r], o)] + [r for r in f if MECH.match(r)]))
    skip_edge = set()
    if cfg:
        try:
            with open(cfg) as stream:
                config = json.load(stream)
            skip = config.get("edge_margin", {}).get("skip_refs", [])
            if not isinstance(skip, list) or not all(isinstance(ref, str) for ref in skip):
                raise ValueError("edge_margin.skip_refs must be a list of references")
            skip_edge = set(skip)
        except (OSError, ValueError, AttributeError, TypeError) as exc:
            fails.append(f"cannot read gate config {cfg}: {exc}")
    for i, r in enumerate(onb):
        x0, x1, y0, y1 = box(f[r])
        if r not in skip_edge and not re.match(r"(J|H|MH|FID)\d", r) and min(x0 - o[0], o[2] - x1, y0 - o[1], o[3] - y1) < 1.0:
            fails.append(f"{r} is within 1 mm of the outline")
        for q in onb[i + 1:]:
            if overlaps(f[r], f[q]):
                fails.append(f"courtyards of {r} and {q} overlap")
    if cfg:
        fails.extend(checker_failures(bp, cfg, path, placed, later))
    pose = {r: footprint_pose(f[r]) for r in d["by"][name]["refs"] if r in f}
    write_log(path, {"cmd": "gate", "block": name, "ok": not fails, "fails": fails, "pose": pose})
    print(f"PCBBLOCK gate {name}: {'PASS' if not fails else 'FAIL'} ({len(placed)} parts on the board, {len(later)} parked)")
    for x in fails:
        print("  FAIL", x)
    sys.exit(1 if fails else 0)


def cohesion(pts, k=3, n=200):
    """pts [(x, y, block)]: mean share of the k nearest in the same block, normalised against shuffled block labels."""
    nb = []
    for i, a in enumerate(pts):
        nb.append([j for _, j in sorted(((a[0] - c[0]) ** 2 + (a[1] - c[1]) ** 2, j) for j, c in enumerate(pts) if j != i)[:k]])
    pur = lambda lab: sum(lab[j] == lab[i] for i, ns in enumerate(nb) for j in ns) / sum(len(ns) for ns in nb)
    lab = [p[2] for p in pts]
    o, s, rng, null = pur(lab), lab[:], random.Random(0), []
    for _ in range(n):
        rng.shuffle(s); null.append(pur(s))
    u = statistics.mean(null)
    return round(o, 3), round((o - u) / (1 - u), 3)


def c_report(args):
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    b, d = pcbnew.LoadBoard(args[0]), load(args[1])
    f, log = fps(b), read_log(args[1])
    pts, outside = [], []
    for g in d["groups"]:
        if len(g["refs"]) < 3:
            continue
        for r in g["refs"]:
            if r in f:
                pts.append((ToMM(f[r].GetPosition().x), ToMM(f[r].GetPosition().y), g["name"]))
    for g in d["groups"]:
        if g.get("region"):
            outside += [r for r in g["refs"] if r in f and not in_region(f[r], g["region"])]
    _, gates = gate_state(log, d["order"])
    done = list(gates)
    moved = sorted({ref for entry in gates.values() for ref in changed_pose(entry, f)})
    for idx, name in enumerate(d["order"]):
        if name in gates and changed_pose(gates[name], f):
            done = [n for n in done if n in d["order"][:idx]]
            break
    missing = [r for g in d["groups"] for r in g["refs"] if r not in f]
    pur, norm = cohesion(pts) if len({p[2] for p in pts}) > 1 else (None, None)
    r = {"cohesion": norm, "purity": pur, "outside_region": outside, "gates_passed": [n for n in d["order"] if n in done], "gates_missing": [n for n in d["order"] if n not in done],
         "moved_after_gate": moved, "missing_footprints": missing, "gate_fails": sum(1 for e in log if e["cmd"] == "gate" and not e["ok"])}
    print(json.dumps(r) if as_json else "PCBBLOCK report " + json.dumps(r))
    sys.exit(1 if outside or moved or missing or r["gates_missing"] else 0)


def main():
    a = sys.argv[1:]
    if not a or a[0] not in ("init", "plan", "gate", "report"):
        sys.exit(__doc__)
    {"init": c_init, "plan": c_plan, "gate": c_gate, "report": c_report}[a[0]](a[1:])


if __name__ == "__main__":
    main()
