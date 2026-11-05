# Review: im73d122_mic, attempt 1 (r3-im73d122-a1)

Checks re-run: ERC 0/0; DRC plain 0 packed 0 (sentinel fired yes, x57; capped: none; project rule on U1 kept in both runs, without it plain 1 packed 1 hole_clearance); pcbcheck 0 fails 0 warns, 72 passes, 2 accepted (with my rows 2 fails, both deliberate); regen-check REGENERATES

**Verdict: ORDER AFTER SMALL FIXES.** Fix the CPL rotation of U1 and U2 first. That is a two-line data change and nothing in the copper moves. As handed in, the placement file would build dead boards unless someone corrects it in JLC's preview. The microphone land pattern, port, pin map and CLK route all hold up.

| Metric | Score | Anchor matched | One-line reason |
|---|---|---|---|
| Electrical correctness | 8 | Works, at most 2 majors | Every pin map, strap and value verified; one major: a 3.3 V host has no clean way to wire this board |
| Manufacturability | 6 | Any blocker caps here | CPL has U1 and U2 180 degrees off; without that blocker this is an 8 |
| Documentation/intent | 8 | Works, at most 2 majors | Regenerates and the log is strong, but it missed JLC's published no-wash statement and misdescribes the DRC warning |
| Layout quality | 7 | Experienced designer's reading | Clean mic block and signal routes; ground return is one-sided, the back silk is cluttered, the planes break the 1 mm rule |

**Small fixes, in order**
1. CPL: U1 and U2 rotation 180, D1 stays 0, then confirm in JLC's preview (issue 1). Make it a post-step in `tools/regen.sh`, or the next regen undoes it.
2. Silk: J1.2 top and back read `3V3 OUT`; README leads with "use 5 V on VIN" (issue 2).
3. `SUMMARY.md` and `DESIGN_LOG.md` section 4: cite JLC's no-wash term and shrink the open question (issue 3).
4. Worth doing in the same pass: `b.zone("GND", "In1.Cu", inset=1.0)` and In2 the same (issue 6); reverse the back legend (issue 9); delete `fab/im73d122_mic_gerbers.zip` (issue 11).

## Previous issues
None. This is the first attempt, so there is nothing to re-verify.

## Measurements

| Item | Value | Source |
|---|---|---|
| Fig 13 vector radii | R0.40, R0.53 (black); R0.58, R1.04 (grey copper); R1.09 (black); scale 40.42 pt/mm | `pdftocairo -svg` page 12, my own path extraction |
| Film, F.Cu ring | R0.58 to R1.04 | `probes/m1.py`, my own Gerber rasteriser at 200 px/mm |
| Film, F.Mask ring opening | R0.53 to R1.09 | same |
| Film, mask at port, both sides | R0.40 | same |
| In1, In2, B.Cu to port centre | 0.700 mm each | same |
| Ring to port, nominal | 0.18 mm | same; `calcs:rv_port_gap_nominal_mm` fails against 0.20 |
| Ring to port with JLC position tolerance +/-0.075 | 0.105 mm | `review_checks.json` |
| Ring to port, worst case with +0.13 hole size | 0.04 mm, copper not cut | same; +0.13 is JLC's plated figure used as a stand-in, JLC states none for round NPTH |
| Mask web, hole to ring opening | 0.13 mm at the flats, against JLC 0.10 (green) | film |
| Mic port (R0.30) inside hole with 0.075 offset | 0.375 mm reach against R0.40, stays clear | calculation |
| Port drill | 0.800 NPTH in `-NPTH.drl`, not in `-PTH.drl` | order zip |
| Package fit | pads 0.85/0.8/1.5, port 0.68 from centre; matches Fig 12 (1.32 + 0.68 = 2.0) and Fig 13 | footprint source, Fig 12 |
| Pin 1 | lower left, port up; Fig 12 top view, Fig 13 leader and the EasyEDA library footprint all agree after rotation | Fig 12, Fig 13, EasyEDA |
| Pin functions | U1 1 DATA, 2 VDD, 3 CLOCK, 4 LR, 5 GND match Table 9 on the nets; U2 1 IN, 2 GND, 3 EN, 4 N/C, 5 OUT match TI pin table | `pinmaps` rows, `tps7a20.pdf` sec 4 |
| Paste apertures on F.Paste | 25 flashes: 4 U1 oblong + 21 others; 6 ring regions R0.6 to R1.0; none on jumpers | film |
| CLK to 3V3 tracks | 1.563 mm, reproduced | `probes/p2.py` |
| CLK to DATA | 1.393 mm, reproduced | same |
| CLK to SEL | 0.45 mm minimum; 3.6 mm within 1 mm, 0.5 mm within 0.5 mm | same, `exposure` row |
| Decoupling | C2 1.270 mm, C1 1.586 mm, C3 1.436 mm, C4 1.373 mm centre | `decoupling` rows |
| C2 GND via to nearest ring via | 4.2 mm in the plane | coordinates |
| Plane coverage under U1 | In1, In2 89.6 % | `pcb q coverage U1` |
| Copper to board edge | F.Cu, B.Cu 1.0 mm; In1, In2 0.5 mm | `probes/p2.py` |
| Live stock, JLC endpoint | U1 3,741; U2 133,536; all nine lines in stock; MPN and LCSC code match on every line | `probes/stock.py` |
| Size | 25.4 x 17.8 mm; `pcb q edge` 25.5 x 17.9 includes the 0.1 mm line | `pcb q edge`, Edge.Cuts |

