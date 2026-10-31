# `pcb apply schematic`: part properties are not written to schematic symbol instances

**Version** pcb 0.4.95, KiCad 10.0.1, macOS.

**What happens** `properties={"MPN": ..., "Manufacturer": ..., "LCSC": ..., "Datasheet": ...}` on a `Component()`
(and `Mpn`/`Lcsc` from `pcb new component`) end up as footprint properties in the `.kicad_pcb` written by
`pcb layout`, but the `.kicad_sch` written by `pcb apply schematic` carries only Reference, Value, Footprint,
Datasheet (empty for stdlib generics) and Description on each symbol instance.

**Why it matters** `kicad-cli sch export bom --fields MPN,LCSC,...` is empty; KiCad's schematic-parity DRC reports
`footprint_symbol_field_mismatch` for every part once the fields exist on one side only; assembly-house BOMs are
built from the schematic by most teams.

**Reproduce** On a board with `Component(... properties={"MPN": "LSM6DS3TR-C", "LCSC": "C967633"})`:
`pcb build && pcb layout --no-open && pcb apply schematic --no-open`, then
`grep -c '"LCSC"' layout/<board>/<board>.kicad_sch` is 0 while `grep -c '"Lcsc"' layout/<board>/<board>.kicad_pcb` is 1.

**Expected** Every component property appears as a hidden `(property "MPN" "...")` on the symbol instance, with the
same name as on the footprint (case included), so KiCad's parity check passes without a post-processor.

**Workaround** A 150-line script copies the footprint properties onto the symbols after each apply (27 fields on a
15-part board) and upper-cases `Mpn`/`Lcsc` on the footprints so the two sides match.
