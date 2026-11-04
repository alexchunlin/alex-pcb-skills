# Board brief: VL53L8CX 8 x 8 multizone time-of-flight

Read `BRIEF-common.md` first. Part: ST VL53L8CXV0GC/1, LGA-16 6.4 x 3.0 mm, 0.75 mm pitch, LCSC C7386355 (917 in stock on 2026-11-04; re-check). Datasheet: https://datasheet.lcsc.com/datasheet/pdf/7f4bc14e797e6799c474b8931a563702.pdf?productCode=C7386355 (ST's copy timed out). Near products are SparkFun's VL53L5CX and Adafruit's VL53L1X, VL53L4CD and VL53L4CX.

- **Function:** a Qwiic breakout for a 3.3 V host, also usable from 5 V on VIN. I2C by default, with SPI reachable on the header if the pins allow it (solder jumpers), reset, LPn and INT on the header.
- **Power:** three domains. AVDD 3.3 V, CORE_1V8 1.8 V, IOVDD 1.2 or 1.8 V only. A 1.8 V LDO and a 3.3 V to 1.8 V bidirectional level shifter are required; stocked candidates are TLV75518 C2877863 and PCA9306 C123752, re-check them. Power-up order and the datasheet's sequencing rules go in the log with how the circuit meets them.
- **Layout:** the optical exclusion zone is clear of parts, silk, and anything taller than the datasheet allows, on the board's top edge or centre, drawn on `User.1` from the datasheet's figure. Reserved pins to ground as the datasheet says, thermal pad soldered and tied to ground with its vias outside the pad's paste openings as the datasheet says.
- **Assembly:** the protective liner stays on through reflow. Note the step in `BRINGUP.md`.
- **Size:** at most 25.4 x 17.8 mm plus connectors. A cover-glass note in `README.md` if the datasheet has one.
