# Review: VL53L8CX Qwiic breakout, attempt 1

**Verdict: ORDER AFTER SMALL FIXES.** The circuit is right and the sensor footprint matches ST's drawing. Do not upload the package as it stands: three ICs are rotated wrongly in the CPL. None of the fixes needs a re-layout.

Fixes before ordering:
1. Correct the CPL: U3 0, U4 90, U5 180. Confirm all eight asymmetric parts in JLC's preview.
2. Rework the J3 silk so VIN and 3V3 sit on their pins.
3. Clear C6 from the U4 body and restore the U3 and U4 courtyards.
4. Fill or plug the U1 thermal vias, set the paste, and read AN5897.
5. Change C9 to 100 nF.

Checks re-run: ERC 0/0; DRC plain 0 packed 0 (17 silk warnings, sentinel fired x199, capped: track_width(sentinel) only); pcbcheck 0 fails 4 warns, 4 fails with review rows; regen-check REGENERATES

| Metric | Score | Anchor matched | One-line reason |
|---|---|---|---|
| Electrical | 8 | Works, at most 2 majors | Every pin map is right and the design works; bias cap and EN numbers stop it at 9 |
| Manufacturability | 6 | A blocker caps the metric | CPL wrong on 3 parts, C6 meets U4, U1 thermal pad unresolved |
| Documentation | 8 | Works | Regenerates and is honest about its gaps, but some bring-up readings are wrong |
| Layout quality | 6 | Reader's judgement, rounded down | Very good around U1; hand routing is busy and one part collision got through |

**Would a person order it?** Not today, but after about half a day of edits, yes. Parts are about $12.57 per board at quantity 1, of which U1 is $10.23, with 6 extended part types.

## Previous issues
First attempt on this board, so there is nothing to verify.

## Measurements

### Re-run results
| Item | Value | Source |
|---|---|---|
| ERC | 0 errors, 0 warnings | `pcb erc` |
| DRC plain | 0 errors, 0 unconnected, 4 parity (N/C pads) | `pcb drc`, `drc/` |
| DRC packed | 0 errors, 17 `silk_over_copper` warnings, minimum 0.067 mm, none on a pad | same |
| pcbcheck, designer's config | 0 fails, 4 warns, 156 passes, 2 accepted | `pcbcheck.json` |
| pcbcheck, review rows | 4 fails, 4 warns, 161 passes, 2 accepted | `pcbcheck_review.json` |
| Airwires | 0 | `pcb q ratsnest` |
| Regeneration | REGENERATES. Mask, paste, silk and inner layers have identical geometry. F.Cu and B.Cu differ only in segment splits. CPL identical, 33 nets identical | `regen/`, `gerbgeo.py` |
| Fab | 14 files, BOM 17 lines, 0 missing LCSC, CPL 32, J3 DNP | `pcb fab` |
| Board | 25.4 x 17.8 mm, 1.5 mm corners, 2 M2.5 holes, 4 layers | `pcb q edge` |

### Parts and pin maps
| Item | Result |
|---|---|
| Part numbers | All 18 LCSC numbers match the MPN on the JLC record and are in stock today. U1 917 |
| U1 land pattern | Pads, pitch 0.75, rows +-1.0575, B1/B7 +-2.6675, B4 2.316 x 1.2, A1 tab all match Fig 26 and Fig 34 |
| U1 pin 1 | A1 at top-view (+2.25, +1.0575), Tx on the A1 end. Matches Fig 4 mirrored, Fig 26 and Fig 34 |
| U1 pins | 17 of 17 match Table 3. RSVD1, 2, 3 on GND. MISO on JP5 only, open as shipped |
| U2, U3, U4 | Pin tables match the datasheets, on the board pads as well as in the netlist |
| U5 | 21 of 21 in `review_checks.json`; all eight A/B pairs are on matching channels |
| Bring-up values | ST ULD source confirms ID 0xF0 / 0x0C, which the designer had from memory. Table 5, Table 22 and the liner notes are all carried through |

### Optical exclusion zone (`zone.py`)
Both squares are on `User.1` and match my own calculation from Fig 28: half-width (2 + apex) x tan 28.95.

