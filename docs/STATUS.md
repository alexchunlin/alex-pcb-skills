# Status (updated 2026-10-31, phase 1-3 items 1-4 done)

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
  pack in the project dir shapes the zone fill; P1-T15). `tools/verify_all.sh`: 98 checks on the two rung-1
  boards and Plink, about 7 min, all passing.
- Decisions (Alex): code is the source of truth; Zener provisional front end for rung 2; 4 layers by default with
  the phase-6 experiment deciding 6/8. Do not reopen.
- Next, in order (handoff "Next"): 5 schematic post-fixer for Zener output (fields on symbol instances, PWR_FLAGs,
  global labels, lib_id embedding, DNP; R1-Z1-T3) with upstream issues at github.com/diodeinc/pcb; 6 SKILL.md + review skill; 7 verify `--changed` selector + replay bench; 8 rung-1 attempt 2.
- Not done: no SKILL.md yet (item 6), no `tools/bench/replay.py`, no workflow template. The
  commits: phase 0, items 1-4.
