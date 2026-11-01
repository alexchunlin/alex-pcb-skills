# Bench: do tool changes catch more of what reviewers and the fab found, without adding noise?

Tier 1 of GAMEPLAN section 4, ported from `alex-3d-skills/tools/bench`. No LLM calls. Plain python3, standard library.

## Replay bench (`replay.py`)

Replays the archived boards through the tools of a chosen commit and scores the reports against the labels.

```sh
python3 -I tools/bench/replay.py                        # HEAD's tools, all boards (about 2 min)
python3 -I tools/bench/replay.py --commit <ref>         # another commit's skills/ (git archive into the scratch dir)
python3 -I tools/bench/replay.py --attempts plink-v1    # a subset
python3 -I tools/bench/replay.py --from-verify /tmp/alexpcb-verify/run-<pid>   # score a verify_all run, including regen-check
python3 -I tools/bench/replay.py --from-run /tmp/alexpcb-bench/run-<pid>       # rescore after a label edit
python3 -I tools/bench/replay.py table                  # one line per (commit, attempt) in results/replay.jsonl
python3 -I tools/bench/replay.py compare BASE NEW       # the gate: recall not down, false fails and noise not up
python3 -I tools/bench/replay.py lint                   # labels vs corpus
```

- **Corpus** (`corpus.json`): four boards. `rung1-zener-a1` and `rung1-skidl-a1` are the reviewed rung-1 attempts
  (`examples/*/board/`, the reviewed files as handed in). `plink-v1` is MotorGo Plink at `fb32540`, the board fabbed
  in October 2024 with the IMU SDA/SCL swap; `plink-fixed` is `0250d75` after the November rework
  (`examples/plink/*.tar.gz`, the full KiCad projects). Per board: `drc` (raw pack, so the masking is visible),
  `check` with the example `checks.json`, `fab`, and `regen` (verify-only: `pcb regen-check` takes a minute per
  board and needs the Diode toolchain, so the bench reads it from a verify_all run with `--from-verify`).
- **Labels** (`labels.json`): one entry per reviewer finding (R1-S1-F*, R1-Z1-F*) or fab-history bug (P0-T9,
  P1-T18), with severity, `tool_catchable`, and locators: `{report, pattern}` regexes over the report lines
  `replay.py` makes (`drc fail plain hole_clearance 8`, `check fail decoupling:U1.8:C3: ...`, `regen fail verdict
  FAILS`, `fab warn cpl_offset J1 0.45`). `partial: true` credits a partial catch. `process: true` labels are out
  of every denominator. `known_true_positives` excuse fails the tools are right about; `negatives` make a fail on
  a fixed board a false fail (plink-fixed must pass `pinmaps`).
- **Scores** per attempt, scopes `designer` (designer-kind runs) and `rows` (reviewer-kind runs too):
  `recall_fail`, `recall_fw`, weighted by severity (`*_w`), `caught_partial`, `missed`, `label_errors` (a crashed
  run is an error, never a miss), `false_fails`, `noise_warns`. `ALL` sums them.
- **Gate for a PR that touches a check**: `replay.py compare <base> <new>` prints nothing worse; a label edit in the
  same PR says why in `source`.

## Where the numbers are today

The HEAD run is in `results/replay.jsonl` (`replay.py table`). Not catchable yet, so counted as misses:
the Plink back-power Schottky (needs a topology row) and silk readability (needs a readability row).

## Route bench (`route_bench.py`, phase 6)

The autorouters against the designers' own copper on the archived rung-2 boards. Each board is copied, its tracks and vias
are deleted with placement kept (`pcb route strip`; the `tracks` variant keeps the zones, `all` deletes them too), each
router runs on the stripped board, the zones are refilled and `pcb route measure --drc` scores the result: airwires still
open (P6-T1), plain and packed DRC errors, vias, length, the DRV8874's nets on their own, router wall time, and whether
the board-setup minimums changed (a router that loosened the rules to read 0, R1-A2-T5).

```sh
python3 -I tools/bench/route_bench.py                                  # all boards, variants, routers, configs (about 25 min)
python3 -I tools/bench/route_bench.py --boards opus --variants tracks --routers krt,freerouting --configs default
python3 -I tools/bench/route_bench.py table                             # one line per row in results/route.jsonl
```

Routers: `designer` (the archived copper as handed in), `freerouting` (the 2.5.0 jar on a JDK, `FREEROUTING_JAR`,
`JAVA`; DSN out of pcbnew, SES back in), `krt` (KiCadRoutingTools, `KRT_DIR`, `KRT_PY`), `kct`. `CONFIGS` in the script
lists the per-router settings and why. The native freerouting CLI is not used (P6-T2). Evidence: FINDINGS "Phase 6".

Installing the routers (both under `/tmp/pcb-ref`, re-create if gone; `pcb route auto` and verify_all 27 read the same paths):

```sh
brew install openjdk                                   # /opt/homebrew/opt/openjdk/bin/java (JAVA)
mkdir -p /tmp/pcb-ref/freerouting && curl -sL -o /tmp/pcb-ref/freerouting/freerouting-2.5.0.jar \
  https://github.com/freerouting/freerouting/releases/download/v2.5.0/freerouting-2.5.0.jar
curl -sL -o /tmp/krt.zip https://github.com/drandyhaas/KiCadRoutingTools/releases/download/v0.23.7/KiCadRoutingTools-0.23.7.zip
mkdir -p /tmp/krt && (cd /tmp/krt && unzip -q /tmp/krt.zip) && mv /tmp/krt/plugins /tmp/pcb-ref/KiCadRoutingTools
cd /tmp/pcb-ref/KiCadRoutingTools && cp rust_router/grid_router-macos-arm64.so rust_router/grid_router.so \
  && uv venv .venv --python 3.12 && uv pip install --python .venv/bin/python numpy scipy shapely Pillow
```

kct (`uv tool install kicad-tools`) is on the machine already; it is off by default in the bench (P6-T3).

## Tier 3, cost telemetry

`~/code-stuff/alex-3d-skills/tools/transcript/cc_transcript.py` runs unchanged on this repo's agent transcripts
(P0-T10); the rung-1 numbers in FINDINGS came from it.
