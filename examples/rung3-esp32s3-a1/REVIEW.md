# Review: r3-esp32s3-a1, bare-chip ESP32-S3 devkit, attempt 1

Checks re-run: ERC 0/0; DRC plain 0 (15 warnings) packed 0 (165 warnings) (sentinel fired yes, x199, capped: track_width sentinel only); pcbcheck 2 fails 0 warns, 214 passes, 13 accepted; regen-check REGENERATES

| Metric | Score | Anchor matched | One-line reason |
|---|---|---|---|
| Electrical | 6 | Real risk of rework at bring-up | Boots and enumerates on paper. GPIO47/48 are swapped against the datasheet; the RF match, crystal and EN layout leave Wi-Fi unproven and likely to need rework |
| Manufacturability | 5 | A blocker in the core function | The CPL carries raw KiCad rotations. USB-C is 180 degrees off by an exact-footprint table entry, and the chip and ESD part are probably off too |
| Documentation | 7 | 3 or more majors | Regenerates, counts all reproduce, weak spots are disclosed. Wrong PINMAP rows, several overclaims, hard-coded impedance rows, stackup absent from the fab package |
| Layout quality | 5 | Experienced designer's reading, no rubric anchor | Tidy, disciplined routing on a floor plan that puts RF, crystal and EN in each other's way |

**Verdict: ORDER AFTER SMALL FIXES**, as a small prototype run by someone with a VNA, not as a product. Not as is: uploaded as it stands, this CPL risks a dead board.

Fixes before ordering:
1. Correct the CPL rotations and confirm every asymmetric part in JLC's placement preview (table below). J3 needs +90, not -90. Resolve U1, U3, U2, D1, J4 and J5 from the preview.
2. Put the J5 orientation in writing: red mark at the south end, the feed end. Add a mark to the footprint.
3. Fix GPIO47/48: swap the two labels on silk and in `PINMAP.md`, `README.md` and the nets.
4. Put "JLC04161H-7628" in the fab package and on the order.

The RF majors (issues 3 to 7) need layout work. They are risks to accept on rev A, or to fix first if an afternoon is available. Issue 3 is the one worth doing first.

## Would it work?

| Question | Answer | Basis |
|---|---|---|
| Boot | **Likely yes**, once assembled correctly | Power, EN RC, straps, VDD_SPI, crystal and EPAD all check out against the guidelines; netlist right apart from the 47/48 label swap |
| Enumerate on USB | **Likely yes** | D+/D- on the right pins, CC 5.1 k each, 92 to 94 ohm pair, about 5 ps skew against a 12 Mb/s signal. Bring-up's VID 303A PID 1001 is right |
| Join Wi-Fi at reasonable range | **Likely joins; range unproven** | Antenna wiring, keepout and 50 ohm feed are right. The match is untuned, 3.8 mm from the pin, with the crystal beside it. Estimate: works room to room, several dB behind a module until tuned on a VNA. Channel 6 (2440 MHz, 40 MHz x 61) is where I would expect any desense. No RF measurement or simulation exists, mine included |

The biggest assembly risks are J5, because no photo or AOI check will catch it, and U3, because 180 degrees puts its GND pin on VBUS.

## Previous issues
None. First review of this attempt.

## Measurements

