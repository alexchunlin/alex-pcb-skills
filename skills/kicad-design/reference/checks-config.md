# checks.json

The design intent `pcb check` measures the board and netlist against. Every key is optional; an unknown key is a
config warn. Anything the netlist shows that is not declared here fails (power nets, connectors `J*`, jumpers `JP*`,
test points `TP*`), the same rule cadcheck applies. Net names are the project's own (`3V3` on Zener, `+3V3` and
`/SDA` on SKiDL). Worked configs: `<repo>/examples/rung1-zener-a1/checks.json`, `<repo>/examples/rung1-skidl-a1/checks.json`.

```jsonc
{
  "_about": "notes start with _",
  "project": "rung1-zener-a1",
  "policy": {"clearance_mm": 0.2, "track_mm": 0.2, "via_drill_mm": 0.3, "via_dia_mm": 0.6, "hole_clearance_mm": 0.3,
             "silk_text_mm": 1.0},                                    // the brief's numbers; never lowered (R1-A2-T5)
  "fields": ["MPN", "Manufacturer", "LCSC", "Datasheet"],              // required on every BOM part (default when absent)
  "pinmaps": {"U1": {"13": "SCL", "14": "SDA"}},                       // pin -> net for any reference (the Plink IMU swap, P1-T18)
  "rails": {"3V3": {"v": 3.3, "source": "Qwiic"}, "GND": {}},        // every net with a power pin or GND-like name
  "decoupling_max_mm": 2.0,                                             // nearest cap to every power_in pin (netlist pin types)
  "decoupling": [{"ic": "U1", "pin": "8", "cap": "C3", "max_mm": 2.0}], // named rows: the cap to that pin, measured (R1-Z1-F3)
  "buses": {"I2C": {"sda": "SDA", "scl": "SCL", "rail": "3V3", "max_sink_ma": 3.0, "chain_boards": 2,
                    "devices": {"U1": {"address": "0x6B", "strap": {"pin": "1", "high": "0x6B", "low": "0x6A"}}}}},
  "connectors": {"J1": {"1": "GND", "2": "3V3", "3": "SDA", "4": "SCL"}},   // pin -> net, from the netlist
  "jumpers": {"JP1": {"pads": {"1": "3V3", "2": "SA0", "3": "GND"}, "default": "1-2"}},  // shipped bridge from the footprint name
  "test_points": {"TP1": "GND", "TP2": "3V3"},
  "currents": {"VIN": 4.0, "5V": 3.0, "MOTOR_A": 2.5}, "copper_oz": {"outer": 1.0, "inner": 0.5}, "rise_c": 20,
                                                                        // IPC-2221 width per net vs the narrowest track per layer (rung 2)
  "thermal_vias": {"U3": {"pad": "EP", "min": 9, "within_mm": 2.5}},   // stitching vias on the pad's net near the pad
  "feeds": [{"pad": "U3.11", "amps": 2.5, "within_mm": 2.0}],           // what reaches a high-current pad: vias + touching tracks, as amps
  "calcs": [                                                            // formula rows, in order; R("R5"), C("C3"), L("L1") read the netlist values
    {"id": "p_ldo", "expr": "(5.0 - 3.3) * 0.5", "unit": "W", "max": 1.0},
    {"id": "tj_ldo", "expr": "40 + p_ldo * 90", "unit": "degC", "max": 125, "note": "theta_ja 90 K/W"},
    {"id": "ripple_pct", "expr": "100 * 5.0 * (1 - 5.0/17.0) / (f * L('L1')) / 3.0", "vars": {"f": 500e3}, "min": 30, "max": 40},
    {"id": "v_sense_2a", "expr": "2.0 * 455e-6 * R('R12')", "unit": "V", "min": 2.25, "max": 2.75}],
  "bringup": "../BRINGUP.md",                                           // default: BRINGUP.md found up to 3 dirs above the board
  "margin": {"pack": "jlcpcb", "default_ratio": 1.0, "min_ratio": {"track_width": 2.0, "clearance": 2.0, "via_drill": 2.0}},
  "accepted_warns": [{"check": "test_points", "match": "rail GND", "reason": "GND is on every connector shell"}]
}
```

