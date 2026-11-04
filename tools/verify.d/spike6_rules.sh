# Spike #6 copper rules and block gates on a scratch copy of the attempt-2 board: `via_in_pad` flags a planted via and honours
# an exposed-pad exemption, `edge_margin` flags a planted track, `ground-islands` grounds the fill, `pcb block` enforces order.
# Sourced by tools/verify_all.sh. About 40 s.
# watch: skills/kicad-design/scripts/pcbblock.py skills/kicad-design/scripts/pcbcheck.py skills/kicad-design/scripts/pcblib/board.py skills/kicad-design/scripts/pcbroute.py
T6="$V/spike6"; mkdir -p "$T6"
cp "$ROOT"/examples/rung2-zener-a2-opus/board/motor1.kicad_p* "$ROOT"/examples/rung2-zener-a2-opus/board/motor1.xml "$T6/" 2>/dev/null
cat > "$T6/plant.py" <<'P'
import json, sys
from pcblib.board import Board
B = Board.load("motor1.kicad_pcb"); B.clearance = 0.2
x, y = B.pad_xy("C10", "1"); B.via(x, y, B.fp("C10").FindPadByNumber("1").GetNetname())
ex = B.b.GetBoardEdgesBoundingBox(); import pcbnew
B.route("GND", [(pcbnew.ToMM(ex.GetLeft()) + 0.5, 120.0), (pcbnew.ToMM(ex.GetLeft()) + 0.5, 122.0)], layer="B.Cu", width=0.2)
B.save()
json.dump({"via_in_pad": {"allow": ["U2.17", "U1.15"]}, "edge_margin": {}, "gnd_islands": {}}, open("c.json", "w"))
P
( cd "$T6" && "$PCB" py plant.py > plant.txt 2>&1; "$PCB" check motor1.kicad_pcb c.json --only via_in_pad,edge_margin --out j.json > check.txt 2>&1 )
python3 -I -c "
import json, sys
r = json.load(open('$T6/j.json'))['rows']
assert any(x['id'].startswith('via_in_pad:C10.1') and x['status'] == 'fail' for x in r), r
assert not any(x['id'].startswith('via_in_pad:U2.17') for x in r), r
assert any(x['id'] == 'edge_margin:track GND' and x['status'] == 'fail' for x in r), r
print('ok')" > "$T6/rows.txt" 2>&1 && ok "spike 6: via_in_pad catches a via planted in C10.1, exposed pads exempt, edge_margin catches a track 0.4 mm off the outline" || bad "spike 6 rows: $(tail -2 "$T6/rows.txt")"
cp "$ROOT"/examples/rung2-zener-a2-opus/board/motor1.kicad_pcb "$T6/"
cat > "$T6/isl.py" <<'P'
from pcblib.board import Board
import pcbnew
B = Board.load("motor1.kicad_pcb"); B.clearance = 0.2; B.edge_clearance = 0.4
for z in [z for z in B.b.Zones() if not z.GetIsRuleArea() and z.GetNetname() != "GND" and z.IsOnLayer(pcbnew.In2_Cu)]:
    B.b.Delete(z)
B.zone("GND", "In2.Cu", clearance=0.3, name="GND_In2x"); B.save(); B.fill()
n = len([i for i in B.fill_islands() if i["area_mm2"] >= 2.0])
r = B.ground_islands(min_mm2=2.0, edge_mm=1.0)
m = len([i for i in B.fill_islands() if i["area_mm2"] >= 2.0])
print("ISL", n, m, len(r["placed"]))
P
( cd "$T6" && "$PCB" py isl.py > isl.txt 2>&1 )
python3 -I -c "
import re
n, m, p = map(int, re.search(r'ISL (\d+) (\d+) (\d+)', open('$T6/isl.txt').read()).groups())
assert n > 0 and p > 0 and m < n, (n, m, p)
print('ok', n, m, p)" > "$T6/isl-ok.txt" 2>&1 && ok "spike 6: ground_islands ties fill islands over 2 mm^2 to ground ($(cat "$T6/isl-ok.txt"))" || bad "spike 6 islands: $(tail -2 "$T6/isl.txt")"
cp "$ROOT"/examples/rung2-zener-a2-opus/board/motor1.kicad_pcb "$T6/"
cat > "$T6/gate.py" <<'P'
import json
from pcblib.board import Board
b = Board.load("motor1.kicad_pcb"); d = json.load(open("blocks.json"))
g = next(g for g in d["groups"] if g["name"] == "LDO")
print(len(b.park(set(g["refs"]) | {f"H{i}" for i in range(1, 5)}))); b.save()
P
( cd "$T6" && "$PCB" block init motor1.kicad_pcb --out blocks.json > init.txt 2>&1
  python3 -I -c "
import json
d = json.load(open('blocks.json'))
for i, g in enumerate(d['groups']): g['region'] = [100 + 10 * i, 100, 110 + 10 * i, 140]
d['order'] = ['LDO', 'BUCK', 'CONN', 'DRV', 'PWR']
json.dump(d, open('blocks.json', 'w'))" ; "$PCB" block plan motor1.kicad_pcb blocks.json > plan.txt 2>&1
  "$PCB" py gate.py > gate0.txt 2>&1; "$PCB" block gate motor1.kicad_pcb blocks.json BUCK > gate1.txt 2>&1 )
grep -q "out of order: the next block is LDO" "$T6/gate1.txt" && ok "spike 6: pcb block gate refuses a block out of order" || bad "spike 6 gate: $(tail -3 "$T6/gate1.txt")"
