#!/usr/bin/env python3
"""Spike 2 corpus scanner over the Hugging Face dataset bshada/open-schematics (939 parquet shards, one schematic per row).

The rows are untrusted data: everything downloaded stays under --work (default /tmp/spike2-corpus), nothing in it is
executed, and the committed index holds hits only (no file contents).

  PY=/tmp/spike2-venv/bin/python     # a venv with pyarrow and huggingface_hub (uv pip install pyarrow huggingface_hub)
  $PY -I tools/corpus/scan.py index  [--shards 0:939] [--jobs 6]     # pass 1: name, schematic, extensions; hits -> index
  $PY -I tools/corpus/scan.py boards [--parts AMS1117-3.3,LSM6DS3]   # pass 2: pcb_files of the shards with hits
  python3 -I tools/corpus/scan.py licences                         # one GraphQL query per 50 repos: SPDX id per hit
  python3 -I tools/corpus/scan.py summary
  $PY -I tools/corpus/scan.py index --classes --work /tmp/spike5-corpus/kicad   # spike 5: the same pass over the sibling
                                                                     # parts of tools/bench/data/class-table.json, into
                                                                     # corpus-class-index.jsonl, not PART_RX or corpus-index

Pass 1 reads three small columns per shard (about 2 MB of the shard's 80 to 400 MB; the boards and renders are the rest)
and finds placed symbols by lib_id or Value (v6+ s-expression schematics: the instances after `lib_symbols`; legacy
`.sch`: `$Comp` blocks). Stop rule: every common part at `--target` projects or every shard read. The schematic text of
each hit is kept under WORK/sch/ for the netlist pass. Pass 2 reads the `pcb_files` column of the shards whose hits need a
board and keeps the board whose text names the part and its references (WORK/pcb/).
"""
from __future__ import annotations

import argparse, concurrent.futures as cf, json, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "tools/bench/data/corpus-index.jsonl"
DATASET = "datasets/bshada/open-schematics/data"
N_SHARDS = 939
# part -> regex on the lib_id name or the Value (shared with pcbcheck's refstat kind). The variant matched is recorded.
sys.path.insert(0, str(ROOT / "skills/kicad-design/scripts"))
from pcbrefstat import PART_RX as PARTS  # noqa: E402
COMMON = ["AMS1117-3.3", "LSM6DS3", "ESP32-WROOM-32", "ESP32-S3-WROOM-1"]
RX = {p: re.compile(r, re.I) for p, r in PARTS.items()}


def use_classes():
    """Spike 5: point the scanner at the class table. Part names stay unique across classes; `class` joins each row later."""
    global INDEX, PARTS, RX, COMMON, IC_VALUES
    tab = json.load(open(ROOT / "tools/bench/data/class-table.json"))["classes"]
    PARTS = {p: r for c in tab.values() for p, r in c.items()}
    RX = {p: re.compile(r, re.I) for p, r in PARTS.items()}
    INDEX = ROOT / "tools/bench/data/corpus-class-index.jsonl"
    COMMON = []
    IC_VALUES = {}


IC_VALUES = None    # class mode: distinct IC symbol names and values, for the misses pass (counts only, kept under --work)


def sexp_end(text: str, start: int) -> int:
    depth, in_str, j, n = 0, False, start, len(text)
    while j < n:
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
                return j + 1
        j += 1
    return n


def file_kind(text: str):
    head = text[:400]
    m = re.search(r"\(kicad_sch\s*\(version\s+(\d+)\)", head)
    if m:
        g = re.search(r'\(generator_version\s+"?([\d.]+)', head)
        return "kicad_sch", int(m.group(1)), g.group(1) if g else None
    m = re.search(r"EESchema Schematic File Version (\d+)", head)
    if m:
        return "sch_legacy", int(m.group(1)), None
    return "other", None, None


