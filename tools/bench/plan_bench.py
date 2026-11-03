#!/usr/bin/env python3
"""Plan bench: who should write the wave and zone plan for `pcb route waves`, rules or an agent (PLAN-1).

Input per board: the archived rung-2 placement on Alex's stackup (tracks stripped, non-GND pours deleted, In2 one GND
zone), the same feeds and thermal vias for every arm. Only the plan differs. Judges, all deterministic:
  clean / new_errors   `pcb route waves` verdict against the input
  vin_mW, vin_drop     `pcb irdrop` VIN, Q1 source (pins 1-3) to U2.11 2.5 A and U1.4 2.8 A
  vin_J                worst current density outside pads on VIN, A/mm2
  refplane_mm          signal track not over solid ground on the adjacent layer (pcbcheck refplane)
  foreign_mm           track of nets that are not the buck's own inside the switch-node box (plan_kpy intrusion)
  fast_off_mm, fast_gaps, mid_off_mm, off_by_bucket   refplane split by the SIG-1 bucket (3/4 hard, 2 and 1 costs)
  return_via_bad, _worst_mm, _fails                   bucket-3 vias with no GND via or through-hole pad within 2 mm (SIG-2)
  exposure_mm, exposure_by_net                        same-layer track within 1 mm of SW copper, victims x3 (SIG-3)
  currents_fails       pcbcheck currents rows failing
  vias, length_mm, wall_s

  python3 -I tools/bench/plan_bench.py prep    --board opus|sonnet|opus2
  python3 -I tools/bench/plan_bench.py rules   --board B [--zones] > plan.json
  python3 -I tools/bench/plan_bench.py summary --board B             (what the agent arm reads)
  python3 -I tools/bench/plan_bench.py score   --board B --plan plan.json --arm NAME [--tag T]
  python3 -I tools/bench/plan_bench.py rescore --board B --run DIR [--tag T]      (judges only, on a finished run)
  python3 -I tools/bench/plan_bench.py table   [--results F]
  python3 -I tools/bench/plan_bench.py rank    [--results F]      PLAN-1 rule against the SIG-4 rule on the rescored rows
Results append to tools/bench/results/plan.jsonl. Scratch /tmp/alexpcb-plan/<board>/.
"""
import argparse, datetime as dt, json, os, shutil, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PCB = str(ROOT / "skills/kicad-design/scripts/pcb")
KPY = str(ROOT / "tools/bench/plan_kpy.py")
RESULTS = ROOT / "tools/bench/results/plan.jsonl"
SCRATCH = Path("/tmp/alexpcb-plan")
BOARDS = {"opus": "examples/rung2-zener-a1-opus", "sonnet": "examples/rung2-zener-a1-sonnet", "opus2": "examples/rung2-zener-a2-opus",
          # the MotorGo Plink (read-only clone, tools/bench/README.md): the designer's placement and pours kept, tracks and vias
          # stripped, net classes from tools/bench/plink/checks.json (`pcb route classes`); its own two-ground stackup stays
          "plink": {"board": "/tmp/pcb-ref/motorgo-plink-hardware/motorgo_plink", "cfg": "tools/bench/plink/checks.json",
                    "keep_pours": True, "classes": True}}
# the rail judged by irdrop per board: (net, source pads, sinks)
IRDROP = {"opus": ("VIN", "Q1.1,Q1.2,Q1.3", ["U2.11=2.5", "U1.4=2.8"]), "sonnet": ("VIN", "Q1.1,Q1.2,Q1.3", ["U2.11=2.5", "U1.4=2.8"]),
          "opus2": ("VIN", "Q1.1,Q1.2,Q1.3", ["U2.11=2.5", "U1.4=2.8"]),
          "plink": ("+BATT", "J11.1", ["U3.11=1.5", "U4.11=1.5", "U5.11=1.5", "U9.11=1.5", "U6.4=1.5"])}


def board_src(board):
    """(board dir, checks.json path, options) for a bench board."""
    b = BOARDS[board]
    if isinstance(b, dict):
        return Path(b["board"]), ROOT / b["cfg"], b
    return ROOT / b / "board", ROOT / b / "checks.json", {}


def netlist_of(board):
    src, cfg, o = board_src(board)
    x = next(src.glob("*.xml"), None)
    if x is None:   # a foreign board: export the netlist once into the scratch dir
        sch = next(src.glob("*.kicad_sch"))
        x = SCRATCH / board / (sch.stem + ".xml"); x.parent.mkdir(parents=True, exist_ok=True)
        if not x.exists():
            sh([PCB, "netlist", sch, x])
    return x


def sh(cmd, cwd=None):
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, cwd=cwd)
    return p.returncode, p.stdout, p.stderr


