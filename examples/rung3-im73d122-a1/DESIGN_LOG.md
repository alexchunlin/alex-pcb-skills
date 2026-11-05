# Design log: IM73D122 PDM microphone breakout rev A

Sources: `docs/IM73D122.pdf` (Infineon IM73D122V01 datasheet v1.00, 2022-08-12), `docs/tps7a20.pdf`. Every number below is a `checks.json` row, a `pcb q` line or a gerber read by `tools/verify_gerbers.py` (`fab/verify_gerbers.txt`).

## 1. Plan

### Rails and current budget
| Rail | V | Source | Load | Row |
|---|---|---|---|---|
| VIN | 3.3 to 5.5 | J1.1 | 2.4 mA | `rails`, `currents` |
| PWR.LDO_OUT | 3.3 | U2.5 | 2.4 mA | `rails` |
| 3V3 | 3.3 | U2 through JP3, or J1.2 with JP3 cut | U1 1.12 mA max (Table 6, 1.8 V; Fig 8 shows 1.0 mA typ, flat with VDD to 3.6 V), D1 1.3 mA | `i_mic_ma`, `i_led_ma`, `i_rail_ma` = 2.426 mA |
| GND | 0 | J1.3 | | `rails` |

No bus: PDM has no address and no pull-ups. `buses` is empty on purpose (the brief overrides the common I2C section).

### Header J1
| Pin | Net | Why this order |
|---|---|---|
| 1 | VIN | power at the left, away from CLK |
| 2 | 3V3 | |
| 3 | GND | splits power from signals |
| 4 | DATA | U1 pad 1 is on the left of the land, so DATA stays left of CLK with no crossing |
| 5 | CLK | U1 pad 3 on the right |
| 6 | SEL | U1 pad 4 on the right |

### Jumpers
| Ref | Pads | Shipped | Meaning |
|---|---|---|---|
| JP1 | 1 3V3, 2 IND.LED_R | 1-2 | LED, cut to disable |
| JP2 | 1 GND, 2 SEL, 3 3V3 | 1-2 | LR low; cut, bridge 2-3 for LR at VDD (Table 8) |
| JP3 | 1 PWR.LDO_OUT, 2 3V3 | 1-2 | cut to feed 3V3 directly |

The two-pad stock footprint name `SolderJumper-2_P1.3mm_Bridged_...` does not carry digits, so `pcb check` read it as open. The vendored copy is renamed `..._Bridged12_...`; the copper is unchanged.

### Parts (stock from the JLC parts endpoint, `docs/stock-check.json`, 2026-11-04)
| Ref | MPN | Maker | LCSC | Type | Stock | Package |
|---|---|---|---|---|---|---|
| U1 | IM73D122V01XTMA1 | Infineon | C5563886 | extended | 3,741 | PG-LLGA-5-3 |
| U2 | TPS7A2033PDBVR | TI | C2862740 | extended | 133,557 | SOT-23-5 |
| C1, C3, C4 | CL05A105KA5NQNC 1 uF 25 V X5R | Samsung | C52923 | basic | 10,119,499 | 0402 |
| C2 | CL05B104KO5NNNC 100 nF 16 V X7R | Samsung | C1525 | basic | 33,547,166 | 0402 |
| R1 | 0402WGF1001TCE 1 k | Uniroyal | C11702 | basic | 20,409,854 | 0402 |
| R2 | 0402WGF330JTCE 33 | Uniroyal | C25105 | basic | 2,891,672 | 0402 |
| R3 | 0402WGF1000TCE 100 | Uniroyal | C25076 | basic | 5,945,872 | 0402 |
| D1 | KT-0603R red | Hubei KENTO | C2286 | basic | 6,728,625 | 0603 |
| J1 | HX PZ2.54-1x6P ZZ, loose, DNP | hanxia | C32713272 | extended | 23,571 | 1x6 2.54 mm THT |

The brief says 2,618 mic in stock; the endpoint read 3,741 on the same date. JP1 to JP3, TP1, TP2 and H1 to H4 are copper only, not BOM lines.

### Floor plan
25.4 x 17.8 mm, four M2.5 holes (y 102.1 and 113.0; the lower pair sits above the header row because the holes' 2.6 mm courtyard hits the header's at the corners). J1 along the bottom edge. Power block upper left: VIN enters at J1.1 and runs up the left side to U2, and JP3 hands 3V3 to the mic from the left. Mic centre right, port at (115.0, 105.82), package centre (115.0, 106.5). Indicator on the right edge. CLK and DATA run straight down to J1 from the bottom of the land, 5.2 + 1.8 mm and 6.9 + 1.3 mm, no vias, while VDD enters at the upper left of the land.

