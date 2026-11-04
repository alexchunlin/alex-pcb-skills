#!/usr/bin/env python3
"""Spike 5: class labels per part of tools/bench/data/class-table.json, from JLC's category and description (issue correction:
labels, not pin-name rules). One POST a part, cached in the table under `labels`, so reruns read the file.

  python3 -I tools/corpus/classlabel.py fetch      # query every part with no label yet
  python3 -I tools/corpus/classlabel.py show       # part, table class, JLC class, category; disagreements first

A part JLC does not carry, or that it files under a generic category, is a miss; the label then comes from the reading pass
(`--read part=class` records `source: reading`, with the datasheet family as the evidence).
"""
import argparse, json, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/bench"))
import jlc_parts  # noqa: E402

TAB = ROOT / "tools/bench/data/class-table.json"
# a representative orderable name per part key where the key itself returns nothing
QUERY = {"TPS62xxx": "TPS62130", "TLV6256x": "TLV62569", "AP6320x": "AP63203", "AP63357": "AP63357", "ISM330": "ISM330DHCX", "ASM330": "ASM330LHH",
         "LSM6DSV": "LSM6DSV16X", "LSM6DSO": "LSM6DSOTR", "MPU-6050": "MPU-6050", "ICM-42688": "ICM-42688-P", "BMI160": "BMI160", "DRV8841": "DRV8841",
         "L298": "L298N", "L293": "L293D", "TB6612": "TB6612FNG", "TB67H420": "TB67H420FTG", "TB67H450": "TB67H450FNG", "MC33887": "MC33887", "RZ7886": "RZ7886",
         "TC78H660": "TC78H660FTG", "A4953": "A4953", "STSPIN240": "STSPIN240", "L6205": "L6205", "DRV8212": "DRV8212", "AMS1117-3.3": "AMS1117-3.3",
         "HT7333": "HT7333", "MCP1700": "MCP1700", "AP2112": "AP2112K-3.3", "LP2985": "LP2985", "TLV700": "TLV70033", "TLV757": "TLV75733", "TLV755": "TLV75533",
         "LD1117": "LD1117", "SY8113": "SY8113", "SY8120": "SY8120", "TPS563200": "TPS563200", "TPS562200": "TPS562200", "TPS561201": "TPS561201"}


def jlc_class(cat, sub, desc):
    t = f"{cat} {sub} {desc}".lower()
    if "motor driver" in t or "brushed dc" in t or "h-bridge" in t or "h bridge" in t or "full bridge" in t:
        return "hbridge"
    if "low drop" in t or "ldo" in t or "linear voltage regulator" in t or "linear regulator" in t:
        return "ldo_fixed"
    if ("dc-dc" in t or "switching regulator" in t or "buck" in t) and "boost" not in t.split("buck")[0][-20:]:
        return "buck_sync"
    if "imu" in t or "accelerometer" in t or "gyroscope" in t or "attitude" in t or "motion sensor" in t:
        return "imu6"
    return None


def fetch(tab):
    labels = tab.setdefault("labels", {})
    for cls, parts in tab["classes"].items():
        for part, rx in parts.items():
            if part in labels:
                continue
            q = QUERY.get(part, part)
            try:
                rows = jlc_parts.query(q, page_size=20)
            except Exception as e:
                labels[part] = {"table": cls, "class": None, "source": "jlc", "error": str(e)[:80]}
                continue
            r = re.compile(rx, re.I)
            hit = [x for x in rows if r.search(x.get("componentModelEn") or "")]
            if not hit:
                labels[part] = {"table": cls, "class": None, "source": "jlc", "category": None, "n_rows": len(rows)}
            else:
                x = hit[0]
                cat, sub = x.get("firstSortName") or "", x.get("secondSortName") or ""
                desc = x.get("describe") or ""
                labels[part] = {"table": cls, "class": jlc_class(cat, sub, desc), "source": "jlc", "model": x.get("componentModelEn"), "category": f"{cat} / {sub}",
                                "describe": desc[:120], "n_rows": len(hit)}
            time.sleep(0.3)
    json.dump(tab, open(TAB, "w"), indent=1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["fetch", "show"])
    ap.add_argument("--read", action="append", default=[], help="part=class:evidence, the reading pass on a miss")
    a = ap.parse_args()
    tab = json.load(open(TAB))
    if a.cmd == "fetch":
        fetch(tab)
    for x in a.read:
        part, rest = x.split("=", 1)
        cls, ev = rest.split(":", 1)
        tab["labels"][part].update({"class": cls, "source": "reading", "evidence": ev})
    if a.read:
        json.dump(tab, open(TAB, "w"), indent=1)
    L = tab.get("labels", {})
    miss = [p for p, v in L.items() if v.get("class") is None]
    bad = [p for p, v in L.items() if v.get("class") and v["class"] != v["table"]]
    print(f"{len(L)} labels: {len(L) - len(miss)} with a class, {len(miss)} misses, {len(bad)} disagree with the table")
    print("misses:", miss)
    for p in bad:
        print(p, L[p]["table"], L[p]["class"], L[p].get("category"), L[p].get("describe", "")[:70])


if __name__ == "__main__":
    main()
