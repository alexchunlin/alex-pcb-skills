#!/usr/bin/env python3
"""Spike #3, C1: the `irdrop` row against the `feeds` row on the 10 replay boards, per label.

For every board in tools/bench/corpus.json: copy the board and its checks.json to /tmp/spike3/irbench/<attempt>, run
`pcb check --only feeds` and `pcb check --only irdrop` (each its own report), time them, and match the six feed and
thermal labels' patterns (FEED_LABELS) against each row family. Every fail line of either row that no label explains is
listed for triage (the bench's false-fail rule). Writes tools/spikes/spike3/results/irdrop_bench.json.

  python3 -I tools/spikes/spike3/irdrop_bench.py [--jobs 3]
"""
from __future__ import annotations

import json, re, shutil, subprocess, sys, tarfile, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PCB = str(ROOT / "skills/kicad-design/scripts/pcb")
OUT = Path("/tmp/spike3/irbench")
RES = Path(__file__).resolve().parent / "results" / "irdrop_bench.json"
# the six "current reached a pin through something no row counted" labels of issue #3, and what each row should print
FEED_LABELS = {
    "R2-S-1": ("rung2-zener-a1-sonnet", "VM fed by one 0.3 mm via and a 0.34 mm zone finger"),
    "R2-O-2": ("rung2-zener-a1-opus", "VM fed only by a 0.335 mm pour neck"),
    "R2-F-3": ("rung2-zener-a1-fable", "VM fed 0.3 mm through an 0402 pad"),
    "R2A2-O-1": ("rung2-zener-a2-opus", "J3.1 fed only by four In2 thermal spokes"),
    "R2A2-O-2": ("rung2-zener-a2-opus", "C17 bulk cap through single vias in series"),
    "R2A2-O-3": ("rung2-zener-a2-opus", "AMS1117 with no heat-sink copper (thermal)"),
}


def run_board(name: str, spec: dict) -> dict:
    w = OUT / name
    if w.exists():
        shutil.rmtree(w)
    w.mkdir(parents=True)
    src = ROOT / spec["dir"]
    if spec.get("tar"):
        with tarfile.open(src / spec["tar"]) as t:
            t.extractall(w)
        board = w / spec["pcb"]
    else:
        shutil.copytree(src / Path(spec["pcb"]).parent, w / Path(spec["pcb"]).parent)
        board = w / spec["pcb"]
    cfg_src = next((src / r["config"] for r in spec["runs"] if r.get("type") == "check" and r.get("config")), None)
    res = {"attempt": name, "rows": {}}
    if cfg_src is None or not cfg_src.exists():
        res["note"] = "no checks.json"
        return res
    cfg = w / "checks.json"
    shutil.copy(cfg_src, cfg)
    for fam in ("feeds", "irdrop"):
        t = time.time()
        rep = w / f"check-{fam}.json"
        p = subprocess.run([PCB, "check", str(board), str(cfg), "--only", fam, "--out", str(rep)], capture_output=True, text=True)
        d = json.load(open(rep)) if rep.exists() else {"rows": [], "not_checked": [p.stderr[-300:]]}
        res["rows"][fam] = {"wall_s": round(time.time() - t, 1), "rows": d["rows"],
                            "not_checked": [n for n in d.get("not_checked", []) if n.startswith(fam)]}
    return res


def main(argv):
    jobs = int(argv[argv.index("--jobs") + 1]) if "--jobs" in argv else 3
    corpus = json.load(open(ROOT / "tools/bench/corpus.json"))["attempts"]
    labels = json.load(open(ROOT / "tools/bench/labels.json"))
    with ThreadPoolExecutor(jobs) as ex:
        results = list(ex.map(lambda kv: run_board(*kv), corpus.items()))
    by = {r["attempt"]: r for r in results}
    lab = {l["id"]: l for l in labels["labels"]}
    ktp = labels.get("known_true_positives", [])
    table = []
    for lid, (att, what) in FEED_LABELS.items():
        locs = [re.compile(x["pattern"]) for x in lab[lid]["locators"] if x["report"] == "check"]
        row = {"label": lid, "attempt": att, "what": what}
        for fam in ("feeds", "irdrop"):
            rows = by[att]["rows"].get(fam, {}).get("rows", [])
            hits = [r for r in rows if r["status"] == "fail" and any(rx.search(f"check fail {r['id']}: {r['msg']}") for rx in locs)
                    and r["check"] == fam]
            row[fam] = hits[0]["id"] if hits else None
        table.append(row)
    triage = []
    for att, r in by.items():
        for fam, d in r["rows"].items():
            for x in d["rows"]:
                if x["status"] != "fail":
                    continue
                line = f"check fail {x['id']}: {x['msg']}"
                labelled = [l["id"] for l in labels["labels"] if l["attempt"] == att and
                            any(re.search(loc["pattern"], line) for loc in l["locators"] if loc["report"] == "check")]
                known = any(k["attempt"] == att and k["report"] == "check" and re.search(k["pattern"], line) for k in ktp)
                triage.append({"attempt": att, "row": fam, "id": x["id"], "labels": labelled, "known_true_positive": known,
                               "msg": x["msg"][:200]})
    summary = {"boards": len(by), "boards_with_feeds": sum(1 for r in by.values() if any(d["rows"] for d in r["rows"].values())),
               "wall_s": {a: {f: d["wall_s"] for f, d in r["rows"].items()} for a, r in by.items()},
               "labels": table,
               "caught": {f: sum(1 for t in table if t[f]) for f in ("feeds", "irdrop")},
               "caught_either": sum(1 for t in table if t["feeds"] or t["irdrop"]),
               "unexplained_fails": {f: sum(1 for t in triage if t["row"] == f and not t["labels"] and not t["known_true_positive"]) for f in ("feeds", "irdrop")},
               "triage": triage,
               "irdrop_summaries": {a: [x["msg"] for x in r["rows"].get("irdrop", {}).get("rows", []) if x["status"] in ("pass", "info")] for a, r in by.items()},
               "not_checked": {a: r["rows"].get("irdrop", {}).get("not_checked", []) for a, r in by.items()}}
    RES.parent.mkdir(parents=True, exist_ok=True)
    json.dump(summary, open(RES, "w"), indent=1)
    for t in table:
        print(f"{t['label']:9} {t['attempt']:22} feeds {t['feeds'] or '-':28} irdrop {t['irdrop'] or '-'}")
    print("caught", summary["caught"], "either", summary["caught_either"], "unexplained fails", summary["unexplained_fails"])
    for t in triage:
        if not t["labels"] and not t["known_true_positive"]:
            print("  UNEXPLAINED", t["attempt"], t["row"], t["id"], t["msg"][:140])
    print("->", RES)


if __name__ == "__main__":
    main(sys.argv[1:])
