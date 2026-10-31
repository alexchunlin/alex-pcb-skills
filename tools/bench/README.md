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

## Tier 3, cost telemetry

`~/code-stuff/alex-3d-skills/tools/transcript/cc_transcript.py` runs unchanged on this repo's agent transcripts
(P0-T10); the rung-1 numbers in FINDINGS came from it.
