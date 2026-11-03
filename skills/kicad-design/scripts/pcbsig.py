"""pcb signals checks.json [--netlist x.xml] [--json] [--md]

Signal classes by knee frequency (SIG-1). The `signals` block in checks.json records, per net, what the designer
knows and the tools cannot measure: the driver pin, the rise time of its edge with the source of that number (a
datasheet line or an explicit assumption), the parts on the board that slow the edge, and whether the net is a victim
(analog, high impedance: it wants distance from aggressors more than ground). This module computes the rest:

  knee_mhz = 500 / t_rise_ns            (f_knee ~= 0.5 / t_rise, the DRIVER's edge, not the clock or PWM rate)
  bucket   1  < 1 MHz     best effort over ground; detours fine
           2  1-50 MHz    over ground, short gap crossings penalised, spacing from aggressors
           3  50-500 MHz  hard: 0 mm off ground, no plane-split or edge crossings, a GND via beside every layer change
           4  >= 500 MHz  hard plus impedance, pairs, length match
           P  rail        a net in `rails` (or `"rail": true`): judged by irdrop and currents, not by knee
  t_rise_ns null = DC or slower than the microsecond scale: bucket 1.

Entry: {"driver": "U1.11 (TPS54620 PH)", "t_rise_ns": 3, "source": "assumption: ...", "slowed_by": ["R7 1k series"],
        "victim": false, "note": "..."}; a plain string value is a note on a net the designer chose not to classify.
Nets in the netlist that are neither GND, a rail, unconnected nor in `signals` are reported as unclassified (so the
coverage is explicit; a judge treats them as bucket 1). Exit 1 if any signal entry names a net the netlist lacks.
"""
import argparse, json, os, sys
import xml.etree.ElementTree as ET

BUCKETS = [(1.0, 1), (50.0, 2), (500.0, 3), (float("inf"), 4)]
LABEL = {1: "slow", 2: "mid", 3: "fast", 4: "hs", "P": "rail"}


def knee_mhz(t_rise_ns):
    if not t_rise_ns:
        return 0.0
    return 500.0 / float(t_rise_ns)


def bucket_of(knee):
    for hi, b in BUCKETS:
        if knee < hi:
            return b
    return 4


def netlist_nets(path):
    """net name -> [(ref, pin, pinfunction)] from a kicadxml netlist."""
    r = ET.parse(path).getroot()
    out = {}
    for n in r.find("nets"):
        out[n.get("name")] = [(nd.get("ref"), nd.get("pin"), nd.get("pinfunction") or "") for nd in n.findall("node")]
    return out


def classify(cfg, nets=None):
    """Rows for every net: name, bucket, knee_mhz, t_rise_ns, driver, source, slowed_by, victim, note, status.
    `nets` (from netlist_nets) adds coverage: unclassified nets and entries the netlist lacks."""
    sig = cfg.get("signals") or {}
    rails = set((cfg.get("rails") or {}).keys())
    gnd = {"GND"} | {k for k, v in (cfg.get("rails") or {}).items() if not v}
    rows = []
    for name, e in sig.items():
        if name.startswith("_"):
            continue
        if not isinstance(e, dict):
            rows.append({"net": name, "bucket": 1, "knee_mhz": 0.0, "t_rise_ns": None, "driver": "", "source": "",
                         "slowed_by": [], "victim": False, "note": str(e), "status": "unclassified"})
            continue
        if e.get("rail") or name in rails:
            rows.append({"net": name, "bucket": "P", "knee_mhz": 0.0, "t_rise_ns": None, "driver": e.get("driver", ""),
                         "source": e.get("source", ""), "slowed_by": [], "victim": False, "note": e.get("note", ""),
                         "status": "ok" if nets is None or name in nets else "missing"})
            continue
        t = e.get("t_rise_ns")
        k = knee_mhz(t)
        rows.append({"net": name, "bucket": bucket_of(k), "knee_mhz": round(k, 3), "t_rise_ns": t, "driver": e.get("driver", ""),
                     "source": e.get("source", ""), "slowed_by": list(e.get("slowed_by") or []), "victim": bool(e.get("victim")),
                     "note": e.get("note", ""), "status": "ok" if nets is None or name in nets else "missing"})
    seen = {r["net"] for r in rows}
    if nets is not None:
        for name, nodes in nets.items():
            if name in seen or name in gnd or name.startswith("unconnected-"):
                continue
            if name in rails:
                rows.append({"net": name, "bucket": "P", "knee_mhz": 0.0, "t_rise_ns": None, "driver": "", "source": "rails block",
                             "slowed_by": [], "victim": False, "note": "", "status": "ok"})
            else:
                rows.append({"net": name, "bucket": 1, "knee_mhz": 0.0, "t_rise_ns": None, "driver": "", "source": "",
                             "slowed_by": [], "victim": False, "note": ", ".join(f"{r}.{p}" for r, p, _ in nodes[:6]),
                             "status": "unclassified"})
    order = {4: 0, 3: 1, 2: 2, 1: 3, "P": 4}
    rows.sort(key=lambda r: (order[r["bucket"]], not r["victim"], r["net"].lower()))
    return rows


def buckets(cfg, nets=None):
    """net -> bucket (1..4 or 'P'); unclassified nets are bucket 1. What the judges read."""
    return {r["net"]: r["bucket"] for r in classify(cfg, nets)}


