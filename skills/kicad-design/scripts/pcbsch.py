#!/usr/bin/env python3
"""pcb schfix SCH.kicad_sch [--board X.kicad_pcb] [--paper A3] [--no-global] [--no-flags] [--no-symlib] [--dry-run]

Post-fix the schematic that Diode `pcb apply schematic` writes (R1-Z1-T3), in place and idempotently. Re-run after
every `pcb apply schematic`. Each step is a gap in the exporter; `docs/upstream/` holds the issue drafts.
  1. fields    MPN, Manufacturer, LCSC, Datasheet, Package from the board's footprint properties onto each symbol
               instance (hidden), so BOM exports and parity see them; the exporter leaves them on the footprint only
  2. dnp       a footprint marked DNP on the board sets (dnp yes) on its symbol; the exporter drops it
  3. labels    local labels become global labels on a single-sheet design, so the schematic net is "SDA" like the
               board net, not "/SDA" (22 parity warnings otherwise)
  4. symlib    the embedded lib_symbols block is written out as <project>_symbols.kicad_sym with a sym-lib-table
               entry, so ERC stops reporting lib_symbol_issues for every bare lib_id (32 on rung 1)
  5. flags     a PWR_FLAG plus global label for every net ERC reports as power_pin_not_driven, so no test-point
               power_out hack is needed in the .zen (the R1-Z1 workaround left one pin_to_pin warning)
Gate: the netlist connectivity before and after must be identical (renames allowed); otherwise the original is
restored and the exit code is 2. Prints ERC errors/warnings before and after. Plain python3 (text operations).
"""
import json, os, re, shutil, subprocess, sys, tempfile, uuid
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
KICAD_CLI = os.environ.get("KICAD_CLI", "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
KICAD_PY = os.environ.get("KICAD_PY", "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3")
FIELD_MAP = {"mpn": "MPN", "manufacturer": "Manufacturer", "lcsc": "LCSC", "datasheet": "Datasheet", "package": "Package"}
PWR_FLAG_SYMBOL = '''	(symbol "PWR_FLAG"
		(power global)
		(pin_numbers (hide yes))
		(pin_names (offset 0) (hide yes))
		(exclude_from_sim no)
		(in_bom yes)
		(on_board yes)
		(in_pos_files yes)
		(duplicate_pin_numbers_are_jumpers no)
		(property "Reference" "#FLG" (at 0 1.905 0) (show_name no) (do_not_autoplace no) (hide yes) (effects (font (size 1.27 1.27))))
		(property "Value" "PWR_FLAG" (at 0 3.81 0) (show_name no) (do_not_autoplace no) (effects (font (size 1.27 1.27))))
		(property "Footprint" "" (at 0 0 0) (show_name no) (do_not_autoplace no) (hide yes) (effects (font (size 1.27 1.27))))
		(property "Datasheet" "" (at 0 0 0) (show_name no) (do_not_autoplace no) (hide yes) (effects (font (size 1.27 1.27))))
		(property "Description" "Special symbol for telling ERC where power comes from" (at 0 0 0) (show_name no) (do_not_autoplace no) (hide yes) (effects (font (size 1.27 1.27))))
		(symbol "PWR_FLAG_0_0"
			(pin power_out line (at 0 0 90) (length 0)
				(name "" (effects (font (size 1.27 1.27))))
				(number "1" (effects (font (size 1.27 1.27))))
			)
		)
		(symbol "PWR_FLAG_0_1"
			(polyline (pts (xy 0 0) (xy 0 1.27) (xy -1.016 1.905) (xy 0 2.54) (xy 1.016 1.905) (xy 0 1.27))
				(stroke (width 0) (type default)) (fill (type none)))
		)
		(embedded_fonts no)
	)
'''


def sexp_block(text, start):
    """The balanced s-expression starting at index `start` (text[start] == '(')."""
    depth, in_str, j = 0, False, start
    while j < len(text):
        c = text[j]
        if in_str:
            if c == "\\":
                j += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start:j + 1]
        j += 1
    raise ValueError("unbalanced s-expression")


