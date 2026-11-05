"""pcblib.board: the one module in this repo that talks to SWIG pcbnew (KiCad 10, bundled Python 3.9).

Both rung-1 designers wrote the same 20 KB of pcbnew boilerplate and hit the same traps (R1-S1-T2, R1-Z1-T2,
R1-S1-T5, R1-Z1-T4). This module is that boilerplate once, with the traps handled, so a layout script is data:
placement, routes, zones, silk. When KiCad 11 replaces SWIG with the IPC API, this file changes and nothing else.

    from pcblib.board import Board
    b = Board.load("layout/x/x.kicad_pcb")            # a board that already has footprints and nets (Zener `pcb layout`)
    b = Board.from_netlist("x.xml", "x.kicad_pcb", libs={"Project": "x.pretty"})   # SKiDL path: build from kicadxml
    b.setup(clearance=0.2, track=0.2, via=(0.6, 0.3), hole_clearance=0.3, edge=0.4, layers=4)
    b.clear()                                         # tracks, vias, zones, board drawings (Delete, never Remove)
    b.outline_rect(100, 100, 25.4, 25.4, r=2.0)
    b.place("U1", 112.7, 112.7, 0)                    # by reference; raises on an unknown ref
    b.route("SDA", ["U1.14", (112.0, 109.5), "J1.3"])  # points are (x, y) mm or "REF.PAD"; width from the net class
    b.via(110.6, 112.7, "GND")
    b.thermal_vias("U2")                              # via grid inside the exposed pad (the router never adds these, ROUTE-T1)
    b.pad_feed("U2", "11", 2.5)                       # pour finger + vias sized for 2.5 A out of a fine-pitch power pin
    b.zone("GND", "In1.Cu")                           # whole board inset 0.5 mm, thermal reliefs
    b.text("Qwiic", 103.3, 103.2); b.text("rev A", 112.7, 112.0, layer="B.SilkS")   # B.* text is mirrored for you
    b.refdes("U1", visible=True, at=(108.2, 112.0)); b.hide_refdes()
    b.fields("U1", {"MPN": "LSM6DS3TR-C"})             # hidden, on F.Fab (SetField's default puts them on silk, R1-S1-T5)
    b.fill()                                          # save, reload, build connectivity, fill, save, reload, fill, save (P1-T10)
    b.save()

Traps handled here (do not work around them in scripts):
  - ZONE_FILLER.Fill on a BOARD() built in memory segfaults: fill() saves and reloads first (R1-S1-T5).
  - The first fill of a fresh board leaves islands that a refill clears: fill() fills twice with a reload (P1-T10).
  - board.Remove() leaks the item back to Python untyped and poisons the SWIG runtime: clear() uses Delete (R1-Z1-T4).
  - GetNetsByName() returns an unmanaged map: net() uses FindNet (R1-Z1-T4).
  - FOOTPRINT.SetField() creates a visible field at the origin; GetFieldByName does not exist in 10.0.1 (R1-S1-T5).
  - BOX2I.Merge into a temporary from GetBoundingBox aborts the interpreter (P1-T6).
  - SaveBoard re-nets a new via that sits in another net's stale zone fill and touches nothing of its own net (a VIN
    feed via inside the old GND pour came back GND, a 0.185 mm short to a VIN pad): save() unfills the zones first
    when this session added vias or tracks, and fill() pours them again (ROUTE-T4). unfill_and_save() does the same
    for scripts that hold a raw BOARD.
  - LSET(layer) has no single-layer constructor in 10.0.1 (P1-T6).
"""
import math, os, re
import xml.etree.ElementTree as ET
import pcbnew
from pcbnew import VECTOR2I, FromMM, ToMM

LAYER = {}   # name -> id, filled from the board on load


def _layers(board):
    LAYER.clear()
    for lid in range(pcbnew.PCB_LAYER_ID_COUNT):
        try:
            LAYER[board.GetLayerName(lid)] = lid
        except Exception:
            pass
    LAYER.update({"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu, "F.SilkS": pcbnew.F_SilkS, "B.SilkS": pcbnew.B_SilkS,
                  "F.Fab": pcbnew.F_Fab, "B.Fab": pcbnew.B_Fab, "Edge.Cuts": pcbnew.Edge_Cuts, "F.CrtYd": pcbnew.F_CrtYd,
                  "B.CrtYd": pcbnew.B_CrtYd, "F.Mask": pcbnew.F_Mask, "B.Mask": pcbnew.B_Mask})
    for i in range(1, 31):
        if hasattr(pcbnew, f"In{i}_Cu"):
            LAYER[f"In{i}.Cu"] = getattr(pcbnew, f"In{i}_Cu")


def unfill_and_save(board, path):
    """Clear every zone fill, then save: KiCad's save re-nets a via that touches only another net's stale fill
    (ROUTE-T4). Refill afterwards (Board.load(path).fill())."""
    for z in board.Zones():
        z.UnFill()
    pcbnew.SaveBoard(path, board)


def layer_id(name):
    if isinstance(name, int):
        return name
    if name not in LAYER:
        raise KeyError(f"unknown layer {name!r}; known: {sorted(LAYER)}")
    return LAYER[name]


def mm(x, y):
    return VECTOR2I(FromMM(x), FromMM(y))


def xy(v):
    return (round(ToMM(v.x), 4), round(ToMM(v.y), 4))


