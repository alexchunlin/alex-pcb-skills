# Bring-up: Qwiic 6-DoF IMU (LSM6DS3TR-C), rev A

Tools: DMM, 3.3 V bench supply or a Qwiic host (SparkFun RedBoard / Arduino with Qwiic cable), I2C scanner sketch.
Board origin for positions below: top-left corner of the 25.4 x 25.4 mm board, x right, y down, mm.

Test points and pins (all on the top side):
- **TP2 = 3V3** pad D1.5 at (3.5, 4.5). **TP1 = GND** pad D1.5 at (3.5, 7.5).
- **J3** 0.1" header (not populated), pins left to right at y = 23.5: 1 INT1 (x 1.8), 2 INT2 (4.34), 3 SDA (6.88), 4 SCL (9.42).
- **J1** (top) and **J2** (bottom) Qwiic JST SH: pin 1 GND, 2 3V3, 3 SDA, 4 SCL (pin 1 is the right pad on J1, the left pad on J2, as the Qwiic cable key dictates).
- **JP1** address jumper (3 pads, below U1): pad 1 = 3V3 (right, triangle mark), pad 2 = SA0 (middle), pad 3 = GND (left). Shipped 1-2 bridged.
- **JP2 / JP3** (right edge): SDA / SCL pull-up jumpers, 2 pads, shipped bridged.

1. **Visual.** U1 pin-1 dot at the bottom-left corner of the LGA (towards JP1). C1, C3 above/right of U1, C2 right of U1. JP1 bridge between the middle and right pads; JP2 and JP3 bridged. J3 empty. Both JST openings face outward.
2. **Rail resistance, unpowered.** TP2 (3V3) to TP1 (GND): expected > 100 kOhm after the 1 uF charges (meter reads rising); a solder short reads < 5 Ohm. SDA (J3.3) to GND and SCL (J3.4) to GND: > 100 kOhm.
3. **Pull-ups.** J3.3 (SDA) to TP2: 2.2 kOhm +-1 %. J3.4 (SCL) to TP2: 2.2 kOhm +-1 %. Cut JP2 or JP3 and the reading goes open (> 1 MOhm).
4. **Address strap.** JP1 middle pad (SA0) to TP2: < 1 Ohm (bridged 1-2, address 0x6B). JP1 middle pad to TP1: open. For 0x6A cut the 1-2 bridge and solder 2-3; then middle pad to TP1 reads < 1 Ohm.
5. **Power.** 3.3 V on J1 (or TP2 vs TP1), current limit 20 mA. Expected: < 0.1 mA at power-up (device in power-down, datasheet IddPD 3 uA typ, plus pull-up leakage), 0.9 mA typ with accel + gyro in high-performance mode (IddHP), 0.45 mA in normal mode. More than 5 mA = stop, check for a short between 3V3 and GND around C1/C2/C3.
6. **Bus scan / WHO_AM_I.** I2C scan at 100 kHz finds exactly one device at 0x6B (0x6A if JP1 is set 2-3). Read register 0x0F (WHO_AM_I): expected **0x6A** (datasheet Table 49). Any other value or NAK: check SDA/SCL continuity J1 pin 3/4 to U1 pins 14/13 and that CS (U1 pin 12) is at 3.3 V.
7. **Function.** Write CTRL1_XL (0x10) = 0x60 (accel 416 Hz, +-2 g) and CTRL2_G (0x11) = 0x60 (gyro 416 Hz, 250 dps). Board flat on the bench, components up: OUTZ_A (0x2C/0x2D) = +16384 +-1600 LSB (+1 g at 0.061 mg/LSB), OUTX_A and OUTY_A = 0 +-650 LSB (+-40 mg). Tilt the board so the silk **X** arrow points up: OUTX_A = +16384 +-1600. Silk **Y** arrow up: OUTY_A = +16384 +-1600. Gyro at rest: all three OUT*_G within +-1200 LSB (+-10 dps at 8.75 mdps/LSB). Rotate the board around the Z axis counter-clockwise seen from above: OUTZ_G positive.
8. **Interrupts (optional, populate J3).** Set INT1_CTRL (0x0D) = 0x01 (accel data-ready on INT1): J3.1 toggles at 416 Hz. INT2_CTRL (0x0E) = 0x02: J3.2 toggles at the gyro rate.
9. **Daisy chain.** Plug a second Qwiic device into J2: the scan shows both addresses; with two of these boards on one bus cut JP2/JP3 on one of them (two 2.2 kOhm pull-ups in parallel sink 3.0 mA, the I2C limit).
