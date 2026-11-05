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

# Board brief: INA745B 35 A digital power monitor

Read `BRIEF-common.md` first. Part: TI INA745BIRELR, VQFN-14 3 x 5 mm, 0.6 mm pitch, LCSC C35213810 (13,165 in stock on 2026-11-04; re-check). No shunt to choose: the sense element is
in the package. Datasheet: https://www.ti.com/lit/ds/symlink/ina745b.pdf . Near products on the market are the INA228 and INA238 breakouts, with an external shunt.

- **Function:** high-side or low-side power and energy monitor over I2C, bus up to 40 V. Qwiic, header, alert pin on the header, A0/A1 address straps on solder jumpers giving at least four addresses.
- **Current path:** this board's point. IS+ and IS- sit on the package's short edges, so the current funnels into a 3 mm edge past 0.6 mm signal pads. Two screw terminals or large plated pads on opposite edges, the path between them as pours on as many layers as the calculation asks. This overrides the common stackup: the high-current path may cut the outer ground fill, and the inner planes may give way under it if the calculation needs them, with the reason in the log. The part senses internally, so no Kelvin tracks are needed, but the signal pads and their tracks must stay clear of the current path's heat and field.
- **Rating:** state the board's continuous current rating from your own numbers (track and pour temperature rise, via count, terminal rating, the datasheet's current-vs-temperature limit), not the part's headline 35 A. Run `pcb irdrop` on the path. 2 oz outer copper is allowed if you use the matching rule pack.
- **Size:** up to 40 x 25.4 mm if the terminals need it.
- **Logic:** VS at 3.3 V from the Qwiic or header rail. If bus voltage reaches 40 V, spell out the creepage between the bus copper and the logic side for that voltage.
