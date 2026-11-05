# Design log: INA745B digital power monitor breakout (ina745_breakout)

Datasheets in `docs/`: `ina745b.pdf` (TI SBOSAC3B, Aug 2025), `parts/tps7a02.pdf` (SBVS277C), `parts/C481445.pdf` (XFCN T44008 drawing 009).

## 1. Plan (before code)

### Rails and current budget
| Rail | Source | V | Load | Budget |
|---|---|---|---|---|
| VIN | header J3.1 | 3.3 to 5.5 | D1 then U2 | 100 mA through the LDO |
| LDO_IN | D1 cathode | VIN - 0.3 | U2 IN, EN, C2 | as VIN |
| 3V3 | U2 OUT and Qwiic pin 2, same copper | 3.3 | U1 VS 1 mA max (5.5), LED 1.3 mA, pull-ups 1 mA | 3.3 mA own load; the Qwiic chain passes through, budget 100 mA from U2 (JST SH 1 A per contact) |
| GND | header, Qwiic | 0 | In1, In2, outer fill | |
| IS_P, IS_N | terminals J4, J5 | -0.1 to 40 V | measured load | see section 2 |

### How the two logic sources coexist (brief: no back-feed fault)
VIN feeds U2 through Schottky D1 (1N5819WS). U2's output and the Qwiic 3V3 are the same net.
- Qwiic only: U2's body diode lifts LDO_IN to about 2.7 V, D1 is reverse biased, nothing reaches header VIN. TPS7A0233 (non-P) has no active discharge
  (SBVS277C 7.3.2, P-version only), so it does not load the rail. LP5907 was rejected for this: its EN-low output pull-down would load the Qwiic rail.
- VIN only: rail 3.3 V from 3.9 V up; at VIN 3.3 V, U2 is in dropout and the rail is VIN minus D1, 3.0 V at 3 mA, still above VS minimum 2.7 V (5.3).
- Both: two sources on one rail; U2 has no sink and the host regulator has none. Whichever is higher carries the chain; difference is regulator tolerance, not a fault.
- D1 also blocks reverse polarity on VIN.
LDO noise: the sensor does not need a low-noise analog supply: PSRR is 4 mA/V max (5.5), so 10 mV of rail ripple is 0.04 mA, 1/30 of an LSB (1.2 mA). TPS7A02 PSRR 55 dB at 1 kHz (SBVS277C 6.5).

### Bus map
| Device | Address | Strap |
|---|---|---|
| U1 INA745B | 0x40 default | A0, A1 to GND by JP3, JP4 |
Table 6-2: A1 A0 = GND GND 0x40; GND VS 0x41; VS GND 0x44; VS VS 0x45. Four addresses on the pads; a wire from the centre pad to SDA or SCL gives the other twelve.
Pull-ups 10 k per brief, one cut jumper JP2. Sink 0.33 mA per line, 0.66 mA for two boards in a chain; datasheet VOL 0.4 V at 3 mA (5.5).
Bus capacitance: rise time 0.8473 R C. 10 k alone meets the 300 ns fast-mode limit (5.6) to 35 pF; a Qwiic cable plus two devices is about 50 pF, 424 ns. So 400 kHz wants a stronger host pull-up
or two boards in parallel (5 k: 212 ns at 50 pF); 100 kHz (1000 ns) is fine at 118 pF. Stated in README.

### Connector maps
J1, J2 Qwiic: 1 GND, 2 3V3, 3 SDA, 4 SCL. J3 header: 1 VIN, 2 3V3, 3 GND, 4 SCL, 5 SDA, 6 ALERT. J4 IS+ terminal, J5 IS- terminal. TP3 VBUS wire pad (bus side, away from the logic header).
| Jumper | Pads | Shipped | Meaning |
|---|---|---|---|
| JP1 | 1 IS_P, 2 VBUS | closed | VBUS sense high side. Cut for low side and wire the rail to TP3 |
| JP2 | 1 PU_SDA, 2 3V3, 3 PU_SCL | both closed | cut both to drop the pull-ups |
| JP3 | 1 GND, 2 A0, 3 3V3 | 1-2 | A0 strap |
| JP4 | 1 GND, 2 A1, 3 3V3 | 1-2 | A1 strap |
| JP5 | 1 3V3, 2 LED_R | closed | cut to disable the power LED |

