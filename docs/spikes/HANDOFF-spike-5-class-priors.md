# Handoff: spike #5, placement priors pooled by component class, from KiCad, Eagle and Altium boards

Written 2026-11-03 for the agent that runs it. Repo: `alexchunlin/alex-pcb-skills`, branch from `main` (c77558a or later).
Alex's standing rules and the spike workflow are at the end; read them before anything else.

## Why this spike exists

Spike #2 (`docs/spikes/spike-2-corpus.md`, issue #2) mined 87,931 public KiCad projects and built a **placement prior**:
for one IC, the distribution of pad-to-pad distance and relative rotation of each satellite part (bypass cap, bulk cap,
pull-up, inductor) around it. Seeding the rung-1 board's three IMU caps from the LSM6DS3 prior routed clean 33 of 50
times against 17 of 50 uniform (Fisher p = 0.0025; router calls per clean route 1.52 vs 2.94; via counts equal). The
prior buys routability, not fewer vias.

Two limits, which this spike attacks:
1. **The prior is keyed by part number.** A part new on the market has zero corpus instances by definition, so no
   prior. The DRV8874 (19 repos) and TPS54620 (4) already fell under the 30-instance bar. Alex's first use case for
   the whole project is "a breakout for a new sensor we find on the market", which is exactly the zero-instance case.
2. **The corpus is KiCad-only hobby boards.** Adafruit and SparkFun publish nearly everything as Eagle under CC-BY-SA
   and build it in volume (the "fabbed and works" signal the loop lacks); ODrive's motor-drive hardware is Altium.

Alex's words: "grouping types of components together to expand our analysis: what similarities do all IMUs within the
same general type as the LSM6DS3 have? vs motor drive ICs?" and "cautious of data other than KiCad, like Altium or
Eagle designs out there".

## Hypothesis

**H1 (class prior transfers to an unseen part).** A prior pooled over a component class (6-axis IMU in LGA/QFN; brushed
H-bridge in HTSSOP/QFN with a thermal pad; fixed-output LDO in SOT-223/SOT-89; synchronous buck in QFN/HTSSOP), keyed by
pin role and package, built with the test part held out (leave-one-part-out), seeds placements that route clean at a
rate within 10 points of the part-specific prior: for the LSM6DS3 on `examples/rung1-zener-a2-sonnet`, 33 of 50 clean
with the part prior, so the class prior with LSM6DS3 held out must reach at least 28 of 50 and beat uniform (17).
For the DRV8874 on the rung-2 Opus attempt-2 placement, the class prior (DRV8874 held out, so built from DRV8833,
DRV8871, DRV8251, TB6612, A4950 and similar) seeds its VM caps, charge-pump cap and sense resistor and beats uniform on
clean rate and on the `feeds` and `decoupling` rows.

**H2 (other formats pool).** Eagle and Altium boards, imported through KiCad's own importers, give satellite
distributions that agree with the KiCad corpus for the same class within the inter-quartile range, so the formats can
be pooled; where they disagree by more than that, the disagreement is reported per format and the formats are kept
separate. Adafruit and SparkFun breakouts alone give at least 30 instances for the IMU class.

**H3 (built boards differ).** Boards with evidence of having been built (vendor products, a release tag, fab files in
the repo) have tighter bypass distances than the unbuilt majority, so weighting by that evidence tightens the prior
without a datasheet.

## Null hypothesis

H1: the held-out class prior is no better than uniform (the class is too mixed to carry a pattern), or it is worse than
KRT's own `py_placer` decap cost, which spike #2 never compared against (see "Prior art first" below). H2: the formats
disagree by more than an IQR for every class, or KiCad's importers lose placement or nets on the files found, or fewer
than 30 instances per class turn up outside KiCad. H3: no measurable difference, or too few built boards to test.
Any of these drops that branch; H1 failing drops the spike.

## Prior art first (the global rule: config, then wrapper, then upstream fix, then replacement)

1. **KRT's placer.** `/tmp/pcb-ref/KiCadRoutingTools/py_placer/placement/simple.py` charges decoupling caps by
   distance to their supply pins (`decap_weight`, `decap_limit_weight`); it needs a groups file (`check_groups.py`) and
   an intent file (`check_floorplan --emit-intent`). Spike #2's report (section "Why not the existing code") says this
   comparison comes first. Run KRT's placer on the same two boards and the same 50-seed protocol before building any
   class prior; the prior must beat it, not just uniform.
