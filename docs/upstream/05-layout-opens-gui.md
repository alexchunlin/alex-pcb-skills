# `pcb layout` opens the KiCad GUI by default; scripted flows need `--no-open` everywhere

**Version** pcb 0.4.95, KiCad 10.0.1, macOS.

**What happens** `pcb layout board.zen` writes the `.kicad_pcb` and then launches pcbnew on it unless `--no-open`
is given (same for `pcb apply schematic`). In an agent or CI flow a pcbnew window on the file is dangerous: KiCad
rewrites the file from memory on save, so any later scripted edit (placement, routing, fill) is lost the moment
someone saves the window.

**Expected** Opening the editor is the interactive case; a `--open` flag (or opening only on a TTY) keeps scripts
safe by default. At minimum, honour an environment variable (`PCB_NO_OPEN=1`) so wrappers need not patch every
call.

**Workaround** A wrapper inserts `--no-open` on `layout` and `apply`, refuses `pcb open`, and a watchdog polls
for pcbnew/eeschema processes during scripted runs.
