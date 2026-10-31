---
name: kicad-design
description: Agent-driven KiCad 10 PCB design from code (Zener for Diode `pcb`, or SKiDL) with the `pcb` wrapper, pcblib layout helpers, pcbcheck intent checks and the fab package. Use when designing, laying out, checking, measuring, regenerating or packaging a KiCad board headlessly, or when a brief asks for a schematic plus PCB with ERC, DRC, fab rules and a bring-up document.
---

# KiCad design from code

`<skill>` is this folder. Tools live in `<skill>/scripts/`; `pcb` is the entry point (`pcb` alone lists commands). The
evidence behind every rule is in `<repo>/docs/FINDINGS.md`; the ID in brackets points at it.

| Tool | Does |
|---|---|
| `pcb erc x.kicad_sch` | ERC as JSON, counts by severity and type; exit 1 on errors |
| `pcb drc x.kicad_pcb [--pack jlcpcb]` | DRC twice on a mirror of the project: plain (board setup) and with the fab pack plus a sentinel rule; pack minimums below the setup are raised first. The headline is `errors_total`. Exit 2 if KiCad rejected the pack (P1-T3, P1-T4) |
| `pcb check x.kicad_pcb checks.json` | intent rows ERC and DRC cannot see: rails, decoupling distance, pull-up current, addresses, connector pin maps, jumpers, test points, silk refdes vs the bring-up doc, feature-vs-floor ratios. Undeclared items fail (P1-T11) |
| `pcb q x.kicad_pcb <cmd>` | one measurement over pcbnew: `decoupling`, `dist`, `net`, `nets`, `vias`, `coverage`, `zones`, `holes`, `silk`, `settings`, `edge`, `fps`, `pads`, `fabdata` (`pcb q` alone lists them) |
| `pcb py script.py` | KiCad's Python with `pcblib` and the cwd importable, after the GUI guard |
| `pcb schfix x.kicad_sch` | post-fix a `pcb apply schematic` output: fields, global labels, symbol library, PWR_FLAGs; refuses if connectivity changed (P1-T16) |
| `pcb netlist`, `pcb diff a b` | kicadxml export; connectivity diff as (ref, pin) sets, renames allowed, exit 1 on change (P0-T3) |
| `pcb fab x.kicad_pcb` | gerbers + drill zip, JLC BOM and CPL from footprint fields, renders, `fab.json` with member hashes (P1-T7) |
| `pcb regen-check DIR --cmd ... --board ... --generated ...` | copy, delete generated outputs, regenerate twice, compare netlist, DRC, fab hashes, placement (P1-T9) |
| `pcb render`, `pcb svg`, `pcb stats` | kicad-cli wrappers with sane defaults |
| `pcb build|layout|apply|dfm|bom|...` | Diode `pcb` passthrough; `layout` and `apply` always get `--no-open`; `open` is refused (P0-T6) |

kicad-cli runs in 1-17 s, a dual DRC in 5 s on a 15-part board, so run the checks after every step. Wall time in the
baseline went to long single generations (18 min of 49, R1-S1-T1): work in small steps and let the tools measure.

## Workflow

1. **Plan checkpoint (first 10 minutes).** Read the brief. Write `DESIGN_LOG.md` with: rails and the current
   budget per rail, the bus map (addresses, pull-up value with the bus-capacitance arithmetic), the connector pin
   maps as tables, the parts with MPN and LCSC, the floor plan (what sits where and why), the stackup and the
   design-margin numbers (clearance, track, via, hole clearance; the fab floor is 0.09/0.09/0.45/0.2 at JLC).
   Then write `checks.json` from those tables before any code (`reference/checks-config.md`), starting with the
   `policy` block: the brief's clearance, track, via, hole-clearance and silk-text numbers, copied once and never
   lowered. Both attempt-2 designers lowered a board setting (clearance to 0.14 and 0.15, silk text to 0.8) until
   plain DRC read 0 and then wrote the relaxed number into their own config; the `policy` row fails that
   (R1-A2-T5). Done when `pcb check` would have a row for every claim the log makes.
   - A stock footprint that cannot meet a policy number (the LGA-14's 0.15 mm pad gap against 0.2 mm clearance)
     gets a **scoped exception rule** in `layout/x/x.kicad_dru`, not a lowered setup:
     `(rule "LGA-14 pad gap on U1" (condition "A.memberOfFootprint('U1') && B.memberOfFootprint('U1')") (constraint clearance (min 0.15mm)))`.
     `pcb drc` keeps project rules in both runs and applies the fab pack on top; a copied-in fab pack is detected
     and dropped from the plain run (P1-T20). Say why in the log and in `accepted_warns`.
   - Fetch the datasheet into `docs/` first (both attempt-2 designers lost 6 minutes to st.com timing out; a
     mirror with the same part number is fine, note the WHO_AM_I if the variant differs).
2. **Scaffold.** Copy `<skill>/templates/project/` (or start from `<repo>/examples/rung1-zener-a1/attempt/`, the
   reviewed rung-1 source: `qwiic_imu.zen`, one `parts/*.zen` per part with its symbol and footprint, `tools/`).
   Zener is the front end (`reference/front-end.md`); SKiDL is the fallback and `Board.from_netlist` takes its netlist.
3. **Netlist first.** `pcb build x.zen` until it passes, then `pcb layout --no-open x.zen` (writes the `.kicad_pcb`
   with footprints and nets, placement preserved on re-runs) and `pcb apply schematic --no-open x.zen` followed by
   `pcb schfix layout/x/x.kicad_sch`. Then `pcb erc`: 0 errors, and every warning gets a line in the log with the
   reason. Then `pcb check --only rails,connectors,jumpers,addresses,pullups,test_points`: the netlist rows pass
   before any copper exists.
4. **Layout as data on pcblib.** Write `tools/layout_board.py` on `pcblib.board` (`reference/api.md`; the worked
   example is `<repo>/examples/rung1-zener-a1/layout_board.py`, 107 lines for a 15-part board): `Board.load`,
   `setup` with the margin numbers, `clear`, `place_many`, `orient_pads` for connectors, `route` by waypoints or
   `REF.PAD`, `via`, `zone`, `text`, `hide_refdes(keep=...)`, `fill`, `save`. Everything the script places is
   rebuilt on every run, so one run restores the layout after a schematic regeneration (code is the source of truth).
   Run it with `pcb py tools/layout_board.py layout/x/x.kicad_pcb`.
   - Never leave a `.kicad_dru` in the project directory: the zone filler reads it and the copper changes
     (hole clearance 0.2 from the pack instead of 0.3 from the setup, 8 DRC errors that appear on the second
     regeneration, P1-T14). `pcb drc --pack` applies the pack on a mirror.
   - `Board.fill()` saves, reloads, builds connectivity and fills twice; do not call `ZONE_FILLER` yourself
     (in-memory boards segfault it and the first fill leaves islands, R1-S1-T5, P1-T10).
   - Silk text 1.0 mm high, 0.15 mm stroke: JLC's stated minimum is 1.0 mm (R1-A2F-1 shipped 0.8 citing the
     page for 0.8; the page says 1.0). The `policy` row reads the smallest silk text on the board.
   - Keep the refdes visible on every part the bring-up doc names (`hide_refdes(keep=[...])`); `pcb check`'s silk
     row fails the rest (R1-Z1-F4: 10 of 11 hidden).
   - A decoupling cap's distance is measured to the supply pin, and pcbnew cannot tell a supply pin from a strap
     (C3 was nearest CS, 2.36 mm, and 2.64 mm from VDD, P1-T5): declare `decoupling` rows with the pin.
