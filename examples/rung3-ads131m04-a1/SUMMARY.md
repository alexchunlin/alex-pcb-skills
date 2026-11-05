# SUMMARY: r3-ads131m04-a1, ADS131M04 breakout rev A

Wall clock: start 18:47:10, end 19:30:36, 2026-11-04 EST, from `date` in this session.

| Measure | Result | Source |
|---|---|---|
| Board | 40.0 x 25.4 mm, 984.28 mm², 4 layers, corners 1.5 mm, 2 M2.5 holes | `pcb stats`, `pcb q edge` |
| Parts | 41 footprints: 33 in the CPL, J1 and J2 DNP loose, 6 non-BOM (JP1, TP1-3, H1-2) | `pcb build`, fab.json |
| ERC | 0 errors, 0 warnings | erc.json |
| DRC plain | 0 errors, 0 warnings, 0 unconnected, parity 1 | drc.json |
| DRC packed (jlcpcb) | 0 errors, 0 warnings, 0 unconnected, parity 1 | drc.json |
| pcb check | 0 fails, 0 warns, 131 passes, 6 accepted | pcbcheck.json |
| Airwires | 0 of 37 nets open | `pcb q ratsnest` |
| Vias | 26, all 0.6/0.3: 20 GND, 6 3V3, 0 on any signal net | `pcb q vias` |
| Regeneration | REGENERATES | regen-check.txt |
| Fab | 14 files in the gerber zip, BOM 13 lines, 0 missing LCSC, CPL 33, no origin offsets | fab/fab.json |

Parity 1 is the U2 NC pad's net name, `POWER.U2.NC_U_NC` on the board against `unconnected-(U2-NC-Pad4)` in the schematic. front-end.md lists this as permanent.

regen-check warns, outside its verdict: canonical gerbers differ between passes on F_Cu and B_Cu, and against the handed-in tree on more layers. Netlist, DRC counts, placement and per-net copper match.

## pcb block report --json
```json
{"cohesion": 0.814, "purity": 0.863, "outside_region": [], "gates_passed": ["power", "inputs", "digital", "adc"], "gates_missing": [], "moved_after_gate": [], "gate_fails": 0}
```
Order power, inputs, digital, adc. Each block gated in stages by `pcb py tools/layout_board.py BOARD N`. An earlier "clock" and "hostconn" pair was merged into "digital" because `pcb block plan` failed J2: a 3.54 mm courtyard would not fit a strip north of the oscillator.

## Numbers the brief asks for
| Item | Value | Row |
|---|---|---|
| Filter corner | 7958 Hz, 1 k + 1 k + 10 nF C0G; design rate 16 kSPS, ratio to Nyquist 0.995 | calcs fc_hz, fc_over_nyquist_16k |
| Attenuation at fMOD 4.096 MHz | 54.23 dB | calcs atten_fmod_db |
| Loss at 32 kHz if run at 64 kSPS | 12.35 dB; 2.2 nF option gives 36.2 kHz | calcs atten_32k_db, fc_wide_hz |
| LDO noise referred to input | 1.778 nVrms, 236 times below the 0.42 uVrms ADC minimum | calcs ldo_noise_rti_nv, ldo_margin_vs_adc |
| 3V3 budget | 11.46 mA max, LDO 19.48 mW at 5 V, TJ 88.9 degC at 85 degC ambient | calcs |
| Decoupling, centre to pin | C1 1.809, C2 1.875, C3 1.771, C4 1.713, C5 1.688, C6 1.532 mm | decoupling |
| refplane | 0.0 mm off solid GND on all 36 routed nets | refplane |
| exposure, 1.0 mm, SCLK, SCLK_R, CLK_OSC, CLKIN | 0 mm on all 16 AIN nets; no AIN row is raised. 4 digital nets 7.4 to 10.6 mm, accepted | exposure |
| Same row at 5.5 mm | 0.3 to 0.5 mm on 7 AIN nets, at the U1 pin row only | one-off run |
| Edge-to-edge spacing | SCLK pin to AIN3N pin 4.43 mm; CLKIN pin to AIN0P pin 4.32 mm; Y1 OUT to AIN0P pin 8.00 mm | `pcb q dist` |
| Plane under U1 | In1 100.0 %, In2 100.0 % | `pcb q coverage` |

Accepted warns, 6: VIN and CAP have no test point; DRDY_R, DOUT_R, CS_R, DIN_R sit beside SCLK_R in the digital fan. Reasons are in checks.json.

## Tools that could not do something
1. `pcb dfm --offline ads131m04_breakout.zen` ends "Error: DFM check failed with 0 error finding(s), 2 not evaluated, 13 not applicable". Both not-evaluated lines are `copper.minimum_copper_clearance`: "copper layer 'F.Cu' has final functional copper without net attribution". The verdict reads fail on JP1's bridge copper. I relied on `pcb drc` for clearance.
2. `pcb check` read KiCad's 2-pad `SolderJumper-2_P1.3mm_Bridged_Pad1.0x1.5mm` as "shipped bridge open". I renamed the vendored copy `..._Bridged12_...`; copper unchanged.
3. Pcblib has no zone-connection call. `pcb drc` gave `starved_thermal` on J1 pins 3 and 9 with "1 spokes connected". The layout script sets `SetLocalZoneConnection(ZONE_CONNECTION_FULL)` on J1 pins 3, 6, 9 through pcbnew directly.
4. `b.ground_islands` reported "no spot inside the piece" on a 1.033 mm² F.Cu piece between J2.8 and J2.9. I moved the CS track and placed a via at (132.0, 102.3). Two pieces of 0.437 and 0.429 mm² are still skipped, both under the 0.5 mm² warn limit, so KiCad removes them.
5. `refstat` and `basic_parts` need files under `tools/bench`, which PATH.md closes. Not run. `tools/verify_parts.py` gave the class and stock of every BOM line instead.

## Not meeting the brief as written
- Top silk: J2 pins 4 to 10 are labelled in a row south of the SPI fan, not beside the pins. J2 pins 1 to 3 and J1 pin names are on the back only; top has channel numbers on J1. The back carries every pin.
- The stock filter passes 8 kHz, so 64 kSPS runs at 12.35 dB down at Nyquist; full band needs C7 to C10 changed to 2.2 nF.
- D1's polarity is from the KiCad footprint convention, not checked against a KENTO drawing.
- Nothing was built or measured. BRINGUP expected values come from datasheets.
