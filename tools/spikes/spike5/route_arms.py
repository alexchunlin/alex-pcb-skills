#!/usr/bin/env python3
"""Spike 5 routing arms: one seeded placement per (board, arm, seed), routed by `pcb route auto`, one JSONL row per seed.

  python3 -I tools/spikes/spike5/route_arms.py run --board r1 --arms krt --n 50 [--jobs 3]
  python3 -I tools/spikes/spike5/route_arms.py run --board r1 --arms uniform,part --seeds 0,11,22,33,44 --tag repro
  python3 -I tools/spikes/spike5/route_arms.py designer --board r1

Resumable: a (tag, board, arm, seed) already in the results file is skipped, so a killed run carries on. Arms:
uniform and part (spike 2's seed_place modes, part reads spike 2's priors file), perturb (--sigma), class_part, class_pkg and
class (seed_place --mode class on pools from pool.py), krt (place_simple, the satellites free, everything else locked by
KRT's place_pose lock), krt_tpl (the same, with a per-seed intent carrying one templates[] row drawn from the class pool).
Every seed of every arm passes the same gate (seed_place: courtyard boxes, outline), and a seed that fails it, or that KRT
leaves illegal, is rejected: a row with seed_ok false, no replacement, not clean. See docs/spikes/spike-5-class-priors.md.
Downloaded boards never come near this: the inputs are the archived examples, copied under /tmp/spike5/route/.
"""
from __future__ import annotations

import argparse, concurrent.futures as cf, json, os, re, shutil, sys, threading, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import krt_arm as K  # noqa: E402

ROOT = K.ROOT
PCB = K.PCB
RESULTS = HERE / "route-results.jsonl"
SEED_PLACE = ROOT / "tools/spikes/spike2/seed_place.py"
PART_PRIORS = "/tmp/spike2-corpus/priors-LSM6DS3.json"
POOLS = Path("/tmp/spike5/pools")
LOCK = threading.Lock()


def last_json(text):
    for l in reversed(text.splitlines()):
        if l.startswith("{"):
            return json.loads(l)
    return {}


def seed_place(board, src, out, mode, seed, moved, *extra):
    b = K.BOARDS[board]
    rc, o, e = K.sh([PCB, "py", SEED_PLACE, src, out, "--ic", b["ic"], "--part", b["part"], "--move", ",".join(moved),
                     "--mode", mode, "--seed", seed, *extra], cwd=ROOT)
    return last_json(o) or {"ok": False, "why": (o + e)[-300:]}


def turn(x, y, q):
    """KRT's simple._turn for a quarter-turn multiple q (read back in krt_tpl's check: the member lands on the drawn pose)."""
    k = int(round(q / 90.0)) % 4
    for _ in range(k):
        x, y = y, -x
    return x, y


def anchor_pose(board):
    return K.BOARDS[board]["anchor"]


def template_intent(board, drawn, path):
    """One templates[] row: the drawn world poses in the chip's frame (KRT carries them with follow(), so invert it)."""
    b = K.BOARDS[board]
    ax, ay, ar = anchor_pose(board)
    members = []
    for ref, (x, y, rot) in drawn.items():
        tx, ty = turn(x - ax, y - ay, (360 - ar) % 360)
        members.append({"ref": ref, "at": [round(tx, 3), round(ty, 3)], "rot": (rot - ar) % 360})
    it = json.load(open(K.base_dir(board) / "intent.json"))
    it["templates"] = [{"anchor": b["ic"], "members": members, "source": "spike 5 class prior draw", "tolerance_mm": 1.0}]
    json.dump(it, open(path, "w"), indent=1)


def seed_board(board, arm, seed, d, moved, a):
    """(seed info, seeded board path or None)."""
    base = K.base_dir(board)
    src = base / "in.kicad_pcb"
    out = d / "seed.kicad_pcb"
    if arm in ("uniform", "part", "perturb") or arm.startswith("class"):
        extra = {"uniform": [], "part": ["--priors", PART_PRIORS], "perturb": ["--sigma", str(a.sigma)]}.get(arm)
        if extra is None:
            extra = ["--pool", POOLS / f"{board}-{arm}.json"]
        mode = {"part": "prior", "uniform": "uniform", "perturb": "perturb"}.get(arm, "class")
        sd = seed_place(board, src, out, mode, seed, moved, *extra, *(["--keep-stuck"] if a.keep_stuck else []))
        return sd, out if sd.get("ok") else None
    extra, intent = [], None
    if arm == "krt_tpl":
        pool_arm = {"r1": "class_part", "r2": "class"}[board]
        sd = seed_place(board, src, out, "class", seed, moved, "--pool", POOLS / f"{board}-{pool_arm}.json", "--dry", *(["--nogate"] if a.nogate else []))
        if not sd.get("ok"):
            return sd, None
        intent = d / "intent.json"
        template_intent(board, sd["moved"], intent)
        extra = ["--template-weight", str(a.template_weight)]
    rc, rep, placed = K.place(board, seed, d, intent, extra)
    info = {"krt_rc": rc, "illegal": rep.get("illegal"), "refused": rep.get("refused"), "fp_errors": (rep.get("floorplan") or {}).get("errors"),
            "templates": rep.get("templates")}
    if rc not in (0,) or rep.get("illegal") or not placed.exists():
        return {"ok": False, "why": f"place_simple rc {rc} illegal {rep.get('illegal')}", **info}, None
    g = seed_place(board, placed, out, "gate", seed, moved)
    if arm == "krt_tpl":
        info["drawn"] = sd["moved"]
    return {**g, "draws": 1, "why": None if g.get("ok") else f"gate {g.get('bad')}", **info}, placed if g.get("ok") else None


