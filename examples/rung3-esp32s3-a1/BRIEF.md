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

# Board brief: bare-chip ESP32-S3 devkit

Read `BRIEF-common.md` first. This board overrides it where stated. **No module:** the ESP32-S3 chip goes on the board with its own crystal, RF
match, antenna and power network. A WROOM or MINI module anywhere on this board fails the brief.

## Function
- **Chip:** ESP32-S3 in QFN56 with in-package flash (and PSRAM if a stocked variant has it), checked at LCSC, or a bare S3 with external quad flash if
  that is what is in stock; say which and why. Follow Espressif's *ESP32-S3 Hardware Design Guidelines* and the datasheet: fetch both into `docs/` first. Every
  requirement you use is cited by section: power pins and their decoupling, the VDD_SPI capacitor, VDD3P3 and the analog supply network, the 40 MHz crystal and
  its load caps (with the calculation from the crystal's CL), the EN RC delay, strapping pins, exposed-pad grounding.
- **RF:** a 2.4 GHz chip antenna or a printed antenna, your choice with the reason. A pi-match network between the chip's LNA_IN pin and the antenna, placed for tuning,
  with starting values and how a person would tune it in `BRINGUP.md`. 50 ohm feed on the JLC stackup you pick, with the stackup, trace width and gap calculation in the log.
  Antenna at the board edge, ground and copper keepout on **all** layers as the antenna's datasheet draws it. Ground-via fence along the feed. The GND planes stop at that
  keepout, which is the exception to the solid-plane rule. `edge_margin.skip_refs` may name the antenna.
- **USB:** USB-C receptacle on the native USB D+/D- pins, CC 5.1 k each, ESD protection, 90 ohm differential routing, as short and matched as the board allows, with the calculation.
  Flashing over native USB needs no USB-UART chip.
- **Power:** 5 V from USB to 3.3 V at 600 mA or more peak with a part that holds up under the Wi-Fi transmit burst; the worst-case drop and dissipation in the log. Bulk capacitance at the 3V3
  entry as the guidelines ask.
- **User:** RESET and BOOT buttons, a power LED, one user LED or addressable LED on a free GPIO, Qwiic connector on I2C.
- **Headers:** two 0.1 inch rows, 0.9 inch apart, breadboard-compatible, carrying the free GPIOs, 3V3, 5V, GND, EN, in a `PINMAP.md` that notes strapping pins, USB pins and input-only caveats.

## Mechanical
At most 60 x 26 mm, 4 layers, two M2.5 holes if they fit. Antenna on a short edge, USB on the opposite short edge.

## Review notes
This is the hardest board in the set. The reviewer checks the chip against the guidelines line by line. If a tool cannot do something here (controlled impedance, plane keepouts, length matching),
say what it could not do and how you got round it: that is a result, not a failure.
