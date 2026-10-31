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