| Item | Value | Source |
|---|---|---|
| Edge | 60.0 x 26.0 mm; `pcb q edge` reads 60.1 x 26.1 including line width | `pcb q edge`, DRC coordinates x = 100.0 |
| Stackup in board file | F 35 um, prepreg 0.2104, core 1.065, 1.6 mm | `kicad_pcb` stackup; JLC impedance page confirms 7628 0.2104 mm er 4.4, and 3313 0.0994 mm er 4.1 |
| RF feed Z0, w 0.32 g 0.25 | 50.6 ohm (designer 49.7) | `scratch/fd2d.py`, 2D field solve. Validation case read about 4 % low against closed form, so about 51 to 52 ohm is plausible |
| RF sensitivity | er 4.2 / 4.6: 51.6 / 49.7. h 0.19 / 0.23: 49.0 / 53.6. **Prepreg 3313: 34.6** | same |
| LNA_IN 0.2 mm section | 62.8 to 66.6 ohm for 2.48 mm | same; track list `scratch/rf_probe.txt` |
| USB, w 0.28 s 0.20 | 92.2 to 93.9 ohm by gap (designer 91.2). 0.2 mm MCU section 106 ohm, 5.3 to 5.9 mm | `scratch/fd2d.py` |
| USB skew, through-path, B-side pads | D+ 36.67, D- 35.75 mm: 0.92 mm, about 5 ps | hand sum from `scratch/net_probe.py` |
| Feed length | 15.43 mm pin to land, no vias; 78 degrees at lambda-g 71 mm | `pcb q net LNA_IN`, `RF1`, `RF2` |
| Pin 1 to C20 | 3.19 mm centre; 3.83 mm along the line (19 degrees) | `pcb q dist U1.1 C20.1`, track sum |
| C23 to antenna land | 5.5 mm along the line | track sum |
| Fence pitch | South 5.2, 1.7, 1.6, 1.15, 1.25, 1.2 mm; north 2.8, 0.85, 1.2, 1.2, 2.2 mm; none near the pin (2.05 to 2.45 mm off). Lambda/20 = 3.6 mm | `scratch/rf_probe.txt` |
| XIN to RF row | 0.99 mm edge to edge; 0.58 mm to C20.1 pad | track coordinates |
| Ground between them | No F.Cu fill at x 147.6 to 148.2; no via from x 146.3 to 151.5 | `scratch/xtal_probe.txt` |
| Keepout fill, 0.05 mm raster | In1 0.265, In2 0.265, B.Cu 0.238 mm^2, all the y = 111.00 boundary row. F.Cu 0.995 mm^2: GND tabs plus fill reaching y = 111.10 | `scratch/rf_probe.txt` |
| Keepout items | Only RF2 and the J5 GND tabs; 0 vias, 0 parts | same |
| Decoupling U1 | C7 1.57, 1.58; C9 1.46; C10 1.19 (pin 56), 1.22 (pin 55); C13 1.88; C14 2.18; C11 2.83; C12 4.55 mm | `pcb q decoupling` |
| Cap GND via | C13 2.20, C10 1.91, C14 1.88, C7 1.70 mm | `pcb q decoupling` |
| EN | 28.65 mm net; C17 7.62 mm from pin; passes the keepout at 1.375 mm | `pcb q net EN`, `dist` |
| GPIO0 | 31.9 mm; R3 14.82 mm from pin | `pcb q net`, `dist` |
| XTAL | XTAL_P 3.78, XIN 7.47, XTAL_N 9.20 mm, no vias; Y1 pad 4.90 mm edge from pin 53; L2 2.44 mm edge from pin 54 | `pcb q` |
| LDO headroom | Input 4.20 V, 0.90 V headroom, 0.52 V after 380 mV hot dropout at 500 mA | `calcs:headroom_vs_hot` |
| LDO burst | Peak 496 mA against ILIMIT 810 min. 0.96 W at 600 mA reproduces | SGM2212 table, `calcs` |
| 3V3 drop | 9.79 mV U2 to L1 at 0.35 A; worst 37.4 A/mm^2 | `pcb irdrop` |
| Coverage under U1 | In1, In2 98.3 %; B.Cu 72.9 %; F.Cu 48.7 % | `pcb q coverage U1` |
| Vias | 121, all 0.6/0.3, 76 on GND, 9 in EPAD | `pcb q vias` |
| Fab | 14 files, BOM 27, CPL 46, 0 missing LCSC; offsets J4 0.45, U2 0.85 | `pcb fab` |
| Stock at JLC today | U1 1729, J5 1644, Y1 2933, U2 2374, J1/J2 2110 | JLC parts endpoint |
| Airwires | 0 of 61 nets | `pcb q ratsnest` |
| Regen vs handed-in gerbers | Differ in aperture numbering only: `pcb q nets` and `fps` 0 diff lines, CPL hash equal | `scratch/nets_*.txt` |

## Line-by-line: Espressif guidelines and datasheet

