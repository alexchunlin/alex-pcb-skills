# pcblib.board and pcb q

`pcblib.board.Board` is the only code in this repo that imports pcbnew (SWIG, KiCad 10.0.1, bundled Python 3.9).
Run scripts with `pcb py script.py args`, which puts `<skill>/scripts` and the cwd on `sys.path` (the interpreter
runs with `-I`, so PYTHONPATH is ignored). When KiCad 11 replaces SWIG with the IPC API, this module changes and
layout scripts do not.

## Board

| Call | Does | Trap it hides |
|---|---|---|
| `Board.load(path)` | a saved board with footprints and nets (`pcb layout --no-open` output) | |
| `Board.from_netlist(xml, path, libs={nick: dir}, fp_dir=None, place=None)` | build from a kicadxml netlist: footprints by ref, pad nets, KiCad paths, fields hidden on F.Fab, DNP and BOM/POS exclusion flags | `SetField` makes visible fields at the origin (R1-S1-T5) |
| `b.setup(clearance, track, via=(d, drill), hole_clearance, edge, silk, hole_to_hole, annular, drill, layers, thickness, netclass_track, aux_origin, tent_vias)` | board-setup minimums (plain DRC) and the default net class | |
| `b.fp(ref)`, `b.pad(ref, num)`, `b.pad_xy(ref, num)` | lookups; `MP1`/`MP2` address same-numbered `MP` pads top to bottom | |
| `b.net(name)` | the net; raises with the net list | `GetNetsByName()` corrupts the runtime (R1-Z1-T4) |
| `b.clear(tracks, zones, drawings)` | delete what a layout script rebuilds | `Remove()` poisons SWIG; `Delete()` is used (R1-Z1-T4) |
| `b.place(ref, x, y, rot, layer=None)`, `b.place_many({ref: (x, y, rot)})` | by reference, raises on unknown | |
| `b.orient_pads(ref, lambda P: ...)` | the rotation (0/90/180/270) under which the predicate on `P(padnum) -> (x, y)` holds | |
| `b.route(net, pts, layer="F.Cu", width=None)` | tracks through `(x, y)` mm or `"REF.PAD"` points; width from the net class | |
| `b.via(x, y, net, size=None, layers=("F.Cu", "B.Cu"))` | through via | |
| `b.zone(net, layer, outline=None, inset=0.5, clearance, min_width, thermal, relief_gap, spoke, priority, name)` | copper zone; default outline is the `outline_rect` frame inset | |
| `b.outline_rect(x0, y0, w, h, r)` | rounded rectangle on Edge.Cuts | |
| `b.line`, `b.arc`, `b.text(s, x, y, layer, size, thick, rot, mirror=None)`, `b.arrow(a, b)` | drawings; `B.*` text is mirrored unless told otherwise | |
| `b.fields(ref, {name: value})`, `b.field(ref, name)` | hidden fields on F.Fab; upper-cases `Lcsc`/`Mpn`; case-insensitive read | no `GetFieldByName` in 10.0.1 (R1-S1-T5) |
| `b.refdes(ref, visible, at, rot, size)`, `b.hide_refdes(keep=())` | reference text; keep what the bring-up doc names (R1-Z1-F4) | |
| `b.park(keep)` | every footprint not in `keep` to a grid right of the outline, for `pcb block` stages | spike #6 |
| `b.ground_islands(min_mm2=0.5, edge_mm=None)` | a ground via in each piece of ground fill KiCad would rip up, then refill; `b.fill_islands()` lists the pieces | spike #6 |
| `b.fill(passes=2)` | save, reload, `BuildConnectivity`, fill, save, twice; `b.b` is the reloaded board afterwards | in-memory fill segfaults (R1-S1-T5); first fill leaves islands (P1-T10) |
| `b.save(path=None)`, `b.summary()` | | |

Worked example: `<repo>/examples/rung1-zener-a1/layout_board.py` (107 lines) reproduces the reviewed rung-1 board's
placement and copper on a fresh `pcb layout` output (verify_all 17).

## pcb q

Every line starts with `PCBQ`; `--json` prints one object. Measurements the R1 reviewers made by hand, as commands:

| Command | Measures |
|---|---|
| `decoupling [IC...]` | each C* with a pad on an IC power net: centre and edge distance to the nearest IC pad on that net, distances to every IC pad on that net (the nearest may be a strap, P1-T5), GND pad to nearest via |
| `dist REF.PAD REF.PAD` | centre-to-centre and copper edge-to-edge |
| `net NAME`, `nets` | widths per layer, length, vias, pads |
| `vias` | count, (diameter, drill) set, per net |
| `coverage REF [LAYER]` | % of the courtyard box under filled zones per layer (plane under an IC) |
| `zones`, `holes`, `silk`, `settings`, `edge`, `fps`, `pads REF`, `fabdata` | inventories; `silk` lists hidden refdes; `settings` the plain-DRC minimums |

## kicad-cli facts that shape the wrappers

- `pcb drc` exits 0 and writes a report that silently omits every custom rule when the `.kicad_dru` has an error;
  only the sentinel rule tells (P0-T5, P1-T4).
- Each violation type is capped at 199 reports (P1-T2); `pcb drc` lists `capped_types`.
- A `.kicad_dru` in the project overrides the board setup in DRC **and** in the zone filler (P1-T3, P1-T14).
- Gerbers and drill files carry three timestamp lines; `pcb fab` hashes without them (P1-T9).
- The kicadxml netlist carries pin types (`power_in` on supply pins), which `pcb check` uses (P1-T12).
