#!/usr/bin/env python3
"""pcb bom JSON + board footprint fields -> fab BOM CSV with LCSC numbers. Usage: bom_csv.py bom.json board.kicad_pcb out.csv"""
import csv, json, re, sys
bom_json, pcb_path, out = sys.argv[1:4]
bom = json.load(open(bom_json))
pcb = open(pcb_path, encoding="utf-8").read()
lcsc, dnp = {}, {}
for m in re.finditer(r'\(footprint "[^"]+"(.*?)\n\t\t\((?:pad|fp_line|fp_text|fp_circle|fp_rect|fp_poly|model) ', pcb, re.S):
    props = dict(re.findall(r'\(property "([^"]+)" "([^"]*)"', m.group(1)))
    lcsc[props.get("Reference")] = props.get("LCSC", props.get("Lcsc", ""))
    dnp[props.get("Reference")] = bool(re.search(r"\(attr[^)]*\bdnp\b", m.group(1)))
rows = []
for g in bom:
    m = g["members"][0]
    refs = sorted(g["designators"])
    rows.append({"Designators": ",".join(refs), "Qty": g["quantity"], "Value": m.get("value", ""), "Package": m.get("package", ""),
                 "Manufacturer": m.get("manufacturer", ""), "MPN": m.get("mpn", ""), "LCSC": lcsc.get(refs[0], ""),
                 "Description": m.get("description", ""), "DNP": "yes" if any(dnp.get(r) for r in refs) else ""})
rows.sort(key=lambda r: r["Designators"])
with open(out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print("BOM rows:", len(rows), "->", out)
