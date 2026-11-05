#!/bin/zsh
# judges on a copy of each handed-in board; one output dir per board (the shared /tmp/pcb-irdrop path cannot reach these)
S=$HOME/code-stuff/alex-pcb-skills-spike6/skills/kicad-design/scripts; R=$HOME/code-stuff/alex-pcb-runs; J=/tmp/spike6/judge
mkdir -p $J
for r in s6-a-1 s6-a-2 s6-a-3 s6-b-1 s6-b-2 s6-b-3; do
 (
  d=$J/$r; mkdir -p $d; cp $R/$r/layout/motor1/motor1.kicad_{pcb,pro,sch} $R/$r/layout/motor1/motor1.xml $d/ 2>/dev/null; cp $R/$r/checks.json $d/; cd $d
  $S/pcb drc motor1.kicad_pcb --pack jlcpcb > drc.txt 2>&1
  $S/pcb q motor1.kicad_pcb ratsnest --json > rats.json 2>&1
  $S/pcb check motor1.kicad_pcb checks.json --out check.json --netlist $d/motor1.xml > check.txt 2>&1
  $S/pcb irdrop motor1.kicad_pcb --net VIN --source Q1.1,Q1.2,Q1.3 --config checks.json --out $d/ir --json > ir.txt 2>&1
  $S/pcb block init motor1.kicad_pcb --out mod.json > /dev/null 2>&1
  python3 -I -c "
import json; d=json.load(open('mod.json'))
for g in d['groups']: g['region']=None
json.dump(d,open('mod.json','w'))"
  $S/pcb block report motor1.kicad_pcb mod.json --json > coh.txt 2>&1
 ) &
done
wait; echo done
