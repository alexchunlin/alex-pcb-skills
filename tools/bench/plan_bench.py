#!/usr/bin/env python3
"""Plan bench: who should write the wave and zone plan for `pcb route waves`, rules or an agent (PLAN-1).

Input per board: the archived rung-2 placement on Alex's stackup (tracks stripped, non-GND pours deleted, In2 one GND
zone), the same feeds and thermal vias for every arm. Only the plan differs. Judges, all deterministic:
  clean / new_errors   `pcb route waves` verdict against the input
  vin_mW, vin_drop     `pcb irdrop` VIN, Q1 source (pins 1-3) to U2.11 2.5 A and U1.4 2.8 A
  vin_J                worst current density outside pads on VIN, A/mm2
  refplane_mm          signal track not over solid ground on the adjacent layer (pcbcheck refplane)
  foreign_mm           track of nets that are not the buck's own inside the switch-node box (plan_kpy intrusion)
  currents_fails       pcbcheck currents rows failing
  vias, length_mm, wall_s

  python3 -I tools/bench/plan_bench.py prep    --board opus|sonnet|opus2
  python3 -I tools/bench/plan_bench.py rules   --board B [--zones] > plan.json
  python3 -I tools/bench/plan_bench.py summary --board B             (what the agent arm reads)
  python3 -I tools/bench/plan_bench.py score   --board B --plan plan.json --arm NAME [--tag T]
  python3 -I tools/bench/plan_bench.py table   [--results F]
Results append to tools/bench/results/plan.jsonl. Scratch /tmp/alexpcb-plan/<board>/.
"""
import argparse, datetime as dt, json, os, shutil, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PCB = str(ROOT / "skills/kicad-design/scripts/pcb")
KPY = str(ROOT / "tools/bench/plan_kpy.py")
RESULTS = ROOT / "tools/bench/results/plan.jsonl"
SCRATCH = Path("/tmp/alexpcb-plan")
BOARDS = {"opus": "examples/rung2-zener-a1-opus", "sonnet": "examples/rung2-zener-a1-sonnet", "opus2": "examples/rung2-zener-a2-opus"}


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
    src = ROOT / BOARDS[board] / "board"
    for f in src.iterdir():
        if f.suffix in (".kicad_pcb", ".kicad_pro", ".kicad_prl"):
            shutil.copy(f, d / f.name)
    pcb = next(d.glob("*.kicad_pcb"))
    sh([PCB, "route", "strip", pcb])
    kpy("prep", pcb)
    return pcb


def judges(board, routed, waves):
    src = ROOT / BOARDS[board]
    cfg = json.load(open(src / "checks.json"))
    cfg["refplane"] = {"ground": "GND"}
    cpath = routed.parent / "judge_checks.json"
    json.dump(cfg, open(cpath, "w"))
    xml = next((src / "board").glob("*.xml"))
    sh([PCB, "check", routed, cpath, "--only", "currents,refplane", "--netlist", xml, "--out", routed.parent / "judge.json"])
    j = json.load(open(routed.parent / "judge.json"))
    rp = [r for r in j["rows"] if r["check"] == "refplane"]
    cur = [r["id"].split(":", 1)[1] for r in j["rows"] if r["check"] == "currents" and r["status"] == "fail"]
    rc, out, err = sh([PCB, "irdrop", routed, "--net", "VIN", "--source", "Q1.1,Q1.2,Q1.3", "--sink", "U2.11=2.5", "--sink", "U1.4=2.8",
                       "--out", routed.parent / "irdrop", "--json"])
    ir = last_json(out) if rc == 0 else {}
    intr = kpy("intrusion", routed)
    m = last_json(sh([PCB, "route", "measure", routed, "--json"])[1])
    return {"clean": waves.get("clean"), "new_errors": waves.get("new_errors"), "airwires": m["ratsnest"]["airwires"],
            "vin_mW": ir.get("power_mW"), "vin_drop_mV": [s["drop_mV"] for s in ir.get("sinks", [])], "vin_J": ir.get("max_J_A_mm2"),
            "refplane_mm": round(sum(r["value"] or 0 for r in rp), 1), "foreign_mm": intr["foreign_mm"], "foreign_by_net": intr["by_net"],
            "currents_fails": cur, "vias": m["vias"], "length_mm": m["length_mm"], "wall_s": waves.get("wall_s")}


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


def table(path):
    rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
    print("| board | arm | tag | clean | VIN mW | VIN J | off ground mm | foreign in SW box mm | currents fails | vias | wall s |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        if "error" in r:
            print(f"| {r['board']} | {r['arm']} | | ERROR | | | | | | | |"); continue
        print(f"| {r['board']} | {r['arm']} | {r.get('tag', '')} | {'yes' if r['clean'] else 'no ' + json.dumps(r['new_errors'])} | {r['vin_mW']} | "
              f"{r['vin_J']} | {r['refplane_mm']} | {r['foreign_mm']} | {len(r['currents_fails'])} | {r['vias']} | {r['wall_s']} |")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["prep", "rules", "summary", "score", "table"])
    ap.add_argument("--board"); ap.add_argument("--plan"); ap.add_argument("--arm", default="custom"); ap.add_argument("--tag", default="")
    ap.add_argument("--zones", action="store_true"); ap.add_argument("--results", default=str(RESULTS))
    a = ap.parse_args()
    if a.cmd == "prep":
        print(base(a.board))
    elif a.cmd == "rules":
        print(json.dumps(kpy("rules", base(a.board), *(["--zones"] if a.zones else [])), indent=1))
    elif a.cmd == "summary":
        print(json.dumps(kpy("summary", base(a.board))))
    elif a.cmd == "score":
        print(json.dumps(score(a.board, a.plan, a.arm, a.tag)))
    elif a.cmd == "table":
        table(a.results)


if __name__ == "__main__":
    main()