### Stackup and margin
JLC 4-layer stock 1.6 mm, ENIG. F.Cu / In1 GND / In2 GND / B.Cu. Clearance 0.2, track 0.2 (0.25 default class, 0.3 power), via 0.6/0.3, hole clearance 0.3, edge 0.4 in setup with 1.0 mm by rule for copper and parts, silk 1.0/0.15. The fab floor is 0.09/0.09/0.45/0.2. Margin rows: track 2.78x, clearance 2.22x, via drill 2.00x.

ENIG, not the HASL default: the LGA has 0.25 mm pad gaps and a 2.3 mm^2 ring that seals the port; HASL's uneven crown is a poor fit. This must be picked on the order form.

## 2. Decisions with numbers

### Supply: low-noise LDO, not direct
Reason: the board's point is far-field pickup, and the host's 3.3 V rail is the noisiest thing near it. Numbers:

| Row | Value | Source |
|---|---|---|
| `mic_noise_dbfs_a` | -99 dBFS(A) | Table 3: -26 dBFS at 94 dBSPL, 73 dB(A) SNR |
| PSR | -80 dBFS for 100 mVpp, 200 Hz to 20 kHz | Table 6 |
| `direct_max_ripple_mvpp` | 3.55 mVpp | in-band supply noise that lands 10 dB below the mic noise, if fed direct |
| `ldo_noise_dbfs` | -151 dBFS | TPS7A20 VN 10 uVrms at 1 mA, 10 Hz to 100 kHz (VOUT 2.8 V row, sec 5.5) through the PSR |
| `ldo_noise_margin_db` | 51.97 dB | below the mic noise floor |
| `usb5v_ripple_dbfs` | -161 dBFS | 50 mVpp on VIN, through 75 dB LDO PSRR at 10 kHz, then the mic PSR |

PSRR at the noise band, TPS7A20 sec 5.5, VIN = VOUT + 1 V, IOUT 20 mA: 95 dB at 100 Hz and 1 kHz, 75 dB at 10 kHz and 100 kHz, 45 dB at 1 MHz. The datasheet has no row at 1 to 3 mA; the curves in section 5.7 are the closest. Treat the numbers as the design point, not a guarantee at 2.4 mA.

Direct feed stays available by cutting JP3, because a 1.8 V host needs VDD = 1.8 V (Table 5: VIH 0.65 VDD, VDD + 0.3 max, VOH 0.7 VDD).

Limit: at VIN = 3.3 V U2 is in dropout (`vdo_mv` 1.17 mV, scaled from 145 mV at 300 mA, DBV), the output tracks VIN and PSRR is gone. VIN needs VOUT + 0.3 V = 3.6 V for the datasheet's tolerance row. A 3.3 V host rail on VIN works but gets no rejection. The README says so.

Alternatives checked in stock: LP5907MFX-3.3 (C80670, 82 dB at 1 kHz, 10 uVrms), ME6211C33 (C82942, 70 dB, 50 uVrms), TLV75533 (46 dB at 100 kHz). TPS7A2033 has the highest PSRR of the SOT-23-5 options (95 dB at 1 kHz).

### How the two sources coexist
Shipped: VIN -> U2 -> JP3 -> 3V3. J1.2 is an output. TPS7A20 sec 5.1 note 2: VOUT at most VIN + 0.3 V; sec 7: reverse current no more than 5 % of rated (15 mA). There is no blocking diode, because the drop would cost headroom at VIN 3.6 V and the 3V3 pin is rarely fed. Direct: cut JP3, leave VIN open. JP3 is a solder jumper and not a diode, so the user acts on it; this is in the README and step 11 of the bring-up. Both sources at once is not supported.

### LED
R1 1 k: `i_led_ma` 1.3 mA from 3.3 V with Vf 2.0 V. It sits on the quiet rail because it draws DC and it should also show direct feed. At 1.8 V direct it stays off (Vf 1.8 to 2.4 V).

### Signal conditioning
R3 100 ohm in DATA next to U1: section 3.5 note, RTERM about 100 ohm. `data_rc_ns` 22 ns into 100 pF against tDV 100 ns inside the 163 ns half period. R2 33 ohm in CLK: slows a fast host edge a little. Host edge 3 ns is an assumption (no driver on board), recorded in `signals`, bucket 3.

No TVS on CLK or DATA: part HBM 2 kV (Table 11), it is a breakout on a bench, and a TVS adds capacitance at 3 MHz.

### LDO thermal
`p_ldo_mw` 5.34 mW at 5.5 V, `tj_ldo_c` 86.2 C at 85 C ambient with RthetaJA 187.1 K/W (sec 5.4). No thermal vias needed: `thermal_vias` block empty on purpose, SOT-23-5 has no pad.

