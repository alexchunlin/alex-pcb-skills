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

# Board brief: IM73D122 IP57 digital MEMS microphone

Read `BRIEF-common.md` first. Part: Infineon IM73D122V01XTMA1, LLGA-5 4 x 3 mm, 0.7 mm pitch, LCSC C5563886 (2,618 in stock on 2026-11-04; re-check). Datasheet: https://datasheet.lcsc.com/datasheet/pdf/7dd43900195f2e2d40f82de2a9982909.pdf?productCode=C5563886 . Near products are Adafruit's PDM mics #3492 and #4346.

- **Function:** PDM microphone breakout for far-field pickup. PDM, so no Qwiic and no I2C: this overrides the common I2C section. Header: 3V3, GND, CLK, DATA, SEL (left/right strap on a solder jumper). VIN 3.3 to 5 V with a low-noise LDO, or 1.62 to 3.6 V direct, your choice with the reason, and the supply noise against the mic's PSRR in the log.
- **Layout:** the board's point. A 0.8 mm non-plated port hole through the board inside the copper ring the datasheet draws (Fig 13: mask R0.58, copper R1.04). Pads are solder-mask defined, so build the footprint from the figure and check the mask openings on the rendered gerber, not just the pads. The port is keepout for every copper layer and the two ground planes pull back from it with the datasheet's clearance. A CLK and DATA route that keeps the 3 MHz clock off the mic's supply.
- **Assembly:** the sound port must survive reflow and JLC's cleaning. Say what you found about wash and what the bring-up step is. Note it as an open question in `SUMMARY.md` if you cannot settle it.
- **Size:** at most 25.4 x 17.8 mm.