def instances(text):
    """(start, end, block) of every top-level symbol instance, i.e. '\\n\\t(symbol' after lib_symbols."""
    out = []
    for m in re.finditer(r"\n\t\(symbol\b", text):
        s = m.start() + 1
        blk = sexp_block(text, s)
        out.append((s, s + len(blk), blk))
    return out


def ref_of(blk):
    m = re.search(r'\(property "Reference" "([^"]+)"', blk)
    return m.group(1) if m else None


def erc(sch):
    tmp = tempfile.mkdtemp(prefix="schfix-")
    out = os.path.join(tmp, "erc.json")
    subprocess.run([KICAD_CLI, "sch", "erc", "--format", "json", "--severity-all", "-o", out, sch], capture_output=True)
    try:
        d = json.load(open(out))
    except (OSError, ValueError):
        shutil.rmtree(tmp, ignore_errors=True)
        return None
    shutil.rmtree(tmp, ignore_errors=True)
    viol = [v for s in d.get("sheets", []) for v in s.get("violations", [])]
    return viol


def erc_counts(viol):
    if viol is None:
        return "ERC failed"
    e = sum(v["severity"] == "error" for v in viol); w = sum(v["severity"] == "warning" for v in viol)
    return f"{e} errors / {w} warnings"


def netlist_nodes(sch):
    tmp = tempfile.mkdtemp(prefix="schfix-")
    out = os.path.join(tmp, "n.xml")
    subprocess.run([KICAD_CLI, "sch", "export", "netlist", "--format", "kicadxml", "-o", out, sch], capture_output=True)
    nets = {}
    padnet = {}
    if os.path.exists(out):
        for n in ET.parse(out).getroot().find("nets"):
            key = frozenset((x.get("ref"), x.get("pin")) for x in n)
            if key:
                nets[key] = n.get("name")
            for x in n:
                padnet[(x.get("ref"), x.get("pin"))] = n.get("name")
    shutil.rmtree(tmp, ignore_errors=True)
    return nets, padnet


