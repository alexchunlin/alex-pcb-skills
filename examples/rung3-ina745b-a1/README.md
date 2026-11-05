# INA745B Power Monitor Breakout

Measures current, bus voltage, power, energy and charge on a rail up to 40 V, over I2C, with the shunt inside the chip. Bolt the rail to two M4 terminals, plug in Qwiic, read the numbers.
40 x 25.4 mm, four M2.5 holes. Open hardware, source in Zener and Python.

**Rated 25 A continuous at 40 C ambient in still air, 40 V.** That is this board's calculation, not the chip's 35 A headline; see DESIGN_LOG.md section 2. 33 mV drop at 25 A.
The rating is calculated, not yet measured on a built board.

| Spec | Value |
|---|---|
| Sensor | TI INA745B, 16-bit, 1.2 mA/LSB, 3.125 mV/LSB, full scale +/-39.32 A |
| Accuracy | gain +/-1.25 %, offset +/-62.5 mA max (B grade) |
| Bus | -0.1 to 40 V, high side or low side |
| Logic supply | VIN 3.3 to 5.5 V on the header, or 3.3 V on Qwiic |
| I2C | 0x40 default, 100 kHz; up to 2.94 MHz in the chip |

## Pinout
| Header J3 | Name | Function |
|---|---|---|
| 1 | VIN | 3.3 to 5.5 V in, through a diode and a 3.3 V regulator |
| 2 | 3V3 | Logic rail, same copper as Qwiic 3V3 |
| 3 | GND | Logic ground. **Must be common with the measured rail's return** |
| 4 | SCL | I2C clock |
| 5 | SDA | I2C data |
| 6 | ALERT | Open drain, active low, 10 k to 3V3. Do not pull above 3.6 V |

J1, J2: Qwiic / Stemma QT, 1 GND, 2 3V3, 3 SDA, 4 SCL. J4 IS+, J5 IS-: M4 screw terminals. TP1 GND, TP2 3V3, TP3 VBUS wire pad.

## I2C address
| JP4 (A1) | JP3 (A0) | Address |
|---|---|---|
| G | G | 0x40 (shipped) |
| G | V | 0x41 |
| V | G | 0x44 |
| V | V | 0x45 |
To move a strap, cut the link to G and bridge to V. Never leave a jumper open. A wire to SCL gives more addresses (TI table 6-2); SDA needs a 100 ns hold your host may not give.

## Jumpers
JP1: closed, VBUS senses IS+ (high side). Low side: cut it and wire your rail to TP3. JP2: cut both links to drop the 10 k pull-ups. JP5: cut to turn off the power LED.

## Wiring
High side: supply + to J4, load to J5, supply - to GND. Low side: load return to J4, J5 to supply -, cut JP1, supply + to TP3, GND to the same return as J5.
Use M4 ring lugs and 10 AWG (5 mm2) wire at 25 A. Keep logic ground connected whenever the board is powered (TI 8.3).
5 V hosts: SDA and SCL tolerate 5.5 V, but they idle at 3.3 V, so a host needing 3.5 V for a high needs a level shifter.
10 k pull-ups meet 400 kHz only to 35 pF. At 400 kHz, add a stronger host pull-up or run 100 kHz.

## First read
Register 0x3E reads 0x5449. BRINGUP.md has the full sequence with expected values.
