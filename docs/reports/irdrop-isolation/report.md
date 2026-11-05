# IR-drop scratch isolation and relative output paths

Branch: `alexchunlin/overnight-irdrop-isolation`. Initial base: `e0bd2e0`.
Scope: `pcbir.py`, the default directory selection in `pcbcheck.check_irdrop`, and filesystem-only regression tests. No `pcbcli.py`, extraction physics, solver arithmetic, or thresholds changed.

## Reproduction and controls

The spike6 report (`docs/spikes/spike-6-block-placement.md`, ranked tool list item 5) records shared IR-drop scratch crossing boards twice. The old CLI default joined `/tmp/pcb-irdrop` with board stem and net. Two controlled CLI invocations for `one/board.kicad_pcb` and `two/board.kicad_pcb` therefore wrote identical artifact paths; the second replaced the first. The committed `before.txt` records that failing equality assertion against the original implementation. It also records relative `--out 'relative output'` resolving the solver input as `relative output/relative output/irdrop-in.json` because `subprocess.run` already used `cwd=out`.

Before: five filesystem tests, two failures and one error; absolute output reuse and recovery controls passed. After: seven tests pass (`after.txt`), including both repros plus repeated identical-board defaults, slash-containing net names, overlapping default runs synchronized after input writes, same explicit directory writer rejection, sequential explicit reuse, stale-success removal after solver failure, recovery after failure, and the actual `check_irdrop` function with native dependencies stubbed. Test stubs preserve a numeric result sentinel (4.2 mW) and tag input/SVG/report with board identity; they do not simulate physics. Native numerical verification remains a separate gate.

## Behavior

Default output uses `tempfile.mkdtemp`, respecting the host temporary directory and retaining artifacts. A sanitized, bounded board/net label makes paths recognizable without letting net names introduce directories. Each `pcb check` invocation also gets a new base, retaining its existing per-net/per-load subdirectories.

Explicit output still writes `irdrop-in.json`, `irdrop.svg`, and `irdrop.json` directly to the requested directory. Relative output is made absolute before starting the child. A nonblocking POSIX advisory lock covers extraction, solving and report publication; overlapping cooperating writers fail with the directory named, and closing the descriptor releases ownership even on exceptions. The empty `.irdrop.lock` file intentionally remains so writers always lock the same inode. Sequential reuse is supported. The previous report and SVG are removed under the lock before a rerun so a failed run cannot advertise old success. Other files are untouched. External programs that ignore the advisory lock are outside this guarantee.

Reports include absolute board, output, input, report and SVG paths, plus net/source; CLI reports retain capacitor exclusions. `pcb check` now also retains a JSON report for each solve. Default artifacts persist for inspection and require ordinary temporary-directory cleanup. The lock uses `fcntl`, consistent with the repository's macOS/Linux execution environment.

## Replay

Filesystem tests (no CAD/solver lease needed):

```sh
python3 -I tools/verify.d/irdrop_paths.py
python3 -I tools/verify.d/verify_select_cases.py "$PWD"
git diff --check
```

The new `tools/verify.d/irdrop_paths.sh` integrates the tests into selective verification. Selector cases pass. The selector requires sections 13, 14, 15, 16, 21, 24, 25, 26, 28, 30, 32 and bench/spike6/path/selector units for the implementation changes.

## Pending integration gates

Await verified spike6 push, rebase onto that commit, then replay tests. Native selected verification and numerical comparison must wait for the coordinator's exclusive CAD lease (after liaison regen and block-gate validation). No real CAD or solver was run during the filesystem reproduction.