Calculations reproduced: `i_led_ma` 1.3, `i_rail_ma` 2.426, `p_ldo_mw` 5.338, `vdo_mv` 1.173, mic noise -99 dBFS(A), LDO noise -151 dBFS, margin 51.97 dB, ripple -161 dBFS, direct limit 3.548 mVpp, `data_rc_ns` 22. One does not: `tj_ldo_c` is 86.0, the log says 86.2.

Not covered: JLC's actual preview and DFM result, because nothing was uploaded. The schematic was checked from the netlist rows, not by eye. `thermal_vias`, `feed_room`, `refstat`, `feeds`, `irdrop` and `basic_parts` are not checked by the tool; I counted 6 basic and 2 extended by hand and the LDO dissipates 5 mW, so none of these matter here.

## Issues

### Blocker
**1. CPL rotates U1 and U2 180 degrees from JLC's zero.**
The CPL has U1 0.0 and U2 0.0. The KiCad footprint at zero has U1 pin 1 lower left with the port up. Fig 14 shows pin 1 upper right on the tape, and the EasyEDA library footprint for C5563886 has pad 1 at (+0.85, -1.5) from package centre with the port at +0.68, so pin 1 is upper right with the port down. For U2, the EasyEDA footprint has pad 1 at (+1.1, +0.95) and KiCad has it at (-1.14, -0.95). Both are a 180 degree difference. Followed literally, the mic's port lands on the pads and the ring lands away from the hole, and U2's IN pin lands on the N/C pad so the rail never comes up. Every board would be dead. D1 is correct at 0: its cathode is at -x in both libraries. The designer named this as a preview check but left the data as it was, although Fig 14 and the library footprint settle it.
Limit of this evidence: I inferred JLC's zero from its tape drawing and library data, not from its preview, which still has to confirm it.
Fix: set U1 and U2 to 180 in the CPL through a regen post-step, then confirm in the preview.

### Major
**2. A 3.3 V host has no clean wiring.**
Every host the README lists is a 3.3 V part. VIN at 3.3 V puts U2 in dropout with no rejection: the log's own limit is 3.55 mVpp, and an assumed 30 mVpp of host ripple lands at -90.5 dBFS, 8.5 dB above the -99 dBFS(A) mic floor (`calcs:rv_host_ripple_dbfs`). The other natural wire, host 3V3 to J1.2 with VIN open, exceeds TPS7A20 sec 5.1 (VOUT at most VIN + 0.3 V) as shipped. Nothing blocks it, and the silk just says `3V3`. Damage is unlikely because only C3 and U2's quiescent current load that path. The board does work from either wiring, so this is a performance and labelling trap. The README covers it, but not at the point where a person wires the board. Also, the 75 to 95 dB PSRR is specified at VIN = VOUT + 1.0 V, so the README's "above 3.6 V ... noise rejection works" is not a datasheet row: 4.3 V is.
Fix: label J1.2 `3V3 OUT` on both sides and lead the README with "5 V on VIN for full rejection; to use a 3.3 V rail, cut JP3 and feed J1.2".

