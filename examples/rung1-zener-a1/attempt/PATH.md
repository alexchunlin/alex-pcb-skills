# Authoring path: Zener (Diode `pcb` 0.4.95)

- Source of truth: `.zen` files in this directory. `pcb build`, `pcb layout --no-open`, `pcb apply schematic`,
  `pcb dfm --offline`, `pcb test`, `pcb bom`. `pcb` is at `~/.local/bin/pcb`.
- Docs: `pcb help`, `pcb <cmd> --help`, https://docs.pcb.new (quickstart, spec, packages). The stdlib (generics,
  interfaces, units) is at `~/Library/Application Support/pcb/toolchains/0.4.95/aarch64-apple-darwin/lib/std/`;
  read `generics/*.zen` and `interfaces.zen` for the API. ICs are not in the stdlib: use `pcb new component` on a
  KiCad library part or a registry package.
- **Never open the KiCad GUI.** Always pass `--no-open` to `pcb layout`. If a KiCad window appears, quit it before
  any further write.
- KiCad CLI: `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli` (`sch erc`, `pcb drc --schematic-parity`,
  `sch export netlist --format kicadxml`, `pcb export gerbers|drill|pos|svg`, `pcb render`, `sch export bom`).
  Bundled Python with `pcbnew`: `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3`.
  Stock libraries: `/Applications/KiCad/KiCad.app/Contents/SharedSupport/{symbols,footprints}`.
- Fab rule pack: `/tmp/pcb-ref/kicad-druid/JLCPCB/JLCPCB.kicad_dru` (copy next to the board as `<board>.kicad_dru`).
- Part import if needed: `~/code-stuff/alex-pcb-skills/.venv/bin/easyeda2kicad --full --lcsc_id=C...`.
- Read-only references: `/tmp/pcb-ref/motorgo-plink-hardware`, `/tmp/pcb-ref/pace-racer-hardware`. Do not write there.
- Write only inside this directory. Append to `progress.md` after every completed step (step, result, time).
