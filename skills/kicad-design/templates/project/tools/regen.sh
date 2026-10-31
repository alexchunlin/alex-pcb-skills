#!/bin/sh
# Full regeneration from the Zener source. Never opens a KiCad window. `pcb regen-check . --cmd tools/regen.sh
# --board layout/PROJECT/PROJECT.kicad_pcb --generated layout fab` must say REGENERATES before hand-off.
set -eu
cd "$(dirname "$0")/.."
PCB="${PCB_WRAPPER:-$HOME/code-stuff/alex-pcb-skills/skills/kicad-design/scripts/pcb}"
P=PROJECT
$PCB build $P.zen
$PCB layout $P.zen                               # --no-open is added by the wrapper
$PCB py tools/layout_board.py layout/$P/$P.kicad_pcb
$PCB apply schematic $P.zen
$PCB schfix layout/$P/$P.kicad_sch
$PCB erc layout/$P/$P.kicad_sch
$PCB drc layout/$P/$P.kicad_pcb --pack jlcpcb || [ $? = 1 ]     # exit 1 = errors found, reported above; 2 = pack rejected, stop
$PCB check layout/$P/$P.kicad_pcb checks.json || true
mkdir -p fab
$PCB fab layout/$P/$P.kicad_pcb --out fab
echo "regen done"
