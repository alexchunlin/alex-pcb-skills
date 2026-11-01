# Status (updated 2026-10-31, phase 1-4 items 1-8 done)

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
- Not done: no workflow template (phase 5), no topology or silk-readability rows (the two Plink misses), no routing tool (phase 6). The
  commits: phase 0, items 1-5.
