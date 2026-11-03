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


def power_nets(b):
    """Nets in a net class at least 0.5 mm wide (the board's own power and motor rails) plus GND."""
    import os
    pro = os.path.splitext(b.GetFileName())[0] + ".kicad_pro"
    ns = json.load(open(pro)).get("net_settings", {})
    w = {c["name"]: float(c.get("track_width") or 0) for c in ns.get("classes", [])}
    import fnmatch
    pats = [x["pattern"] for x in ns.get("netclass_patterns", []) if w.get(x.get("netclass"), 0) >= 0.5]
    nets = {n.GetNetname() for n in b.GetNetInfo().NetsByNetcode().values()}
    return {n for n in nets if any(fnmatch.fnmatchcase(n, p) for p in pats)} | RAILS


def subsystem(b, ic, power):
    """The IC plus every two-pad part with a pad on one of the IC's non-power nets; the subsystem's local nets are the
    nets whose every pad is on those parts."""
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    ic_nets = {p.GetNetname() for p in fps[ic].Pads() if p.GetNetname() and p.GetNetname() not in power}
    members = {ic}
    for r, f in fps.items():
        pads = [p for p in f.Pads() if p.GetNetname()]
        if r != ic and len(pads) <= 3 and r[0] in "CRLD" and any(p.GetNetname() in ic_nets for p in pads):
            members.add(r)
    by_net = {}
    for r, f in fps.items():
        for p in f.Pads():
            if p.GetNetname():
                by_net.setdefault(p.GetNetname(), set()).add(r)
    local = sorted(n for n, rs in by_net.items() if rs <= members and n not in RAILS)
    return members, local


def hot_loop(b):
    """The switch node: the inductor pad net that also reaches an IC pin (L1.1 = SW on the rung-2 boards); its pads'
    bounding box grown 0.8 mm. Returns (net, [x0, y0, x1, y1], owning IC)."""
    for f in b.GetFootprints():
        if not f.GetReference().startswith("L"):
            continue
        for p in f.Pads():
            n = p.GetNetname()
            pads = [q for g in b.GetFootprints() for q in g.Pads() if q.GetNetname() == n]
            ics = {q.GetParentFootprint().GetReference() for q in pads if q.GetParentFootprint().GetReference().startswith("U")}
            if ics and n not in RAILS:
                xs, ys = [], []
                for q in pads:
                    x, y = xy(q.GetPosition()); r = ToMM(q.GetBoundingRadius())
                    xs += [x - r, x + r]; ys += [y - r, y + r]
                return n, [round(min(xs) - 0.8, 2), round(min(ys) - 0.8, 2), round(max(xs) + 0.8, 2), round(max(ys) + 0.8, 2)], sorted(ics)[0]
    return None, None, None


def rules(path, zones):
    b = pcbnew.LoadBoard(path)
    import pcbroute
    plan = pcbroute.default_plan(path)
    pads = {f"{f.GetReference()}.{p.GetNumber()}" for f in b.GetFootprints() for p in f.Pads()}
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
        print(json.dumps(rules(path, "--zones" in sys.argv)))
    elif cmd == "intrusion":
        print(json.dumps(intrusion(path)))
    elif cmd == "summary":
        print(json.dumps(summary(path)))
