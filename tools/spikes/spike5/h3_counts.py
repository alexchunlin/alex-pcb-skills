#!/usr/bin/env python3
"""Spike 5, H3 (dropped under its own null): the counts only, from the per-repo flags the review read through the API.

  python3 -I tools/spikes/spike5/h3_counts.py /tmp/spike5/lit-work/h3.json        # writes h3-counts.json beside this file
  python3 -I tools/spikes/spike5/h3_counts.py --check                             # the committed counts add up
"""
import json, sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "h3-counts.json"
if sys.argv[1:] == ["--check"]:
    d = json.load(open(OUT))
    assert {k: v["strict"] for k, v in d.items()} == {"LSM6DS3": 8, "DRV8874": 1, "AMS1117-3.3": 4}, d
    print("ok")
    sys.exit()
rows = json.load(open(sys.argv[1]))
out = {}
for part in ("LSM6DS3", "DRV8874", "AMS1117-3.3"):
    x = [r for r in rows if r["part"] == part]
    live = [r for r in x if not r.get("gone")]
    f = lambda k: sum(bool(r[k]) for r in live)
    out[part] = {"repos": len(x), "live": len(live), "release": f("rel"), "tag": f("tag"), "gerbers": f("ger"), "bom": f("bom"),
                 "any": sum(bool(r["rel"] or r["tag"] or r["ger"] or r["bom"]) for r in live), "strict": sum(bool((r["rel"] or r["tag"]) and r["ger"]) for r in live)}
json.dump(out, open(OUT, "w"), indent=1)
print(json.dumps(out))
