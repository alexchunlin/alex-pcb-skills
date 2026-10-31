# Bring-up: Qwiic 6-DoF IMU breakout (qwiic_imu, rev A)

Tools: DMM, 3.3 V bench supply with current limit, a Qwiic cable or jumper wires, an I2C host (any Qwiic-capable
MCU board) running an I2C scan and a register read. Test points: **TP1 = 3V3**, **TP2 = GND** (round pads at the
lower left, silk `TP1` and `TP2`). The 1x4 header **J3** (silk `J3`, unpopulated) carries, left to right from the
square pad: INT1, INT2, SDA, SCL (silk names above and below the row). Solder jumpers: **JP1** (address, silk
`JP1 SA0`), **JP2** (SDA pull-up, silk `JP2 PU SDA`), **JP3** (SCL pull-up, silk `JP3 PU SCL`). The chip is **U1**.

1. **Visual.** Under magnification check U1 pin 1 (dot at the top left of the package, next to the X/Y arrows:
   X to the right, Y up), the two JST SH connectors seated square, no solder bridges on the U1 pads. JP1 must show
   pads 1-2 joined (as shipped), JP2 and JP3 must show their copper strip intact. J3 is unpopulated by design.
2. **Rail resistance, unpowered.** DMM from TP1 to TP2. Expected: not a short. A short reads below 10 ohm. A good
   board reads above 500 kohm once the 1 uF and the two 100 nF caps have charged (the reading climbs); the
   datasheet power-down current is 6 uA, so no steady low resistance is expected. TP2 to either connector's
   shell tab (the large side pads): below 1 ohm.
3. **Pull-ups.** DMM from TP1 to J3 pin 3 (SDA): 2.2 kohm +/-5% (2.2 kohm 1% part plus meter error). TP1 to J3 pin 4
   (SCL): 2.2 kohm +/-5%. Do this with JP2 and JP3 as shipped. (Cutting JP2 makes the SDA reading go open: that is
   the check that the jumper is the only path; reflow or re-bridge afterwards if the board is to stay a 2.2 kohm
   board.) The expected pull-up current at 3.3 V is 1.5 mA per line for this board alone.
4. **Address strap.** DMM continuity between JP1 pad 1 (3V3 side) and pad 2 (centre, SA0): below 1 ohm as shipped.
   JP1 pad 2 to pad 3 (GND side): open. SA0 high means 7-bit address 0x6B. To use 0x6A: cut the strip between pads
   1-2 and bridge pads 2-3 with solder.
5. **Power.** Supply 3.3 V, current limit 20 mA, to either Qwiic connector (pin 2 = 3V3, pin 1 = GND, check with
   the table in DESIGN_LOG.md) or to TP1 and TP2. Expected: supply stays at 3.3 V; current below 0.1 mA with the
   chip in its power-on power-down state (datasheet: 6 uA typical; the pull-ups draw nothing while both lines are
   high). A current above 2 mA before any I2C traffic means a fault: remove power and go back to step 2.
   With power on: TP1 to TP2 = 3.3 V +/-0.1 V; J3 pin 3 and pin 4 (SDA, SCL) = 3.3 V +/-0.1 V to TP2.
6. **Bus scan and WHO_AM_I.** Connect the host to a Qwiic connector. An I2C scan must show exactly one device at
   **0x6B** (JP1 as shipped) or **0x6A** (JP1 moved to 2-3). Read register 0x0F (WHO_AM_I) from that address:
   expected **0x6A** for the LSM6DS3TR-C. (The older LSM6DS3 returns 0x69; if you read 0x69 the part is not the
   -TR-C. The 0x6A figure is the one in the design brief; the datasheet copy in docs/ is the LSM6DS3 revision.)
   With a second board on the other connector (daisy chain) set one board to 0x6A and one to 0x6B and expect both.
7. **Function and axes.** Set CTRL1_XL (0x10) = 0x60 (accelerometer 416 Hz, +/-2 g) and read OUTX_L_XL..OUTZ_H_XL
   (0x28..0x2D, 0.061 mg/LSB). Board flat, component side up: Z = +1000 mg +/-100 mg, X and Y within +/-100 mg of
   zero (datasheet zero-g offset +/-40 mg typical). Tilt so the X arrow on the silk points up: X = +1000 mg
   +/-100 mg; tilt so the Y arrow points up: Y = +1000 mg +/-100 mg. Set CTRL2_G (0x11) = 0x60 and read OUTX_L_G..
   (0x22..0x27, 8.75 mdps/LSB at 250 dps): board at rest, each axis within +/-10 dps (datasheet zero-rate +/-10 dps).
8. **Interrupt header (optional).** Solder a header into J3, route INT1 to an input, enable the data-ready interrupt
   (INT1_CTRL = 0x01): J3 pin 1 pulses high at the ODR. INT2 likewise with INT2_CTRL (0x0E) = 0x01 on J3 pin 2.