**3. The wash question was answerable and the log says it was not.**
`SUMMARY.md` says "Not settled" and that a search "found no JLC statement". JLC's assembly terms, section 4 item 3, say: "We use no-clean solder paste, so by default we do not wash the boards after soldering is complete." Cleaning is by request through Support after ordering. That matches the datasheet's section 7 recommendation and removes the main fear about the port. What remains open is narrower: no JLC statement covers air blow, or MEMS handling in general. A search summary also pointed at a forum report of JLC dry-ice cleaning damaging MEMS mics after hand soldering; I could not open the post, so treat it as unverified. It would not apply here anyway, since J1 ships loose and nothing is hand-soldered at JLC.
Fix: cite the term, keep the remark "no cleaning of any kind, no air blow on U1" on the order, and keep bring-up steps 1 and 9.

### Minor
**4. The 0.18 mm waiver is sound, and I would accept it.** Film nominal is 0.18 against JLC's 0.20; JLC publishes 0.2 for NPTH to track and no general NPTH-to-pad figure. Copper survives even the 0.04 mm worst case, and if JLC's CAM trims the ring to R0.60 it still lands the package ring (R0.6 to R1.0) and all six paste segments. The exposure is a DFM email. Three corrections: DRC's 0.2100 is explained, 0.61 - 0.40 = 0.21 is the inner edge of the pad's 0.4 mm anchor circle, so KiCad measured the anchor and not the ring, which is why it disagreed with the film; the log's "drill wander of 0.05 leaves 0.13" should be 0.105 with JLC's stated +/-0.075; "plain 0" exists only because of the project rule. If a clean check matters more than matching Fig 13 to 0.02 mm, `R_CU_IN = 0.60` removes the waiver without touching paste.

**5. The true-SMD option in the log is wrong; do not take it.** The film matches Fig 13's paths, and the designer's reading of them is right. But "true SMD" is not `MASK` moved in by 0.1: that gives a 0.65 x 0.35 opening, smaller than Fig 13's 0.75 x 0.45 dimensions and than the 0.65 x 0.40 paste. Fig 13 fits SMD only if the black outlines are copper (0.85 x 0.55, R0.53 to R1.09) and the grey is the opening, which puts copper 0.13 mm from the port. Exposed metal is the same either way. Keep the board as built, and close item 5 of the designer's order list.

**6. In1 and In2 are 0.5 mm off the outline** against the brief's 1 mm and the log's "1.0 mm by rule for copper and parts". `edge_margin` measures tracks, vias and parts, not pours, which is why it passed. Fix: `inset=1.0` on both inner zones, one line plus regen.

**7. CLK passes SEL at 0.45 mm.** Shipped, SEL is grounded so this does no harm. On the R strap, which is the README's stereo use, SEL is the 3V3 rail, so CLK-to-rail spacing for that board is 0.45 mm, not the quoted 1.563 mm, though only 0.5 mm of length is that close. Small in effect, but the claim should carry the qualification.

**8. The ground return is one-sided.** All three ring tracks leave from the top, while VDD and C2 are below the ring, so C2's ground reaches the mic through a via, 4.2 mm of plane and a second via. The no-via-under-package zone is the designer's own choice; Fig 13 does not require it, and a tented via beside pad 2 would shorten the loop. Keep it for rev A; it is unlikely to be measurable at 1 mA.

**9. The back legend reads in reverse and locates nothing.** Viewed from the back it reads `GND TP2 3V3 TP1`, which pairs TP2 with 3V3; the truth is TP1 = 3V3 and TP2 = GND. The same happens on the other two rows. All 20 refdes are hidden, and the code comment says the tokens are there "so `pcb check` silk can read the refdes", so the `silk` pass says little. The top-side labels 3V3, GND, LDO, LED, L and R do let a technician get through bring-up.

