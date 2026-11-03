"""verify 28 helper: pad_feed / thermal_vias on the archived attempt-2 board (run with `pcb py`, cwd = a scratch copy)."""
import json, math, pcbnew
from pcblib.board import Board
B = Board.load("motor1.kicad_pcb"); b = B.b; B.clearance = 0.2
for z in [z for z in b.Zones() if z.GetZoneName() in {"VM_neck", "MOTOR_B_neck", "PVIN", "Q1_source", "C17_vin"}]:
    b.Delete(z)
for t in [t for t in b.Tracks()]:
    b.Delete(t)
B.save(); B.fill(); b = B.b    # the router's input state: copper stripped, pours refilled into the space it left
import os, shutil
os.makedirs("orig", exist_ok=True)
for ext in (".kicad_pcb", ".kicad_pro"):
    shutil.copy("motor1" + ext, "orig/motor1" + ext)   # the stripped placement, for plan_feeds and feed_room below
out = {}
r = B.pad_feed("U2", "11", 2.5, length=1.0, across=1)
out["vm_vias"] = r["vias"]; out["vm_amps"] = r["amps_capacity"]
try:
    B.pad_feed("U2", "10", 2.5, length=1.0, across=3)
    out["out2"] = "placed"
except ValueError as e:
    out["out2"] = "C13" in str(e) or "C12" in str(e) or "feed_U2_11" in str(e)
r = B.pad_feed("U1", "4,5,6", 2.8, splay=-30)
out["pvin_vias"] = r["vias"]; xy_ = r["vias_xy"]
out["thermal_u1"] = B.thermal_vias("U1")
B.save()
b2 = pcbnew.LoadBoard("motor1.kicad_pcb")
nets = {}
for t in b2.GetTracks():
    if t.GetClass() == "PCB_VIA":
        p = (round(pcbnew.ToMM(t.GetPosition().x), 3), round(pcbnew.ToMM(t.GetPosition().y), 3))
        if any(math.hypot(p[0] - x, p[1] - y) < 0.01 for x, y in xy_):
            nets[str(p)] = t.GetNetname()
out["pvin_nets_after_save"] = sorted(set(nets.values()))

# FEED-2: plan_feeds on a fresh copy fans VM and OUT2 apart (straight exit past the pin tips, splay away from the neighbour)
B2 = Board.load("orig/motor1.kicad_pcb"); B2.clearance = 0.2
res = B2.plan_feeds([("U2.11", 2.5), ("U2.10", 2.5), ("U2.8", 2.5)])
print(json.dumps({**out, "plan": {k: ("FAIL" if "error" in v else v["vias"]) for k, v in res.items()},
                  "splays_opposite": "error" not in res["U2.10"] and "error" not in res["U2.11"] and res["U2.10"]["splay"] * res["U2.11"]["splay"] <= 0}))
