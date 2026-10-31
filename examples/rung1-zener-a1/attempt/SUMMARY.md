# SUMMARY — rung1-zener-a1 (Qwiic 6-DoF IMU breakout, LSM6DS3TR-C)

Authoring path: Zener / Diode `pcb` 0.4.95 -> KiCad 10.0.1, fully headless (no KiCad GUI was opened).
Wall time: about 56 min.

## What was built
- **Source of truth:** `qwiic_imu.zen` (board, nets, rules) + `parts/*.zen` (LSM6DS3TR-C in I2C mode, Qwiic
  JST SH connector, 3-pad solder jumper, 1x4 header, R, C, test point) + `parts/symbols|footprints` (stock KiCad
  10 library items vendored verbatim).
- **KiCad 10 project:** `layout/qwiic_imu/qwiic_imu.kicad_pro|kicad_sch|kicad_pcb`, with `qwiic_imu.kicad_dru`
  (JLCPCB rule pack), project `sym-lib-table`, `erc.json`, `drc.json`, netlist `qwiic_imu.xml` (kicadxml).
- **Fab package** `fab/`: `qwiic_imu_gerbers.zip` (11 gerber layers + Excellon drill + drill map + job file),
  `qwiic_imu_bom.csv` (6 lines, MPN + LCSC on every line, J3 marked DNP), `qwiic_imu_pos.csv`,
  `qwiic_imu_top.png`, `qwiic_imu_bottom.png`.
- **Docs:** `DESIGN_LOG.md` (decisions with numbers, checks, every warning explained, open issues),
  `BRINGUP.md` (13 numbered steps with expected readings), `progress.md` (step log).
- **Tools** `tools/`: `regen.sh` (one-shot regeneration: build -> layout -> place/route -> schematic -> field
  sync -> ERC/DRC -> netlist checks -> fab exports -> DFM), `layout_board.py` (pcbnew placement/routing/planes/
  silk), `sync_schematic.py`, `make_symlib.py`, `verify_netlist.py`, `bom_csv.py`, `extract_symbol.py`.

Board: 25.4 x 25.4 mm, r = 2 mm, 4 layers (F.Cu signals + GND fill / In1 GND / In2 3V3 / B.Cu INT lines + GND fill),
JLCPCB stock stackup 1 oz outer, HASL-LF. Tracks 0.25 mm (min 0.2), clearance 0.2, vias 0.6/0.3, copper-to-edge
0.4. Holes 2.7 mm on the vertical centre line 20.32 mm apart; Qwiic connectors on the left/right edges.

## Check counts (last `tools/regen.sh` run, reproducible)
| Check | Result |
|---|---|
| ERC (`kicad-cli sch erc --severity-all`) | **0 errors, 1 warning** (pin_to_pin: SDx tied to GND meets the power_out test-point pin used as ERC rail source) |
| DRC with schematic parity + JLCPCB.kicad_dru (`kicad-cli pcb drc --schematic-parity --severity-all`) | **0 violations, 0 unconnected, 2 parity warnings** (KiCad vs Zener naming of the two no-connect pads) |
| Netlist verification (`tools/verify_netlist.py`) | **38/38** (Qwiic pin order on J1 and J2, all U1 pins, JP1/JP2, pull-ups, header, decoupling, test points) |
| Diode DFM (`pcb dfm --offline`) | 43 passed, **0 failed**, 0 warned, 1 incomplete (the tool cannot attribute the solder-jumper bridge copper to a net; KiCad DRC covers it), 12 n/a |
| `pcb build` | OK, 15 components, 2 advisory lint warnings (explained in DESIGN_LOG) |
| `pcb layout --check` | OK |
| Regeneration idempotence | second `regen.sh` run: `schematic unchanged`, identical counts |

## What is missing / caveats
- Live LCSC stock for C967633 not confirmed (product page loads, no stock query). BRINGUP step 7 detects a
  substituted plain LSM6DS3 (WHO_AM_I 0x69 instead of 0x6A).
- The TR-C-specific datasheet could not be downloaded (ST served the LSM6DS3 DocID026899 Rev 4 document; Mouser
  bot-walled). Pinout, address scheme and decoupling are identical; current figures were not re-verified.
- No Zener `TestBench` tests (`pcb test` runs none); netlist intent is verified on the exported KiCad netlist.
- Schematic part fields (MPN/Manufacturer/LCSC/Datasheet) and global labels are added by a reproducible
  post-step (`tools/sync_schematic.py`) because the Zener exporter does not emit them; they survive
  regeneration because the step is part of `regen.sh`.
- Connector housing face sits 0.6 mm inside the board edge (fab copper-to-edge limit on the retention tabs).

## Commands a reviewer should run
```
cd /Users/alxchunlin/code-stuff/alex-pcb-runs/rung1-zener-a1
tools/regen.sh                                   # full regeneration + all checks (~3 min, no GUI)
python3 -I tools/verify_netlist.py layout/qwiic_imu/qwiic_imu.xml
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli sch erc --severity-all --format json --output /tmp/erc.json layout/qwiic_imu/qwiic_imu.kicad_sch
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli pcb drc --schematic-parity --severity-all --format json --output /tmp/drc.json layout/qwiic_imu/qwiic_imu.kicad_pcb
~/.local/bin/pcb build qwiic_imu.zen; ~/.local/bin/pcb dfm --offline qwiic_imu.zen | head -c 400
open fab/qwiic_imu_top.png fab/qwiic_imu_bottom.png
```
