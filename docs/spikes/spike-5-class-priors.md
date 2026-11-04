# Spike 5: placement priors pooled by component class

Issue: [#5](https://github.com/alexchunlin/alex-pcb-skills/issues/5). Branch `spike/5-class-priors` from `main` at 820621d.
This file was first committed with the Method section alone, before any scored route, so the design below is fixed
ahead of the results. Changes made after seeing results are listed under "Design changes after the Method commit".

## Method (fixed before the first scored route)

### Boards and moved satellites

- **r1**: `examples/rung1-zener-a2-sonnet`, `pcb route strip` (tracks and vias gone, zones kept). Moved: C1 and C2 (100 nF,
  `decoupling` rows on U1 pads 8 and 5), C3 (1 uF, pad 8). Everything else stays where the designer put it.
- **r2**: `examples/rung2-zener-a2-opus` (attempt 2), stripped the same way. Moved: C10 (VM 100 nF, bypass), C11 (VM 10 uF, bulk), R10
  (IPROPI to GND, current-mirror role). C12 (VCP to VM) and C13 (CPH-CPL flying cap) are charge-pump roles: each joins the
  moved set only if the pooled measurement, with DRV8874 held out, holds at least 5 rows from at least 3 repos in its role.
  That count is taken from the measured boards before the first r2 route and the set is then the same in every r2 arm. A
  satellite left out keeps the designer's pose in every arm.

### Arms and seeds

Seeds 0 to 49 per arm. Same arm list per board, every arm moves the same satellites and nothing else.

| Arm | r1 | r2 | Seeding |
|---|---|---|---|
| `uniform` | yes (comparator) | yes | spike 2's: x, y uniform over the outline box inset 1 mm, rotation from 0/90/180/270 |
| `part` | yes (comparator) | no | spike 2's LSM6DS3 prior, its own `priors-LSM6DS3.json` |
| `krt` | yes | yes | KRT `place_simple`, default weights (`--decap-weight 2`, no limit), one `--seed` per seed |
| `class_part` (r1) / `class` (r2) | yes | yes | class prior, test part held out |
| `class_pkg` | yes | no | class prior, all of LGA-14 held out |
| `krt_tpl` | yes | yes | KRT with one `templates[]` row per seed, the row drawn from `class_part` (r1) or `class` (r2), `--template-weight 100` |
| `perturb` | no | yes | the designer's satellite x, y plus N(0, 1.0 mm) per axis, rotation kept |

**r1 comparators.** `uniform` and `part` reuse spike 2's 17/50 and 33/50 only if 5 seeds per arm (0, 11, 22, 33, 44) of
`tools/spikes/spike2/placement-results.jsonl`, reseeded by the same code on today's `main`, give the same `moved` poses, the
same clean flag, and the same vias and length. Any mismatch reruns both arms for all 50 seeds.

**Perturbation sigma: 1.0 mm**, stated here before routing. Spike 1 saw no sigma trend on this board at 1 to 4 mm (7/38,
9/37, 12/37, 9/37), and 1 mm stays inside a tight satellite's working distance.

### Locking the KRT arms

KRT's own lock: `place_pose.py lock` on every footprint except the moved satellites, then `check_floorplan --emit-intent
--no-declare-decaps`, and one group {IC, moved satellites} anchored on the IC (`check_groups` passes on both boards).
`--decaps-from` is not used: it derives limits from the archived board, which is the designer's answer. Dry runs without
routing (12 seeds each, median pin distance per satellite) showed weight 10 and a 2 mm limit graded at error move the
median by at most 0.6 mm and add floorplan errors at weight 10 on r1 and with the limit on r2, so the arm runs at KRT's
defaults. 8 dry seeds on each board left no part illegal with the board locked.

### Illegal seeds

Every arm passes one gate, spike 2's: the moved part's courtyard box must not overlap another footprint's box (or a moved
part's) and must stay in the outline box.
- Sampled arms redraw a part up to 500 times; a part with no legal draw rejects the seed.
- KRT arms get one `place_simple` run per seed (its internal restarts included). The seed is rejected if `place_simple`
  exits non-zero, names a part illegal, or the result fails the gate.
- There are no replacement seeds. **A rejected seed counts as not clean in the /50 denominator**. Rejected seeds per arm
  are reported, and so is clean among the seeds emitted.

### Clean, and what is measured per seed

**Clean** is `pcb route auto`'s own verdict in `route.json`: 0 airwires, no new plain DRC error against the seeded input, packed
errors no higher, board setup unchanged. Per seed also: vias, signal vias (`pcb route measure`: vias on nets with no filled inner
zone), length, and `pcb check --only feeds,decoupling` on the routed board. KRT runs under `PYTHONHASHSEED=0`, at most 3
processes at once. The designer's own placement is routed once on each board as a reference row.

### Class prior

- **Class.** JLC category and `describe`, then KRT `_converters` on KiCad boards, then a reading pass on the misses. Pin-name
  rules are not used.
- **Instances.** KiCad corpus siblings from a new `scan.py --classes` pass, vendor Eagle (Adafruit, SparkFun), third-party
  Eagle. Modules are dropped by pad extent (a GY-521 is a header, not a package). Altium is out of role-keyed rows.
- **Package key.** Pad extent, pitch class and thermal pad by size, never the library name or the pad count.
- **Role.** From the pad's `pinfunction` and `pintype` on KiCad boards, from the `.sch` pin map on Eagle. Roles: supply bypass
  (under 1 uF to ground on a supply pin), bulk (1 uF and up), charge pump, shunt, current mirror, limit setting, pull-up,
  feedback.
- **Frame.** Rotation and mirror undone by `frame()`. Canonical orientation: long pad axis on x, pad 1 on the x < 0 side; for a
  square pad extent, pad 1 in the x < 0, y < 0 quadrant. Pad 1 is checked on LGA-14 and HTSSOP-16 from at least two sources
  before anything is pooled.
- **Pose.** The satellite's centre in the frame of the IC pin it serves (u out of the package at that pin, v a quarter turn from
  u) and the direction of its pin-side pad, so a sample carries across pinouts and package sizes. A cap sits next to a
  pin, not next to a package centre.
- **Pooling.** Three levels, part, package, class. Part weight n / (n + 30), or 1 at n >= 30. Of the rest, package weight
  n / (n + 30) the same way, and class takes what is left. A held-out level has n = 0. Within a level a draw takes a repo
  uniformly, then a row in that repo. Quantiles and medians shrink by the same weights (`tools/corpus/pooling.py`, tested).
- **Fallback.** A role with fewer than 5 rows in at least 3 repos at every level falls back to its family (`sense` for shunt,
  current mirror and limit setting), and the fallback is reported.
- Raw poses stay in `/tmp`. Published rows need n >= 5 and at least 3 repos.

### Order of work

The KRT arms on r1 run before any pooling code exists (issue step 1). If `krt` reaches 33/50 on r1 the class prior has to
beat it and the report says so plainly.

### Pass rules

Two-sided Fisher exact on clean counts /50; rank-sum (Wilcoxon, unpaired: seeds do not pair across arms) on signal vias of clean
routes; a comparison "beats" at p < 0.05 with the count in that direction.

**H1, r1.** For each of `class_part` and `class_pkg`, separately: clean >= 28/50, beats `uniform`, and does not lose to `krt`.
"Does not lose" means `krt` is not ahead by Fisher p < 0.05; if `krt` reaches 33/50 or more, the arm must beat `krt` outright.
Passing `class_part` and failing `class_pkg` reads as "the prior transfers within a package".

**H1, r2.** `class` beats `uniform` on clean, and among clean routes it has fewer failing `feeds` and `decoupling` rows than
`uniform` by rank-sum p < 0.05 on the sum of the two. It must not lose to `krt` or to `krt_tpl` as on r1. `perturb` is
reported beside it: a prior that only beats "anywhere on the board" says little.

**Waves judges, r2.** Each arm's best 5 clean placements (fewest signal vias, then shortest) and the designer's start go through
`pcb route waves` with the rules plan on Alex's stackup, and `plan_bench.judges`: refplane, return_via, exposure, irdrop,
`feeds`, `decoupling`. A class prior that wins on clean and loses on these is reported as a mixed result.

**Comparisons.** r1: `class_part` and `class_pkg` each against `uniform`, `part`, `krt`, `krt_tpl` (8), `krt` against `uniform` and
`part` (2), `krt_tpl` against `krt` (1). r2: `class` against `uniform`, `krt`, `krt_tpl`, `perturb` (4), `krt` against `uniform` (1),
`krt_tpl` against `krt` (1), `perturb` against `uniform` (1). 18 Fisher tests, and the same pairs on rank-sum where both arms
have at least 5 clean routes. Raw p values are reported with the Bonferroni line at 0.05 / 18 = 0.0028.

**H2.** Per (source org, package, role), repo as the unit of n: one repo median per repo, then the median and IQR of those.
Two rows pool when each median sits inside the other's IQR. Reported: whether designer or package moves the median more.

**H3.** Dropped under its own null. Counts only.
