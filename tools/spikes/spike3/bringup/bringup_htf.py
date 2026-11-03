#!/usr/bin/env python3
"""Spike #3, C2: a board's BRINGUP.md as an OpenHTF test, run against a simulated instrument (skeleton, nothing ordered).

  uv run --no-project --with openhtf python3 -I tools/spikes/spike3/bringup/bringup_htf.py BRINGUP.md --out DIR
      [--parse-only] [--fault NAME=VALUE ...] [--dut ID]

parse(): the numbered steps of BRINGUP.md into (step, measurement, expected, tolerance) rows: `X = 3.3 V +/-0.1 V`,
`2.2 kohm +/-5%`, `4.98 V +/- 2 %`, `> 10 kOhm`, `below 1 ohm`, `10-40 mA`, `expected **0x6A**`, `at **0x6B**`.
Prose a regex cannot turn into a number (visual checks, "motor turns") stays as an operator prompt: the step is listed
with no measurement and the run marks it `manual`. run(): one OpenHTF phase per step, one `htf.Measurement` per row
with `in_range` or `equals`, readings from the `Instrument` plug. `SimInstrument` answers every measurement with a value
inside its limits (nominal plus noise, deterministic seed), or the value a `--fault` gives it, so the whole chain runs
with no hardware; a real plug (DMM over SCPI, an ESP32 doing the I2C reads) replaces it. Output: OpenHTF's JSON record
(every reading, limit and outcome) and rows.json (the parse) in --out.
"""
import json, random, re, sys
from pathlib import Path

UNIT = {"ohm": ("ohm", 1), "kohm": ("ohm", 1e3), "mohm": ("ohm", 1e6), "v": ("V", 1), "mv": ("V", 1e-3), "a": ("A", 1),
        "ma": ("A", 1e-3), "ua": ("A", 1e-6), "hz": ("Hz", 1), "khz": ("Hz", 1e3), "mhz": ("Hz", 1e6), "mg": ("mg", 1),
        "dps": ("dps", 1), "degc": ("degC", 1), "ms": ("s", 1e-3), "us": ("s", 1e-6)}
U = r"(kohm|mohm|ohm|kHz|MHz|Hz|mV|V|mA|uA|A|mg|dps|degC|ms|us)\b"
NUM = r"([+-]?\d+(?:\.\d+)?)"
PATTERNS = [   # (kind, regex): the subject is the text before the match in the same clause
    ("drop", re.compile(NUM + r"\s*" + U + r"\s*minus\s*<\s*" + NUM + r"\s*" + U, re.I)),   # "12 V minus < 0.05 V"
    ("tol", re.compile(NUM + r"\s*" + U + r"\s*\+/-\s*" + NUM + r"\s*(%|" + U[1:-3] + r")?", re.I)),
    ("zero", re.compile(r"within\s*\+/-\s*" + NUM + r"\s*" + U, re.I)),
    ("range", re.compile(NUM + r"\s*-\s*" + NUM + r"\s*" + U, re.I)),
    ("min", re.compile(r"(?:>=?|above|at least)\s*" + NUM + r"\s*" + U, re.I)),
    ("max", re.compile(r"(?:<=?|below|under)\s*" + NUM + r"\s*" + U, re.I)),
    ("eq", re.compile(r"(?:expected|at)\s+\*\*(0x[0-9A-Fa-f]+)\*\*", re.I)),
]


def si(v, u):
    base, k = UNIT[u.lower()]
    return float(v) * k, base


def parse(md):
    text = Path(md).read_text()
    steps = []
    for m in re.finditer(r"^(\d+)\.\s+\*\*(.+?)\*\*(.*?)(?=^\d+\.\s+\*\*|\Z)", text, re.S | re.M):
        n, title, body = int(m.group(1)), m.group(2).strip(" ."), " ".join(m.group(3).split())
        rows, taken = [], []
        for kind, rx in PATTERNS:
            for h in rx.finditer(body):
                if any(a < h.end() and h.start() < b for a, b in taken):
                    continue
                taken.append((h.start(), h.end()))
                clause = re.split(r"[.;:(]\s", body[:h.start()])[-1].strip()
                what = " ".join(clause.split()[-7:]) or title
                r = {"step": n, "title": title, "what": what, "text": body[max(0, h.start() - 40):h.end() + 5].strip(), "kind": kind}
                g = h.groups()
                if kind == "drop":
                    v, base = si(g[0], g[1]); d, _ = si(g[2], g[3]); r.update(expected=v, lo=v - d, hi=v, unit=base)
                elif kind == "zero":   # "within +/-100 mg of zero", "each axis within +/-10 dps"
                    t, base = si(g[0], g[1]); r.update(expected=0.0, lo=-t, hi=t, unit=base)
                elif kind == "tol":
                    v, base = si(g[0], g[1])
                    t = float(g[2]) / 100 * abs(v) if (g[3] or "").strip() == "%" else si(g[2], g[3] or g[1])[0]
                    r.update(expected=v, lo=v - t, hi=v + t, unit=base)
                elif kind == "range":
                    lo, base = si(g[0], g[2]); hi, _ = si(g[1], g[2])
                    r.update(expected=(lo + hi) / 2, lo=lo, hi=hi, unit=base)
                elif kind == "min":
                    v, base = si(g[0], g[1]); r.update(expected=None, lo=v, hi=None, unit=base)
                elif kind == "max":
                    v, base = si(g[0], g[1]); r.update(expected=None, lo=None, hi=v, unit=base)
                else:
                    r.update(expected=g[0].lower(), lo=None, hi=None, unit="hex")
                # a sentence that describes the failure ("a short reads below 10 ohm", "above 2 mA ... means a fault")
                # limits the good reading from the other side
                pre = re.split(r"[.;,(]", body[:h.start()])[-1]
                post = re.split(r"[.;,(:]", body[h.end():])[0]
                if kind in ("min", "max") and (re.search(r"\ba short\b", pre, re.I) or re.search(r"\b(means|is) a fault\b", post, re.I)):
                    r["lo"], r["hi"] = r["hi"], r["lo"]
                    r["kind"] = "max" if kind == "min" else "min"
                    r["inverted"] = True
                rows.append(r)
        rows.sort(key=lambda r: body.find(r["text"][:20]))
        for k, r in enumerate(rows):
            r["name"] = f"s{n:02d}_{k + 1}_" + re.sub(r"[^a-z0-9]+", "_", r["what"].lower()).strip("_")[:40]
        steps.append({"step": n, "title": title, "rows": rows, "manual": not rows})
    return steps


