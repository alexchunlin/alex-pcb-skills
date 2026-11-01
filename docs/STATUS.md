# Status (updated 2026-11-01, phase 6 routing measured and wrapped)

- Plan: `docs/GAMEPLAN.md`. Evidence: `docs/FINDINGS.md`. Survey with URLs: `docs/SURVEY-2026-10-31.md`. Handoff
  from the kickoff session: `docs/HANDOFF-2026-10-31.md` (its "Next" list is the work order).
- Phase 0 done: tooling verified (P0-T1..T10), rung-1 and rung-2 briefs in `bench/design/`, review protocol in
  `bench/design/REVIEW.md`, two rung-1 attempts designed and reviewed (`~/code-stuff/alex-pcb-runs/rung1-{skidl,zener}-a1`).
  Result: SKiDL 9/8/8 (49 min), Zener 8/8/8 (57 min); both missed 9/9/9 on the same two majors (DRC reported only
  with the fab pack loaded; regeneration not verified from a clean tree).
- Phase 1 item 1 done: `skills/kicad-design/scripts/pcb` wrapper (`erc`, dual `drc` with sentinel and
  pack-vs-setup floor, `netlist`, `diff`, `render`, `svg`, `stats`, `fab`, `q`, `py`, `guard`, Diode passthrough
  with `--no-open` forced). Evidence P1-T1..T8. Item 2 done: `pcb regen-check` (P1-T9, P1-T10: both rung-1
  regenerations diverge on the first pass from clean; SKiDL's was unnoticed). Item 3 done: `pcb check` (pcbcheck v0, nine
  checks, `examples/rung1-{zener,skidl}-a1/checks.json`; P1-T11..T13). Item 4 done: `pcblib.board` (one module over
  SWIG pcbnew, traps handled; the Zener layout ported to 107 lines with identical copper; P1-T14 found that a rule
  pack in the project dir shapes the zone fill; P1-T15). Item 5 done: `pcb schfix` (fields, DNP guard, global labels,
  symbol lib, PWR_FLAGs; ERC 2/32 to 0/1 on a raw Diode schematic; P1-T16) with five upstream issue drafts in
  `docs/upstream/` awaiting Alex's go to post. Item 6 done: `skills/kicad-design/` (SKILL.md, reference/, templates/project/)
  and `skills/pcb-design-review/` (SKILL.md, rubric.md, checklist.md); P1-T17. Item 7 done: `tools/verify_all.sh --changed`
  (selector ported) and `tools/bench/replay.py` with 4 boards and 17 labels (recall 8/11 fails, 0 false fails;
  P1-T18, P1-T19). `tools/verify_all.sh`: 169 checks, about 17 min, all passing.
- Decisions (Alex): code is the source of truth; Zener provisional front end for rung 2; 4 layers by default with
  the phase-6 experiment deciding 6/8. Do not reopen.
- Item 8 done: rung-1 attempt 2 on the skill. Sonnet 5.5 designer 9/9/8 in 42.9 min, Fable designer 9/8/8 in
  43.9 min (attempt 1: 9/8/8 and 8/8/8 in 49 and 57 min); both attempt-1 majors gone; the new majors were a
  lowered board setup and a gerber-order false alarm, both fixed as tools (P1-T20: `policy` and `fields` rows,
  scoped exception rules in `pcb drc`, canonical gerber hashes). FINDINGS "Rung 1, attempt 2". Both attempt-2
  boards are in `examples/` and the bench (6 boards, 24 labels).
- Next: rung 2 (`bench/design/rung2-motor-channel/BRIEF.md`) on the skill, one designer first (Sonnet 5.5, the
  cheaper of the two at the same score), reviewer on Fable; it exercises part import (DRV8874, TPS54620 are not in
  the stock libraries, P0-T8), current-vs-width rows and the 4-layer plane policy, none of which rung 1 touched.
  Before launching: a `calcs` row family (trace width vs current, LDO/buck dissipation) in pcbcheck, since rung 2's
  claims will be those. Handoff for the next session: `docs/HANDOFF-2026-10-31-session2.md`.