def last_json(out):
    for line in reversed(out.strip().splitlines()):
        if line.startswith("{"):
            return json.loads(line)
    raise RuntimeError(out[-400:])


def kpy(*args):
    rc, out, err = sh([PCB, "py", KPY, *args])
    if rc:
        raise RuntimeError(err[-600:] or out[-600:])
    return last_json(out)


def base(board):
    d = SCRATCH / board / "base"
    pcb = next(d.glob("*.kicad_pcb"), None) if d.exists() else None
    if pcb:
        return pcb
    d.mkdir(parents=True, exist_ok=True)
    src, cfg, o = board_src(board)
    for f in src.iterdir():
        if f.suffix in (".kicad_pcb", ".kicad_pro", ".kicad_prl"):
            shutil.copy(f, d / f.name)
    pcb = next(d.glob("*.kicad_pcb"))
    if o.get("classes"):
        sh([PCB, "route", "classes", pcb, "--config", cfg])
    sh([PCB, "route", "strip", pcb])   # tracks and vias; zones stay (prep below removes the non-ground ones on the rung-2 boards)
    if not o.get("keep_pours"):
        kpy("prep", pcb)
    else:
        sh([PCB, "route", "fill", pcb])
    return pcb


def judges(board, routed, waves):
    src, cfg_path, o = board_src(board)
    cfg = json.load(open(cfg_path))
    cfg["refplane"] = {"ground": "GND"}
    cfg["return_via"] = {"ground": "GND"}     # SIG-2
    cfg["exposure"] = {}                      # SIG-3: the switch node found from the inductor
    cpath = routed.parent / "judge_checks.json"
    json.dump(cfg, open(cpath, "w"))
    xml = netlist_of(board)
    sh([PCB, "check", routed, cpath, "--only", "currents,refplane,return_via,exposure", "--netlist", xml, "--out", routed.parent / "judge.json"])
    j = json.load(open(routed.parent / "judge.json"))
    rp = [r for r in j["rows"] if r["check"] == "refplane"]
    cur = [r["id"].split(":", 1)[1] for r in j["rows"] if r["check"] == "currents" and r["status"] == "fail"]
    rv = [r for r in j["rows"] if r["check"] == "return_via"]
    ex = [r for r in j["rows"] if r["check"] == "exposure"]
    off = {}
    for r in rp:
        k = str(r.get("bucket", 1))
        off[k] = round(off.get(k, 0.0) + (r["value"] or 0), 1)
    sig = {"off_by_bucket": off,                                   # mm off ground per bucket (3/4 hard, 2 cost, 1 and P cost)
           "fast_off_mm": round(sum(r["value"] or 0 for r in rp if r.get("bucket") in (3, 4)), 1),
           "fast_gaps": sum(r.get("gaps", 0) for r in rp if r.get("bucket") in (3, 4)),
           "mid_off_mm": round(sum(r["value"] or 0 for r in rp if r.get("bucket") == 2), 1),
           "return_via_fails": [r["id"].split(":", 1)[1] for r in rv if r["status"] == "fail"],
           "return_via_bad": sum(r.get("bad", 0) for r in rv if r.get("bucket") in (3, 4)),
           "return_via_worst_mm": max([r["value"] for r in rv if r.get("bucket") in (3, 4)] or [0]),
           "exposure_mm": round(sum(r["value"] or 0 for r in ex), 1),
           "exposure_by_net": {r["id"].split(":", 1)[1]: r["value"] for r in ex}}
    net, source, sinks = IRDROP[board]
    rc, out, err = sh([PCB, "irdrop", routed, "--net", net, "--source", source, *[a for sk in sinks for a in ("--sink", sk)],
                       "--out", routed.parent / "irdrop", "--json"])
    ir = last_json(out) if rc == 0 else {}
    intr = kpy("intrusion", routed, *(["--config", cfg_path] if o else []))
    m = last_json(sh([PCB, "route", "measure", routed, "--json"])[1])
    return {"clean": waves.get("clean"), "new_errors": waves.get("new_errors"), "airwires": m["ratsnest"]["airwires"],
            "vin_mW": ir.get("power_mW"), "vin_drop_mV": [s["drop_mV"] for s in ir.get("sinks", [])], "vin_J": ir.get("max_J_A_mm2"),
            "refplane_mm": round(sum(r["value"] or 0 for r in rp), 1), "foreign_mm": intr["foreign_mm"], "foreign_by_net": intr["by_net"],
            "currents_fails": cur, "vias": m["vias"], "length_mm": m["length_mm"], "wall_s": waves.get("wall_s"), **sig}


