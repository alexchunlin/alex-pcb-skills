# Review: INA745B power monitor breakout (r3-ina745b-a1), attempt 1

Checks re-run: ERC 0/0; DRC plain 0 packed 0 (sentinel fired yes, capped: track_width sentinel at 199; 1 parity warning, U2.4 NC name); pcbcheck 0 fails 0 warns with the designer's config, 6 fails with the reviewer's rows; regen-check REGENERATES.

**Verdict: ORDER AFTER SMALL FIXES.** A person would order 3 to 5 of these for a first build once the fixes below are in. No blocker. The netlist, U1 footprint, pin 1, current path and 25 A rating all held up. What stops an order today is missing order and terminal information, plus one LDO datasheet limit. The rating is still calculated; no board has carried current.

Fixes before ordering:
1. Write the order spec into the source and README: 2 oz outer, 0.5 oz inner, 1.6 mm, ENIG. Set the stackup to 0.07 mm.
2. Get a JLC quote on J4 and J5. If they will not fit them, take them off the CPL and write the hand-solder procedure.
3. Add terminal limits to README: M4 x 6 at most, 3.4 mm of tine below the board, standoffs 5 mm or taller.
4. Deal with U2 reverse current in Qwiic-only mode.
5. Add VBUS against IS_P and IS_N to the 0.6 mm rule, and move ALERT off U1.9.

Then run BRINGUP steps 10 and 11 on the first build before any larger batch.

| Metric | Score | Anchor matched | One-line reason |
|---|---|---|---|
| Electrical correctness | 8 | Works, at most 2 majors, no re-layout | All pin maps, straps, pull-ups, decoupling and register values check out. One major: U2 reverse conduction |
| Manufacturability | 7 | Works, 3 majors | DRC clean and footprint correct, but copper weight, finish, terminal soldering and terminal limits are all open |
| Documentation/intent | 8 | Works, 2 majors under an hour | Log numbers reproduce and regen passes. README lacks the order spec and terminal limits; five overclaims |
| Layout quality | 7 | Reviewer judgement | Current path very good, logic band adequate, silk and mechanical details not finished |

Layout reasons: the current path is the best part: straight, symmetric, wide on both outer layers, with via fields right up to the lands, and both layers fed directly by the terminals. C1 is 0.29 mm from VS, and the signal escape is clean. It loses points for silk that runs together, a non-rectangular hole pattern, and an uneven IS_P via field where JP1 and TP3 sit in the pour (46 vias against 53). The south band works, but SDA and SCL take 50 mm and 5 vias each, and both ground fills are chopped up by the routing.

## Previous issues
None: this is the first attempt.

## Reworking the 25 A rating
The 25 A rating holds in open still air at 40 C. The designer's thermal number reproduced independently.

| Limit | Designer | Reviewer | Result |
|---|---|---|---|
| Part, table 5.5 | 25 A, -40 to 125 C | Read in SBOSAC3B 5.5 | Holds, and this is the limit that sets the rating |
| Part, Figure 6-4 | About 42 A at 40 C, EVM | Curve read at 41 to 42 A; 37.5 A at 60 C gives 43 K/W | Reproduced. The EVM's size and copper are unknown |
| Package loss | 0.625 W typ, 0.8125 W max at 25 C | Same; 1.03 W at the hot 1.3 mOhm part (h 12) | Reproduced |
| Copper drop | 3.87 mV, 4.10 mV | 3.87 mV, 4.10 mV (`pcb irdrop` re-run) | Reproduced |
| Necks | x1.03 pad exit, x0.99 | Same. A uniform 25 A strip at 70 um would need 8.4 mm; the neck is 7.0 mm wide over 0.9 mm | Acceptable, because the neck is short |
| Via count | 46 + 53; 40 and 47 within 5 mm | Counts match. Each field carries 11.8 A, 47 % of the current | Enough, but see the worst-via overclaim |
| Worst single via | "x0.21" | 1.06 A: x0.87 at 25 um, x1.10 at JLC's 18 um | Local IPC excess on a short barrel, not a failure |
| Terminal | 50 A, drawing note | Note confirmed. No temperature-rise or torque data. Brass about 27 uOhm, 17 mW (reviewer estimate) | Enough on paper. Lug contact loss is not modelled and would add under 5 K |
| Thermal | 45 K/W, Tj 94.2 C | Network below: 37.7 K/W at h 15, 44.0 K/W and 94.2 C at h 12 | Reproduced |
| ADC range | Not stated | Figure 8-1: 39.3 A flat to about 110 C, about 36 A at 150 C | Holds |

