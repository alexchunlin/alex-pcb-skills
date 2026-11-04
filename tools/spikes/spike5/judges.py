#!/usr/bin/env python3
"""Spike 5: the waves label on r2. Each arm's best 5 clean placements (fewest signal vias, then shortest) plus the designer's start, on
Alex's stackup through `pcb route waves` with the rules plan, scored by plan_bench.judges and the `feeds` and `decoupling` rows.

  python3 -I tools/spikes/spike5/judges.py run [--jobs 3]     # resumable, one row per placement in judges.jsonl
  python3 -I tools/spikes/spike5/judges.py table              # per arm: medians, and how many beat the start

The same steps as spike 1's search.judge (tools/spikes/spike1/search.py), which reads an unrelated model stack on import.
"""
import argparse, concurrent.futures as cf, datetime as dt, importlib.util, json, shutil, statistics as st, sys, threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import krt_arm as K  # noqa: E402

ROOT = K.ROOT
PCB = K.PCB
OUT = HERE / "judges.jsonl"
W = Path("/tmp/spike5/plan")
LOCK = threading.Lock()
ARMS = ["uniform", "krt", "class", "krt_tpl", "perturb", "class_rerun"]


def mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


pb = mod("plan_bench", ROOT / "tools/bench/plan_bench.py")


def placement_of(moved):
    rc, o, e = K.sh([PCB, "q", K.BOARDS["r2"]["src"].with_suffix(".kicad_pcb"), "fps", "--json"], cwd=ROOT)
    fp = json.loads(o[o.index("{"):])["footprints"]
    pl = [[f["ref"], f["pos"][0], f["pos"][1], f["rot"]] for f in fp]
    return [[r, *(moved[r] if r in moved else (x, y, a))] for r, x, y, a in pl]


def judge(arm, seed, moved):
    d = W / f"{arm}-{seed}"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    src, cfg, _ = pb.board_src("opus2")
    for f in src.iterdir():
        if f.suffix in (".kicad_pcb", ".kicad_pro", ".kicad_prl"):
            shutil.copy(f, d / f.name)
    pcb = next(d.glob("*.kicad_pcb"))
    json.dump(placement_of(moved), open(d / "placement.json", "w"))
    rc, o, e = K.sh([PCB, "py", ROOT / "tools/spikes/spike4/perturb_kpy.py", pcb, pcb, "--apply", d / "placement.json"])
    assert rc == 0, (o + e)[-400:]
    K.sh([PCB, "route", "canon", pcb])
    K.sh([PCB, "route", "strip", pcb])
    pb.kpy("prep", pcb)
    plan = pb.kpy("rules", pcb)
    json.dump(plan, open(d / "plan.json", "w"), indent=1)
    rc, o, e = K.sh([PCB, "route", "waves", pcb, "--plan", d / "plan.json", "--work", d / "work"])
    waves = json.load(open(d / "waves.json")) if (d / "waves.json").exists() else {}
    j = pb.judges("opus2", pcb, waves) if waves else {"error": (o + e)[-300:]}
    rc, o, e = K.sh([PCB, "check", pcb, cfg, "--only", "feeds,decoupling", "--netlist", pb.netlist_of("opus2"), "--out", d / "rows.json"])
    rows = json.load(open(d / "rows.json"))["rows"] if (d / "rows.json").exists() else []
    for fam in ("feeds", "decoupling"):
        fr = [x for x in rows if x["check"] == fam]
        j[fam] = {"n": len(fr), "fail": [x["id"].split(":", 1)[1] for x in fr if x["status"] == "fail"]}
    row = {"ts": dt.datetime.now().isoformat(timespec="seconds"), "arm": arm, "seed": seed, **j}
    with LOCK:
        with open(OUT, "a") as f:
            f.write(json.dumps(row, sort_keys=True) + "\n")
    shutil.rmtree(d, ignore_errors=True)
    print(arm, seed, j.get("clean"), j.get("signal_vias"), j.get("return_via_bad"), j.get("exposure_mm"), j.get("vin_mW"), len(j.get("feeds", {}).get("fail", [])), len(j.get("decoupling", {}).get("fail", [])), flush=True)


def best5():
    rows = [json.loads(l) for l in open(HERE / "route-results.jsonl")]
    out = []
    for arm in ARMS:
        tag, src = ("rerun", "class") if arm == "class_rerun" else ("h1", arm)   # the pre-registered r2 rerun, seeds 100 to 149
        rs = [r for r in rows if r["tag"] == tag and r["board"] == "r2" and r["arm"] == src and r.get("auto", {}).get("clean")]
        rs.sort(key=lambda r: (r["auto"].get("signal_vias") or 999, r["auto"]["length_mm"]))
        out += [(arm, r["seed"], r["moved"]) for r in rs[:5]]
    return out


def cmd_run(a):
    done = {(x["arm"], x["seed"]) for x in map(json.loads, open(OUT))} if OUT.exists() else set()
    todo = [("designer", 0, {})] + best5()
    todo = [t for t in todo if t[:2] not in done]
    print(len(todo), "to judge", flush=True)
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        for fu in cf.as_completed([ex.submit(judge, *t) for t in todo]):
            fu.result()


def cmd_table(a):
    rows = [json.loads(l) for l in open(OUT)]
    s0 = next(r for r in rows if r["arm"] == "designer")
    print("| Arm | Placements | Clean on waves | Signal vias, median | Length mm, median | VIN mW, median | Off-plane mm (bucket 3), median | Return-via bad, median | Exposure mm, median | Currents fails, median | Feeds fails, median | Decoupling fails, median |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    summ = {}
    for arm in ["designer"] + ARMS:
        rs = [r for r in rows if r["arm"] == arm and "error" not in r]
        if not rs:
            continue
        med = lambda f: st.median([f(r) for r in rs])
        s = {"n": len(rs), "clean": sum(bool(r.get("clean")) for r in rs), "signal_vias": med(lambda r: r["signal_vias"]), "length_mm": round(med(lambda r: r["length_mm"]), 1), "vin_mW": round(med(lambda r: r["vin_mW"]), 1),
             "bucket3_off_mm": med(lambda r: r["off_by_bucket"].get("3", 0)), "return_via_bad": med(lambda r: r["return_via_bad"]), "exposure_mm": med(lambda r: r["exposure_mm"]),
             "currents_fails": med(lambda r: len(r["currents_fails"])), "feeds_fails": med(lambda r: len(r["feeds"]["fail"])), "decoupling_fails": med(lambda r: len(r["decoupling"]["fail"]))}
        summ[arm] = s
        print(f"| `{arm}` | {s['n']} | {s['clean']} | {s['signal_vias']} | {s['length_mm']} | {s['vin_mW']} | {s['bucket3_off_mm']} | {s['return_via_bad']} | {s['exposure_mm']} | {s['currents_fails']} | {s['feeds_fails']} | {s['decoupling_fails']} |")
    json.dump(summ, open(HERE / "judges-summary.json", "w"), indent=1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["run", "table"])
    ap.add_argument("--jobs", type=int, default=3)
    a = ap.parse_args()
    {"run": cmd_run, "table": cmd_table}[a.cmd](a)


if __name__ == "__main__":
    main()
