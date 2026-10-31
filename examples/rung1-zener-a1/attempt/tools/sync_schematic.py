#!/usr/bin/env python3
"""Post-process the schematic that `pcb apply schematic` writes so it carries what the brief asks for:

1. Part fields on every symbol instance: MPN, Manufacturer, LCSC, Datasheet (and Package when present), copied
   from the footprint properties of the matching reference in the generated .kicad_pcb (Zener puts Mpn /
   Manufacturer / Lcsc / Datasheet on footprints but not on schematic symbols).
2. Net labels: the exporter writes local labels, which KiCad names "/SDA" on the root sheet while the board
   nets are "SDA"; on this single-sheet design they are converted to global labels so DRC schematic parity
   compares like with like. Power nets already use global power symbols and are untouched.

4. Sheet size A4 -> A3 so the auto-placed symbols all sit inside the frame.

Idempotent. Re-run after every `pcb apply schematic`. Usage: sync_schematic.py <board.kicad_pcb> <sch.kicad_sch>
"""
import re, sys

pcb_path, sch_path = sys.argv[1:3]
pcb = open(pcb_path, encoding="utf-8").read()
sch = open(sch_path, encoding="utf-8").read()

# ---- 1. harvest footprint properties per reference from the board
FIELD_MAP = {"Mpn": "MPN", "MPN": "MPN", "Manufacturer": "Manufacturer", "Lcsc": "LCSC", "LCSC": "LCSC", "Datasheet": "Datasheet", "Package": "Package"}
fields = {}
for m in re.finditer(r'\(footprint "[^"]+"(.*?)\n\t\t\((?:pad|fp_line|fp_text|fp_circle|fp_rect|fp_poly|model) ', pcb, re.S):
    block = m.group(1)
    props = dict(re.findall(r'\(property "([^"]+)" "([^"]*)"', block))
    ref = props.get("Reference")
    if ref:
        fields[ref] = {FIELD_MAP[k]: v for k, v in props.items() if k in FIELD_MAP and v}

# ---- 2. inject fields into each symbol instance (the part of the file after lib_symbols)
head_end = sch.index("\n\t(symbol\n") if "\n\t(symbol\n" in sch else sch.index('\n\t(symbol (lib_id')
def add_fields(m):
    block = m.group(0)
    ref_m = re.search(r'\(property "Reference" "([^"]+)"', block)
    if not ref_m:
        return block
    ref = ref_m.group(1)
    want = fields.get(ref, {})
    if not want:
        return block
    have = dict(re.findall(r'\(property "([^"]+)" "([^"]*)"', block))
    # position/visibility template: copy the Value property's "at" and hide the new fields
    at_m = re.search(r'\(property "Value" "[^"]*"\n\t\t\t\(at ([^)]+)\)', block)
    at = at_m.group(1) if at_m else "0 0 0"
    new = ""
    for k, v in want.items():
        if k in have:
            if have[k] == "" and v:
                block = block.replace(f'(property "{k}" ""', f'(property "{k}" "{v}"', 1)
            continue
        new += f'\t\t(property "{k}" "{v}"\n\t\t\t(at {at})\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(hide yes)\n\t\t\t)\n\t\t)\n'
    if new:
        # insert before the first (pin ...) or (instances ...) entry of the instance
        i = block.find("\n\t\t(pin ")
        if i < 0:
            i = block.find("\n\t\t(instances")
        block = block[: i + 1] + new + block[i + 1 :]
    return block

tail = re.sub(r'\n\t\(symbol\n\t\t\(lib_id .*?\n\t\)(?=\n)', lambda m: add_fields(m), sch[head_end:], flags=re.S)
sch = sch[:head_end] + tail

# ---- 3. local labels -> global labels (single sheet): "(label "X" (at ...) (effects ...) (uuid ...))"
def to_global(m):
    body = m.group(1)
    # global labels need a shape; insert it right after the "at" clause
    body = re.sub(r'(\(at [^)]+\))', r'\1\n\t\t(shape passive)', body, count=1)
    return "\t(global_label " + body
sch, n_labels = re.subn(r'\t\(label (".*?"\n\t\t\(at [^)]+\).*?\n\t\))', lambda m: to_global(m) , sch, flags=re.S)

# ---- 4. the exporter auto-places on A4 and the right-hand column runs off the sheet; A3 keeps everything inside
sch = sch.replace('(paper "A4")', '(paper "A3")', 1)

open(sch_path, "w", encoding="utf-8").write(sch)
print(f"synced {len(fields)} footprints' fields into symbols; converted {n_labels} local labels to global labels")
