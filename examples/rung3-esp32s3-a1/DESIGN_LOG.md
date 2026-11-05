# Design log: r3-esp32s3-a1, bare-chip ESP32-S3 devkit, rev A

Sources in `docs/`: `esp32-s3_datasheet_en.pdf` (DS, v2.2), `esp32-s3_hardware_design_guidelines_en.pdf` (HDG, master), `ant_2450AT18D0100E.pdf` (Johanson, ver 4.4), `sgm2212.pdf`, `fa238.pdf`, `skrpace.pdf`, `usblc6.pdf`, `type-c-31-m-12.pdf`, `b5819w.pdf`, `sm04b.pdf`. Part numbers and stock: `docs/parts_verified.tsv`, read from the LCSC API on 2026-11-04. Numbers below come from `pcb q`, `pcb check` rows, or `tools/z0.py`; `calcs:` names a row in `checks.json`.

## 1. Plan

### Chip and memory
ESP32-S3FH4R2, C3013940, LCSC stock 1248 at check time: 4 MB flash and 2 MB PSRAM in package, quad SPI, VDD_SPI 3.3 V, -40 to 85 C (DS table 1-1). Chosen over S3FN8 (C2913196, 8 MB flash, no PSRAM) because the brief asks for PSRAM if a stocked part has it, and over S3R8 (C2913194, no flash, octal PSRAM takes GPIO33 to 37). Quad flash keeps GPIO33 to 37 free (HDG 1.3.1). This variant has the larger EPAD, 5.6/5.7/5.8 mm (DS fig 7-2).

### Rails and budget
| Rail | Source | Budget | Note |
|---|---|---|---|
| VBUS | J3 | 650 mA | USB 4.75 to 5.25 V; USBLC6 VBUS clamp, C1 1 uF |
| 5V | D1 from VBUS, or J2.1 | 650 mA | D1 stops a 5 V header supply back-feeding the USB host |
| 3V3 | U2 SGM2212-3.3 | 496 mA peak (`calcs:i_3v3_peak_a`) | S3 340 mA 802.11b TX peak (DS table 5-7), Qwiic 100 mA, LEDs 6 mA, 50 mA margin |
| VDD3P3 | L1 from 3V3 | 350 mA | pins 2, 3, analog domain |
| VDD_SPI | U1 pin 29 output | in-package memory only | 3.3 V through RSPI from VDD3P3_RTC (HDG 1.3.2 table 1) |

**Source coexistence.** VBUS and a 5 V supply on J2.1 meet at D1's cathode: the higher one wins and D1 blocks current into USB. The Qwiic 3V3 on J4 and J1.1 is an output of U2. No back-feed fault exists while the board powers itself. Feeding 3V3 into J1.1 or J4 from outside with no 5 V drives U2's output; the SGM2212 datasheet has no statement on reverse current, so the bring-up only does this current-limited.

### Regulator
Espressif asks for 500 mA or more on a single supply (HDG 1.3.2); the brief asks for 600 mA peak. SGM2212-3.3 is rated 800 mA, limit 810 mA min, dropout 240 mV typ, 280 mV max at 500 mA, 390 mV typ at 800 mA (SGM2212 electrical table).
- Worst-case headroom: 4.75 V USB - 0.05 V cable and trace - 0.5 V D1 = 4.20 V in; 0.90 V above 3.3 V (`calcs:vin_ldo_min`, `headroom_min`), three times the 0.28 V dropout.
- Worst-case dissipation: (5.25 - 0.35 - 3.3) V x 0.6 A = 0.96 W (`calcs:p_ldo_burst`).
- Package: theta_ja 56 K/W in TO-252-2 gives Tj 93.8 C at 40 C ambient (`calcs:tj_ldo_burst`). SOT-223-3 is 117 K/W and gives 152.3 C (`calcs:tj_sot223_rejected`), above the 125 C limit. So TO-252-2, C5152863, stock 2374.
- Bulk: C3 10 uF at the 3V3 entrance, C4 10 uF at VDD3P3, 20 uF nominal (HDG 1.3.2). SGM2212 asks for 1 to 10 uF effective on COUT; 10 V X5R 0603 parts at 3.3 V bias read about half nominal, so about 10 uF effective. Check this against the Samsung bias curve; it is an estimate.
- PSRR: 80 dB at 120 Hz (SGM2212). No low-noise analog sensor on this board.

