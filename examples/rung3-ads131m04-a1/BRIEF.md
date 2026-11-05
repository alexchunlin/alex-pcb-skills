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

# Board brief: ADS131M04 four-channel simultaneous 24-bit ADC

Read `BRIEF-common.md` first. Part: TI ADS131M04IPWR, TSSOP-20, 0.65 mm pitch, LCSC C2862562 (1,074 in stock on 2026-11-04; re-check). Datasheet: https://www.ti.com/lit/ds/symlink/ads131m04.pdf . Near products are Adafruit's ADS122C04 and NAU7802, and SparkFun's ADS1219.

- **Function:** four simultaneous differential channels to 64 kSPS for vibration, power or sensor logging. SPI, so no Qwiic: this overrides the common I2C section. Header carries SPI, DRDY, SYNC/RESET, power. Inputs on a 3.5 mm screw terminal block or a second 0.1 inch header, your choice with the reason.
- **Clock:** an 8.192 MHz CMOS oscillator is required, the M04 has no crystal pins. Stocked candidate C7425393, re-check. Keep the clock clean and short and away from the inputs.
- **Analog:** AVDD and DVDD 2.7 to 3.6 V. Decoupling per the datasheet (1 uF each, 220 nF on CAP), C0G input caps, an input RC anti-alias filter per channel with the corner frequency calculated from a chosen data rate. The AVDD source's noise against the ADC's input-referred noise in the log. VIN 3.3 to 5 V with a low-noise LDO.
- **Ground:** the datasheet's ground advice against this project's two solid planes is the question here. Read it, decide, cite it. Digital traces stay off the analog input area on every layer. Show the separation with a `refplane` result and an `exposure` row with the SPI clock and the oscillator as aggressors.
- **Size:** at most 40 x 25.4 mm.
