"""Spike #3, C8: plant one bug into a copy of a board and its netlist (KiCad's Python: `pcb py` this file).

  pcb py tools/spikes/spike3/mutate.py BOARD.kicad_pcb NETLIST.xml OUTDIR '{"op": ..., ...}'

The bug goes where it would come from, so both the schematic's connectivity (the kicadxml netlist `pcb check` reads)
and the board (pads, tracks, placement) carry it, as if the design had been regenerated with the mistake:
  swap_pins   {ref, a, b}          the nets on two pins of one part trade places (I2C SDA/SCL on the IMU)
  delete      {ref}                a part is gone from the netlist and the board (a missing pull-up)
  rotate_pins {ref, pins}          every pin in the list takes the next one's net (a connector map off by one)
  track_width {net, width_mm}      the longest track segment on the net is redrawn at width_mm (0.2 mm on a 3 A net)
  move_away   {ref, from, mm}      the part moves so its nearest pad sits `mm` from the pin `from`, inside the outline
  none        {}                   the baseline: the same load and save, nothing changed
Writes OUTDIR/<board>.kicad_pcb and OUTDIR/<netlist>.xml; prints one JSON line describing what changed.
"""
import json, math, os, sys
import xml.etree.ElementTree as ET
import pcbnew

M, F = pcbnew.ToMM, pcbnew.FromMM


def main(board, netlist, out, spec):
    op = json.loads(spec)
    os.makedirs(out, exist_ok=True)
    b = pcbnew.LoadBoard(board)
    tree = ET.parse(netlist)
    root = tree.getroot()
    nets = root.find("nets")
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    did = {"op": op["op"]}

    def node(ref, pin):
        for n in nets:
            for x in n:
                if x.get("ref") == ref and x.get("pin") == pin:
                    return n, x
        raise SystemExit(f"mutate: no netlist node {ref}.{pin}")

    def pads(ref, pin):
        return [p for p in fps[ref].Pads() if p.GetNumber() == pin]

    if op["op"] == "swap_pins":
        (na, xa), (nb, xb) = node(op["ref"], op["a"]), node(op["ref"], op["b"])
        na.remove(xa); nb.remove(xb); na.append(xb); nb.append(xa)
        pa, pb = pads(op["ref"], op["a"]), pads(op["ref"], op["b"])
        ka, kb = pa[0].GetNet(), pb[0].GetNet()
        for p in pa:
            p.SetNet(kb)
        for p in pb:
            p.SetNet(ka)
        did.update(a=f"{op['ref']}.{op['a']} {na.get('name')} -> {nb.get('name')}", b=f"{op['ref']}.{op['b']} {nb.get('name')} -> {na.get('name')}")
    elif op["op"] == "delete":
        for n in nets:
            for x in [x for x in n if x.get("ref") == op["ref"]]:
                n.remove(x)
        comps = root.find("components")
        for c in [c for c in comps if c.get("ref") == op["ref"]]:
            comps.remove(c)
        b.Delete(fps[op["ref"]])
        did.update(deleted=op["ref"])
    elif op["op"] == "rotate_pins":
        pins = op["pins"]
        found = [node(op["ref"], p) for p in pins]
        names = [n.get("name") for n, _ in found]
        knets = [pads(op["ref"], p)[0].GetNet() for p in pins]
        for (n, x), _ in zip(found, pins):
            n.remove(x)
        for i, (_, x) in enumerate(found):
            j = (i + 1) % len(pins)
            nets_by = {n.get("name"): n for n in nets}
            nets_by[names[j]].append(x)
            for p in pads(op["ref"], pins[i]):
                p.SetNet(knets[j])
        did.update(map={f"{op['ref']}.{p}": f"{names[i]} -> {names[(i + 1) % len(pins)]}" for i, p in enumerate(pins)})
    elif op["op"] == "track_width":
        trk = [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetNetname() == op["net"]]
        if not trk:
            raise SystemExit(f"mutate: no track on {op['net']}")
        t = max(trk, key=lambda t: t.GetLength())
        did.update(segment=[round(M(t.GetStart().x), 2), round(M(t.GetStart().y), 2), round(M(t.GetEnd().x), 2), round(M(t.GetEnd().y), 2)],
                   was_mm=round(M(t.GetWidth()), 3), now_mm=op["width_mm"], layer=b.GetLayerName(t.GetLayer()), length_mm=round(M(t.GetLength()), 2))
        t.SetWidth(F(op["width_mm"]))
    elif op["op"] == "move_away":
        ref, (pref, ppin), d = op["ref"], op["from"].split("."), float(op["mm"])
        pin = pads(pref, ppin)[0].GetPosition()
        fp = fps[ref]
        bb = b.GetBoardEdgesBoundingBox()
        x0, y0, x1, y1 = M(bb.GetX()) + 1.5, M(bb.GetY()) + 1.5, M(bb.GetRight()) - 1.5, M(bb.GetBottom()) - 1.5
        cur = fp.GetPosition()
        a0 = math.atan2(M(cur.y - pin.y), M(cur.x - pin.x))
        best = None
        for k in range(36):           # the direction closest to where the part already sits that stays on the board
            for sgn in (1, -1):
                a = a0 + sgn * k * math.pi / 18
                tx, ty = M(pin.x) + d * math.cos(a), M(pin.y) + d * math.sin(a)
                if x0 <= tx <= x1 and y0 <= ty <= y1:
                    best = (tx, ty); break
            if best:
                break
        if best is None:
            raise SystemExit("mutate: no on-board spot at that distance")
        fp.SetPosition(pcbnew.VECTOR2I(F(best[0]), F(best[1])))
        near = min(math.hypot(M(p.GetPosition().x - pin.x), M(p.GetPosition().y - pin.y)) for p in fp.Pads())
        did.update(moved=ref, to=[round(best[0], 2), round(best[1], 2)], nearest_pad_mm=round(near, 2))
    elif op["op"] != "none":
        raise SystemExit(f"mutate: unknown op {op['op']}")
    ob = os.path.join(out, os.path.basename(board))
    pcbnew.SaveBoard(ob, b)
    tree.write(os.path.join(out, os.path.splitext(os.path.basename(board))[0] + ".xml"))
    print(json.dumps(did))


if __name__ == "__main__":
    main(*sys.argv[1:])
