#!/usr/bin/env python3
"""Spike #1 (C): the search test. One router slot and one hour per arm, the same start (the board's archived placement).

  .venv/bin/python3 -I tools/spikes/spike1/search.py prep  --board opus2
  .venv/bin/python3 -I tools/spikes/spike1/search.py arm2  --board opus2 [--budget 3600]      KRT place_simple + judge_seeds
  .venv/bin/python3 -I tools/spikes/spike1/search.py arm3  --board opus2 --model /tmp/spike1/model.pkl [--budget 3600]
  .venv/bin/python3 -I tools/spikes/spike1/search.py kct   --board opus2 [--budget 3600]      kct optimize-placement --route-check
  .venv/bin/python3 -I tools/spikes/spike1/search.py judge --board opus2 --arm NAME --placement P.json
  .venv/bin/python3 -I tools/spikes/spike1/search.py label --board opus2 --pcb X.kicad_pcb --arm NAME

Arm (i), random candidates routed by the real router, is the generator's own rows for the board (perturb.py: the start
perturbed at the board's sigmas, every one routed), replayed in generation order; it is not run again.
Arm (ii): KiCadRoutingTools' shipped placement search as its skill runs it (plan-pcb-placement 3.1-3.7): connectors and
holes locked (place_pose.py), intent emitted from the board with decap limits from the archived placement
(check_floorplan.py --emit-intent --decaps-from), groups = the design's own Zener modules (BUCK, DRV, LDO, PWR, CONN,
anchored on their chip or connector), then batches of 12 seeds (6 scattered, 6 clustered) placed by place_simple, the 6
it names fast-routed by judge_seeds.py (route.py at --quick 2 on our `outer` arguments) and the best by
quick_score.judge_key full-routed. Arm (iii): the same place_simple batches, 24 seeds, every legal seed scored by the
GBT (features.py on the seed's placement and its MPS conflicts) and only the top one full-routed. kct: CMA-ES from the
current placement with its own route-check acceptance, the result full-routed by KRT.
A full route is the bench's `krt outer` call (perturb.py krt/finish: the label the dataset uses); a placement whose
stripped board has more overlap-type DRC errors than the archived one is not routed. Every router call is a row in
tools/bench/results/search.jsonl. judge: the placement put on the plan bench's input (Alex's stackup: tracks and non-GND
pours stripped, In2 GND), routed by `pcb route waves` on the rules plan, and scored by plan_bench.judges (refplane,
return_via, exposure, irdrop) plus the board's `feeds` and `decoupling` rows.
"""
import argparse, datetime as dt, importlib.util, json, os, pickle, re, shutil, subprocess, sys, time
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import features as F  # noqa: E402
import surrogate as S  # noqa: E402
import dataset as D  # noqa: E402

ROOT = HERE.parents[2]
PCB = str(ROOT / "skills/kicad-design/scripts/pcb")
RESULTS = ROOT / "tools/bench/results/search.jsonl"
SR = Path("/tmp/spike1/search")


def mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


P = mod("perturb", ROOT / "tools/spikes/spike4/perturb.py")
P.SCR = Path("/tmp/spike1/gen")
rb = P.rb
KRT_DIR, KRT_PY = rb.KRT_DIR, rb.KRT_PY
OUTER = ["--no-fix-drc-settings", "--escalation", "off", "--layers", "F.Cu", "In1.Cu", "In2.Cu", "B.Cu", "--layer-costs", "1.0", "-1", "-1", "1.0"]


def sh(cmd, cwd=None, timeout=None):
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, cwd=cwd, timeout=timeout,
                       env={**os.environ, "PYTHONHASHSEED": "0"})
    return p.returncode, p.stdout, p.stderr


def krt_tool(script, *args, timeout=None):
    return sh([KRT_PY, "-X", "utf8", Path(KRT_DIR) / script, *args], cwd=KRT_DIR, timeout=timeout)


def summary_json(out):
    line = next((l for l in reversed(out.splitlines()) if l.startswith("JSON_SUMMARY:")), None)
    return json.loads(line.split(":", 1)[1]) if line else None


def log_call(row):
    row = {"ts": dt.datetime.now().isoformat(timespec="seconds"), "tag": "spike1-search", **row}
    with RESULTS.open("a") as fh:
        fh.write(json.dumps(row) + "\n")
    print(json.dumps({k: v for k, v in row.items() if k not in ("placement", "feat", "edges", "signal_vias_by_net")}), flush=True)