Reviewer thermal network: `review/scripts/thermal.py`, results in `review/thermal.json`. It is a 4-layer steady-state model on the real filled copper at 0.2 mm, with barrels at 18 um, Joule heat from the irdrop maps x1.15, and 0.39 %/K. Junction to land is an assumed 5 K/W per side. All cases are 25 A at 40 C unless stated.

| Case | Part | K/W | Tj | J1 |
|---|---|---|---|---|
| h 15, no wires | 1.3 mOhm | 37.7 | 85.5 C | 67 C |
| h 12, no wires | 1.3 mOhm | 44.0 | 94.2 C | 75.5 C |
| h 12, 10 AWG wires | 1.3 mOhm | 32.7 | 78.7 C | 62 C |
| Top 10, bottom 8 | 1.3 mOhm | 53.3 | 108.1 C | 88.5 C |
| h 6, closed box | 1.3 mOhm | 75.2 | 144.8 C | 123 C |
| h 12, 25 C ambient (bring-up) | 1.0 mOhm | 43.6 | 65.3 C | 52 C |
| 30 A, h 12 | 1.3 mOhm | 44.1 | 124.3 C | 95 C |

The model's h and the 5 K/W are assumptions, so only a build can settle this. BRINGUP step 11 expects 68 C typical and sets a 90 C stop, which fits these numbers.

## 40 V creepage
Measured by the reviewer on filled copper with shapely (`review/scripts/clear.py`), against IPC-2221 table 6-1 at 31 to 50 V as the log quotes it.

| Pair | Measured | Limit | Result |
|---|---|---|---|
| Bus to logic, outer layers, outside U1_ESC | 0.600 mm on F.Cu and B.Cu | B2 0.6 | Holds |
| Bus to GND, inner layers | 0.25 mm (log says 0.2) | B1 0.1 | Holds |
| U1 pad gaps | 0.243 to 0.3 mm | A6 0.4 | Under the limit, logged, and fixed by TI's land |
| ALERT track to U1.9 pad | 0.200 mm | B2 0.6, B4 0.13 | Not in the log, and avoidable |
| VBUS track to GND track | 0.253 mm | B4 0.13 under mask | Not in the log |
| VBUS to IS_P (JP1.2, TP3, track), low-side mode only | 0.200 mm | B2 0.6 | No DRC rule; contradicts the JP1 reasoning |

## Measurements
| Item | Value | Source |
|---|---|---|
| Part numbers and stock | All 11 codes match their MPN. U1 13,165, U2 15,269, J4 and J5 33,196 | JLC API, reviewer's own query, 2026-11-04 |
| U1 pin functions | All 14 match Table 4-1; SH+/IN+ and SH-/IN- tied as Figure 8-2 | `pinmaps:U1`, datasheet |
| U1 land | Side pads 0.6 x 0.3 at +/-1.4, pitch 0.6; IS pads 1.8 x 1.1, inner edge +/-1.6; corner gap 0.243 | `pcb q pads U1`, TI p.40-41 |
| U1 mask and stencil | E shape as p.41; bar 1.8 x 0.3, three tines 0.3 x 0.6 at +/-0.75 and +/-2.4 | Regions read from the F_Mask and F_Paste gerbers |
| U1 pin 1 | Rotation 90, not mirrored; silk dot at (117.95, 109.95) next to pin 1 | Pad coordinates and footprint source |
| Addresses | A1, A0 table matches Table 6-2 | Datasheet; `addresses` row covers A0 only |
| Registers | 0x05, 0x06, 0x07, 0x0B, 0x0C, 0x3E = 0x5449 correct; 3840, 8333, 4167 correct; DIETEMP shift missing (issue 16) | Table 7-1, Table 7-6, arithmetic |
| Decoupling | C1 0.29 mm edge to U1.11 | `pcb q decoupling` |
| Size | 40 x 25.4 mm, R1.5, 4 x M2.5 | `pcb q edge` (bbox includes line width) |
| Fab | 14 files, BOM 10 lines, 0 without LCSC, CPL 15, DNP J3, J1 and J2 offset 0.45 mm | `pcb fab` |
| Gerbers | Same coordinates as a fresh run on mask, paste, silk, edge. Against both regen passes, only 2 extra fill vertices on B.Cu in pass 2 | Coordinate comparison |
| DFM | 0 errors, 2 not evaluated (jumper bridge copper), exits non-zero as logged | `pcb dfm --offline` |

