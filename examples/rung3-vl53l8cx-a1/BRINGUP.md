# Bring-up: VL53L8CX Qwiic breakout

Nothing here has been run on hardware. Expected readings come from the datasheets and `DESIGN_LOG.md`.
Probe points: VIN J3.1, 3V3 TP2 or J3.2, 1V8 TP1, GND TP3 or J3.3, SYNC TP4 (all TPs on the back).

## Assembly notes

1. **Keep the protective liner on the sensor through reflow** (DS14161 sect 10.3: the liner is rated to 260 C and comes off just before the cover glass goes on). Do not remove it at the assembly house. It overhangs the module by 0.3 mm at the corner by the Rx lens.
2. Reflow is dry convection only, no vapour phase, recommended peak 240 C, maximum 260 C, maximum three passes (DS14161 sect 10.5, Table 22). No-wash flux: do not wash the board. The sensor is MSL 3: 168 h out of the bag, then bake 6 h at 90 C (sect 10.6.5). Maximum compression on the module 25 N.
3. J3 ships loose and is DNP in the CPL. Solder pins down so the plastic stays off the top side; pins up are also clear of the sensor cone (`DESIGN_LOG.md` section 5).

## First power, no host, liner on

Use a current-limited bench supply set to 200 mA.

| Step | Do | Expected |
|---|---|---|
| 1 | Unpowered, ohms from TP2 to TP3 and TP1 to TP3 | no short: above 1 kohm once the caps charge |
| 2 | 5.0 V into J3.1, GND on J3.3 | idle current below 10 mA: the sensor boots to LP or HP idle (CORE 3 mA typ, AVDD 1 mA typ in HP idle, Table 12), LED D1 1.3 mA |
| 3 | Measure TP2 | 3.27 to 3.33 V; D1 lit. Allowed by AVDD: 3.13 to 3.47 |
| 4 | Scope TP1 at power-on, single shot, trigger on TP2 rising | TP2 rises first; TP1 stays at 0 for 4.6 ms (3.0 to 6.5 with part tolerance), then rises. **Measure 0.9 V to 1.6 V: must be 63 us or less (DS14161 Fig 9).** Expected about 33 us with the 1.8 V LDO at its 80 us typ. Final value 1.80 V, limits 1.62 to 1.98 |
| 5 | Measure TP1 | 1.77 to 1.83 V |
| 6 | Measure J3.10 (INT), J3.9 (LPN) | INT 3.3 V through its 10k pull-up. LPN floats on the host side; the sensor pin is held at 1.8 V |
| 7 | Remove VIN. 3.3 V into J1 pin 2, GND pin 1. Measure J3.1 | below 0.1 V: the ideal diode is blocking. TP2 3.3 V |
| 8 | Keep Qwiic 3.3 V and add 5 V on VIN | TP2 stays 3.27 to 3.35 V; supply current in neither source negative |

A power cycle needs at least 50 ms off: the EN_1V8 RC holds its charge for about 9 ms, and a shorter dropout skips the delay in step 4.

## First register read

Connect a 3.3 V I2C host at 400 kHz or lower on J1. Leave J3 NCS, RST, LPN unconnected: straps hold I2C mode.

| Step | Do | Expected |
|---|---|---|
| 9 | I2C scan | one device at 7-bit **0x29** (the datasheet's 8-bit 0x52, write; 0x53, read) |
| 10 | ST ULD `vl53l8cx_is_alive()`: write 0x00 to register 0x7FFF, read 0x0000 and 0x0001, write 0x02 to 0x7FFF | **device id 0xF0, revision id 0x0C** (values from ST's published ULD driver, not DS14161; check against the UM3109 revision in use) |
| 11 | `vl53l8cx_init()` | firmware upload about 84 kB takes under 10 s at 400 kHz, status 0 |
| 12 | Remove the liner, then range 8 x 8 at 15 Hz at a white card 300 mm away | zone distances near 300 mm, target status 5 in most zones. AVDD total about 47 mA, 1V8 about 53 mA, board 215 mW sensor power (Table 13) |

If step 9 finds nothing: check TP1, then toggle J3.8 RST high and low (it resets the I2C interface only, DS14161 Table 3 note), then check that JP3 and JP4 still bridge pads 1-2.

## SPI

1. Cut JP3 and JP4 between pads 1 and 2, bridge pads 2 and 3.
2. Bridge JP5.
3. Power cycle. MOSI on J3.6, MCLK on J3.5, MISO on J3.4, NCS on J3.7. 3 MHz maximum, mode 3 (DS14161 sect 5, Table 8).

## Jumpers

| Ref | Shipped | Change |
|---|---|---|
| JP1 (top, by J2) | closed | cut to remove both 10k I2C pull-ups for a long Qwiic chain |
| JP2 | closed | cut to turn off D1 |
| JP3 | 1-2 closed, I2C | SPI above |
| JP4 | 1-2 closed, I2C | SPI above |
| JP5 | open | bridge for SPI |

Refs labelled on silk: J1, J2, J3, D1, JP1 to JP5, TP1 to TP4.
