# Handoff: alex-pcb-skills, end of session 4 (2026-11-03, branch `dev`, worktree `phase6-routing`)

Read in this order: `docs/STATUS.md` (bottom), `docs/FINDINGS.md` "Routing session 4" (ROUTE-T1..T4, REFPLANE-1, IRDROP-1,
FEED-1, WAVES-1, STARVE-1, FEED-2, PLAN-1), `tools/bench/plan_bench.py` and `tools/bench/plan_kpy.py` docstrings,
`skills/kicad-design/scripts/pcbroute.py` (`c_waves`, `default_plan`). Commits this session: b76ac15, ec64806, f36e3c4
on `dev` (local, not pushed; pushing is Alex's call).

## How Alex wants to work (standing, from this session)
- State the hypothesis and its null before building; measure prior art first (his global CLAUDE.md); report honestly.
- Iteration speed matters: judge tool changes on deterministic benches and stage-sliced runs, full designer runs only as
  milestones. The frontier is tokens, time, quality, determinism.
- Stackup policy: In1 and In2 solid GND, 3V3/5V routed, high-current rails as pours or thick tracks, signals over
  unbroken ground. He wants side-by-side trace images to judge progress (renderer: `/tmp/alexpcb-viz/extract.py` +
  `build.py`, alex-style dark; inline pages via the orca-chat-visuals skill, files under 512 KB).
- Commit on `dev` when he says so; never rm a variable+glob path; no posts to repos he does not own.

## Where things stand
- `pcb route auto` outer-only and reproducible; `pcb route waves` (feeds and thermal vias as wave 0, locked KRT waves,
  per-wave keepouts and `timeout_s`, verdict against the input); judges `pcb irdrop`, `refplane`, `feed_room`.
- PLAN-1 result: a 6-plan deterministic search matched one Sonnet agent per board on 2 of 3 boards at zero tokens.
  The ranking rule was the open question. Alex's answer (below) replaces the single priority order.

## Alex's decision this session: rank signals by class, not "signal" as one thing
Four aggressor buckets by knee frequency, f_knee ~= 0.5 / t_rise (the DRIVER's edge, not the clock rate):
1. < 1 MHz: best effort over ground; detours fine.
2. 1 to 50 MHz: over ground, short gap crossings penalised, spacing from aggressors.
3. 50 to 500 MHz: hard: 0 mm off ground, no plane-split or edge crossings, a GND via beside every layer change, out
   of hot zones.
4. > 500 MHz: hard plus impedance, pairs, length match (none on rung 2 yet).
Second axis: victims (analog, high impedance: IPROPI, ISENSE) want distance from aggressors more than ground.
Each bucket's rules become hard limits (3, 4) or weighted costs (1, 2); VIN loss is one more cost; the search picks the
plan that meets every hard limit at the lowest total cost. "Foreign signal in the switch loop" is to be replaced by
same-layer exposure to the SW copper, weighted by the victim flag (B.Cu under the SW node is shielded by two planes).

## The work, in order (Alex approved all three)
1. **Classify.** An agent pass on the rung-2 schematic (the three boards share topology and references) records per
   net: driver pin, rise time with its source (datasheet line, or an explicit assumption such as "MCU GPIO behind the
   header, assume 3 ns"), anything on the board that slows the edge (series R, RC, pull-up RC), and a victim flag. Code
   computes knee and bucket. Store it where the tools can read it: net classes named by bucket in the Zener code are the
   smallest change (KRT and pcbcheck already read classes); a `signals` block in checks.json is the fallback. SHOW ALEX
   THE TABLE before anything uses it. Expect surprises (raw-GPIO PWM lands in bucket 3).
2. **Judges per bucket.** Split `refplane` by bucket (hard limits for 3/4, weighted mm for 1/2); add a return-via check
   (a bucket-3 net changing layer moves its return from In1 to In2: GND via within a set distance of the signal via);
   replace `foreign_mm` with same-layer exposure to SW copper weighted by victim flag. Prior art first: check KRT
   (`--gnd-via-net`, `add_gnd_vias.py`, "GND return via placement" in its README) and kct (`analyze signal-integrity`,
   `current-sense`) before writing code; measure them on the PLAN-1 boards.
3. **Re-rank.** Score with the new limits and costs: the existing PLAN-1 rows in `tools/bench/results/plan.jsonl` (the
   routed boards are under `/tmp/alexpcb-plan/<board>/<arm>-*`; re-run `plan_bench.py score` if /tmp was cleared) and
   the 6-plan search. Report whether the winning plan per board changes. Then build `pcb route waves --search`.

Hypothesis for step 3, stated with Alex before running: class-aware ranking picks plans that keep bucket-3 nets fully
referenced at a VIN cost within the limit, and changes the winner on at least one board. Null: same winners as the
priority order, or no plan meets the bucket-3 hard limits on some board (then the placement, not the plan, is the gap).

## Practical notes
- Router installs under `/tmp/pcb-ref/` (README recipe in `tools/bench/README.md`); `uv` needed for `pcb irdrop`.
- Background commands over 10 min get moved to the background; foreground `sleep` is blocked.
- verify: `bash tools/verify_all.sh 27 28` (KRT sections, ~5 min); `--changed` is ~30 min. Section 26's Fable
  shorting_items count drifts (19-21) under CPU load (P6-T5); re-run it alone when idle.
- pcblib traps: never `board.Remove()` (use Delete); BOX2I from GetBoundingBox is broken in SWIG here; save after
  adding copper unfills first (ROUTE-T4).
