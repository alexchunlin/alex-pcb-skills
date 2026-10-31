# Status (updated 2026-10-31, phase 1-4 items 1-6 done)

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
  and `skills/pcb-design-review/` (SKILL.md, rubric.md, checklist.md); P1-T17. `tools/verify_all.sh`: 111 checks on
  the two rung-1 boards and Plink, about 8 min, all passing.
- Decisions (Alex): code is the source of truth; Zener provisional front end for rung 2; 4 layers by default with
  the phase-6 experiment deciding 6/8. Do not reopen.
- Next, in order (handoff "Next"): 7 `verify_all --changed` selector (port from alex-3d-skills) + `tools/bench/replay.py`
  scoring the rung-1 attempts and the Plink pre/post-rework boards against `labels.json`; 8 rung-1 attempt 2 on the
  tools (designers on Sonnet 5.5 and Fable, reviewers on Fable), then rung 2.
- Not done: no `tools/bench/replay.py`, no workflow template, skills not yet linked into `~/.claude/skills`, upstream
  issues not posted. The
  commits: phase 0, items 1-5.