| Check | Row | Fails when | ID |
|---|---|---|---|
| rails | one per power net | net carries power pins but is not declared; declared rail missing | P0-T2 |
| decoupling | one per IC `power_in` pin on a non-GND net, plus each declared row | no cap between the net and a GND net; nearest cap (or the declared cap) farther than `max_mm`, centre to centre | R1-Z1-F3, R1-S1-F2 |
| pullups | one per bus line | no resistor from the line to the rail through default-closed jumpers; `V / (R / chain_boards)` above `max_sink_ma` | R1-S1-F2 |
| addresses | one per device | duplicate address on a bus; strap pin resolves (through jumpers) to a level whose address differs from the declared one | P0-T2 |
| connectors | one per `J*` | undeclared connector; a declared pin on another net | P0-T2 |
| jumpers | one per `JP*` | undeclared; declared pad nets differ; shipped bridge differs from `default` | |
| test_points | one per `TP*`, one warn per rail without a TP | undeclared; wrong net; not named in the bring-up doc | |
| silk | one row | a refdes the bring-up doc names has no visible Reference or silk text | R1-Z1-F4 |
| margin | one per feature | actual / fab floor below `min_ratio` (track width and vias measured; clearances are the setup values) | R1-S1-F2 |
| policy | one per brief number | the board setup, the default net class or a measured minimum (narrowest track, smallest via, smallest silk text) is below the policy | R1-A2-T5 |
| fields | one per BOM part | a required field is empty on the footprint | R1-A2S-1 |
| pinmaps | one per declared reference | a declared pin is on another net | P1-T18 |
| currents | one per declared net | narrowest outer or inner track below the IPC-2221 width for the amps and rise (external k 0.048, internal 0.024); a net with no tracks warns (pours are not sized: use `feeds`) | P1-T21 |
| thermal_vias | one per pad | fewer vias on the pad's net within `within_mm` than `min` | P1-T21 |
| feeds | one per pad | via ampacity (IPC-2221 internal on the barrel, 25 um plating) within `within_mm` plus touching-track ampacity below `amps`; a pour-only feed fails because pour necks are not sized | R2-T5 |
| calcs | one per row | the value falls outside `min`/`max`; an expression that fails to evaluate | P1-T21 |
| refplane | one per net with tracks | bucket 3/4 net has more than `max_gap_mm` (0) off solid ground on the adjacent layer; bucket 2 warns above `mid_max_mm` (5); 1 and rails carry the mm as a cost; points within `antipad_mm` (0.5) of the net's own vias and `connector_mm` (1.5) of the through-hole pads of footprints it lands on are skipped; rows have `bucket`, `gaps` | REFPLANE-1, SIG-1, SIG-4 |
| return_via | one per net with vias | a via on a bucket 3/4 net has no ground via or through-hole ground pad within `max_mm_3` 2.0 / `max_mm_4` 1.0 mm; bucket 2 warns above `max_mm_2` 5.0 | SIG-2 |
| exposure | one per exposed net | track within `within_mm` (1.0) of the aggressor's copper on the same layer (default aggressor: the switch node), mm times `victim_weight` (3) for victims; fails (victim) or warns above `max_mm` if set, else a cost | SIG-3 |
| refstat | one per (row, matching part instance) | no passive of `pattern.class` in `pattern.band` on the part's canonical `pin` net whose other pin lands on `pattern.to` (GND, IC:<pin>, PWR); nearest one farther than `pattern.max_mm` pad to pad. Rows are corpus counts (`tools/bench/data/refstat-rows.json`, spike 2); declare the ones you want, the message quotes the support | SPIKE2 |
| signals | (data, no rows) per net: `driver`, `t_rise_ns` (null = DC), `source`, `slowed_by`, `victim`; `pcb signals checks.json --netlist x.xml` prints knee and bucket (1 <1 MHz, 2 1-50, 3 50-500, 4 >=500, P rail) and the nets left unclassified; the routing judges read the bucket | SIG-1 |

`pcb check x.kicad_pcb checks.json --only connectors,rails` runs a subset; `--netlist x.xml` and `--bringup F`
override the defaults (`<stem>.xml`, exported from `<stem>.kicad_sch` when missing). The report is `pcbcheck.json`:
`summary` (fails, warns, passes, accepted), `rows` (check, status, id, msg, value, limit, objects, finding),
`coverage`, `not_checked`. Exit 1 on any fail.
