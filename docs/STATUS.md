# Status (updated 2026-10-31, phase 1-4 items 1-7 done)

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
  P1-T18, P1-T19). `tools/verify_all.sh`: 136 checks, about 10 min, all passing.
- Decisions (Alex): code is the source of truth; Zener provisional front end for rung 2; 4 layers by default with
  the phase-6 experiment deciding 6/8. Do not reopen.
- Next (handoff "Next" item 8): rung-1 attempt 2 on the tools, two designers (Sonnet 5.5 and Fable) on the
  `kicad-design` skill, reviewers on Fable with `pcb-design-review`, same brief, compared with 9/8/8 and 8/8/8 and
  the token counts in FINDINGS; then rung 2 (`bench/design/rung2-motor-channel/BRIEF.md`). Before that: link the
  skills into `~/.claude/skills`, decide on posting `docs/upstream/`.
- Not done: no workflow template (phase 5), no topology or silk-readability rows (the two Plink misses), skills not
  linked into `~/.claude/skills`, upstream issues not posted. The
  commits: phase 0, items 1-5.
