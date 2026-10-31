# Review protocol (phase 0, no tools)

You are the reviewer, not the designer. Score an attempt 1-10 on three metrics with measured evidence. Every issue
carries a number, a file or a command a third party can re-run. "Looks wrong in the render" is a lead, not a finding.

## Steps
0. Create `<review_dir>/notes.md` first and append each measurement as you make it.
1. Re-run ERC and DRC yourself on a copy of the project with `kicad-cli` (JSON), and DRC again with the kicad-druid
   JLCPCB rule pack (`/tmp/pcb-ref/kicad-druid/JLCPCB/JLCPCB.kicad_dru` copied next to the board with the board's
   name, plus a sentinel rule `track_width min 99mm` severity warning that must fire). Diff against what the
   designer claimed. Any error they did not mention is an overclaim finding.
2. Export the netlist (`kicad-cli sch export netlist --format kicadxml`) and verify every bus and connector pin map in
   the brief from the netlist, not from the drawing: Qwiic pin order on both connectors, I2C address jumper, pull-up
   nets, decoupling cap nets. Use `pcbnew` (KiCad's bundled Python) for distances: decoupling cap pad to IC pin, trace
   widths per net, via sizes, plane coverage under the IC.
3. Check the BOM: every part has MPN, Manufacturer, LCSC, Datasheet; LCSC numbers look like `C\d+`; passives have
   values and packages; nothing DNP without a note.
4. Read `DESIGN_LOG.md` and `BRINGUP.md`: every claimed calculation gets re-done (pull-up vs bus capacitance,
   decoupling placement, address). Missing calculation = finding.
5. Rank issues by severity: **blocker** (would not work, would not fab, would not assemble), **major** (works with
   real risk or rework), **minor** (polish). Each with evidence and a fix with numbers.
6. Score with the anchors below, write the anchor matched next to each score.

## Anchors (match the lowest that holds; round down)
| Score | Anchor |
|---|---|
| 10 | No credible issue; you would order it. |
| 9 | Minor polish only; ERC/DRC/fab-rule 0 errors and every warning explained; every brief item verified from the netlist or a measurement. |
| 8 | Works; at most 2 majors, each fixable in under an hour without a re-layout. |
| 7 | Works; 3+ majors, or one major that needs a re-layout. |
| 6 | Any blocker caps here; or real risk of rework at assembly or bring-up. |
| 5 | Two blockers, or a blocker in the core function (the I2C bus, the sensor power). |
| <= 4 | Would not work as designed. |

Metrics: **Electrical correctness** (nets, values, pin maps, power), **Manufacturability** (fab rules, assembly,
courtyards, silk, bring-up), **Documentation/intent** (log, calculations, bring-up, BOM fields, code as source of
truth and regenerable).

## Output
`<review_dir>/review.md`:
```
# Review: <project>, attempt N
Checks re-run: ERC <errors>/<warnings>; DRC <errors>/<warnings>; fab pack <errors>; sentinel fired: yes/no
| Metric | Score | Anchor matched | One-line reason |
## Measurements (item, value, source command)
## Issues (ranked; severity, problem, evidence, fix)
## Overclaims (what the designer said vs what you measured)
## What is good
```
and `review.json` with `{scores: {electrical, manufacturability, documentation}, issues: [{severity, title, evidence, fix}], checks: {...}}`.
