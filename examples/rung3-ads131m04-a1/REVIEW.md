# Review: ADS131M04 breakout (r3-ads131m04-a1), attempt 1

Checks re-run: ERC 0/0; DRC plain 0 packed 0 (sentinel fired yes, x192; capped: none; parity 1, the known U2 NC name); pcbcheck 0 fails 0 warns, 131 passes, 6 accepted; regen-check REGENERATES

**Verdict: ORDER AFTER SMALL FIXES.** Nothing found stops the board working: nets, footprints, parts and fab files all check out. What would stop a person ordering it today is one product decision and three small fixes, all done in the source with no re-placement of parts.

Fixes before ordering:
1. Top silk: add names for J2.1-3 and P/N for J1 (issue 1).
2. Decide the filter. Fit 2.2 nF in C7-C10, or sell it as an 8 kHz board and say so (issue 2).
3. Correct BRINGUP step 11, which a good board fails (issue 3).
4. Give J1.3, 6 and 9 thermal relief back (issue 4).
5. In JLC's preview, confirm U1, U2, Y1 and D1, with D1's green cathode mark to the south (issues 5, 6).

| Metric | Score | Anchor matched | One-line reason |
|---|---|---|---|
| Electrical | 8 | Works, at most 2 majors, each under an hour, no re-layout | Every pin, rail and calculation verified; one major: the stock filter leaves 7.0 kHz of the 64 kSPS the brief headlines |
| Manufacturability | 8 | Works, at most 2 majors, each under an hour, no re-layout | DRC clean both ways, fab package clean, parts in stock; two majors: top silk, and solid header joints on the part the buyer solders by hand |
| Documentation | 8 | Works, at most 2 majors, each under an hour, no re-layout | Log calculations reproduce, regen passes; one major: bring-up step 11 has the wrong expected readings |
| Layout quality | 7 | Experienced-designer read, not a rubric anchor | Good partition and clean analog routing; loses points on filter-cap placement, ground return details and silk (reasons below) |

Rubric anchors are applied per metric. Counts: 0 blockers, 4 majors, 13 minors.

Nothing was built. Every value here is from the design files, datasheets or calculation, not from hardware.

## Layout quality: 7

Good:
- The partition is right and simple: analog south, digital north, ADC between, power west.
- All 16 AIN nets and all SPI lines stay on F.Cu with zero signal vias.
- The smallest analog-to-digital copper spacing on any layer is 4.30 mm, and that is across the U1 pin rows. Nothing digital is in the input area on any layer.
- Y1 to pin 17 is 5.3 mm through a source resistor at the oscillator.
- Bypass caps sit 0.5 to 0.9 mm edge to pin, with the supply entering through the cap.
- In1 and In2 are solid: 100.0 % under U1.

Held back:
- Filter caps are not at the pins. C7 and C10 are 5.48 and 6.17 mm out against 2.90 to 3.12 mm for C8 and C9, so channels 0 and 3 carry about 3 to 4 mm more copper between the cap and the ADC pin (AIN0P 8.5 mm, AIN1P 5.0 mm). Datasheet 11.1 says as close as possible.
- Ground returns are the weak detail. Each bypass cap reaches its IC ground pin only through vias and the plane (F.Cu paths are 39 to 50 mm against 2 mm straight). C3 and Y1.2 share one via. C6 has no via of its own and returns through J2.3, 2.7 mm away.
- Space is unevenly used: the west end is tight while the area around x 127 to 138, y 109 to 122 holds only the product text. The filter block could spread into that space to close up channels 0 and 3.
- Top pin labels sit 8 to 10 mm from their pins, beyond the series resistors and the fan.
- Series resistors on DOUT and DRDY are at the host end, away from the driver. This is harmless at 10 to 14 mm, but it does not terminate what it claims to terminate.

## Previous issues

None. This is attempt 1.

## Measurements

