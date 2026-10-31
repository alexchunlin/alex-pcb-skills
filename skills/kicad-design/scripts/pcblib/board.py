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
        return v

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
        path = path or self.path
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
