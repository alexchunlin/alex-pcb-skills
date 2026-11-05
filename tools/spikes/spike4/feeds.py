"""Spike #4 (H3): the archived attempt-2 board's `feeds` rows on the routed H3 boards (the reviewer's R2A2-O-1/O-2 rows).

  python3 -I tools/spikes/spike4/feeds.py            one line per spike4-h3 run and the opus2 rules (mps) waves run
"""
import json, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PCB = str(ROOT / "skills/kicad-design/scripts/pcb")
EX = ROOT / "examples/rung2-zener-a2-opus"


def main():
    rows = [json.loads(l) for l in (ROOT / "tools/bench/results/plan.jsonl").read_text().splitlines() if l.strip()]
    runs = {}
    for r in rows:
        if r.get("tag") == "spike4-h3" or (r.get("tag") == "spike4-h2-waves" and r["board"] == "opus2" and r["arm"] == "mps"):
            runs[r["arm"]] = r["run"]
    for arm, run in runs.items():
        pcb = next(Path(run).glob("*.kicad_pcb"))
        out = Path(run) / "feeds.json"
        subprocess.run([PCB, "check", str(pcb), str(EX / "checks.json"), "--only", "feeds", "--netlist", str(EX / "board/motor1.xml"),
                        "--out", str(out)], capture_output=True, text=True)
        d = json.load(open(out))
        fr = [x for x in d["rows"] if x["check"] == "feeds"]
        print(json.dumps({"arm": arm, "feeds": len(fr), "fail": [x["id"].split(":", 1)[1] for x in fr if x["status"] == "fail"]}))


if __name__ == "__main__":
    main()
