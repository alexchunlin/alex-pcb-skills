# Design brief, common to all rung-3 boards: a breakout you could sell

Each board is an open-hardware breakout or devkit of the kind Adafruit or SparkFun publish. The test is whether one designer pass
gets to a board a person would order. Your board's own brief adds the part and its circuit; this file holds what they share.

## Conventions
- **Fab and assembly:** JLCPCB, 4 layers, stock stackup, one-sided assembly (top) unless the board brief says otherwise. Every placed
  part has `MPN`, `Manufacturer`, `LCSC`, `Datasheet`, and is in stock at LCSC today; check, do not recall. Prefer JLC basic parts for
  passives. Part numbers are verified against the LCSC page or API, and the footprint against the manufacturer's drawing, with the pin 1
  and pad-count check in the log. A wrong footprint is the blocker this project has hit most often.
- **Stackup:** In1 and In2 are both solid GND planes. Power routed on the outer layers, ground fill on the outer layers wherever nothing
  else is, signals only over unbroken ground.
- **Header:** 0.1 inch, breadboard-compatible, every pin labelled on silk on both sides of the board where room allows. Headers are
  through-hole, shipped loose (DNP in the CPL).
- **I2C parts:** two Qwiic / Stemma QT JST-SH 4-pin connectors on opposite edges (GND, 3V3, SDA, SCL, pin 1 GND), 10 k pull-ups on a
  solder-jumper you can cut, address strap on a solder jumper if the part has one. Interrupt or data-ready pins reach the header.
- **Power:** VIN 3.3 to 5 V on the header with a 3.3 V LDO if the part cannot take 5 V, and the Qwiic 3V3 feeding the same rail with no
  back-feed fault. Say how the two sources coexist. Power LED with a cut jumper to disable it. If the sensor needs a low-noise analog
  supply, the LDO choice and its PSRR at the noise band go in the log.
- **Mechanical:** 25.4 x 25.4 mm or smaller, unless the board brief says otherwise. Two or four M2.5 holes. Rounded corners 1.5 mm. Connector
  faces flush at the board edge. Silk: product name, rev, pin 1 marks, polarity. No silk on pads.
- **Datasheet layout first:** the part's own land pattern, keepouts and layout notes are requirements: cite the section for each one in
  `DESIGN_LOG.md` (aperture, port hole, exposed pad, analog ground, thermal relief, no copper under). If a note conflicts with a rule below, say so
  and pick the datasheet, with the reason.

## Rules
- Lay it out block by block (PATH.md points at the procedure).
- No via in an SMD pad (exposed pads named in `thermal_vias` or `via_in_pad.allow` are the exception). Copper and parts 1 mm off the outline,
  connectors and castellations excepted. Ground fill islands get a via rather than being left to KiCad's removal.
- `checks.json` from the template, filled at the plan checkpoint with the brief's numbers: `policy`, `rails`, `decoupling`, `buses`, `connectors`,
  `test_points`, `via_in_pad`, `edge_margin`, `gnd_islands`, `refplane`, `return_via`, `signals`. Never lower a number to make a tool read 0.

## Deliverables
Code as source of truth (Zener modules, one per block), the KiCad 10 project, ERC/DRC JSON, netlist, `fab/` package, `DESIGN_LOG.md` with every
calculation and citation, `BRINGUP.md` (first power, what to measure, the first register read with its expected value), a one-page `README.md` as the
product page (pinout table, I2C address, what it does), `progress.md`, `SUMMARY.md`, `blocks.json` and its report. Regeneration proved with `pcb regen-check`.

## Review targets
Scored 1-10 on Electrical correctness, Manufacturability and Documentation/intent. Target 9/9/9. A 9 needs ERC, DRC and fab rules clean, every datasheet layout
requirement met and cited, every part verified in stock on a checked footprint, bring-up steps with expected readings, and a board a person would order.
Do not order anything.

# Board brief: VL53L8CX 8 x 8 multizone time-of-flight

Read `BRIEF-common.md` first. Part: ST VL53L8CXV0GC/1, LGA-16 6.4 x 3.0 mm, 0.75 mm pitch, LCSC C7386355 (917 in stock on 2026-11-04; re-check). Datasheet: https://datasheet.lcsc.com/datasheet/pdf/7f4bc14e797e6799c474b8931a563702.pdf?productCode=C7386355 (ST's copy timed out). Near products are SparkFun's VL53L5CX and Adafruit's VL53L1X, VL53L4CD and VL53L4CX.

- **Function:** a Qwiic breakout for a 3.3 V host, also usable from 5 V on VIN. I2C by default, with SPI reachable on the header if the pins allow it (solder jumpers), reset, LPn and INT on the header.
- **Power:** three domains. AVDD 3.3 V, CORE_1V8 1.8 V, IOVDD 1.2 or 1.8 V only. A 1.8 V LDO and a 3.3 V to 1.8 V bidirectional level shifter are required; stocked candidates are TLV75518 C2877863 and PCA9306 C123752, re-check them. Power-up order and the datasheet's sequencing rules go in the log with how the circuit meets them.
- **Layout:** the optical exclusion zone is clear of parts, silk, and anything taller than the datasheet allows, on the board's top edge or centre, drawn on `User.1` from the datasheet's figure. Reserved pins to ground as the datasheet says, thermal pad soldered and tied to ground with its vias outside the pad's paste openings as the datasheet says.
- **Assembly:** the protective liner stays on through reflow. Note the step in `BRINGUP.md`.
- **Size:** at most 25.4 x 17.8 mm plus connectors. A cover-glass note in `README.md` if the datasheet has one.