### Parts (stock read from the JLC API 2026-11-04)
| Ref | MPN | Maker | LCSC | Stock | JLC class |
|---|---|---|---|---|---|
| U1 | INA745BIRELR | TI | C35213810 | 13165 | extended |
| U2 | TPS7A0233DBVR | TI | C5142805 | 15269 | extended |
| D1 | 1N5819WS | Hottech | C191023 | 3099131 | basic |
| D2 | KT-0603R | KENTO | C2286 | 6728830 | basic |
| C1 | CL05B104KO5NNNC (0402) | Samsung | C1525 | 33540701 | basic |
| C2, C3 | CL10A105KB8NNNC | Samsung | C15849 | 12143613 | basic |
| R1-R3 | 0603WAF1002T5E | UNI-ROYAL | C25804 | 44423006 | basic |
| R4 | 0603WAF1001T5E | UNI-ROYAL | C21190 | 28490651 | basic |
| J1, J2 | SM04B-SRSS-TB(LF)(SN) | JST | C160404 | 59153 | extended |
| J3 | PZ254V-11-06P | XFCN | C492405 | 65659 | extended, DNP |
| J4, J5 | T44008 | XFCN | C481445 | 33196 | extended, through-hole |

### Floor plan
40 x 25.4 mm. Current runs west to east along the north band (y 101 to 113), logic in the south band (y 114 to 124). U1 long axis on the current path with IS+ west, the orientation of TI's Figure 8-5, which makes
pins 1-6 (A1, A0, SDA, SCL) face the logic band and pins 8-13 (VBUS, GND, VS, ALERT, SH-, IN-) face north. The gap between the IS+ and IS- pours is a channel the signals use; no signal crosses a pour.
Only VS and ALERT have to come back from the north side, on B.Cu under the package, in the gap between the B.Cu pours.

### Stackup and margin
JLC 4-layer 1.6 mm, 2 oz outer (brief allows it with the matching pack: `pcb drc --pack JLCPCB-4L-2oz.kicad_dru`), inner 0.5 oz as both GND planes. Clearance 0.2, track 0.2 (0.25 default), via 0.6/0.3, hole clearance 0.3,
edge 0.4, silk 0.15, text 1.0. Fab floor in the 2 oz pack: clearance 0.15, track 0.15.

## 2. Decisions with numbers

### Current path and rating
**Board rating: 25 A continuous, 40 degC ambient, still air, 40 V.** Not the part's 35 A. Each limit, from `pcb check` rows and `pcb irdrop` (reports in `docs/irdrop/`):
| Limit | Number | Source |
|---|---|---|
| Datasheet, full temperature range | 25 A | SBOSAC3B 5.5 "Maximum continuous current", -40 to 125 degC |
| Datasheet, Figure 6-4 at 40 degC | about 42 A | TI's EVM, read off the curve; Tj 150 degC, not a working point |
| Terminal | 50 A | XFCN T44008 drawing note 1 |
| Via field to B.Cu | 48.7 A (IS_P, 40 vias), 57.2 A (IS_N, 47 vias) within 5 mm | `feeds` rows, IPC-2221 on 0.3 mm barrels, 20 K rise |
| Worst via current at 25 A | barrel x0.21 of its rating | `pcb irdrop` |
| Pad exit necks at 25 A, 2 oz | x1.03 at U1.14, x0.99 at U1.7 of IPC-2221 at 20 K | `pcb irdrop`; the first is status PAD, a 7.0 mm cut 0.9 mm long at the pad itself: 21.4 K local rise by IPC's own exponent |
| Pours beyond the necks | x0.37 to x0.62 | `pcb irdrop` |
| Junction, rating point | 94.2 degC at 25 A, 40 degC ambient, 1.3 mOhm part | `calcs` |
| Junction at 35 A, 25 degC, typical part | 120.0 degC, with the copper near 100 degC | `calcs`: why the board is not rated 35 A |

Copper loss at 25 A: IS_P 3.87 mV, 92.8 mW; IS_N 4.10 mV, 98.6 mW. With the package, 25 A drops 33 mV end to end.
1 oz was rejected: IPC-2221 current goes as area^0.725, so the same necks at 35 um rate 0.6 times as much, x1.7 at the pads. 2 oz with both GND planes kept whole was enough, so the inner planes do not give way under the path. They stay GND, carry no current, and add heat spreading.