def rescore(board, run, tag="rescore"):
    """Re-run the judges on an existing run directory (no routing) and append a row; for new judges on old runs."""
    run = Path(run)
    pcb = next(f for f in run.glob("*.kicad_pcb"))
    waves = json.load(open(run / "waves.json"))
    arm = run.name.rsplit("-", 2)[0]
    old = [json.loads(l) for l in RESULTS.read_text().splitlines() if l.strip()] if RESULTS.exists() else []
    old = [r for r in old if r.get("run") == str(run) and "error" not in r]
    if old:   # keep the arm and the original tag so the rescored row joins its first scoring
        arm, tag = old[-1]["arm"], f"{old[-1].get('tag', '')}+{tag}"
    row = {"ts": dt.datetime.now().isoformat(timespec="seconds"), "board": board, "arm": arm, "tag": tag, "run": str(run),
           **judges(board, pcb, waves),
           "plan_waves": [w.get("name") for w in json.load(open(run / "plan.json")).get("waves", [])] if (run / "plan.json").exists() else [],
           "feeds_placed": sum(1 for v in (waves["waves"][0].get("feeds") or {}).values() if "error" not in v)}
    with RESULTS.open("a") as fh:
        fh.write(json.dumps(row) + "\n")
    return row


def score(board, plan_path, arm, tag=""):
    b = base(board)
    run = SCRATCH / board / f"{arm}-{os.getpid()}-{int(time.time())}"
    run.mkdir(parents=True)
    for f in b.parent.iterdir():
        if f.suffix in (".kicad_pcb", ".kicad_pro", ".kicad_prl"):
            shutil.copy(f, run / f.name)
    pcb = run / b.name
    shutil.copy(plan_path, run / "plan.json")
    rc, out, err = sh([PCB, "route", "waves", pcb, "--plan", run / "plan.json", "--work", run / "work"])
    (run / "waves.txt").write_text(out + err)
    try:
        waves = json.load(open(run / "waves.json"))
    except FileNotFoundError:
        return {"board": board, "arm": arm, "error": (out + err)[-600:]}
    row = {"ts": dt.datetime.now().isoformat(timespec="seconds"), "board": board, "arm": arm, "tag": tag, "run": str(run),
           **judges(board, pcb, waves),
           "plan_waves": [w.get("name") for w in json.load(open(run / "plan.json")).get("waves", [])],
           "feeds_placed": sum(1 for v in (waves["waves"][0].get("feeds") or {}).values() if "error" not in v)}
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS.open("a") as fh:
        fh.write(json.dumps(row) + "\n")
    return row


# ---------------------------------------------------------------------------------------------------- ranking (SIG-4)
import importlib.util
_spec = importlib.util.spec_from_file_location("pcbsig", ROOT / "skills/kicad-design/scripts/pcbsig.py")
pcbsig = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(pcbsig)
WEIGHTS = pcbsig.WEIGHTS
FAST_MAX = 0.0


def latest_rows(path, tag_filter=None):
    rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
    rows = [r for r in rows if "error" not in r and (tag_filter is None or tag_filter in r.get("tag", ""))]
    by = {}
    for r in rows:
        by[r["run"]] = r      # the last row per run wins (a rescore replaces the first scoring)
    return list(by.values())


def rank_old(rows, rules):
    """PLAN-1's rule: pass limits (clean, currents fails and VIN no worse than rules + 10 %), then foreign, off ground, VIN,
    currents, vias."""
    ok = [r for r in rows if r["clean"] and len(r["currents_fails"]) <= len(rules["currents_fails"]) and r["vin_mW"] <= rules["vin_mW"] * 1.1]
    return sorted(ok, key=lambda r: (r["foreign_mm"], r["refplane_mm"], r["vin_mW"], len(r["currents_fails"]), r["vias"]))


def cost(r, w=None):
    return pcbsig.plan_cost(r, w)


def rank_new(rows, rules, w=None, return_via_hard=False, fast_max=None):
    """SIG-4 (pcbsig.plan_rank): hard limits, then the lowest weighted cost."""
    return pcbsig.plan_rank(rows, rules, w, FAST_MAX if fast_max is None else fast_max, return_via_hard)[0]