| Item | Value | Source |
|---|---|---|
| Board | 40.0 x 25.4 mm, corners 1.5, 4 layers, 2 x 2.7 mm NPTH | `pcb q edge`, `holes`, less 0.1 outline stroke |
| Header grid | Rows 22.86 mm apart (0.9 in), columns offset 7.62 mm, both on 2.54 grid. On a standard breadboard the pins land in columns b and i; a and j stay free | `pcb q holes` |
| Part numbers | 16 of 16 MPNs match LCSC codes, all in stock live 2026-11-04. U1 C2862562 1,074; U2 133,536; Y1 4,494; C85973 262,038; C33353 2,738 | `scripts/parts_live.py`, `live/parts_live.json` |
| U1 land | 20 pads, 1.5 x 0.45, pitch 0.65, rows 5.8 apart = PW0020A 20X (1.5), 20X (0.45), 18X (0.65), (5.8). Pin 1 SW at (114.075, 115.6), silk mark beside it | `pcb q pads U1`, datasheet land pattern |
| U1 pins | All 20 match Table 5-1 TSSOP column, on the board and in the netlist | `pcb q pads U1`, `pinmaps` rows |
| U2 pins | 1 VIN, 2 GND, 3 EN on VIN, 4 NC, 5 3V3 = Pin Functions SOT-23 | `pcb q pads U2` |
| U2 land | KiCad 1.325 x 0.6, rows 2.275; TI 1.1 x 0.6, rows 2.6. Outer extent 3.6 against 3.7. Acceptable | TPS7A20 DBV0005A land pattern |
| Y1 land | 1.3 x 1.2, pitch 2.1 and 1.9 = YXC 3.2 x 2.5 land, gaps 0.8 and 0.7 | `pcb q pads Y1`, YXC page 3 |
| Y1 pins | Pad 1 NW tri-state on 3V3, 2 GND, 3 OUT, 4 VDD; matches YXC Pin Assignments after the -90 rotation | `pcb q pads Y1`, YXC page 2 |
| D1 | KENTO drawing: pad 1 +, pad 2 - with the green mark. Land suggestion 0.7 x 0.7, gap 0.7; board 0.875 x 0.95 | `live/kt-02.png` |
| Decoupling | C1 1.809, C2 1.875, C3 1.771, C4 1.713, C5 1.688, C6 1.532 mm centre to pin, as claimed | `decoupling` rows |
| Input caps | C7 5.48, C8 3.12, C9 2.90, C10 6.17 mm to pins 3, 6, 7, 10 | `pcb q decoupling`, `review_pcbcheck.json` |
| Analog to digital spacing | 4.30 mm minimum, all layers | `scripts/meas.py` |
| exposure at 3.0 mm | 0 mm on all 16 AIN nets, SCLK, SCLK_R, CLK_OSC, CLKIN as aggressors | `review_pcbcheck.json` |
| refplane | 0.0 mm off solid ground on all 36 routed nets | `refplane` rows |
| Plane under U1 | In1 100.0 %, In2 100.0 %, B.Cu 100.0 %, F.Cu 51.1 % | `pcb q coverage U1` |
| Vias | 26, 0.6/0.3, 20 GND, 6 3V3, 0 signal; none in a pad; all tented | `pcb q vias`, `via_in_pad`, F_Mask count |
| Copper | 192 tracks, airwires 0 of 37 nets | `scripts/meas.py`, `pcb q ratsnest` |
| Margins | Track 2.22x, via drill 2.00x, via 1.33x, hole clearance 1.50x, edge 2.00x | `margin` rows |
| Pour to outline | 0.5 mm on all four layers | `scripts/meas.py` |
| Fab | 14 files, BOM 13 lines, 0 missing LCSC, CPL 33, no offsets, J1 J2 DNP; BOM and CPL byte-identical to the handed-in package; 89 paste apertures = 89 SMD pads | `pcb fab` |
| Handed-in gerbers | 0 flashes or lines differ from a fresh fab on all 11 layers; the regen-check warning is order only | `scripts/gerber_geometry_diff.py` |
| Calculations | All 15 `calcs` rows reproduce; skew 2.42 us and LDO margin 236 redone by hand | `pcbcheck.json`, recomputed |
| Filter + sinc3 at 64 kSPS | -3 dB at 6,995 Hz; -3.68 dB at 7.96 kHz; -24.11 dB at 32 kHz | Equation 7 with RC, `review_pcbcheck.json` |
| Filter + sinc3 at 16 kSPS | -3 dB at 3.59 kHz; sinc3 alone 4.18 kHz | Equation 7 |
| Register values | RREG `A0 00`, `A0 80`, RESET `00 11`, ID `24xx`, STATUS reset `0500`, reply `FF24`, mode 1, DRDY half rate (Table 9-1) all reproduce | SBAS890D 8.5, 8.6, Table 9-1 |
| LDO | VN 10 uV, PSRR rows, dropout 145 mV at 300 mA DBV, COUT 1 to 200 uF, effective minimum 0.47 uF confirmed | SBVS338H 5.3, 5.5 |
| LDO at README's 100 mA | 5 V in, 85 degC ambient: TJ 120.5 degC, limit 125 | `review_pcbcheck.json` row `tj_ldo_100ma_user` |

## Issues

### Blockers

None.

### Majors

