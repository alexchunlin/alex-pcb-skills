# Ordering the two C2 boards (spike #3): packages, stock, quote inputs, checklist

Prepared 2026-11-03 on branch `spike/3-conventions`. Nothing has been ordered; the order is Alex's. Numbers below come
from the archived boards in `examples/`, `pcb fab` run on copies under `/tmp/spike3/fab/`, and the JLC parts cache
`tools/bench/data/jlc_parts.json` (fetched 2026-11-03).

| | Rung-1 Sonnet attempt 2 | Rung-2 Opus attempt 2 |
|---|---|---|
| Archive | `examples/rung1-zener-a2-sonnet/board/qwiic_imu.kicad_pcb` | `examples/rung2-zener-a2-opus/board/motor1.kicad_pcb` |
| Review | 9 / 9 / 8 | 8 / 8 / 7 |
| What the order tests | first-power pass; WHO_AM_I 0x6A at 0x6B | rails within 3 %, motor under PWM, IPROPI 2.49 V at 2 A, LDO and J3.1 temperature |

## Fab packages: verified complete

`pcb fab BOARD --out DIR --no-render` on a copy of each board (the archive is never written):

| Item | Rung 1 | Rung 2 |
|---|---|---|
| Gerber zip | 14 files: F/B Cu, In1/In2 Cu, F/B mask, F/B paste, F/B silk, Edge.Cuts, drill + drill map, job | same 14 |
| BOM (JLC format) | 5 lines, 0 without LCSC | 29 lines, 0 without LCSC |
| CPL (JLC format) | 8 parts | 44 parts |
| DNP | J3 (the 1x4 header) | none |
| CPL origin off the body centre, mm | J1 0.45, J2 0.45 | J1 1.89, J2 0.45, J3 5.24, J4 8.96 |

Regenerate before uploading, from the commit you order:

```sh
mkdir -p /tmp/order/r1 /tmp/order/r2
cp examples/rung1-zener-a2-sonnet/board/qwiic_imu.kicad_p* /tmp/order/r1/
cp examples/rung2-zener-a2-opus/board/motor1.kicad_p* /tmp/order/r2/
skills/kicad-design/scripts/pcb fab /tmp/order/r1/qwiic_imu.kicad_pcb --out /tmp/order/r1/fab
skills/kicad-design/scripts/pcb fab /tmp/order/r2/motor1.kicad_pcb --out /tmp/order/r2/fab
```

## Stock today (2026-11-03, JLC parts API)

Every LCSC line on both boards is in stock. The thinnest eight:

| LCSC | Part | Board | Library | Stock | Unit @ 1 |
|---|---|---|---|---|---|
| C16072 | AO4407A | rung 2 (Q1) | extended | 1,154 | $0.34 |
| C19193807 | XDFH-0254-2*5P header | rung 2 (J3) | extended | 3,989 | $0.21 |
| C263274 | TPS54620RHLR | rung 2 (U1) | extended | 6,358 | $1.71 |
| C265092 | BM05B-SRSS-TBT | rung 2 (J2) | extended | 6,722 | $0.46 |
| C148219 | SMAJ18A | rung 2 (D4) | extended | 10,982 | $0.11 |
| C1855818 | DRV8874PWPR | rung 2 (U2) | extended | 13,913 | $1.01 |
| C474892 | KF350-3.5-2P | rung 2 (J1) | extended | 16,094 | $0.12 |
| C967633 | LSM6DS3TR-C | rung 1 (U1) | extended | 19,514 | $1.46 |

Re-run before ordering: `python3 -I tools/bench/jlc_parts.py fetch <both boards>`, then the `basic_parts` row
(`pcb check` with `"basic_parts": {"boards": 5}`) fails any line under quantity x boards.

## Quote inputs

From `tools/spikes/spike3/order_inputs.py` (results in `tools/spikes/spike3/results/order/`):

| Input | Rung 1 | Rung 2 |
|---|---|---|
| Size | 25.5 x 25.5 mm, 2 mm corner radius | 50.1 x 40.1 mm |
| Layers / thickness | **4** / 1.6 mm | 4 / 1.6 mm |
| Copper | 1 oz outer, 0.5 oz inner | 1 oz outer, 0.5 oz inner |
| Smallest track / via / drill | 0.25 / 0.6 / 0.3 mm | 0.2 / 0.6 / 0.3 mm |
| Board setup clearance | 0.14 mm (R1-A2S-2; JLC 4-layer floor is 0.09) | 0.2 mm |
| Vias | 26 | 64 |
| Surface finish | HASL lead-free (default; ENIG if the LGA-14 pads print badly) | HASL lead-free |
| Assembly side | top only | top only |
| BOM lines / parts | 5 / 8 | 29 / 44 |
| SMD / through-hole joints | 36 / 0 | 126 / 16 (J1 screw terminal, J3 2x5 header, J4 XT30) |
| Extended types (feeder fee) | 2 ($6.14) | 17 ($52.19) |
| Parts per board | $1.90 | $6.00 |