Thermal model: the leadframe shunt is the heat source. TI's curve gives the EVM's junction-to-ambient directly: 37.5 A at 60 degC reaches 150 degC at 1.49 mOhm (0.39 %/K from Figure 6-1), 42.95 K/W; the same arithmetic at 40, 80, 100 and 120 degC gives 42, 43, 43 and 41.6. This board: 32.8 K/W from both faces at 15 W/m2K, plus 4.9 K/W radial spreading in two 70 um layers, 37.7 K/W. Design value 45 K/W, above both.
That number is a model, not a measurement, and it ignores the wires, which help. BRINGUP step 11 tests it against the die temperature register. The RthJA in table 5.4 (103 K/W) is not used: note 2 there says it is conservative for leadframe heating.

### Current path geometry
Pours on F.Cu and B.Cu, net IS_P west and IS_N east, zone connection solid (`thermal=False`), each 178 to 186 mm2 filled (`pcb q zones`). U1's IS pads have only the F.Cu land; the field of 46 + 53 tented vias (0.6/0.3, hex 0.9 mm) brings B.Cu in, starting 0.45 mm from the land. In1 and In2 stay GND.
T44008: four legs in plated 1.8 mm holes, 3.0 mm pads, so the terminal feeds both outer layers directly.
Signals: the gap between the two pours is the channel. A0, A1, SDA, SCL run south on F.Cu, GND, VS, ALERT north. VS and ALERT return south on B.Cu under the package, in a 2.1 mm gap between the B.Cu pours. Logic tracks stay 0.6 mm from bus copper by DRC rule, on both outer layers. No Kelvin tracks: SH+ ties to IN+ and SH- to IN- on a 0.6 mm link at the pins, 0.6 mm long (Figure 8-2).

### Creepage at 40 V (brief)
IPC-2221 table 6-1, 31 to 50 V: B2 external uncoated 0.6 mm, B4 external under solder mask 0.13, A6 external lead uncoated 0.4, B1 internal 0.1.
- Outer bus copper to logic copper: 0.6 mm, enforced by `layout/ina745_breakout/ina745_breakout.kicad_dru`, rule "bus to logic, outer layers, 40 V", which covers IS_P, IS_N, SH_P, SH_N and VBUS against every other net. Zone filler obeys it. DRC reads 0.
- Inner layers: GND plane to bus vias and terminal holes, 0.2 mm setup clearance, against 0.1 for B1.
- **Exception, the part's own land:** inside rule area U1_ESC, 0.2 mm. Measured with `pcb q dist`: U1.2 IN+ to U1.3 A1 0.3; U1.9 IN- to U1.10 ALERT 0.3; U1.13 VBUS to U1.12 GND 0.3; U1.6 SCL to U1.7 IS- 0.2424 (TI's 0.242 on p.41). Bare pad gaps under the package body, below A6 0.4 mm at 40 V. Datasheet wins: the land pattern is TI's, the package is rated for 40 V to those neighbours (5.1, 5.3), and no track can widen a 0.6 mm pitch.
- JP1 has its own 1.6 mm pitch footprint: once cut, 40 V can sit across it in low-side mode, and the stock 0.3 mm gap would break B2.
- Bus copper to mounting screws: head radius 2.35 + 0.75 mm to the pour notch, outer layers; no bus copper in reach of a head.