## Issues
No blockers. Four majors, twelve minors. Full evidence and fixes are in `review.json`.

1. **Major: no order spec.** README has no copper weight, and the stackup and job file say 35 um. JLC offers both weights, so a default 1 oz order gives x1.7 at the U1.14 neck. HASL is still set for a 0.6 mm QFN carrying 25 A.
2. **Major: terminal soldering is unresolved.** J4 and J5 are in the CPL with no evidence JLC will fit them. By hand, four legs go into solid-connected 2 oz pours, and no bring-up step finds a cold joint.
3. **Major: terminal limits are undocumented.** 3.4 mm of bare tine stands below the board, taller than the 2.5 mm header spacer. An M4 x 8 screw through a lug bottoms on the PCB. No screw is on the BOM.
4. **Major: U2 reverse conduction.** Qwiic-only is the main mode, and it puts OUT above IN. SBVS277C 6.1 allows 0.3 V and 7.3.2 allows 10 mA for a short time. The log cites neither, and the 2.7 V figure is unmeasured.
5. Minor: low-side VBUS to IS_P is 0.200 mm.
6. Minor: ALERT and VBUS tracks use the U1_ESC exception documented for pad gaps.
7. Minor: the worst-via figure is a field total.
8. Minor: rating conditions are too narrow for "25A MAX"; J1 and J2 can exceed 85 C.
9. Minor: T44008 tine diagonal 1.803 mm against a hole as small as 1.72 mm.
10. Minor: silk runs together, and JP5, D1, D2, J1, J2, J3 and U2 have no top label.
11. Minor: mounting holes span 35.4 and 35.0 mm; head overhang 0.35 mm.
12. Minor: inner planes stop 0.5 mm from the edge against the brief's 1 mm.
13. Minor: Figure 8-5 notes 2 and 4 are not addressed.
14. Minor: no proper rail-return point, and no transient warning at 40 V.
15. Minor: the rule pack lives in /tmp.
16. Minor: BRINGUP steps 10 and 11 omit the 4-bit shift on DIETEMP (bits 15-4), so a raw read is 16 times high.

## Overclaims
| Designer said | Measured |
|---|---|
| Worst via x0.21 | x0.87 for a single via at 25 um, x1.10 at 18 um |
| Logic stays 0.6 mm from bus; the exception is bare pad gaps | True outside U1_ESC. Inside, track gaps of 0.200 and 0.253 mm |
| JP1 widened so B2 holds in low-side mode | JP1.2 is 0.200 mm from IS_P |
| assemblyComponentFlag false counts against T44008 | False on all 11 parts, so it carries no information |
| Body diode lifts LDO_IN to 2.7 V, no fault | Unmeasured, and over SBVS277C 6.1 as written |

Everything else checked in `SUMMARY.md` matched: ERC, DRC, pcbcheck, irdrop, feeds, fab counts and stock. The designer's stated gaps (rating unmeasured, hand-drawn footprint, HASL, `progress.md` batching, the `current` gate not re-run) are honest.

## Check-config audit
- `accepted_warns`: both are fine. VIN is probed at J3.1, and LDO_IN at C2.
- Coverage gaps: `addresses` covers A0 but not A1. `edge_margin` does not cover zones. `feeds` and `irdrop` assume 25 um plating. `margin` reads setup values, not gaps. Not checked: `exposure`, `feed_room`, `refstat`, `basic_parts`.
- Rows added in `review_checks.json`: single via at 18 um, tine diagonal, tine length, VBUS to IS_P, J1 temperature, Tj at h 12 and h 6, and a `thermal_vias` baseline of 12 vias within 2.5 mm of U1.14 (TI sets no number). Six fail, all reported above.
- Not verified: TI's EVM guide (not found), whether JLC fits T44008, JLC's price for 2 oz, the CPL rotation in JLC's preview, and any real current or temperature. Coverage is from models and documents only.

## What is good
- U1 footprint, mask, stencil and pin 1 are all right, the item this project fails on most.
- The netlist is correct everywhere checked, and every register value reproduces.
- Clearance of 0.600 mm outside U1 is enforced by a rule, and the fill obeys it.
- The designer stated the rating from their own numbers and an independent model landed on the same result.
- Regeneration really is deterministic, despite the gerber warnings.
- `SUMMARY.md` tells a person what remains before ordering.

Sources: [JLCPCB capabilities](https://jlcpcb.com/capabilities/pcb-capabilities), [INA745BEVM listing](https://www.digikey.at/en/products/detail/texas-instruments/INA745BEVM/22119499) (found no board data there).