**1. Top silk does not name the power pins or the input polarity.**
- Problem: the board sits top-up in a breadboard, so its back silk cannot be read in use. J2 pins 1 to 3 have no name on top. J1 has only `CH 0 1 2 3`, with no P or N, and its order alternates P N, N P.
- Risk: 5 V on the unmarked J2.2 goes straight to DVDD and AVDD, abs max 3.9 V (6.1). VIN has no reverse protection.
- Evidence: `pcb q silk`; `tools/silk.py` skips n <= 3 with "no room on top"; SUMMARY lists it as not meeting the brief.
- Room exists: `0+ 0- G 1- 1+ G 2+ 2- G 3- 3+` fits the band at y 122.75 where `CH 0 1 2 3` now sits. `VIN 3V3 GND` fits west of J2's "1" on the same row, about 9 mm, moving the U2 and JP1 refs.
- Fix: edit `tools/silk.py`. Silk only.

**2. Stock filter gives 7.0 kHz at the 64 kSPS the brief and README headline.**
- Problem: the 10 nF corner of 7.96 kHz was tied to 16 kSPS. Combined with sinc3, the -3 dB point at 64 kSPS is 6,995 Hz and 32 kHz is 24.1 dB down. A vibration buyer has to rework four unlabelled 0603 caps.
- The choice is disclosed and follows Figure 9-1, but the product does not do what its title says as shipped.
- Fix: choose one. Fit 2.2 nF C0G (C33353, 2,738 in stock): corner 36.2 kHz, chain -3 dB 14.8 kHz, 41.1 dB at fMOD against 54.2 dB. Note 9.1.2 warns about charge for the sampling circuit and 2.2 nF is outside Figure 9-1, so bench it. Or keep 10 nF and state "bandwidth about 7 kHz" on the README's first line.
- BOM change only.

**3. BRINGUP step 11 fails on a good board.**
- Problem: it expects -3 dB at 7.96 kHz +/- 10 % (7.16 to 8.76 kHz) and -12.4 dB at 32 kHz. Both ignore the sinc3 filter at OSR 64.
- Reproduced: -3 dB at 6,995 Hz is outside the window; 32 kHz reads -24.11 dB (-12.35 RC, -11.76 sinc3). A sine at exactly fDATA/2 also reads phase-dependent amplitude.
- Evidence: `calcs:chain_at_32k_db` in `review_pcbcheck.json`.
- Fix: expect -3 dB at 7.0 kHz +/- 10 %, and test at 24 kHz, not at Nyquist. Correct the "12.35 dB down at Nyquist" lines in SUMMARY and DESIGN_LOG to say RC only.

**4. J1 pins 3, 6, 9 have solid connections to all four copper layers, and the buyer hand-solders them.**
- Problem: `SetLocalZoneConnection(ZC_FULL)` in `tools/layout_board.py`. J2 keeps relief. The change cleared a `starved_thermal` DRC error caused by F.Cu tracks and the board edge, and it cost relief on In1, In2 and B.Cu too. Risk is a slow or cold joint on the analog header's grounds.
- Fix: move the neighbouring AIN `_IN` tracks so each pad gets two F.Cu spokes, then drop the override. Script edit, no parts move.

### Minors

5. **D1 polarity unchecked, and the numbering conflicts.** KENTO marks pad 1 as + and pad 2 as - with the green mark; KiCad's pad 1 is cathode. Copper is fine: cathode must land on the GND pad at (102.2, 107.09), south. Fix: add the drawing check to the log; confirm in JLC's preview that the green mark is south.
6. **CPL rotations not checked against JLC's library.** `pcb fab` writes KiCad rotations (U1 90, U2 180, Y1 -90, D1 90). The log has no rotation check and I could not check either: the EasyEDA API returned 403. Fix: check all four in JLC's placement preview before paying.
7. **C7 and C10 far from their pins, requirement not cited.** 5.48 and 6.17 mm. 11.1 says "place the required capacitors as close as possible", and the log's table covers it only for supplies. Fix: pull C7 and C10 inward and add the citation. This is a reviewer's limit (3.5 mm), not a brief number.
8. **SCLK and DIN float with no host.** 9.1.1 says do not float digital inputs because excessive supply leakage can result; bring-up steps 3 and 7 run this way. The log's reading is reasoned but this is a deviation. Fix: 100 k pulldowns on a later rev, and a note that step 3 current may read high.
9. **Pours stop 0.5 mm from the outline; brief says copper 1 mm off.** All four layers. `edge_margin` covers tracks, vias and parts, not pours, so this was neither checked nor disclosed. The fab needs 0.2 mm, so this is harmless. Fix: record it as a deviation with the reason, or pull the pours back.
10. **Ground slivers left to KiCad's removal.** The brief says islands get a via. `gnd_islands` reports 8 unfed pieces, all under 0.5 mm²; SUMMARY mentions 2. Fix: report 8 and accept with a reason.
11. **Log claim on bypass vias is only half true.** "C1, C2, C3 reach their pins on F.Cu with no via" holds for the supply side. Ground goes through vias and the plane: F.Cu paths 39.1, 48.5, 50.4 mm against 2 mm straight (`scripts/fcu.py`). Fix: reword. Consider separate vias for C3 and Y1.2.
12. **RthJA from the wrong package.** The log uses 200 K/W, and `checks.json` cites "DBV 199.6 or 201.4", which are the YCJ and YCK columns. DBV is 187.1 (SBVS338H 5.4). The real number is better. Fix: correct the row.
13. **U2 land not compared with TI's drawing.** The log gives pad count and pins only, and the brief asks for the drawing check. The land is fine (see Measurements). Fix: add one line.
14. **README input limits are incomplete.** "Absolute limits" are the recommended range, and the table quotes gain 128 without its limit: gains 8 to 128 stop at AVDD - 1.8 V, 1.5 V here. No SYNC width is given: low for 2048 tCLKIN or more (250 us) is a reset, not a sync. Fix: two README lines.
15. **Named parts have no silk refdes.** 31 of 41 are hidden, including C7-C10, which README tells the user to change, and C3, which the accepted warn says to probe. Fix: a small outline or `C7-C10` note near the row.
16. **Margin ratio lowered from the template.** `via_drill` 1.5 against template 2.0. Measured 2.00x, so it changes nothing, but the brief says never to lower a number. Fix: restore 2.0.
17. **BRINGUP STATUS value ignores live bits.** `05 00 00` is the reset value; bits 3:0 are live DRDY flags, so a running ADC may return a non-zero low nibble. Fix: expect `05 0x 00`.