# ------------------------------------------------------------------------------------------------------------- prep
def groups_of(board):
    """The design's own modules (the Zener Path property: BUCK.C1 -> BUCK) as KRT groups, each anchored on its first chip
    (U, then Q), else its first connector; power entry near the converters, the LDO near the buck."""
    xml = next((ROOT / "examples" / D.EXAMPLES[board] / "board").glob("*.xml"))
    g = {}
    for c in ET.parse(xml).iter("comp"):
        path = next((p.get("value") for p in c.findall("property") if p.get("name") == "Path"), "") or "TOP.x"
        g.setdefault(path.split(".")[0].lower(), []).append(c.get("ref"))
    out = []
    for name, refs in sorted(g.items()):
        refs = sorted(refs, key=lambda r: (re.sub(r"\d", "", r), int(re.sub(r"\D", "", r) or 0)))
        anchor = next((r for p in ("U", "Q", "J") for r in refs if re.fullmatch(p + r"\d+", r)), refs[0])
        grp = {"name": name, "role": "power" if name in ("buck", "ldo", "pwr", "power") else "interface" if name == "conn" else "core",
               "refs": refs, "anchor": anchor, "why": f"the design's Zener module {name.upper()}"}
        out.append(grp)
    role = {"pwr": "entry", "power_in": "entry", "power": "entry", "drv": "driver", "driver": "driver", "conn": "conn",
            "connectors": "conn", "buck": "buck", "ldo": "ldo"}
    by_role = {role.get(x["name"]): x["name"] for x in out}
    for x in out:
        near = {"entry": ["buck", "driver"], "ldo": ["buck"], "driver": ["conn"]}.get(role.get(x["name"]), [])
        near = [by_role[r] for r in near if r in by_role]
        if near:
            x["near"] = near
        if role.get(x["name"]) in ("buck", "ldo", "entry"):
            x["role"] = "power"
        elif role.get(x["name"]) == "conn":
            x["role"] = "interface"
    return {"schema": 1, "groups": out}


def prep(board):
    d = SR / board
    d.mkdir(parents=True, exist_ok=True)
    base = P.base(board)
    stem = base.stem
    for ext in (".kicad_pcb", ".kicad_pro"):
        shutil.copy(base.with_suffix(ext), d / f"in{ext}")
    src = ROOT / "examples" / D.EXAMPLES[board] / "board"
    for ext in (".kicad_pcb", ".kicad_pro"):
        shutil.copy(src / f"{stem}{ext}", d / f"ref{ext}")
    st = D.static(board)
    fixed = [f["ref"] for f in st["footprints"] if re.match(r"(J|H|MH)\d", f["ref"])]
    rc, out, err = krt_tool("py_placer/place_pose.py", d / "in.kicad_pcb", d / "fixed.kicad_pcb", "lock", *fixed)
    assert rc == 0, (out + err)[-500:]
    rc, out, err = krt_tool("py_tools/check_floorplan.py", d / "fixed.kicad_pcb", "--emit-intent", d / "intent.json", "--decaps-from", d / "ref.kicad_pcb")
    assert rc == 0, (out + err)[-500:]
    json.dump(groups_of(board), open(d / "groups.json", "w"), indent=1)
    rc, out, err = krt_tool("py_tools/check_groups.py", d / "fixed.kicad_pcb", "--groups", d / "groups.json", "--intent", d / "intent.json")
    (d / "check_groups.txt").write_text(out + err)
    (d / "chain.txt").write_text(" ".join(["python3", str(Path(KRT_DIR) / "py_router/route.py"), "{in}", "{out}", *OUTER,
                                           "--json-out", "{dir}/route.json"]) + "\n")
    base_err = P.overlap_errors(json.load(open(P.SCR / board / "p0" / "drc" / "drc.json"))["plain"]["by_type"].get("error", {}))
    json.dump({"board": board, "stem": stem, "fixed": fixed, "base_overlap_errors": base_err, "check_groups_rc": rc}, open(d / "prep.json", "w"))
    print(f"prep {board}: locked {fixed}; check_groups rc {rc}; base overlap errors {base_err}; {d}")


