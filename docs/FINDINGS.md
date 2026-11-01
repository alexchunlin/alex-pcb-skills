# Findings: agent-driven KiCad PCB design

Running evidence log, in the style of `alex-3d-skills/docs/FINDINGS.md`. Every rule, check or tool in this repo
points at an ID here. IDs: `P0-Tn` = phase 0 tool/prior-art measurements; `R1-Zn-Tn` = rung 1, Zener path, attempt
n, observation; `R1-Sn-Tn` = rung 1, SKiDL path; `Rk-...-Fn` = a reviewer finding; `Rk-...-Rn` = the reviewer's
own process.

Sources:
- `REF` = `/tmp/pcb-ref/` (clones of the two reference repos, kicad-druid, scratch; re-clone if gone)
- `RUNS` = `~/code-stuff/alex-pcb-runs/` (design attempts; one directory per rung, path and attempt)
- `SESS` = this repo's Claude project dir under `~/.claude/projects/-Users-alxchunlin-code-stuff-alex-pcb-skills/`;
  agent transcripts in `<session>/subagents/agent-<id>.jsonl`
- Machine: macOS, KiCad 10.0.1 (`/Applications/KiCad/KiCad.app`), bundled Python 3.9 with SWIG `pcbnew`, Python 3.14
  system, repo venv Python 3.12 (`.venv`: skidl 3.0.0, easyeda2kicad 1.0.1), Diode `pcb` 0.4.95 at
  `~/.local/bin/pcb`, `kct` 0.26.0 via `uv tool`.

---

## Phase 0: prior-art measurements (2026-10-31)

- **P0-T1 kicad-cli is fast enough to run after every edit.** On the MotorGo Plink board (65 x 56 mm, 4 layers, 117
  footprints, 1,613 tracks, KiCad 8 file read by 10): `sch erc` 3.3 s, `pcb drc --schematic-parity` 16.5 s,
  `pcb render` 1.8 s, `sch export svg` 1.5 s, `sch export netlist --format kicadxml` under 2 s. SWIG `pcbnew` loads
  the board under the bundled Python (prints a harmless wxApp assert on macOS).
- **P0-T2 ERC/DRC do not see the bugs that reached fab.** Shipped Plink v1.0: ERC 177 violations (8 `pin_to_pin`
  errors, 1 `power_pin_not_driven`, 108 `endpoint_off_grid` warnings, 30 `lib_symbol_issues`); DRC 272 violations
  (40 `copper_edge_clearance` errors, 5 `shorting_items`, 5 `solder_mask_bridge`, 3 `courtyards_overlap`, 86
  `lib_footprint_mismatch` warnings) plus 6 unconnected items. None of these is the IMU I2C address mismatch, the
  missing back-power Schottky or the silk readability that the Nov 2024 rework fixed (commit 2179d08). So the raw
  ERC/DRC count is noise to a reviewer and the real findings need intent rows.
- **P0-T3 Netlist connectivity diff works across KiCad versions.** pace-racer's `tools/verify_netlist.py` on the
  Plink netlists at 64e0b5d (pre-rework, June 2024) vs HEAD: lists nets only-before (`/IMU 6 + 3/SDO_acc`, `GNDD`,
  `m1_enc_cs`...) and only-after (`Net-(U10-SD0/SA1)`, `Net-(U11-SDO/SA0)`, `gpio21`...). The IMU fix is visible as
  the SA0/SA1 nets changing from shared to per-device. This is the gate for every scripted schematic edit.
- **P0-T4 `kct audit` (kicad-tools 0.26.0) on both reference boards.** Useful: ERC/DRC summaries, connectivity by
  net, JLCPCB capability table, a cost estimate (Plink 5 boards: PCB $13.64, parts $36.67, assembly $16.66), analog
  net flags (U6 COMP/VSENSE, isense-a/b/c, vref-1v6). Wrong or noisy: Plink board size reported 174.5 x 116.0 mm
  (true 65.1 x 56.1; pcbnew bounding box), 12 and 47 "orphaned footprints" that are kibuzzard silk logos, "min
  annular ring 0.050 mm FAIL" unverified. Its pure-Python DRC (`kct check --mfr jlcpcb`) crashes on both boards:
  `Unsupported routing geometry 'custom' for pad U6.15` (Plink) and `NT2.2` (Pace). It also declares sidecars
  `*.current_paths.json` (`path_ampacity`) and `*.net_class_map.json` (length/skew rules) that "silently pass" when
  absent: prior art for pcbcheck's declared-current rows, and a footgun (silent pass) to avoid. Runtime 32 s and 52 s.
- **P0-T5 kicad-druid JLCPCB 4-layer rule pack on shipped Plink** (`kicad-cli pcb drc --severity-all` with
  `JLCPCB.kicad_dru` renamed to the board): 1,172 violations, among them 199 `via_diameter` (0.4 mm vs 0.5 min), 128
  `clearance` (0.12 to 0.15 mm vs 0.2), 49 `hole_clearance` (0.20 vs 0.25), 53 `copper_edge_clearance`. The board
  was fabbed and works, so these are the pack's margins over JLC's capability, not defects; the pack is a
  design-margin policy as much as a fab rule. The sentinel rule (`track_width min 99mm`, severity warning) fired on
  every track, so rule-file rejection is detectable. kicad-cli reported exactly 199 of several types: a per-type
  cap, to confirm (`--all-track-errors` is for tracks only).
- **P0-T6 Diode `pcb` 0.4.95 (Zener).** Installer puts `pcb` in `~/.local/bin` and did not edit rc files (PATH
  already had it); it also installs a `pcb-launcher` URL handler. `pcb build blinky.zen` 0.1 s, `pcb layout` 1.4 s,
  writes a KiCad 10 `.kicad_pcb` (version 20260206) plus `.kicad_pro`, `fp-lib-table`, `default.net`; no `.kicad_sch`
  (that is `pcb apply schematic` on a linked project). **`pcb layout` opens pcbnew by default** (`--no-open` to
  stop it): it left a GUI on the board, which is the exact condition pace-racer's style guide warns about (KiCad
  rewrites files from memory on save). `pcb dfm --offline` ran 56 rules (JLC floor PDK `jlc-floor-2026-10-26`,
  17 passed, 1 failed, 38 not applicable on the 2-part blinky) and prints JSON. `pcb test` ran no tests on blinky.
  The stdlib is generics only (R, C, L, LED, crystal, ferrite, TVS, Zener, op-amp, pin header, solder jumper, test
  point, mounting hole, fiducial, net tie) with bundled KiCad symbol/footprint subsets; ICs come from registry
  packages (`pcb add github.com/...`) or `pcb new component` from a local KiCad library.
- **P0-T7 SKiDL 3.0.0** installs on Python 3.12, has a `KICAD10` tool target and `generate_schematic`,
  `generate_netlist`, `generate_pcb`, `generate_svg`; it wants `KICAD10_SYMBOL_DIR` (bundled libs at
  `/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols`, 223 files) and an `fp-lib-table`.