**10. Back silk quality.** Text crosses three tented vias at (115.0, 103.9), (111.1, 107.75) and (109.0, 101.6). The slash in `L/R` nearly touches `DATA`, and `PDM MIC` is squeezed between two rows. `SOUND PORT` is centred 2.4 mm above the hole with no pointer, while the `G` of `GND` is the nearest silk, 0.205 mm from the hole edge. Fix: a ring or arrow at the port.

**11. Two zips sit in `fab/`.** Only the order zip has the split drills; the other has the single MixedPlating `.drl`, which is one wrong upload away from a misread port. Fix: delete it in `regen.sh`.

**12. Check-row gaps.** Brief items with no row: port drill, ring radii, mask openings, plane pull-back. They live in `tools/verify_gerbers.py`, so they are checked, but not by `pcb check`. The `margin hole_clearance` row reads 1.50x and the `policy` row reads "0.3 met", yet the true minimum is 0.18, or 0.90x, because both use board setup and not the measured gap.

**13. No port-length note.** The log has no acoustic estimate for a 1.6 mm port in series with the mic's own. A rough Helmholtz estimate moves the 37 kHz peak to about 23 kHz, which would lift the top of the band. That is an estimate from an assumed front volume, not a measurement. It needs a line in the log, and step 9's 10 kHz comparison should state an expected value.

**14. Mounting holes** leave a 0.75 mm web to the edge (hole R1.35 at 2.1 mm). It will fabricate, but it is fragile if a screw is overtightened.

## Overclaims

| Designer said | Measured |
|---|---|
| The 1 DRC warning is `net_conflict` on U2.4 | `lib_footprint_mismatch` on U1, in their own `drc.json` too |
| No JLC statement on cleaning | JLC terms: no-clean paste, no wash by default |
| 1.0 mm edge for copper | In1, In2 at 0.5 mm |
| `tj_ldo_c` 86.2 C | 86.0 C (their own row reads 86) |
| Mask web 0.135 mm | 0.13 mm at the flats; 0.135 is at the vertices only |
| Sentinel x58 | x57 |
| Regen warn is F_Cu only | Six layers flagged by the tool. My parse found no geometry difference on any of the 8 layers compared, which include all six flagged, so this looks like aperture naming and is harmless |
| Margin hole clearance 1.50x | True minimum 0.18, 0.90x, under the disclosed waiver |

## Check-config audit
- `accepted_warns`: both agreed. J1.1 and the exposed JP3 pad 1 are real probe points.
- Rows added in `review_checks.json`: port gap nominal (fails, the waiver), with position tolerance, worst case, mask web, Tj, and 3.3 V host ripple (fails, issue 2). Result in `review_pcbcheck.json`: 2 fails, 76 passes, 2 accepted.
- Brief items with no row: see issue 12.

## What is good
- U1's land pattern is the best thing on the board: built from the PDF's vectors, every radius confirmed on film, pin 1 right three independent ways.
- The port is right: 0.8 mm NPTH in its own drill file, all other copper pulled back to R0.70, more than the R0.58 that Fig 13 draws.
- CLK and DATA have no vias, sit over solid ground and run straight to the header; VDD enters from the opposite side of the mic.
- The parts are real and in stock, and the U2 choice is argued with numbers.
- Regeneration from clean holds, and the fab package matches. The designer's list of things a person must do is honest, including admitting scratch files outside the run.

Sources: [JLC assembly terms](https://jlcpcb.com/help/article/terms-and-conditions-of-jlcpcb-assembly-service), [JLC PCB capabilities](https://jlcpcb.com/capabilities/pcb-capabilities), [JLC assembly capabilities](https://jlcpcb.com/capabilities/pcb-assembly-capabilities), [JLC PCBA FAQ](https://jlcpcb.com/help/article/common-pcba-after-sales-issues-and-faq), [EasyEDA](https://easyeda.com) library footprints for C5563886 and C2862740.