| Item | Courtyard into zone | Pad clearance | Nominal body clearance |
|---|---|---|---|
| R3 | 0.068 mm in | 0.077 mm | 0.357 mm |
| R7 | 0.053 mm in | 0.092 mm | 0.372 mm |
| R5 | 0.023 mm in | 0.122 mm | 0.222 mm |

The designer's figures hold, and this is **not an issue**:
- The cone only exists above the module top at 1.75 mm, and these parts are 0.35 mm tall.
- The zone is 0 pads, 0 silk. The nearest silk is U1's dot, 0.017 mm clear.
- Tall items also clear: J1/J2 at 2.95 mm give a cone half-width of 1.09 mm, about 5 mm from either connector. J3 pins up reach y 108.76 against the row at 116.3.

### Power sequencing and CORE_1V8 slew
| Item | Designer | Measured | Limit |
|---|---|---|---|
| EN delay, threshold 1.2 V | 4.6 ms | 4.64 ms | |
| EN delay, Fig 5-2 typical 0.79 V | not computed | **2.78 ms**, 2.48-3.09 with tolerance | 3.3 ms in the log's argument |
| 0.9-1.6 V, linear at tON 150 us | 61.4 us | 61.4 us | 63 us (Fig 9) |
| Slew, same | 0.0114 V/us | 0.0114 V/us | 0.012 (Table 5), 5 % short |
| 0.9-1.6 V from digitised Fig 5-15 | not computed | 22 us typical, **41 us at tON max** | 63 us |
| Slew, same | not computed | **0.0169 V/us** at tON max | 0.012 |
| EN off time to re-arm | about 9 ms | 12.5 ms to 0.76 V | UM3109 reset is 10 ms |

Findings:
- **The sequencing is sound.** U4 follows 3V3, and CORE_1V8 and IOVDD are one net. Table 5 allows AVDD first, and U2 and any normal host ramp well inside 2.8 ms. The shorter delay does no harm, but the log's reason for the delay is wrong.
- **The slew margin is better than the designer feared.** Fig 5-15 has 33 us of dead time before the output moves, so the linear estimate is pessimistic. My 41 us scales a typical 2.8 V curve at 25 C, so it is an estimate. No 1.8 V curve is published. BRINGUP step 4 should still measure it.
- **Choosing LP5907 was right.** It reaches 95 % in 80 us typical, against 550 us for the brief's TLV75518.

### LSF0108
- **Wiring is correct.** Vref_A is on 1V8, Vref_B ties to EN, and 200k goes to 3V3, as TI's Figure 8-1 shows. Headroom is 1.5 V against the required 0.8 V.
- **EN is tied the way TI asks.** The designer did not drive it from a push-pull output.
- **Back-drive before 1V8 is up is blocked.** The gate sits a Vgs above an off 1V8, and U4's 230 ohm pull-down holds that rail, so the 3V3 pull-ups cannot reach the sensor.
- **One departure.** C9 is 100 pF where rev M asks for 0.1 uF.

