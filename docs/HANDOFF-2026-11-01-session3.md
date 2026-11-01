# Handoff: alex-pcb-skills, end of session 3 (2026-11-01, branch `alexchunlin/phase6-routing`)

Read in this order: `docs/STATUS.md`, `docs/FINDINGS.md` "Phase 6" (P6-T1..T5), `skills/kicad-design/SKILL.md` (the
`pcb route auto` row and step 4), `tools/bench/README.md` (route bench and the router install recipe). The two earlier
handoffs hold Alex's standing decisions and the designer/reviewer prompts.

## State
- Phase 6 item 1 is done and committed on this branch (merging into `main` is Alex's): the routers measured on the three
  archived rung-2 boards with placement kept (`tools/bench/route_bench.py`, 33 rows in `tools/bench/results/route.jsonl`),
  and `pcb route auto` wrapping KiCadRoutingTools with the second pass, stitch pass, dual DRC, inherited-error split and
  the clean verdict. verify_all is 27 sections, 177 checks, about 18 min; `--changed` ran green except one flake (P6-T5).
- Router installs live under `/tmp/pcb-ref/` (freerouting jar + Homebrew OpenJDK 27, KiCadRoutingTools tree + `.venv`);
  the README has the six lines to re-create them. verify_all 27 says NOTE and skips the loop check when KRT is absent.
- Not run yet: a designer on `pcb route auto`. The numbers so far are the tool on the designers' placements, not a
  designer using the tool.

## Update, later the same day: rung-2 attempt 2 ran
- Opus 5.5 at medium on `pcb route auto`, reviewer Fable at default (Alex's call, to keep the reviewer constant):
  8/8/7 in 71.3 min / 196k tokens against 8/6/7 in 38.7 min / 189k. FINDINGS "Rung 2, attempt 2" has the table, the
  review and the reading; the board is `examples/rung2-zener-a2-opus/` with the reviewer's two `feeds` rows added to
  its config and labelled (R2A2-O-1/2). P6-T6: KRT follows footprint file order and Zener reorders per layout, so
  regen-check failed; `pcb route auto` now sorts the footprints first and the attempt REGENERATES.
- The time did not fall. The designer's 30 min of reaction were two things: signals routed onto the plane layers
  (it added keepouts) and wide-class nets routed as 0.2 mm stubs or plane spokes (it hand-routed VM/OUT, the reviewer
  found J3.1 and C17 it missed). Next tool move, before attempt 3: `pcb route auto` routes signal nets on the outer
  layers only by default and refuses to route a net in a wide class (leave those to the layout script), and a `feeds`
  row is generated for every pin of a wide-class net.

## Decisions pending with Alex (do not act without him)
- Merge this branch.
- Whether rung-2 attempt 2 (Opus 5.5 at medium, reviewer Fable, same brief and PATH.md) runs before or after the rows in
  item 2. The skill now tells the designer to place and pour by hand and route by tool.

## Next, in order (from the session-2 handoff, item 1 done)
1. Rows the rung-2 reviews asked for (P1-T22 end): pour-neck width, sourcing attributes, capacitor ripple rating,
   bring-up text against PINMAP, thermal pads with in-pad PTH.
2. Rung-2 attempt 2 with Opus at medium on the routing tool; compare with 8/6/7 and 38.7 min. Watch `route.json` in the
   run dir: `final.new_errors` is the designer's to fix, `start.inherited_by_type` is placement.
3. The per-sheet loop (Agent tool unless Alex says "use a workflow").
4. The design-margin experiment (GAMEPLAN phase 6, 4/6/8 layers, +20 % area, 0603 vs 0402) can run on the route bench
   as it stands: strip, route, measure, with the same rows.

## Guardrails added this session
- A router that loosens the board setup is caught: `setup_changed` in every bench row and in `route.json`; KRT runs
  with `--no-fix-drc-settings --escalation off` first (P6-T2 e, P6-T3).
- Clean means 0 airwires and no new plain errors and packed errors not above the inherited count; a router's own
  "all routed" is never the verdict (freerouting says routed with 21 GND pads open, P6-T3).
- The freerouting native CLI is never used (it crashes and hangs, P6-T2); `-drc` is a mode, not an output.