class Board:
    def __init__(self, board, path):
        self.b = board
        self.path = os.path.abspath(path)
        _layers(board)
        self._fps = None
        self._padnet = {}
        self.vias_added = 0
        self.tracks_added = 0
        self._dirty = False   # copper added since the last save: the next save unfills first (ROUTE-T4)

    # ------------------------------------------------------------------ construction
    @classmethod
    def load(cls, path):
        """A board with footprints and nets already in it (Zener `pcb layout --no-open`, or any saved board)."""
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        return cls(pcbnew.LoadBoard(path), path)

    @classmethod
    def from_netlist(cls, xml, path, libs=None, fp_dir=None, place=None):
        """Build a board from a kicadxml netlist: footprints by reference with pad nets, KiCad paths, fields hidden
        on F.Fab, DNP and exclusion flags. `libs` maps a library nickname to a .pretty directory; other nicknames
        resolve under fp_dir (default KiCad's bundled footprints). Nothing is placed unless `place` is given."""
        fp_dir = fp_dir or "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
        libs = libs or {}
        root = ET.parse(xml).getroot()
        board = pcbnew.BOARD()
        board.SetFileName(os.path.abspath(path))
        self = cls(board, path)
        nets = {}
        for n in root.find("nets"):
            name = n.get("name")
            ni = pcbnew.NETINFO_ITEM(board, name)
            board.Add(ni)
            nets[name] = ni
            for x in n:
                self._padnet[(x.get("ref"), x.get("pin"))] = name
        for c in root.find("components"):
            ref = c.get("ref")
            fpid = c.findtext("footprint") or ""
            if ":" not in fpid:
                raise ValueError(f"{ref}: footprint {fpid!r} has no library nickname")
            lib, name = fpid.split(":", 1)
            libdir = libs.get(lib) or os.path.join(fp_dir, lib + ".pretty")
            fp = pcbnew.FootprintLoad(libdir, name)
            if fp is None:
                raise FileNotFoundError(f"{ref}: footprint {name} not in {libdir}")
            fp.SetReference(ref)
            fp.SetValue(c.findtext("value") or "")
            fp.SetFPIDAsString(fpid)
            sp = c.find("sheetpath")
            sp = sp.get("tstamps") if sp is not None else "/"
            sp = sp if sp.endswith("/") else sp + "/"
            fp.SetPath(pcbnew.KIID_PATH(sp + (c.findtext("tstamps") or "")))
            fields = {f.get("name"): (f.text or "") for f in (c.find("fields") or [])}
            dnp = any(p.get("name") == "dnp" for p in c.findall("property")) or fields.get("dnp") == "yes"
            board.Add(fp)
            self._fps = None
            self.fields(ref, {k: v for k, v in fields.items() if k != "Footprint"})
            attrs = fp.GetAttributes()
            if dnp:
                attrs |= pcbnew.FP_DNP | pcbnew.FP_EXCLUDE_FROM_POS_FILES
                fp.SetDNP(True)
            if fields.get("exclude_from_bom") == "yes" or any(p.get("name") == "exclude_from_bom" for p in c.findall("property")):
                attrs |= pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES
            fp.SetAttributes(attrs)
            for pad in fp.Pads():
                n = self._padnet.get((ref, pad.GetNumber()))
                if n:
                    pad.SetNet(nets[n])
        if place:
            self.place_many(place)
        return self

    # ------------------------------------------------------------------ setup
    def setup(self, clearance=0.2, track=0.2, via=(0.6, 0.3), hole_clearance=0.25, edge=0.3, silk=0.15,
              hole_to_hole=0.5, annular=0.15, drill=0.3, layers=None, thickness=1.6, netclass_track=None,
              aux_origin=None, tent_vias=True):
        """Board-setup minimums (what the plain DRC enforces) and the default net class. These are the
        design-margin policy; the fab pack is applied on top by `pcb drc` (P1-T3)."""
        ds = self.b.GetDesignSettings()
        if layers:
            ds.SetCopperLayerCount(layers)
        ds.SetBoardThickness(FromMM(thickness))
        ds.m_MinClearance = FromMM(clearance)
        ds.m_TrackMinWidth = FromMM(track)
        ds.m_ViasMinSize = FromMM(via[0])
        ds.m_ViasMinAnnularWidth = FromMM(annular)
        ds.m_MinThroughDrill = FromMM(drill)
        ds.m_HoleClearance = FromMM(hole_clearance)
        ds.m_HoleToHoleMin = FromMM(hole_to_hole)
        ds.m_CopperEdgeClearance = FromMM(edge)
        ds.m_SilkClearance = FromMM(silk)
        ds.m_MinSilkTextHeight = FromMM(1.0)
        ds.m_MinSilkTextThickness = FromMM(0.15)
        ds.m_TentViasFront = ds.m_TentViasBack = bool(tent_vias)
        if aux_origin:
            ds.SetAuxOrigin(mm(*aux_origin))
        nc = ds.m_NetSettings.GetDefaultNetclass()
        nc.SetClearance(FromMM(clearance))
        nc.SetTrackWidth(FromMM(netclass_track or max(track, 0.25)))
        nc.SetViaDiameter(FromMM(via[0]))
        nc.SetViaDrill(FromMM(via[1]))
        self.track_default = netclass_track or max(track, 0.25)
        self.via_default = via
        _layers(self.b)
        return self

    # ------------------------------------------------------------------ lookup
    @property
    def fps(self):
        if self._fps is None:
            self._fps = {f.GetReference(): f for f in self.b.GetFootprints()}
        return self._fps

    def fp(self, ref):
        try:
            return self.fps[ref]
        except KeyError:
            raise KeyError(f"no footprint {ref}; board has {sorted(self.fps)}")

    def pad(self, ref, num):
        """Pad by number. 'MP1'/'MP2' address same-numbered 'MP' pads top to bottom (JST retention tabs)."""
        pads = list(self.fp(ref).Pads())
        if num.startswith("MP") and len(num) == 3 and not any(p.GetNumber() == num for p in pads):
            mps = sorted([p for p in pads if p.GetNumber() == "MP"], key=lambda p: p.GetPosition().y)
            return mps[int(num[2]) - 1]
        for p in pads:
            if p.GetNumber() == num:
                return p
        raise KeyError(f"{ref} has no pad {num}; pads {[p.GetNumber() for p in pads]}")

    def pad_xy(self, ref, num):
        return xy(self.pad(ref, num).GetPosition())

    def net(self, name):
        n = self.b.FindNet(name)   # GetNetsByName() returns an unmanaged map (R1-Z1-T4)
        if n is None:
            names = sorted(x.GetNetname() for x in self.b.GetNetInfo().NetsByNetcode().values())
            raise KeyError(f"no net {name!r}; nets {names}")
        return n

    def pt(self, p):
        """(x, y) in mm or 'REF.PAD' -> VECTOR2I."""
        if isinstance(p, str):
            ref, num = p.split(".", 1)
            return self.pad(ref, num).GetPosition()
        return mm(*p)

    # ------------------------------------------------------------------ edit
    def clear(self, tracks=True, zones=True, drawings=True):
        """Delete (not Remove) everything a layout script rebuilds; footprints stay."""
        if tracks:
            for t in list(self.b.Tracks()):
                self.b.Delete(t)
        if zones:
            for z in list(self.b.Zones()):
                self.b.Delete(z)
        if drawings:
            for d in list(self.b.GetDrawings()):
                self.b.Delete(d)
        return self

    def place(self, ref, x, y, rot=0, layer=None):
        f = self.fp(ref)
        if layer is not None and f.GetLayer() != layer_id(layer):
            f.Flip(f.GetPosition(), False)
        f.SetOrientationDegrees(rot)
        f.SetPosition(mm(x, y))
        return f

    def place_many(self, table):
        for ref, spec in table.items():
            self.place(ref, *spec)
        return self

    def park(self, keep, pitch=12.0):
        """Block-by-block placement (`pcb block`, spike #6): every footprint not in keep goes to a grid right of the
        outline, so the parts of blocks not yet placed stay off the board and out of the gate's way."""
        bb = self.b.GetBoardEdgesBoundingBox()
        x, y = ToMM(bb.GetRight()) + 15, ToMM(bb.GetTop())
        rest = [r for r in sorted(self.fps) if r not in keep]
        for i, r in enumerate(rest):
            self.fp(r).SetPosition(mm(x + (i % 8) * pitch, y + (i // 8) * pitch))
        return rest

    def orient_pads(self, ref, want):
        """Pick the rotation (0/90/180/270) under which want(pad_xy_fn) holds; raises if none does."""
        for rot in (0, 90, 180, 270):
            self.fp(ref).SetOrientationDegrees(rot)
            if want(lambda n: self.pad_xy(ref, n)):
                return rot
        raise ValueError(f"{ref}: no rotation satisfies the orientation rule")

    def route(self, net, pts, layer="F.Cu", width=None):
        ni = self.net(net)
        w = FromMM(width or getattr(self, "track_default", 0.25))
        v = [self.pt(p) for p in pts]
        for a, b in zip(v, v[1:]):
            t = pcbnew.PCB_TRACK(self.b)
            t.SetStart(a); t.SetEnd(b); t.SetWidth(w); t.SetLayer(layer_id(layer)); t.SetNet(ni)
            self.b.Add(t)
            self.tracks_added += 1
            self._dirty = True
        return self

    def via(self, x, y, net, size=None, layers=("F.Cu", "B.Cu")):
        d, drill = size or getattr(self, "via_default", (0.6, 0.3))
        v = pcbnew.PCB_VIA(self.b)
        v.SetPosition(self.pt((x, y)) if not isinstance(x, str) else self.pt(x))
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(layer_id(layers[0]), layer_id(layers[1]))
        v.SetDrill(FromMM(drill)); v.SetWidth(FromMM(d)); v.SetNet(self.net(net))
        self.b.Add(v)
        self.vias_added += 1
        self._dirty = True
        return v

    def _via_spot(self, gnd, d, edge_mm=None):
        """(tracks, clear(x, y)): clear says why a via of diameter d on net gnd cannot stand at (x, y), or None. Other nets'
        pads, vias, tracks and filled zones on every copper layer at the board clearance, any SMD pad of any net (no via
        in a pad, spike #6) with a 0.15 mm mask web, and the board edge at edge_mm (default the setup's edge clearance)."""
        b = self.b
        clr = getattr(self, "clearance", 0.2)
        margin = FromMM(d / 2 + clr + 0.02)   # HitTest's accuracy rounds: 0.5 passed a via 0.199 mm off R6.2 (s6-a-1)
        edge = b.GetBoardEdgesBoundingBox()
        ex0, ey0, ex1, ey1 = ToMM(edge.GetLeft()), ToMM(edge.GetTop()), ToMM(edge.GetRight()), ToMM(edge.GetBottom())
        edge_clr = getattr(self, "edge_clearance", 0.3) if edge_mm is None else edge_mm
        zones = [(z, L) for z in b.Zones() if not z.GetIsRuleArea() and z.GetNetname() != gnd for L in z.GetLayerSet().CuStack() if z.HasFilledPolysForLayer(L)]
        pads = [q for f in b.GetFootprints() for q in f.Pads()]
        tracks = [t for t in b.GetTracks()]

        def clear(x, y):
            if not (ex0 + edge_clr + d / 2 <= x <= ex1 - edge_clr - d / 2 and ey0 + edge_clr + d / 2 <= y <= ey1 - edge_clr - d / 2):
                return "board edge"
            pt = mm(x, y)
            for q in pads:
                if q.GetNetname() != gnd and q.HitTest(pt, margin):
                    return f"{q.GetParentFootprint().GetReference()}.{q.GetNumber()} ({q.GetNetname()})"
                if q.GetNetname() == gnd and q.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and q.HitTest(pt, FromMM(d / 2)):
                    return "a ground pad hole"
                if q.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and q.HitTest(pt, FromMM(d / 2 + 0.15)):
                    return f"in pad {q.GetParentFootprint().GetReference()}.{q.GetNumber()}"
            for t in tracks:
                if t.GetClass() == "PCB_VIA":
                    v = xy(t.GetPosition())
                    if math.hypot(v[0] - x, v[1] - y) < d / 2 + ToMM(t.GetWidth(pcbnew.F_Cu)) / 2 + (clr if t.GetNetname() != gnd else 0.0):
                        return f"a {t.GetNetname()} via"
                elif t.GetNetname() != gnd and t.HitTest(pt, margin):
                    return f"a {t.GetNetname()} track"
            for z, L in zones:
                if z.GetFilledPolysList(L).Collide(pt, margin):
                    return f"the {z.GetNetname()} pour on {b.GetLayerName(L)}"
            return None
        return tracks, clear

    def fill_islands(self, gnd="GND"):
        """Fill the gnd zones with island removal off, on the saved board, and return every piece no gnd copper touches:
        [{layer, area_mm2, centre, outline (SHAPE_POLY_SET), zone}], with the removal modes left as found. These are the
        pieces KiCad's fill rips up. The caller saves or refills; the board wraps the filled copy afterwards."""
        modes = [(z.GetZoneName(), z.GetIslandRemovalMode()) for z in self.b.Zones() if z.GetNetname() == gnd]
        for z in self.b.Zones():
            if z.GetNetname() == gnd and not z.GetIsRuleArea():
                z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
        self.fill(passes=1)
        b = self.b
        items = []
        for t in b.GetTracks():
            if t.GetNetname() == gnd:
                if t.GetClass() == "PCB_VIA":
                    items.append((None, t.GetPosition()))
                else:
                    items.append((t.GetLayer(), t.GetStart())); items.append((t.GetLayer(), t.GetEnd()))
        for f in b.GetFootprints():
            for q in f.Pads():
                if q.GetNetname() == gnd:
                    items.append((None if q.GetAttribute() == pcbnew.PAD_ATTRIB_PTH else f.GetLayer(), q.GetPosition()))
        out = []
        for z in b.Zones():
            if z.GetNetname() != gnd or z.GetIsRuleArea():
                continue
            for L in z.GetLayerSet().CuStack():
                if not z.HasFilledPolysForLayer(L):
                    continue
                polys = z.GetFilledPolysList(L)
                for i in range(polys.OutlineCount()):
                    one = pcbnew.SHAPE_POLY_SET()
                    one.AddOutline(polys.Outline(i))
                    # a pad or track that only reaches this piece counts: KiCad's own island test keeps such pieces too
                    if any((lay is None or lay == L) and one.Collide(p, FromMM(0.05)) for lay, p in items):
                        continue
                    bb = one.BBox()
                    out.append({"layer": b.GetLayerName(L), "area_mm2": round(one.Area() / 1e12, 3), "zone": z.GetZoneName(), "poly": one,
                                "bbox": (ToMM(bb.GetLeft()), ToMM(bb.GetTop()), ToMM(bb.GetRight()), ToMM(bb.GetBottom()))})
        for z in b.Zones():
            for name, mode in modes:
                if z.GetNetname() == gnd and z.GetZoneName() == name and not z.GetIsRuleArea():
                    z.SetIslandRemovalMode(mode)
        return out

    def ground_islands(self, gnd="GND", size=None, min_mm2=0.5, step=0.2, edge_mm=None, dry=False):
        """Spike #6: tie the ground fill's islands to ground with a via instead of letting KiCad rip them up. For each
        piece over min_mm2 with no ground copper, the spot deepest inside it that passes _via_spot and sits fully on the
        piece gets a through via onto the ground planes; one via frees the same piece on every layer it crosses, so
        islands are re-read after each. Returns {"placed": [(layer, area, x, y)], "skipped": [(layer, area, why)]}; the
        board is refilled with the removal modes as they were, so what is left is what KiCad would remove anyway."""
        d, drill = size or getattr(self, "via_default", (0.6, 0.3))
        out = {"placed": [], "skipped": []}
        tried = set()
        while True:
            isl = sorted((i for i in self.fill_islands(gnd) if i["area_mm2"] >= min_mm2), key=lambda i: -i["area_mm2"])
            isl = [i for i in isl if (i["layer"], i["area_mm2"]) not in tried]
            if not isl:
                break
            i = isl[0]
            tried.add((i["layer"], i["area_mm2"]))
            _, clear = self._via_spot(gnd, d, edge_mm)
            x0, y0, x1, y1 = i["bbox"]
            nx, ny = max(1, int((x1 - x0) / step)), max(1, int((y1 - y0) / step))
            ring = lambda x, y, r: [(x + r * math.cos(a * math.pi / 4), y + r * math.sin(a * math.pi / 4)) for a in range(8)]
            best, why = None, "no spot inside the piece"
            for ix in range(nx + 1):
                for iy in range(ny + 1):
                    x, y = round(x0 + ix * step, 3), round(y0 + iy * step, 3)
                    if not all(i["poly"].Collide(mm(a, b_)) for a, b_ in ring(x, y, d / 2)):
                        continue
                    depth = sum(i["poly"].Collide(mm(a, b_)) for r in (d / 2 + 0.2, d / 2 + 0.5) for a, b_ in ring(x, y, r))
                    w = clear(x, y)
                    if w:
                        why = w
                    elif best is None or depth > best[0]:
                        best = (depth, x, y)
            if best:
                out["placed"].append((i["layer"], i["area_mm2"], best[1], best[2]))
                if not dry:
                    self.via(best[1], best[2], gnd, size=(d, drill))
                    tried = set()
            else:
                out["skipped"].append((i["layer"], i["area_mm2"], why))
        self.fill()
        return out

    def return_vias(self, nets, max_mm=2.0, gnd="GND", size=None, rings=(0.8, 1.0, 1.2, 1.5, 1.8, 2.0), step_deg=30, dry=False):
        """SIG-2: a ground via beside every via of `nets` that has none within max_mm. A via on a fast net moves its return
        current from one ground plane to the other, and the planes only meet at ground vias and through-hole ground
        pads. Candidates on rings around the signal via (nearest first, step_deg apart) are checked at the board
        clearance against other nets' pads, vias, tracks and filled zones on every copper layer and against the board
        edge; the first clear one is placed. Returns {"placed": [...], "covered": n, "skipped": [(net, x, y, why)]}."""
        d, drill = size or getattr(self, "via_default", (0.6, 0.3))
        b = self.b
        returns = [xy(t.GetPosition()) for t in b.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetname() == gnd]
        for f in b.GetFootprints():
            for q in f.Pads():
                if q.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and q.GetNetname() == gnd:
                    returns.append(xy(q.GetPosition()))
        tracks, clear = self._via_spot(gnd, d)

        out = {"placed": [], "covered": 0, "skipped": []}
        for t in [t for t in tracks if t.GetClass() == "PCB_VIA" and t.GetNetname() in nets]:
            x, y = xy(t.GetPosition())
            if any(math.hypot(gx - x, gy - y) <= max_mm for gx, gy in returns):
                out["covered"] += 1
                continue
            placed = None; last = ""
            for r in rings:
                if r > max_mm + 1e-9:
                    break
                for a in range(0, 360, step_deg):
                    cx = round(x + r * math.cos(math.radians(a)), 3); cy = round(y + r * math.sin(math.radians(a)), 3)
                    why = clear(cx, cy)
                    if why is None:
                        placed = (cx, cy); break
                    last = why
                if placed:
                    break
            if placed:
                if not dry:
                    v = self.via(placed[0], placed[1], gnd, size=(d, drill))
                    tracks.append(v)
                returns.append(placed)
                out["placed"].append((t.GetNetname(), x, y, placed[0], placed[1], round(math.hypot(placed[0] - x, placed[1] - y), 2)))
            else:
                out["skipped"].append((t.GetNetname(), x, y, f"no clear spot within {max_mm} mm, last hit {last}"))
        return out

    def _pad_frame(self, p):
        """Pad centre, its half-extents along x and y after rotation, in mm."""
        c = xy(p.GetPosition()); sx, sy = ToMM(p.GetSize().x), ToMM(p.GetSize().y)
        a = round(p.GetOrientationDegrees()) % 180
        if a == 90:
            sx, sy = sy, sx
        elif a != 0:
            raise ValueError(f"pad at {a} degrees: only 0/90/180/270 are handled")
        return c, sx / 2, sy / 2

    def thermal_vias(self, ref, pad=None, pitch=1.0, size=None, margin=0.4, layers=("F.Cu", "B.Cu")):
        """A via grid inside a footprint's exposed pad (the largest pad unless `pad` names one), on the pad's net. The
        router strips and never adds these (ROUTE-T1: no thermal vias under the DRV8874 in any KRT config). Prefer the
        stock `_ThermalVias` footprint where KiCad has one; this is for vendored footprints. Grid points within the board
        clearance of another net's pad are skipped and listed in `self.thermal_skipped`. Returns the via count."""
        f = self.fp(ref)
        p = self.pad(ref, pad) if pad else max(f.Pads(), key=lambda q: q.GetSize().x * q.GetSize().y)
        (cx, cy), hx, hy = self._pad_frame(p)
        nx = max(1, int((2 * hx - 2 * margin) / pitch) + 1); ny = max(1, int((2 * hy - 2 * margin) / pitch) + 1)
        dvia = (size or getattr(self, "via_default", (0.6, 0.3)))[0]
        clr = getattr(self, "clearance", 0.2)
        others = [q for g in self.b.GetFootprints() for q in g.Pads() if q.GetNetname() != p.GetNetname()
                  and not (g.GetReference() == ref and q.GetNumber() == "")]   # the footprint's own paste-aperture pads
        n, self.thermal_skipped = 0, []
        for i in range(nx):
            for j in range(ny):
                x, y = cx + (i - (nx - 1) / 2) * pitch, cy + (j - (ny - 1) / 2) * pitch
                hit = next((q for q in others if q.HitTest(mm(x, y), FromMM(dvia / 2 + clr))), None)
                if hit is not None:   # a QFN's exposed pad sits 0.2 mm from its own pins and nearby caps
                    self.thermal_skipped.append(f"({x:.2f}, {y:.2f}) near {hit.GetParentFootprint().GetReference()}.{hit.GetNumber()}")
                    continue
                self.via(x, y, p.GetNetname(), size=size, layers=layers)
                n += 1
        return n

    @staticmethod
    def via_amps(drill_mm, rise_c=20.0, plating_mm=0.025):
        """IPC-2221 internal on the barrel, 25 um plating: pcbcheck's `feeds` formula, so a pad_feed passes its row."""
        area_mil2 = math.pi * (drill_mm / 0.0254) * (plating_mm / 0.0254)
        return 0.024 * rise_c ** 0.44 * area_mil2 ** 0.725

    @staticmethod
    def _inside(pt, poly):
        x, y = pt; inside = False
        for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
            if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
        return inside

    def _area_hits(self, outline, net, clr, priority, skip=(), step=0.1):
        """Points of `outline` (0.1 mm grid) within `clr` of another net's pad or via, or inside another net's zone of
        equal or higher priority (a feed pour; the ground pours rank lower and pull back on their own)."""
        xs = [p[0] for p in outline]; ys = [p[1] for p in outline]
        pts = [(x0, y0) for i in range(int((max(xs) - min(xs)) / step) + 1) for j in range(int((max(ys) - min(ys)) / step) + 1)
               for x0, y0 in [(min(xs) + i * step, min(ys) + j * step)] if self._inside((x0, y0), outline)]
        skip_ids = {(q.GetParentFootprint().GetReference(), q.GetNumber()) for q in skip}
        others = [q for f in self.b.GetFootprints() for q in f.Pads()
                  if q.GetNetname() != net and (q.GetParentFootprint().GetReference(), q.GetNumber()) not in skip_ids]
        vias = [(xy(t.GetPosition()), ToMM(t.GetWidth(pcbnew.F_Cu)) / 2, t.GetNetname()) for t in self.b.GetTracks()
                if t.GetClass() == "PCB_VIA" and t.GetNetname() != net]
        zones = []
        for z in self.b.Zones():
            if not z.GetIsRuleArea() and z.GetNetname() != net and z.GetAssignedPriority() >= priority:
                zones.append(([xy(z.GetCornerPosition(i)) for i in range(z.GetNumCorners())], z.GetNetname(), z.GetZoneName()))
        hits, seen = [], set()
        for x, y in pts:
            pt = mm(x, y)
            near = [q for q in others if abs(ToMM(q.GetPosition().x) - x) < 3 and abs(ToMM(q.GetPosition().y) - y) < 3]
            for q in near:
                key = (q.GetParentFootprint().GetReference(), q.GetNumber())
                if key not in seen and q.HitTest(pt, FromMM(clr)):
                    seen.add(key); hits.append(f"pour at ({x:.2f}, {y:.2f}) on {key[0]}.{key[1]} ({q.GetNetname()})")
            for (vx, vy), r, vn in vias:
                if ("v", vx, vy) not in seen and math.hypot(vx - x, vy - y) < r + clr:
                    seen.add(("v", vx, vy)); hits.append(f"pour at ({x:.2f}, {y:.2f}) on a {vn} via at ({vx:.2f}, {vy:.2f})")
            for poly, zn, name in zones:
                if name not in seen and self._inside((x, y), poly):
                    seen.add(name); hits.append(f"pour at ({x:.2f}, {y:.2f}) inside {name} ({zn})")
        return hits

    def plan_feeds(self, rows, dry=False):
        """pad_feed_search over many pins at once (FEED-2): biggest current first, and a pad with other feed pads beside it
        on the same footprint tries splaying away from them first, so neighbours fan apart instead of the first one taking
        the straight-out slot (DRV8874 VM beside OUT2). rows: [(\"U2.11\", 2.5), ...]. Returns {pad: result or error}."""
        out = {}
        pads = {}
        for pad, _ in rows:
            ref, nums = pad.split(".", 1)
            ps = [self.pad(ref, n) for n in nums.split(",")]
            pads[pad] = (ref, sum(xy(q.GetPosition())[0] for q in ps) / len(ps), sum(xy(q.GetPosition())[1] for q in ps) / len(ps))
        for pad, amps in sorted(rows, key=lambda r: -r[1]):
            ref, nums = pad.split(".", 1)
            ref_, px, py = pads[pad]
            near = [(x, y) for k, (r2, x, y) in pads.items() if k != pad and r2 == ref and math.hypot(x - px, y - py) < 2.5]
            prefer = 0
            if near:
                q = self.pad(ref, nums.split(",")[0]); _, hx, hy = self._pad_frame(q)
                allp = [xy(o.GetPosition()) for o in self.fp(ref).Pads()]
                fx, fy = sum(a for a, _ in allp) / len(allp), sum(b for _, b in allp) / len(allp)
                d = ((1.0 if px >= fx else -1.0), 0.0) if hx >= hy else (0.0, (1.0 if py >= fy else -1.0))
                n = (-d[1], d[0])
                ox, oy = sum(x for x, _ in near) / len(near), sum(y for _, y in near) / len(near)
                prefer = 1 if (px - ox) * n[0] + (py - oy) * n[1] > 0 else -1
            splays = (30 * prefer, 50 * prefer, 70 * prefer, 0, -30 * prefer) if prefer else (0, 30, -30, 50, -50)
            try:
                out[pad] = self.pad_feed_search(ref, nums, amps, splays=splays, splay_first=bool(prefer))
            except ValueError as e:
                out[pad] = {"error": str(e)}
        return out

    def pad_feed_search(self, ref, num, amps, splays=(0, 30, -30, 50, -50), lengths=(1.0, 1.8, 2.6), acrosses=(3, 2, 1),
                        splay_first=False, **kw):
        """pad_feed over a small grid of splay x length x across, first fit wins (fewest changes from straight-out,
        short, wide first; with splay_first, every length and width at the first splay before the next, so a preferred
        direction is not given up for a wider field). Raises with the last collision when nothing fits; the placement
        then needs to move."""
        import itertools
        last = None
        grid = (((sp, ln, ac) for sp in splays for ln in lengths for ac in acrosses) if splay_first else
                ((sp, ln, ac) for ln in lengths for ac in acrosses for sp in splays))
        for splay, length, across in grid:
            if True:
                if True:
                    try:
                        r = self.pad_feed(ref, num, amps, length=length, splay=splay, across=across, **kw)
                        r.update(splay=splay, length=length, across=across)
                        return r
                    except ValueError as e:
                        last = e
        raise ValueError(f"pad_feed_search {ref}.{num}: nothing fits in {len(splays) * len(lengths) * len(acrosses)} tries; last: {last}")

    def pad_feed(self, ref, num, amps, layer="F.Cu", length=1.0, splay=0.0, size=None, pitch=None, across=3, rise_c=20.0,
                 priority=3, layers=("F.Cu", "B.Cu"), check=True, exit=0.4):
        """Feed a fine-pitch power pin the way the rung-2 designers did by hand (R2A2-T1): a pour on the pad's net that
        covers the pad, leaves the package along the pad's long axis at the pad's width, flares over `length` mm and
        ends in a field of vias, as many as IPC-2221 needs for `amps` at `rise_c` (0.3 mm drill: 1.22 A each, so 2.5 A
        gets 3). `num` may be "4,5,6": adjacent pins on one net on one side share one pour. `splay` turns the flare and
        the via field by that many degrees off straight-out, so neighbouring power pins on different nets fan apart
        (DRV8874 OUT2/VM: -40 and +40). Before anything is added every via is checked against other nets' pads and vias
        at the board clearance; a collision raises with the parts it hit (check=False skips that). The router then treats
        the feed as existing copper and does not neck the pin (ROUTE-T1: 0.2 mm into VM in every KRT config).
        Returns {"vias", "amps_capacity", "outline", "vias_xy"}."""
        nums = [x.strip() for x in str(num).split(",")]
        pads = [self.pad(ref, x) for x in nums]
        net = pads[0].GetNetname()
        if any(q.GetNetname() != net for q in pads):
            raise ValueError(f"pad_feed {ref}.{num}: pads on different nets")
        frames = [self._pad_frame(q) for q in pads]
        _, hx, hy = frames[0]
        allp = [xy(q.GetPosition()) for q in self.fp(ref).Pads()]          # pad centroid, not the footprint origin
        fx, fy = sum(a for a, _ in allp) / len(allp), sum(b for _, b in allp) / len(allp)   # (vendored SOIC-8: origin at pin 1)
        cxm = sum(f[0][0] for f in frames) / len(frames); cym = sum(f[0][1] for f in frames) / len(frames)
        if hx >= hy:
            d = (1.0 if cxm >= fx else -1.0, 0.0)
        else:
            d = (0.0, 1.0 if cym >= fy else -1.0)
        nrm = (-d[1], d[0])
        along = [(f[0][0] - cxm) * d[0] + (f[0][1] - cym) * d[1] for f in frames]
        perp = [(f[0][0] - cxm) * nrm[0] + (f[0][1] - cym) * nrm[1] for f in frames]
        hl = max(a + (f[1] if d[0] else f[2]) for a, f in zip(along, frames))
        hw_lo = min(q - (f[2] if d[0] else f[1]) for q, f in zip(perp, frames))
        hw_hi = max(q + (f[2] if d[0] else f[1]) for q, f in zip(perp, frames))
        dvia, drill = size or getattr(self, "via_default", (0.6, 0.3))
        pitch = pitch or round(dvia + 0.35, 2)
        n = max(1, math.ceil(amps / self.via_amps(drill, rise_c)))
        k = min(n, across); rows = math.ceil(n / k)
        half = max(k * pitch / 2, (hw_hi - hw_lo) / 2)
        mid = (hw_hi + hw_lo) / 2
        a = math.radians(splay)
        d2 = (d[0] * math.cos(a) - d[1] * math.sin(a), d[0] * math.sin(a) + d[1] * math.cos(a)); n2 = (-d2[1], d2[0])
        def at(t, s):                                # pad frame: t along the pad axis from the group centre, s across
            return (cxm + d[0] * t + nrm[0] * s, cym + d[1] * t + nrm[1] * s)
        ex, ey = at(hl + exit, mid)                  # straight out past the pin row's tips before any turn (FEED-2)
        ox, oy = ex + d2[0] * length, ey + d2[1] * length
        def fat(t, s):                               # field frame: from the end of the flare, along the splayed axis
            return (ox + d2[0] * t + n2[0] * s, oy + d2[1] * t + n2[1] * s)
        depth = rows * pitch
        outline = [at(min(along), hw_lo), at(hl + exit, hw_lo), fat(0, -half), fat(depth, -half), fat(depth, half), fat(0, half),
                   at(hl + exit, hw_hi), at(min(along), hw_hi)]
        outline = [(round(x, 4), round(y, 4)) for x, y in outline]
        spots = []
        for r in range(rows):
            for c in range(k):
                if len(spots) < n:
                    spots.append(fat((r + 0.5) * pitch, (c - (k - 1) / 2) * pitch))
        if check:
            clr = getattr(self, "clearance", 0.2)
            hits = self._area_hits(outline, net, clr, priority, skip=pads)
            for x, y in spots:
                pt = mm(x, y)
                for f in self.b.GetFootprints():
                    for q in f.Pads():
                        if q.GetNetname() != net and q.HitTest(pt, FromMM(dvia / 2 + clr)):
                            hits.append(f"via ({x:.2f}, {y:.2f}) on {f.GetReference()}.{q.GetNumber()} ({q.GetNetname()})")
                for t in self.b.GetTracks():
                    if t.GetClass() == "PCB_VIA" and t.GetNetname() != net:
                        v = xy(t.GetPosition())
                        if math.hypot(v[0] - x, v[1] - y) < dvia / 2 + ToMM(t.GetWidth(pcbnew.F_Cu)) / 2 + clr:
                            hits.append(f"via ({x:.2f}, {y:.2f}) on a {t.GetNetname()} via at ({v[0]:.2f}, {v[1]:.2f})")
            if hits:
                raise ValueError(f"pad_feed {ref}.{num}: {len(hits)} collision(s), try splay/length/across: " + "; ".join(hits[:4]))
        lid = layer_id(layer)
        for z in self.b.Zones():   # KiCad: intersecting zones need distinct priorities; a same-net pour it overlaps ranks below
            if z.GetIsRuleArea() or z.GetNetname() != net or not z.IsOnLayer(lid):
                continue
            poly = [xy(z.GetCornerPosition(i)) for i in range(z.GetNumCorners())]
            if any(self._inside(q, poly) for q in outline) or any(self._inside(q, outline) for q in poly):
                priority = max(priority, z.GetAssignedPriority() + 1)
        self.zone(net, layer, outline=outline, clearance=getattr(self, "clearance", 0.2), min_width=0.2, thermal=False, priority=priority,
                  name=f"feed_{ref}_{'_'.join(nums)}")
        for x, y in spots:
            self.via(x, y, net, size=(dvia, drill), layers=layers)
        return {"vias": len(spots), "amps_capacity": round(len(spots) * self.via_amps(drill, rise_c), 2), "outline": outline,
                "vias_xy": [(round(x, 3), round(y, 3)) for x, y in spots]}

    def line(self, a, b, layer="F.SilkS", width=0.15):
        s = pcbnew.PCB_SHAPE(self.b)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(self.pt(a)); s.SetEnd(self.pt(b)); s.SetLayer(layer_id(layer)); s.SetWidth(FromMM(width))
        self.b.Add(s)
        return s

    def arc(self, start, mid, end, layer="Edge.Cuts", width=0.1):
        s = pcbnew.PCB_SHAPE(self.b)
        s.SetShape(pcbnew.SHAPE_T_ARC)
        s.SetArcGeometry(self.pt(start), self.pt(mid), self.pt(end)); s.SetLayer(layer_id(layer)); s.SetWidth(FromMM(width))
        self.b.Add(s)
        return s

    def outline_rect(self, x0, y0, w, h, r=0.0):
        """Rounded rectangle on Edge.Cuts; remembers the frame for zone() and the JLC CPL origin."""
        self.frame = (x0, y0, w, h)
        x1, y1, x2, y2 = x0, y0, x0 + w, y0 + h
        if r <= 0:
            for a, b in (((x1, y1), (x2, y1)), ((x2, y1), (x2, y2)), ((x2, y2), (x1, y2)), ((x1, y2), (x1, y1))):
                self.line(a, b, "Edge.Cuts", 0.1)
            return self
        k = r * (1 - math.sqrt(0.5))
        self.line((x1 + r, y1), (x2 - r, y1), "Edge.Cuts", 0.1); self.line((x2, y1 + r), (x2, y2 - r), "Edge.Cuts", 0.1)
        self.line((x2 - r, y2), (x1 + r, y2), "Edge.Cuts", 0.1); self.line((x1, y2 - r), (x1, y1 + r), "Edge.Cuts", 0.1)
        self.arc((x2 - r, y1), (x2 - k, y1 + k), (x2, y1 + r)); self.arc((x2, y2 - r), (x2 - k, y2 - k), (x2 - r, y2))
        self.arc((x1 + r, y2), (x1 + k, y2 - k), (x1, y2 - r)); self.arc((x1, y1 + r), (x1 + k, y1 + k), (x1 + r, y1))
        return self

    def zone(self, net, layer, outline=None, inset=0.5, clearance=0.25, min_width=0.25, thermal=True,
             relief_gap=0.3, spoke=0.3, priority=0, name=None):
        """Copper zone. outline: list of (x, y); default the outline_rect frame inset by `inset` mm."""
        z = pcbnew.ZONE(self.b)
        z.SetLayer(layer_id(layer)); z.SetNet(self.net(net))
        z.SetLocalClearance(FromMM(clearance)); z.SetMinThickness(FromMM(min_width))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL if thermal else pcbnew.ZONE_CONNECTION_FULL)
        z.SetThermalReliefGap(FromMM(relief_gap)); z.SetThermalReliefSpokeWidth(FromMM(spoke))
        z.SetAssignedPriority(priority)
        z.SetZoneName(name or f"{net}_{layer if isinstance(layer, str) else self.b.GetLayerName(layer)}")
        if outline is None:
            if not hasattr(self, "frame"):
                bb = self.b.GetBoardEdgesBoundingBox()
                self.frame = (ToMM(bb.GetX()), ToMM(bb.GetY()), ToMM(bb.GetWidth()), ToMM(bb.GetHeight()))
            x0, y0, w, h = self.frame
            e = inset
            outline = [(x0 + e, y0 + e), (x0 + w - e, y0 + e), (x0 + w - e, y0 + h - e), (x0 + e, y0 + h - e)]
        o = z.Outline(); o.NewOutline()
        for x, y in outline:
            o.Append(FromMM(x), FromMM(y))
        self.b.Add(z)
        return z

    def text(self, s, x, y, layer="F.SilkS", size=1.0, thick=0.15, rot=0, mirror=None):
        t = pcbnew.PCB_TEXT(self.b)
        t.SetText(s); t.SetPosition(mm(x, y)); t.SetLayer(layer_id(layer))
        t.SetTextSize(VECTOR2I(FromMM(size), FromMM(size))); t.SetTextThickness(FromMM(thick))
        t.SetTextAngleDegrees(rot)
        if mirror is None:
            mirror = str(layer).startswith("B.")
        t.SetMirrored(bool(mirror))
        self.b.Add(t)
        return t

    def arrow(self, a, b, layer="F.SilkS", width=0.15, head=0.5):
        self.line(a, b, layer, width)
        ax, ay = self.pt(a).x, self.pt(a).y
        bx, by = self.pt(b).x, self.pt(b).y
        ang = math.atan2(by - ay, bx - ax)
        bxm, bym = ToMM(bx), ToMM(by)
        for s in (+1, -1):
            self.line((bxm, bym), (bxm - head * math.cos(ang + s * 0.5), bym - head * math.sin(ang + s * 0.5)), layer, width)
        return self

    def fields(self, ref, values, visible=False, layer="F.Fab", rename_upper=("Lcsc", "Mpn")):
        """Set footprint fields hidden on F.Fab (SetField's default makes them visible at the origin, R1-S1-T5);
        also upper-cases Zener's Lcsc/Mpn so schematic parity matches the symbol field names (R1-Z1 layout)."""
        f = self.fp(ref)
        for k, v in values.items():
            f.SetField(k, v)
        for fl in f.GetFields():
            if fl.GetName() in rename_upper:
                fl.SetName(fl.GetName().upper())
            if fl.GetName() not in ("Reference", "Value"):
                fl.SetVisible(visible)
                fl.SetLayer(layer_id(layer))
        return self

    def field(self, ref, name):
        """Case-insensitive field read (GetFieldByName does not exist in 10.0.1)."""
        for fl in self.fp(ref).GetFields():
            if fl.GetName().lower() == name.lower():
                return fl.GetText()
        return ""

    def refdes(self, ref, visible=True, at=None, rot=0, size=1.0, thick=0.15, layer=None):
        r = self.fp(ref).Reference()
        r.SetVisible(visible)
        if at:
            r.SetPosition(mm(*at))
        r.SetTextAngleDegrees(rot)
        r.SetTextSize(VECTOR2I(FromMM(size), FromMM(size))); r.SetTextThickness(FromMM(thick))
        if layer:
            r.SetLayer(layer_id(layer))
        return r

    def hide_refdes(self, keep=(), values=True):
        """Hide every reference (and value) except `keep`. pcbcheck's silk row fails any refdes the bring-up doc
        names that is hidden (R1-Z1-F4), so keep the ones the technician needs."""
        for ref, f in self.fps.items():
            if ref not in keep:
                f.Reference().SetVisible(False)
            if values:
                f.Value().SetVisible(False)
        return self

    # ------------------------------------------------------------------ fill / save
    def save(self, path=None):
        """Save. When vias or tracks were added since the last save the zone fills are cleared first (ROUTE-T4: SaveBoard
        re-nets a new via inside another net's stale fill); fill() pours them again, so call it before handing the board on."""
        path = path or self.path
        if self._dirty:
            unfill_and_save(self.b, path)
            self._dirty = False
        else:
            pcbnew.SaveBoard(path, self.b)
        return path

    def fill(self, passes=2):
        """Fill zones the way that converges: save, reload from disk (an in-memory BOARD() segfaults the filler,
        R1-S1-T5), build connectivity, fill, save; then once more (the first fill of a fresh board leaves islands
        that a refill clears, P1-T10). The instance now wraps the reloaded board."""
        self.save()
        for _ in range(passes):
            self.b = pcbnew.LoadBoard(self.path)
            self._fps = None
            _layers(self.b)
            self.b.BuildConnectivity()
            pcbnew.ZONE_FILLER(self.b).Fill(self.b.Zones())
            self.save()
        self.b = pcbnew.LoadBoard(self.path)
        self._fps = None
        return self

    def summary(self):
        tr = [t for t in self.b.GetTracks() if t.GetClass() != "PCB_VIA"]
        vs = [t for t in self.b.GetTracks() if t.GetClass() == "PCB_VIA"]
        return {"footprints": len(self.fps), "tracks": len(tr), "vias": len(vs), "zones": len(list(self.b.Zones())),
                "drawings": len(list(self.b.GetDrawings())), "path": self.path}