def placed_symbols(text: str, kind: str):
    """[(ref, lib_id, value)] of the placed symbols."""
    out = []
    if kind == "kicad_sch":
        i = text.find("(lib_symbols")
        body = text[sexp_end(text, i):] if i >= 0 else text
        for m in re.finditer(r"\(symbol\s*\(lib_id\s+\"([^\"]+)\"", body):
            end = sexp_end(body, m.start())
            blk = body[m.start():end]
            ref = re.search(r'\(property\s+"Reference"\s+"([^"]*)"', blk)
            val = re.search(r'\(property\s+"Value"\s+"([^"]*)"', blk)
            out.append((ref.group(1) if ref else "?", m.group(1), val.group(1) if val else ""))
    elif kind == "sch_legacy":
        for m in re.finditer(r"\$Comp\s*\nL\s+(\S+)\s+(\S+)(.*?)\$EndComp", text, re.S):
            lib, ref, rest = m.groups()
            v = re.search(r'\nF\s*1\s+"([^"]*)"', rest)
            out.append((ref, lib, v.group(1) if v else ""))
    return out


def match_parts(syms):
    hits = {}
    for ref, lib, val in syms:
        if ref.startswith("#"):
            continue
        name = lib.split(":")[-1]
        for p, rx in RX.items():
            m = rx.search(name) or rx.search(val)
            if m:
                h = hits.setdefault(p, {"refs": [], "variants": set(), "lib_ids": set()})
                if ref not in h["refs"]:
                    h["refs"].append(ref)
                h["variants"].add(m.group(0).upper())
                h["lib_ids"].add(lib)
    return hits


def hf_open(path: str):
    from huggingface_hub import HfFileSystem
    return HfFileSystem().open(path, "rb", block_size=8 << 20)


def read_columns(shard: int, cols, tries=6):
    import pyarrow.parquet as pq
    path = f"{DATASET}/train-{shard:05d}.parquet"
    err = None
    for k in range(tries):
        try:
            with hf_open(path) as f:
                return pq.ParquetFile(f).read(columns=cols).to_pylist()
        except Exception as e:  # 429 and transient HTTP: back off
            err = e
            time.sleep(min(60, 5 * 2 ** k))
    raise RuntimeError(f"shard {shard}: {err}")


def scan_shard(shard: int, work: Path):
    rows = read_columns(shard, ["name", "schematic", "extensions_used"])
    out, kinds = [], {}
    for i, r in enumerate(rows):
        text = r.get("schematic") or ""
        kind, ver, gen = file_kind(text)
        kinds[kind] = kinds.get(kind, 0) + 1
        if kind == "other":
            continue
        syms = placed_symbols(text, kind)
        if IC_VALUES is not None:
            for ref, lib, val in syms:
                if re.match(r"(U|IC)\d", ref):
                    for t in {lib.split(":")[-1], val}:
                        IC_VALUES[t] = IC_VALUES.get(t, 0) + 1
        hits = match_parts(syms)
        if not hits:
            continue
        ext = r.get("extensions_used") or []
        key = f"{shard:05d}-{i:03d}"
        sch_path = work / "sch" / f"{key}.{'kicad_sch' if kind == 'kicad_sch' else 'sch'}"
        sch_path.parent.mkdir(parents=True, exist_ok=True)
        sch_path.write_text(text)
        for p, h in hits.items():
            out.append({"key": key, "part": p, "repo": r.get("name"), "shard": shard, "row": i,
                        "file": f"train-{shard:05d}.parquet row {i} (the dataset records no path)",
                        "sch_format": kind, "sch_version": ver, "generator_version": gen,
                        "n_instances": len(h["refs"]), "refs": h["refs"][:12], "variants": sorted(h["variants"]),
                        "lib_ids": sorted(h["lib_ids"])[:4], "has_pcb_ext": ".kicad_pcb" in ext, "extensions": ext,
                        "board": None, "licence": None})
    return shard, len(rows), kinds, out


def load_index():
    return [json.loads(l) for l in open(INDEX)] if INDEX.exists() else []


def save_index(rows):
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    rows.sort(key=lambda r: (r["shard"], r["row"], r["part"]))
    with open(INDEX, "w") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")