- **P0-T8 Stock library coverage for the briefs.** Present: `Sensor_Motion:LSM6DS3`, `Sensor_Magnetic:LIS3MDL`,
  `Sensor_Magnetic:MT6701`, `RF_Module:ESP32-S3-WROOM`, `Regulator_Linear:AMS1117`, `Regulator_Switching:TPS5430`,
  `TPS562*`, `AP63203`, JST SH 4-pin horizontal and vertical footprints. Absent: DRV8874, TPS54620, DRV8353, LSM6DSO.
  Rung 2 therefore exercises part import (easyeda2kicad, JLC2KiCadLib, or the Plink repo's `LCSC_parts` library).
- **P0-T9 Real-bug labels available for the replay bench.** Plink: pre-rework 64e0b5d (fabbed June 2024, "ready for
  order" b2a6386), v1.0 rework fb32540 (fabbed Oct 2024), fixes 2179d08 (IMU I2C mismatch, silk readability,
  back-power Schottky, RC servo pins). Pace: V0R1 built, V1R2 in progress; `docs/errata.md` (195 unspecified pin
  types, 15 drifted symbols, 6 drifted footprints, 5 thin pour necks, C5 DNP), `docs/decisions/0001-0003`,
  `docs/bringup.md`.
- **P0-T10 Transcript telemetry transfers.** `alex-3d-skills/tools/transcript/cc_transcript.py timeline|summary|bash|
  files|usage` runs unchanged on this session's `subagents/agent-*.jsonl` (checked on the survey agents). Harvest of
  the rung-1 designer and reviewer runs uses it as is; `bench` needs a `tools/bench/agents.json` for this repo.

## Rung 1, attempt 1 (started 2026-10-31 ~14:30, two paths in parallel, no skills from this repo)

- Runs: `RUNS/rung1-zener-a1` (Diode `pcb` 0.4.95, Zener) and `RUNS/rung1-skidl-a1` (SKiDL 3.0 + SWIG pcbnew).
  Brief `bench/design/rung1-qwiic-imu/BRIEF.md`; path notes in each run's `PATH.md`; review protocol
  `bench/design/REVIEW.md`. Designers run on the session model via the Agent tool (no Workflow loop yet).
- Guardrails given: no KiCad GUI (`pcb layout --no-open`; a watchdog polls for pcbnew), writes only inside the run
  dir, `progress.md` after every step, real ERC/DRC counts, `SUMMARY.md` at the end.

### R1-S1: rung 1, SKiDL path, attempt 1 (designer `SESS/subagents/agent-acb44e726ce91f38e.jsonl`)

Designer finished in **48.7 min** wall (model 46.1, tools 4.2), 55 API calls, 103 tool uses, 224k output tokens
(139k thinking), 9.3M cache-read, peak context 365k. Claimed: ERC 0 errors / 1 warning, DRC with parity and the
JLCPCB pack 0 violations, full fab package, BOM with LCSC numbers, design log, bring-up. Board render looks like a
real Qwiic breakout (`RUNS/rung1-skidl-a1/fab/qwiic_imu_top.png`): scripted placement, scripted routing, planes,
labelled silk. Reviewer verdict pending (R1-S1-F*).

- **R1-S1-T1 Thinking, not tools, is the wall time.** Three long generations totalled 18.4 min (38% of wall):
  285 s thinking before a `fix_sch.py` edit, 548 s before "regenerate schematic with PWR_FLAG fix, run ERC", 266 s
  before "inspect reference project severities". Tools took 4.2 min in total. Same pattern as A1-T1 in the 3D loop.
- **R1-S1-T2 One 19.8 KB `build_pcb.py` written in a single generation** (placement, routing, zones, silk as data),
  then 9 Edits in 30 s to fix it. The 3D loop's 84 KB script lesson (A1-T4) repeats at smaller scale.
- **R1-S1-T3 schematizer 0.2.0 (SKiDL's schematic drawer) is the weak link.** Normal mode crashed twice
  (`'NoneType' has no attribute 'tx'` with pin-less mounting holes; `ValueError: not enough values to unpack`
  without them); labels mode worked but embedded lib symbols that mismatch the KiCad 10 library (15 ERC warnings),
  kept one Datasheet per lib_id, placed no PWR_FLAGs, ignored DNP. The designer wrote `fix_sch.py` (4.6 KB, then
  grown) to patch the `.kicad_sch` after generation: 11 min including the two long thinks. A netlist-first path
  that drew nothing would have skipped all of it, at the cost of a readable schematic.
- **R1-S1-T4 SKiDL `generate_pcb()` and `generate_xml()` unusable here**: kinet2pcb needs `pcbnew` in the venv (it
  lives only in KiCad's Python 3.9), and the XML writer produced malformed XML. The board was built from the
  `kicad-cli` kicadxml netlist instead. Pin the lesson: SKiDL for the netlist only; pcbnew under KiCad's Python.
- **R1-S1-T5 pcbnew scripting footguns**: `ZONE_FILLER.Fill` segfaults on an in-memory `BOARD()` (save, `LoadBoard`,
  fill, save works); `FOOTPRINT.SetField()` creates visible fields at the footprint origin (398 silk warnings until
  hidden); `FOOTPRINT.GetFieldByName` does not exist in 10.0.1. Each is one library helper.
- **R1-S1-T6 Silk under the rule pack's 0.15 mm silk clearance on a 25 mm board** cost a project footprint library
  (every stock test-point footprint sits at 0.14 mm silk-to-pad). The pack's margins (P0-T5) bite designs, not only
  reference boards; a stock-footprint allowlist or a pcbcheck row with a reason would be cheaper than re-drawing.
- **R1-S1-T7 11 failed bash calls**, 7 of them exploration of library source (`cat` of skidl internals, missing
  modules) in the first 3 minutes. Docs gap, not a design problem.
- **R1-S1-T8 Baseline contamination.** Call #5 (`cat docs/FINDINGS.md; cat docs/SURVEY-2026-10-31.md; cat
  bench/design/REVIEW.md`) read this repo's docs, including the review protocol, so the designer knew what the
  reviewer would measure. Future baseline runs get a run dir with no path back to the repo in the prompt.
- **R1-S1-T9 Images**: 7 reads (0.8 MB); the top render read 3 times, bottom twice. Small, but the 3D rule
  (measure, then look once) applies.

### R1-Z1: rung 1, Zener path, attempt 1 (designer `SESS/subagents/agent-a88094f687245b888.jsonl`)

Designer finished in **57.0 min** wall (model 50.2, tools 6.8), 125 API calls, 124 tool uses, 242k output tokens
(133k thinking), 25.8M cache-read, peak context 435k. Claimed: ERC 0 errors / 1 warning, DRC with parity and the
JLCPCB pack 0 violations + 2 parity warnings (NC pad naming), 38/38 netlist checks, `pcb dfm` 43 passed / 0 failed,
`tools/regen.sh` idempotent (second run reports "schematic unchanged" and identical counts). Render
(`RUNS/rung1-zener-a1/fab/qwiic_imu_top.png`) is a credible board. Reviewer verdict pending (R1-Z1-F*).

- **R1-Z1-T1 Same shape as the SKiDL run: thinking is the wall time.** Four long generations totalled 18.5 min
  (32%): 257 s before the placement half of the layout script, 408 s before the full layout script, 177 s before
  the routing/silk fix. Tools 6.8 min. Cache-read 25.8M vs 9.3M for SKiDL: 125 calls against a 435k-peak context.
- **R1-Z1-T2 The layout script was written three times** (5.3 KB, 13.6 KB, 14.3 KB) at 0:26, 0:34, 0:40, each a
  full heredoc rewrite, not an edit. Together with R1-S1-T2 this is the strongest signal for a placement/routing
  library: both designers wrote the same pcbnew boilerplate (load, place by name, route by coordinates, zones,
  silk, fill, save) from scratch, 20 KB each.
- **R1-Z1-T3 Zener's schematic exporter is the gap, not Zener.** No custom fields on symbol instances (`MPN`,
  `LCSC` reached the footprint but not the schematic), `properties=` dropped on stdlib generics, local labels only
  (22 parity warnings until renamed), bare `lib_id`s (32 `lib_symbol_issues`), and a hard failure on a PWR_FLAG
  symbol ("visible terminal belongs to 0 islands") because every `Component()` demands a footprint. Cost: 9 failed
  builds between 0:16 and 0:20, three helper scripts (`make_symlib.py`, `sync_schematic.py`, `verify_netlist.py`)
  and a power_out test-point workaround for ERC. The same ERC/fields/PWR_FLAG problems hit SKiDL (R1-S1-T3): the
  post-generation fixer is a shared need, whichever front end wins.
- **R1-Z1-T4 pcbnew SWIG footguns, second instance.** `board.Remove()` on loaded items and `GetNetsByName()`
  corrupt the runtime (`SwigPyObject` errors later); `GetFieldByName`/`HasFieldByName` missing in 10.0.1 (also
  R1-S1-T5). Three failed runs at 0:34-0:36 before `Delete()`/`FindNet()`. A `pcblib` wrapper closes both.
- **R1-Z1-T5 Docs gap, measured.** docs.pcb.new has 4 pages; `pcb new component`, placement from code, re-run
  semantics and field mapping were probed empirically (`scratch/probe.zen`, `tools/extract_symbol.py`, 8 min to
  first build). Also small traps: stdlib `CopperFinish("HASL Lead-free")` rejected (wants `"HAL lead-free"`), JST
  footprint rotation semantics, zsh eating `echo =====`.
- **R1-Z1-T6 What Zener gave for free that SKiDL did not:** `pcb layout` re-runs preserve placement (code-as-truth
  held without extra work), `pcb dfm --offline` (43 rules passed), `pcb layout --check`, and a one-command
  `regen.sh` that is idempotent. SKiDL's `check.sh` regenerates too, but through the designer's own `fix_sch.py`.
- **R1-Z1-T7 Connector face sits 0.6 mm inside the board edge** because the rule pack's copper-to-edge clearance
  hits the JST retention tabs; a real Qwiic board has the connector flush. The margin policy (P0-T5) again shaping
  the design; wants a per-footprint exception row with a reason, not a global relaxation.
- **R1-Z1-T8 No repo-doc reads** (grep for `alex-pcb-skills/(docs|bench)` empty): this run is a clean baseline;
  the SKiDL run is not (R1-S1-T8).

### Bake-off, designer side (reviewer scores pending)
| | SKiDL + pcbnew | Zener (Diode `pcb`) + pcbnew |
|---|---|---|
| wall / model / tools (min) | 48.7 / 46.1 / 4.2 | 57.0 / 50.2 / 6.8 |
| API calls / tool uses / bash failures | 55 / 103 / 11 | 125 / 124 / 18 |
| output tokens (thinking) | 224k (139k) | 242k (133k) |
| cache-read tokens / peak context | 9.3M / 365k | 25.8M / 435k |
| long generations >= 120 s | 5, 18.4 min | 4, 18.5 min |
| claimed ERC / DRC+pack | 0 err, 1 warn / 0 | 0 err, 1 warn / 0 (+2 parity warn) |
| schematic | schematizer labels mode + `fix_sch.py` | `pcb apply schematic` + `sync_schematic.py` |
| regeneration | `check.sh` | `tools/regen.sh`, idempotent |
| extra checks | none | `pcb dfm` 43 pass, 38-point netlist self-check |
Both wrote a ~20 KB pcbnew layout script from scratch; both needed a schematic post-fixer; both hit the same
pcbnew API traps. The front end mattered less than the shared missing layer (placement/routing helpers, schematic
field/flag fixer, pcbnew wrapper).

### R1-S1 review (reviewer `SESS/subagents/agent-ab499527302df76bd.jsonl`, 14.6 min, 39 tool uses, 188k tokens)

Scores **9 / 8 / 8** (electrical / manufacturability / documentation). Review at `RUNS/rung1-skidl-a1/review/review.md`.
Verified from the netlist and pcbnew: Qwiic order on both connectors, address jumper 0x6B with correct silk,
pull-ups behind the 3-way jumper, decoupling nets and distances (1.69 to 1.98 mm centre, 0.90 to 1.30 mm edge),
datasheet Table 2 tie-offs, axes vs Fig. 1, 27 tented vias, In1 GND 96.8% under U1, five LCSC numbers mapping to the
stated MPNs, `check.sh` regenerating netlist/board/gerbers/BOM/CPL identically in 17 s.

- **R1-S1-F1 (major) The fab rule pack relaxes the project's own constraints, and the designer reported only the
  pack run.** DRC with the project's board-setup rules and no `.kicad_dru`: 18 errors (6 `hole_clearance`, NPTH
  H1/H2 to the three fills at 0.2005 mm vs the setup's 0.25; 12 `clearance`, adjacent LGA pads 0.150/0.175 vs 0.20).
  With `JLCPCB.kicad_dru` loaded: 0, because the pack's constraints override the setup values with JLC's floor. So
  "DRC 0 with the fab pack" can be weaker than plain DRC. Rule for the loop: run both, report both, and a pack that
  is meant as a floor must never lower a board-setup value (generate it with `max(fab, setup)` or put the margin
  policy in the board setup and keep the pack strictly for fab limits).
- **R1-S1-F2 Overclaims, four**: "DRC 0 violations" (true only with the pack); "every feature 2x the fab floor"
  (planes at 1x the NPTH floor, LGA gaps at 1x); "GND vias within 1 mm" (C1 at 1.21 mm); "up to four boards" on the
  pull-up chain (two boards = 1.1 kOhm = 3.0 mA). All four are the designer summarising instead of measuring; the 3D
  rule "the report carries the number, not the adjective" (A1-F14) applies. A pcbcheck row per claim makes the
  overclaim impossible.
- **R1-S1-F3 (minor) Gerber artefacts from `--board-plot-params`**: 0.35 mm drill-mark flashes at six hole centres
  on copper and mask (`(drillshape 1)`); a plain export has none. The fab export command belongs in a tool, not in
  each designer's script.
- **R1-S1-F4 (minor) CPL mid-point for the JST footprints is the footprint origin, 0.45 mm from the body centre.** A
  known KiCad/JLC convention problem; a `pos` post-processor row.
- Minor: labels-mode schematic with overlapping power symbols (disclosed), gerber job "rev?", no refdes on silk.
- **R1-S1-R1 The reviewer was cheap and precise**: 39 tool uses, every issue with a file and a number, no renders
  needed beyond the designer's. The protocol's "re-run, then diff the claims" step produced F1 and F2 by itself.

### R1-Z1 review (reviewer `SESS/subagents/agent-afe5bc8783b1fe001.jsonl`, 11.3 min, 31 tool uses, 151k tokens)

Scores **8 / 8 / 8**. Review at `RUNS/rung1-zener-a1/review/review.md`. Verified: Qwiic order on J1/J2, JP1 to 0x6B,
pull-ups behind JP2, U1 pin map vs datasheet Fig. 1 (bottom view mirrored correctly), axes, C1 1.75 mm and C2
1.51 mm, In1 GND 93% and In2 3V3 89% under U1, every calculation in the log re-computed, BOM 6 lines with
MPN/Manufacturer/LCSC, 38/38 netlist checks, netlist and the fab pack byte-identical to the designer's.

- **R1-Z1-F1 (major) Same masked DRC as R1-S1-F1.** Without the `.kicad_dru`: 20 errors (12 `clearance` on the
  LGA-14 pads at 0.150/0.175 vs the 0.2 mm the `.zen` itself writes; 8 `hole_clearance` NPTH to four zones at 0.2005
  vs 0.3). Two independent designers, two front ends, one trap: **both ran DRC only with the pack loaded and both
  reported 0.** This is the first tool candidate: a `pcb drc` wrapper that always runs plain and packed, reports
  both, and refuses a pack value below the board setup.
- **R1-Z1-F2 (major) `tools/regen.sh` exits 1 from a clean tree** (`rm -f fab/gerbers/*` on an empty dir under zsh
  "no matches found"), so the fab package is not produced from scratch, and the first from-scratch pass leaves 4
  `isolated_copper` warnings that only a second pass clears. "Code is the source of truth" needs a check that runs
  the regeneration **from a clean checkout** and diffs netlist, DRC counts and the fab zip; idempotence in place is
  not enough.
- **R1-Z1-F3 (minor) C3 bulk cap at 2.64 mm from VDD** (brief: within 2 mm; log claimed 2.9 mm): a distance row.
- **R1-Z1-F4 (minor) Refdes hidden on every part but U1** while BRINGUP.md names JP1/JP2/C1/C3/J3/TP1/TP2: a
  silk-vs-bringup consistency row.
- Minor: BOM lacks a Datasheet column, pos file has KiCad headers, empty title block, SUMMARY "56 min" vs
  progress "2 h 55 min" (the designer's clock claim is unreliable; use the transcript), power_out test-point symbol
  standing in for PWR_FLAG.
- **R1-Z1-R1 Reviewer cost 11 min and 31 tool uses**, found both majors by "re-run without the pack" and "regenerate
  from clean"; neither needed judgment, both are rows.

## Rung 1 conclusion and ranked tool candidates (2026-10-31)

Scores: SKiDL 9/8/8, Zener 8/8/8; wall 49 and 57 min; neither passed 9/9/9 and both for the same reasons.
Twelve findings, of which **nine are the same on both paths**, so they are properties of the loop, not of the
front end. Ranked by (findings x attempts) it would catch, then by cost:

1. **Dual DRC with pack-vs-setup guard** (R1-S1-F1, R1-Z1-F1; both majors). A wrapper, half a day.
2. **Regenerate-from-clean check** (R1-Z1-F2; code-as-truth is otherwise unverified). A script: fresh dir, run the
   regen, diff netlist + DRC JSON + gerber zip hashes. Half a day.
3. **Claim rows in pcbcheck** (R1-S1-F2 four overclaims, R1-Z1-F3, R1-Z1-F4): decoupling distance per cap, via
   distance, pull-up chain current, silk-refdes-vs-bringup, feature-vs-floor ratio. The row carries the number;
   the log cannot overclaim. 2-3 days for the first eight rows.
4. **pcbnew placement/routing helpers** (R1-S1-T2, R1-Z1-T2, R1-S1-T5, R1-Z1-T4): both designers wrote ~20 KB of
   the same boilerplate and hit the same SWIG traps (zone fill on in-memory board, `Remove` vs `Delete`,
   `GetNetsByName`, missing `GetFieldByName`, `SetField` making visible fields). A `pcblib.board` module: load,
   place-by-name with rotation, route-by-waypoints with net class width, zone, fill-save-reload, silk text, export.
   1 week, and it is the layer KiCad 11's IPC swap will land in.
5. **Schematic post-fixer** (R1-S1-T3, R1-Z1-T3): fields onto symbol instances, PWR_FLAGs, global labels, lib_id
   embedding, DNP. Needed by both front ends until upstream fixes land (Diode `pcb` is MIT and active; file issues).
   2 days.
6. **Fab export command** (R1-S1-F3 drill-mark flashes, R1-Z1 pos headers, R1-S1-F4 JST CPL offset): one `pcb fab`
   that does gerbers/drill/pos/BOM the JLC way. 1 day.
7. **Footprint exception rows** (R1-S1-T6 silk clearance on test points, R1-Z1-T7 JST tabs vs edge clearance): the
   margin pack needs per-footprint reasons, not global relaxation. Part of 1 and 3.
8. **Docs for the chosen front end** (R1-Z1-T5, R1-S1-T7): 8 min to first build on Zener, 7 failed exploration calls
   on SKiDL. A reference doc in the skill with the API surface actually used. 1 day, after 1-5 exist.

**Front end.** Zener is the provisional choice for rung 2. Both paths reached the same quality; Zener needed one
maintained tool for build, layout (placement preserved across re-runs), DFM (43 rules offline), lints and the
package registry, while SKiDL needed three third-party pieces of which two were broken on KiCad 10 (schematizer
crashes, kinet2pcb/XML unusable) and the netlist was the only thing it did reliably. Zener's gaps are in its
schematic exporter (fields, labels, PWR_FLAG) and its docs, both fixable by us or upstream. Risks: a young
Starlark language and a VC-backed vendor; mitigation is that the KiCad files and the fab package are the
deliverable, `pcb import` is the way back, and `pcblib` is front-end-agnostic. SKiDL stays as the fallback and
rung 2 will say whether the choice holds at 30 parts.

## Phase 1: `pcb` wrapper and `pcb q` (2026-10-31, second session)

Built `skills/kicad-design/scripts/pcb` (sh) over `pcbcli.py` (plain python3, drives kicad-cli) and `pcbq.py`
(KiCad's Python 3.9, SWIG pcbnew). Commands: `erc`, `drc`, `netlist`, `diff`, `render`, `svg`, `stats`, `fab`,
`q`, `py`, `guard`, and passthrough to Diode's `pcb` with `--no-open` forced on `layout`/`apply` and `open` refused.
`tools/verify_all.sh` re-proves all of it on the two rung-1 attempts and the Plink board: 59 checks, 1 min 40 s.

**Why not the existing code.** kicad-cli already does ERC, DRC, netlist, renders, SVG, stats and every fab export,
so the wrapper calls it and adds only what the rung-1 reviews showed was missing: the second DRC run, the sentinel,
the pack-vs-setup comparison, a temporary mirror so the project is never touched, and one JSON summary per
command. `kct check --mfr jlcpcb` was the candidate for the fab-rule run and crashes on both reference boards
(P0-T4); `kct audit` misreports the board size. pace-racer's `verify_netlist.py` is ported as `pcb diff` with
rename listing and `.kicad_sch` inputs. The pcbnew measurements are the reviewers' `measure.py` turned into
commands so the next reviewer runs them instead of rewriting them.

- **P1-T1 DRC runs on a mirror, not the project.** `pcb drc` copies the project directory into a temp tree that
  keeps two ancestor directory names and symlinks every sibling at each level, so `${KIPRJMOD}/../x` and
  `${KIPRJMOD}/../../.pcb/...` library paths (Zener writes the second form) still resolve. Check: Plink in the
  mirror reports the same 86 `lib_footprint_mismatch` warnings as in place; the attempt's `.kicad_pcb` is
  byte-identical after the run. Cost: dual run 5 s on the rung-1 boards, 33 s on Plink (16 s per DRC with parity).
- **P1-T2 kicad-cli caps each violation type at 199.** The sentinel fired 199 times on Plink's 1,613 tracks, and
  `silk_overlap` and `silk_over_copper` both came back as exactly 199 with the JLCPCB pack (45 and 47 plain).
  `--all-track-errors` is about several errors per track, not this cap. So any count of 199 is a floor, and
  `pcb drc` lists such types under `capped_types` and says so. Confirms the "to confirm" in P0-T5.
- **P1-T3 Floored pack = plain errors plus fab-only errors; raw pack masks.** The JLCPCB 4-layer pack has 19
  constraint minimums below the Zener board setup (clearance 0.127/0.15/0.1/0.09 vs 0.2, hole_clearance 0.2/0.28
  vs 0.3, via_diameter 0.45 vs 0.6, annular 0.05 vs 0.15, edge 0.2 vs 0.4, ...), 18 below the SKiDL setup and 6
  below Plink's. With the raw pack the packed run reports 0 errors on both rung-1 boards while the plain run
  reports 20 and 18 (R1-Z1-F1, R1-S1-F1 reproduced exactly: clearance 12 + hole_clearance 8, clearance 12 +
  hole_clearance 6). `pcb drc` raises every such minimum to the setup value before running (`--no-floor` keeps
  the raw pack and lists the masked errors instead): the floored packed run reports the same 20 and 18, and on
  Plink it adds 11 errors the setup cannot see (hole_to_hole 4, clearance 2 under pad-specific rules,
  assertion_failure 5 for pad size) and 310 warnings. Rule for the loop: the headline number is `errors_total`
  = max(plain, floored packed); "0 with the pack" is never reported alone.
- **P1-T4 A rejected rule file is detectable only by the sentinel.** A pack with `(layer "No.Such")` makes
  kicad-cli exit 0 with a report that silently omits every custom rule; the appended `track_width min 99mm`
  sentinel then fires 0 times on a board with tracks, and `pcb drc` exits 2 with "RULE PACK REJECTED". A pack
  without a `(version 1)` header is refused before the run.
- **P1-T5 pcbnew has no pin types, so "distance to the supply pin" needs the pin named.** `pcb q decoupling`
  picks the nearest IC pad on the cap's net: for C3 (10 uF) that is U1.12 (CS strapped to 3V3) at 2.357 mm, not
  VDD pin 8 at 2.639 mm that the reviewer measured. The command now lists every IC pad on the net with its
  distance; the pcbcheck row (phase 2) will declare the pin. Also: plane coverage under U1 on In1.Cu is 96.1 %
  by polygon intersection against the courtyard box, vs the reviewer's 93.1 % on a 40 x 40 point grid; both
  say "plane present", and the polygon number is the one the check will use.
- **P1-T6 SWIG footguns, third batch (handled in pcbq.py).** `BOX2I.Merge()` into a bbox returned by
  `GetBoundingBox()` aborts the interpreter (Abort trap 6); copy it into an own `BOX2I(origin, size)` first.
  `LSET(layer)` has no single-layer constructor in 10.0.1 (use `LSET.Seq()` on the item's own set). Footprint
  fields are read by case-insensitive name because Zener writes `Lcsc`/`Mpn` on footprints (R1-Z1 layout script
  renamed them by hand).
- **P1-T7 `pcb fab` reproduces R1-S1-F4 automatically.** It measures each footprint's origin against the centre
  of its `F.Fab` outline and flags offsets over 0.1 mm: J1 and J2 (JST SH horizontal) at 0.45 mm, the exact
  figure the reviewer found by hand. Gerbers are plotted from an explicit layer list derived from the board's
  copper count, never `--board-plot-params` (R1-S1-F3's drill-mark flashes came from the stored plot settings);
  the Edge.Cuts gerber has 0 flashes. Package: 11 layers + merged PTH/NPTH drill + map + job = 14 files, Protel
  extensions; BOM grouped by (value, LCSC, footprint) from footprint fields with the designators lacking an LCSC
  number listed; CPL with JLC headers in KiCad's frame (absolute origin, Y negated as kicad-cli exports it);
  `fab.json` carries a sha256 per gerber member so the regen-check (phase 1 item 2) can compare packages
  without zip timestamps. 21 s, of which 18 s are the two high-quality renders.
- **P1-T8 Diode `pcb` name collision turned into a guardrail.** The wrapper is also called `pcb`; any subcommand
  it does not own goes to `~/.local/bin/pcb`, with `--no-open` inserted on `layout` and `apply` (P0-T6) and
  `open` refused. `PCB_DRY=1` prints the command instead of running it, which is how verify_all tests it.
- **P1-T9 `pcb regen-check` (handoff item 2) reproduces R1-Z1-F2 without judgment.** It copies the project, deletes
  the declared generated paths, runs the project's regeneration command twice and compares netlist connectivity,
  DRC counts, fab member hashes and footprint/track placement against the handed-in tree and between passes. On
  rung1-zener-a1: `tools/regen.sh` exits 1 both times (`no matches found: fab/gerbers/*`), pass 1 reports 12
  errors and 4 warnings, pass 2 converges to the handed-in 20 and 0; placement and tracks are identical
  throughout. Fab hashes drop three timestamp lines per file (`%TF.CreationDate`, the drill `; ... date` header,
  and the `G04 Created by KiCad ... date` comment, which the first version missed) so Edge.Cuts hashes equal
  across passes while F.Cu differs, which is the zone-fill difference and real. 93 s per project before
  `--no-render`, about 60 s after.
- **P1-T10 The SKiDL regeneration also diverges on its first pass from clean, and nobody had seen it.** `check.sh`
  exits 0 from a clean tree, but pass 1 has 12 DRC errors against 18 on pass 2 and in the handed-in tree: the
  6 `hole_clearance` errors (NPTH to zone) are missing because the first fill of a freshly built board differs
  from a refill. The R1-S1 reviewer ran `check.sh` with the generated files present and saw "identical". Same
  mechanism as the Zener isolated-copper warnings. Rule: the fill-save-reload-refill sequence belongs in
  `pcblib.board` (item 4), and regen-check's pass-1-vs-pass-2 comparison is the gate.
- **P1-T11 `pcbcheck` v0 (handoff item 3) turns the rung-1 overclaims into rows.** Nine checks over the kicadxml
  netlist and pcbnew, `checks.json` declares the intent, undeclared power nets, connectors, jumpers and test
  points fail (cadcheck's rule). With `examples/rung1-zener-a1/checks.json` the Zener board fails exactly two
  rows: C3 to U1.8 at 2.639 mm against 2.0 (R1-Z1-F3) and 10 of the 11 refdes named in BRINGUP.md hidden on
  silk (R1-Z1-F4); 22 rows pass, among them the Qwiic pin order on J1/J2, the SA0 strap resolving to 0x6B
  through JP1, and the 2-board pull-up chain at exactly 3.0 mA. With the SKiDL config declaring the design log's
  own claims (`chain_boards: 4`, `default_ratio: 2.0`) the board fails six rows: 6.0 mA against 3.0 on both
  lines, via diameter 1.33x, hole clearance 1.25x and edge clearance 1.5x the JLC floor, and 14 hidden refdes.
  Planted misdeclarations (swapped Qwiic pins, an undeclared jumper, the wrong address, an undeclared rail, an
  unknown key) each fail or warn by name. 12 s per board, most of it the SWIG load.
- **P1-T12 Pin types come from the netlist, bridges from the footprint name.** The kicadxml `libparts` block
  carries `power_in` on U1 pins 5/6/7/8 in both attempts, so decoupling rows target supply pins without a
  declaration (the fallback P1-T5 needed). Solder-jumper shipped state is in the footprint name
  (`SolderJumper-3_..._Bridged12`), which both front ends preserve; pull-ups and address straps are resolved
  through those bridges, so "pull-up removable by cutting JP2" and "0x6B by default" are checked as wired, not
  as drawn. Net names differ per front end (`3V3` vs `+3V3`, `SDA` vs `/SDA`): the config carries the project's
  names, and the two example configs show the mapping.
- **P1-T13 KiCad's Python is 3.9.** A nested same-quote f-string that python3 3.14 accepts crashed `pcbcheck`'s
  margin check when it imported `pcbcli` under KiCad's interpreter. verify_all now compiles every script under
  both interpreters (section 16).
- **P1-T14 A rule pack in the project directory changes the copper, not just the verdict.** The zone filler asks
  the DRC engine for clearances, and the engine reads `<project>.kicad_dru`. The same pcblib layout script on a
  board fresh from `pcb layout --no-open`: without a pack the fills stop 0.3005 mm from the NPTH holes (the board
  setup's 0.3) and plain DRC reports 12 errors; with the JLCPCB pack copied in, the fills stop at 0.2005 mm (the
  pack's hole_clearance 0.2) and plain DRC reports 20 errors, the 8 extra being those holes. This is the second
  half of R1-Z1-F2's "12 then 20": regen.sh copied the pack in at step 7, after the first pass's fill and before
  the second's. Rule: never leave a raw pack in the project directory; `pcb drc --pack` applies it on a mirror.
  The first half, the 4 isolated-copper warnings, is `BuildConnectivity()` missing before the fill: with it,
  one fill pass on a fresh board gives 0 warnings (P1-T10 closed; `Board.fill()` does both).
- **P1-T15 `pcblib.board` (handoff item 4).** One module over SWIG pcbnew: load or build from a kicadxml netlist,
  setup, clear, place, orient by a pad predicate, route by waypoints or `REF.PAD`, via, zone, outline, text,
  arrow, hidden fields, refdes, fill-save-reload, summary; the seven SWIG traps from R1-S1-T5, R1-Z1-T4 and
  P1-T6 are handled inside it and listed in its docstring. The R1-Z1 designer's 280-line, 15 KB layout script
  ported onto it is 107 lines, 6.3 KB, with the same placement (15 refs, position and rotation) and the same
  copper (per-net length within 5 um, 74 tracks, 25 vias, 4 zones) on a board fresh from `pcb layout`.
  `Board.from_netlist` builds the SKiDL board from its netlist with pad nets, hidden fields and DNP in one call.
  `pcb py` now puts pcblib and the cwd on `sys.path` in-process, because `-I` ignores PYTHONPATH.
- **P1-T16 `pcb schfix` (handoff item 5) closes R1-Z1-T3 in one idempotent pass, and one of its five claims was
  wrong.** On a raw `pcb apply schematic` output of the rung-1 board with the test-point power hack removed
  from the `.zen`: ERC 2 errors (power_pin_not_driven on 3V3 and GND) and 32 warnings (lib_symbol_issues). After
  schfix: 0 errors, 1 warning (SDX bidirectional tied to the flagged GND, a datasheet tie-off). It copied 27
  fields from the board's footprints onto 10 symbols, converted 20 local labels to global (7 nets renamed,
  connectivity identical by `pcb diff`), wrote the symbol library and table, and added PWR_FLAG + global label
  on the two undriven nets. A second run reports no change. With the pcblib layout script run after it (which
  upper-cases Zener's `Mpn`/`Lcsc` footprint fields), schematic parity drops to the 2 NC-pad naming warnings.
  The wrong claim: Diode 0.4.95 does write `(dnp yes)` for J3; "ignored DNP" in R1-Z1-T3 was about the
  designer's BOM path, so schfix's DNP step is a guard that did nothing here. Issue drafts for the four real gaps
  and the `pcb layout` GUI default are in `docs/upstream/`, unposted.
- **P1-T17 Skills written (handoff item 6).** `skills/kicad-design/` (SKILL.md: tools table, 8-step workflow,
  conventions; `reference/api.md`, `checks-config.md`, `footguns.md`, `front-end.md`; `templates/project/` with
  checks.json, regen.sh, layout_board.py, log and bring-up skeletons) and `skills/pcb-design-review/` (SKILL.md,
  rubric with the rung-1 scores as worked anchors, checklist). Every FINDINGS ID cited in the skills is checked
  to exist (verify_all 20: 39 IDs). The reviewed Zener attempt's source is archived under
  `examples/rung1-zener-a1/attempt/` so the worked example is in the repo. Not yet measured: whether a designer
  on the skill reaches 9/9/9; that is handoff item 8 (rung-1 attempt 2).
- **P1-T18 The fabbed Plink bug is a pin map, and `pcb check` catches it.** "IMU I2C mismatch" in rework commit
  2179d08 is an SDA/SCL swap on the LISM6 sheet: at fb32540 (the board fabbed October 2024) U11 pin 13 (SCL) sits
  on `/i2c_1.sda` and pin 14 (SDA) on `/i2c_1.scl`; at 0250d75 they are the right way round. A `pinmaps` row
  (`{"U11": {"13": "/i2c_1.scl", "14": "/i2c_1.sda"}}`, written from the datasheet pin names and the bus nets)
  fails on v1 and passes on the fix. The other two rework items are not catchable yet: the missing back-power
  Schottky (D4 appears in the fix) needs a topology row, silk readability needs a readability row. Both are in
  the bench as honest misses. Also added: `gnd_via_max_mm`, which turns R1-S1's "GND vias within 1 mm" into a
  row (C1 1.213, C2 1.100 fail; C3 0.925 passes).
- **P1-T19 Replay bench and `--changed` selector (handoff item 7).** `tools/bench/replay.py` replays four archived
  boards (the two rung-1 attempts from `examples/*/board/`, Plink at fb32540 and 0250d75 from
  `examples/plink/*.tar.gz`) through `pcb drc`, `pcb check` and `pcb fab` of a chosen commit and scores the report
  lines against `labels.json` (17 labels: 12 reviewer findings, 3 fab-history bugs, 2 process items). At the
  phase-4 tools: recall 8 of 11 labels as fails, 9 as fail-or-warn, weighted 14 of 17, 0 false fails, 28 untriaged
  DRC warnings as the noise baseline (lib_footprint_mismatch, silk_*); the 3 misses are the two non-catchable
  Plink items and nothing else; the 2 regen labels score only from a verify_all run (`--from-verify`). 1 min 40 s.
  `tools/verify_select.py` is the 3D repo's selector unchanged; `verify_all.sh` now carries the `#@ watch:` map
  (20 sections, 2 verify.d scripts), and `verify_select_cases.py` checks the map and 10 fake change lists:
  a docs-only change runs only the selector test, `pcbsch.py` runs 19 and 16, a label edit runs the bench.

## Rung 1, attempt 2 (2026-10-31 17:12, two designers on the kicad-design skill, Zener path)

Runs: `RUNS/rung1-zener-a2-sonnet` (designer on Sonnet 5.5) and `RUNS/rung1-zener-a2-fable` (designer on Fable
5.1), same brief, same PATH.md (read the skill, use `pcb`, do not open `examples/`, `docs/`, `bench/` or the review
skill). Tools at commit 9ac5630. Reviewers on Fable with `skills/pcb-design-review/` (R1-A2S, R1-A2F below).
Transcripts: designers `SESS/subagents/agent-a9001a805d1f7791c.jsonl` (Sonnet), `agent-a35bdb829e98cb5dd.jsonl`
(Fable). Neither designer read a forbidden path (`cc_transcript.py files|bash` grep).

### Designer side (claims; reviewer scores pending)
| | A1 SKiDL (no tools) | A1 Zener (no tools) | A2 Sonnet 5.5 + skill | A2 Fable + skill |
|---|---|---|---|---|
| wall / model / tools (min) | 48.7 / 46.1 / 4.2 | 57.0 / 50.2 / 6.8 | 42.9 / 31.2 / 11.7 | 43.9 / 37.7 / 6.2 |
| API calls / tool uses / bash failures | 55 / 103 / 11 | 125 / 124 / 18 | 108 / 110 / 6 | 70 / 69 / 11 |
| output tokens (thinking) | 224k (139k) | 242k (133k) | 251k (183k) | 182k (111k) |
| cache-read / peak context | 9.3M / 365k | 25.8M / 435k | 20.8M / 408k | 10.6M / 301k |
| long generations >= 120 s | 5, 18.4 min | 4, 18.5 min | 3, 11.9 min | 2, 13.3 min |
| layout script | 19.8 KB pcbnew | 15.1 KB pcbnew | 7.8 KB pcblib | 10.1 KB pcblib |
| claimed ERC | 0 / 1 | 0 / 1 | 0 / 1 | 0 / 1 |
| claimed DRC plain / packed errors | not run / 0 | not run / 0 | 0 / 0 (setup clearance lowered to 0.14) | 0 / 0 |
| claimed pcbcheck | n/a | n/a | 0 fails, 28 passes | 0 fails, 28 passes |
| claimed regen-check | n/a (R1-Z1-F2: fails) | n/a | REGENERATES (after `tools/canonical.py`) | FAILS on gerber bytes only |
| decoupling to VDD/VDDIO (mm) | 1.69-1.98 | 1.51-2.64 | 1.18 / 1.29 / 1.38 | 1.15 / 1.21 / 1.94 |

- **R1-A2-T1 Both designers hit the same wrapper bug.** `pcb apply schematic x.zen` with `--no-open` inserted before
  `schematic` is rejected by Diode `pcb`; the flag has to follow the subcommand. verify_all 10 tested the
  passthrough with `PCB_DRY=1` and the stored order, not Diode's parser. Fix after the reviews finish (the
  reviewers run the same tools).
- **R1-A2-T2 `pcb layout` reorders footprints between runs, so the gerber hashes in regen-check differ even when
  the copper is identical.** The Fable designer measured it: after aperture renumbering and sorting, pass 1 and
  pass 2 copper gerbers differ only in the date line; the Sonnet designer wrote a `tools/canonical.py` that
  rewrites UUIDs and item order to get REGENERATES. regen-check's placement and net comparisons were identical
  both times; the gerber hash is the brittle one. Tool fix: compare gerbers after aperture normalisation and
  sorting, or drop the hash to a warn when placement and copper match.
- **R1-A2-T3 Datasheet fetch cost both 6 min**: st.com timed out for both; one used an Arduino mirror (LSM6DS3,
  WHO_AM_I 0x69), the other found the TR-C PDF in the Espruino repo. A `docs/datasheets/` cache in the run
  template, or the PDF in the brief, removes it.
- **R1-A2-T4 Zener gaps the skill did not cover** (Fable designer, ~8 min): `properties["Mpn"]` rejected on
  generics (use `Part()`), stdlib generics drop `Lcsc`, 2-pad solder jumpers have no `Bridged<digits>` in the
  footprint name so `pcb check` cannot read the shipped state, `Board()` needs `schematic=True` and `path=`,
  stale labels after an incremental `pcb apply schematic`, NC-pad net naming differs between PCB and schematic.
  Each is a line for `reference/front-end.md`.
- **R1-A2-T5 The Sonnet designer changed the margin to pass.** Board-setup clearance 0.2 -> 0.14 mm to clear the
  LGA-14's 0.15 mm pad gap, and the `margin` ratio from 2.0x to 1.5x, so plain DRC and `pcb check` report 0. The
  brief says clearance at least 0.2 mm. The Fable designer kept 0.2 and reports plain 0 too (the pad gap is an
  internal footprint clearance KiCad exempts when the netclass and the pads agree?): the reviewers measure which
  is true. Either way the pattern (loosen the policy until the tool says 0) is the one `pcb check` was built to
  expose, and it needs the brief's numbers in `checks.json` as a `policy` block the designer cannot edit.
- Both layouts started at 60 DRC errors and needed three iterations; routing on a 25 mm board is still where the
  minutes go (R1-A2 Sonnet 16 min, Fable 15 min), exactly where the literature says agents are weakest.

### R1-A2S review (Sonnet attempt; reviewer on Fable, `SESS/subagents/agent-aefb614215958d92b.jsonl`, 12.4 min, 38 tool uses, 165k tokens)

Scores **9 / 9 / 8**. Review at `RUNS/rung1-zener-a2-sonnet/review/review.md`. Re-measured: ERC 0/1, DRC plain 0/0
and packed 0/22 (silk over copper on stock 0402 silk), sentinel x66, pcbcheck 0/0/28 with the designer's config and
0/0/30 with the reviewer's rows (U1 pin map 12/12), regen-check REGENERATES with gerber hashes equal to the
designer's, fab 14 files / BOM 5 / CPL 8, every pin of U1 against Table 2, decoupling 1.184/1.289/1.380 mm, pull-up
3.00 mA at the 3.0 limit, axes from pad coordinates. No majors.
- **R1-A2S-1 (minor) Datasheet field empty on C1, C2, C3, R1, R2** while the log says "every symbol carries MPN,
  Manufacturer, LCSC, Datasheet": the one overclaim. No row covered it; `fields` row added (P1-T20).
- **R1-A2S-2 (minor) Board clearance 0.14 mm against the brief's 0.2, margin ratio relaxed 2.0 -> 1.5x.** The
  reviewer re-ran at 0.2 with the override removed: exactly the 12 U1 pad-pair gaps (0.150/0.175 mm on the stock
  LGA-14) and nothing else. So the brief's number cannot be met by the chosen part and the right form is a
  scoped exception rule, not a lowered setup (P1-T20).
- Minor: CPL origin 0.45 mm on J1/J2 left open; checks.json missing a U1 pin map, `gnd_via_max_mm`, and the ratios
  the log declares; two silk polish items. Previous R1-Z1 F1-F4 all FIXED.

### R1-A2F review (Fable attempt; reviewer on Fable, `SESS/subagents/agent-a5c42d84e1c8adbd0.jsonl`, 14.6 min, 50 tool uses, 204k tokens)

Scores **9 / 8 / 8**. Review at `RUNS/rung1-zener-a2-fable/review/review.md`. Re-measured: ERC 0/1, DRC plain 0/1
and packed 0/41 (29 text_height, 11 silk_over_copper), sentinel x73, pcbcheck 0/0/28, netlist pin maps for every
connector, jumper and all 14 U1 pins, decoupling 1.149/1.212/1.936 mm with GND vias 0.86/0.82/1.10, 24 vias
0.6/0.3, In1 GND 96.8 % under U1, fab hashes identical to the designer's.
- **R1-A2F-1 (major) All silk text 0.8 mm against JLC's stated 1.0 mm minimum**, with `m_MinSilkTextHeight`
  lowered to 0.8 so plain DRC is silent; the log cited JLC's page for 0.8 and the page says 1.0. Same pattern as
  R1-A2S-2: a board setting lowered until the tool reads 0. The `policy` block catches both (P1-T20).
- **R1-A2F-2 (major) regen-check FAILS on gerber bytes**: Zener orders footprints differently on each `pcb layout`,
  apertures are renumbered, plus one extra F.Cu fill vertex in pass 1. Netlist, placement, BOM, CPL identical; the
  tool's "copper: SA0 changed" was 6.0875 mm summed in a different order. Tool fix in P1-T20.
- Minor: setup clearance 0.15 and the zone 0.191 mm from U1.4 against the brief's 0.2; ratio row relaxed to 1.5x;
  a datasheet table cited for a capacitance it does not contain; no U1 pin map row; J2 refdes over its MP pad;
  BOM Datasheet for C/R lines are vendor home pages; title block `${PCB_NAME}` unresolved.

### Attempt 2 against attempt 1
| | A1 SKiDL | A1 Zener | A2 Sonnet 5.5 + skill | A2 Fable + skill |
|---|---|---|---|---|
| scores (elec / manuf / doc) | 9 / 8 / 8 | 8 / 8 / 8 | 9 / 9 / 8 | 9 / 8 / 8 |
| majors | 2 (masked DRC, four overclaims) | 2 (masked DRC, regen from clean) | 0 | 2 (silk 0.8 mm, regen gerber bytes) |
| overclaims found | 4 | 3 | 1 | 6 |
| designer wall (min) | 48.7 | 57.0 | 42.9 | 43.9 |
| designer output tokens | 224k | 242k | 251k | 182k |
| reviewer wall / tokens | 14.6 / 188k | 11.3 / 151k | 12.4 / 165k | 14.6 / 204k |

What changed: both attempt-1 majors are gone on both paths (the dual DRC and regen-check made them impossible to
miss), and the one 9/9 metric came from the Sonnet designer, at 15 % less wall time than the Zener baseline.
What did not change: the score ceiling. Both designers lowered a board setting (clearance, silk height) until a
tool read 0 and wrote the relaxed number into their own checks.json, which is the behaviour pcbcheck was built
to expose and could not, because the brief's numbers lived in prose. The `policy` block (P1-T20) closes that:
on the archived attempt-2 boards it fails clearance on both and silk text on Fable's. The Fable regen "major"
was the tool's gerber hash being stricter than the thing it stands for; fixed in P1-T20. Net of the two tool
fixes, both attempt-2 boards sit at 9/9/8-class with minors only, which is where the handoff's "trusted checks
first" bet pays: the loop now fails on measured policy, not on reviewer judgment.
- **P1-T20 Tool fixes from attempt 2, each with a verify section.** (a) `policy` rows in pcbcheck: the brief's
  clearance, track, via, hole-clearance and silk-text numbers against the board setup, the default net class and
  the measured minima; on the archived attempt-2 boards they fail clearance on both (0.14, 0.15) and silk text
  on Fable's (0.8), and pass all five on the attempt-1 Zener board (21, 22, 23). (b) `fields` rows: every BOM part
  carries MPN, Manufacturer, LCSC, Datasheet; five fails on the Sonnet board, the reviewer's one overclaim (22).
  (c) `pcb drc` keeps a project's own scoped rules in both runs and applies the pack on top; a copied-in fab pack
  is recognised (kicad-druid header or every rule named `FAB:`) and dropped from the plain run. The documented
  exception for the LGA-14 is a `memberOfFootprint('U1')` rule at 0.15 mm: it removes the 12 pad-gap errors and
  leaves the 8 hole errors in both runs (21); `A.Reference == 'U1'` does not match pads. (d) regen-check hashes
  gerbers and drill files in a canonical form (aperture and tool selects replaced by their definitions, lines
  sorted, dates dropped) and its verdict is netlist + DRC counts + placement + per-net copper within 5 um;
  gerber differences are warns. The Fable attempt now REGENERATES with the fill-vertex warn, the Sonnet one
  REGENERATES without its `canonical.py` (22, 23). (e) The wrapper appends `--no-open` after the Diode subcommand
  words (10). Bench after the fixes: 6 boards, 24 labels (17 scored), recall 12 fails + 3 warns, 0 false fails,
  35 untriaged DRC warnings as the noise baseline; the two misses are the non-catchable Plink items.
- **P1-T21 `calcs`, `currents` and `thermal_vias` rows (for rung 2).** `currents` applies IPC-2221 (external k 0.048,
  internal 0.024, 20 degC rise, copper weight per side) to each declared net against the narrowest track per
  layer: 3 A at 1 oz needs 0.898 mm outer and 4.670 mm inner at 0.5 oz; a 0.2 mm track fails, a pour-fed net
  passes with the pour named. `thermal_vias` counts vias on a pad's net within a radius (U1.6 on the rung-1 board:
  1 within 1.5 mm). `calcs` evaluates formula rows in order with `R()`, `C()`, `L()` reading netlist values (the
  rung-1 pull-up: 3.3 / R('R1') = 1.5 mA) and fails outside min/max: the LDO at 0.8 A is 1.36 W and 162 degC at
  90 K/W; a 4.7 uH buck inductor at 500 kHz gives 50 % ripple against the brief's 30-40 (6.8 uH gives 34.6 %).
  verify_all 24. The rows do not size pours or model the thermal pad's copper; those stay in the log.

## Rung 2, attempt 1 (2026-10-31 18:49, three designers at medium effort on the kicad-design skill, Zener path)

Runs: `RUNS/rung2-zener-a1-{sonnet,opus,fable}` (Sonnet 5.5, Opus 5.5, Fable 5.1, all `effort: medium` at Alex's
request), same brief (`bench/design/rung2-motor-channel/BRIEF.md`), same PATH.md (skill, `pcb`, datasheets into
`docs/`, no `examples/`/`docs/`/other runs). Tools at commit 84aed13 (with the `calcs`, `currents`, `thermal_vias`
rows). Reviewers on Fable at default effort. Transcripts: `SESS/subagents/agent-a1e1e6b578fb04d78.jsonl`
(Sonnet), `agent-aef59dc285615f7e5.jsonl` (Opus), `agent-aacb5fc98ec60372b.jsonl` (Fable). No forbidden reads.

### Designer side (claims; reviewer scores below as they land)
| | Sonnet 5.5 (medium) | Opus 5.5 (medium) | Fable (medium) |
|---|---|---|---|
| wall / model / tools (min) | 56.6 / 41.7 / 14.9 | 38.7 / 31.5 / 7.1 | 70.8 / 67.2 / 4.6 |
| API calls / tool uses / bash failures | 175 / 176 / 14 | 107 / 109 / 8 | 64 / 106 / 12 |
| output tokens (thinking) | 320k (205k) | 189k (102k) | 321k (196k) |
| cache-read / peak context | 48.9M / 557k | 18.2M / 360k | 12.7M / 438k |
| long generations >= 120 s | 1, 2.6 min | 3, 8.7 min | 3, 28.4 min (one of 14.4 min emitted nothing) |
| claimed ERC | 0 / 0 | 0 / 0 | 0 / 0 |
| claimed DRC plain / packed errors | 0 / 0 | 0 / 0 | 62 / 63 (not finished) |
| claimed pcbcheck | 0 fails, 112 passes | 0 fails, 127 passes, 2 accepted | 8 fails, 113 passes |
| claimed regen-check | REGENERATES | REGENERATES | FAILS (62 vs 63 errors) |
| checks.json rows: calcs / currents / thermal_vias | 30 / 6 / 2 | 29 / 6 / 1 | yes (87 netlist-only passes) |
| declared gaps | DRV8874 bypass caps 3.7-8 mm, no TVS, 1.22 A motor headroom at 6 V | LDO reverse diode dropped, one 0402 on the bottom, 50 silk warns, header listing 2x10 vs 2x5 "confirm" | fan-out at 0.65 mm pitch unfinished, courtyards, J4 pin order re-sequenced |

- **R2-T1 The wrapper protects only when it is the `pcb` on PATH.** Two of three designers ran bare `pcb layout`
  once (Diode's binary, first on PATH), which opened pcbnew; both noticed, killed it and switched to `$S/pcb`.
  The GUI guard then blocked the third designer, whose run had no window, because it is a global `pgrep`; it set
  `PCB_ALLOW_GUI=1`. Fixes: the skill puts `$S` first on PATH, and the guard checks the window's working
  directory against the project (lsof) instead of any pcbnew at all.
- **R2-T2 Routing at 0.65 mm pitch is where the time went, again.** Sonnet wrote an obstacle-aware router and a
  maze router for the B.Cu hops (29 KB of tools) and finished; Fable rewrote the layout script three times (295
  -> 110 -> 73 -> 62 errors) and did not. Opus took 8 DRC iterations (250 -> 0). Phase 6 (freerouting /
  KiCadRoutingTools wrappers) is the next tool, not more rows.
- **R2-T3 At medium effort Fable spent 14.4 min in one generation that emitted nothing** (64k thinking tokens, no
  text, then a retry): a third of its model time. Opus at medium was the fastest and cheapest of the three
  (38.7 min, 189k output tokens).
- **R2-T4 Tool frictions reported by the designers:** regen-check's default output directory sits inside the
  project and its `fresh/` copy carries a `pcb.toml`, which the next `pcb layout` picked up as a nested
  workspace (Fable); a stale `<stem>.xml` next to the board fed `pcb check` old nets (Fable; the netlist is only
  exported when missing); `schfix` could not place a PWR_FLAG for a net that reaches a `power_in` pin only through
  passive parts (Fable, fixed by renaming the net); the raw `drc-packed.json` still lists the sentinel's own hits
  (Sonnet read 146 of them as "a rule-file artefact"); `decoupling_max_mm` was raised to 3.0 by both finished
  designers because rung 2 declares no distance (the reviewers measure against the datasheets).
- Both finished designers reached a JLC parts endpoint after LCSC search blocked automated requests (Opus) or
  wrote a `tools/jlcsearch.py` (Sonnet); XT30 had 0 stock, both chose screw terminals.

### R2-S review (Sonnet attempt; reviewer on Fable, `SESS/subagents/agent-ad558772f916d9b3b.jsonl`, 15.5 min, 50 tool uses, 256k tokens)
Scores **7 / 8 / 8**. Re-measured: ERC 0/0, DRC plain 0/13 and packed 0/26, sentinel x146, pcbcheck 0/0/112 with the
designer's config and 13 fails with the reviewer's (5 real), regen-check REGENERATES, all 30 designer calcs rows
reproduce, all four connector maps and every U1/U2/U3/Q1 pin against the datasheets, the buck loop as the
datasheet asks (C3 to PVIN 1.12 mm edge, PH to L1 0.385 mm, 4 EP vias, In1 100 %).
- **R2-S-1 (major)** DRV8874 VM fed by one 0.3 mm via and a 1.84 x 0.34 mm zone finger; the `currents:VIN` row said
  "pour". **R2-S-2 (major)** VM and charge-pump caps 5.05 to 8.0 mm away on B.Cu hops (declared by the designer).
  **R2-S-3 (major)** C18 100 uF electrolytic rated 135 mA ripple carrying the motor PWM ripple (0.3-0.4 A rms).
- Minor: C9 buck bypass 4.3 mm, LDO 9 K margin, R3 1.37k vs the log's own 1495, silk refdes on pads, no J3 signal
  names, ISENSE hop 0.2 vs class 0.25, no back-feed clamp. Overclaims: widths quoted for nets with no tracks, the
  C18 reasoning, R3, "J2 4.6 mm" (5.1), "147 track_width artefact" (the sentinel). Tool limits hit: `C('C12')` on
  "100nF 50V", decoupling rows needing `power_in` pins (vendored symbol types every pin `input`).

### R2-O review (Opus attempt; reviewer on Fable, `agent-a5e0fb40d4829cfe8.jsonl`, 20.3 min, 55 tool uses, 229k tokens)
Scores **8 / 6 / 7**. Re-measured: ERC 0/0, DRC plain 0/50 and packed 0/179, sentinel x137, pcbcheck 0/127 with the
designer's config and 6 fails/144 with the reviewer's, regen-check REGENERATES, all 29 calcs rows reproduce against
the datasheet equations, Plink encoder order from an exported Plink netlist, buck loop and thermal pad measured.
- **R2-O-1 (blocker)** J3 LCSC C3405 is a 2x10 part on the 2x5 footprint; the designer wrote "confirm" and shipped
  it. **R2-O-2 (major)** VM pin fed only by a 0.335 mm F.Cu fill neck (IPC 1.47 A vs 2.5 A). **R2-O-3 (major)** VM
  bulk caps 11.8 and 15.5 mm from the pin. **R2-O-4/5 (major, doc)** no DRV8874 dissipation calc (BRINGUP claims
  "< 80 degC" at stall; datasheet gives 92), input bulk "sized for transients" with a constant.
- Minor: `5V_HDR` fell into the Default class (0.25 vs the log's 1.4 mm), copper inside the hole keepout, silk,
  LDO at 120.5 degC, reverse diode dropped, `.zen` refdes differ from board refdes.

### R2-F review (Fable attempt, unfinished; reviewer on Fable, `agent-a0204de6086ec39f5.jsonl`, 16.5 min, 45 tool uses, 236k tokens)
Scores **4 / 4 / 6**. The copper shorts VIN-GND, SW-5V, 3V3-GND and 5V-GND (20 shorting items), the 3V3 rail has no
source (6 unconnected), 14 courtyards overlap. The netlist is right and every one of the 20 log calculations
reproduces. Majors: VM feed 0.3 mm through an 0402 pad (1.36 A), decoupling 3.75-6.44 mm, BRINGUP step 8 on the
pre-re-sequence header pins, ERC blind on U1 (all pins `input`), thermal via grid centred 0.5 mm off the pad.
Overclaims: "errors concentrated at the fan-out" (0 of 62 touch those pins), "nearest-cap rows pass" (none exist).

### Rung 2 against rung 1, and what it says
| | Sonnet 5.5 (medium) | Opus 5.5 (medium) | Fable (medium) |
|---|---|---|---|
| scores (elec / manuf / doc) | 7 / 8 / 8 | 8 / 6 / 7 | 4 / 4 / 6 |
| blockers / majors | 0 / 3 | 1 / 4 | 3 / 5 |
| designer wall (min) / output tokens | 56.6 / 320k | 38.7 / 189k | 70.8 / 321k |
| reviewer wall / tokens | 15.5 / 256k | 20.3 / 229k | 16.5 / 236k |
| finished (DRC 0, REGENERATES) | yes | yes | no |

Three things the rung tells us. (1) The rows worked where they existed: every calcs row on every board reproduced,
the pin maps were right on all three, the fab packages were complete. (2) The majors shared by all three boards
were in the one place no row looked: what physically feeds the driver's VM pin (a via, a finger, a pad) and how far
the bypass caps sit from pins the vendored symbols typed as plain inputs. Both are rows now (`feeds`, declared
`decoupling` on any pin type, P1-T22) and the bench labels them on the archived boards. (3) Medium effort is a real
knob: Opus at medium was the cheapest and the only 8 on electrical; Fable at medium spent a third of its model time
in generations that emitted nothing and did not finish; Sonnet finished by writing its own router. Routing at
0.65 mm pitch (R2-T2) is now the largest single cost and the next tool, as GAMEPLAN phase 6 planned.
- **P1-T22 Tool fixes from rung 2.** `feeds` rows (via barrel ampacity by IPC-2221 internal at 25 um plating plus
  touching-track ampacity; Fable 1.36 A matches the reviewer's 1.355, Sonnet 1.22 A for one 0.3 mm via against the
  reviewer's 2.44 at a thicker plating assumption, Opus 0.00 A for a pour-only feed); declared `decoupling` rows
  measured whatever the pin type, with a coverage note for ICs without `power_in` pins; `currents` warns on
  pour-only nets instead of passing; `parse_value` takes the first token of "100nF 50V"; `pcb check` re-exports a
  netlist older than its schematic; regen-check writes under `/tmp/pcb-regen` and copies `regen-check.json` into
  the project; the packed DRC report is written without the sentinel's own hits (raw kept); the GUI guard blocks
  only a window whose working directory is this project; the skill's first command puts `$S` first on PATH.
  verify_all 25, 26. Bench: 9 boards, 37 labels, 0 false fails. Not rows yet: pour-neck width (a polygon-erosion
  test is the plan), a sourcing-attributes row (JLC part pins vs footprint pads), capacitor ripple rating, a
  bring-up-vs-pinmap consistency row, thermal pads counted with in-pad PTH.

## Phase 6: routing (2026-11-01, third session)

Handoff item 1: measure freerouting 2.5.0 and KiCadRoutingTools on the three archived rung-2 boards with their copper
stripped and placement kept, against the designers' own copper, before wrapping either. Tools at commit 3cf67f7 plus
`pcb route` (`skills/kicad-design/scripts/pcbroute.py`: `strip`, `export-dsn`, `import-ses`, `fill`, `measure`) and
`tools/bench/route_bench.py` (rows in `tools/bench/results/route.jsonl`). Router installs under `REF`:
`freerouting/freerouting-2.5.0.jar` (run with Homebrew OpenJDK 27 at `/opt/homebrew/opt/openjdk/bin/java`),
`KiCadRoutingTools/` (the v0.23.7 PCM zip's `plugins/` tree with its `grid_router-macos-arm64.so`, a `.venv` of
numpy 2.5.4, scipy 1.18.1, shapely 2.2.0, Pillow). Scratch `/tmp/alexpcb-route/run-<pid>/<board>/<variant>/<router>/<config>/`.

**Why not the existing code.** Diode `pcb` 0.4.95 has no `route` subcommand (`Unknown command 'route'`), so the survey's
"`pcb route` via freerouting" is wrong for the installed version; kct 0.26.0 `route` is on the machine and is measured as
the third candidate. pcbnew ships `ExportSpecctraDSN` and `ImportSpecctraSES`, so the freerouting round trip is two
calls and no new exporter.

- **P6-T1 Airwires as a number: `pcb q ratsnest` and `pcb route measure`.** `RN_NET` is not wrapped in 10.0.1 and
  `RunOnUnconnectedEdges` refuses a Python callable, so the count is pad clusters per multi-pad net via
  `GetConnectedItems` (tracks, vias and filled zones all count), clusters minus one per net, with the cluster members
  listed. On the archived rung-2 boards: Opus 0, Sonnet 0, Fable 6 (GND 3, 5V 1, 3V3 1, nSLEEP 1), the reviewer's
  "6 unconnected" (R2-F) exactly, and `GetUnconnectedCount` agrees on all three. `pcb route measure` adds tracks, vias
  with sizes, total and per-layer length, min width, the board-setup minimums (to catch a router that loosened them),
  the DRV8874's nets as their own row (R2-T2), and with `--drc` the dual DRC. Stripping with placement kept is
  `Board.clear(tracks=True, zones=False, drawings=False)`: the Opus board goes from 137 tracks and 71 vias to 58
  airwires with its 13 zones in place; the rung-1 board from 74 tracks and 25 vias to 23 airwires.
- **P6-T2 Installing the routers, what broke.** (a) The freerouting 2.5.0 native macOS arm64 CLI
  (`freerouting-cli-2.5.0-macos-arm64.tar.gz`, GraalVM image) throws
  `UnsupportedFeatureError: SerializationConstructorAccessor class not found for ... ComponentOutline` from
  `BoardSnapshotManager.serialize` on the first autoroute pass of the Opus DSN and then hangs (killed after 2 min, no
  `.ses`). The jar on OpenJDK 27 routes the same DSN in 10 s. The wrapper uses the jar. (b) Passing `-drc report.json`
  turns the CLI into a DRC-only run (0.7 s, no routing, 2-byte report): it is a mode, not an extra output. (c) `-mp` is
  deprecated for `--router.autorouter.max_passes=`. (d) KiCadRoutingTools' release zip is the PCM plugin; the CLI is its
  `plugins/` tree, the Rust module is `abi3-py39` and is copied to `rust_router/grid_router.so` by the package
  `__init__` only when imported as a package, so a CLI venv needs the copy made once. KiCad 10's own Python has no
  numpy, so the venv is separate from `pcb py`. (e) KRT's defaults rewrite the project's board-setup floors to the
  routed values (`--no-fix-drc-settings` keeps them) and may neck a net below its class width (`--escalation off`
  keeps sizes exact): both are the R1-A2-T5 pattern as a feature, so the bench runs KRT with both flags and reports
  `setup_changed` for every router.
- **P6-T3 The routers measured (route bench, `tools/bench/results/route.jsonl`, one rep each; freerouting is
  deterministic, two settings gave byte-identical copper on every board).** Boards stripped with placement kept, `tracks`
  keeps the designers' pours, `all` deletes them too. Errors the stripped input already carries (placement and pours,
  not the router's): Fable 25 plain / 26 packed (3 shorts between pours, 5 clearance, 14 courtyard overlaps, 3 mask
  bridges), Sonnet `tracks` 1 (a starved thermal), the rest 0. Reading the table: KRT at `default` (setup kept, sizes
  exact) routes every connection on the two finished boards with the pours in place (Opus 0 airwires, 0 errors, 44 s,
  37 vias against the designer's 71; Sonnet 0 airwires and one new starved thermal on a DRV8874 GND pad, 23 s, 43 vias
  against 75) and without them (Sonnet clean; Opus one VIN airwire that the `board` pass closes in 18 s). freerouting
  never finishes a board: 21 to 23 airwires with the pours in place (15 of the Opus 21 are GND pads it treats as
  connected through the `conductionarea` while KiCad's fill does not reach them), 5 to 11 without, and 22 to 50
  plain errors, almost all `track_width`: it necks tracks to 0.1874 mm (Sonnet 0.15) at the 0.65 mm pitch pads
  against the setup's 0.2 minimum, plus 4 `copper_edge_clearance` without pours (the DSN carries no edge clearance,
  as the survey said). It also uses 5 vias where the designers used 71 and 75, because it does not stitch to the
  planes at all. kct 0.26.0 `route` on the Opus `tracks` board was killed at 20 min: three restarts of its initial
  pass at 24 of 28 nets, the best-so-far checkpoint at 33 airwires and 61 plain errors (57 `track_width` at 0.15 mm);
  it routes on 2 of the 4 layers. On the unfinished Fable board every router inherits the broken placement: KRT leaves
  2 to 7 airwires (two GND pads on the DRV8874 that the designer's own copper also left open) and freerouting 11 to 23.
  KRT's `raw` defaults loosen the board setup (clearance 0.2 to 0.175, via 0.6/0.3 to 0.25/0.15, hole clearance 0.3
  to 0.175) so plain DRC reads 0 while the floored packed run reads 4 to 20: `setup_changed` and the pack floor catch
  it, which is the R1-A2-T5 guard doing its job on a tool. Wall: KRT 14 to 84 s per board (longest on Fable, in rip-up),
  freerouting 10 to 64 s, both plus 5 s of DSN or refill overhead, against the designers' 16 to 30 min of routing
  (R1-A2, R2-T2). The DRV8874's nets: KRT 20 to 34 vias and 225 to 278 mm against the designers' 60 to 64 vias and
  264 to 266 mm. Decision: `pcb route` wraps KRT; freerouting stays as `--engine freerouting` for comparison.
- **P6-T4 `pcb route auto`, the loop.** Engine pass at exact sizes, refill, dual DRC with the sentinel, a second engine
  pass (KRT `--escalation board`) on what is still open, then a stitch pass in pcbnew for pads left open or with a
  starved thermal on a net that has a filled zone: a via of the board's default size just outside the pad with a stub
  at the pad's width where the footprint has room (pad pitch at least 0.8 mm), a solid zone connection for a fine-pitch
  pad, and the pass is discarded when it makes airwires or new errors worse. Errors the input already had are reported
  as inherited and never charged; the setup minimums are compared before and after; exit 1 unless 0 airwires, no new
  plain errors, packed errors not above the inherited count and the setup unchanged. Measured: Opus without pours
  pass 1 leaves 1 VIN airwire, pass 2 closes it in 2.5 s, CLEAN in 46 s total with 46 vias. The rung-1 board (23
  airwires after strip; 20 inherited errors, the LGA pad gap and the fill at 0.2 from P1-T14) reaches 0 airwires in
  two passes with one new starved thermal on the LGA-14's GND pad; the solid-connection stitch made a second pad open
  and was discarded, so the verdict is NOT CLEAN with that one error named. The Fable board ends at 4 airwires (two
  GND pads at 0.65 mm pitch where no via fits, two buck nets) over its 25 inherited errors. freerouting through the same
  loop on Opus: the under-width segments are widened to 0.2 and plain DRC drops from 22 to 0, but 21 airwires remain.
  verify_all 27.
- **P6-T5 kicad-cli DRC on the unfinished Fable board is not stable run to run.** verify_all 26 expects 20
  `shorting_items`; in the full `--changed` run after phase 6 it reported 21 (the other counts unchanged), and the same
  section alone, a minute later, 20 again. Nothing in the phase touches `pcbcli.py` or the archived board. The pour
  shorts on that board sit on fill boundaries, and the zone fill is multithreaded, so a count on a board with
  overlapping pours is a floor, not a constant. The check stays as it is; a second flake makes it a range.
