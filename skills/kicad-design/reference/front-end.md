# Zener (Diode `pcb` 0.4.95) as measured

Provisional front end (Alex, 2026-10-31). The reviewed rung-1 source is `<repo>/examples/rung1-zener-a1/attempt/`:
read `qwiic_imu.zen` and one `parts/*.zen` before writing your own; the baseline took 8 minutes and 9 failed builds
to learn what is below (R1-Z1-T5, R1-Z1-T3).

## The commands that matter

| Command | Does | Measured |
|---|---|---|
| `pcb build x.zen` | evaluates the Starlark, writes the netlist and lints | 0.1 s; prints pin-type warnings (a test-point pin on a plain `Net` instead of `Ground()`) |
| `pcb layout --no-open x.zen` | writes `layout/x/x.kicad_pcb`, `.kicad_pro`, `fp-lib-table`; footprints with nets; re-runs keep placement | 1.4 s; **opens pcbnew without `--no-open`** (P0-T6); the `pcb` wrapper adds the flag |
| `pcb apply schematic --no-open x.zen` | writes `layout/x/x.kicad_sch`; idempotent ("schematic unchanged") | needs `pcb schfix` after it (P1-T16) |
| `pcb dfm --offline x.zen` | JLC floor rules offline, JSON | 56 rules on blinky, 43 pass on rung 1; exits non-zero on "fail" even when the one failing rule is one it cannot evaluate (solder-jumper bridge copper) |
| `pcb bom --offline -f json x.zen` | BOM with the component properties | the designer's `tools/bom_csv.py` turned it into the CSV; `pcb fab` now builds the BOM from the footprint fields instead |
| `pcb layout --check x.zen` | validate the existing layout and run DRC | runs with whatever `.kicad_dru` is in the project: use `pcb drc` instead |
| `pcb new component`, `pcb add github.com/...` | ICs come from the registry or from a local KiCad library | the stdlib is generics only (R, C, L, LED, crystal, ferrite, TVS, op-amp, headers, jumpers, test points, holes); LSM6DS3 came from `pcb new component` on the stock `Sensor_Motion` library, with the symbol and footprint vendored under `parts/` |

## What it gives that SKiDL did not

Placement preserved across re-runs, offline DFM, lints, a package registry, one tool for build and layout. SKiDL's
schematic drawer crashed on KiCad 10 and its `generate_pcb` needs pcbnew in the venv (R1-S1-T3, R1-S1-T4); SKiDL is
the netlist-only fallback, and `Board.from_netlist` takes that netlist.

## Where it stops (P1-T16, `docs/upstream/`)

- `properties=` reach the footprint (as `Mpn`, `Lcsc`) but not the schematic symbol: `pcb schfix` copies them, and
  pcblib's `fields()` upper-cases the footprint names so parity matches.
- Nets are local labels (`/SDA`): `pcb schfix` makes them global on a single sheet.
- Bare `lib_id`s with no library table: 32 `lib_symbol_issues`; `pcb schfix` writes the library and table.
- No PWR_FLAG: every `Component()` needs a footprint. Do not type a test-point pin `power_out` as the baseline did
  (it leaves a `pin_to_pin` warning); `pcb schfix` adds a PWR_FLAG per undriven net.
- `(dnp yes)` is written correctly for `dnp=True` components; R1-Z1-T3's "ignored DNP" was about the BOM path.

## Traps

- `CopperFinish("HASL Lead-free")` is rejected; the string is `"HAL lead-free"` (R1-Z1-T5).
- JST footprint rotation: decide the opening direction with `Board.orient_pads` on pad coordinates, not by guessing.
- `pcb dfm` runs the JLC floor, not the design-margin policy; the policy is `Board.setup()` plus `pcb drc` plain.
- Keep the `.kicad_dru` out of the project directory (P1-T14).
