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

## Decisions from Alex after rung 2 (2026-11-01)
- **Default designer: Opus 5.5 at medium effort** (rung 2: 8/6/7 in 38.7 min and 189k output tokens, the cheapest and
  the only 8 on electrical). Reviewers stay on Fable at default effort. Fable at medium is not a verdict on Fable:
  one 14-minute generation hit the 64k thinking cap and emitted nothing (R2-T3); if a Fable designer runs again,
  run it at default effort.
- **Next structural idea, not yet built:** a hierarchical schematic with one Sonnet 5.5 sub-agent per sub-sheet
  (power_in, buck, ldo, driver, connectors), the way the 3D loop runs one builder per subsystem. The plan agent
  writes the sheet contract (nets at the sheet boundary, the checks.json rows for that sheet); each sheet agent
  builds its `.zen` module and must pass `pcb check --only` on its rows before hand-back; the layout stays one
  agent. Zener modules already map one to one onto sheets (all three rung-2 designers wrote five modules).

## Update after rung 2 (same day, later)
Rung 2 ran with three designers at medium effort (Alex's choice): Sonnet 7/8/8, Opus 8/6/7, Fable 4/4/6 unfinished.
FINDINGS "Rung 2, attempt 1" has the harvest; P1-T22 the tool fixes. The bench is 9 boards and 37 labels. The next
item is phase 6 routing, not more rows: all three designers spent their time at the DRV8874's 0.65 mm pitch (R2-T2).
Memory holds Alex's rules: no posts to repos he does not own; rung-2 designers at medium effort.

## Next, in order
1. **Phase 6 routing.** All three rung-2 designers lost most of their time at the DRV8874's 0.65 mm pitch (R2-T2;
   Sonnet wrote its own maze router). Measure before wrapping: freerouting 2.5.0 (native macOS binary, CLI; export
   DSN from pcbnew via `pcblib`, import SES) and KiCadRoutingTools (reads/writes `.kicad_pcb`, no DSN round trip)
   on the three archived rung-2 boards with their copper stripped (`Board.clear(tracks=True)` keeps placement):
   clean-route rate, DRC errors after `pcb drc`, via count, total length, wall time. Then `pcb route` wrapping
   whichever wins, with the DRC fix loop and the sentinel. GAMEPLAN section 3 has the URLs and the 1,157-board
   benchmark numbers to compare against.
2. **Rows the rung-2 reviews asked for** (P1-T22 end): pour-neck width (erode the filled polygon by half the IPC
   width and test the pad stays connected), a sourcing-attributes row (JLC part pin count vs footprint pads; the
   Opus blocker), capacitor ripple-current rating against the PWM ripple (calcs can do it once the rating is a
   field), bring-up text against PINMAP (the Fable major), thermal pads counted with in-pad PTH.
3. **Rung-2 attempt 2** with Opus at medium on the routing tool, reviewer on Fable; compare with 8/6/7.
4. **The per-sheet loop** (the decision above): a `templates/pcb-loop.workflow.js` only if Alex opts into the
   Workflow tool; otherwise the plan/sheet/layout/review roles as Agent calls, like the 3D loop's roles.
5. Phase 5 loop template, the two Plink rows (topology, silk readability), as they come up.

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
