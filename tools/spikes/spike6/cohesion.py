"""Block cohesion of a placement: do parts sit next to parts from their own schematic block?
kNN purity normalised against shuffled labels (0 = blocks mean nothing, 1 = every neighbour same block),
intrusion = share of parts inside another block's bounding box."""
import re, sys, json, glob, os, random, statistics as st
SPLIT = re.compile(r'\n[\t ]{1,2}\((?:footprint|module) ')
SKIP = re.compile(r'^(H|MH|TP|FID|FD|G|LOGO|REF|NT|JP|SJ|#)')
def parse(p):
    t = open(p, errors="ignore").read()
    out = []
    for b in SPLIT.split(t)[1:]:
        m = re.search(r'\(at ([-\d.]+) ([-\d.]+)', b[:1500])
        r = re.search(r'\(property "Reference" "([^"]+)"', b) or re.search(r'\(fp_text reference "?([^"\s]+)', b)
        if not (m and r): continue
        z = re.search(r'\(property "Path" "([^"]+)"', b)
        if z:
            k = z.group(1).rsplit(".", 1)[0] if "." in z.group(1) else ""
        else:
            q = re.search(r'\(path "([^"]*)"', b)
            s = q.group(1).strip("/").split("/") if q else []
            k = "/".join(s[:-1])
        out.append((r.group(1), float(m.group(1)), float(m.group(2)), k))
    return out
def knn(pts, k=3):
    nb = []
    for i, a in enumerate(pts):
        d = sorted((((a[1]-b[1])**2+(a[2]-b[2])**2), j) for j, b in enumerate(pts) if j != i)
        nb.append([j for _, j in d[:k]])
    return nb
def purity(lab, nb):
    return sum(lab[j] == lab[i] for i, n in enumerate(nb) for j in n) / sum(len(n) for n in nb)
def measure(p, k=3, n=200, minparts=20):
    pts = [x for x in parse(p) if not SKIP.match(x[0])]
    c = {}
    for x in pts: c[x[3]] = c.get(x[3], 0) + 1
    keep = {b for b, v in c.items() if b and v >= 3}
    if len(keep) < 2: return None
    pts = [x for x in pts if x[3] in keep]
    if len(pts) < minparts: return None
    if len({(x[1], x[2]) for x in pts}) < 0.8 * len(pts): return None   # unplaced pile
    lab = [x[3] for x in pts]
    nb = knn(pts, k)
    o = purity(lab, nb)
    rng = random.Random(0); s = lab[:]; ns = []
    for _ in range(n):
        rng.shuffle(s); ns.append(purity(s, nb))
    nu = st.mean(ns)
    bx = {b: (min(x[1] for x in pts if x[3]==b), max(x[1] for x in pts if x[3]==b),
              min(x[2] for x in pts if x[3]==b), max(x[2] for x in pts if x[3]==b)) for b in keep}
    intr = sum(any(b != x[3] and v[0] < x[1] < v[1] and v[2] < x[2] < v[3] for b, v in bx.items()) for x in pts) / len(pts)
    return dict(parts=len(pts), blocks=len(keep), purity=round(o,3), null=round(nu,3),
                norm=round((o-nu)/(1-nu),3), intr=round(intr,3))
if __name__ == "__main__":
    R = os.path.expanduser("~/code-stuff/alex-pcb-runs")
    print("board parts blocks purity null norm intrusion")
    for n, p in [("sonnet-a1", f"{R}/rung2-zener-a1-sonnet"), ("opus-a1", f"{R}/rung2-zener-a1-opus"),
                 ("fable-a1", f"{R}/rung2-zener-a1-fable"), ("opus-a2", f"{R}/rung2-zener-a2-opus"),
                 ("plink-human", "/tmp/pcb-ref/motorgo-plink-hardware"), ("pace-human", "/tmp/pcb-ref/pace-racer-hardware")]:
        for f in glob.glob(p + "/**/*.kicad_pcb", recursive=True):
            if any(s in f for s in ("/fab/", "/regen-check", "/scratch", "backup", "/review", "-backups")): continue
            r = measure(f, minparts=10)
            print(n, os.path.relpath(f, p)[:40], r)
    files = []
    for rt in ("/tmp/spike2-corpus", "/tmp/spike5-corpus"):
        files += glob.glob(rt + "/**/*.kicad_pcb", recursive=True)
    seen, rows = set(), []
    for f in files:
        try: pts = parse(f)
        except Exception: continue
        key = tuple(sorted((a, b, c) for a, b, c, _ in pts))
        if key in seen: continue
        seen.add(key)
        try: r = measure(f)
        except Exception: r = None
        if r: rows.append(r)
    json.dump(rows, open("/tmp/spike6/corpus.json", "w"))
    print("corpus files", len(files), "unique", len(seen), "with >=2 blocks, >=20 parts", len(rows))
    v = sorted(r["norm"] for r in rows); w = sorted(r["intr"] for r in rows)
    q = lambda a, f: a[int(f*(len(a)-1))]
    print("norm p10/25/50/75/90", [q(v, f) for f in (.1,.25,.5,.75,.9)])
    print("intrusion p10/25/50/75/90", [q(w, f) for f in (.1,.25,.5,.75,.9)])
