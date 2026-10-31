# Bring-up: Qwiic LSM6DS3TR-C breakout, rev A1

Equipment: bench multimeter, a 3.3 V I2C host with a Qwiic cable (e.g. any SparkFun/Adafruit Qwiic/STEMMA QT
board, or a Raspberry Pi with a Qwiic adapter), `i2cdetect`/`i2cget` or an Arduino sketch. No power supply beyond
the host: the board takes 3.3 V from the Qwiic cable only.

Test points and access (top side, see `fab/qwiic_imu_top.png`):

| Point | Where | Net |
|---|---|---|
| TP1 "3V3" | 1.5 mm square pad, top right | +3V3 |
| TP2 "GND" | 1.5 mm square pad, top right, next to TP1 | GND |
| J3 pin 1..4 (unpopulated 0.1" row, bottom left, labelled on silk) | INT1, INT2, SDA, SCL | |
| JP2 "ADDR" pads | left pad = +3V3, centre = SA0, right pad = GND | SA0 |
| JP1 "I2C PU" pads | centre = +3V3, outer pads = tops of R1 (SDA) / R2 (SCL) | PU_SDA, PU_SCL |
| J1 / J2 Qwiic pins, cable side to board side: GND, 3V3, SDA, SCL | | |

## 1. Visual (before any power)

1. Compare with `fab/qwiic_imu_top.png`: U1 pin-1 dot at the top-left corner of the package (toward JP1/R1),
   C1 and C3 to the right of U1, C2 below-left, R1/R2 above. J3 is empty (DNP).
2. JP2: the solder bridge is between the LEFT and CENTRE pads (marked "6B"). The right pad ("6A") is open.
3. JP1: both bridges present (left-centre and centre-right).
4. No solder balls between the LGA pads of U1 (0.15 mm gaps). Reflow defects here show up in step 3.

## 2. Resistance, unpowered (multimeter on ohms, red lead first)

| Step | Measure | Expect | If not |
|---|---|---|---|
| 2.1 | TP1 (+3V3) to TP2 (GND) | > 1 MOhm after the caps charge (reading climbs). Diode-test mode: ~0.6-1.0 V one way through U1's ESD structures, open the other. | < 100 Ohm: short; look at C1/C2/C3 and U1 pads 5/6/7/8. |
| 2.2 | J3 pin 3 (SDA) to TP1 | 2.2 kOhm +-1% (R1 through JP1) | open: R1 or JP1 bridge missing; ~0: short at R1 |
| 2.3 | J3 pin 4 (SCL) to TP1 | 2.2 kOhm +-1% (R2 through JP1) | same for R2 |
| 2.4 | J3 pin 3 (SDA) to J3 pin 4 (SCL) | 4.4 kOhm (two pull-ups in series via +3V3) | lower: SDA/SCL shorted |
| 2.5 | JP2 centre pad (SA0) to TP1 | 0 Ohm (bridge 1-2 closed, default 0x6B) | open: bridge missing, address floats |
| 2.6 | JP2 centre pad (SA0) to TP2 | open (> 1 MOhm) | 0 Ohm: 2-3 also bridged = 3V3-GND short through the jumper! Fix before power. |
| 2.7 | J1 pin 1 to J2 pin 1 (GND), J1 pin 2 to J2 pin 2 (3V3), pin 3-3, pin 4-4 | 0 Ohm each (daisy chain) | open: connector solder joint |
| 2.8 | J3 pin 1 (INT1) / pin 2 (INT2) to TP2 | > 100 kOhm (CMOS outputs, unpowered) | 0 Ohm: short to GND |

## 3. First power (host connected through J1 or J2)

| Step | Measure | Expect |
|---|---|---|
| 3.1 | Host 3.3 V rail current, board plugged in, idle (no driver) | < 1 mA above the host's own draw. LSM6DS3TR-C power-down current is ~3 uA; the only other paths are the pull-ups when a line is held low. |
| 3.2 | TP1 to TP2, DC | 3.3 V +-5 % (host rail). Below 3.0 V: cable/connector drop or a short. |
| 3.3 | SDA, SCL (J3 pins 3, 4) to GND, bus idle | 3.3 V (pulled up). 0 V: a line is held low; unplug and retest 2.4. |
| 3.4 | INT1, INT2 (J3 pins 1, 2) | 0 V at power-up (interrupts inactive, push-pull low by default) |

## 4. I2C scan and identity

| Step | Do | Expect |
|---|---|---|
| 4.1 | `i2cdetect -y 1` (Pi) or an I2C scanner sketch | one device at **0x6B** (default, JP2 1-2 bridged). With JP2 cut and 2-3 bridged: **0x6A**. Nothing found: check 3.3 and 2.5; two devices or random addresses: SA0 floating. |
| 4.2 | Read WHO_AM_I, register 0x0F: `i2cget -y 1 0x6b 0x0f` | **0x6A** (LSM6DS3TR-C). 0x69 means an LSM6DS3 (non-TR-C) was fitted; the same board works but driver IDs differ. |
| 4.3 | Scan with a second Qwiic board chained on the other connector | both addresses appear; the IMU still answers (daisy chain verified). |
| 4.4 | Bus timing (scope on SCL at 400 kHz, with one host and this board) | rise time (30-70 %) under 300 ns: 2.2 kOhm with ~100 pF gives ~190 ns. If a long chain pushes it past 300 ns, drop to 100 kHz or cut JP1 on the boards at the far end. |

## 5. Sensor data and axes

Use any LSM6DS3/LSM6DS3TR-C driver (SparkFun LSM6DS3, Adafruit LSM6DS, ST C driver); set the accelerometer to
+-2 g, 104 Hz (CTRL1_XL = 0x40) and the gyro to 245 dps, 104 Hz (CTRL2_G = 0x40).

| Step | Do | Expect |
|---|---|---|
| 5.1 | Board flat on the bench, top side up | accel Z = +1.0 g (+-0.1 g), X and Y = 0 +-0.1 g |
| 5.2 | Tilt so the silk **X** arrow (bottom right of the top silk) points at the ceiling | X = +1 g. The arrow points from J1 toward J2 (board right); the LGA pin-1 dot is at the top-left corner, matching datasheet Fig. 1. |
| 5.3 | Tilt so the silk **Y** arrow points at the ceiling | Y = +1 g. The arrow points toward the top edge (H1 side). |
| 5.4 | Rotate the board counter-clockwise (seen from the top) about Z | gyro Z positive |
| 5.5 | Gyro at rest | each axis within +-10 dps of zero (TR-C: +-10 dps offset max over temperature) |
| 5.6 | Tap the board | with the tap detection example, INT1 pulses high (J3 pin 1); confirms the interrupt route |

## 6. Optional: address change rework

1. Unplug power. Cut the trace between JP2 left and centre pads with a knife; measure JP2 centre to TP1: open.
2. Bridge centre and right pads with solder; measure JP2 centre to TP2: 0 Ohm.
3. Repeat 4.1: device at 0x6A.

## 7. Optional: remove the pull-ups (mid-chain boards)

Cut both JP1 bridges; 2.2 confirms open (> 1 MOhm from SDA/SCL to +3V3 on this board). The bus still needs
pull-ups somewhere, so leave them on at least one board or the host.