### Input and output capacitors
C3, C4: 1 uF 25 V X5R 0402. TPS7A20 sec 5.3 needs effective 0.47 uF minimum on the output, 1 uF nominal. Bias at 3.3 V on a 25 V part leaves more than 0.47 uF, by Samsung's general derating. Not measured.

### Footprint from Figure 13
`tools/make_footprint.py` writes `parts/footprints/IM73D122V01_LLGA-5.kicad_mod`. The numbers came from the PDF's vector paths (`docs/p12.svg`), scale 40.42 pt/mm from the 1.7 mm pad pitch.

| Item | Measured in Fig 13 vector | In the gerber (`fab/verify_gerbers.txt`) |
|---|---|---|
| Pad copper | 0.75 x 0.45 (grey path) | 0.75 x 0.45 |
| Pad mask opening | 0.85 x 0.55 (hatch edge) | RoundRect 0.75 x 0.45 + 0.05 per side = 0.85 x 0.55 |
| Ring copper | R0.58 to R1.04 | R0.585 (vertex, flat at 0.58) to R1.04 |
| Ring mask opening | R0.53 to R1.09 | R0.535 to R1.09 |
| Port | R0.40 | 0.800 drill NPTH, F.Mask and B.Mask flash 0.800 |
| Paste pads | oblong 0.65 x 0.40 | O 0.65 x 0.40 x 4 |
| Paste ring | 6 segments R0.6 to R1.0, 0.12 webs | 6 regions R0.6 to R1.0, vertices traced from the figure |
| Pin 1 | Lower left, top view | pad 1 (-0.85, +1.5) from package centre |

Pin 1 check. Figure 12 is a bottom view: pads 1 and 2 left, 3 and 4 right, port low. Its top view has the pin 1 dot upper right. Mirrored for the top view and rotated so the port is up: pad 1 lower left, pad 2 above it, pad 3 lower right, pad 4 above it. Figure 13's "Pin1" leader also lands on the lower-left pad. Two independent statements agree. Pad count: 4 + 1 ring + 1 NPTH, against Table 9's 5 pins. Package fit: port to pad rows 1.48 and 2.18 mm in both figures.

**Finding on "solder mask defined".** Section 5 calls the pads SMD, and the brief reads Fig 13 as "mask R0.58, copper R1.04". The vector paths say otherwise: R0.58 and R1.04 are both on the grey copper outline, 0.75 x 0.45 is the grey pad, and the hatch stops 0.05 mm outside the copper everywhere (black path Ø2.18 and Ø1.055, 0.85 x 0.55). By geometry these are copper-defined pads with 0.05 mm mask relief. I built the figure as drawn. Exposed metal is the same either way, to within the 0.05 band, and the ring's 2.34 mm^2 still fully lands the package's R0.6 to R1.0 ring. If Infineon's intent was true SMD, the mask would move in by 0.1 mm per side; that is a footprint constant (`MASK` in `make_footprint.py`).

### Port keepouts
- Copper to port on the ring: 0.18 mm as drawn (R0.58 minus R0.40), 0.185 on the film at polygon vertices. KiCad DRC reports 0.2100 for the same pair (`pcb route` work dir, drc-plain.json); the gerber is the number I trust. Below the policy 0.3 and JLC's NPTH floor of 0.2. Brief rule: conflicts go to the datasheet. Scoped exception in `tools/im73d122_mic.kicad_dru`, `U1 port hole to ring`, applying only inside U1. `pcb drc` puts project rules after the pack, so this rule is what makes packed DRC read 0. **This is a waiver of the fab floor by 0.02 mm.** The exposure is that JLC's DFM flags it; drill wander of 0.05 mm still leaves 0.13 mm.
- In1, In2, B.Cu: keepout circle R0.70 in the footprint for tracks, vias and pour: datasheet copper-free radius 0.58, plus policy 0.3 from the hole. Gerber: nearest copper 0.700 mm on all three.
- F.Cu: keepout R0.55 inside the ring, and no pour or via under the package. Figure 13 shows only mask between the lands, and copper under mask would raise the package off the ring.
- Mask web R0.40 to R0.535 stays per the figure, 0.135 mm wide, over bare laminate.
- Plane coverage under U1 from `pcb q coverage`: In1 and In2 89.6 %; the shortfall is the antipad.

### Ring to ground
`zone_connect 0` on pad 5 and no pour under the package, so the ring keeps its drawn outline. Three 0.3 mm tracks leave the ring to GND vias just outside the package at (113.1, 104.1), (116.9, 104.1), (115.0, 103.9). No via in any SMD pad: `via_in_pad` row, 11 vias, none.

