"""Spike #3, C2: a pogo-pin plate for a board, from jig_points.py's JSON, built with alex-3d-skills' cadlib.

    ~/code-stuff/alex-3d-skills/skills/print-cad-blender/scripts/cad build tools/spikes/spike3/jig/build_jig.py -- \
        --points /tmp/spike3/jig/jig.json --out /tmp/spike3/jig/build

The plate is held above the face-up board on two M2.5 standoffs through the board's mounting holes; P75 pins pressed
into it reach down to the test pads and the DNP header's plated holes. Plate: the board outline plus MARGIN on every
side, THICK thick, printed flat (no supports). Pin holes PIN_HOLE (P75 barrel 1.02 mm: 1.10 printed shrinks to a press
fit; 1.70 for an R75 receptacle), alignment holes M25_CLEAR. Each pin hole gets a 0.6 mm chamfer-free counterbore of
PIN_CB on the top face so the pin's collar seats flush. Outputs: stl/PRT_pogo_plate.stl, manifest.json, model.blend.
"""
import json, os, sys
SKILL = os.environ.get("CAD_SKILL") or sys.exit("run through cad build (CAD_SKILL unset)")
sys.path.insert(0, os.path.join(SKILL, "scripts"))
from cadlib import asm, export, geom as G  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
PTS = json.load(open(arg("--points", "/tmp/spike3/jig/jig.json")))
OUT = arg("--out", "/tmp/spike3/jig/build")
MARGIN, THICK = 4.0, 6.0
PIN_HOLE = float(arg("--pin-hole", "1.10"))
PIN_CB, PIN_CB_D = 1.6, 1.0           # P75 collar seat
M25_CLEAR = 2.9

w, h = PTS["outline_mm"]
r = PTS["corner_r_mm"] + MARGIN
asm.new_scene(params={"MARGIN": MARGIN, "THICK": THICK, "PIN_HOLE": PIN_HOLE, "M25_CLEAR": M25_CLEAR, "pins": len(PTS["pins"])})
plate = G.prism("plate", G.rrect(-w / 2 - MARGIN, w / 2 + MARGIN, -h / 2 - MARGIN, h / 2 + MARGIN, r), 0, THICK, "Z")
cuts = []
for p in PTS["pins"]:
    x, y = p["xy"]
    cuts.append(G.cyl("pin_" + p["ref"], (x, y), PIN_HOLE / 2, -1, THICK + 1, "Z"))
    cuts.append(G.cyl("cb_" + p["ref"], (x, y), PIN_CB / 2, THICK - PIN_CB_D, THICK + 1, "Z"))
for a in PTS["align"]:
    x, y = a["xy"]
    cuts.append(G.cyl("align_" + a["ref"], (x, y), M25_CLEAR / 2, -1, THICK + 1, "Z"))
G.csg(plate, sub=cuts)
asm.part(plate, "PRT_pogo_plate", "PRT", "pla_a", stl="pogo_plate", print_rot=asm.R_ID,
         orient="flat on the bed, collar seats up", supports="no", infill=40,
         pins=[p["ref"] for p in PTS["pins"]], board=PTS["board"])
os.makedirs(OUT, exist_ok=True)
qty = export.export_stls(os.path.join(OUT, "stl"))
asm.write_manifest(os.path.join(OUT, "manifest.json"))
export.save_blend(os.path.join(OUT, "model.blend"))
print("JIG_DONE", qty, "pins", len(PTS["pins"]), "align", len(PTS["align"]))