class SimInstrument:
    """Answers each measurement inside its limits (or with a --fault value); stands in for the DMM / I2C host plug."""
    FAULTS = {}

    def __init__(self):
        self.rng = random.Random(3)

    def read(self, row):
        if row["name"] in self.FAULTS:
            return self.FAULTS[row["name"]]
        if row["unit"] == "hex":
            return row["expected"]
        lo, hi = row["lo"], row["hi"]
        if lo is not None and hi is not None:
            mid, span = (lo + hi) / 2, (hi - lo) / 2
            return mid + self.rng.uniform(-0.4, 0.4) * span
        if lo is not None:
            return lo * (2.0 + self.rng.random()) if lo > 0 else lo + 1.0
        return hi * (0.2 + 0.3 * self.rng.random())


def run(steps, out, dut, faults):
    import openhtf as htf
    from openhtf.output.callbacks import json_factory
    from openhtf.plugs import BasePlug

    class Instrument(BasePlug):
        def __init__(self):
            self.sim = SimInstrument()

        def read(self, row):
            return self.sim.read(row)

    SimInstrument.FAULTS = faults
    phases = []
    for st in steps:
        meas = []
        for r in st["rows"]:
            m = htf.Measurement(r["name"]).doc(f"{r['what']} ({r['text']})")
            if r["unit"] == "hex":
                m = m.equals(r["expected"])
            else:
                m = m.in_range(minimum=r["lo"], maximum=r["hi"]).with_units(None)
            meas.append(m)

        def phase(test, instrument, st=st):
            if st["manual"]:
                test.logger.info("step %d %s: operator check (no number in BRINGUP.md)", st["step"], st["title"])
            for r in st["rows"]:
                v = instrument.read(r)
                test.measurements[r["name"]] = v
                test.logger.info("step %d %s = %s %s", st["step"], r["name"], v, r["unit"])
        phase.__name__ = f"step_{st['step']:02d}_" + re.sub(r"[^a-z0-9]+", "_", st["title"].lower()).strip("_")
        p = htf.plug(instrument=Instrument)(phase)
        phases.append(htf.measures(*meas)(p) if meas else p)
    test = htf.Test(*phases, test_name=Path(out).name)
    test.add_output_callbacks(json_factory.OutputToJSON(str(Path(out) / "record.json"), indent=1))
    return test.execute(test_start=lambda: dut)


def main(argv):
    md = argv[0]
    out = Path(argv[argv.index("--out") + 1]) if "--out" in argv else Path("/tmp/spike3/bringup")
    out.mkdir(parents=True, exist_ok=True)
    faults = {}
    for i, a in enumerate(argv):
        if a == "--fault":
            k, v = argv[i + 1].split("=")
            faults[k] = v if v.startswith("0x") else float(v)
    steps = parse(md)
    json.dump(steps, open(out / "rows.json", "w"), indent=1)
    n = sum(len(s["rows"]) for s in steps)
    for s in steps:
        print(f"step {s['step']:2} {s['title'][:40]:40} " + ("manual" if s["manual"] else f"{len(s['rows'])} measurements"))
        for r in s["rows"]:
            print(f"     {r['name'][:48]:48} {r['kind']:5} lo {r['lo']} hi {r['hi']} {r['unit']}  <- {r['text'][:60]}")
    print(f"BRINGUP {md}: {len(steps)} steps, {n} measurements, {sum(s['manual'] for s in steps)} manual steps -> {out / 'rows.json'}")
    if "--parse-only" in argv:
        return
    ok = run(steps, str(out), argv[argv.index("--dut") + 1] if "--dut" in argv else "sim-001", faults)
    rec = json.load(open(out / "record.json"))
    rec["station_id"] = "sim-bench"   # OpenHTF records the host name twice; the record is committed
    rec.get("metadata", {}).get("config", {})["station_id"] = "sim-bench"
    json.dump(rec, open(out / "record.json", "w"), indent=1)
    fails = [m for ph in rec["phases"] for m in ph["measurements"].values() if m["outcome"] != "PASS"]
    print(f"OPENHTF outcome {rec['outcome']}, {len(rec['phases'])} phases, "
          f"{sum(len(ph['measurements']) for ph in rec['phases'])} measurements, {len(fails)} not PASS -> {out / 'record.json'}")
    for m in fails:
        print(f"  {m['outcome']} {m['name']} = {m.get('measured_value')} {m.get('validators')}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main(sys.argv[1:])
