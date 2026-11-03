#!/usr/bin/env python3
"""Spike #3, C8: plant the six bug kinds of GAMEPLAN section 4 into copies of two archived boards and measure what
fraction each board's own checks.json catches through `pcb check` (the guardrail coverage).

  python3 -I tools/spikes/spike3/mutation_bench.py [--jobs 3]   -> tools/spikes/spike3/results/mutation.json

Each mutant is mutate.py on a copy (board and netlist both carry the bug, as a regenerated design would) and one
`pcb check` with the archived checks.json. Caught = a fail row that the unmutated copy (same load and save) does not
have, or a row that went from pass to fail; a new warn alone is reported as `warn`. A kind the board has no circuit for
(no diode on the rung-1 board, no net above 0.1 A) is n/a, not a miss. The instances are picked by hand (the parts a
reviewer would name); several per kind and board where the board has them.
"""
import json, shutil, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PCB = str(ROOT / "skills/kicad-design/scripts/pcb")
MUT = str(Path(__file__).resolve().parent / "mutate.py")
OUT = Path("/tmp/spike3/mut")
RES = Path(__file__).resolve().parent / "results" / "mutation.json"
# the check families whose job a kind is; a catch only by another family is `incidental` (a calc that names the deleted
# part) or an artefact of the mutation (copper left on the old net: the mutant swaps pad nets without re-routing)
ON_TOPIC = {"swapped I2C pins": {"pinmaps", "connectors", "pullups", "addresses"}, "missing pull-up": {"pullups"},
            "reversed diode": {"pinmaps", "connectors"}, "0.2 mm trace on a 3 A net": {"currents", "feeds", "irdrop", "margin", "policy"},
            "decoupling cap 15 mm from its pin": {"decoupling"}, "connector pin map off by one": {"connectors", "pinmaps"}}
KINDS = ["swapped I2C pins", "missing pull-up", "reversed diode", "0.2 mm trace on a 3 A net",
         "decoupling cap 15 mm from its pin", "connector pin map off by one"]
BOARDS = {
    "rung1-zener-a2-sonnet": {"stem": "qwiic_imu", "mutants": [
        ("swapped I2C pins", "U1 SDA/SCL (pins 14/13)", {"op": "swap_pins", "ref": "U1", "a": "13", "b": "14"}),
        ("swapped I2C pins", "J1 SDA/SCL (pins 3/4)", {"op": "swap_pins", "ref": "J1", "a": "3", "b": "4"}),
        ("missing pull-up", "R1 (SDA)", {"op": "delete", "ref": "R1"}),
        ("missing pull-up", "R2 (SCL)", {"op": "delete", "ref": "R2"}),
        ("reversed diode", "n/a: no diode on the board", None),
        ("0.2 mm trace on a 3 A net", "n/a: no net above 0.1 A", None),
        ("decoupling cap 15 mm from its pin", "C1 from U1.8", {"op": "move_away", "ref": "C1", "from": "U1.8", "mm": 15}),
        ("decoupling cap 15 mm from its pin", "C2 from U1.5", {"op": "move_away", "ref": "C2", "from": "U1.5", "mm": 15}),
        ("connector pin map off by one", "J1 pins 1-4", {"op": "rotate_pins", "ref": "J1", "pins": ["1", "2", "3", "4"]}),
        ("connector pin map off by one", "J2 pins 1-4", {"op": "rotate_pins", "ref": "J2", "pins": ["1", "2", "3", "4"]}),
    ]},
    "rung2-zener-a2-opus": {"stem": "motor1", "mutants": [
        ("swapped I2C pins", "no I2C: U2 PWM/DIR (pins 1/2) instead", {"op": "swap_pins", "ref": "U2", "a": "1", "b": "2"}),
        ("swapped I2C pins", "no I2C: J2 ENC_A/ENC_B (pins 2/3) instead", {"op": "swap_pins", "ref": "J2", "a": "2", "b": "3"}),
        ("missing pull-up", "R12 (nFAULT, open drain)", {"op": "delete", "ref": "R12"}),
        ("missing pull-up", "R5 (ENC_A)", {"op": "delete", "ref": "R5"}),
        ("reversed diode", "D4 SMAJ18A TVS on VIN", {"op": "swap_pins", "ref": "D4", "a": "1", "b": "2"}),
        ("reversed diode", "D3 BZT52C12 Q1 gate clamp", {"op": "swap_pins", "ref": "D3", "a": "1", "b": "2"}),
        ("0.2 mm trace on a 3 A net", "5V (1.4 mm -> 0.2)", {"op": "track_width", "net": "5V", "width_mm": 0.2}),
        ("0.2 mm trace on a 3 A net", "VIN (1.4 mm -> 0.2)", {"op": "track_width", "net": "VIN", "width_mm": 0.2}),
        ("0.2 mm trace on a 3 A net", "MOTOR_A (0.8 mm -> 0.2)", {"op": "track_width", "net": "MOTOR_A", "width_mm": 0.2}),
        ("decoupling cap 15 mm from its pin", "C10 from U2.11 (VM)", {"op": "move_away", "ref": "C10", "from": "U2.11", "mm": 15}),
        ("decoupling cap 15 mm from its pin", "C1 from U1.6 (PVIN)", {"op": "move_away", "ref": "C1", "from": "U1.6", "mm": 15}),
        ("connector pin map off by one", "J3 pins 1-10", {"op": "rotate_pins", "ref": "J3", "pins": [str(i) for i in range(1, 11)]}),
        ("connector pin map off by one", "J2 pins 2-5", {"op": "rotate_pins", "ref": "J2", "pins": ["2", "3", "4", "5"]}),
    ]},
}