# ----------------------------------------------------------------------------------------------------- one label
def meta_of(board, pcb, k, extra):
    """Start measure, MPS conflicts and the placement of a candidate board (as perturb.gen_one records them)."""
    sh([PCB, "route", "canon", pcb])
    sh([PCB, "route", "fill", pcb])
    start = rb.pcb_json("route", "measure", str(pcb), "--drc")
    rc, out, err = sh([PCB, "q", pcb, "conflicts", "--as-is", "--json"])
    c = P.last_json(out)
    rc, out, err = sh([PCB, "q", pcb, "fps", "--json"])
    pl = [[f["ref"], f["pos"][0], f["pos"][1], f["rot"]] for f in P.last_json(out)["footprints"]]
    dd = start.get("drc", {})
    return {"board": board, "k": k, "seed": extra.get("seed"), "sigma": None, "moved": None, "placement": pl, "pcb": str(pcb),
            "conflicts": c["conflicts"], "signal_conflicts": c["signal_conflicts"], "rounds": c["rounds"], "nets": c["nets"],
            "bipartite": c["bipartite"], "late_nets": c["late_nets"], "edges": c["edges"], "hpwl_mm": c["hpwl_mm"],
            "hpwl_signal_mm": c["hpwl_signal_mm"], "plane_nets": c["plane_nets"], "airwires_start": start["ratsnest"]["airwires"],
            "errors_start": [dd.get("plain_errors"), dd.get("packed_errors")], "settings": start["settings"],
            "start_by_type": dd.get("plain_by_type") or {}}


def candidate(board, src, cdir):
    """Copy a placed board (and its project) into its own folder under the board's stem."""
    pr = json.load(open(SR / board / "prep.json"))
    cdir.mkdir(parents=True, exist_ok=True)
    pcb = cdir / f"{pr['stem']}.kicad_pcb"
    shutil.copy(src, pcb)
    shutil.copy(SR / board / "in.kicad_pro", cdir / f"{pr['stem']}.kicad_pro")
    return pcb


def legal(board, meta):
    pr = json.load(open(SR / board / "prep.json"))
    return P.overlap_errors(meta["start_by_type"]) <= pr["base_overlap_errors"]


def full_route(board, meta, arm, info):
    t = time.time()
    rr = P.krt(meta)
    row = P.finish(meta, rr, "spike1-search")
    row["feat"] = D.feat_of(row, D.static(board), D.decoupling(board))
    keep = {k: row.get(k) for k in ("clean", "airwires", "new_errors", "signal_vias", "vias", "length_mm", "wall_s", "conflicts",
                                    "signal_conflicts", "hpwl_mm", "placement", "feat", "error")}
    log_call({"board": board, "arm": arm, "kind": "full", **info, **keep, "call_s": round(time.time() - t, 1)})
    return row


# ---------------------------------------------------------------------------------------------------- arms ii, iii
def place_batch(board, bdir, seeds, clustered, judge):
    d = SR / board
    bdir.mkdir(parents=True, exist_ok=True)
    rc, out, err = krt_tool("py_placer/place_simple.py", d / "fixed.kicad_pcb", bdir / "s{seed}.kicad_pcb", "--groups", d / "groups.json",
                            "--intent", d / "intent.json", "--seeds", seeds, "--clustered-seeds", clustered, "--judge", judge, "--jobs", "2",
                            "--json", bdir / "s{seed}.json", timeout=1800)
    (bdir / "place.log").write_text(out + err)
    j = json.load(open(bdir / "judge.json")) if (bdir / "judge.json").exists() else {}
    return rc, j


def resume(board, arm, elapsed0):
    """A restarted arm carries on: next batch, call count and the arm's elapsed time so far (the machine slept once mid-arm,
    so the elapsed time is passed in, not read off the clock)."""
    rows = [json.loads(l) for l in RESULTS.read_text().splitlines() if l.strip()] if RESULTS.exists() else []
    rows = [r for r in rows if r.get("tag") == "spike1-search" and r["board"] == board and r["arm"] == arm and "batch" in r]
    b = max((r["batch"] for r in rows), default=-1) + 1
    return time.time() - (elapsed0 or 0.0), b, len([r for r in rows if r.get("kind") in ("quick", "full")])


