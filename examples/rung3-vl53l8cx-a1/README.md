# VL53L8CX 8 x 8 Time-of-Flight Breakout, Qwiic

64-zone distance sensing to 4 m with a 45 x 45 degree field of view, up to 60 Hz. Plug into any 3.3 V Qwiic / STEMMA QT host. The ST VL53L8CX runs on 1.8 V logic and three supplies; this board makes the 1.8 V, sequences it the way the datasheet asks, and level-shifts all eight signal lines.

25.4 x 17.8 mm, two M2.5 holes, 4 layers, open hardware.

## Pinout: J3, 0.1 inch

| Pin | Name | Dir | Function |
|---|---|---|---|
| 1 | VIN | in | 3.3 to 5 V, to the on-board 3.3 V regulator |
| 2 | 3V3 | in/out | sensor rail, same net as Qwiic 3V3, 170 mA max load from this board |
| 3 | GND | | |
| 4 | MISO | out | SPI only, after bridging JP5 |
| 5 | SCL | in | I2C clock, SPI MCLK. 3.3 V level |
| 6 | SDA | in/out | I2C data, SPI MOSI. 3.3 V level |
| 7 | NCS | in | SPI chip select |
| 8 | RST | in | high pulse resets the I2C interface only. Leave open if unused. Full sensor reset is a power cycle (DS14161 Table 3 note) |
| 9 | LPN | in | low disables I2C in low-power mode. Open = enabled |
| 10 | INT | out | open-drain interrupt with a 10k pull-up to 3.3 V |

All logic on J3 and Qwiic is 3.3 V. Inputs tolerate 5 V, but a 5 V host will read SDA and INT high at only 3.3 V, so use a 3.3 V host. VIN is the only pin meant for 5 V. SYNC is on back pad TP4, 3.3 V side, with no pull-up on that side.

Qwiic J1 and J2: 1 GND, 2 3V3, 3 SDA, 4 SCL.

## I2C address

**0x29** (7-bit), 0x52 in ST's 8-bit notation. No strap: change it in software, using LPN to keep other sensors quiet. Host-side pull-ups are 10k, through JP1 on the top by J2: cut it once to remove both on a long chain. This board guarantees 400 kHz with 10k; 1 MHz needs stronger host pull-ups.

## Power

Two sources share the 3V3 rail: Qwiic 3V3, and VIN through the regulator and an ideal diode. Either or both are fine. VIN cannot be back-fed from Qwiic. With VIN on, this board powers the Qwiic connectors, so a host that is switched off on the same cable gets power on its 3V3 rail: disconnect it. The LED shows the rail; cut JP2 on the back to turn it off. Typical sensor power 215 mW while ranging.

## Cover glass

The board ships with ST's protective liner on the sensor: **peel it off before use**. If you put the board behind a window, the opening must be at least as wide as the 57.9 x 57.9 degree collector cones (DS14161 sect 2.2, Fig 28), and the glass affects crosstalk: see ST AN5897. The exclusion zone is on layer `User.1` of the KiCad board.

## I2C to SPI

Move JP3 and JP4 to pads 2-3, bridge JP5, power cycle. `BRINGUP.md` has the steps.

## Software

ST's VL53L8CX ULD driver (STSW-IMG040); user manual UM3109. Rev A has not been built or tested.
