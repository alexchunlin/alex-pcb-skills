#!/usr/bin/env python3
"""JLC parts cache for the `basic_parts` row (spike #3, C2): one fetch, dated, then every `pcb check` reads the file.

  python3 -I tools/bench/jlc_parts.py fetch BOARD.kicad_pcb [...]   # every LCSC code on the boards -> the cache
  python3 -I tools/bench/jlc_parts.py alts BOARD.kicad_pcb [...]    # basic parts with the same value and package for
                                                                    # each extended 0402/0603 R or C on the boards
  python3 -I tools/bench/jlc_parts.py show                          # the cache, one line a part

Cache: tools/bench/data/jlc_parts.json {fetched, source, fee_usd, parts: {LCSC: {library basic|extended, preferred,
stock, price_1, package, mpn, brand, describe}}, alternatives: {LCSC: [...]}}. The library type is JLC's
`componentLibraryType` ("base" = basic, "expand" = extended); `preferred` is JLC's preferredComponentFlag (preferred
extended parts carry no feeder fee on Economic PCBA). Source: the parts endpoint JLC's own search page calls; one POST a
part, no key. Fee: JLC assembly pricing (https://jlcpcb.com/help/article/pcb-assembly-price, read 2026-11-03), $3.07 per
extended part type on Economic, $1.53 on Standard. Plain python3, standard library.
"""
import datetime as dt, json, re, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PCB = str(ROOT / "skills/kicad-design/scripts/pcb")
CACHE = ROOT / "tools/bench/data/jlc_parts.json"
URL = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList/v2"
FEE = {"economic": 3.07, "standard": 1.53}


def query(keyword, page_size=10, extra=None):
    body = {"keyword": keyword, "currentPage": 1, "pageSize": page_size}
    body.update(extra or {})
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json",
                                                                               "User-Agent": "alex-pcb-skills bench"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.load(r)
    return ((d.get("data") or {}).get("componentPageInfo") or {}).get("list") or []


def entry(x):
    pr = sorted(x.get("componentPrices") or [], key=lambda p: p["startNumber"])
    return {"library": {"base": "basic", "expand": "extended"}.get(x.get("componentLibraryType"), x.get("componentLibraryType")),
            "preferred": bool(x.get("preferredComponentFlag")), "stock": x.get("stockCount"),
            "price_1": pr[0]["productPrice"] if pr else None, "package": x.get("componentSpecificationEn"),
            "mpn": x.get("componentModelEn"), "brand": x.get("componentBrandEn"), "describe": (x.get("describe") or "")[:160],
            "type": x.get("firstSortName")}


def bom(board):
    p = subprocess.run([PCB, "q", str(board), "fabdata", "--json"], capture_output=True, text=True)
    fps = json.loads(p.stdout.strip().splitlines()[-1])["footprints"]
    return [f for f in fps if not f["dnp"] and not f["exclude_bom"]]


def load():
    return json.load(open(CACHE)) if CACHE.exists() else {"parts": {}, "alternatives": {}}


def save(c):
    c.update(fetched=dt.date.today().isoformat(), source=URL, fee_usd=FEE,
             fee_source="https://jlcpcb.com/help/article/pcb-assembly-price (read 2026-11-03)")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    json.dump(c, open(CACHE, "w"), indent=1, sort_keys=True)
    open(CACHE, "a").write("\n")


def fetch(boards):
    c = load()
    codes = sorted({f["lcsc"].strip() for b in boards for f in bom(b) if f.get("lcsc", "").strip()})
    for code in codes:
        hits = [x for x in query(code) if x.get("componentCode") == code]
        c["parts"][code] = entry(hits[0]) if hits else {"library": "not found"}
        time.sleep(0.3)
        print(code, c["parts"][code].get("library"), c["parts"][code].get("stock"), c["parts"][code].get("mpn"))
    save(c)


def size_code(fp):
    m = re.search(r"_(0201|0402|0603|0805|1206)_", fp)
    return m.group(1) if m else None


def two_sig(val):
    """'68.1k' -> '68k', '2.74k' -> '2.7k', '52.3k' -> '52k': the nearest two-significant-digit value (E24 territory)."""
    m = re.match(r"([\d.]+)([kKmMR]?)", val)
    if not m:
        return None
    x = float(m.group(1))
    d = 10 ** (len(str(int(x))) - 2) if x >= 10 else 0.1
    r = round(x / d) * d
    return (f"{r:g}" + m.group(2)) if abs(r - x) > 1e-9 else None


def alts(boards):
    """For each extended R or C: JLC basic parts of the same value (any size, the same size first), and for a resistor
    the nearest two-significant-digit value too. The JLC search takes componentLibraryType 'base' as a filter."""
    c = load()
    c["alternatives"] = {}
    for b in boards:
        for f in bom(b):
            code, sz = f.get("lcsc", "").strip(), size_code(f["footprint"])
            p = c["parts"].get(code, {})
            if p.get("library") != "extended" or not sz or not re.match(r"[RC]\d", f["ref"]) or code in c["alternatives"]:
                continue
            val = f["value"].split()[0]
            unit = "Ω" if f["ref"].startswith("R") else ""
            tries = [val] + ([two_sig(val)] if unit and two_sig(val) else [])
            found = []
            for v in tries:
                for x in query(v + unit, 50, {"componentLibraryType": "base"}):
                    e = entry(x) | {"lcsc": x.get("componentCode"), "value": v}
                    if v + unit in (x.get("describe") or "") and e["package"] in ("0201", "0402", "0603", "0805"):
                        found.append(e)
                time.sleep(0.3)
            found.sort(key=lambda e: (e["value"] != val, e["package"] != sz))
            c["alternatives"][code] = {"ref": f["ref"], "board": Path(b).stem, "value": f["value"], "size": sz,
                                       "basic": [{k: e[k] for k in ("lcsc", "value", "package", "describe", "stock")} for e in found[:4]]}
            print(f["ref"], code, f["value"], sz, "->", [(e["lcsc"], e["value"], e["package"]) for e in found[:4]])
    save(c)


def main(argv):
    if not argv or argv[0] not in ("fetch", "alts", "show"):
        sys.exit(__doc__)
    if argv[0] == "fetch":
        fetch(argv[1:])
    elif argv[0] == "alts":
        alts(argv[1:])
    else:
        c = load()
        print("fetched", c.get("fetched"))
        for k, v in sorted(c["parts"].items()):
            print(k, v.get("library"), v.get("preferred"), v.get("stock"), v.get("price_1"), v.get("mpn"))


if __name__ == "__main__":
    main(sys.argv[1:])
