# Block-by-block placement (`pcb block`)

Used when the run's PATH.md or brief says so. Lay the board out the way a person does: fix what the mechanics fix, give
each schematic block a region, finish one block before the next goes on the board, and join the blocks last.

1. **Blocks.** After `pcb layout`, `pcb block init layout/x/x.kicad_pcb --out blocks.json` gives one group per Zener
   module. Edit it: group by function, not by sheet alone. A connector goes with the circuit it serves, so the group
   that holds a connector anchors on it (`check_groups` warns about parts with more links to another group). Each group
   gets `region` [x0, y0, x1, y1] and the file gets `order`.
2. **Floorplan.** Lock the outline, mounting holes and connectors first, because they decide where signals enter. Regions
   follow the signal flow, with the power block between the power entry and its loads. Keep switching and noisy blocks
   apart from sensitive ones. `order` starts with the connector-bound and power blocks and ends with the block that has
   the most interface nets. Run `pcb block plan layout/x/x.kicad_pcb blocks.json` until it says OK; it prints the links
   between blocks, which are the nets you are about to run between regions, so read them. Regions that cross a
   high-link pair over a long distance are the thing to fix now.
3. **One block at a time.** Add the block's rows to `PLACEMENT` in `tools/layout_board.py`, its critical local copper
   (buck loop, feeds, decoupling exits, thermal vias) and call `b.park(PLACEMENT)` before `b.save()`, so every part not
   placed yet stays off the board. Run the script, then
   `pcb block gate layout/x/x.kicad_pcb blocks.json NAME --config checks.json`. A failed gate is fixed before the next
   block starts. Re-gating the block just passed is allowed; a block out of order is refused. Do not write the whole
   placement table in one go and gate afterwards: judge each block on the render or `pcb q` before moving on.
4. **Join.** When every gate has passed, route between blocks with `pcb route auto` or `pcb route waves`. Move a whole
   block if the join shows a problem, then re-gate from that block on.
5. **Report.** `pcb block report layout/x/x.kicad_pcb blocks.json --json` goes in `SUMMARY.md`: cohesion, parts out of
   region, gates, moves after a gate. Exit 1 when a part is out of its region or a gate is missing.