def arm2(board, budget, elapsed0=0.0):
    d = SR / board / "arm2"
    t0, b, calls = resume(board, "arm2", elapsed0)
    while time.time() - t0 < budget:
        bdir = d / f"b{b}"
        s0 = 12 * b
        rc, j = place_batch(board, bdir, f"{s0}-{s0 + 11}", f"{s0 + 6}-{s0 + 11}", "6")
        named = j.get("judge") or []
        if not named:
            print(f"arm2 b{b}: place_simple rc {rc}, no seed named", flush=True)
            b += 1
            continue
        tq = time.time()
        rc, out, err = krt_tool("py_placer/judge_seeds.py", bdir / "judge.json", "--chain", SR / board / "chain.txt",
                                "--intent", SR / board / "intent.json", "--jobs", "1", timeout=3600)
        (bdir / "judge.log").write_text(out + err)
        sm = summary_json(out) or {}
        for s, v in (sm.get("seeds") or {}).items():
            calls += 1
            log_call({"board": board, "arm": "arm2", "kind": "quick", "batch": b, "seed": int(s), "call": calls,
                      "elapsed_s": round(time.time() - t0, 1), "quick": v})
        for s in sm.get("ranking") or []:
            if time.time() - t0 >= budget:
                break
            pcb = candidate(board, bdir / f"s{s}.kicad_pcb", bdir / f"c{s}")
            meta = meta_of(board, pcb, 1000 + int(s), {"seed": int(s)})
            if not legal(board, meta):
                print(f"arm2 b{b} s{s}: more overlap-type DRC errors than the archived placement, next seed", flush=True)
                continue
            calls += 1
            full_route(board, meta, "arm2", {"batch": b, "seed": int(s), "call": calls, "elapsed_s": round(time.time() - t0, 1),
                                             "judge_rank": (sm.get("ranking") or []).index(s)})
            break
        b += 1


def arm3(board, budget, model_path, top=1, elapsed0=0.0):
    md = pickle.load(open(model_path, "rb"))
    m, f0 = md["model"], md["p0"][board]
    st, dec = D.static(board), D.decoupling(board)
    d = SR / board / "arm3"
    t0, b, calls = resume(board, "arm3", elapsed0)
    while time.time() - t0 < budget:
        bdir = d / f"b{b}"
        s0 = 1000 + 24 * b    # seeds apart from arm (ii)'s
        rc, j = place_batch(board, bdir, f"{s0}-{s0 + 23}", f"{s0 + 12}-{s0 + 23}", "24")
        named = j.get("judge") or []
        scored = []
        for s in named:   # the scoring needs only the placement and KRT's conflict counts (no DRC): a few seconds a seed
            sp = bdir / f"s{s}.kicad_pcb"
            c = P.last_json(sh([PCB, "q", sp, "conflicts", "--as-is", "--json"])[1])
            pl = [[x["ref"], x["pos"][0], x["pos"][1], x["rot"]] for x in P.last_json(sh([PCB, "q", sp, "fps", "--json"])[1])["footprints"]]
            f = F.features(st, pl, dec, (c["conflicts"], c["signal_conflicts"]))
            pc, ps = m.predict_feats([f], f0)
            scored.append((float(pc[0]), float(ps[0]), int(s)))
        scored.sort(key=lambda x: (-x[0], x[1]))
        (bdir / "scores.json").write_text(json.dumps([[s, pc, ps] for pc, ps, s in scored]))
        print(f"arm3 b{b}: {len(named)} named, top {[(s, round(pc, 3), round(ps, 3)) for pc, ps, s in scored[:3]]}", flush=True)
        routed = 0
        for pc, ps, s in scored:
            if routed >= top or time.time() - t0 >= budget:
                break
            pcb = candidate(board, bdir / f"s{s}.kicad_pcb", bdir / f"c{s}")
            meta = meta_of(board, pcb, 2000 + s, {"seed": s})
            if not legal(board, meta):
                print(f"arm3 b{b} s{s}: more overlap-type DRC errors than the archived placement, next seed", flush=True)
                continue
            calls += 1
            routed += 1
            full_route(board, meta, "arm3", {"batch": b, "seed": s, "call": calls, "elapsed_s": round(time.time() - t0, 1),
                                             "p_clean": round(pc, 4), "pred_sv": round(ps, 4), "scored_seeds": len(scored)})
        b += 1


def kct(board, budget):
    """kct optimize-placement from the current placement, its own --route-check acceptance; then the label."""
    d = SR / board / "kct"
    d.mkdir(parents=True, exist_ok=True)
    src = candidate(board, SR / board / "in.kicad_pcb", d / "in")
    out_pcb = d / "out" / src.name
    out_pcb.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(SR / board / "in.kicad_pro", out_pcb.with_suffix(".kicad_pro"))
    t = time.time()
    p = subprocess.run(["kct", "optimize-placement", str(src), "-o", str(out_pcb), "--seed", "current", "--route-check",
                        "--time-budget", str(budget), "--pad-anchored-wirelength", "--format", "json"],
                       capture_output=True, text=True, timeout=budget + 1800)
    (d / "kct.log").write_text(p.stdout + p.stderr)
    info = {"rc": p.returncode, "kct_wall_s": round(time.time() - t, 1)}
    print("kct:", info, (p.stdout + p.stderr)[-600:], flush=True)
    if out_pcb.exists():
        meta = meta_of(board, out_pcb, 3000, {"seed": 0})
        if legal(board, meta):
            full_route(board, meta, "kct", {"call": 1, "elapsed_s": round(time.time() - t, 1), **info})
        else:
            log_call({"board": board, "arm": "kct", "kind": "illegal", **info, "start_by_type": meta["start_by_type"]})
    else:
        log_call({"board": board, "arm": "kct", "kind": "none", **info})