5. **Check after every layout run.** `pcb drc layout/x/x.kicad_pcb --pack jlcpcb` and report both numbers;
   "0 with the pack" alone is the overclaim both baseline designers made (R1-S1-F1, R1-Z1-F1: 18 and 20 plain
   errors behind a packed 0). Then `pcb check` for every row, then `pcb q` for anything the log states as a
   number. Fix every fail before the next step; put each accepted warn in `accepted_warns` with the reason.
6. **Package.** `pcb fab layout/x/x.kicad_pcb --out fab`: read `fab.json` for `bom_missing_lcsc` and
   `cpl_origin_offsets_mm` (the JST SH footprint origin sits 0.45 mm from its body centre, R1-S1-F4). Write
   `BRINGUP.md` as numbered steps with expected readings and the test point or header pin for each.
7. **Prove regeneration.** Write `tools/regen.sh` (build, layout, layout script, apply schematic, schfix, erc, drc,
   check, fab) and run `pcb regen-check . --cmd tools/regen.sh --board layout/x/x.kicad_pcb --generated layout fab`.
   It must say REGENERATES: both baseline regenerations diverged on the first pass from a clean tree and one
   exited 1 (R1-Z1-F2, P1-T10). The verdict is on netlist, DRC counts, placement and per-net copper; gerber
   differences from Zener's footprint ordering or a fill vertex are reported as warns (R1-A2-T2). Put the
   verdict line in `SUMMARY.md`.
8. **Report evidence, not verdicts.** `SUMMARY.md` carries the numbers: ERC errors/warnings, DRC plain and packed,
   pcbcheck fails/warns/passes, regen-check verdict, fab file count, the wall clock from the transcript (the
   designer's own clock was off by 2 h in R1-Z1). Every claim in the log cites a check row or a `pcb q` line
   (four of the R1-S1 claims were adjectives with no number behind them, R1-S1-F2).

## Conventions

- Run directory: `<run>/x.zen`, `parts/`, `tools/`, `layout/x/` (generated), `fab/` (generated), `checks.json`,
  `DESIGN_LOG.md`, `BRINGUP.md`, `progress.md` (one line per step with the time), `SUMMARY.md`.
- Net names: rails `3V3`, `GND`; signals bare (`SDA`), no sheet prefix. `pcb schfix` makes the labels global so the
  schematic agrees. checks.json uses the project's names as they are.
- Fields on every part: `MPN`, `Manufacturer`, `LCSC`, `Datasheet`, `Package` (upper-case `MPN`/`LCSC`; pcblib's
  `fields()` renames Zener's `Mpn`/`Lcsc` so parity matches).
- Design-margin defaults for JLC 4-layer: clearance 0.2, track 0.2 (0.25 default class), via 0.6/0.3, hole clearance
  0.3, copper-to-edge 0.4, silk clearance 0.15, 1.0 mm text. Set them in `Board.setup()` and in the `.zen`
  `DesignRules`; they are what the plain DRC enforces.
- Never open a KiCad GUI from a script; `pcb guard` says whether one is running.

## Reference

- `reference/api.md`: `pcblib.board` and `pcb q`, with the SWIG traps each call hides.
- `reference/checks-config.md`: `checks.json` keys with the rung-1 example and what each row measures.
- `reference/footguns.md`: every mistake from the two baseline attempts and the tool that catches it now.
- `reference/front-end.md`: Zener (`pcb`) as measured: what it gives, where it stops, the traps.