| Requirement | Source | Board | Result |
|---|---|---|---|
| 3.3 V supply, 500 mA or more | HDG 1.3.2, DS 5-2 | SGM2212 800 mA | Pass |
| ESD diode and 10 uF at power entrance | HDG 1.3.2 | D2 bidirectional (JLC attributes, polarity immaterial), C3 | Pass |
| VDD3P3 10 uF, 1 uF, 0.1 uF, LC, 0.1 uF | Fig 1 | C4, C5, C6, L1, C7 | Pass |
| 10 uF per pin 2 and 3 | HDG 1.4.2 text | One shared, per Fig 1; the guideline contradicts itself | Accepted deviation |
| LC near pins, inductor 500 mA or more | HDG 1.3.2, 1.4.2 | L1 900 mA, C7 1.57 mm | Pass |
| Width 25 mil main, 20 mil pins 2, 3, 10 mil other | HDG 1.4.2 | 0.65, 0.5, 0.2 to 0.4 mm; pin necks 0.2 forced by pitch | Near pass |
| Two vias when main power changes layer | HDG 1.4.2 | Two at x 133.3; **one** at (152.85, 115.1) | Partial, minor |
| VDDA 1 uF, 10 nF | Fig 1 | C9, C10 | Pass |
| 0.1 uF close to pins 46, 20 | HDG 1.3.2 | 2.83, 4.55 mm | **Fail, issue 8** |
| VDD_SPI 0.1 uF + 1 uF close, nothing large | HDG 1.3.2 | C13 1.88, C14 2.18 mm | Pass |
| VDD3P3_RTC above 3.0 V via 14 ohm RSPI | HDG 1.3.2 | 3.3 V rail, 10 mV drop | Pass |
| CHIP_PU 10 k + 1 uF | HDG 1.3.3 | R2, C17, 10 ms | Pass |
| CHIP_PU trace as short as possible | HDG 1.3.3 | 28.65 mm | **Fail, issue 7** |
| Flash pins unused | DS 2.6 | 28, 30 to 35 open; VDD_SPI on C13, C14 only | Pass |
| 40 MHz within 10 ppm | HDG 1.3.5 | 10 ppm at room temperature only | Partial, minor |
| 24 nH series on XTAL_P, near chip | HDG 1.3.5, 1.4.3 | L2, 2.44 mm edge | Pass |
| Load caps from CL | HDG 1.3.5 | 12 pF gives 9 pF at Cstray 3 | Pass |
| Crystal 2 mm or more from clock pin; no vias | HDG 1.4.3 | 4.90 mm, no vias | Pass |
| Caps at crystal, ground near crystal ground | HDG 1.4.3 | C15, C16 by Y1 | Pass |
| Clock trace surrounded by ground, stitched | HDG 1.4.3 | XIN and XTAL_N run open, GPIO46 alongside | **Fail, issue 4** |
| CLC close to chip, zigzag | HDG 1.3.6, 1.4.4 | Zigzag yes; 3.83 mm from pin | **Fail, issue 3** |
| 0201 and stub | HDG 1.3.6 | 0402, no stub; HDG waives the stub at 0402 | Accepted deviation |
| 50 ohm, consistent width | HDG 1.4.4 | 50.6 ohm, but 2.48 mm at 0.2 mm | Partial |
| Outer layer, no vias, 135 degree bends | HDG 1.4.4 | Yes | Pass |
| Complete adjacent ground, nothing under | HDG 1.4.4 | In1 and In2 solid under the feed | Pass |
| Dense ground vias along RF | HDG 1.4.4, brief | Gaps to 5.2 mm | **Fail, issue 6** |
| Antenna CLC close to antenna | HDG 1.4.4 | Present, 5.5 mm away | Partial, minor |
| Antenna ESD | HDG 1.3.6, Fig 1 NC | No footprint | Disclosed, minor |
| Antenna away from crystal | HDG 1.4.4, 1.4.11 | Y1 1.64 mm from the feed | **Fail, issue 4** |
| U0TXD 499 ohm | HDG 1.3.7 | R4, 4.26 mm from pin | Pass |
| Strapping: GPIO0 pull-up, no big cap; 45, 46 low; 3 float | HDG 1.3.9, DS 3 | R3 10 k; no external parts on 45, 46, 3 | Pass |
| GPIO19 D-, GPIO20 D+ | HDG 1.3.13 | Pins 25, 26 through R6, R5 | Pass |
| Series R and shunt C near chip | HDG 1.3.13 | R5, R6 5.3 to 5.9 mm line; C18, C19 about 15 mm away, DNP | Partial, minor |
| USB 90 ohm +/-10 %, ground vias at transitions | HDG 1.4.8 | 92 to 94 ohm; `return_via` rows pass | Pass |
| ESD at connector | Brief | U3 about 5 mm from J3, flow-through pads | Pass |
| EPAD 9 or more vias, gaps in paste grid | HDG 1.4.2 | 9, on grid gaps, 65 % paste | Pass, issue 17 |
| EP size for this variant | DS fig 7-2, 5.6/5.7/5.8 | Land 5.6 | Pass |
| In-package constraints | DS 1-1, 2-14, HDG 1.3.4 | Quad flash and PSRAM, 33 to 37 free, SPICS1 used by PSRAM | Pass |
| GPIO number on pins 36, 37 | DS tables 2-4, 7-1 | **Swapped** | **Fail, issue 2** |

