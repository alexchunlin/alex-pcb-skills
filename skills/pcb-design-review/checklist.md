# Evidence checklist

Each line names the evidence that settles it. A `pcb check` row beats a `pcb q` line, which beats a render. IDs
point into `<repo>/docs/FINDINGS.md`.

## Electrical
- [ ] Connector pin maps from the netlist: `connectors` rows pass for every `J*`, including the daisy-chained pair
  (Qwiic order GND, 3V3, SDA, SCL on both). An undeclared connector is a config finding.
- [ ] Bus: `addresses` rows (unique, strap resolves to the declared default through the shipped jumper bridge),
  `pullups` rows (resistor present through the default-closed jumper; sink current per line and with the declared
  chain under the limit). Re-do the bus-capacitance arithmetic from the log (R1-Z1: 161 pF at 2.2 k, 300 ns).
- [ ] Rails: every power net declared (`rails`); each has a source (PWR_FLAG or a regulator output) and a test point
  (`test_points` warn otherwise); current budget per rail in the log.
- [ ] Decoupling: `decoupling` rows per supply pin, with the declared cap named for bulk caps, under the brief's
  distance (R1-Z1-F3: 2.64 mm against 2). Read `ic_pads_mm` when the nearest pad is a strap (P1-T5).
- [ ] Pin map vs datasheet: the IC's power, ground, NC and strap pins on the right nets (the `rails` and
  `addresses` rows cover power and straps; grep the netlist for the NC pins).
- [ ] Axes and orientation marks match the datasheet figure; verify from the footprint pad numbers and the
  silk arrow coordinates (`pcb q silk`, `pcb q pads U1`), not from the render.
- [ ] ERC: 0 errors; each warning in the log with a reason (the `pin_to_pin` on a flagged GND tie-off is one).

## Manufacturability
- [ ] `pcb drc`: plain errors and packed errors both 0 at a 9; otherwise list by type. Sentinel fired. Any
  `capped_types` means the count is a floor (P1-T2). `pack_relaxes_setup` says how much the pack would have hidden.
- [ ] `margin` rows against the declared ratios; the log's "Nx the floor" claim measured (R1-S1-F2).
- [ ] Zones: `pcb q coverage U1` for the plane under the IC; `pcb q zones` all filled; no isolated copper warnings
  in the plain DRC (P1-T10).
- [ ] Vias and tracks: `pcb q vias` sizes against the brief; `pcb q net <power>` widths against the current budget.
- [ ] Fab package: `pcb fab` file count, `bom_missing_lcsc` empty, every DNP intentional, `cpl_origin_offsets_mm`
  explained (R1-S1-F4), no `--board-plot-params` artefacts (R1-S1-F3).
- [ ] Connectors at the edge: opening outward, body inside the edge by a stated amount with a reason (R1-Z1-T7:
  0.6 mm inside because of the pack's edge clearance; a per-footprint accepted warn, not a global relaxation).
- [ ] Silk: `silk` row passes (every part the bring-up names is findable), text 1.0 mm / 0.15 mm, jumper states and
  header pin names present (`pcb q silk`).
- [ ] Courtyards, mask bridges, hole clearances: zero in the plain DRC by type.

## Documentation and intent
- [ ] `pcb regen-check` REGENERATES: exit 0 twice, pass 1 equal to pass 2 and to the handed-in tree (R1-Z1-F2).
- [ ] `checks.json` has a row for every numeric or structural claim in the brief and the log; `accepted_warns`
  each with a reason you agree with; `coverage` and `not_checked` read.
- [ ] `DESIGN_LOG.md`: every decision with its number; every number reproduces (pull-up, decoupling, address,
  current budget, margin); the wall time from the transcript, not the designer's clock.
- [ ] `BRINGUP.md`: numbered steps, each with the probe point and the expected reading; the register values
  reproduce from the datasheet; the `test_points` rows show the named points exist on the declared nets.
- [ ] BOM: MPN, Manufacturer, LCSC, Datasheet on every line; LCSC like `C\d+`; passives with value and package.
- [ ] `SUMMARY.md` numbers equal yours: ERC, DRC plain and packed, pcbcheck, regen-check, fab file count.