def victims(cfg):
    return {n for n, e in (cfg.get("signals") or {}).items() if isinstance(e, dict) and e.get("victim")}


def fmt_t(t):
    if t is None:
        return "dc"
    t = float(t)
    if t >= 1000:
        return f"{t / 1000:g} us"
    return f"{t:g} ns"


def fmt_knee(k):
    if not k:
        return "-"
    if k < 1:
        return f"{k * 1000:.3g} kHz"
    return f"{k:.3g} MHz"


def table_md(rows):
    out = ["| net | bucket | knee | t_rise | victim | driver | source | slowed by |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        b = r["bucket"]
        tag = f"{b} {LABEL[b]}" if b != "P" else "P rail"
        if r["status"] == "unclassified":
            tag = "? (1)"
        if r["status"] == "missing":
            tag += " MISSING"
        out.append(f"| {r['net']} | {tag} | {fmt_knee(r['knee_mhz'])} | {fmt_t(r['t_rise_ns'])} | {'yes' if r['victim'] else ''} | "
                   f"{r['driver']} | {r['source'] or r['note']} | {', '.join(r['slowed_by'])} |")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--netlist")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--md", action="store_true")
    a = ap.parse_args()
    cfg = json.load(open(a.config))
    nets = netlist_nets(a.netlist) if a.netlist else None
    rows = classify(cfg, nets)
    if a.json:
        print(json.dumps(rows, indent=1))
    else:
        if a.md:
            print(table_md(rows))
        else:
            w = max(len(r["net"]) for r in rows) if rows else 8
            for r in rows:
                b = r["bucket"]
                tag = ("? " if r["status"] == "unclassified" else f"{b} ") + (LABEL[b] if b != "P" else "rail")
                print(f"{r['net']:{w}s}  {tag:8s} {fmt_knee(r['knee_mhz']):>9s}  {fmt_t(r['t_rise_ns']):>7s}  {'victim' if r['victim'] else '      '}  "
                      f"{r['driver']}" + (f"  [{r['status']}]" if r["status"] != "ok" else ""))
        n = {b: sum(1 for r in rows if r["bucket"] == b and r["status"] == "ok") for b in (4, 3, 2, 1, "P")}
        unc = [r["net"] for r in rows if r["status"] == "unclassified"]
        miss = [r["net"] for r in rows if r["status"] == "missing"]
        print(f"\nsignals: bucket 4: {n[4]}, 3: {n[3]}, 2: {n[2]}, 1: {n[1]}, rails: {n['P']}, victims: {sum(1 for r in rows if r['victim'])}"
              + (f"; unclassified (treated as 1): {', '.join(unc)}" if unc else "") + (f"; NOT IN NETLIST: {', '.join(miss)}" if miss else ""))
    sys.exit(1 if any(r["status"] == "missing" for r in rows) else 0)


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------------------------------- plan ranking (SIG-4)
WEIGHTS = {"mid": 1.0, "slow": 0.2, "exposure": 1.0, "vin": 0.1, "currents": 5.0, "vias": 0.05}
"""Cost of a routed plan = bucket-2 mm off ground x mid + (bucket-1 and rail mm off ground) x slow + same-layer exposure
(victims x3 already) x exposure + rail loss mW x vin + currents fails x currents + vias x vias. 10 mW of VIN loss
weighs as much as 1 mm of a bucket-2 net off ground."""


def plan_cost(r, w=None):
    w = w or WEIGHTS
    slow = sum(v for k, v in (r.get("off_by_bucket") or {}).items() if k in ("1", "P"))
    return (r.get("mid_off_mm", 0) * w["mid"] + slow * w["slow"] + r.get("exposure_mm", 0) * w["exposure"] + (r.get("vin_mW") or 0) * w["vin"]
            + len(r.get("currents_fails") or []) * w["currents"] + (r.get("vias") or 0) * w["vias"])


def plan_rank(rows, rules, w=None, fast_max=0.0, return_via_hard=False, vin_slack=1.1):
    """Hard limits: clean, bucket 3/4 off ground at most fast_max mm, currents fails and rail loss no worse than the
    `rules` plan (+10 %), optionally every bucket-3 via with a return via. Then the lowest plan_cost. Returns
    (passing rows sorted, failing rows with the reason)."""
    ok, bad = [], []
    for r in rows:
        why = []
        if not r.get("clean"):
            why.append("not clean")
        if r.get("fast_off_mm", 0) > fast_max + 1e-6:
            why.append(f"bucket-3 off ground {r['fast_off_mm']} mm > {fast_max}")
        if rules and len(r.get("currents_fails") or []) > len(rules.get("currents_fails") or []):
            why.append(f"currents fails {len(r['currents_fails'])} > rules {len(rules['currents_fails'])}")
        if rules and (r.get("vin_mW") or 0) > (rules.get("vin_mW") or 0) * vin_slack + 1e-6:
            why.append(f"rail loss {r['vin_mW']} mW > rules {rules['vin_mW']} + {round((vin_slack - 1) * 100)} %")
        if return_via_hard and r.get("return_via_bad", 0):
            why.append(f"{r['return_via_bad']} bucket-3 vias without a return via")
        (bad if why else ok).append((r, why) if why else r)
    return sorted(ok, key=lambda r: plan_cost(r, w)), bad
