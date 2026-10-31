# Bring-up: Qwiic 6-DoF IMU breakout (rung1-zener-a1, rev A)

Tools: DMM, 3.3 V bench supply with current limit, any I2C host at 3.3 V (Raspberry Pi, Arduino, Bus Pirate),
one Qwiic cable, optional scope. Test points: **TP2 = 3V3**, **TP1 = GND** (1.5 mm pads, top right, labelled);
the unpopulated header J3 (INT1 INT2 SDA SCL, bottom left) takes probe pins or a soldered header; GND for probes
is TP1 or the J1/J2 shell tabs.

Register map (LSM6DS3TR-C): WHO_AM_I 0x0F, CTRL1_XL 0x10, CTRL2_G 0x11, INT1_CTRL 0x0D, OUTX_L_G 0x22..0x27,
OUTX_L_XL 0x28..0x2D (little-endian int16).

1. **Visual.** U1's pin-1 dot must be at the top-left corner of the package (toward the "U1" label and the Y
   arrow). C1/C3 right of U1, C2 below it. JP1 (left, "6B | 6A") and JP2 (right, "I2C PU") show their factory
   copper bridges intact. Header J3 is empty (DNP).
2. **Rail resistance, unpowered.** DMM in ohms, black lead on TP1 (GND):
   - TP2 (3V3): starts low and climbs as the 10 uF charges, settles **> 1 MOhm** (OL on most meters). A steady
     reading below 10 kOhm means a short (check under U1 and the C1/C2/C3 pads).
   - J3 pin 3 (SDA) and pin 4 (SCL) to GND: **> 1 MOhm**.
   - J1 pin 1 (GND, outermost pad nearest the "IMU/Qwiic" corner) to TP1: **< 1 Ohm**.
3. **Pull-ups.** Red lead on TP2: J3 pin 3 (SDA) **2.2 kOhm +/-1 %**, J3 pin 4 (SCL) **2.2 kOhm**. OL means the
   JP2 link for that line is cut/open.
4. **Address strap.** JP1 centre pad (SA0) to TP2 (3V3): **< 1 Ohm** (bridged, 0x6B). To TP1: OL. (For 0x6A, cut
   the 1-2 bridge and solder 2-3; then the readings swap.)
5. **Power.** Bench supply 3.30 V, limit 20 mA, + on TP2, - on TP1 (or through a Qwiic cable). Expect
   **TP2 = 3.3 V +/-0.1 V** and supply current **< 1 mA** before configuration (power-down: ~6 uA plus leakage;
   after step 7 in normal mode about 0.6-0.9 mA, high-performance up to 1.25 mA). Current above 5 mA: stop,
   check U1 orientation.
6. **I2C scan.** Connect the host (Raspberry Pi: `i2cdetect -y 1`). Exactly one device at **0x6B** (0x6A after
   re-strapping JP1). Nothing found: check SDA/SCL swap on the cable and the pull-ups (step 3).
7. **WHO_AM_I.** Read register 0x0F: **0x6A**. A reply of 0x69 means a plain LSM6DS3 (not TR-C) was fitted;
   register map and axes are the same, WHO_AM_I and current differ. Any other value: bad part or bus.
   (`i2cget -y 1 0x6b 0x0f`)
8. **Enable sensors.** Write CTRL1_XL (0x10) = 0x60 (416 Hz, +/-2 g) and CTRL2_G (0x11) = 0x60 (416 Hz,
   250 dps). Current rises to about **0.9 mA**. (`i2cset -y 1 0x6b 0x10 0x60; i2cset -y 1 0x6b 0x11 0x60`)
9. **Accelerometer sanity, board flat on the bench, components up.** Read 0x28..0x2D as three int16:
   X ~ 0, Y ~ 0, **Z ~ +16400 LSB (+1.0 g at 0.061 mg/LSB)**, each +/-800 LSB. Stand the board on its edge so
   the silk **X arrow points up**: X ~ +16400. Stand it so the **Y arrow points up**: Y ~ +16400. Flip the board
   face-down: Z ~ -16400. Sign errors here mean the axis arrows on the silk do not match the datasheet.
10. **Gyro sanity.** Read 0x22..0x27 at rest: each **|value| < 300 LSB** (8.75 mdps/LSB, < ~3 dps). Rotate the
    board counter-clockwise about Z (looking down at the top): Z goes positive; back: negative.
11. **Interrupt pin.** Write INT1_CTRL (0x0D) = 0x01 (accelerometer data-ready on INT1). Scope on J3 pin 1
    (INT1) vs TP1: **3.3 V pulses at 416 Hz** that clear when the output registers are read. Repeat with
    INT2_CTRL (0x0E) = 0x01 on J3 pin 2.
12. **Daisy chain.** Plug a second Qwiic device into J2 (or a second copy of this board strapped to 0x6A).
    `i2cdetect` shows both. If a third board joins the chain, cut both JP2 links on all but one board and
    confirm step 3 reads OL on the cut boards and 2.2 k on the remaining one.
13. **Record.** Note WHO_AM_I, idle and active current, and the three +1 g readings on the board's bag label.
