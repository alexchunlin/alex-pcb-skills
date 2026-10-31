# Scoring rubric

Scores are absolute, never relative to the previous attempt. Match the **lowest** anchor whose condition holds.
Round down. Three metrics: **Electrical correctness** (nets, values, pin maps, power, addresses),
**Manufacturability** (fab rules, assembly, courtyards, silk, bring-up), **Documentation/intent** (log with
calculations, bring-up, BOM fields, checks.json coverage, code as source of truth and regenerable).

| Score | Anchor (all metrics) |
|---|---|
| 10 | No credible issue; you would order it. |
| 9 | Minor polish only. `pcb drc` 0 errors plain and packed, `pcb erc` 0 errors with every warning explained, `pcb check` 0 fails with every warn accepted for a reason, `pcb regen-check` REGENERATES, every brief item verified from the netlist or a measurement. |
| 8 | Works. At most 2 majors, each fixable in under an hour without a re-layout. |
| 7 | Works. 3 or more majors, or one major that needs a re-layout. |
| 6 | Any blocker caps the metric here; or real risk of rework at assembly or bring-up. |
| 5 | Two blockers, or a blocker in the core function (the bus, the sensor power, the motor drive). |
| <= 4 | Would not work as designed. |

Severity:
- **Blocker:** would not work, would not fab, would not assemble. A pin map wrong in the netlist, a rail with no
  source, a `pcb drc` error class the fab rejects (clearance, hole size), a part not purchasable.
- **Major:** works, with real risk or rework. A plain-DRC error hidden by the pack, decoupling outside the brief's
  limit, a pull-up chain over the sink limit, regeneration that fails from clean, a bring-up step with no test point.
- **Minor:** polish. Hidden refdes on a named part, a BOM column, CPL origin offsets, title block, a wrong number
  in the log with the right design.

## Metric-specific anchors

**Electrical.** 9 needs every connector pin map, bus address, strap, pull-up and decoupling row passing in
`pcb check`, the ERC warnings explained, and the calculations in the log reproducing. R1-Z1 scored 8: all nets
verified, but C3 at 2.64 mm against the brief's 2 mm and 20 plain-DRC errors behind the pack.

**Manufacturability.** 9 needs `pcb drc` plain 0 and packed 0 with the sentinel fired, `margin` rows at or above
the declared ratios, a `pcb fab` package with every BOM line sourced, CPL offsets explained, silk refdes on every
part the bring-up names, and test points for every rail. R1-S1 scored 8: packed 0 but plain 18 (NPTH to zone at
the pack's floor), and "2x the floor" measured at 1.33x on vias.

**Documentation.** 9 needs `pcb regen-check` REGENERATES on `tools/regen.sh`, a `checks.json` with a row for every
brief claim, a log whose numbers the reviewer reproduces, and a bring-up a technician can run. R1-Z1 scored 8:
`regen.sh` exited 1 from clean and the design-margin numbers in the log were not the ones on the board.

## review.md format

```
# Review: <project>, attempt N
Checks re-run: ERC <e>/<w>; DRC plain <e> packed <e> (sentinel fired yes/no, capped: ...); pcbcheck <f> fails <w> warns; regen-check <verdict>
| Metric | Score | Anchor matched | One-line reason |
## Previous issues   (one row each: issue, FIXED/PARTIAL/NOT FIXED, new number)
## Measurements      (table: item, value, source command or check row)
## Issues            (ranked; severity, problem, evidence, fix with numbers)
## Overclaims        (what the designer said vs what you measured)
## Check-config audit (accepted_warns disputed, brief items with no row, rows you added)
## What is good
```

`review.json`: `{scores: {electrical, manufacturability, documentation}, anchors: {...}, checks: {erc, drc_plain,
drc_packed, sentinel, pcbcheck, regen}, issues: [{severity, title, evidence, fix}], overclaims: [...]}`.
