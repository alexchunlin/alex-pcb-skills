# Design brief: single brushed-DC motor channel module (rung 2)

One channel of a robot motor controller as a stand-alone module, in the style of the MotorGo Plink (one of its four
channels plus its power system). Exercises power, thermal, current sensing, a connector pin map shared with firmware,
and net classes. Reference designs for parts and values: `/tmp/pcb-ref/motorgo-plink-hardware` (DRV8874 channels,
TPS54620 buck, AMS1117 LDO; read-only).

## Function
- **Input**: 6 to 17 V DC on a 2-pin 3.5 mm screw terminal or XT30 (your choice, say why), 4 A continuous budget.
  Reverse-polarity protection (P-MOSFET ideal-diode style preferred over a series Schottky; justify the loss
  numbers). Input bulk capacitance sized for the buck and the motor transients, with the ripple-current rating
  checked.
- **5 V rail**: synchronous buck, 3 A continuous (TPS54620 or an equivalent with an LCSC stock part), switching
  frequency and inductor chosen with the calculation in the log (ripple current 30 to 40 percent of load, output
  ripple under 50 mV). Feedback divider values stated. Layout: input cap, switch node and inductor loop minimal;
  say how small.
- **3.3 V rail**: LDO from 5 V, 500 mA (AMS1117-3.3 or better; dissipation number in the log).
- **Motor driver**: TI **DRV8874** (H-bridge, 2.1 A peak per datasheet with the thermal pad soldered), PWM/EN and
  PH/DIR control, nSLEEP, nFAULT pulled up, IPROPI current sense with the sense resistor scaled so 2 A reads about
  2.5 V at the ADC pin and never exceeds 3.3 V; RC filter on the sense line. Thermal pad to a copper pour with
  stitching vias (count and via size in the log).
- **Encoder port**: 5-pin JST (match the Plink encoder connector pin order: read it from the Plink schematic and
  cite it), 3.3 V supply to the encoder, A/B signals with series resistors to the control header.
- **Control header**: 2x5 0.1" shrouded header to an external MCU. Pin map (the firmware contract) is declared in a
  table in the design log and must match the netlist: 3V3, GND, 5V, PWM, DIR, nSLEEP, nFAULT, ISENSE, ENC_A, ENC_B.
- Status: power LED on 5 V, fault LED on nFAULT.
- Test points: TP1..TPn on VIN, 5V, 3V3, SW node, IPROPI, nFAULT, GND (at least two GND), numbered and listed in
  `BRINGUP.md`.

## Mechanical
- Board at most 50 x 40 mm, four M3 holes at the corners (3.2 mm, keepout 6 mm). Connectors on edges: power and
  motor on one edge, encoder and control header on the opposite edge.
- Silk: connector pin 1 marks, every connector labelled with its signals, polarity on the power input, revision.

## Stackup and fab
- **4 layers**, JLCPCB stock 4-layer stackup. Layer 2 solid GND under everything, layer 3 power pours (VIN, 5 V), no
  signal routing on layers 2 or 3 except short jogs that stay over the GND plane. 2 oz outer copper if the current
  calculation asks for it (then use the `JLCPCB-4L-2oz` rule pack).
- Net classes: `Default` 0.2 mm; `Power5V` and `VIN` sized for 4 A by IPC-2221 at 20 degC rise (state the width);
  motor outputs sized for 2.5 A; `Sense` for IPROPI; widths set by class, not by hand.
- Zero errors in KiCad DRC with parity, zero errors with the kicad-druid JLCPCB rule pack, ERC zero errors with every
  warning explained. All parts JLCPCB-assemblable with `MPN`, `Manufacturer`, `LCSC`, `Datasheet` fields filled.

## Deliverables
Same as rung 1: code as source of truth (Zener or SKiDL modules, one per subsystem: power_in, buck, ldo, driver,
connectors), the KiCad 10 project, ERC/DRC JSON, netlist, `fab/` package, `DESIGN_LOG.md` with every calculation,
`BRINGUP.md`, `progress.md`. Add `PINMAP.md` (the control-header table) and a `calcs/` directory with the
scripts that produced the numbers (buck ripple, trace widths, LDO dissipation, sense scaling).

## Review targets
Scored 1-10 on Electrical correctness, Manufacturability (fab, assembly, thermal, bring-up) and Documentation/intent.
Target 9/9/9. A 9 needs: every rail current path wide enough by the stated rule, the buck loop and thermal pad laid
out as the datasheet asks, the sense scaling correct at 3.3 V, the pin map matching the netlist, reverse-polarity
and back-feed considered, DRC/ERC/fab-rule clean, BOM fully sourced, bring-up steps with expected readings.
