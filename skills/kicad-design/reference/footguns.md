# Foot-guns from the rung-1 baseline, and what catches them

IDs point into `<repo>/docs/FINDINGS.md`. "Caught" means the tool flags it on the archived rung-1 boards
(`tools/verify_all.sh` section in brackets).

## Reviewer findings (both designers, no tools)

| ID | Mistake | Catch | Caught |
|---|---|---|---|
| R1-S1-F1, R1-Z1-F1 | DRC run only with the fab pack loaded, which relaxes the board setup: "0 errors" over 18 and 20 real ones | `pcb drc` runs plain and packed, floors the pack to the setup, reports both; the headline is the max | yes: 18 / 20 plain, 0 raw packed (1, 2) |
| R1-Z1-F2 | `regen.sh` exits 1 from a clean tree; first pass differs from the second | `pcb regen-check`: fresh copy, two passes, netlist + DRC + fab hashes + placement compared | yes: exit 1, 12/4 then 20/0 (11) |
| P1-T10 | SKiDL `check.sh` exits 0 from clean but the first fill differs (12 vs 18 errors) | same; `Board.fill()` builds connectivity and fills twice | yes (12) |
| R1-S1-F2 | "DRC 0", "every feature 2x the floor" (1.33x), "GND vias within 1 mm" (1.21), "up to four boards" (6 mA) | `pcb check` margin, decoupling and pullups rows carry the number | yes: 6.0 mA, 1.33x (14) |
| R1-Z1-F3 | bulk cap 2.64 mm from VDD, brief says 2, log says 2.9 | `decoupling` row with the pin named | yes: 2.639 (13) |
| R1-Z1-F4 | refdes hidden on every part the bring-up doc names | `silk` row reads BRINGUP.md | yes: 10 of 11 (13) |
| R1-S1-F3 | drill-mark flashes on copper from `--board-plot-params` | `pcb fab` plots an explicit layer list | by construction (8) |
| R1-S1-F4 | CPL mid-point is the footprint origin, 0.45 mm off the JST body | `pcb fab` reports `cpl_origin_offsets_mm` from the F.Fab outline | yes: J1, J2 0.45 (8) |
| R1-Z1 minor | BOM without Datasheet, pos file with KiCad headers | `pcb fab` writes both JLC files and the full BOM | yes (8) |
| R1-S1-T8 | baseline designer read the review protocol | run dirs outside the repo; the prompt gives no path back | process |

## Designer time sinks

| ID | Mistake | Catch |
|---|---|---|
| R1-S1-T2, R1-Z1-T2 | 20 KB of pcbnew boilerplate written from scratch, three times | `pcblib.board`; the port is 107 lines (17) |
| R1-S1-T5, R1-Z1-T4, P1-T6 | `ZONE_FILLER` on an in-memory board, `Remove`, `GetNetsByName`, `GetFieldByName`, visible `SetField`, `BOX2I.Merge` on a temporary, `LSET(layer)` | handled inside pcblib and pcbq (17, 18) |
| R1-S1-T3, R1-Z1-T3 | schematic exporter gaps: fields, labels, lib_ids, PWR_FLAG | `pcb schfix` (19); upstream drafts in `docs/upstream/` |
| R1-S1-T1, R1-Z1-T1 | 18 min of a 50-min run in long single generations | work in small steps; every step has a 1-17 s check |
| R1-Z1-T5, R1-S1-T7 | 8 min to first Zener build; 7 failed exploration calls on SKiDL | `reference/front-end.md`, the archived attempt source |
| P0-T6 | `pcb layout` opens pcbnew; the GUI rewrites files on save | wrapper forces `--no-open`, refuses `open`, `pcb guard` (10) |
| P1-T14 | a `.kicad_dru` left in the project changes the zone fill | never copy the pack in; `pcb drc --pack` uses a mirror (17) |
| P1-T2 | kicad-cli caps each violation type at 199 | `pcb drc` lists `capped_types` (3) |
| P0-T5, P1-T4 | a rejected rule file makes DRC exit 0 silently | sentinel rule; exit 2 (4) |
| R1-S1-T6, R1-Z1-T7 | pack margins bite the design (silk clearance on test points, JST tabs vs edge) | declare per-footprint exceptions in `accepted_warns` with the reason; not yet a row |