### Crystal
Epson X1E0000210177 (FA-238), 40 MHz, CL 9 pF, +/-10 ppm at room temperature, ESR 40 ohm, -40 to 85 C (LCSC attributes C255943). HDG 1.3.5 asks for 40 MHz within +/-10 ppm. Load caps: CL = C/2 + Cstray, Cstray estimated 2.5 pF, C = 13 pF; 12 pF E24 gives 8.5 pF (`calcs:xtal_cl`). Series L2 24 nH on XTAL_P near the chip, as HDG 1.3.5 suggests. Tune against the frequency offset in BRINGUP.md. The FA-238 sheet lists temperature stability only in generic form; LCSC lists no over-temperature figure for this part, so total accuracy over temperature is unverified.

### Stackup and impedance
JLC04161H-7628: F.Cu 35 um, prepreg 7628 0.2104 mm, er 4.4 to In1 (`tools/z0.py`). The 0.2104 mm and er figures are from memory of JLC's stack table, not fetched here: confirm in JLC's calculator before ordering.
- RF: CPWG on In1, w 0.32 mm, gap 0.25 mm (the F.Cu zone clearance): 49.7 ohm, interpolated between the w 0.30 and 0.34 rows at gap 0.25 (`calcs:z_rf_ohm`). Plain microstrip at the same width is 52.9 ohm. Where fill does not reach the track, the impedance sits between those two.
- USB: edge-coupled microstrip w 0.28, s 0.20: Z0 56.5, Zdiff 91.2 ohm (IPC-2141 form, `calcs:z_usb_ohm`), inside 90 +/-10 % (HDG 1.4.8).
- KiCad has no headless impedance check. The numbers are hand calculation, the geometry is enforced only by the layout script and `pcb q net`. No field solver was run.

### Antenna
Johanson 2450AT18D0100E, C2917718, stock 1644: 3.2 x 1.6 mm, edge mount, 72 % efficiency on a 40 x 20 mm board (Johanson p1, p2). Chosen over a printed antenna because Johanson gives a land pattern and a ground clearance of only 4.0 x 6.0 mm that fits this board, while a printed MIFA needs simulation (HDG 1.4.4) and more area. Fed from the right, Mounting Considerations 4, p6: terminal 4 FEED, terminals 1, 2, 3 GND (p1 table, function 2).
- Lands 1.0 x 0.6 mm, columns 2.0 mm apart inside, rows 0.7 mm apart inside (p6). Footprint `parts/footprints/ANT_Johanson_2450AT18D0100.kicad_mod` drawn from that page, 4 pads, terminal numbers checked against the p1 top view.
- Keepout 4.0 x 6.0 mm on all four layers: x 153.6 to 160, y 111 to 115. **Deviation:** the lands sit 0.4 mm in from the edge, not flush as drawn, because 0.4 mm is the board copper-to-edge setup. The clearance runs 6.4 mm deep to keep the drawn 6.0 mm behind the lands. Expect a small detune; the match has room for it.
- Audit: `tools/keepout.py` finds no fill at the keepout centre on F.Cu, In1, In2, B.Cu; the only copper inside is RF2 into terminal 4 and the two GND tabs into terminals 2 and 3, lands the datasheet puts there. KiCad rule areas (`ANT_KEEPOUT_*`) make DRC enforce it.

### RF network (HDG 1.3.6, fig 7, table 6; 1.4.4)
Chip CLC: C20 1.5 pF shunt, L3 2.7 nH series, C21 1.5 pF shunt, mid-range of table 6 (1.2 to 1.8 pF, 2.0 to 3.0 nH). Antenna CLC: C22 DNP, R12 0 ohm, C23 DNP, at the antenna (HDG 1.4.4). C20 and C21 sit on opposite sides of the trace, the zigzag HDG asks for.
- **0402, not 0201.** HDG 1.3.6 says 0201; HDG 1.4.4 notes no stub is needed for 0402 and above. 0402 is chosen so a person can rework the match, the brief's "placed for tuning". No stub on C20.
- Feed lengths: LNA_IN 4.80 mm, RF1 4.21 mm, RF2 6.43 mm, about 15 mm pin to land, no vias (`pcb q net`). At about 0.04 dB/mm on FR4 that is 0.6 dB, an estimate. The chip sits west of the antenna to clear the east-side fan-out; see section 2.
- Via fence along the feed at 1.2 mm nominal pitch, both sides.
- Antenna ESD (HDG 1.3.6, D2 NC in fig 1): not fitted and no footprint. The ceramic body has no exposed conductor at the user side and a shunt pad on the feed adds capacitance. Open item.