- Decided 2026-11-01 (Alex): default designer is Opus 5.5 at medium effort; reviewers Fable. Next structural idea:
  hierarchical schematic with one Sonnet sub-agent per sub-sheet (handoff session 2).
- Decided 2026-10-31 (Alex): upstream drafts stay unposted (no posts to repos he does not own); skills linked into
  `~/.claude/skills`; rung 2 after the `calcs` rows, with three designers at medium effort (Sonnet 5.5, Opus 5.5,
  Fable) and reviewers on Fable.
- Rung 2 done (2026-10-31 evening): three designers at medium effort on the skill, reviewers on Fable. Sonnet 7/8/8
  (56.6 min), Opus 8/6/7 (38.7 min), Fable 4/4/6 (70.8 min, unfinished). Shared majors (VM pin feed, bypass-cap
  distance on `input`-typed pins) became `feeds` and pin-type-free `decoupling` rows (P1-T22); the three boards are
  archived in `examples/` and labelled in the bench (9 boards, 37 labels, 0 false fails). FINDINGS "Rung 2".
- Next: phase 6 routing (freerouting 2.5 / KiCadRoutingTools wrappers measured against the rung-2 boards: all three
  designers lost most of their time at the DRV8874's 0.65 mm pitch, R2-T2); then the rows listed under P1-T22
  (pour-neck width, sourcing attributes, cap ripple rating, bring-up vs pin map); then rung-2 attempt 2.
- Phase 6 routing (2026-11-01, branch `alexchunlin/phase6-routing`): freerouting 2.5.0 (jar on OpenJDK; the native CLI
  crashes, P6-T2), KiCadRoutingTools 0.23.7 and kct 0.26.0 measured on the three rung-2 boards stripped with placement
  kept (`tools/bench/route_bench.py`, 33 rows in `tools/bench/results/route.jsonl`, P6-T3). KRT routes both finished
  boards clean with the pours in place in 23 to 44 s with half the designers' vias; freerouting leaves 21 to 23 airwires
  and necks tracks under the setup minimum; kct did not finish in 20 min. `pcb route auto` wraps KRT (engine pass,
  refill, dual DRC, second pass, stitch pass, inherited errors separated, exit 1 unless clean; P6-T4); `pcb route
  strip|export-dsn|import-ses|fill|measure` and `pcb q ratsnest` are the primitives (P6-T1). verify_all 27.
- Rung-2 attempt 2 done (2026-11-01, Opus 5.5 at medium on `pcb route auto`, reviewer Fable at default): **8/8/7** in
  71.3 min and 196k tokens against attempt 1's 8/6/7 in 38.7 min and 189k. The router routed clean on its first call;
  the designer spent 30 min reacting to its copper (hand escapes at the DRV8874, keepouts to get signals off the
  planes) and 8 min on regen-checks that failed because Zener reorders footprints per `pcb layout` and KRT routes in
  that order (P6-T6; fixed, `pcb route auto` sorts the footprints first, the attempt REGENERATES with the fix). The
  reviewer's majors: a 5 V header pin and the VIN bulk cap fed only through plane spokes or a via chain (now `feeds`
  labels on the archived board, bench 10 boards / 41 labels / 0 false fails), no LDO heat-sink copper. FINDINGS
  "Rung 2, attempt 2". Hypothesis verdict: score up on manufacturability, time and tokens not down (n = 1).
- Next: make the router pay in time: keep signal nets off the plane layers and wide-class nets with the layout script
  by default (wrapper or skill), generated `feeds` rows for every pin of a wide-class net; then the review rows
  (pour-neck width, sourcing attributes, cap ripple, bring-up vs pin map, LDO pour area vs theta); then attempt 3;
  the rows the rung-2 reviews asked for (pour-neck width, sourcing attributes, cap ripple rating, bring-up vs pin map);
  the per-sheet loop. The design-margin experiment (4/6/8 layers) can now run on the route bench.
- Not done: no workflow template (phase 5), no topology or silk-readability rows (the two Plink misses).
