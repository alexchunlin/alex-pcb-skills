# Spike 6 liaison: regeneration output overlap

2026-11-05, task `task_8a9f3f424a6e`, dispatch `ctx_2ff17effaf49`.
Initial implementation base: `86f902c56` (spike 7 protocol branch, before spike 6 merge).
Opus confirmed ownership transfer and unchanged `cmd_regen_check` on spike 6 via
Orca message `msg_f4da0242e2ea`.

## Reproduction and fix

`python3 -I tools/verify.d/regen_paths.py "$PWD"` imports the real command and
stops at its first measurement using a mock; no CAD or regeneration subprocess
runs. The command performs real scratch directory operations in disposable
projects, each containing a source preservation sentinel.

Before: equal and ancestor outputs delete the sentinel; nested and symlink-nested
outputs reach measurement rather than rejecting overlap; symlink-project output
raises an incidental OS error rather than the intended diagnostic. Five of seven
controls fail. The reported recursive copy on a real board was independently
reported by the VL53L8CX spike 6 run; this test deliberately stops before recursive
copy and does not claim to rerun that CAD workflow.

After: realpath containment in either direction is rejected before deletion,
creation or measurement. All seven controls pass, including nonexisting nested
paths, symlink parents, similarly prefixed safe siblings and default output.
`before.txt` and `after.txt` preserve the raw outputs. The comparison changes no
board checks, labels or thresholds.

Filesystem-only repo verification:
`sh tools/verify_all.sh regen_paths.sh verify_select.sh`: 19 passed, 0 failed,
`/tmp/alexpcb-verify/run-13065` (metadata retained here).
Full changed-path verification and replay remain pending the final spike 6 push
and an explicit CAD lease. This patch is not yet cleared for integration.

## Initial remote evidence and baseline hold

At 04:31 UTC `git ls-remote origin` returned main
`df0f2d86044ff69b92767827c51858368fd542cf` and dev
`2bb566ae1c37f0cfa3e262353e43ab99614d12bc`.
These are stale for the requested spike 6 baseline. Live Opus mailbox is
`orca_session_id:claude_d28de4ef_3d84_421f_8677_a9a5ac2273ea` in the primary
workspace; phase6-routing contains only completed structured chats.
Do not freeze until Opus finishes regression and both pushes are verified.

## Review extension: generated-path deletion escape

Review message `msg_4c9dc05a4d04` identified a separate escape after fresh copy:
absolute generated paths, parent traversal and a symlink into the original
project can delete original source. Added whole-list validation before deleting
any generated target; reject absolute paths, parent traversal, fresh root itself,
and realpaths outside fresh. Four unsafe controls fail before and pass after;
three positive controls allow fresh files, directories and missing artifacts.
Every unsafe case also puts a valid artifact first and verifies it survives,
proving that validation precedes the entire deletion pass. Original-source
sentinels survive every fixed case. CAD and the regen subprocess remain mocked.
Raw evidence is `generated-before.txt` and `generated-after.txt`.
Filesystem-only verification again passes 19/19 at
`/tmp/alexpcb-verify/run-20872`; 14 direct path controls now pass.
