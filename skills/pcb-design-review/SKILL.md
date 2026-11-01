---
name: pcb-design-review
description: Independent review and 1-10 scoring of a KiCad board attempt for electrical correctness, manufacturability and documentation, with measured evidence from pcb drc, pcb check, pcb q and pcb regen-check. Use when asked to review, score or verify a PCB design attempt, or to check whether previous review issues were fixed.
---

# PCB design review

You are the reviewer, not the designer. Every issue carries a number, a file or a command a third party can
re-run. Tools come from the `kicad-design` skill (`<kd>` = `~/code-stuff/alex-pcb-skills/skills/kicad-design`):
`<kd>/scripts/pcb`. The two rung-1 reviews (`<repo>/docs/FINDINGS.md`, R1-S1 and R1-Z1) found both majors with
"re-run without the pack" and "regenerate from clean"; both are commands now, so the review starts there.

## Steps

0. **Notes as you measure.** Create `<review_dir>/notes.md` before the first command and append each result after
   it (what, number, command). Work on `<review_dir>/copy/`, never on the designer's files.
1. **Re-run the checks.** `pcb erc`, then `pcb drc <copy>/x.kicad_pcb --pack jlcpcb --out <review_dir>/drc`:
   read plain **and** packed errors, `sentinel`, `pack_relaxes_setup`, `capped_types`. Diff against what the
   designer claimed; any error they did not report is an overclaim finding (R1-S1-F1, R1-Z1-F1: "DRC 0" over 18
   and 20). Then `pcb check <copy>/x.kicad_pcb checks.json --out <review_dir>/pcbcheck.json`: every fail is an
   issue, every warn a lead, and read `coverage` and `not_checked` before saying anything passed.
2. **Audit the check config.** Read `checks.json` (`<kd>/reference/checks-config.md`). Every `accepted_warns`
   entry needs a reason you agree with. Every claim in the brief needs a row: connectors, buses, decoupling with
   the pin named, rails, test points, margin ratios. Add the rows the designer left out to
   `<review_dir>/review_checks.json` (a copy with your rows) and run `pcb check` with it; a brief item with no
   row is a documentation issue.
3. **Verify the netlist, not the drawing.** `pcb netlist`, then the pin maps from the XML (the `connectors`,
   `jumpers` and `addresses` rows do this; read their messages). Vision on schematics is unreliable
   (GAMEPLAN 3b, OmniSch), so the render is a lead only.
4. **Measure what the log states.** `pcb q <copy>/x.kicad_pcb decoupling`, `dist`, `net`, `vias`, `coverage U1`,
   `silk`, `settings`, `ratsnest` (airwires left, with the open pad clusters, P6-T1); `pcb route measure --drc` gives the
   copper totals and the DRV-class part's nets in one line. If the designer used `pcb route auto`, read its `route.json`:
   `final.new_errors` must be empty or explained in the log, `start.inherited_by_type` is placement the router could not fix. Re-do every calculation in `DESIGN_LOG.md` (pull-up vs bus capacitance, sink current with
   the chain, decoupling distance, address). A missing calculation is a finding; a wrong number is an overclaim.
5. **Regenerate from clean.** `pcb regen-check <copy> --cmd tools/regen.sh --board layout/x/x.kicad_pcb --generated layout fab`.
   Anything but REGENERATES is a major: code is the source of truth only if this passes (R1-Z1-F2, P1-T10).
6. **Package.** `pcb fab <copy>/x.kicad_pcb --out <review_dir>/fab`: `bom_missing_lcsc`, `cpl_origin_offsets_mm`,
   file count; compare the designer's BOM (MPN, Manufacturer, LCSC, Datasheet on every line; LCSC like `C\d+`;
   DNP with a note). Read `BRINGUP.md` as the technician: every step names a test point or pin and an expected
   reading; the `silk` and `test_points` rows say whether those parts are findable on the board.
7. **Verify previous issues.** Re-run the measurement that defined each one; mark FIXED, PARTIAL or NOT FIXED
   with the new number.
8. **Walk `checklist.md`**, cite a row or a `pcb q` line per item. Look at the renders once, at the end, for
   silk readability and connector orientation only.
9. **Score with `rubric.md`**, write the anchor next to each score, then `review.md` and `review.json`.

## Evidence rules

- Measured beats inferred. "C3 to U1.8 2.639 mm (pcb q dist)" is evidence; "the cap looks far" is a lead.
- Both DRC numbers, always. A packed 0 is not a result on its own (P1-T3).
- Quote coverage. If a class of problem was not checked, say so instead of implying it passed.
- Re-run, don't trust. The designer's clock, counts and adjectives were all wrong at least once in rung 1
  (R1-Z1 "56 min" vs 2 h 55 in progress.md; R1-S1 "2x the floor" at 1.33x).
- Rows, not probe scripts. A measurement you make twice belongs in `review_checks.json` so the designer re-runs it.
