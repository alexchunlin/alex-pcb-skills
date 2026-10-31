# Upstream issue drafts for github.com/diodeinc/pcb (Zener, `pcb` 0.4.95)

Each file is one issue, written from a measured reproduction on the rung-1 Qwiic IMU board (FINDINGS R1-Z1-T3,
P0-T6, P1-T16). `pcb schfix` papers over 1-4 locally; the drafts ask for the fix at the source. Not posted yet:
posting goes out under Alex's GitHub account, so he decides. Reproduction project: `~/code-stuff/alex-pcb-runs/rung1-zener-a1`.

| # | File | Gap | Local workaround |
|---|---|---|---|
| 1 | `01-symbol-fields.md` | `properties=` (MPN, Manufacturer, LCSC, Datasheet) reach the footprint but not the schematic symbol instances | `pcb schfix` copies them from the board (27 fields on 10 symbols) |
| 2 | `02-local-labels.md` | nets are drawn as local labels, so the schematic net is `/SDA` and the board net `SDA`; 22 parity warnings | `pcb schfix` converts to global labels on single-sheet designs |
| 3 | `03-bare-lib-ids.md` | `lib_id "C_Small"` with no library nickname and no sym-lib-table: ERC reports `lib_symbol_issues` for all 32 symbols | `pcb schfix` writes `<project>_symbols.kicad_sym` + `sym-lib-table` |
| 4 | `04-pwr-flag.md` | every `Component()` needs a footprint, so a PWR_FLAG cannot be expressed; ERC `power_pin_not_driven` on every rail (2 errors) | `pcb schfix` adds a PWR_FLAG + global label per undriven net |
| 5 | `05-layout-opens-gui.md` | `pcb layout` opens pcbnew unless `--no-open`; a stray GUI rewrites scripted edits on save | the `pcb` wrapper forces `--no-open` and refuses `pcb open` |

Not filed: "DNP ignored" from R1-Z1-T3 does not reproduce on 0.4.95 (`(dnp yes)` is written for J3, verify_all 19).
