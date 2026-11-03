#!/usr/bin/env python3
"""Spike #4 (H1): perturbed placements of the four rung-2 boards, their MPS conflicts and HPWL, routed by KRT.

  python3 -I tools/spikes/spike4/perturb.py gen   [--boards opus,sonnet,fable,opus2] [--n 20] [--workers 2]
  python3 -I tools/spikes/spike4/perturb.py route [--boards ...] [--workers 3] [--tag T]

gen: per board the route bench's own input (archived project copied, footprints sorted, tracks and vias stripped, pours
kept: route_bench.prep), then placement 0 (as archived) and n perturbed placements (perturb_kpy.py, sigma 1, 2, 3, 4 mm
in turn, seed = index, redrawn while KiCad's DRC on the stripped board shows more overlap-type errors than placement 0: courtyards,
shorts, clearance, mask bridges, copper to edge), each with `pcb q conflicts --as-is` and the start measure (`pcb route measure --drc`).
route: each placement routed with the bench's `krt outer` config (KRT's default MPS order, outer layers, setup
kept, sizes exact, the full pass: `--quick 2` left 11 airwires on the archived opus2 placement, so its via count is not a
label), measured as the bench measures; one row per placement in tools/bench/results/placements.jsonl with the placement
as (ref, x, y, rot) so spike #1 can reuse it; a restart skips placements that already have a row. Scratch /tmp/spike4/perturb3/<board>/p<k>/.
"""
import argparse, concurrent.futures as cf, datetime as dt, importlib.util, json, os, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PCB = str(ROOT / "skills/kicad-design/scripts/pcb")
OUT = ROOT / "tools/bench/results/placements.jsonl"
SCR = Path("/tmp/spike4/perturb3")
CONFIG = "outer"   # route_bench config for the labels; outer_quick2 (KRT --quick 2) left 11 airwires on opus2 p0 where the full pass leaves 0
_spec = importlib.util.spec_from_file_location("route_bench", ROOT / "tools/bench/route_bench.py")
rb = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(rb)


def sh(cmd):
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def last_json(out):
    for line in reversed(out.strip().splitlines()):
        if line.startswith("{"):
            return json.loads(line)
    raise RuntimeError(out[-400:])


def base(board):
    d = SCR / board / "base"
    pcb = next(d.glob("*/tracks/input/*.kicad_pcb"), None) if d.exists() else None
    if pcb is None:
        pcb, _ = rb.prep(board, "tracks", d)
    return pcb


# DRC types a moved part can cause by landing on or next to another (a starved thermal is the fixed pour's, not an overlap)
OVERLAP = ("courtyards_overlap", "shorting_items", "clearance", "hole_clearance", "solder_mask_bridge", "copper_edge_clearance",
           "hole_to_hole", "drill_out_of_range")


def overlap_errors(by_type):
    return sum(v for k, v in by_type.items() if k in OVERLAP)


def gen_one(board, k, b):
    d = SCR / board / f"p{k}"
    if (d / "meta.json").exists():
        return json.load(open(d / "meta.json"))
    d.mkdir(parents=True, exist_ok=True)
    pcb = d / b.name
    shutil.copy(b.with_suffix(".kicad_pro"), d / (b.stem + ".kicad_pro"))
    if k == 0:
        shutil.copy(b, pcb)
        pert = {"seed": 0, "sigma": 0.0, "moved": 0, "rejected_draws": 0}
        rc, out, err = sh([PCB, "q", pcb, "fps", "--json"])
        pert["placement"] = [[f["ref"], f["pos"][0], f["pos"][1], f["rot"]] for f in last_json(out)["footprints"]]
        start = rb.pcb_json("route", "measure", str(pcb), "--drc")
    else:
        # rejection by KiCad's own DRC: a placement whose stripped board has more plain errors than the archived one
        # (courtyard overlap, pad-to-pad clearance, copper to edge) is drawn again with the next seed; the box and
        # polygon tests in perturb_kpy.py catch most, some vendored courtyards leave the pins outside
        sigma = 1.0 + (k - 1) % 4
        base_err = overlap_errors(json.load(open(SCR / board / "p0" / "drc" / "drc.json"))["plain"]["by_type"].get("error", {}))
        for tries in range(12):
            seed = k + 1000 * tries
            rc, out, err = sh([PCB, "py", ROOT / "tools/spikes/spike4/perturb_kpy.py", b, pcb, "--seed", seed, "--sigma", sigma])
            if rc:
                raise RuntimeError(err[-400:] or out[-400:])
            pert = last_json(out)
            sh([PCB, "route", "canon", pcb])
            start = rb.pcb_json("route", "measure", str(pcb), "--drc")
            if overlap_errors(start.get("drc", {}).get("plain_by_type") or {}) <= base_err:
                break
        else:
            raise RuntimeError(f"no DRC-clean placement in 12 draws at sigma {sigma}")
        pert["drc_draws"] = tries + 1
    rc, out, err = sh([PCB, "q", pcb, "conflicts", "--as-is", "--json"])
    c = last_json(out)
    dd = start.get("drc", {})
    meta = {"board": board, "k": k, **{x: pert[x] for x in ("seed", "sigma", "moved", "rejected_draws", "placement")}, "drc_draws": pert.get("drc_draws", 0),
            "pcb": str(pcb), "conflicts": c["conflicts"], "signal_conflicts": c["signal_conflicts"], "rounds": c["rounds"],
            "nets": c["nets"], "bipartite": c["bipartite"], "late_nets": c["late_nets"], "edges": c["edges"],
            "hpwl_mm": c["hpwl_mm"], "hpwl_signal_mm": c["hpwl_signal_mm"], "plane_nets": c["plane_nets"],
            "airwires_start": start["ratsnest"]["airwires"], "errors_start": [dd.get("plain_errors"), dd.get("packed_errors")],
            "settings": start["settings"], "start_by_type": dd.get("plain_by_type") or {}}
    json.dump(meta, open(d / "meta.json", "w"))
    return meta


