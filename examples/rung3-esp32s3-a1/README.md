# ESP32-S3 Devkit, rev A

An open-hardware ESP32-S3 board with no module: the chip, crystal, RF match, chip antenna and power all sit on a 60 x 26 mm four-layer board. Flash it over USB-C with nothing else attached. Two 0.1 inch rows, 0.9 inch apart, fit a breadboard.

| | |
|---|---|
| Chip | ESP32-S3FH4R2, dual LX7, 2.4 GHz Wi-Fi, Bluetooth LE |
| Memory | 4 MB flash, 2 MB PSRAM, in package |
| Power | USB-C or 5 V on J2.1, 3.3 V LDO, 800 mA rated |
| Antenna | Johanson 2450AT18D0100 ceramic, on the short edge |
| I2C | Qwiic on J4, SDA GPIO17, SCL GPIO18, 10 k pull-ups, cut JP2 to remove |
| Buttons | RST, BOOT |
| LEDs | Power (red, cut JP1), user on GPIO9 (yellow) |
| Free GPIO on headers | 35, plus 3V3, 5V, EN, 2 GND |

The ESP32-S3 has no fixed I2C address. Any device you add on Qwiic sets its own.

## Pinout
Pin 1 is at the USB end. Details and strapping notes are in `PINMAP.md`.

| Pin | J1 | J2 |
|---|---|---|
| 1 | 3V3 | 5V |
| 2 | GPIO18 SCL | GND |
| 3 | GPIO17 SDA | GPIO21 |
| 4 | GPIO16 | GPIO47 |
| 5 | GPIO15 | GPIO48 |
| 6 | GPIO14 | GPIO33 |
| 7 | GPIO13 | GPIO34 |
| 8 | GPIO12 | GPIO35 |
| 9 | GPIO11 | GPIO36 |
| 10 | GPIO10 | GPIO37 |
| 11 | GPIO8 | GPIO38 |
| 12 | GPIO7 | GPIO39 |
| 13 | GPIO6 | GPIO40 |
| 14 | GPIO5 | GPIO41 |
| 15 | GPIO4 | GPIO42 |
| 16 | GPIO3 strap | GPIO43 U0TXD |
| 17 | GPIO2 | GPIO44 U0RXD |
| 18 | GPIO1 | GPIO45 strap |
| 19 | GPIO0 BOOT strap | GPIO46 strap |
| 20 | EN | GND |

## First flash
Hold BOOT, tap RST, release BOOT, then `esptool.py --chip esp32s3 write_flash ...` over USB. `BRINGUP.md` has the full sequence and the RF tuning steps. The RF match is unproven until someone tunes one on a VNA.

Keep hands and metal away from the antenna end. Do not pull GPIO45 high at reset: the flash runs at 3.3 V and needs VDD_SPI there.

## Files
`esp32s3_devkit.zen` and `blocks/` are the source. `tools/regen.sh` rebuilds the KiCad project and `fab/`. `DESIGN_LOG.md` has every calculation.