def make_and_check(board, i, kind, where, op):
    src = ROOT / "examples" / board / "board"
    stem = BOARDS[board]["stem"]
    w = OUT / board / (f"m{i:02d}" if op else "base")
    if w.exists():
        shutil.rmtree(w)
    w.mkdir(parents=True)
    shutil.copy(src / f"{stem}.kicad_pro", w / f"{stem}.kicad_pro")
    p = subprocess.run([PCB, "py", MUT, str(src / f"{stem}.kicad_pcb"), str(src / f"{stem}.xml"), str(w), json.dumps(op or {"op": "none"})],
                       capture_output=True, text=True)
    did = json.loads(p.stdout.strip().splitlines()[-1]) if p.returncode == 0 else {"error": (p.stdout + p.stderr)[-300:]}
    rep = w / "pcbcheck.json"
    subprocess.run([PCB, "check", str(w / f"{stem}.kicad_pcb"), str(ROOT / "examples" / board / "checks.json"),
                    "--netlist", str(w / f"{stem}.xml"), "--bringup", str(src / "BRINGUP.md"), "--out", str(rep)], capture_output=True, text=True)
    rows = json.load(open(rep))["rows"] if rep.exists() else []
    return {"board": board, "kind": kind, "where": where, "op": op, "did": did, "rows": {r["id"]: (r["status"], r["msg"][:200]) for r in rows}}


def main(argv):
    jobs = int(argv[argv.index("--jobs") + 1]) if "--jobs" in argv else 3
    tasks = [(b, -1, "baseline", "", None) for b in BOARDS]
    tasks += [(b, i, k, wh, op) for b, d in BOARDS.items() for i, (k, wh, op) in enumerate(d["mutants"]) if op]
    with ThreadPoolExecutor(jobs) as ex:
        res = list(ex.map(lambda t: make_and_check(*t), tasks))
    base = {r["board"]: r["rows"] for r in res if r["kind"] == "baseline"}
    out = []
    for b, d in BOARDS.items():
        for i, (k, wh, op) in enumerate(d["mutants"]):
            if not op:
                out.append({"board": b, "kind": k, "where": wh, "verdict": "n/a"}); continue
            r = next(x for x in res if x["board"] == b and x["where"] == wh)
            bs = base[b]
            new_fail = [(rid, m) for rid, (st, m) in r["rows"].items() if st == "fail" and bs.get(rid, ("absent",))[0] != "fail"]
            new_warn = [(rid, m) for rid, (st, m) in r["rows"].items() if st == "warn" and bs.get(rid, ("absent",))[0] not in ("warn", "fail")]
            verdict = "caught" if new_fail else ("warn" if new_warn else "missed")
            on = [rid for rid, _ in new_fail if rid.split(":")[0] in ON_TOPIC[k]]
            out.append({"board": b, "kind": k, "where": wh, "did": r["did"], "verdict": verdict, "on_topic": bool(on),
                        "new_fails": new_fail[:6], "new_warns": new_warn[:4], "n_rows": len(r["rows"])})
    summ = {}
    for k in KINDS:
        xs = [o for o in out if o["kind"] == k and o["verdict"] != "n/a"]
        summ[k] = {"instances": len(xs), "caught": sum(o["verdict"] == "caught" for o in xs), "warn": sum(o["verdict"] == "warn" for o in xs),
                   "caught_on_topic": sum(o["verdict"] == "caught" and o["on_topic"] for o in xs),
                   "n/a": sum(1 for o in out if o["kind"] == k and o["verdict"] == "n/a"),
                   "by_board": {b: [o["verdict"] for o in xs if o["board"] == b] for b in BOARDS}}
    tot = [o for o in out if o["verdict"] != "n/a"]
    RES.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"summary": summ, "total": {"instances": len(tot), "caught": sum(o["verdict"] == "caught" for o in tot),
                                          "caught_on_topic": sum(o["verdict"] == "caught" and o["on_topic"] for o in tot)},
               "baseline_fails": {b: sorted(rid for rid, (st, _) in v.items() if st == "fail") for b, v in base.items()},
               "mutants": out}, open(RES, "w"), indent=1)
    for o in out:
        print(f"{o['board'][:20]:20} {o['kind'][:34]:34} {o['where'][:40]:40} {o['verdict']:7} {'' if o.get('on_topic', True) else '(off-topic) '}" +
              "; ".join(rid for rid, _ in o.get("new_fails", [])[:3]))
    for k, s in summ.items():
        print(f"{k:34} {s['caught']}/{s['instances']} caught, {s['caught_on_topic']} by the row meant for it ({s['warn']} warn only, {s['n/a']} n/a)")
    print("total", sum(o["verdict"] == "caught" for o in tot), "/", len(tot), "caught,",
          sum(o["verdict"] == "caught" and o["on_topic"] for o in tot), "by the row meant for it ->", RES)


if __name__ == "__main__":
    main(sys.argv[1:])
