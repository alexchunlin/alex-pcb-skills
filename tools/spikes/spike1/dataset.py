#!/usr/bin/env python3
"""Spike #1: board geometry and the feature columns of the placement rows.

  .venv/bin/python3 -I tools/spikes/spike1/dataset.py static   [--boards opus,sonnet,fable,opus2,r1sonnet]
  .venv/bin/python3 -I tools/spikes/spike1/dataset.py annotate [--check]
  .venv/bin/python3 -I tools/spikes/spike1/dataset.py summary

static: board_kpy.py (KiCad's Python) on each board's generator base (/tmp/spike1/gen/<board>/base, the route bench's
stripped copy with pours kept) into /tmp/spike1/static/<board>.json. annotate: every row of the spike-1 tags in
tools/bench/results/placements.jsonl without a `feat` gets one (features.py with the board's declared decoupling rows
and the row's own MPS conflict counts); existing values are never changed, and the file is rewritten whole (run it with
no generator writing). --check recomputes the stored ones and exits 1 on a difference. summary: rows, clean rate,
signal vias per board and sigma.
"""
import argparse, json, os, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import features as F  # noqa: E402
import surrogate as S  # noqa: E402

ROOT = HERE.parents[2]
PCB = str(ROOT / "skills/kicad-design/scripts/pcb")
STATIC = Path("/tmp/spike1/static")
GEN = Path("/tmp/spike1/gen")
EXAMPLES = {"opus": "rung2-zener-a1-opus", "sonnet": "rung2-zener-a1-sonnet", "fable": "rung2-zener-a1-fable",
            "opus2": "rung2-zener-a2-opus", "r1sonnet": "rung1-zener-a2-sonnet"}


def decoupling(board):
    return json.load(open(ROOT / "examples" / EXAMPLES[board] / "checks.json")).get("decoupling", [])


def static(board):
    p = STATIC / f"{board}.json"
    if not p.exists():
        src = next((GEN / board / "base").glob("*/tracks/input/*.kicad_pcb"))
        STATIC.mkdir(parents=True, exist_ok=True)
        subprocess.run([PCB, "py", str(HERE / "board_kpy.py"), str(src), str(p)], check=True, capture_output=True)
    return json.load(open(p))


def feat_of(row, st, dec):
    return F.features(st, row["placement"], dec, (row["conflicts"], row["signal_conflicts"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["static", "annotate", "summary"])
    ap.add_argument("--boards", default="opus,sonnet,fable,opus2,r1sonnet")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.cmd == "static":
        for b in a.boards.split(","):
            st = static(b)
            print(b, len(st["footprints"]), "footprints", sum(len(f["pads"]) for f in st["footprints"]), "pads", st["plane_nets"])
        return
    lines = S.DATA.read_text().splitlines()
    if a.cmd == "summary":
        import numpy as np
        rows = S.load()
        for b in sorted({r["board"] for r in rows}):
            rs = [r for r in rows if r["board"] == b]
            print(f"{b}: {len(rs)} rows, clean {sum(bool(r.get('clean')) for r in rs)} "
                  f"({100 * np.mean([bool(r.get('clean')) for r in rs]):.0f} %), signal vias median {np.median([r['signal_vias'] for r in rs])}, "
                  f"feat {sum('feat' in r for r in rs)}")
            for s in sorted({r["sigma"] for r in rs}):
                ss = [r for r in rs if r["sigma"] == s]
                print(f"   sigma {s}: {len(ss)} rows, clean {sum(bool(r.get('clean')) for r in ss)}, "
                      f"clean with signal vias {sorted(r['signal_vias'] for r in ss if r.get('clean'))}")
        return
    if not a.check and subprocess.run(["pgrep", "-f", "spike4/perturb.py"], capture_output=True).returncode == 0:
        sys.exit("annotate: a generator is writing placements.jsonl (its open handle would keep the old file); run it after")
    cache, out, added, bad = {}, [], 0, 0
    for line in lines:
        if not line.strip():
            out.append(line); continue
        r = json.loads(line)
        if r.get("tag", "").startswith("spike") and r.get("config") == "outer" and "placement" in r and r["board"] in EXAMPLES \
                and "error" not in r and r.get("tag") != "spike4-h1q":
            if r["board"] not in cache:
                cache[r["board"]] = (static(r["board"]), decoupling(r["board"]))
            st, dec = cache[r["board"]]
            if "feat" not in r:
                r["feat"] = feat_of(r, st, dec)
                added += 1
                line = json.dumps(r)
            elif a.check and json.dumps(feat_of(r, st, dec), sort_keys=True) != json.dumps(r["feat"], sort_keys=True):
                bad += 1
                print("differs:", r["board"], r["k"], r.get("tag"))
        out.append(line)
    if a.check:
        print(f"annotate --check: {bad} rows differ")
        sys.exit(1 if bad else 0)
    tmp = S.DATA.with_suffix(".jsonl.tmp")
    tmp.write_text("\n".join(out) + "\n")
    os.replace(tmp, S.DATA)
    print(f"annotate: {added} rows given features")


if __name__ == "__main__":
    main()
