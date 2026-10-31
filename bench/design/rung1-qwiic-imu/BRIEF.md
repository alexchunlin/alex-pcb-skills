# Design brief: Qwiic 6-DoF IMU breakout (rung 1)

A small I2C sensor breakout in the Qwiic ecosystem. Deliberately simple: one IC, two connectors, one voltage. The
point is to exercise the whole chain (code -> schematic -> layout -> checks -> fab package -> review), not the
circuit. Reference for the ecosystem: SparkFun Qwiic standard (3.3 V, I2C, JST SH 1.0 mm 4-pin, pin order
GND, 3V3, SDA, SCL).

## Function
- Sensor: ST **LSM6DS3TR-C** (accel + gyro, I2C). It is in KiCad's stock `Sensor_Motion` library and in
  JLCPCB's extended parts (LCSC C967633; confirm stock). Alternatives with the same footprint and pinout are
  acceptable if justified in the design log.
- Two **Qwiic connectors** (JST SH SM04B-SRSS-TB, horizontal, stock footprint
  `Connector_JST:JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal`), daisy-chain wired, pin order per the Qwiic
  standard.
- I2C address select: solder jumper on SA0, default address 0x6B (SA0 high) or 0x6A, state marked on silk.
- I2C pull-ups 2.2 kOhm to 3V3 on SDA and SCL, each removable by cutting a 3-way or 2-way solder jumper (default
  closed).
- INT1 and INT2 brought to a 0.1" 1x4 header footprint (unpopulated): INT1, INT2, SDA, SCL. The header also allows
  non-Qwiic use.
- Power: 3.3 V from Qwiic only. No regulator. Decoupling per the LSM6DS3 datasheet (100 nF on VDD and VDDIO, plus
  a bulk 1 uF or larger), caps within 2 mm of the pins.
- Power LED is **not** wanted (Qwiic power budget).

## Mechanical
- Board 1.0 x 1.0 inch (25.4 x 25.4 mm), corner radius 2 mm, two M2.5 (or #4-40 2.84 mm) mounting holes 0.8 inch
  (20.32 mm) apart on the centre line, SparkFun Qwiic breakout style. Connectors on the two opposite edges that do
  not carry the holes.
- Sensor at the board centre; X and Y axis arrows on the top silk matching the datasheet axes.
- Silk: part name, "Qwiic", I2C address with jumper state, pull-up jumper label, header pin names, revision text.

## Stackup and fab
- **4 layers**, JLCPCB stock 4-layer stackup, 1 oz outer. Layer 2 solid GND, layer 3 3V3 pour (or GND), signals on
  outer layers only. Vias 0.3 mm drill / 0.6 mm pad or larger. Track/clearance at least 0.2 mm (well above the fab
  minimum). This is the design-margin policy: do not go to the fab minimums.
- Pass the JLCPCB `.kicad_dru` rule pack from kicad-druid (`/tmp/pcb-ref/kicad-druid/JLCPCB/JLCPCB.kicad_dru`) with
  zero errors, and KiCad DRC with schematic parity with zero errors. ERC zero errors; every warning listed with a
  reason.
- All parts JLCPCB-assemblable (basic or extended), every symbol carrying `MPN`, `Manufacturer`, `LCSC` and
  `Datasheet` fields.

## Deliverables (in the project directory)
- Source of truth is **code**: the Zener (`.zen`) or SKiDL (`.py`) modules that generate the KiCad project. Hand
  edits to the generated `.kicad_sch`/`.kicad_pcb` are allowed only for placement and routing, and must survive a
  regeneration of the schematic (say in the log how).
- The KiCad 10 project (`.kicad_pro`, `.kicad_sch`, `.kicad_pcb`), ERC and DRC JSON reports, netlist (kicadxml).
- `fab/`: gerbers + drill zip, BOM CSV with LCSC numbers, position file, top and bottom renders.
- `DESIGN_LOG.md`: decisions with the number behind each (pull-up value vs bus capacitance, decoupling placement,
  address choice), what was checked and how, open issues.
- `BRINGUP.md`: numbered steps with expected readings (resistance rails to GND, I2C scan address, WHO_AM_I = 0x6A),
  and the test points that make them possible.
- `progress.md`: one line per completed step with the time, appended as you go.

## Review targets
Scored 1-10 on Electrical correctness, Manufacturability (fab, assembly, bring-up) and Documentation/intent. Target
9/9/9. A 9 needs: I2C bus correct (address, pull-ups, Qwiic pin order on both connectors verified against the
netlist), decoupling within 2 mm and on the correct pins, axis arrows matching the datasheet, DRC/ERC/fab-rule
clean, BOM fully sourced, bring-up steps that a technician could run.
