"""KiCad-Python half of the plan bench (run with `pcb py`): input prep, the rule plans, the hot-loop intrusion judge.

  pcb py plan_kpy.py prep BOARD               non-GND zones deleted, In2 one GND zone (Alex's stackup), saved and filled
  pcb py plan_kpy.py rules BOARD [--zones]    the rule plan as JSON on stdout
  pcb py plan_kpy.py intrusion BOARD          foreign signal track inside the switch-node loop, JSON on stdout
  pcb py plan_kpy.py summary BOARD            what an agent gets to write a plan from, JSON on stdout
"""
import json, math, sys

import pcbnew
from pcbnew import ToMM
from pcblib.board import Board, xy

FEEDS = [("U2.11", 2.5), ("U2.10", 2.5), ("U2.8", 2.5), ("U1.4,5,6", 2.8), ("Q1.2", 4.0), ("Q1.6", 4.0), ("L1.2", 3.0)]
THERMAL = ["U2", "U1"]
RAILS = {"GND"}


def prep(path):
    bd = Board.load(path); b = bd.b
    src = next(z for z in b.Zones() if not z.GetIsRuleArea() and z.GetNetname() == "GND" and z.IsOnLayer(pcbnew.In1_Cu))
    outline = [xy(src.GetCornerPosition(i)) for i in range(src.GetNumCorners())]
    gone = [z for z in b.Zones() if not z.GetIsRuleArea() and (z.GetNetname() != "GND" or z.IsOnLayer(pcbnew.In2_Cu))]
    bd.zone("GND", "In2.Cu", outline=outline, clearance=0.3, name="GND_In2")
    for z in gone:
        b.Delete(z)   # Delete, never Remove (R1-Z1-T4)
    bd.save(); bd.fill()
    return {"deleted_zones": len(gone)}


import pcbroute
power_nets, subsystem, hot_loop = pcbroute.power_nets, pcbroute.subsystem, pcbroute.hot_loop   # moved into the tool (SIG-4)


def rules(path, zones, cfg=None):
    """The rule plan; feeds and thermal vias from the config when one is given (a foreign board), else the rung-2 lists."""
    b = pcbnew.LoadBoard(path)
    plan = pcbroute.default_plan(path)
    pads = {f"{f.GetReference()}.{p.GetNumber()}" for f in b.GetFootprints() for p in f.Pads()}
    if cfg:
        c = json.load(open(cfg))
        plan["feeds"] = [{"pad": f["pad"], "amps": float(f["amps"])} for f in c.get("feeds", []) if not f["pad"].startswith("C")]
        plan["thermal_vias"] = list((c.get("thermal_vias") or {}).keys())
    else:
        plan["feeds"] = [{"pad": p, "amps": a} for p, a in FEEDS if p.split(",")[0] in pads or p.split(".")[0] + "." + p.split(".")[1].split(",")[0] in pads]
        plan["thermal_vias"] = THERMAL
    if zones:
        power = power_nets(b)
        sw, box, ic = hot_loop(b)
        if sw:
            _, local = subsystem(b, ic, power)
            x0, y0, x1, y1 = box
            poly = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
            waves = [w for w in plan["waves"] if w["name"] == "power"]
            waves.append({"name": f"{ic.lower()}-local", "nets": local})
            for w in plan["waves"]:
                if w["name"] != "power":
                    waves.append({**w, "keepouts": [poly]})
            plan["waves"] = waves
    return plan


def intrusion(path):
    b = pcbnew.LoadBoard(path)
    power = power_nets(b)
    sw, box, ic = hot_loop(b)
    _, local = subsystem(b, ic, power)
    own = set(local) | power | {sw}
    x0, y0, x1, y1 = box
    mm_in = {}
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA" or t.GetNetname() in own:
            continue
        a, e = t.GetStart(), t.GetEnd(); n = 20
        for k in range(n):
            x = ToMM(a.x + (e.x - a.x) * (k + 0.5) / n); y = ToMM(a.y + (e.y - a.y) * (k + 0.5) / n)
            if x0 < x < x1 and y0 < y < y1:
                mm_in[t.GetNetname()] = mm_in.get(t.GetNetname(), 0) + ToMM(t.GetLength()) / n
    return {"hot_net": sw, "box": box, "owner": ic, "local_nets": local,
            "foreign_mm": round(sum(mm_in.values()), 1), "by_net": {k: round(v, 1) for k, v in sorted(mm_in.items(), key=lambda kv: -kv[1])}}


def summary(path):
    b = pcbnew.LoadBoard(path)
    power = power_nets(b)
    parts = [{"ref": f.GetReference(), "value": f.GetValue(), "xy": [round(v, 2) for v in xy(f.GetPosition())],
              "rot": round(f.GetOrientationDegrees()), "side": "B" if f.GetLayer() == pcbnew.B_Cu else "F"} for f in b.GetFootprints()]
    nets = {}
    for f in b.GetFootprints():
        for p in f.Pads():
            if p.GetNetname():
                nets.setdefault(p.GetNetname(), []).append(f"{f.GetReference()}.{p.GetNumber()}")
    sw, box, ic = hot_loop(b)
    edge = [xy(d.GetStart()) for d in b.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]
    return {"board_extent_mm": [round(min(x for x, _ in edge), 1), round(min(y for _, y in edge), 1), round(max(x for x, _ in edge), 1),
                                round(max(y for _, y in edge), 1)] if edge else None,
            "stackup": "F.Cu signals and rails, In1.Cu solid GND, In2.Cu solid GND, B.Cu signals and rails",
            "power_nets": sorted(power), "switch_node": {"net": sw, "box": box, "owner": ic}, "parts": parts,
            "nets": {k: v for k, v in sorted(nets.items())}}


if __name__ == "__main__":
    cmd, path = sys.argv[1], sys.argv[2]
    if cmd == "prep":
        print(json.dumps(prep(path)))
    elif cmd == "rules":
        cfg = sys.argv[sys.argv.index("--config") + 1] if "--config" in sys.argv else None
        print(json.dumps(rules(path, "--zones" in sys.argv, cfg)))
    elif cmd == "intrusion":
        print(json.dumps(intrusion(path)))
    elif cmd == "summary":
        print(json.dumps(summary(path)))