## RF rework

- **50 ohm.** At w 0.32, gap 0.25, the 0.2104 mm prepreg, er 4.4, the field solve gives 50.6 ohm, so the designer's 49.7 stands. JLC's page confirms the stackup figures the log took from memory.
- **What depends on unconfirmed numbers.** Finished prepreg thickness and er at 2.4 GHz are nominal. +/-10 % on height moves Z0 49 to 53.6 ohm, which is fine. Choosing another stackup is not fine: 3313 gives 34.6 ohm.
- **Pi match.** Values sit in HDG table 6, but that table applies only if the layout follows the HDG chapter. It does not, so treat them as a starting guess.
- **Keepout.** Lands match Johanson p2/p6 and the clearance is 4.0 x 6.0 mm behind the lands. Rasterised, it holds on all four layers, including In1 and In2. The designer's `tools/keepout.py` tests only the centre point; the claim holds anyway. The one exception is F.Cu fill reaching 0.1 mm past y = 111.0.
- **Terminal map.** Page 2 and page 6 show the same part rotated 180 degrees: the red mark sits on the long-axis centreline and moves from the left end to the right end. So the **mark end is the feed end**. Footprint at KiCad rotation 90 puts terminal 4 at (158.0, 114.5), matching Function 2 and page 6.
- **Inset.** 0.4 mm against flush on the datasheet. Small detune expected, disclosed.

## Regulator during the Wi-Fi burst
Holds. The input stays at 4.20 V or above, with 0.52 V margin after worst-case dropout. Peak 496 mA is well under the 810 mA minimum limit. Dissipation of 0.96 W at 600 mA reproduces, but the Tj of 93.8 C uses the datasheet's 56 K/W. This board has a 37 mm^2 tab with no pour and no via on it. I estimate 70 to 90 K/W, so 107 to 126 C if 600 mA were sustained. It is not sustained: real average load is well under that. No load-step calculation exists; 9.8 mV of IR drop and local bulk make it low risk.

## CPL audit

**Method.** `pcb fab` writes KiCad rotation unchanged (`pcbcli.py` lines 573 to 586); no correction exists anywhere. For each part I took the KiCad zero from pad coordinates, the needed physical orientation from the datasheet, then looked for JLC's zero. I could not get JLC's zero for these parts directly:
- EasyEDA's library API returned CloudFront 403 "Request blocked". I did not retry it or route around it.
- JLC's parts endpoint has no rotation field; its detail endpoint returned 400.
- So the evidence is the community table `cpl_rotations_db.csv` from matthewlai/JLCKicadTools, saved in `scratch/dl_rot/`. It records KiCad footprint to JLC corrections. It is not JLC's record for these LCSC numbers, and I do not know its age per row.