### 3V3 source arrangement
- U2, then U3 with CE on VOUT (TI's reverse-current mode, ST on GND as TI says). Qwiic and J3.2 share the rail.
- **Qwiic cannot back-feed VIN.** That part of the design is correct and meets the brief.
- **VIN can feed the host.** U3 blocks one direction only. The README covers an unpowered host but not a live one; see issue 6.
- Rail at VIN 3.3 V, 168 mA: 3.20 V. At 5 V: 3.23 to 3.35 V, inside 3.13 to 3.47.
- U2 at 5 V: 0.29 W, Tj 89 C, reproduced. U4: 0.15 W, 90 C, reproduced.

### Other electrical
| Item | Value |
|---|---|
| Decoupling | C3 1.69, C4 1.67, C5 1.21 mm to the pins, reproduced |
| I2C | 254 ns at 10k and 30 pF. Limit is 35.4 pF for 300 ns, of which about 16 pF is this board (LSF0108 CIO(on) 12.5 pF, about 3.8 pF of trace, my estimate) |
| Feeds | U4.5 1.36 A, U3.6 1.01 A, U2.1 4.78 A, U1.C4 1.01 A available, all well over the need |
| Paste on exposed pads | U1 36 %, U2 22.6 %, U5 65 % |

## CPL: will JLC place it correctly?

**How I worked it out.**
- JLC places by the LCSC part's EasyEDA footprint, not the KiCad one. The `kicad-jlcpcb-tools` project documents this, with JLC's preview as its evidence.
- I downloaded each part's EasyEDA footprint and fitted its pads to the board pads at 0, 90, 180 and 270 degrees. The turn that fits best is the rotation the CPL needs.
- I checked the sign against that project's worked example: a `-BL` SOIC-8 needs 270.
- For D1 I matched by polarity using the EasyEDA symbol, because its pad numbers are reversed from KiCad's.

| Ref | LCSC package | Fit residual, mm | Needs | CPL says | Error | Result |
|---|---|---|---|---|---|---|
| U1 | LGA-16_L6.4-W3.0 | 0.008 | 0 | 0 | 0 | Correct |
| U2 | WSON-6...-TL-EP | 0.019 | 0 | 0 | 0 | Correct |
| **U3** | SC-70-6...-BL | 0.263 | **0** | 90 | **90** | **Wrong** |
| **U4** | SOT-23-5...-BR | 0.163 | **90** | -90 | **180** | **Wrong** |
| **U5** | DHVQFN-20...-BL-EP | 0.029 | **180** | -90 | **90** | **Wrong** |
| J1 | SM04B | 0.129 | -90 | -90 | 0 | Correct |
| J2 | SM04B | 0.129 | 90 | 90 | 0 | Correct |
| D1 | LED-SMD...-R-RD | 0.038 | 90 by polarity | 90 | 0 | Correct |

**Effect.** U4 turned 180 degrees leaves IN and GND on no land, with OUT on EN_1V8 and EN on 1V8, so there is no 1V8 and no sensor. It would not be a silent fault: the 3-to-2 lead pattern shows in the preview, as do the 90 degree misfits on U3 and U5. A careful JLC engineer may stop or fix them, but the package as handed in is wrong.

**Second source.** The JLCKicadTools rotation table is keyed by footprint name rather than part, so it is weaker evidence:
- It rejects the current U3 and U4 rotations, but gives other angles (270 and 180) than the per-part fit.
- It has no DHVQFN row. Its QFN-20 row, applied by family, gives my 180 for U5.
- For U2 its `^DFN-` row would add 270, but this LCSC footprint is `-TL` and fits at 0 with a 0.019 mm residual. I trust the per-part fit, and U2 is the first part to look at in the preview.

**Origins.** The 0.45 and 0.15 mm offsets from `pcb fab` come from the fab outline, not the placement. By pads, U1 is 0.008 mm off and J1/J2 about 0.06 mm. No correction needed.

**What I could not confirm.**
- JLC's own preview, which needs an upload. The final say is there.
- That JLC's library matches the EasyEDA footprint for these exact parts today. That is inferred.
- The physical cathode of KT-0603R on the reel against the EasyEDA footprint.

## Issues

### Blocker

**1. CPL rotations wrong for U3, U4 and U5.** See the section above.
Fix: set U3 0, U4 90, U5 180 from a correction step in `tools/regen.sh`, so a regeneration does not undo it. `pcb fab` has no per-part correction, and no check here looks at this: all DRC, pcbcheck and regen rows pass over it.

### Major

**2. The VIN label sits nearest the 3V3 pin.**
- VIN text is 0.91 mm from pin 2 and 1.63 mm from pin 1, on both sides.
- The pin 1 dot is 1.23 mm from pin 1 and 1.31 mm from pin 2, so it does not settle the question.
- Front SCL is 1.27 mm from pins 5 and 6.
- A user following the silk puts 5 V on the 3V3 rail. AVDD's absolute maximum is 3.47 V and nothing blocks it, so this one damages the sensor.

Fix: swap rows, with VIN on the lower row at x 101.9 and 3V3 on the upper at x 103.81. Move SCL to x 111.43 and pull MISO, NCS and INT onto their pins. Put the pin 1 mark on the edge side of pad 1. Silk only.

**3. C6 meets the U4 body, and tightened courtyards hide it.**
- U4's body ends at x 108.75 nominal, or 108.825 at TI's 3.05 mm maximum. C6 starts at 108.78.
- That is 0.03 mm nominal and a 0.045 mm overlap at maximum.
- `tools/tight_courtyards.py` set U4's courtyard to pad bbox + 0.1, leaving its edge at 108.69, inside the body. U3's courtyard is also inside its body.
- The log discloses the tightening but not this effect, so "0 courtyard errors" is not evidence here.
- C6 cannot go east: U1's cap is at 109.5.

Fix: restore body + 0.1 on U3 and U4, then move C6 north to about (109.05, 101.8) and move the 3V3 via at (108.9, 101.9) and its stubs. Aim for 0.2 mm at U4's maximum. About an hour, local copper only.

**4. U1 thermal pad: open vias, 36 % paste, AN5897 unread.**
- Four 0.3 mm vias sit in B4, open on the top and tented on the back, with plugging and covering off.
- The paste window gives about 0.06 mm3 of solder at a 0.12 mm stencil, against about 0.31 mm3 of barrel volume.
- The brief's rule, vias outside the paste, is met. But solder that melts can still reach them, and the back tent traps gas.
- GND continuity is safe through the other GND pins. The risk is to the thermal joint, on a part that dissipates 215 mW.
- U2's EP has 22.6 % paste and one via.

Fix: order these vias filled and capped, or plug them, then open paste to 50-60 %. AN5897 could not be obtained by the designer or by me, and it overrides this advice.

### Minor

5. **C9 is 100 pF.** LSF0108 rev M 9.2.1.1.2 asks for 0.1 uF. Change to C1525 and note that Vref_B then settles in about 28 ms.
6. **"Either or both are fine" does not hold for a live host.** U2 at 5 V can carry the host's rail: a 200 mA host plus 170 mA here is 0.63 W, Tj 123 C at 60 C ambient. State a limit in the README.
7. **EN delay.** BRINGUP step 4's 3.0-6.5 ms window misses the typical 2.8 ms, and 33 us should read about 22 us. Expect 2.3 to 5.2 ms and 20 to 45 us.
8. **The slew row runs at typical only.** Table 5 at tON max is never tested as a row. Add it; BRINGUP step 4 remains the real proof.
9. **A 10 ms power cycle skips the delay.** C8 needs 12.5 ms, so after UM3109's 10 ms reset CORE tracks 3V3. At U2's 550 us ramp that is about 116 us against 63 us. The 50 ms in BRINGUP is safe; put it in the README too.
10. **BRINGUP step 7 will false-alarm.** LM66100 leakage of 0.2 uA on a 10 M meter can read over 1 V at J3.1. Use a 10 k load.
11. **C2 limit raised.** 3.43 mm through two vias; the row moved from 3.0 to 3.5 mm to pass. It is disclosed, but the brief forbids this. TI's stability need is met at the capacitor value.
12. **Solid pours.** All four zones use full connection. J3.3 is hand-soldered by the buyer to four GND layers. Relieve that pad at least.
13. **Four GND pieces left to KiCad's removal**, 0.65 to 1.40 mm2. The brief says stitch them.
14. **Top silk.** 44 of 44 refdes are hidden. JP1 is on top with its label on the back. Name and rev are on the back only. Top labels run together as SCLNCS.
15. **J3 has no line in the full BOM.**
16. **J1, J2 tab lands.** 1.4 mm against JST's 1.8 mm. eSH.pdf is now read and the land ends 0.2 mm behind the housing face where JST's extends 0.2 mm past it. Reasonable for a flush face; record it.
17. **Small log errors.** U3 95 mOhm is the 5 V figure, so 21 mV not 16 mV. The "U1 thermal via pitch" rule applies to every GND via pair.
18. **Vias butt against pads.** 16 are within 0.05 mm of a same-net pad, minimum 0.005 mm at U2.1. Legal and tented; pull back where easy.

## Layout quality: 6

**What an experienced designer would like:**
- The U1 breakout is clean: straight drops from rows A to U5's A side, with C3's ground going directly into U1's C6 and C7.
- Both inner planes are whole at 294 mm2, and only 0.2 mm of track in the board lacks a solid reference.
- No signal runs on an inner layer, and the shifter sits between sensor and header so the two voltage domains stay apart.

**What they would mark up:**
- 59 vias on a 25 x 18 mm board, 34 of them not ground.
- A 3V3 ring around the back, 59 mm, which with SDA and SCL along the south edge cuts B.Cu fill into 11 pieces. F.Cu is in 15.
- SDA_1V8 takes two vias to reach a pull-up 2.6 mm away.
- U2's output reaches its capacitor through two vias.
- C6 is wedged against U4, and the routing leaves no room to move it without touching copper.
- Top silk is large for the space, and labels drift off their pins because that is where the space was.

The result works and is honest copper, but it reads as routed to reach DRC 0 rather than designed. The designer's own time split agrees: 65 of 111 minutes went on it.

## Overclaims

| Designer said | Measured |
|---|---|
| EN holds 1V8 off 4.6 ms (3.0 to 6.5) | 2.8 ms typical; 4.6 ms only at the guaranteed VIH |
| LSF0108 has "same 200k and 100 pF bias" | Rev M in `docs/`: 0.1 uF |
| README: "Either or both are fine" | Not with a loaded live host |
| Dropout under "about 9 ms" skips the delay | 12.5 ms to reach the typical threshold |
| DRC courtyards clean | U3 and U4 courtyards are inside their bodies |

**Holds as stated:** ERC, DRC, pcbcheck, fab counts, zone numbers, decoupling distances, thermal numbers, and the 1 h 51 min wall time. The designer's "before ordering" list named most of these risks, including the CPL.

## Check-config audit

- **`accepted_warns`:** both agreed. VIN is probed at J3.1, and 3V3_LDO at C2.
- **Disputed limit:** C2 at 3.5 mm, back to 3.0 in my copy.
- **Rows added in `review_checks.json`:** full U5 and U3 pin maps, D1 polarity, four `feeds`, typical EN delay, Table 5 at tON max, Fig 5-15 shape, LSF0108 bias cap.
- **Results:** three calcs fail plus the C2 limit, covering issues 5, 7, 8 and 11. All pin maps and feeds pass.
- **`not_checked`:** `feeds` (now added), `feed_room`, `refstat`, `irdrop`, `basic_parts`, `exposure` (no switch node, correct).

**Not checked by anyone:** the JLC preview, reflow behaviour, tombstoning, ranging performance, and anything on real hardware.

## What is good

- The hard electrical calls are right, including two the designer made against the brief: LP5907 over TLV75518 and LSF0108 over PCA9306. PCA9306 could not cover eight lines.
- U1's land pattern, including the A1 tab, is exact against ST's drawing.
- MISO's "do not connect" in I2C mode is honoured with JP5, and all eight signals are shifted.
- Regeneration from code works, and the source is readable.
- The designer listed what they could not verify instead of hiding it, which is why this review could go straight to those points.

## Sources

- [JST SH catalogue, eSH.pdf](https://www.jst-mfg.com/product/pdf/eng/eSH.pdf)
- [ST UM3109, Pololu mirror](https://www.pololu.com/file/0J2030/um3109-a-guide-for-using-the-vl53l8cx-lowpower-highperformance-timeofflight-multizone-ranging-sensor-stmicroelectronics.pdf)
- [ST ULD, stm32duino/VL53L8CX](https://github.com/stm32duino/VL53L8CX)
- [kicad-jlcpcb-tools jlcfootprint notes](https://github.com/Bouni/kicad-jlcpcb-tools/tree/main/jlcfootprint)
- [JLCKicadTools rotation table](https://github.com/matthewlai/JLCKicadTools)
- [ST DS14161 listing](https://www.st.com/content/st_com/en/technical-documents/DS14161.html); the datasheet read is `docs/VL53L8CX.pdf`
- EasyEDA, JLC and LCSC part records, saved in `review/jlc/`