### USB (HDG 1.3.13, 1.4.8)
HRO TYPE-C-31-M-12, C165948, stock 142990. CC1, CC2 5.1 k to GND. USBLC6-2SC6 (ST, C7519) at the connector. 22 ohm R5, R6 near the chip. Shunt caps C18, C19 reserved DNP. **Deviation:** C18 and C19 sit about 15 mm from the chip on the connector side of the series resistors, near x 120, because the header bands take the space near R5, R6. They are unpopulated by default.
- Lengths: D+ 35.34 + 5.35 = 40.69 mm, D- 35.65 + 5.86 = 41.51 mm, 0.82 mm mismatch (`pcb q net`); 22 ps, small against a 4 ns FS edge. Each net has 2 vias: the 16-pin connector forces a crossing, D+ A6 and D- A7 hop on B.Cu. GND vias at (111.4, 115.5) and (110.65, 117.2) (HDG 1.4.8).
- Length matching was done by routing the pair together, then measured; no tool enforces it.

### Power pins (HDG 1.3.2, 1.4.2; fig 1)
| Pin | Caps | Distance centre to pin |
|---|---|---|
| 2, 3 VDD3P3 | C4 10 uF, C5 1 uF, C6 100 nF, L1 2.0 nH 900 mA, C7 100 nF | C7 1.57, 1.58 mm |
| 55, 56 VDDA | C9 1 uF, C10 10 nF | C9 1.46, C10 1.22 mm |
| 46 VDD3P3_CPU | C11 100 nF | 2.83 mm |
| 20 VDD3P3_RTC | C12 100 nF | 4.55 mm |
| 29 VDD_SPI | C13 100 nF, C14 1 uF | 1.88, 2.18 mm |
| 3V3 entrance | C3 10 uF, D2 ESD (HDG 1.3.2) | |

Main 3V3 trace 0.65 mm, over 25 mil, two vias at the layer change (HDG 1.4.2). VDD3P3 row 0.5 mm, 20 mil, necking to 0.2 mm into the 0.4 mm pitch pins. Power runs on B.Cu, because In1 and In2 are both ground by the brief; HDG prefers an inner power layer. The brief's stackup wins.
**Deviations:** HDG asks for caps close to the pins and a 10 uF per VDD3P3 pin in one sentence, one shared in fig 1; fig 1 is followed. C12 at 4.55 mm and C11 at 2.83 mm are far for a decoupling cap; the 0.4 mm pitch signals on both sides leave no way out for a via or a cap, so the pin runs north as a 0.2 mm trace first. Limits 4.6 and 3.3 mm in `checks.json` are the measured layout, not a design target. A reviewer should treat them as weak spots.

### Reset, straps (HDG 1.3.3, 1.3.9; DS section 3)
CHIP_PU: R2 10 k, C17 1 uF, tau 10 ms (`calcs:en_tau_ms`) against tSTBL 50 us. GPIO0 pull-up R3 10 k, no capacitor on it. GPIO45 and GPIO46 have no external parts, weak pull-downs hold them low. GPIO3 floats. U0TXD R4 499 ohm (HDG 1.3.7). In-package flash pins left open (DS section 2.6).

### EPAD (HDG 1.4.2, DS fig 7-2)
KiCad QFN-56-1EP_7x7mm_P0.4mm_EP5.6x5.6mm: 56 pads, 0.4 pitch, pad 1 at (-3.4375, -2.6), EP 5.6 mm, inside the 5.6 to 5.8 range. 9 GND vias on the gaps of the 4 x 4 paste grid (`thermal_vias:U1` pass, 9 of 9). At 0.6 mm they overlap the corners of the paste windows by up to 0.165 mm; the HDG wants them in the gaps. Via fill is not specified in this package.

### Bus
I2C: GPIO17 SDA, GPIO18 SCL; R9, R10 10 k on JP2, cut to remove. 0.33 mA sink at 3.3 V (`calcs:ipullup_ma`). Rise time 0.85 RC: at 10 k, the 1 us standard-mode limit is reached at 118 pF and the 300 ns fast-mode limit at 35 pF. A long Qwiic chain or 400 kHz wants a stronger external pull-up. No device on the board, so no address row.