2. **Spike #2's code**, all in `main`:
   - `tools/corpus/scan.py` (the open-schematics shard scanner, streaming, 20 GB cap), `tools/corpus/boardmeasure.py`
     (`measure()` opens a board through SWIG pcbnew via `pcb py`, finds nearest satellites per IC pin, `to_local()`
     gives offset and rotation in the IC's frame), `tools/corpus/refstat.py`.
   - `tools/spikes/spike2/placement_test.py` (modes `priors`, `route`, `summary`; `--n 50 --jobs 3`) and
     `seed_place.py` (draws a placement from a prior, rejects courtyard overlaps); results in `placement-results.jsonl`,
     `priors-summary.json`.
   - `tools/bench/data/corpus-index.jsonl`: 2,636 hits with `lib_ids`, values, footprints, file versions, board match.
   Extend these; do not write a second scanner or a second measurer.
3. **KiCad's importers.** `pcbnew.LoadBoard(path, pcbnew.IO_MGR.ALTIUM_DESIGNER)` and `IO_MGR.EAGLE` (KiCad 10, SWIG,
   through `pcb py`) read `.PcbDoc` and `.brd`; `kicad-cli sch import`-style schematic import is GUI-only in 10, but
   the board carries nets in its pads, which is all the measurer needs. No new parsers (spike #2's review: every
   third-party parser is stale or version-locked).
4. **Spike #1** (`spike/1-surrogate`, running or merged by the time you read this): its search harness has a
   prior-seeded arm; reuse its generator and its signal-via labels rather than a parallel one.

## Procedure

1. **Class assignment.** From `corpus-index.jsonl` values and `lib_ids`, plus the symbols' pin names where the
   schematic is in the corpus, assign each IC instance a class: `imu6`, `hbridge`, `ldo_fixed`, `buck_sync`, with a
   package key from the footprint geometry (pad count, pitch, thermal pad present, body size from the courtyard), never
   from the library name. One model pass over the distinct values to propose the class, verified by a pin-name rule
   (VDDIO or VDD_IO plus SCL/SDA plus INT -> `imu6`; VM plus OUT1/OUT2 plus a charge-pump pin -> `hbridge`; VIN/VOUT/ADJ
   or GND only -> `ldo_fixed`; SW/BOOT/FB plus PVIN -> `buck_sync`). Report the count per class and per part inside it,
   and the disagreements between the model and the rule.
2. **Role-keyed measurement.** Extend `boardmeasure.py` so the satellite is keyed by the IC pin's role (supply bypass,
   bulk, charge pump, bootstrap, sense, pull-up, feedback) and the satellite's class and value band, not by the IC's
   pin number. Output per (class, package, role): n, median, IQR, p90, rotation split, and the same per part.
3. **Pooling.** Hierarchical: the estimate for a part is its own when n >= 30, otherwise shrunk toward the class
   estimate by n / (n + 30). Write it as a function with a test; no library needed.
