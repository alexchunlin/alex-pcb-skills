"""KiCadRoutingTools' own net selection and MPS conflict graph, read without routing (spike #4).

Runs under KRT's venv Python (numpy, scipy), not KiCad's: `pcb q BOARD conflicts` and the route bench call it as
  KRT_PY pcbkrt.py nets BOARD                 the nets `route.py BOARD` routes by default ('*'), in KRT's order, as JSON
  KRT_PY pcbkrt.py conflicts BOARD [NET ...]  KRT's MPS ordering with return_extended_info=True: the conflict graph
                                              (MST-segment crossings, layer-filtered, as route.py uses it), rounds, order
Every step is KRT's own function, called with route.py's defaults (net_queries.expand_net_patterns,
routing_common.resolve_net_ids / filter_already_routed / setup_bga_exclusion_zones, net_queries.filter_routable_nets, compute_mps_net_ordering
with mps_unroll on, crossing-layer check on, segment intersection auto). verify_all 30 checks the count against the
"MPS: N nets with K crossing conflicts" line KRT prints when it routes the same board.
"""
import contextlib, io, json, os, sys

KRT_DIR = os.environ.get("KRT_DIR", os.path.join(os.environ.get("PCB_REF", "/tmp/pcb-ref"), "KiCadRoutingTools"))
sys.path.insert(0, os.path.join(KRT_DIR, "py_router"))


def load(board):
    from kicad_parser import parse_kicad_pcb
    with contextlib.redirect_stdout(io.StringIO()):
        return parse_kicad_pcb(board)


def routed_nets(pcb, patterns=None):
    """(name, id) in the order route.py hands them to the ordering strategy."""
    from net_queries import expand_net_patterns, filter_routable_nets
    from routing_common import resolve_net_ids, filter_already_routed
    with contextlib.redirect_stdout(io.StringIO()):
        names = expand_net_patterns(pcb, patterns or ["*"])
        ids = resolve_net_ids(pcb, names)
        # route.py: nets already connected (pads joined through a filled zone) are skipped before ordering; the config
        # argument is only read for its verbose flag
        ids, _ = filter_already_routed(pcb, ids, None, fragment_gate=True)
        return filter_routable_nets(pcb, ids)


def conflicts(board, patterns=None):
    from net_queries import compute_mps_net_ordering
    from routing_common import setup_bga_exclusion_zones
    pcb = load(board)
    net_ids = routed_nets(pcb, patterns)
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        zones = setup_bga_exclusion_zones(pcb, None, None, selected_net_ids=[nid for _, nid in net_ids])
        r = compute_mps_net_ordering(pcb, [nid for _, nid in net_ids], diff_pairs={}, use_boundary_ordering=True,
                                     bga_exclusion_zones=zones, reverse_rounds=False, crossing_layer_check=True,
                                     return_extended_info=True, use_segment_intersection=None)
    name = {nid: nm for nm, nid in net_ids}
    uname = lambda u: "+".join(name.get(n, str(n)) for n in r.unit_to_nets.get(u, [u]))
    edges = sorted({tuple(sorted((uname(a), uname(b)))) for a, bs in r.conflicts.items() for b in bs})
    geo = sorted({tuple(sorted((uname(a), uname(b)))) for a, bs in (r.geometric_conflicts or {}).items() for b in bs})
    deg = {}
    for a, b in edges:
        deg[a] = deg.get(a, 0) + 1
        deg[b] = deg.get(b, 0) + 1
    rounds = {}
    for u, k in r.round_assignments.items():
        rounds.setdefault(k, []).append(uname(u))
    return {"board": board, "nets": len(net_ids), "units": len(r.conflicts), "conflicts": len(edges), "geometric_conflicts": len(geo),
            "edges": [list(e) for e in edges], "degree": dict(sorted(deg.items(), key=lambda kv: (-kv[1], kv[0]))),
            "rounds": r.num_rounds, "late_nets": sorted(n for k, ns in rounds.items() if k > 1 for n in ns),
            "order": [name[n] for n in r.ordered_ids if n in name], "krt_says": [l for l in log.getvalue().splitlines() if l.startswith("MPS")],
            "bipartite": bipartite(edges)}


def bipartite(edges):
    """Two-colourable? (zero vias on two layers in the disk model iff the crossing graph is bipartite; Kajitani 1980)."""
    adj = {}
    for a, b in edges:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    col = {}
    for s in adj:
        if s in col:
            continue
        col[s], stack = 0, [s]
        while stack:
            u = stack.pop()
            for v in adj[u]:
                if v not in col:
                    col[v] = 1 - col[u]
                    stack.append(v)
                elif col[v] == col[u]:
                    return False
    return True


def main():
    a = sys.argv[1:]
    if len(a) < 2 or a[0] not in ("nets", "conflicts"):
        sys.exit(__doc__)
    if a[0] == "nets":
        print(json.dumps([nm for nm, _ in routed_nets(load(a[1]), a[2:] or None)]))
    else:
        print(json.dumps(conflicts(a[1], a[2:] or None)))


if __name__ == "__main__":
    main()
