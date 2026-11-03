"""Canonical pins, component classes and value bands for the `refstat` rows (spike 2, corpus reference circuits).

Shared by pcbcheck's `refstat` kind and by tools/corpus/refstat.py, which counts the patterns over bshada/open-schematics:
symbol libraries name the same pin differently (AMS1117 VI / VIN / IN, LSM6DS3 "SDO/SA0" / "SA0"), so rows key on a
canonical name. Plain python3, 3.9-compatible (KiCad's bundled Python imports it through pcbcheck).
"""
import re

PART_RX = {
    "AMS1117-3.3": r"AMS1117[-_ ]?(3[.,V]3|33\b)",
    "LSM6DS3": r"LSM6DS3(TR)?(-C)?(?![0-9A-Z])",
    "ESP32-WROOM-32": r"ESP32-WROOM-32",
    "ESP32-S3-WROOM-1": r"ESP32-S3-WROOM-1",
    "DRV8874": r"DRV8874",
    "TPS54620": r"TPS54620",
}
# pin number -> canonical name, used when the symbol's pin name says nothing
BY_NUMBER = {
    "AMS1117-3.3": {"1": "GND", "2": "VOUT", "3": "VIN", "4": "VOUT"},
    "LSM6DS3": {"1": "SA0", "2": "SDX", "3": "SCX", "4": "INT1", "5": "VDDIO", "6": "GND", "7": "GND", "8": "VDD",
                "9": "INT2", "10": "NC", "11": "NC", "12": "CS", "13": "SCL", "14": "SDA"},
    "ESP32-WROOM-32": {"1": "GND", "2": "3V3", "3": "EN", "25": "IO0", "35": "TXD0", "34": "RXD0", "38": "GND", "39": "GND"},
    "ESP32-S3-WROOM-1": {"1": "GND", "2": "3V3", "3": "EN", "27": "IO0", "37": "TXD0", "36": "RXD0", "40": "GND", "41": "GND"},
}


def part_regex(part):
    return re.compile(PART_RX[part], re.I)


def canon_pin(part, num, name):
    n = (name or "").upper().replace(" ", "").replace("~", "").replace("{", "").replace("}", "")
    num = str(num)
    if part == "AMS1117-3.3":
        if "IN" in n:
            return "VIN"
        if "OUT" in n:
            return "VOUT"
        if "GND" in n or "ADJ" in n:
            return "GND"
    elif part == "LSM6DS3":
        for key, c in (("VDDIO", "VDDIO"), ("VDD_IO", "VDDIO"), ("VDD", "VDD"), ("SA0", "SA0"), ("SDX", "SDX"), ("SCX", "SCX"),
                       ("OCS", "OCS"), ("CS", "CS"), ("INT1", "INT1"), ("INT2", "INT2"), ("SCL", "SCL"), ("SPC", "SCL"),
                       ("SDA", "SDA"), ("SDI", "SDA"), ("GND", "GND"), ("NC", "NC")):
            if key in n:
                return c
    elif part in ("ESP32-WROOM-32", "ESP32-S3-WROOM-1"):
        if n in ("3V3", "VDD", "3.3V", "VDD3P3", "VCC", "+3V3"):
            return "3V3"
        if n in ("EN", "CHIP_PU", "CHIP_EN", "RST", "RESET"):
            return "EN"
        if n in ("IO0", "GPIO0", "BOOT", "IO0/BOOT", "GPIO0/BOOT"):
            return "IO0"
        if "GND" in n:
            return "GND"
        if n in ("TXD0", "TX", "U0TXD", "TXD0/IO1", "IO1/TXD0") or (part == "ESP32-WROOM-32" and n in ("IO1", "GPIO1")):
            return "TXD0"
        if n in ("RXD0", "RX", "U0RXD", "RXD0/IO3", "IO3/RXD0") or (part == "ESP32-WROOM-32" and n in ("IO3", "GPIO3")):
            return "RXD0"
    return BY_NUMBER.get(part, {}).get(num) or (n or "#" + num)


def gnd_like(name):
    n = (name or "").upper().lstrip("/")
    return n.startswith(("GND", "VSS", "AGND", "DGND", "PGND", "0V")) or n in ("0", "EARTH", "-")


def power_like(name):
    n = (name or "").upper().lstrip("/")
    return bool(re.match(r"^(\+|VCC|VDD|VBUS|VBAT|VIN|VOUT|VSYS|V\d|\d+V\d*|3V3|5V)", n)) or bool(re.search(r"(^|[_+])\d+V\d*$|3V3|3\.3V|5V0", n))


def comp_class(ref, libpart=""):
    m = re.match(r"^([A-Za-z]+)", ref or "")
    p = (m.group(1) if m else "?").upper()
    lp = (libpart or "").upper()
    if p in ("C", "CP", "CE", "CB"):
        return "C"
    if p in ("R", "RN", "RV"):
        return "R"
    if p in ("FB", "FL") or "FERRITE" in lp or lp.startswith("FB"):
        return "FB"
    if p == "L":
        return "L"
    if p in ("D", "LED", "ZD", "TVS"):
        return "D"
    if p in ("U", "IC"):
        return "U"
    if p in ("J", "P", "CN", "CON", "X"):
        return "J"
    if p in ("SW", "S", "BTN", "K"):
        return "SW"
    if p in ("Q", "T", "M"):
        return "Q"
    if p in ("TP",):
        return "TP"
    if p in ("JP", "SJ"):
        return "JP"
    return p


def parse_value(s):
    """'4.7k' -> 4700, '2k2' -> 2200, '100nF' -> 1e-7, '10u/16V' -> 1e-5, '0.1uF' -> 1e-7; None when not a number."""
    s = (s or "").strip().replace("µ", "u").replace("μ", "u")
    m = re.match(r"^([\d.]+)\s*([pnumkKMGrR]?)\s*(\d*)", s)
    if not m or not m.group(1).replace(".", "", 1).isdigit():
        return None
    whole, unit, frac = m.groups()
    val = float(whole + ("." + frac if frac and "." not in whole else ""))
    return val * {"p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9, "r": 1, "R": 1, "": 1}[unit]


CAP_BANDS = [(1e-9, "pF"), (50e-9, "10n"), (300e-9, "100n"), (3e-6, "1u"), (15e-6, "10u"), (60e-6, "22u"), (1e9, "100u+")]
RES_BANDS = [(100, "R<100"), (1e3, "100R"), (10e3, "1k"), (100e3, "10k"), (1e12, "100k+")]


def value_band(cls, value):
    if cls not in ("C", "R"):
        return "-"
    v = parse_value(value)
    if v is None:
        return "?"
    if cls == "C" and v >= 1e-3:   # a bare "10" or "100" on a capacitor means uF in most hobby schematics
        v = v * 1e-6
    for lim, band in (CAP_BANDS if cls == "C" else RES_BANDS):
        if v < lim:
            return band
    return "?"


PASSIVE = ("C", "R", "L", "FB", "D")


def coarse_band(cls, band):
    """Capacitors split at 1 uF into bypass and bulk; other classes keep their band."""
    if cls != "C" or band in ("?", "-"):
        return band
    return "bypass" if band in ("pF", "10n", "100n") else "bulk"


def band_matches(cls, want, value):
    b = value_band(cls, value)
    return want == "*" or want == b or want == coarse_band(cls, b)