def cmd_index(a):
    work = Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    state_p = work / "state.json"
    state = json.load(open(state_p)) if state_p.exists() else {"done": [], "rows": 0, "kinds": {}, "seconds": 0.0, "errors": []}
    lo, hi = (int(x) for x in a.shards.split(":"))
    done = set(state["done"])
    todo = [s for s in range(lo, hi) if s not in done]
    rows = load_index()
    t0 = time.time()

    def projects(part):
        return len({r["key"] for r in rows if r["part"] == part})

    with cf.ThreadPoolExecutor(a.jobs) as ex:
        futs = {ex.submit(scan_shard, s, work): s for s in todo}
        for n, fu in enumerate(cf.as_completed(futs)):
            try:
                shard, nrows, kinds, hits = fu.result()
            except Exception as e:
                state.setdefault("errors", []).append(str(e)[:200])
                print("ERR", e, file=sys.stderr); continue
            rows.extend(hits)
            state["done"].append(shard); state["rows"] += nrows
            for k, v in kinds.items():
                state["kinds"][k] = state["kinds"].get(k, 0) + v
            if n % 20 == 0:
                state["seconds"] += time.time() - t0; t0 = time.time()
                json.dump(state, open(state_p, "w")); save_index(rows)
                if IC_VALUES is not None:
                    json.dump(dict(IC_VALUES), open(work / f"ic-values-{lo}.json", "w"))
                print(f"{len(state['done'])} shards, {state['rows']} rows: " + ", ".join(f"{p} {projects(p)}" for p in PARTS), flush=True)
            if COMMON and all(projects(p) >= a.target for p in COMMON):
                print("stop rule: every common part at target"); ex.shutdown(cancel_futures=True); break
    state["seconds"] += time.time() - t0
    json.dump(state, open(state_p, "w")); save_index(rows)
    if IC_VALUES is not None:
        json.dump(dict(IC_VALUES), open(work / f"ic-values-{lo}.json", "w"))
    print(f"done: {len(state['done'])} shards, {state['rows']} rows, {state['seconds']:.0f} s; kinds {state['kinds']}")


PCB_HEAD = re.compile(r"\(kicad_pcb\s*\(version\s+(\d+)\)")


def pick_board(pcbs, part, refs):
    best = None
    for j, t in enumerate(pcbs or []):
        if not t:
            continue
        m = PCB_HEAD.search(t[:300])
        if not m:
            continue
        score = 1 if RX[part].search(t) else 0
        for ref in refs:
            if re.search(r'(\(property\s+"Reference"|\(fp_text\s+reference)\s+"?%s"?[\s)]' % re.escape(ref), t):
                score += 1
        if score >= 2 and (best is None or score > best[0]):
            best = (score, j, int(m.group(1)), t)
    return best


def cmd_boards(a):
    work = Path(a.work)
    rows = load_index()
    parts = sorted({r["part"] for r in rows}) if a.parts == "all" else a.parts.split(",")
    caps = {p: (10 ** 9 if p in ("LSM6DS3", "DRV8874", "TPS54620") or a.cap <= 0 else a.cap) for p in parts}
    want, seen = {}, {p: 0 for p in parts}
    for r in rows:
        if r["part"] in parts and r["has_pcb_ext"] and seen[r["part"]] < caps[r["part"]]:
            seen[r["part"]] += 1
            if r["board"] is None:
                want.setdefault(r["shard"], []).append(r)
    print(f"boards: {len(want)} shards for {sum(len(v) for v in want.values())} hits", flush=True)
    t0 = time.time()

    def one(shard):
        data = read_columns(shard, ["pcb_files"])
        res = []
        for r in want[shard]:
            pcbs = data[r["row"]]["pcb_files"]
            b = pick_board(pcbs, r["part"], r["refs"])
            if b is None:
                res.append((r, {"match": False, "n_pcb_files": len(pcbs or [])}))
                continue
            score, j, ver, text = b
            p = work / "pcb" / f"{r['key']}.kicad_pcb"
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.exists():
                p.write_text(text)
            res.append((r, {"match": True, "n_pcb_files": len(pcbs), "pcb_index": j, "pcb_version": ver, "score": score}))
        return res

    done = 0
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        for fu in cf.as_completed([ex.submit(one, s) for s in want]):
            try:
                for r, b in fu.result():
                    r["board"] = b
            except Exception as e:
                print("ERR", e, file=sys.stderr)
            done += 1
            if done % 10 == 0:
                save_index(rows); print(f"{done}/{len(want)} shards, {time.time() - t0:.0f} s", flush=True)
    save_index(rows)
    print(f"boards done in {time.time() - t0:.0f} s")