| Ref | Part | CPL | Correct physical result | Evidence | Would need | Call |
|---|---|---|---|---|---|---|
| J3 | USB-C | -90 | Opening west | **Exact table row, 180** | +90 | **Wrong, high confidence** |
| U1 | ESP32-S3 | 180 | Pin 1 SE | No row for this footprint; `RP2040-QFN-56` and QFN-16 to 40 rows say 270 | 90 by class | **Probably wrong** |
| U3 | USBLC6 | 0 | Pin 1 NW | `^SOT-23` prefix says -90, but the row may mean 3-pin; `SC-74-6` and `TSOT-23` say 180 | -90 or 180 | **Probably wrong, value unclear**. At 180 its GND pin lands on VBUS |
| J4 | JST SH | -90 | Opening west | No row; `JST_GH_SM`, `JST_PH_S` say 180 | +90 by analogy | **Suspect** |
| U2 | SGM2212 | 0 | Tab east | No row; `SOT-223` says 180 | Unknown | **Unconfirmed** |
| D1 | B5819W | 180 | Band east, at x 119.5 | No row | Unknown | **Unconfirmed**; reversed means no USB power |
| LED1 | KT-0603R | 0 | K west | No row | Unknown | Unconfirmed, cosmetic if wrong |
| LED2 | KT-0603Y | -90 | K north | No row | Unknown | Unconfirmed, user LED dark if wrong |
| J5 | Antenna | 90 | **Mark south** | No row, no record | Unknown | **Unconfirmed, critical**. 180 puts a GND terminal on the feed land and the body looks the same either way |
| Y1 | FA-238 | 0 | Pad 1 SW | No row | 0 or 180 | Harmless: pins 1/3 and 2/4 swap. 90 cannot land |
| SW1, SW2 | SKRPACE010 | 90 | Long axis north-south | No row | 90 or -90 | Harmless: 180 swaps two equivalent contacts. 90 cannot land |
| D2 | PESD5V0S1BA | 90 | Either way | Bidirectional | Any | Safe |
| R, L, C | | | | Not polarised | Any | Safe |

Not confirmed: JLC's actual library zero for every part above, including J3, and whether JLC's review step would catch each case. The offsets on U2 (0.85 mm) and J4 (0.45 mm) also need the preview. To settle all of this, upload the package to JLC's order flow and read the placement preview, without paying. J5 needs a zoomed look at the red mark, or an order note.

## Issues

### Blocker

**1. CPL rotations are uncorrected.** Evidence: table above; `fab/esp32s3_devkit_cpl_jlcpcb.csv` equals KiCad rotation for all 46 parts. J3 has an exact-footprint correction of 180 that was not applied. Assembled that way the board has no USB and no power. Fix: as listed under Verdict, and add a per-footprint correction to `pcb fab`. Under an hour, no copper change.

### Majors

**2. GPIO47 and GPIO48 are swapped.** DS tables 2-4 and 7-1: pin 36 is GPIO48, pin 37 is GPIO47. The netlist puts net GPIO47 on U1.36 and GPIO48 on U1.37; `PINMAP.md`, `README.md` and silk follow it. Firmware driving GPIO47 moves the pad labelled 48. The designer checked Table 2-1, which only gives SPICLK_N/P. Fix: swap labels and nets; no copper change. The rubric's example list would call a wrong netlist pin map a blocker. I rate it major because no circuit function breaks and the fix is a relabel. Say if you read it the other way: blockers become 2, and Electrical drops to 6 at most, which it already is.

**3. Chip match sits 3.83 mm down the line from pin 1.** HDG 1.3.6 says close to the chip. The first 2.48 mm is 0.2 mm wide, 63 to 67 ohm, with no ground vias within 2 mm. That is 19 degrees of line before the first shunt, so HDG table 6 no longer applies, and the 35 ohm target is harder to reach. Fix: move C20 and L3 to within about 1 mm of the pin, 0.32 mm from the first bend. Needs the VDD3P3 network moved, so a local re-layout.

**4. Crystal sits against the RF row.** XIN runs 0.99 mm from it, and 0.58 mm from the C20.1 pad. The log says "about 2 mm ... with a ground fence between". There is no via across 5.2 mm, and no fill at x 147.6 to 148.2. Y1 is 1.64 mm from the feed. GPIO46 passes 0.22 mm from the XTAL_N pad, with 11.8 mm within 1.5 mm of crystal nets. HDG 1.4.3, 1.4.4 and 1.4.11 all warn against this; 40 MHz multiples land at 2400, 2440 and 2480 MHz. Fix: move Y1 south-west away from the feed, put a stitched ground strip between, and route XIN away from y 119.55.

