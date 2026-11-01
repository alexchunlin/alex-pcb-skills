# Handoff: alex-pcb-skills, end of session 2 (2026-10-31)

Read in this order: `docs/STATUS.md`, `docs/FINDINGS.md` from "Phase 1" to the end (P1-T1..T20 and "Rung 1,
attempt 2"), `skills/kicad-design/SKILL.md`, `skills/pcb-design-review/SKILL.md`, `tools/bench/README.md`. The
first handoff (`docs/HANDOFF-2026-10-31.md`) still holds the decisions Alex made and the prompts that ran the loop.

## State
- Phase 0 to 4 of the GAMEPLAN are done and committed on `main`: the `pcb` wrapper (dual DRC with sentinel and
  pack floor, `check`, `q`, `fab`, `regen-check`, `schfix`, `py`, Diode passthrough), `pcblib.board`, pcbcheck with
  13 checks, both skills, the replay bench (6 boards, 24 labels) and `verify_all.sh --changed` (149 checks,
  14 min). Every rule cites a FINDINGS ID; `verify_all` section 20 checks the citations exist.
- Rung-1 attempt 2 on the skill: 9/9/8 (Sonnet 5.5, 42.9 min) and 9/8/8 (Fable, 43.9 min) against 9/8/8 and
  8/8/8 without tools. The reviewers' remaining majors became `policy` and `fields` rows and the gerber-verdict
  fix (P1-T20); on the archived boards the bench now catches them.
- Run dirs (outside the repo): `~/code-stuff/alex-pcb-runs/rung1-{skidl,zener}-a1`, `rung1-zener-a2-{sonnet,fable}`,
  each with `review/`. Board files and configs are archived under `examples/`; the bench and verify read those
  except regen-check, which needs the `.zen` and tools of the run dirs (`RUNS`).
- Reference clones under `/tmp/pcb-ref/` (re-clone if gone; URLs in GAMEPLAN). kicad-druid is needed by `pcb drc
  --pack jlcpcb` (`KICAD_DRUID`).

## Decisions pending with Alex (do not act without him)
- Post the five issue drafts in `docs/upstream/` to github.com/diodeinc/pcb.
- Link the skills into `~/.claude/skills` (README has the two `ln -s` lines).

## Update after rung 2 (same day, later)
Rung 2 ran with three designers at medium effort (Alex's choice): Sonnet 7/8/8, Opus 8/6/7, Fable 4/4/6 unfinished.
FINDINGS "Rung 2, attempt 1" has the harvest; P1-T22 the tool fixes. The bench is 9 boards and 37 labels. The next
item is phase 6 routing, not more rows: all three designers spent their time at the DRV8874's 0.65 mm pitch (R2-T2).
Memory holds Alex's rules: no posts to repos he does not own; rung-2 designers at medium effort.

## Next (as planned before rung 2; items 1-3 are done, see above)
1. `calcs` rows in pcbcheck (trace width vs current per declared net current, copper pour thermal, LDO and buck
   dissipation, pull-up vs bus capacitance already exists) with the formula and a datasheet-cited limit in the
   row: rung 2's claims are these. Gate with a planted-bug test and a bench label.
2. Rung 2 (`bench/design/rung2-motor-channel/BRIEF.md`): one designer on Sonnet 5.5, reviewer on Fable, same
   prompts as attempt 2 (FINDINGS "Rung 1, attempt 2" header and `rung1-zener-a2-*/PATH.md`). Expect part
   import to be the time sink (DRV8874, TPS54620 absent from stock libraries, P0-T8): decide beforehand whether
   `easyeda2kicad` output goes through a KLC check row.
3. Harvest rung 2 into FINDINGS (R2-...), extend `labels.json`, and rerun the bench gate.
4. Phase 5 loop template (`templates/pcb-loop.workflow.js`) only if Alex opts into the Workflow tool.
5. The two Plink misses: a topology row (back-power protection on an externally fed rail) and a silk
   readability row, when a brief needs them.

## Guardrails added this session (in tools, with the ID)
- Never leave a raw fab pack in the project directory: it changes the zone fill (P1-T14); scoped exception rules
  are fine and stay in both DRC runs (P1-T20).
- The brief's numbers go in `checks.json` `policy` and are never lowered (R1-A2-T5).
- `Board.fill()` builds connectivity and fills twice (P1-T10); regen-check's verdict ignores gerber byte order
  (R1-A2-T2).
- pcbnew cannot tell a supply pin from a strap; decoupling rows name the pin (P1-T5). Netlist pin types do the
  rest (P1-T12).
