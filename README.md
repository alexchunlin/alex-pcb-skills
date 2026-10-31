# alex-pcb-skills

Skills and tools for agent-driven KiCad 10 PCB design from code, modelled on `alex-3d-skills`. The evidence behind
every rule is in `docs/FINDINGS.md`; the plan in `docs/GAMEPLAN.md`; current state in `docs/STATUS.md`.

| Path | What |
|---|---|
| `skills/kicad-design/` | Designer skill: the `pcb` wrapper (`erc`, dual `drc`, `check`, `q`, `fab`, `regen-check`, `schfix`, `py`, Diode passthrough), `pcblib.board` over pcbnew, `pcbcheck` with `checks.json`, reference docs, project template |
| `skills/pcb-design-review/` | Reviewer skill: check-first protocol, rubric with anchors, evidence checklist |
| `examples/` | The two reviewed rung-1 attempts (configs, boards, the Zener source and its pcblib layout port) and MotorGo Plink before and after its rework |
| `tools/verify_all.sh` | Re-proves everything (about 10 minutes; `--changed [BASE]` runs only what a change affects, `--dry-run` prints the plan) |
| `tools/bench/` | Replay bench: a tools commit scored against reviewer findings and fab-history bugs |
| `bench/design/` | Design-bench briefs (rung 1 Qwiic IMU, rung 2 motor channel) and the phase-0 review protocol |
| `docs/upstream/` | Issue drafts for Diode `pcb` (not posted) |

## Requirements

KiCad 10.0.1 at `/Applications/KiCad/KiCad.app` (kicad-cli and the bundled Python with `pcbnew`), Diode `pcb` 0.4.95
at `~/.local/bin/pcb` for the Zener front end, kicad-druid at `/tmp/pcb-ref/kicad-druid` (`KICAD_DRUID`) for the fab
rule packs, python3. No pip dependencies for the tools; `.venv` holds SKiDL for the fallback path.

## Install (manual)

```sh
ln -s ~/code-stuff/alex-pcb-skills/skills/kicad-design ~/.claude/skills/kicad-design
ln -s ~/code-stuff/alex-pcb-skills/skills/pcb-design-review ~/.claude/skills/pcb-design-review
```

## Quick use

```sh
S=~/code-stuff/alex-pcb-skills/skills/kicad-design/scripts
$S/pcb drc layout/x/x.kicad_pcb --pack jlcpcb        # plain and packed DRC, sentinel, pack floored to the board setup
$S/pcb check layout/x/x.kicad_pcb checks.json        # intent rows; undeclared rails, connectors, jumpers, test points fail
$S/pcb q layout/x/x.kicad_pcb decoupling             # one measurement (pcb q alone lists them)
$S/pcb fab layout/x/x.kicad_pcb --out fab            # gerbers, drill, JLC BOM and CPL, renders, fab.json
$S/pcb regen-check . --cmd tools/regen.sh --board layout/x/x.kicad_pcb --generated layout fab
$S/pcb schfix layout/x/x.kicad_sch                   # after pcb apply schematic
$S/pcb py tools/layout_board.py layout/x/x.kicad_pcb # a pcblib layout script
sh tools/verify_all.sh --changed --dry-run           # what this change affects
python3 -I tools/bench/replay.py                     # the replay bench on HEAD
```
