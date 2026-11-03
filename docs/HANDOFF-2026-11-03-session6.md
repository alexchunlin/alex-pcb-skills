# Handoff: alex-pcb-skills, end of session 5 (2026-11-03, branch `dev`, worktree `phase6-routing`)

Read in this order: `docs/STATUS.md` (bottom), `docs/FINDINGS.md` "Routing session 5" (SIG-1..SIG-4, PLINK-0),
`skills/kicad-design/scripts/pcbsig.py` (classes, ranking), `pcbroute.py` (`plan_variants`, `c_search`, `c_return_vias`,
`c_classes`), `tools/bench/plan_bench.py` (`rescore`, `rank`, the `plink` board), `tools/bench/plink_signals.py`.
Everything is uncommitted on `dev` (Alex commits). Previous handoff: `docs/HANDOFF-2026-11-03-session5.md`.

## How Alex wants to work (standing)
- State the hypothesis and its null before building; measure prior art first; report honestly; "don't wait on me to do
  good science". Iteration on deterministic benches; full designer runs as milestones. Frontier: tokens, time, quality,
  determinism. Stackup: In1 and In2 solid GND, 3V3/5V routed, high-current rails as pours, signals over unbroken ground.
- Commit on `dev` when he says so; never rm a variable+glob path; no posts to repos he does not own.

## What this session did
1. **SIG-1** `pcb signals` and the `signals` block: per net the driver's edge with its source, slowing parts, victim
   flag; code computes knee (0.5 / t_rise) and bucket (1 <1 MHz, 2 1-50, 3 50-500, 4 >=500). Rung-2 boards: 7 bucket-3
   nets (SW, BOOT, PWM, DIR, nSLEEP, ENC_x_IN), motor outputs bucket 2 (DRV8874 150 ns). Alex saw the table.
2. **SIG-2/3** judges: `refplane` limits by bucket (hard at 0 mm for 3/4; own-connector pin fields skipped,
   `connector_mm`), `return_via` (GND via within 2 mm of every bucket-3 via), `exposure` (same-layer mm within 1 mm of
   the switch node and other named aggressors, victims x3; replaces the switch-node box). `pcb route return-vias`
   places the missing ground vias (6 in 0.8 s on a rung-2 board, DRC clean).
3. **SIG-4** re-rank and `pcb route waves --search`: six plans in parallel, judged, ranked by hard limits then weighted
   cost (`pcbsig.plan_rank`, weights in `pcbsig.WEIGHTS`). Result in FINDINGS SIG-4: the winner changed on opus2
   (rules beats the zone plans), ties with the agents' best on opus and sonnet; the search reproduces PLAN-1's numbers
   exactly (deterministic) in 170-235 s a board with 3 jobs, zero tokens.
4. **Plink readiness (PLINK-0)**: the MotorGo Plink judged as the designer left it (baseline for the benchmark Alex
   wants), `tools/bench/plink/checks.json` with its 106-net classification (41 bucket-3, 16 bucket-2, 10 victims),
   `pcb route classes` (net classes from the config's currents for a board that has none), the bench's `plink` board
   (placement and pours kept, tracks and vias stripped, classes applied, rule plans with 15 feeds and 5 thermal-via
   pads). NOT run: Alex said not to spin the benchmark up until the tools maximise quality per cost.

## Plink benchmark: what is ready and what is not
Ready: prep (`plan_bench.py prep --board plink`, 1.5 s), rule and zone plans (`rules --board plink [--zones]`), the
judges (0.9 s on the full board), irdrop on +BATT (J11.1 to the four VM pins and PVIN at 1.5 A each: the designer's
copper is 148 mW, 8-31 mV, worst 193 A/mm2), the search with return vias.
Not ready, in the order I would do them:
1. **Wall time is unmeasured.** 106 nets, 65 x 56 mm, 0.12 mm tracks. One `pcb route auto` on the prepped base (no
   plan) calibrates KRT's time and the per-wave `timeout_s` (300 s today) before any search. Expect minutes per wave.
2. **The feeds on a pour-fed board.** The designer feeds VM and OUTx from F.Cu pours; `plan_feeds` draws pours with
   via fields designed for the rung-2 placements. On the Plink the pours are kept, so the feeds may collide with
   them (FEED-2's precheck raises per pad; `feeds_placed` in the row says how many fit). Decide: feeds off when pours
   are kept, or pours stripped too (the harder variant). Both are one flag in `BOARDS["plink"]`.
3. **`currents` and `feeds` rows do not size pours**, so on this board they fail everywhere by construction (12 of 12
   and 15 of 15 on the designer's own copper). irdrop is the power judge here; drop those two from the Plink's hard
   limits or teach `feeds` to read irdrop (noted since FEED-2).
4. **The USB pair.** usb_d+/- and the nets through R6/R7 and USBLC6 are a 90 ohm pair (bucket 3 by the 4 ns full-speed
   edge, the pair rule from USB). KRT `route_diff.py` routes pairs; `waves` has no pair wave. Either a `pairs` wave
   calling route_diff first, or accept single-ended routing and measure the length mismatch as a cost.
5. **The designer's board is not a clean reference**: 4 airwires (U8.3 and C24.1 on +5V, R24.1, R8.2) and 71 DRC
   errors (40 copper-to-edge, 5 shorting_items, zones_intersect) as published. The bench strips tracks, so the
   inherited-error mechanism only sees the pours' errors; the +5V irdrop on the original returns NaN because U8.3 is
   open. Say so in the write-up; do not "fix" the reference.
6. **Judge cost at scale**: refplane samples every 0.25 mm (0.9 s here), fine; the search's six plans at Plink wall
   times may be 10-30 min with 3 jobs. Run with `--jobs 2` if the laptop thrashes (ROUTE-T3's determinism holds under
   load, section 26's drift was a KiCad DRC count).
7. Return vias: `return-vias` skips a via boxed in by its own connector (1 of 9 on opus2); on the Plink's 2x20
   headers expect more. A second ring at 2.5 mm or moving the via is the next step; the row reports what is left.

## Open threads from SIG-4
- The 0 mm hard limit for bucket 3 is brittle to sub-millimetre voids; the connector halo fixed the J3 case. Watch
  for the next kind (a neighbouring net's via antipad) and prefer measuring the void's cause over an allowance.
- Weights: sonnet's winner flips at VIN x2 or vias x0.5 (a 0.1 cost tie). Alex may want VIN weighted higher.
- `rescore` rows carry chained tags (`+rescore+rescore2`); `rank` reads the last row per run, so it is cosmetic.

## Practical notes
- Scratch: `/tmp/alexpcb-plan/<board>/` (bench), `/tmp/alexpcb-sig/` (this session: search/, search-rv/, plink/,
  plink-prep/, rv/). Router under `/tmp/pcb-ref/` (README recipe); `uv` for `pcb irdrop`.
- verify: `bash tools/verify_all.sh 28 29` (~3 min) covers the judges, signals, variants, rank, return vias;
  `27 28 29` adds route auto (~5 min more). Replay bench unchanged (24 labels, 0 false fails).
- Background commands over 10 min get moved to the background; foreground `sleep` is blocked.
