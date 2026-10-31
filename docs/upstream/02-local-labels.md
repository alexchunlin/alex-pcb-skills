# `pcb apply schematic`: nets are drawn as local labels, so schematic and board net names differ

**Version** pcb 0.4.95, KiCad 10.0.1.

**What happens** Signal nets (`SDA`, `SCL`, `INT1`, ...) are drawn with `(label "SDA" ...)`. KiCad names a
local label's net `/SDA` (sheet-path prefixed) while `pcb layout` writes the board net as `SDA`. `kicad-cli pcb drc
--schematic-parity` then reports a `net_conflict` for every pad on those nets: 22 warnings on a 15-part board.
Power nets use power symbols and match.

**Expected** Either global labels (the net is `SDA` on both sides) or, on multi-sheet designs, hierarchical labels
with the sheet path that `pcb layout` uses for the board net names.

**Workaround** Convert `(label` to `(global_label` with `(shape passive)` on single-sheet designs; parity then
shows only the two `unconnected-(U1.U:10)` vs `unconnected-(U1-NC-Pad10)` NC-pad naming warnings.