def cmd_licences(a):
    import subprocess
    rows = load_index()
    cache_p = Path(a.work) / "licences.json"
    got = json.load(open(cache_p)) if cache_p.exists() else {}
    repos = sorted({r["repo"] for r in rows if r["repo"] and "/" in r["repo"]} - set(got))
    for k in range(0, len(repos), 50):
        chunk = repos[k:k + 50]
        q = "query {" + " ".join(
            f'r{i}: repository(owner: {json.dumps(o)}, name: {json.dumps(n)}) {{ licenseInfo {{ spdxId }} }}'
            for i, (o, n) in enumerate(x.split("/", 1) for x in chunk)) + "}"
        p = subprocess.run(["gh", "api", "graphql", "-f", f"query={q}"], capture_output=True, text=True)
        try:
            d = json.loads(p.stdout).get("data") or {}
        except ValueError:
            d = {}
        for i, name in enumerate(chunk):
            v = d.get(f"r{i}")
            got[name] = "NOT_FOUND" if v is None else ((v.get("licenseInfo") or {}).get("spdxId") or "NONE")
    json.dump(got, open(cache_p, "w"), indent=0)
    if a.no_apply:
        print(f"licences: {len(got)} repos cached in {cache_p}"); return
    rows = load_index()
    for r in rows:
        if r["repo"] in got:
            r["licence"] = got[r["repo"]]
    save_index(rows)
    print(f"licences: {len(got)} repos")


def cmd_summary(a):
    rows = load_index()
    work = Path(a.work)
    st = json.load(open(work / "state.json")) if (work / "state.json").exists() else {}
    print(f"shards read {len(st.get('done', []))}/{N_SHARDS}, rows {st.get('rows')}, {st.get('seconds', 0):.0f} s, kinds {st.get('kinds')}")
    for p in PARTS:
        rs = [r for r in rows if r["part"] == p]
        print(f"{p:18} projects {len({r['key'] for r in rs}):5} repos {len({r['repo'] for r in rs}):5} placed {sum(r['n_instances'] for r in rs):5} "
              f"with .kicad_pcb ext {sum(r['has_pcb_ext'] for r in rs):5} board matched {sum(bool(r['board'] and r['board'].get('match')) for r in rs):5}")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["index", "boards", "licences", "summary"])
    ap.add_argument("--work", default="/tmp/spike2-corpus")
    ap.add_argument("--shards", default=f"0:{N_SHARDS}")
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--target", type=int, default=200)
    ap.add_argument("--parts", default="AMS1117-3.3,LSM6DS3,ESP32-WROOM-32,ESP32-S3-WROOM-1")
    ap.add_argument("--classes", action="store_true", help="spike 5: the class table and corpus-class-index.jsonl (--parts all, --cap 0: no cap)")
    ap.add_argument("--no-apply", action="store_true", help="licences: query and cache only (another pass is writing the index)")
    ap.add_argument("--cap", type=int, default=300, help="board-bearing hits per common part to fetch boards for")
    a = ap.parse_args(argv)
    if a.classes:
        use_classes()
    {"index": cmd_index, "boards": cmd_boards, "licences": cmd_licences, "summary": cmd_summary}[a.mode](a)


if __name__ == "__main__":
    main(sys.argv[1:])