Economic PCBA estimate from JLC's published fees (setup $8.18, stencil $1.53, $0.0016 a joint, $3.07 an extended type,
hand solder $3.58 an order plus $0.0164 a joint), parts at the 1-piece price, **bare boards and shipping not
included** (JLC's quote page shows them only in its form):

| Quantity | Rung 1 assembly + parts | Rung 2 assembly + parts |
|---|---|---|
| 2 (JLC's minimum) | $19.77 | $78.42 |
| 5 | $25.65 | $97.82 |
| 50 | $113.89 | $388.89 |

Corrections to the literature review's figures: the rung-1 board is **4 layers**, not 2 (`pcb q edge`: copper layers 4),
so its bare-board line is the 4-layer price, not the 2-layer $2-5; and the basic-alternative saving on rung 2 is one
drop-in 0402 part (C13 22 nF, C1532), not five (see the spike report, C2).

## Known issues on the boards as archived (order them anyway: the C2 hypothesis needs these measured)

- Rung 2, R2A2-O-1: J3.1 (5 V header pin) is fed by four 0.3 mm In2 spokes; `irdrop` rates the worst spoke at 0.98 A
  against IPC 0.41 A (x2.38) at 3 A. Bring-up step 6 puts 3 A through it: put the thermocouple on J3.1 for that step.
- Rung 2, R2A2-O-2: C17 bulk cap through single 0.3 mm vias in series (x2.05 at its 2.5 A ripple row).
- Rung 2, new from `irdrop`: L1.2's 3 A of 5 V reaches In2 through two single 0.3 mm vias (1.52 / 1.48 A, IPC 1.22 A each).
- Rung 2, R2A2-O-3: AMS1117 with no 3V3 pour; the log claims 116.5 degC at 500 mA; kicad-analysis-suite says 77 degC
  at its pads with the LDO alone (unvalidated). Step 7 measures it.
- Rung 2: open TVS clamp question (SMAJ18A above the buck's 20 V abs max) and no header back-feed protection: power
  from J4 only.
- Rung 1: setup clearance 0.14 mm (manufacturable at JLC), CPL origin of J1/J2 0.45 mm off the JST body.

## Checklist (Alex)

1. Pick the commit; regenerate both fab packages with the commands above; open each gerber zip in JLC's viewer and
   check the outline, the four copper layers in order (F, In1, In2, B) and the drill.
2. Re-fetch stock (`jlc_parts.py fetch`) and run `pcb check` with `basic_parts`; no fail rows.
3. JLC order, PCB: 4 layers, 1.6 mm, 1 oz outer / 0.5 oz inner, HASL lead-free, green, quantity 5 (2 is the minimum
   if cost matters; the fixed fees stay the same). Board 1 is 25.5 x 25.5 mm, board 2 50.1 x 40.1 mm.
4. PCBA: Economic, top side, quantity 5 (or 2). Upload `*_bom_jlcpcb.csv` and `*_cpl_jlcpcb.csv`.
5. In JLC's placement review: fix rotation and offset of J1/J2 (both boards, 0.45 mm) and on rung 2 J1 (1.89), J3
   (5.24), J4 (8.96); confirm U1/U2 pin-1 marks against the silk dots; confirm the DRV8874 and TPS54620 thermal pads
   get paste.
6. Rung 2 through-hole parts (J1, J3, J4, 16 joints): either JLC hand soldering (about $3.58 + $0.26 a board) or leave
   them off and solder them yourself.
7. Record the quote at 5 and at 50 (bare board, assembly, parts, shipping) in the spike issue; that closes the "quote"
   question the spike could not answer from the API.
8. On arrival: print `tools/spikes/spike3/results/jig/pogo_plate.stl` (PLA, flat, no supports; P75 pins pressed into
   the 1.1 mm holes, two M2.5 standoffs through H1/H2), and run
   `uv run --no-project --python 3.12 --with openhtf python3 -I tools/spikes/spike3/bringup/bringup_htf.py
   examples/rung1-zener-a2-sonnet/board/BRINGUP.md --out <dir>` with a real instrument plug in place of
   `SimInstrument`.
