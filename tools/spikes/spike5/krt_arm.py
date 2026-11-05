#!/usr/bin/env python3
"""Spike 5: KRT's place_simple moving only the satellites, the rest of the board locked (the prior-art arms).

  python3 -I tools/spikes/spike5/krt_arm.py prep  --board r1 [--moved C1,C2,C3]
  python3 -I tools/spikes/spike5/krt_arm.py place --board r1 --seed 0 [--intent I.json] [-- extra place_simple flags]

prep: strip the archived board (zones kept), lock every footprint but the moved satellites with KRT's own `place_pose.py
lock`, emit the intent (`check_floorplan --emit-intent --no-declare-decaps` unless --decaps-from is asked: the archived
board's distances are the designer's answer, so the arm must not read them), one group {IC + satellites} anchored on the IC.
place: one `place_simple` run for one seed, with the group file and the intent (for the templates arm, a per-seed intent
carrying one templates[] row). Nothing else moves: KRT's own lock keeps it, and the harness checks it after the run.
"""
from __future__ import annotations

import argparse, json, os, re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PCB = str(ROOT / "skills/kicad-design/scripts/pcb")
KRT_DIR = os.environ.get("KRT_DIR", "/tmp/pcb-ref/KiCadRoutingTools")
KRT_PY = os.environ.get("KRT_PY", os.path.join(KRT_DIR, ".venv/bin/python"))
WORK = Path(os.environ.get("SPIKE5_WORK", "/tmp/spike5/route"))

BOARDS = {
    "r1": {"src": ROOT / "examples/rung1-zener-a2-sonnet/board/qwiic_imu", "ic": "U1", "part": "LSM6DS3", "moved": ["C1", "C2", "C3"], "anchor": (112.7, 112.7, 0),
           "checks": ROOT / "examples/rung1-zener-a2-sonnet/checks.json"},
    "r2": {"src": ROOT / "examples/rung2-zener-a2-opus/board/motor1", "ic": "U2", "part": "DRV8874", "moved": ["C10", "C11", "R10"], "anchor": (119.0, 112.0, 270),
           "checks": ROOT / "examples/rung2-zener-a2-opus/checks.json"},
}


def sh(cmd, cwd=None, timeout=None):
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, cwd=cwd, timeout=timeout,
                       env={**os.environ, "PYTHONHASHSEED": "0"})
    return p.returncode, p.stdout, p.stderr


def krt(script, *args, timeout=None):
    return sh([KRT_PY, "-X", "utf8", Path(KRT_DIR) / script, *args], cwd=KRT_DIR, timeout=timeout)


def refs_of(pcb):
    t = open(pcb).read()
    return sorted(set(re.findall(r'\(property\s+"Reference"\s+"([^"]+)"', t)))


def base_dir(board):
    return WORK / board / "base"


def prep(board, moved=None, decaps_from=False):
    b = BOARDS[board]
    moved = moved or b["moved"]
    d = base_dir(board)
    d.mkdir(parents=True, exist_ok=True)
    src = b["src"]
    stem = src.name
    shutil.copy(src.with_suffix(".kicad_pcb"), d / "src.kicad_pcb")
    shutil.copy(src.with_suffix(".kicad_pro"), d / "src.kicad_pro")
    rc, out, err = sh([PCB, "route", "strip", d / "src.kicad_pcb", "--out", d / "in.kicad_pcb"])
    assert rc == 0, (out + err)[-400:]
    shutil.copy(src.with_suffix(".kicad_pro"), d / "in.kicad_pro")
    keep = [r for r in refs_of(d / "in.kicad_pcb") if r not in moved]
    rc, out, err = krt("py_placer/place_pose.py", d / "in.kicad_pcb", d / "fixed.kicad_pcb", "lock", *keep)
    assert rc == 0, (out + err)[-600:]
    shutil.copy(src.with_suffix(".kicad_pro"), d / "fixed.kicad_pro")
    arg = ["--decaps-from", d / "src.kicad_pcb"] if decaps_from else ["--no-declare-decaps"]
    rc, out, err = krt("py_tools/check_floorplan.py", d / "fixed.kicad_pcb", "--emit-intent", d / "intent.json", *arg)
    (d / "intent.log").write_text(out + err)
    groups = {"schema": 1, "groups": [{"name": "sat", "role": "core", "refs": [b["ic"], *moved], "anchor": b["ic"],
                                        "why": "the satellites of one IC, as the other arms move them"}]}
    json.dump(groups, open(d / "groups.json", "w"), indent=1)
    rc2, out, err = krt("py_tools/check_groups.py", d / "fixed.kicad_pcb", "--groups", d / "groups.json", "--intent", d / "intent.json")
    (d / "check_groups.txt").write_text(out + err)
    json.dump({"board": board, "stem": stem, "moved": moved, "locked": keep, "intent_rc": rc, "check_groups_rc": rc2}, open(d / "prep.json", "w"), indent=1)
    print(f"prep {board}: moved {moved}; locked {len(keep)}; intent rc {rc}; check_groups rc {rc2}; {d}")


def place(board, seed, out_dir, intent=None, extra=()):
    d = base_dir(board)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "seed.kicad_pcb"
    js = out_dir / "place.json"
    rc, o, e = krt("py_placer/place_simple.py", d / "fixed.kicad_pcb", out, "--groups", d / "groups.json", "--intent", intent or d / "intent.json",
                   "--seed", seed, "--json", js, *extra, timeout=600)
    (out_dir / "place.log").write_text(o + e)
    rep = json.load(open(js)) if js.exists() else {}
    return rc, rep, out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["prep", "place"])
    ap.add_argument("--board", required=True, choices=sorted(BOARDS))
    ap.add_argument("--moved")
    ap.add_argument("--decaps-from", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="/tmp/spike5/dry/place")
    ap.add_argument("--intent")
    ap.add_argument("extra", nargs="*")
    a = ap.parse_args()
    if a.cmd == "prep":
        prep(a.board, a.moved.split(",") if a.moved else None, a.decaps_from)
    else:
        rc, rep, out = place(a.board, a.seed, a.out, a.intent, a.extra)
        print("rc", rc, {k: (v if not isinstance(v, (dict, list)) or len(str(v)) < 300 else "...") for k, v in rep.items()})


if __name__ == "__main__":
    main()