**5. J5 orientation has no guard.** Nothing on the board, footprint or order states it. `BRINGUP.md` 1.1 says "terminal 4 at the south inner land", but terminal numbers are not printed on the part. Only the red mark is visible. A 180 degree error puts terminal 2, GND in both functions, on the feed. Fix: a mark on the footprint and silk, "red mark toward the feed" in the bring-up, an order note.

**6. Via fence has gaps.** Log: "1.2 mm nominal pitch, both sides". Measured 0.85 to 5.2 mm, with none near the pin. The 5.2 and 2.8 mm spans run at the match; 5.2 mm exceeds lambda/20 of 3.6 mm. Fix: vias at about (147, 119) and (150, 117.2), and on the LNA_IN stretch, once issues 3 and 4 free the space.

**7. EN and GPIO0 are long and run beside the antenna.** EN is 28.65 mm against HDG 1.3.3 "as short as possible". C17 is 7.62 mm from the pin, and R2 and R3 are at the far end. EN passes 1.375 mm from the keepout on a 21 dBm radio. Stray resets are the risk. Fix: put C17 and R2 within 2 mm of pin 4, or at least C17.

**8. C11 and C12 pass only on limits set from the layout.** C11 2.83 mm at limit 3.3, C12 4.55 mm at 4.6, global 4.6. Disclosed by the designer, not defended. With a 2.0 mm limit both fail (`pcbcheck_review.json`). Fix: bring both within 2 mm, or give each a via from the plane side.

**9. Stackup is not in the fab package.** `fab/` and `README.md` never name it; only `DESIGN_LOG.md` and `SUMMARY.md` do. On 3313 the 15.4 mm feed becomes a 35 ohm line of 78 degrees. Fix: a fab note, and name the stackup on the order.

### Minors

10. `return_via` fails: GPIO35 2.34 mm, GPIO45 2.82 mm, limit 2.0. Assumed 3 ns edge. Add vias if the space appears.
11. `gnd_islands`: 11 accepted over 0.5 mm^2, and `regen.sh` uses `--min-mm2 1.5`. The brief says islands get a via. The reason offered, slivers between header pads, does not fit F.Cu (107.6, 107.2), B.Cu (116.2, 117.1) or B.Cu (135.5, 114.5).
12. Silk labels: top lacks 17, EN, 38, 39, 43, 45, 46 and the last GND, including straps 45 and 46, which an owner most needs to see; bottom lacks 47 and prints 48 as a bare number. 13 overlaps: 3V3 on 18, 33 and 34 on TP rings, 36 and 37 on LED1.
13. Refdes exist only as a bottom-side list, not beside parts. `silk` row passes, but C7, C13 and L1 are hard to find from the top where they are probed.
14. J4 mating face is 0.62 mm inside the edge. Brief says flush; not disclosed.
15. COUT: 22 uF nominal on 3V3, about 12 uF effective by my estimate, against 1 to 10 uF in the SGM2212 table. C4 is far from the LDO, so low risk. Unmeasured.
16. Thermal: 56 K/W is the JEDEC figure, not this board. See the regulator section.
17. EPAD: 9 open 0.3 mm vias in the top pad, tented below; fill not specified. Paste corners stay 0.04 mm clear of the drills; the log's 0.165 mm overlap is on the ring.
18. Wrong log numbers, right design: dropout 280 mV is 25 C only, 380 mV over TJ. 0.82 mm is about 5 ps, not 22 ps. "12 pF E24" passes over 13 pF, also E24.
19. Crystal stability over temperature unverified, as disclosed. FA-238 generic sheet: +/-30 ppm, -20 to 70 C.
20. No antenna ESD footprint, disclosed; Fig 1 reserves one.
21. C18, C19 about 15 mm from the chip, HDG says close; DNP, disclosed.
22. VDD3P3 branch has one via and a 0.3 mm neck, against "two vias". 9.79 mV, so electrically fine.
23. C23 is 5.5 mm from the land; HDG 1.4.4 says as close as possible.
24. No RF test launch. `BRINGUP.md` step 7.3 needs a port at the chip side with U1 fitted and offers no point for it.
25. F.Cu fill reaches 0.1 mm into the keepout at the north edge.
26. CPL origin offsets U2 0.85, J4 0.45 mm.
27. `PINMAP.md` omits HDG table 12: USB-OTG download mode drives GPIO38, 39, 40 and reads 21, 41, 42.
28. Cap GND vias: C13 2.20, C10 1.91, C14 1.88, C7 1.70 mm. HDG asks for close.
29. D2, L1, L3, C20 and the LEDs have no datasheet in `docs/`, so their footprints are not checked against a drawing. L1 tolerance is the Murata S code, against 0.1 nH in Fig 1 (from memory of the code).

