# Spike 6: block-by-block placement, and three copper rules

Issue: to be linked. Branch `spike/6-block-placement` from `main` at df0f2d8. This file is committed before the first scored
designer run, so the design below is fixed ahead of the results. Later changes go under "Design changes after the Method commit".

## Why

Alex: a person lays out a circuit block by block from the schematic (power stage, then sensors, then the microcontroller)
and connects the blocks last; placing everything at once gives messier boards. He also asked for three rules after reading
board renders: no vias in pads, ground fill islands tied to ground with vias instead of ripped up, and copper further from
the board edge.

## Evidence before the method

Cohesion: mean share of a part's 3 nearest parts in its own schematic block, normalised so 0 = shuffled labels, 1 = all
(`pcb block report`; scratch form `/tmp/spike6/cohesion.py` on 216 unique corpus boards with at least 2 blocks, 20 parts).

| Boards | Cohesion |
|---|---|
| Rung-2 Sonnet a1, Opus a1, Opus a2 | 0.60, 0.67, 0.58 (15th to 26th percentile of the row below) |
| Corpus, 25-60 parts and 3-7 blocks (n = 34) | median 0.77, IQR 0.63-0.85 |
| Plink, Pace-core (human, built) | 0.82, 0.62 |

Cohesion alone is not quality: Pace-core is a real board at the LLM level. On the LLM boards the IC blocks are tight (0.74-0.96)
and the small ones loose. Opus a2's script has block headings but wrote the placement in one table, with power copper and zones,
in one step. Spike 1 arm (ii) gave KRT's placer the same modules as groups and routed 2 of 7 and 0 of 9 clean, so grouping alone
does not carry the claim: the test here is the designer's working order.

### Rule measurements (four archived placements, tracks stripped, `pcb route auto` before and after)

| Board | SMD pads with a router via | Vias | Length mm | Nearest via mm | Clean |
|---|---|---|---|---|---|
| opus2 before / after | 12 / 0 | 43 / 38 | 632 / 680 | 0.45 / 1.05 | yes / yes |
| opus before / after | 16 / 1 | 53 / 32 | 494 / 493 | 1.55 / 3.15 | yes / yes |
| sonnet before / after | 10 / 0 | 44 / 38 | 437 / 439 | 2.15 / 2.35 | yes / yes |
| r1 before / after | 10 / 0 | 19 / 20 | 184 / 208 | 0.65 / 2.85 | yes / no (INT2 open) |

r1's INT2 stays open with either flag alone, so the placement is marginal there and the rule costs one clean verdict in four.
The attempt-2 board on the two-plane stackup, routed outer-only (2 airwires left on this placement), had 10 ground fill pieces over
2 mm² with no ground copper (largest 97.5 mm² on B.Cu); `pcb route ground-islands` placed 11 vias in 7.6 s, `gnd_islands` went to 0
fails and 3 warns, DRC 0 errors.

## Method: the A/B (fixed before the first scored run)

**Question.** With the rules held constant, does placing block by block with gates beat placing the board in one pass?

**Input, both arms.** The rung-2 attempt-2 design at the netlist stage: `motor1.zen`, `modules/`, `parts/`, `calcs/`, datasheets,
`PINMAP.md`, the brief, and `checks.json` with the `feeds`, `decoupling`, `signals`, `currents` and `thermal_vias` rows, plus
`refplane`, `return_via`, `feed_room`, `via_in_pad`, `edge_margin` and `gnd_islands`. Nothing that reveals a placement: no
layout script, layout directory, design log, bring-up or review. Stackup: two solid GND planes (In1, In2), Alex's policy.

**Arms.** A: the skill as it stands, one designer places and routes. B: the same plus `reference/block-placement.md`, gates
enforced by `pcb block`. Three runs per arm (`s6-a-1..3`, `s6-b-1..3` in `~/code-stuff/alex-pcb-runs/`), Opus 5.5 at medium effort,
same prompt apart from the one PATH.md line. Stop at a routed, checked board; schematic changes are out of scope, no fab or
bring-up documents. Time cap 90 min.

**Judges, applied by the session on the handed-in board, not by the designer.**

| Rank | Judge | How |
|---|---|---|
| 1 | Finished: airwires 0 and DRC 0 errors, packed | `pcb route measure --drc`, `pcb drc --pack jlcpcb` |
| 2 | `pcb check` fails over all rows | same `checks.json`, tools at the method commit |
| 3 | VIN loss mW, `refplane` bucket-3 mm, `return_via` bad | `pcb irdrop`, `pcb check` |
| 4 | Reviewer layout score | `skills/pcb-design-review`, Opus (Fable out of credits), blind to the arm, on a copy with `blocks*` files removed |
| 5 | Cohesion, tokens, wall time | `pcb block report`, agent usage |

**Decision.** B becomes the skill's default if at n = 3 it finishes at least as often as A, its median of judge 2 is no worse,
and it improves the median of at least one of judges 3 and 4, at no more than 1.3× A's median tokens. Otherwise it stays
opt-in and the numbers go on the issue. Three runs detect a large effect only.

**Null.** Block order changes cohesion and nothing the judges care about, or costs more tokens than it returns.

## Method: breakouts (a readiness test, not an A/B)

Five boards on the skill, Opus 5.5 at medium, block order on, the three copper rules on: four parts not yet sold as an Adafruit or
SparkFun breakout, and one ESP32-S3 devkit on the bare chip (no module). Brief: `bench/design/rung3-breakouts/`. Reviewer as above.
Question: how close to orderable is a board with one designer pass? Reported per board: review scores, blockers, wall time, tokens,
and what a person would still have to do.

## Why not the existing code

- **Via in pad:** configuration, not code. KRT's `--same-net-pad-clearance` (default allows via in pad), now passed by every route
  call; `return_vias` also refuses SMD pads. New: the `via_in_pad` row, because no row looked. KRT's `fab_notes` only prints a note.
- **Edge:** configuration. KRT's `--board-edge-clearance` at 1.0. New: the `edge_margin` row, because DRC only checks the fab floor.
- **Islands:** KRT `route_planes --stitch-vias` lays a lattice and rejects off-cluster sites by design (it does not anchor islands),
  and KiCad's island removal only deletes. New: `ground_islands`, reusing `return_vias`' spot test.
- **Block gates:** KRT `check_groups` and the `groups.json` format are reused as they stand (`pcb block plan` calls it and prints its
  link matrix). KRT's placer places the groups by search; spike 1 measured that at 2 of 7 and 0 of 9 clean, and it has no notion of
  an order or a gate. New: `pcbblock.py`. KiCad 10's rule areas could assert the regions but not the order.

## Design changes after the Method commit

- **Tool bug fixed mid-run, both arms alike.** The island step of `pcb route auto` crashed with `UnboundLocalError` (`_sh`) on any board
  that reached 0 airwires without entering the stitch branch. Found by `verify_all` after the designers had started, fixed in the shared
  scripts, and all seven running designers were told. No judge or row changed.

## Results

Pending.
