# `pcb apply schematic`: bare `lib_id`s with no library table make ERC report `lib_symbol_issues` for every symbol

**Version** pcb 0.4.95, KiCad 10.0.1.

**What happens** Symbols are embedded in `(lib_symbols ...)` and referenced as `(lib_id "C_Small")` with no
library nickname, and no `sym-lib-table` is written next to the schematic. `kicad-cli sch erc --severity-all`
reports one `lib_symbol_issues` warning per symbol instance ("The current configuration does not include the symbol
library ''"): 32 on a 15-part board, which buries the real warnings.

**Expected** A project `sym-lib-table` pointing at a generated `<board>_symbols.kicad_sym` (or lib_ids with a
nickname that the table resolves), as KiCad itself does on "save a copy of embedded symbols".

**Workaround** Write the `lib_symbols` block out as `<board>_symbols.kicad_sym` and a `sym-lib-table` with an
empty nickname: ERC goes from 33 warnings to 1.
