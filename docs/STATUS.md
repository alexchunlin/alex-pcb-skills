# Status (updated 2026-11-03, dev merged to main, all four spikes merged)

- Plan: `docs/GAMEPLAN.md`; next steps and moonshots after phase 6: `docs/ROADMAP-2026-11-01.md`. Evidence: `docs/FINDINGS.md`. Survey with URLs: `docs/SURVEY-2026-10-31.md`. Handoff
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
- Session 4 (2026-11-02, FINDINGS "Routing session 4"): `pcb route auto` routes outer-only by default (ROUTE-T1) and is
  now reproducible run to run (ROUTE-T2 track UUIDs from content, ROUTE-T3 KRT hash seed pinned); the judges `refplane`
  (pcbcheck, opt-in, on in the template) and `pcb irdrop` (DC drop and current density on real copper, scipy via `uv`);
  pcblib `pad_feed`/`pad_feed_search`/`thermal_vias` and the SaveBoard re-net trap fixed (ROUTE-T4). verify_all has 28
  sections. `pcb route waves` (WAVES-1): power first, then sense, then the rest, wave 0 feeds and thermal vias, per-wave
  keepouts; on Alex's stackup VIN loss 440 mW (one-shot) -> 158 (waves) -> 102 (waves + feeds).
- Decided 2026-11-02 (Alex): stackup policy is two solid GND planes (In1, In2), 3V3/5V routed point to point, high-current
  rails as pours or thick tracks, signals only over unbroken ground. The archived rung-2 boards predate it (In2 power
  plane), which is why `refplane` is opt-in rather than on for the replay bench.
- Starved through-hole thermals fixed (STARVE-1); feeds planned at placement with `plan_feeds` and the `feed_room` row,
  every feed fits the attempt-2 placement and waves + feeds route it CLEAN at 94 mW VIN loss (FEED-2).
- PLAN-1 (2026-11-03): a 6-plan deterministic search matches Sonnet agents on 2 of 3 boards at zero tokens; agents cost
  65-95k tokens each and hung the router twice (per-wave timeout added). Pending with Alex: the judge priority order.
- Next: `pcb route waves --search` (the 6 plans in parallel, pick by pass limits then priority); teach the `feeds` row
  to read pour feeds (irdrop); then a routing-stage designer run from the attempt-2 placement (old wrapper
  first, to check the stage run reproduces attempt 2), then 3 against 3.
- Session 5 (2026-11-03, FINDINGS "Routing session 5"): SIG-1 `pcb signals` and the `signals` block (driver, rise time
  with source, slowing parts, victim flag; code computes knee and bucket); the three rung-2 boards classified from
  `tools/bench/rung2_signals.py`: 7 nets in bucket 3 (SW, BOOT, PWM, DIR, nSLEEP, ENC_x_IN), 7 in bucket 2 (MOTOR_A/B
  at 150 ns, nFAULT, ENC_x, IPROPI), the rest bucket 1, 7-9 victims. Table shown to Alex before any judge uses it.
- Per-bucket judges done (SIG-2, SIG-3): `refplane` limits follow the bucket (3/4 hard at 0 mm, 2 warns at 5 mm, 1 and
  rails a cost), `return_via` (GND via within 2 mm of every bucket-3 via; fails on every PLAN-1 plan and the archived
  attempt-2 board, so the fix is a post-route via placement, not a plan choice), `exposure` (same-layer mm within 1 mm of
  SW copper, victims x3; replaces the switch-node box: opus2 rules 16.4 -> 0.8 mm). Prior art measured: KRT
  `--add-gnd-vias` placed 0 of 42 and wrote the .kicad_pro; kct signal-integrity 0 findings, current-sense nearest-net only.
  verify 28 covers all three. Bench `judges()` records the new columns; `plan_bench.py rescore` re-judges old runs.
- Step 3 done (SIG-4): the 31 PLAN-1 runs rescored and ranked (hard limits, then weighted cost; `plan_bench.py rank`):
  opus2's winner moves from the zone plan to rules; opus and sonnet tie with the agents' best. The opus hard-limit
  case was J3's pin-field void (refplane now skips a net's own connector pins). `pcb route waves --search` (six plans
  in parallel, judged, ranked) reproduces PLAN-1 exactly in 170-235 s a board at zero tokens. `pcb route return-vias`
  closes the return-via limit (6 vias in 0.8 s, DRC clean); the search runs it, and with it every plan on every board
  passes the limit. verify 29 covers signals, variants, rank, return vias.
- Plink benchmark prepared, not run (PLINK-0, Alex: not until the tools maximise quality per cost): the designer's
  board judged as the baseline, `tools/bench/plink/checks.json` (106 nets classified), `pcb route classes`, the bench's
  `plink` board (placement and pours kept). Readiness list in `docs/HANDOFF-2026-11-03-session6.md`: calibrate KRT wall
  time, feeds vs kept pours, drop currents/feeds as hard limits on a pour-fed board, the USB pair, the reference's own
  4 airwires and 71 DRC errors.

- 2026-11-03: `dev` (routing sessions 4 and 5) merged into `main`; README rewritten with renders, a routing demo and
  the results chart (`tools/readme/make_images.sh`). Four `Spike:` issues (#1 to #4) written with hypothesis, null,
  procedure and cost, each reviewed by a literature agent and corrected, then run by Opus 5.5 agents in worktrees and
  merged where the number justified it (FINDINGS "Spikes 1 to 4"). Kept: the `irdrop` row (precision on pour-fed boards,
  one new true positive), `basic_parts`, the pogo jig and OpenHTF bring-up skeleton and `docs/spikes/ORDER.md` (the order
  is Alex's), the C8 mutation bench (16 of 21 caught; misses are missing config rows), `signal_vias` and `pcb q
  conflicts`, 84 labelled placements, the open-schematics index and placement priors (33/50 vs 17/50 clean), the opt-in
  `refstat` kind. Dropped: guide corridors, rev-diff mining, corpus-learned limits. Roadmap item 6 stays open as order
  variants in `pcb route waves --search`. Spike #1 (GBT surrogate over HPWL, search arms): all null, no surrogate in `pcb`; the 651 labelled placements,
  features and verify 33 are kept (FINDINGS SPIKE-1). Next spike written up for handoff:
  `docs/spikes/HANDOFF-spike-5-class-priors.md`.
- 2026-11-04: Spike #5 run and merged, no change to `pcb` (FINDINGS "Spike 5"). The class prior transfers to an unseen part
  (39/50 part held out, 33/50 package held out, uniform 17) but ties KRT's decap cost on rung 1 (37/50), and on rung 2 the
  pre-registered rerun reached 34/50 against a 35/50 bar (uniform 24, p = 0.068), with better signal vias and rows than
  uniform and worse than perturbing the designer's satellites. Kept: role-keyed `boardmeasure`, `eagle.py`, `pooling.py`,
  the class table and 8,297-hit index, verify 34. Fable was out of credits, so Opus ran the review and the spike.
- Spike 6 (2026-11-04, branch `spike/6-block-placement`, not merged): block order did not beat one pass at n = 3 (blind layout median 7 vs 7, VIN loss 55.7 vs 34.4 mW), so `pcb block` stays opt-in behind PATH.md. The rules `via_in_pad`, `edge_margin` and `gnd_islands` are on in the template. Five rung-3 boards all reviewed "order after small fixes"; CPL rotation wrong on 3 of 3 examined. One `verify_all` failure stands: section 27 `route auto` on the Qwiic board under the new rules. Tool list in `docs/spikes/spike-6-block-placement.md`.
