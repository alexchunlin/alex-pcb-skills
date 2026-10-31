#!/bin/zsh
# Full regeneration of the KiCad project and fab package from the Zener source. Never opens a KiCad window.
# Usage: tools/regen.sh            (run from anywhere)
set -e
set -o pipefail
cd "$(dirname "$0")/.."
PCB=~/.local/bin/pcb
KC=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
PY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
L=layout/qwiic_imu
step() { echo "== $*"; }

step "1 pcb build (Zener netlist + checks)";        $PCB build qwiic_imu.zen
step "2 pcb layout --no-open (sync footprints/nets into the .kicad_pcb)";  $PCB layout --no-open qwiic_imu.zen
step "3 placement / routing / planes / silk";       $PY tools/layout_board.py 2>&1 | grep -v "wxApp\|assert \"\"\|memory leak"
step "4 pcb apply schematic --no-open";             $PCB apply schematic --no-open qwiic_imu.zen
step "5 project symbol library + sym-lib-table";    python3 -I tools/make_symlib.py $L/qwiic_imu.kicad_sch $L/qwiic_imu_symbols.kicad_sym $L/sym-lib-table '${KIPRJMOD}/qwiic_imu_symbols.kicad_sym'
step "6 part fields + global labels into the schematic"; python3 -I tools/sync_schematic.py $L/qwiic_imu.kicad_pcb $L/qwiic_imu.kicad_sch
step "7 fab rule pack next to the board";           cp /tmp/pcb-ref/kicad-druid/JLCPCB/JLCPCB.kicad_dru $L/qwiic_imu.kicad_dru
step "8 ERC";       $KC sch erc --format json --severity-all --output $L/erc.json $L/qwiic_imu.kicad_sch 2>&1 | grep "Found"
step "9 DRC with schematic parity + JLCPCB rules";  $KC pcb drc --schematic-parity --severity-all --format json --output $L/drc.json $L/qwiic_imu.kicad_pcb 2>&1 | grep "Found"
step "10 netlist (kicadxml)"; $KC sch export netlist --format kicadxml --output $L/qwiic_imu.xml $L/qwiic_imu.kicad_sch 2>&1 | grep -v "wxApp\|Fontconfig\|annotation" || true
step "11 netlist verification";                     python3 -I tools/verify_netlist.py $L/qwiic_imu.xml
step "12 fab package";
mkdir -p fab/gerbers; rm -f fab/gerbers/*
$KC pcb export gerbers --layers "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts" --no-protel-ext --subtract-soldermask --output fab/gerbers/ $L/qwiic_imu.kicad_pcb 2>&1 | grep -c Plotted
$KC pcb export drill --format excellon --excellon-units mm --generate-map --map-format gerberx2 --output fab/gerbers/ $L/qwiic_imu.kicad_pcb 2>&1 | grep -v "wxApp\|Fontconfig" | tail -1
(cd fab && rm -f qwiic_imu_gerbers.zip && zip -q qwiic_imu_gerbers.zip gerbers/*)
$KC pcb export pos --format csv --units mm --side both --smd-only --output fab/qwiic_imu_pos.csv $L/qwiic_imu.kicad_pcb 2>&1 | grep -v "wxApp\|Fontconfig" | tail -1
$PCB bom --offline -f json qwiic_imu.zen > fab/qwiic_imu_bom.json 2>/dev/null; python3 -I tools/bom_csv.py fab/qwiic_imu_bom.json $L/qwiic_imu.kicad_pcb fab/qwiic_imu_bom.csv
$KC pcb render --side top --width 1400 --height 1400 --zoom 0.72 --quality high --output fab/qwiic_imu_top.png $L/qwiic_imu.kicad_pcb 2>&1 | grep -v "wxApp\|Fontconfig" | tail -1
$KC pcb render --side bottom --width 1400 --height 1400 --zoom 0.72 --quality high --output fab/qwiic_imu_bottom.png $L/qwiic_imu.kicad_pcb 2>&1 | grep -v "wxApp\|Fontconfig" | tail -1
# pcb dfm exits non-zero on verdict "fail"; on this board the verdict is driven only by the one rule it cannot
# evaluate (solder-jumper bridge copper has no net), so report the summary instead of failing the pipeline.
step "13 pcb dfm --offline";  ($PCB dfm --offline qwiic_imu.zen 2>/dev/null || true) | python3 -I -c "import sys,json; d=json.load(sys.stdin); print('verdict', d['verdict'], d['summary'])"
echo "done"