## Overclaims

| Designer said | Measured |
|---|---|
| XIN "about 2 mm from the RF row with a ground fence between" | 0.99 mm, 0.58 mm to C20.1; no via across 5.2 mm, fill absent at x 147.6 to 148.2. Their own `exposure:XIN` row showed 2.8 mm within 1 mm |
| "Via fence ... 1.2 mm nominal pitch, both sides" | 0.85 to 5.2 mm, none near the pin |
| "two vias at the layer change" | True at x 133.3, one at the VDD3P3 branch |
| Pin names "compared to DS table 2-1" | That table cannot catch 47/48; Tables 2-4 and 7-1 show the swap |
| `calcs:z_rf_ohm`, `calcs:z_usb_ohm` | Hard-coded literals. They pass whatever the board does. Numbers happen to be right |
| 22 ps skew | About 5 ps |
| Dropout "280 mV max at 500 mA" | 25 C only; 380 mV over TJ |

Every count in `SUMMARY.md` reproduced: ERC, DRC plain and packed, pcbcheck, regen, fab, BOM, CPL, vias.

## Check-config audit
- **Accepted warns:** `gnd_islands` disputed (issue 11). The two `test_points` warns accepted: a test point on those nodes would add a stub or load.
- **Limits from layout:** C11 3.3, C12 4.6, global 4.6 disputed. Also C3 at 7.0 mm against U2.2, which I accept: its edge distance is 0.665 mm and the pad is large. C20 had no row.
- **RF2 skip:** the reason holds, 0.7 of 6.4 mm by the datasheet. But it exempts the whole net. I sampled the rest: In1 and In2 solid.
- **Exposure:** no `max_mm`, so it can never fail. No aggressor row for XIN or XTAL_N.
- **Brief items with no row:** keepout, fence, match distance, stackup, feed width and gap.
- **Rows added** in `review_checks.json`: U1 pins 36, 37 and 6 more, J5, U3, RF signals, 2.0 mm decoupling, crystal aggressors, hot dropout. Result: 11 fails, 11 warns, 212 passes. `decoupling:U2.3` and `C14` fail only because of my tighter global limit; `refplane:RF2` fails only because I removed the skip. Neither is an issue.
- **Not checked by any tool:** `feed_room`, `refstat`, `basic_parts`; `irdrop` I ran by hand. `pcb block` gates were not re-run.

## What is good
- Netlist right on all 57 U1 pins but two, and on U2, U3, J3, J4, J5, Y1 and both switches, checked against drawings.
- Feed impedance and USB impedance right, and the from-memory stackup numbers right.
- Antenna land pattern, terminal map and four-layer keepout right. That is the hardest part of this board and it was done properly.
- Power tree sound; the TO-252 reasoning over SOT-223 is correct.
- Regenerates from clean: two passes identical, nets and placement equal to the handed-in board.
- `SUMMARY.md` is candid: it names the weak spots and limits itself, which is why several findings here were easy to verify.

## Layout quality: 5
Good: the nested GPIO bands are clean and consistent, 35 nets by hand with no DRC error. USB runs as a tight pair with flow-through ESD. Power is correctly sized, ground stitching is generous away from the RF end, and In1 and In2 are unbroken.

Weak: the chip sits 14 mm from the antenna to clear the fan-out, so the feed wraps around the VDD3P3 network and over the crystal. EN and BOOT parts sit at the far end of the board from their pins. The DPAK takes the board's middle with no copper to spread heat. F.Cu ground is chopped into strips, and silk collides where it matters. It reads as routing solved well inside a floor plan that was never rearranged for RF.

## Evidence limits
No RF measurement, simulation of the antenna, or thermal measurement. The field solver is quasi-static and 2D. Wi-Fi range and thermal figures are estimates and are labelled as such.
