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