def route_one(board, arm, seed, d, seeded, rec):
    pr = json.load(open(K.base_dir(board) / "prep.json"))
    stem = pr["stem"]
    wk = d / "r"
    wk.mkdir(exist_ok=True)
    pcb = wk / f"{stem}.kicad_pcb"
    shutil.copy(seeded, pcb)
    shutil.copy(K.base_dir(board) / "in.kicad_pro", wk / f"{stem}.kicad_pro")
    t0 = time.time()
    rc, o, e = K.sh([PCB, "route", "auto", pcb, "--out", wk / "auto.kicad_pcb", "--work", wk / "w"], cwd=ROOT)
    try:
        rj = json.load(open(wk / "route.json"))
        f = rj["final"]
        rec["auto"] = {"clean": rj["clean"], "vias": f["vias"], "airwires": f["airwires"], "length_mm": f["length_mm"], "plain_errors": f["plain_errors"],
                       "packed_errors": f["packed_errors"], "new_errors": f.get("new_errors"), "wall_s": rj["wall_s"], "passes": len(rj.get("passes", []))}
    except (OSError, ValueError, KeyError):
        rec["auto"] = {"clean": False, "error": (o + e)[-300:]}
        return rec
    m = wk / "auto.kicad_pcb"
    if m.exists():
        rc, o, e = K.sh([PCB, "route", "measure", m, "--json"], cwd=ROOT)
        try:
            jm = last_json(o) or json.loads(o[o.index("{"):])
            rec["auto"]["signal_vias"] = jm.get("signal_vias")
        except ValueError:
            rec["auto"]["signal_vias"] = None
        b = K.BOARDS[board]
        out = wk / "rows.json"
        K.sh([PCB, "check", m, b["checks"], "--only", "feeds,decoupling", "--netlist", b["src"].with_suffix(".xml"), "--out", out], cwd=ROOT)
        if out.exists():
            rows = json.load(open(out))["rows"]
            for fam in ("feeds", "decoupling"):
                fr = [x for x in rows if x["check"] == fam]
                rec[fam] = {"n": len(fr), "fail": [x["id"].split(":", 1)[1] for x in fr if x["status"] == "fail"]}
    return rec


def one(board, arm, seed, a, moved):
    d = K.WORK / board / a.tag / f"{arm}-{seed:02d}"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    t0 = time.time()
    sd, seeded = seed_board(board, arm, seed, d, moved, a)
    rec = {"tag": a.tag, "board": board, "arm": arm, "seed": seed, "seed_ok": bool(sd.get("ok") and seeded), "why": sd.get("why"), "draws": sd.get("draws"),
           "moved": sd.get("moved"), "levels": sd.get("levels"), **{k: sd[k] for k in ("krt_rc", "illegal", "refused", "fp_errors", "drawn") if k in sd}}
    if rec["seed_ok"]:
        route_one(board, arm, seed, d, seeded, rec)
    rec["wall_s"] = round(time.time() - t0, 1)
    with LOCK:
        with open(a.results, "a") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")
    if not a.keep:
        shutil.rmtree(d, ignore_errors=True)   # keep only the row: (board, arm, seed) rebuilds the seed, and `moved` holds its poses
    au = rec.get("auto", {})
    print(f"{board} {arm:10} {seed:2} seed {rec['seed_ok']} clean {au.get('clean')} vias {au.get('vias')} sig {au.get('signal_vias')} air {au.get('airwires')} {rec['wall_s']} s", flush=True)
    return rec


def done_keys(path):
    out = set()
    if Path(path).exists():
        for l in open(path):
            x = json.loads(l)
            out.add((x["tag"], x["board"], x["arm"], x["seed"]))
    return out


def cmd_run(a):
    pr = json.load(open(K.base_dir(a.board) / "prep.json"))
    seeds = [int(x) for x in a.seeds.split(",")] if a.seeds else list(range(a.n))
    done = done_keys(a.results)
    todo = [(arm, s) for s in seeds for arm in a.arms.split(",") if (a.tag, a.board, arm, s) not in done]
    print(f"{a.board}: {len(todo)} to route, moved {pr['moved']}", flush=True)
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        for fu in cf.as_completed([ex.submit(one, a.board, arm, s, a, a.order.split(",") if a.order else pr["moved"]) for arm, s in todo]):
            fu.result()


def cmd_designer(a):
    d = K.WORK / a.board / "designer"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    rec = {"tag": a.tag, "board": a.board, "arm": "designer", "seed": 0, "seed_ok": True}
    route_one(a.board, "designer", 0, d, K.base_dir(a.board) / "in.kicad_pcb", rec)
    with open(a.results, "a") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")
    print(json.dumps(rec.get("auto")), rec.get("feeds"), rec.get("decoupling"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["run", "designer"])
    ap.add_argument("--board", required=True, choices=sorted(K.BOARDS))
    ap.add_argument("--arms", default="")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seeds")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--tag", default="h1")
    ap.add_argument("--sigma", type=float, default=1.0)
    ap.add_argument("--template-weight", type=float, default=100.0)
    ap.add_argument("--results", default=str(RESULTS))
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--order", help="the draw order of the moved parts, tightest role first (a sensitivity run, its own --tag)")
    ap.add_argument("--keep-stuck", action="store_true", help="class: a part with no legal draw keeps the designer's pose (a sensitivity run, its own --tag)")
    ap.add_argument("--nogate", action="store_true", help="krt_tpl: template rows from the first draw, not gated (a sensitivity run, its own --tag)")
    a = ap.parse_args()
    {"run": cmd_run, "designer": cmd_designer}[a.cmd](a)


if __name__ == "__main__":
    main()