# -------------------------------------------------------------------------------------------------------- dev judges
def judge(board, arm, placement):
    """The placement on the plan bench's input, `pcb route waves` on the rules plan, plan_bench.judges and feeds/decoupling."""
    pb = mod("plan_bench", ROOT / "tools/bench/plan_bench.py")
    src, cfg, _ = pb.board_src(board)
    d = Path("/tmp/spike1/plan") / board / arm
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    for f in src.iterdir():
        if f.suffix in (".kicad_pcb", ".kicad_pro", ".kicad_prl"):
            shutil.copy(f, d / f.name)
    pcb = next(d.glob("*.kicad_pcb"))
    json.dump(placement, open(d / "placement.json", "w"))
    rc, out, err = sh([PCB, "py", ROOT / "tools/spikes/spike4/perturb_kpy.py", pcb, pcb, "--apply", d / "placement.json"])
    assert rc == 0, (out + err)[-400:]
    sh([PCB, "route", "canon", pcb])
    sh([PCB, "route", "strip", pcb])
    pb.kpy("prep", pcb)
    plan = pb.kpy("rules", pcb)
    json.dump(plan, open(d / "plan.json", "w"), indent=1)
    t = time.time()
    rc, out, err = sh([PCB, "route", "waves", pcb, "--plan", d / "plan.json", "--work", d / "work"])
    (d / "waves.txt").write_text(out + err)
    waves = json.load(open(d / "waves.json")) if (d / "waves.json").exists() else {}
    j = pb.judges(board, pcb, waves) if waves else {"error": (out + err)[-300:]}
    rc, out, err = sh([PCB, "check", pcb, cfg, "--only", "feeds,decoupling", "--netlist", pb.netlist_of(board), "--out", d / "rows.json"])
    rows = json.load(open(d / "rows.json"))["rows"] if (d / "rows.json").exists() else []
    for fam in ("feeds", "decoupling"):
        fr = [x for x in rows if x["check"] == fam]
        j[fam] = {"n": len(fr), "fail": [x["id"].split(":", 1)[1] for x in fr if x["status"] == "fail"]}
    row = {"ts": dt.datetime.now().isoformat(timespec="seconds"), "tag": "spike1-judge", "board": board, "arm": arm,
           "waves_wall_s": round(time.time() - t, 1), **j}
    with RESULTS.open("a") as fh:
        fh.write(json.dumps(row) + "\n")
    print(json.dumps(row), flush=True)
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["prep", "arm2", "arm3", "kct", "judge", "label"])
    ap.add_argument("--board", required=True)
    ap.add_argument("--budget", type=float, default=3600)
    ap.add_argument("--elapsed0", type=float, default=0.0, help="arm2/arm3 restart: the arm's elapsed seconds so far")
    ap.add_argument("--model", default="/tmp/spike1/model.pkl")
    ap.add_argument("--arm")
    ap.add_argument("--placement")
    ap.add_argument("--pcb")
    a = ap.parse_args()
    if a.cmd == "prep":
        prep(a.board)
    elif a.cmd == "arm2":
        arm2(a.board, a.budget, a.elapsed0)
    elif a.cmd == "arm3":
        arm3(a.board, a.budget, a.model, elapsed0=a.elapsed0)
    elif a.cmd == "kct":
        kct(a.board, a.budget)
    elif a.cmd == "judge":
        judge(a.board, a.arm, json.load(open(a.placement)))
    elif a.cmd == "label":
        pcb = candidate(a.board, a.pcb, SR / a.board / (a.arm or "label") / Path(a.pcb).stem)
        meta = meta_of(a.board, pcb, 4000, {})
        full_route(a.board, meta, a.arm or "label", {"legal": legal(a.board, meta)})


if __name__ == "__main__":
    main()
