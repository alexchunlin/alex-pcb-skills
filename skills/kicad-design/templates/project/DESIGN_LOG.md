# Design log: PROJECT

## 1. Plan (before code)
- Rails and current budget per rail (table). Source of each rail; PWR_FLAG by `pcb schfix`.
- Bus map: devices and addresses, straps, pull-up value with the bus-capacitance arithmetic, sink current per line
  and with the declared chain.
- Connector pin maps (one table per connector), jumper tables (pads, shipped bridge, meaning).
- Parts: ref, MPN, Manufacturer, LCSC, package, datasheet URL.
- Floor plan: what sits where and why; decoupling caps with the pin each serves and the target distance.
- Stackup and design margin: clearance, track, via, hole clearance, edge, silk; the fab floor for comparison.
Every row above has a line in `checks.json` before step 2.

## 2. Decisions with numbers
## 3. What was checked and how (command, result)
## 4. Open issues