def route_one(meta, tag):
    pcb = Path(meta["pcb"])
    out_dir = pcb.parent / f"krt-{CONFIG}"
    rr = rb.run_router("krt", CONFIG, pcb, out_dir, 600)
    m = rb.measure(rr["board"], meta["settings"]) if rr.get("board") else {"error": rr.get("error", "no output")}
    row = {"ts": dt.datetime.now().isoformat(timespec="seconds"), "tag": tag, "router": "krt", "config": CONFIG,
           **{k: meta[k] for k in ("board", "k", "seed", "sigma", "moved", "conflicts", "signal_conflicts", "rounds", "nets",
                                   "bipartite", "hpwl_mm", "hpwl_signal_mm", "plane_nets", "airwires_start", "errors_start")},
           "wall_s": rr.get("wall_s"), "mps": rr.get("mps")}
    if "error" in m:
        row["error"] = m["error"]
    else:
        d = m.get("drc", {})
        row.update(airwires=m["ratsnest"]["airwires"], vias=m["vias"], signal_vias=m["signal_vias"], signal_vias_by_net=m["signal_vias_by_net"],
                   length_mm=m["length_mm"], plain_errors=d.get("plain_errors"), packed_errors=d.get("packed_errors"),
                   new_errors=max(0, (d.get("plain_errors") or 0) - (meta["errors_start"][0] or 0)))
        row["clean"] = bool(row["airwires"] == 0 and row["new_errors"] == 0)
    row["placement"] = meta["placement"]
    row["edges"] = meta["edges"]
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["gen", "route"])
    ap.add_argument("--boards", default="opus,sonnet,fable,opus2")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--tag", default="spike4-h1")
    a = ap.parse_args()
    boards = a.boards.split(",")
    if a.cmd == "gen":
        bases = {b: base(b) for b in boards}
        with cf.ThreadPoolExecutor(a.workers) as ex:   # placement 0 first: it sets each board's error budget
            list(ex.map(lambda b: gen_one(b, 0, bases[b]), boards))
        jobs = [(b, k) for b in boards for k in range(a.n + 1)]
        with cf.ThreadPoolExecutor(a.workers) as ex:
            futs = {ex.submit(gen_one, b, k, bases[b]): (b, k) for b, k in jobs}
            for f in cf.as_completed(futs):
                b, k = futs[f]
                try:
                    m = f.result()
                    print(f"{b} p{k} sigma {m['sigma']} moved {m['moved']} conflicts {m['conflicts']} signal {m['signal_conflicts']} "
                          f"hpwl {m['hpwl_mm']} start air {m['airwires_start']} err {m['errors_start']}", flush=True)
                except Exception as e:  # noqa: BLE001
                    print(f"{b} p{k} ERROR {type(e).__name__}: {e}"[:300], flush=True)
        return
    metas = [json.load(open(p)) for b in boards for p in sorted((SCR / b).glob("p*/meta.json"), key=lambda p: int(p.parent.name[1:]))]
    done = set()   # a restart skips the placements this tag and config already have a row for
    if OUT.exists():
        for line in OUT.read_text().splitlines():
            r = json.loads(line) if line.strip() else {}
            if r.get("tag") == a.tag and r.get("config") == CONFIG and "error" not in r:
                done.add((r["board"], r["k"]))
    metas = [m for m in metas if (m["board"], m["k"]) not in done]
    with cf.ThreadPoolExecutor(a.workers) as ex, OUT.open("a") as fh:
        for row in ex.map(lambda m: route_one(m, a.tag), metas):
            fh.write(json.dumps(row) + "\n"); fh.flush()
            print(f"{row['board']} p{row['k']} sigma {row['sigma']} conflicts {row['conflicts']}/{row['signal_conflicts']} hpwl {row['hpwl_mm']} "
                  f"-> {'CLEAN' if row.get('clean') else 'open/new'} air {row.get('airwires')} sig vias {row.get('signal_vias')} vias {row.get('vias')} "
                  f"len {row.get('length_mm')} wall {row.get('wall_s')}", flush=True)


if __name__ == "__main__":
    main()
