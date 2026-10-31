#!/usr/bin/env python3
"""Check the exported KiCad netlist (kicadxml) against the brief's electrical requirements. Exit 1 on any failure."""
import sys
import xml.etree.ElementTree as ET

root = ET.parse(sys.argv[1]).getroot()
nets = {}
for n in root.find("nets"):
    nets[n.get("name")] = {f"{x.get('ref')}.{x.get('pin')}" for x in n.findall("node")}
def net_of(node):
    for name, nodes in nets.items():
        if node in nodes:
            return name
    return None

checks = []
def expect(desc, cond):
    checks.append((desc, bool(cond)))

# Qwiic pin order on both connectors: 1 GND, 2 3V3, 3 SDA, 4 SCL
for j in ("J1", "J2"):
    for pin, net in (("1", "GND"), ("2", "3V3"), ("3", "SDA"), ("4", "SCL")):
        expect(f"{j} pin {pin} = {net} (Qwiic order)", net_of(f"{j}.{pin}") == net)
    expect(f"{j} retention tabs on GND", net_of(f"{j}.MP") == "GND")
# sensor pins
pins = {"1": "SA0", "2": "GND", "3": "GND", "4": "INT1", "5": "3V3", "6": "GND", "7": "GND", "8": "3V3", "9": "INT2",
        "12": "3V3", "13": "SCL", "14": "SDA"}
for p, net in pins.items():
    expect(f"U1 pin {p} ({net})", net_of(f"U1.{p}") == net)
for p in ("10", "11"):
    expect(f"U1 pin {p} unconnected", (net_of(f"U1.{p}") or "unconnected").startswith("unconnected"))
# address jumper: pad 1 3V3 (bridged by default -> 0x6B), pad 2 SA0, pad 3 GND
expect("JP1: 3V3 / SA0 / GND", (net_of("JP1.1"), net_of("JP1.2"), net_of("JP1.3")) == ("3V3", "SA0", "GND"))
# pull-ups: R1 SDA, R2 SCL, tops to JP2 outer pads, JP2 centre on 3V3
expect("R1 between SDA and PU_SDA", {net_of("R1.1"), net_of("R1.2")} == {"SDA", "PU_SDA"})
expect("R2 between SCL and PU_SCL", {net_of("R2.1"), net_of("R2.2")} == {"SCL", "PU_SCL"})
expect("JP2: PU_SDA / 3V3 / PU_SCL", (net_of("JP2.1"), net_of("JP2.2"), net_of("JP2.3")) == ("PU_SDA", "3V3", "PU_SCL"))
# header: INT1 INT2 SDA SCL
for pin, net in (("1", "INT1"), ("2", "INT2"), ("3", "SDA"), ("4", "SCL")):
    expect(f"J3 pin {pin} = {net}", net_of(f"J3.{pin}") == net)
# decoupling: three caps between 3V3 and GND
for c in ("C1", "C2", "C3"):
    expect(f"{c} between 3V3 and GND", {net_of(f"{c}.1"), net_of(f"{c}.2")} == {"3V3", "GND"})
expect("TP1 = GND, TP2 = 3V3", net_of("TP1.1") == "GND" and net_of("TP2.1") == "3V3")
# nothing else on the I2C nets
expect("SDA members", nets.get("SDA") == {"U1.14", "J1.3", "J2.3", "J3.3", "R1.2"})
expect("SCL members", nets.get("SCL") == {"U1.13", "J1.4", "J2.4", "J3.4", "R2.2"})

bad = [d for d, ok in checks if not ok]
for d, ok in checks:
    print(("PASS " if ok else "FAIL ") + d)
print(f"{len(checks) - len(bad)}/{len(checks)} netlist checks passed")
sys.exit(1 if bad else 0)