def board_data(board):
    p = subprocess.run([KICAD_PY, "-I", os.path.join(HERE, "pcbq.py"), board, "fabdata", "--json"], capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit("schfix: pcbq fabdata failed:\n" + p.stderr[-500:])
    return {r["ref"]: r for r in json.loads(p.stdout)["footprints"]}


def prop(name, value, at, hide=True):
    return (f'\t\t(property "{name}" "{value}"\n\t\t\t(at {at})\n' + ("\t\t\t(hide yes)\n" if hide else "") +
            '\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n')


def main(argv):
    opts = {a for a in argv if a.startswith("--") and "=" not in a}
    def val(flag, default=None):
        if flag in argv:
            return argv[argv.index(flag) + 1]
        return default
    pos = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] not in ("--board", "--paper"))]
    if not pos:
        sys.exit(__doc__)
    sch = os.path.abspath(pos[0])
    board = val("--board") or os.path.splitext(sch)[0] + ".kicad_pcb"
    paper = val("--paper")
    dry = "--dry-run" in opts
    orig = open(sch, encoding="utf-8").read()
    text = orig
    report = {"sch": sch, "board": board if os.path.exists(board) else None}
    before_nets, _ = netlist_nodes(sch)
    report["erc_before"] = erc_counts(erc(sch))
    project = os.path.splitext(os.path.basename(sch))[0]
    root_uuid = re.search(r'\(uuid "([0-9a-f-]+)"\)', text).group(1)
    multi_sheet = "\n\t(sheet\n" in text or "\n\t(sheet " in text

    # ---- 1 + 2: fields and DNP from the board
    n_fields = n_dnp = 0
    if report["board"]:
        fd = board_data(board)
        new_text = text
        for s, e, blk in reversed(instances(text)):
            ref = ref_of(blk)
            if not ref or ref not in fd:
                continue
            r = fd[ref]
            have = dict(re.findall(r'\(property "([^"]+)" "([^"]*)"', blk))
            at_m = (re.search(r'\(property "Footprint" "[^"]*"\s*\(at ([^)]+)\)', blk)
                    or re.search(r'\(property "Reference" "[^"]*"\s*\(at ([^)]+)\)', blk))
            at = at_m.group(1) if at_m else "0 0 0"
            add = ""
            nb = blk
            for key, name in FIELD_MAP.items():
                v = r.get(key, "")
                if not v:
                    continue
                if name in have:
                    if have[name] == "":
                        nb = nb.replace(f'(property "{name}" ""', f'(property "{name}" "{v}"', 1); n_fields += 1
                    continue
                add += prop(name, v.replace('"', '\\"'), at); n_fields += 1
            if add:
                i = nb.find("\n\t\t(pin ")
                if i < 0:
                    i = nb.find("\n\t\t(instances")
                nb = nb[:i + 1] + add + nb[i + 1:]
            if r["dnp"] and "(dnp no)" in nb:
                nb = nb.replace("(dnp no)", "(dnp yes)", 1); n_dnp += 1
            new_text = new_text[:s] + nb + new_text[e:]
        text = new_text
    report["fields_added"] = n_fields
    report["dnp_set"] = n_dnp

    # ---- 3: local labels -> global labels (single sheet only)
    n_labels = 0
    if "--no-global" not in opts and not multi_sheet:
        def to_global(m):
            body = m.group(1)
            body = re.sub(r"(\(at [^)]+\))", r"\1\n\t\t(shape passive)", body, count=1)
            return "\t(global_label " + body
        text, n_labels = re.subn(r'\t\(label (".*?"\n\t\t\(at [^)]+\).*?\n\t\))', to_global, text, flags=re.S)
    report["labels_to_global"] = n_labels
    if multi_sheet:
        report["note"] = "multi-sheet schematic: labels left local"

    # ---- 4: project symbol library from lib_symbols, sym-lib-table with an empty nickname (bare lib_ids)
    if "--no-symlib" not in opts and "(lib_symbols" in text and not re.search(r'\(lib_id "[^":]+:', text):
        i = text.index("(lib_symbols")
        blk = sexp_block(text, i)
        inner = blk[len("(lib_symbols"):-1]
        if "PWR_FLAG" not in inner and "--no-flags" not in opts:
            pass  # added below once flags are known
        libp = os.path.join(os.path.dirname(sch), f"{project}_symbols.kicad_sym")
        tabp = os.path.join(os.path.dirname(sch), "sym-lib-table")
        report["symlib"] = libp
    else:
        libp = tabp = None

    # ---- 5: PWR_FLAG per undriven power net (needs the fixed-so-far text on disk to run ERC)
    n_flags = 0
    flagged = []
    if "--no-flags" not in opts:
        tmpd = tempfile.mkdtemp(prefix="schfix-")
        tsch = os.path.join(tmpd, os.path.basename(sch))
        open(tsch, "w", encoding="utf-8").write(text)
        for extra in ("sym-lib-table", f"{project}_symbols.kicad_sym", f"{project}.kicad_pro"):
            src = os.path.join(os.path.dirname(sch), extra)
            if os.path.exists(src):
                shutil.copy(src, tmpd)
        viol = erc(tsch) or []
        _, padnet = netlist_nodes(tsch)
        shutil.rmtree(tmpd, ignore_errors=True)
        nets = []
        for v in viol:
            if v.get("type") != "power_pin_not_driven":
                continue
            for it in v.get("items", []):
                m = re.match(r"Symbol (\S+) Pin (\S+) ", it.get("description", ""))
                if m:
                    n = padnet.get((m.group(1), m.group(2)))
                    if n and n not in nets:
                        nets.append(n)
        if nets:
            ats = [tuple(float(x) for x in m.groups()) for m in re.finditer(r"\n\t\t\(at ([\d.-]+) ([\d.-]+) [\d.-]+\)", text)]
            maxy = max((y for _, y in ats), default=50.0)
            y = round(maxy + 15.24, 2)
            if "PWR_FLAG" not in sexp_block(text, text.index("(lib_symbols")):
                i = text.index("(lib_symbols")
                blk = sexp_block(text, i)
                text = text[:i] + blk[:-1].rstrip() + "\n" + PWR_FLAG_SYMBOL + "\t)" + text[i + len(blk):]
            add = ""
            for k, net in enumerate(nets):
                x = round(25.4 + 25.4 * k, 2)
                u1, u2, u3 = (str(uuid.uuid4()) for _ in range(3))
                ref = f"#FLG{k + 1:02d}"
                add += (f'\t(symbol\n\t\t(lib_id "PWR_FLAG")\n\t\t(at {x} {y} 0)\n\t\t(unit 1)\n\t\t(body_style 1)\n\t\t(exclude_from_sim no)\n'
                        f'\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(in_pos_files yes)\n\t\t(dnp no)\n\t\t(fields_autoplaced yes)\n\t\t(uuid "{u1}")\n'
                        + prop("Reference", ref, f"{x} {y} 0") + prop("Value", "PWR_FLAG", f"{x} {round(y - 3.81, 2)} 0", hide=False)
                        + prop("Footprint", "", f"{x} {y} 0") + prop("Datasheet", "", f"{x} {y} 0")
                        + prop("Description", "Power flag added by pcb schfix for ERC (power_pin_not_driven)", f"{x} {y} 0")
                        + f'\t\t(pin "1"\n\t\t\t(uuid "{u2}")\n\t\t)\n\t\t(instances\n\t\t\t(project "{project}"\n\t\t\t\t(path "/{root_uuid}"\n'
                        f'\t\t\t\t\t(reference "{ref}")\n\t\t\t\t\t(unit 1)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)\n')
                add += (f'\t(global_label "{net}"\n\t\t(shape passive)\n\t\t(at {x} {y} 0)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n'
                        f'\t\t\t(justify left bottom)\n\t\t)\n\t\t(uuid "{u3}")\n\t)\n')
                flagged.append(net)
            n_flags = len(nets)
            # before the closing paren of the file (after the last top-level item)
            j = text.rstrip().rfind("\n)")
            text = text[:j + 1] + add + text[j + 1:]
    report["pwr_flags"] = flagged

    if paper:
        text = re.sub(r'\(paper "[^"]+"\)', f'(paper "{paper}")', text, count=1)

    if libp:
        i = text.index("(lib_symbols")
        inner = sexp_block(text, i)[len("(lib_symbols"):-1]
        lib_text = ('(kicad_symbol_lib\n\t(version 20251024)\n\t(generator "pcb_schfix")\n\t(generator_version "10.0")\n'
                    + inner.rstrip() + "\n)\n")
        tab_text = ('(sym_lib_table\n\t(version 7)\n\t(lib (name "")(type "KiCad")(uri "${KIPRJMOD}/%s")(options "")'
                    '(descr "lib_symbols embedded by pcb apply schematic; written by pcb schfix"))\n)\n' % os.path.basename(libp))

    changed = text != orig
    if dry:
        print(json.dumps(report, indent=1)); return 0
    if changed:
        open(sch, "w", encoding="utf-8").write(text)
    if libp:
        if not os.path.exists(libp) or open(libp).read() != lib_text:
            open(libp, "w", encoding="utf-8").write(lib_text)
        if not os.path.exists(tabp) or open(tabp).read() != tab_text:
            open(tabp, "w", encoding="utf-8").write(tab_text)
    after_nets, _ = netlist_nodes(sch)
    if set(after_nets) != set(before_nets):
        open(sch, "w", encoding="utf-8").write(orig)
        only_a = [before_nets[k] for k in before_nets if k not in after_nets]
        only_b = [after_nets[k] for k in after_nets if k not in before_nets]
        print(f"schfix: CONNECTIVITY CHANGED, original restored. only before: {only_a}; only after: {only_b}")
        return 2
    report["erc_after"] = erc_counts(erc(sch))
    report["changed"] = changed
    renamed = sum(1 for k in before_nets if before_nets[k] != after_nets.get(k))
    print(f"schfix {os.path.basename(sch)}: {'changed' if changed else 'no change'}; fields +{n_fields}, dnp {n_dnp}, "
          f"labels->global {n_labels}, PWR_FLAG {flagged or 'none'}, symlib {'written' if libp else 'skipped'}; "
          f"nets renamed {renamed}, connectivity identical; ERC {report['erc_before']} -> {report['erc_after']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