def rank(path, tag_filter="rescore"):
    rows = [r for r in latest_rows(path, tag_filter) if "fast_off_mm" in r]
    out = {}
    for board in sorted({r["board"] for r in rows}):
        rs = [r for r in rows if r["board"] == board]
        rules = next(r for r in rs if r["arm"] == "rules")
        old = rank_old(rs, rules)
        new = rank_new(rs, rules)
        hard_rv = rank_new(rs, rules, return_via_hard=True)
        # sensitivity: the winner under each weight halved and doubled
        flips = {}
        for k in WEIGHTS:
            for f in (0.5, 2.0):
                w = {**WEIGHTS, k: WEIGHTS[k] * f}
                alt = rank_new(rs, rules, w)
                if alt and new and alt[0]["run"] != new[0]["run"]:
                    flips[f"{k} x{f}"] = f"{alt[0]['arm']} {alt[0].get('tag', '')}"
        out[board] = {"old_winner": old[0] if old else None, "new_winner": new[0] if new else None,
                      "new_passing": len(new), "of": len(rs), "return_via_hard_passing": len(hard_rv), "flips": flips,
                      "ranked_new": [(r["arm"], r.get("tag", ""), round(cost(r), 1), r["mid_off_mm"], r["exposure_mm"], r["vin_mW"], len(r["currents_fails"]), r["return_via_bad"]) for r in new],
                      "failed_hard": [(r["arm"], r.get("tag", ""), "fast_off %.1f" % r["fast_off_mm"], "vin %.0f" % r["vin_mW"], "cur %d" % len(r["currents_fails"]), "clean" if r["clean"] else "NOT CLEAN") for r in rs if r not in new]}
    return out


def rank_report(path):
    out = rank(path)
    print("| board | PLAN-1 winner | SIG-4 winner | cost | plans passing the hard limits | pass with return_via hard | weight flips |")
    print("|---|---|---|---|---|---|---|")
    for board, o in out.items():
        ow, nw = o["old_winner"], o["new_winner"]
        print(f"| {board} | {ow['arm'] + ' ' + ow.get('tag', '') if ow else 'none'} | {nw['arm'] + ' ' + nw.get('tag', '') if nw else 'none'} | "
              f"{round(cost(nw), 1) if nw else ''} | {o['new_passing']} of {o['of']} | {o['return_via_hard_passing']} | {', '.join(f'{k}: {v}' for k, v in o['flips'].items()) or 'none'} |")
    for board, o in out.items():
        print(f"\n{board}: ranked (arm, tag, cost, mid off, exposure, VIN mW, currents fails, return-via bad)")
        for t in o["ranked_new"]:
            print("  ", t)
        if o["failed_hard"]:
            print("  failed a hard limit:")
            for t in o["failed_hard"]:
                print("  ", t)


def table(path):
    rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
    print("| board | arm | tag | clean | VIN mW | VIN J | off ground mm | fast off / gaps | mid off | return-via bad / worst | exposure mm | foreign in SW box mm | currents fails | vias | wall s |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        if "error" in r:
            print(f"| {r['board']} | {r['arm']} | | ERROR | | | | | | | | | | | |"); continue
        sig = (f"{r['fast_off_mm']} / {r['fast_gaps']} | {r['mid_off_mm']} | {r['return_via_bad']} / {r['return_via_worst_mm']} | {r['exposure_mm']}"
               if "fast_off_mm" in r else " | | | ")
        print(f"| {r['board']} | {r['arm']} | {r.get('tag', '')} | {'yes' if r['clean'] else 'no ' + json.dumps(r['new_errors'])} | {r['vin_mW']} | "
              f"{r['vin_J']} | {r['refplane_mm']} | {sig} | {r['foreign_mm']} | {len(r['currents_fails'])} | {r['vias']} | {r['wall_s']} |")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["prep", "rules", "summary", "score", "rescore", "table", "rank"])
    ap.add_argument("--board"); ap.add_argument("--plan"); ap.add_argument("--arm", default="custom"); ap.add_argument("--tag", default="")
    ap.add_argument("--run", help="rescore: an existing run directory under the scratch dir")
    ap.add_argument("--fast-max", type=float, default=0.0, help="rank: mm a bucket-3 net may run off ground (hard limit, default 0)")
    ap.add_argument("--zones", action="store_true"); ap.add_argument("--results", default=str(RESULTS))
    a = ap.parse_args()
    if a.cmd == "prep":
        print(base(a.board))
    elif a.cmd == "rules":
        src, cfg_path, o = board_src(a.board)
        print(json.dumps(kpy("rules", base(a.board), *(["--zones"] if a.zones else []), *(["--config", cfg_path] if o else [])), indent=1))
    elif a.cmd == "summary":
        print(json.dumps(kpy("summary", base(a.board))))
    elif a.cmd == "score":
        print(json.dumps(score(a.board, a.plan, a.arm, a.tag)))
    elif a.cmd == "rescore":
        print(json.dumps(rescore(a.board, a.run, a.tag or "rescore"), indent=1))
    elif a.cmd == "rank":
        global FAST_MAX
        FAST_MAX = a.fast_max
        rank_report(a.results)
    elif a.cmd == "table":
        table(a.results)


if __name__ == "__main__":
    main()