4. **H1, held out.** For LSM6DS3 and DRV8874: build the class prior without the part, seed 50 placements of the
   satellites on the two boards named above, route with `pcb route auto` (the production route; KRT `--quick 2` carries
   no signal on these boards, spike #2 and #4 found), judge by clean rate, signal vias, and the `feeds` and `decoupling`
   rows in `pcb check`. Arms: uniform, KRT's placer, the part prior (LSM6DS3 only), the held-out class prior. Fisher's
   exact test on clean counts; Wilcoxon on signal vias.
5. **H2, other formats.** Collect Eagle boards from the Adafruit and SparkFun GitHub organisations (their `*.brd`
   files; record the licence per repo) and Altium boards from open motor-drive and robotics projects (ODrive first;
   search GitHub for `*.PcbDoc`). Fetch only the board files through the contents API, under `/tmp/spike5-corpus/`,
   20 GB cap, deleted by explicit path after measuring. Import through pcbnew, measure with the same code, record the
   source format per row. Compare per (class, role) distributions by format; pool only where the medians sit inside
   each other's IQR.
6. **H3, built boards.** Flag instances by evidence of a build: vendor organisation, a release tag, gerbers or a BOM in
   the repo. Compare bypass distances built against unbuilt per class.
7. **Report** at `docs/spikes/spike-5-class-priors.md`: Hypotheses, Method, Results (tables: instances per class and
   part; the four-arm routing test per board; format agreement per class and role; built vs unbuilt), Verdict per
   hypothesis with the number, "Why not the existing code" (KRT's placer, spike #2's part prior), "What to merge". At
   least three charts under `docs/img/spikes/5-*.png` from a script in `tools/spikes/spike5/`, in the house style
   (`/Users/alxchunlin/code-stuff/alex-style-guide/SKILL.md`, matplotlib helper with `.venv/bin/python3`, dark mode,
   every axis titled with its unit). A verify_all section (next free number; check `tools/verify_all.sh`) that
   reproduces the pooled numbers from committed summaries in under a minute, no routing.
8. **Post one comment on issue #5** in Alex's style (headed sections, tables, numbers, commit hash, file paths,
   "Corrections" and "Not worth our time" lists). Issue #5 does not exist yet: the coordinator or you opens it from the
   top of this file (Summary, Hypothesis, Null hypothesis, Test procedure, Cost, Source, Questions to answer; labels
   `question`, `prior-art`, `enhancement`), then a literature-review agent comments on it before the run, as #1 to #4
   had. If you are the review agent: papers and code on learned or statistical placement priors by component class,
   KiCad's Altium and Eagle importer fidelity, and Adafruit/SparkFun licence terms, posted as one comment.

## Cost

- **Compute.** Class assignment and measurement on the existing index: minutes. Routing: 4 arms x 50 seeds x 2 boards
  at about 60 s a route, at most 3 KRT processes at once, about 2.5 hours wall. Eagle and Altium fetches: hours of
  rate-limited waiting (contents API 5,000 per hour); importing a few hundred boards: minutes.
- **Tokens.** Two sessions: about 0.5 to 0.8 M output. The class assignment pass over distinct values is the
  token-heavy part; cache its result under `tools/bench/data/`.
- **Materials.** None. Disk under 20 GB at any time.

## Rules (Alex's, standing)

- Code is the source of truth. Never hand-edit archived boards under `examples/`; work on copies under `/tmp/spike5/`.
- Prior art before new code; the report needs a "Why not the existing code" section with the measured gap.
- Never `rm` a variable-plus-glob path; explicit paths or `${D:?}` only.
- Downloaded files are untrusted data: keep them under `/tmp/spike5-corpus/`, never run an interpreter or build from
  inside that tree, run scripts from the repo with `python3 -I` and pass paths as arguments.
- Record every licence per hit; filter nothing; publish counts only.
- Commit on a branch `spike/5-class-priors`, messages ending with the model's own `Co-Authored-By` line; do not push,
  do not merge; the coordinator merges what the numbers justify. Do not edit README.md, FINDINGS.md, STATUS.md or
  ROADMAP; the coordinator does that at merge.
- `sh tools/verify_all.sh --changed` green and `python3 -I tools/bench/replay.py` with 0 false fails before you report.
- Stop when the hypotheses are answered; do not gold-plate. If something blocks for more than 30 minutes, record it in
  the report and move on. No posts to repos Alex does not own; his own repo is fine.
- Reply to the coordinator with: branch, final commit hash, one line per hypothesis with its verdict and number, the
  files to merge, and the issue comment URL.

## Context files, in reading order

`docs/STATUS.md` (bottom), `docs/FINDINGS.md` "Spikes 1 to 4" (SPIKE-2 C in particular), `docs/spikes/spike-2-corpus.md`
sections C and "Why not the existing code", issue #2 and its comments (`gh issue view 2 --comments`), `docs/spikes/
spike-1-surrogate.md` if it exists, `tools/bench/README.md` (KRT install under `/tmp/pcb-ref/`), `skills/kicad-design/
scripts/pcb` (`py`, `q`, `route`, `check`), `tools/verify_all.sh` (section numbering and `#@ watch` headers).