## Overclaims

| Designer said | Measured |
|---|---|
| BRINGUP step 11: -3 dB at 7.96 kHz, -12.4 dB at 32 kHz | 6,995 Hz, -24.11 dB (issue 3) |
| Log 10.3: C1, C2, C3 reach pins on F.Cu with no via | Supply side only; ground goes through vias (issue 11) |
| RthJA 200 K/W, "DBV 199.6 or 201.4" | DBV 187.1; those are DSBGA columns (issue 12) |
| SUMMARY: two ground pieces skipped | 8 unfed pieces (issue 10) |
| Log: JLC floor 0.09/0.09/0.45/0.2 | Pack via drill floor is 0.15 mm (`margin:via_drill`) |

No overclaim on ERC, DRC, pcbcheck counts, regen, fab counts, decoupling, vias, stock or wall clock. The designer also disclosed the top silk, the filter trade and D1 unprompted.

## Check-config audit

- Accepted warns, 6: all agreed. VIN sits on J2.1. CAP takes no stub, though C3 should be findable (issue 15). The four digital exposure rows are digital neighbours of SCLK, not analog victims.
- Brief items with no row: pour-to-outline distance, input cap distance, header grid, top-silk labels. Silk is covered only for refdes named in BRINGUP, so the `silk` row passes with issue 1 open.
- Reviewer rows in `review_checks.json`: exposure at 3.0 mm, input cap rows at 3.5 mm, signal-chain `calcs`, `tj_ldo_100ma_user`, `gain_err_300k_pct`. Result in `review_pcbcheck.json`: 3 fails (C7, C10, `chain_at_32k_db`), 3 digital-only exposure warns; each is an issue above or a digital row.
- `calcs` rows have no `sin`, so `sinc3_at_32k_db` is a literal computed outside.
- `gain_err_pct` uses Equation 4's 330 k; 6.5 lists 300 k, which gives 0.667 % against 0.606 %. No effect on the design.
- Not checked by any tool or by me: `refstat` and `basic_parts` (closed to the designer by PATH.md, not run here), JLC library rotations, SPI signal integrity by simulation, real noise. `feeds` and `thermal_vias` do not apply: no EP, under 150 mA by design.
- `pcb dfm --offline` exits non-zero on JP1's net-tie copper; disclosed, and DRC covers clearance.
- `tools/regen.sh` hard-codes an absolute wrapper path and ends `pcb check` with `|| true`. It passed here, but it would not run on another machine without `PCB_WRAPPER`.

## What is good

- Every pin of U1, U2 and Y1 is right, and U1 and Y1 lands match the maker's drawings exactly. This is the failure the brief warns about most, and it did not happen.
- The ground question has the correct answer: one solid ground, partition by placement, pins 2 and 19 tied at the device, as 10.3 and 11.1 read. The log quotes the right sentences.
- Two-minute bring-up details are right: ID, STATUS, RESET, SPI mode, frame length, half-rate DRDY from Table 9-1. Most engineers would have had to look these up.
- J1 and J2 on the 0.9 inch grid do fit a breadboard with one free column per side. I checked this because it looked wrong; it is right.
- The handed-in gerbers are the board: regenerated from clean, no geometry change.
- The designer's disclosure section is honest and specific.
