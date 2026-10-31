# Status (updated 2026-10-31, phase 1 item 1 done)

- Plan: `docs/GAMEPLAN.md`. Evidence: `docs/FINDINGS.md`. Survey with URLs: `docs/SURVEY-2026-10-31.md`. Handoff
  from the kickoff session: `docs/HANDOFF-2026-10-31.md` (its "Next" list is the work order).
- Phase 0 done: tooling verified (P0-T1..T10), rung-1 and rung-2 briefs in `bench/design/`, review protocol in
  `bench/design/REVIEW.md`, two rung-1 attempts designed and reviewed (`~/code-stuff/alex-pcb-runs/rung1-{skidl,zener}-a1`).
  Result: SKiDL 9/8/8 (49 min), Zener 8/8/8 (57 min); both missed 9/9/9 on the same two majors (DRC reported only
  with the fab pack loaded; regeneration not verified from a clean tree).
- Phase 1 item 1 done: `skills/kicad-design/scripts/pcb` wrapper (`erc`, dual `drc` with sentinel and
  pack-vs-setup floor, `netlist`, `diff`, `render`, `svg`, `stats`, `fab`, `q`, `py`, `guard`, Diode passthrough
  with `--no-open` forced). Evidence P1-T1..T8. `tools/verify_all.sh`: 59 checks on the two rung-1 boards and
  Plink, 1 min 40 s, all passing.
- Decisions (Alex): code is the source of truth; Zener provisional front end for rung 2; 4 layers by default with
  the phase-6 experiment deciding 6/8. Do not reopen.
- Next, in order (handoff "Next"): 2 `regen-check` (fresh dir, project regeneration, diff netlist + DRC JSON +
  gerber member hashes from `fab.json`); 3 `pcbcheck` v0 with `checks.json`; 4 `pcblib.board`; 5 schematic
  post-fixer; 6 SKILL.md + review skill; 7 verify `--changed` selector + replay bench; 8 rung-1 attempt 2.
- Not done: no SKILL.md yet (item 6), no `tools/bench/replay.py`, no workflow template. Nothing committed; the
  phase-0 files are staged, the phase-1 files are not.