### Connector and jumper maps
`PINMAP.md`, mirrored in `checks.json` `connectors`, `jumpers`, `pinmaps`. J4: 1 GND, 2 3V3, 3 GPIO17, 4 GPIO18. JP1 cut disables the power LED. JP2 bridged 1-2-3.

### Footprint checks
| Part | Footprint source | Pads, pin 1 check |
|---|---|---|
| U1 | KiCad QFN-56 EP5.6 | 57 pads; pin order DS fig 2-1; symbol stock MCU_Espressif, pin names compared to DS table 2-1 |
| J5 | drawn from Johanson p1, p2, p6 | 4; terminal 4 feed lands at (158.0, 114.5) by `orient_pads` |
| U2 | KiCad TO-252-2 | 3; pin 1 GND, 2 tab VOUT, 3 VIN, SGM2212 pin configuration figure |
| U3 | KiCad SOT-23-6 | 6; pin 1 by USBLC6 sheet |
| J3 | KiCad HRO TYPE-C-31-M-12 | 16 + 4 shell; courtyard trimmed to pads + 0.05 |
| J4 | rung-1 JST footprint | 4 + 2 MP; courtyard trimmed |
| Y1 | KiCad Crystal 3225-4 | 4; 1 and 3 crystal, 2 and 4 GND |
| SW1, SW2 | drawn from Alps SKRP page 2 | 4; 1-2 and 3-4 tied in the part |
| J1, J2 | KiCad 1x20 | 20; F.Silk outline removed, courtyard trimmed to 1.0 mm because the plastic sits on the bottom on a breadboard |
| H1, H2 | rung-1 M2.5 | courtyard cut from 2.95 to 1.85 mm radius; a 4.5 mm screw head at H1 clears the J2.4 pad by 0.45 mm |
| D1, D2, LED | KiCad SOD-123, SOD-323, 0603 | pad 1 K |

Antenna reference is J5, not E1: `pcb block gate` exempts only J, H, MH, FID references from the 1 mm rule and ignores `edge_margin.skip_refs`.

### Floor plan
USB and Qwiic at the west edge, antenna at the east edge. U2 between the USB entry and the chip. Chip at (142, 114), rotated 180 degrees so LNA_IN faces the antenna and the VDD3P3 network sits next to it. Headers 22.86 mm apart. Crystal SE of the chip. H1 (111.8, 120.95), H2 (157.9, 102.9).

### Design margin
Clearance 0.2, track 0.2, via 0.6/0.3, hole clearance 0.3, edge 0.4, silk 1.0 mm text; JLC floor 0.09/0.09/0.45/0.2. `policy` rows pass, nothing lowered.

## 2. Decisions with numbers

- **Fan-out was the hard part.** KRT left 34 of 69 airwires and Freerouting 25 of 69 on the first floorplan, at 281 s and 745 s, both stuck at U1. The chip's east side carries 10 nets that must reach J1, and the first floorplan put the VDD3P3 network across their way. Fix: chip moved 2 mm west, VDD3P3 caps hung south of their row, east nets taken by hand to columns, and 8 of them through vias to B.Cu.
- **All 35 header GPIOs are hand-routed, planar and nested** (`tools/copper.py`), locked, then `pcb route auto` does the 16 small nets left. An unlocked auto pass ripped hand tracks and opened 7 nets.
- **GPIO9 drives the user LED** rather than a free GPIO48, because pin 14 is next to it and GPIO48 needed a header slot.
- **Crystal tracks:** XTAL_P 3.78 mm, XIN 7.47 mm, XTAL_N 9.20 mm, no vias. The NE pad of Y1 forces XIN over the crystal's north edge, about 2 mm from the RF row with a ground fence between. HDG 1.4.3 and 1.4.4 want more distance. Weak spot.
- **16 signals on B.Cu,** where HDG 1.4.1 says a few. In2 is ground, so they keep a reference.

## 3. What was checked and how
See `SUMMARY.md` for final counts and exact commands. `pcb check` calcs carry each number above.

## 4. Open issues
1. RF match values are starting points; no VNA data. No simulation.
2. `return_via` fails on GPIO35 (2.34 mm) and GPIO45 (2.82 mm), limit 2.0 mm, assuming a 3 ns edge the datasheet does not state. No spot for a via.
3. Stackup figures to confirm with JLC.
4. C11, C12 distance. XIN length.
5. ERC warnings 0; DRC parity 9 are the NC pad names (Zener `NC_*` vs schematic `unconnected-*`), permanent, `reference/front-end.md`.