### CLK and DATA route against the supply
| Measure | Value | Tool |
|---|---|---|
| CLK + CLK_MIC to 3V3 copper, min edge to edge | 1.563 mm | `tools/measure_clk.py` |
| CLK track within 1 mm of 3V3 | 0.00 mm | same |
| CLK to DATA and DATA_MIC | 2.030, 1.393 mm | same |
| U1.2 VDD to U1.3 CLOCK, pad edge | 0.982 mm | `pcb q dist` |
| Vias on CLK, CLK_MIC, DATA | 0, 0, 0 | `pcb q net` |
| CLK, DATA off solid ground | 0.0 mm of 5.2, 6.9 | `refplane` rows |
| SEL beside CLK within 1 mm | 3.6 mm (DC strap) | `exposure` row |

C2 100 nF: 1.270 mm to U1.2, C1 1 uF: 1.586 mm (centre to centre by `pcb q`, target 2.0 from Table 5 note 4 and section 3.5 note, which say "close").

## 3. Datasheet layout requirements

| Requirement | Section | Met by |
|---|---|---|
| Port Ø0.8 mm, larger than the mic's | 5 | NPTH 0.8; mic port 0.6 |
| Land pattern and stencil | Fig 13 | table above, gerber read |
| 1 uF close to VDD | Table 5 note 4 | C1 1.586 mm |
| 100 nF as close as possible | 3.5 note | C2 1.270 mm |
| RTERM about 100 ohm | 3.5 note | R3 |
| LR tied to GND or VDD | Table 8 | JP2 |
| Cload 200 pF on DATA | Table 5 | README |
| Clock rise and fall 13 ns; duty | Table 5 | README, BRINGUP 7 |
| VDD ramp 50 ms | Table 5 | TPS7A20 tSTR 750 us typ, 1150 us max (sec 5.6) |
| Peak 260 C, three reflows | 7, Table 10, Table 11 | JLC economic 255 +/- 5 C, capabilities page |
| No air blow, no ultrasonic, no-clean paste | 7 | open question below |
| Tape over the port during sawing or assembly | 7 | BRINGUP 3; JLC cannot do this in panel routing |
| Do not pick on the port | 7 | port is on the underside, JLC picks the lid |

## 4. Wash and reflow

What I found. Datasheet section 7: no air blow, no ultrasonic, no-clean paste recommended, "The microphone MEMS can be severely damaged by cleaning substances". IP57 is for the component with dust and immersion, Table 2; it does not cover solvent or wash. JLC's capabilities page (https://jlcpcb.com/capabilities/pcb-assembly-capabilities) says nothing on PCBA cleaning, washing or paste type. It gives reflow at 255 +/- 5 C (economic, not adjustable) and 240 +/- 5 C (standard). JLC's blog on cleanliness mentions industrial cleaning in fabrication, not assembled boards. A TDK mic datasheet says water should not contact the port, and ultrasonic should not be used (https://www.manualslib.com/manual/2889916/Tdk-T5919.html?page=19). ADI's guidance is the same on ultrasonics. **I could not settle what JLC does after reflow.** Open question in `SUMMARY.md`. Bring-up steps 1, 3 and 9 are the check.

Header is loose, so no wave and no selective solder touches this board.

## 5. What was checked and how

Results are in `SUMMARY.md`. Commands: `pcb erc`, `pcb drc --pack jlcpcb`, `pcb check`, `pcb block gate`, `pcb block report`, `pcb regen-check`, `python3 -I tools/verify_gerbers.py`, `pcb py tools/measure_clk.py`.

Accepted, with reason:
- `net_conflict` on U2.4 (DRC warning, parity 1): NC pad name differs between Zener's board and schematic, permanent per `reference/front-end.md`.
- `test_points` warns on VIN (J1.1 is the probe) and PWR.LDO_OUT (JP3 pad 1 is exposed).
- `pcb route auto` reports one inherited hole_clearance error (U1 port to ring) because its private DRC does not see the project rule; `pcb drc` is the count. An earlier run of it also showed a 0.1596 mm clearance from PWR.LDO_OUT to the NC pad U2.4 that `pcb drc` did not report. I rerouted that track.
- Not checked: `feeds`, `feed_room`, `irdrop` (no pin above 10 mA), `thermal_vias` (no thermal pad), `refstat`, `basic_parts` (no local cache in the run; counted by hand: 6 basic, 3 extended lines of which J1 is loose).

Silk removed from the vendored 0402, jumper and test-point footprints: their ticks sat 0.10 mm from pads against the pack's 0.15, and the boxes collided with pin labels. Refdes live in a legend on the back.

## 6. Open issues
1. JLC's post-reflow cleaning, section 4.
2. SMD wording against the vector geometry, section 2.
3. U1 and U2 rotation in JLC's assembly preview: the CPL carries KiCad rotations. Fig 14 shows pin 1 dot upper right on the tape.
4. PSRR at 2.4 mA load is not tabulated.
