# checks.json

The design intent `pcb check` measures the board and netlist against. Every key is optional; an unknown key is a
config warn. Anything the netlist shows that is not declared here fails (power nets, connectors `J*`, jumpers `JP*`,
test points `TP*`), the same rule cadcheck applies. Net names are the project's own (`3V3` on Zener, `+3V3` and
`/SDA` on SKiDL). Worked configs: `<repo>/examples/rung1-zener-a1/checks.json`, `<repo>/examples/rung1-skidl-a1/checks.json`.

```jsonc
{
  "_about": "notes start with _",
  "project": "rung1-zener-a1",
  "rails": {"3V3": {"v": 3.3, "source": "Qwiic"}, "GND": {}},        // every net with a power pin or GND-like name
  "decoupling_max_mm": 2.0,                                             // nearest cap to every power_in pin (netlist pin types)
  "decoupling": [{"ic": "U1", "pin": "8", "cap": "C3", "max_mm": 2.0}], // named rows: the cap to that pin, measured (R1-Z1-F3)
  "buses": {"I2C": {"sda": "SDA", "scl": "SCL", "rail": "3V3", "max_sink_ma": 3.0, "chain_boards": 2,
                    "devices": {"U1": {"address": "0x6B", "strap": {"pin": "1", "high": "0x6B", "low": "0x6A"}}}}},
  "connectors": {"J1": {"1": "GND", "2": "3V3", "3": "SDA", "4": "SCL"}},   // pin -> net, from the netlist
  "jumpers": {"JP1": {"pads": {"1": "3V3", "2": "SA0", "3": "GND"}, "default": "1-2"}},  // shipped bridge from the footprint name
  "test_points": {"TP1": "GND", "TP2": "3V3"},
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

`pcb check x.kicad_pcb checks.json --only connectors,rails` runs a subset; `--netlist x.xml` and `--bringup F`
override the defaults (`<stem>.xml`, exported from `<stem>.kicad_sch` when missing). The report is `pcbcheck.json`:
`summary` (fails, warns, passes, accepted), `rows` (check, status, id, msg, value, limit, objects, finding),
`coverage`, `not_checked`. Exit 1 on any fail.