### Datasheet layout requirements (SBOSAC3B)
| Requirement | Section | Done |
|---|---|---|
| Land: side pads 0.6 x 0.3, pitch 0.6, centres at +/-1.4; IS pads inner edge +/-1.6, depth 1.1 | p.41 | `tools/make_parts.py`; `pcb q pads U1`: 14 pads, pin 1 (118.5, 109.4) on the row facing the logic band, 7 and 14 on the short edges; 0.2424 mm corner gap matches TI's 0.242 |
| IS pad mask opening is the E shape, metal runs on under mask | p.41 | F.Mask polygon per pad; copper land is the plain rectangle, the pour is the metal under mask |
| Stencil: bar 1.8 x 0.3, three tines 0.3 x 0.6 at y +/-2.4 | p.42 | F.Paste polygons |
| Non-solder-mask-defined side pads, 0.05 margin | p.41 | `solder_mask_margin 0.05` |
| Bypass 0.1 uF as close as possible to VS and GND | 8.4.1 | C1 0.8702 mm centre to centre to pin 11, 0.29 mm edge (`pcb q dist`) |
| Vias as close as possible, number by current | Figure 8-5 | first column 0.45 mm from the land, counts above |
| Vias near pin pads tented | Figure 8-5 note 1 | `tent_vias` on; every via tented |
| No via in the land | p.41 note 5, brief | `via_in_pad` row: 130 vias, none in an SMD pad |
| IS+ to IS- pour gap 8 mil in TI's example | Figure 8-5 note 3 | not copied: wider here, signals use the gap; the package carries the current across |
| SH+ to IN+, SH- to IN- | Figure 8-2 | SH_P, SH_N nets, links at the pins |
| Establish A0, A1 before bus activity; do not float | 6.5.1 | hard-wired by JP3, JP4 |
| Keep GND connected while powered | 8.3 | README warning |
| Address pins tied to the bus give 100 ns hold requirement | Table 6-2 note 1 | SDA and SCL straps are not on pads, by wire only; README says so |

### Parts: footprint checks
| Part | Checked against | Result |
|---|---|---|
| U1 | TI p.40-42 | above |
| J4, J5 T44008 | XFCN drawing 009: 6.9 x 5.0 hole pitch, dia 1.8, body 7.9 | 4 pads all numbered 1 |
| U2 SOT-23-5 | SBVS277C table 5-1, DBV: 1 IN, 2 GND, 3 EN, 4 NC, 5 OUT | `pinmaps` row passes |
| J1, J2 | SM04B-SRSS-TB, from rung 1's reviewed footprint; courtyard trimmed to pads + 0.1 | pin map row passes |
| J3 | KiCad PinHeader_1x06, C492405 | |
| Drawing used by LCSC for T44008 | PDF from JLC's file endpoint: `docs/parts/C481445.pdf` | |
LDO choice: see section 1. TPS7A0233DBVR, 55 dB at 1 kHz. Sensor PSRR 4 mA/V max, so supply noise is not a design driver.

### Rework the routing took
`pcb route auto` is not used in the final regeneration. Its output was captured once into `tools/logic_routes.json` and rebuilt by `tools/layout_board.py`, with hand edits to SCL, because it does not see the project rule file (see SUMMARY.md). So the router's result is source, and regeneration is deterministic.
Fill pieces no via fits in are not poured (`no_pour` in the layout script, five rectangles) rather than left for KiCad's removal: a via needs 1.0 mm of width and those gaps are under that.

## 3. What was checked and how
| Check | Command | Result |
|---|---|---|
| ERC | `pcb erc layout/ina745_breakout/ina745_breakout.kicad_sch` | 0 errors, 0 warnings |
| DRC | `pcb drc ... --pack /tmp/pcb-ref/kicad-druid/JLCPCB/JLCPCB-4L-2oz.kicad_dru` | plain 0/0, packed 0/0, unconnected 0, sentinel fired, parity 1 warning (NC pin name, U2.4, permanent per front-end notes) |
| Intent | `pcb check ... checks.json` | 0 fails, 0 warns, 103 passes, 2 accepted (no test point on VIN, LDO_IN) |
| IR drop | `pcb irdrop ... --sink U1.14=25`, `--sink U1.7=25` | numbers above |
| DFM | `pcb dfm --offline ina745_breakout.zen` | 0 error findings, 2 not evaluated, 13 not applicable; exits non-zero on the solder jumper bridge copper, as front-end notes say |
| Regeneration | `pcb regen-check . --cmd tools/regen.sh ...` | REGENERATES |

## 4. Open issues
- Thermal rating is calculated, not measured. BRINGUP step 11 is the test.
- T44008 on JLC: `assemblyComponentFlag` false, class "Plugin". Whether JLC solders it needs a quote. By hand it wants a large iron: four legs into 2 oz pours and two planes' worth of via field nearby.
- JLC lists no price or stackup for 2 oz outer here; the pack file is the only evidence for its rules. Confirm the inner weight at order. The calculation does not use inner copper.
- HASL on a 0.6 mm QFN: `copper_finish` stays HAL lead-free per the Zener source. ENIG would be flatter under U1 and is a one-word change.
- 400 kHz with 10 k alone only to 35 pF (section 1).
