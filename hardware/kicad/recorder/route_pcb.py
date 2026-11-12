#!/usr/bin/env python3
"""Pour planes and route traces on the existing recorder board.

Run with any interpreter that has KiCad 10's ``pcbnew`` module. On Linux the
distro KiCad package puts it in the system python3; on Windows use
``.../KiCad/10.0/bin/python.exe``.

    python3 route_pcb.py                    # planes + full autoroute + pours
    python3 route_pcb.py --planes-only      # re-pour zones, keep the traces
    python3 route_pcb.py --export-dsn F     # planes only, write a Specctra DSN
    python3 route_pcb.py --import-ses F     # apply a session, pour, stitch
    python3 route_pcb.py --finish-only      # drop stub vias, re-seat silk
    python3 route_pcb.py --repair-only      # maze leftover opens, keep copper

The router is freerouting (https://freerouting.app), driven headless through
Specctra DSN/SES. The old in-tree A* router that used to live here is gone:
it left 373 DRC errors and 38 open nets, mostly shorts and sub-minimum track
widths, and no amount of grid tuning made it competitive with a real
rip-up-and-retry router. Point PSV_FREEROUTING at the launcher, or put
``freerouting`` on PATH; scripts/setup-ubuntu.sh installs it.

This script loads recorder.kicad_pcb. It never calls CreateEmptyBoard and it
does not move footprints. Edge.Cuts, mounting holes, and placement stay as
they are. It refuses to write while ~recorder.kicad_pcb.lck is present.

Coordinates are the same magnet-centred millimetres as generate_pcb.py.
The hand-routed stitch points in this file are from before the lid 180° spin
(pogo now at +Y / phone-top; clocking magnet still 6 o'clock in the tray).
Do not run a full re-route until those absolute points are regenerated;
--planes-only still re-pours the zones that are already on the board.
"""

from __future__ import annotations

import collections
import heapq
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import pcbnew

try:
    import wx
except ImportError:
    wx = None
else:
    # KiCad 10's Windows build still trips PCB_VIA::GetWidth() without a
    # layer inside DSN export. That is a wx assert dialog, not a real DRC
    # failure. Mute it so a headless route can finish.
    wx.DisableAsserts()

from generate_pcb import DESIGN_RULES, apply_project_policy, tuck_reference_text

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PARAMS = os.path.join(REPO, "hardware", "cad", "params.json")
PCB = os.environ.get("PSV_ROUTE_PCB", os.path.join(HERE, "recorder.kicad_pcb"))
PROJECT = os.environ.get("PSV_ROUTE_PRO", os.path.join(HERE, "recorder.kicad_pro"))
PLACEMENT = os.path.join(HERE, "placement.json")
LOCK = os.path.join(HERE, "~recorder.kicad_pcb.lck")
SKIP_LOCK = os.environ.get("PSV_ROUTE_SKIP_LOCK") == "1"

# Analog island on F.Cu: an AGND pour, no F.Cu VDD33 and no F.Cu GND.
# In1.Cu (GND) sits between F.Cu and the In2.Cu VDD33 plane, so the analog
# copper never faces the digital supply even though In2 spans the board.
# 3V3A is routed as traces; it used to be a second pour over the identical
# rectangle at a higher priority, which simply swallowed the AGND pour.
ANALOG = (12.0, 6.0, 32.0, 38.0)

PLANE_NETS = {"GND", "VDD33", "/Audio/AGND"}

# Local F.Cu VDD33 patches around the bulk decoupling only. In2.Cu is the plane.
VDD33_ISLANDS = (
    (22.8, -26.8, 26.2, -16.8, "VDD33_F_C1C3"),
    (-22.5, -42.2, -18.5, -37.8, "VDD33_F_C8"),
    (-13.0, -13.8, -9.0, -10.2, "VDD33_F_C14"),
)

STITCH_OFFSETS = (
    (1.1, 0.0),
    (-1.1, 0.0),
    (0.0, 1.1),
    (0.0, -1.1),
    (0.9, 0.9),
    (-0.9, 0.9),
    (0.9, -0.9),
    (-0.9, -0.9),
    (1.6, 0.0),
    (-1.6, 0.0),
    (0.0, 1.6),
    (0.0, -1.6),
    (1.4, 0.8),
    (-1.4, 0.8),
    (1.4, -0.8),
    (-1.4, -0.8),
    (2.0, 0.0),
    (-2.0, 0.0),
    (0.0, 2.0),
    (0.0, -2.0),
)

CLEARANCE = 0.15
HOLE_CLEARANCE = 0.30
HOLE_TO_HOLE = 0.25
EDGE_CLEAR = 0.35
VIA_SIZE = 0.60
VIA_DRILL = 0.30


def via_width(via):
    """KiCad 10 vias are per-layer; the no-arg GetWidth() asserts."""
    return via.GetFrontWidth()
HOLE_R = 2.1
DEFAULT_WIDTH = 0.15
USB_WIDTH = 0.20
POWER_WIDTH = 0.30
ZONE_CLEARANCE = 0.20

# Same list as NETCLASS_PATTERNS "POWER" in generate_pcb.py: the rails that
# carry charge current rather than logic.
POWER_NETS = {"VBUS", "VBUS_CHG", "VBAT", "VSYS", "/Power/3V3_RAW", "3V3A"}


def vec(x_mm, y_mm):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm))


def mm(pt):
    return pcbnew.ToMM(pt.x), pcbnew.ToMM(pt.y)


def in_analog(x, y):
    x0, y0, x1, y1 = ANALOG
    return x0 <= x <= x1 and y0 <= y <= y1


def in_charger_keep(x, y):
    """Skip the GND stitch grid over the BQ24073 body.

    H2 sits 3 mm east of U3, so a 6 mm grid via lands on the QFN or crowds
    an ISET pad. The EP gets its own 0.6/0.3 via in fanout_charger.
    """
    return 16.0 <= x <= 27.0 and -42.0 <= y <= -27.0


def ensure_closed():
    if SKIP_LOCK:
        return
    if os.path.isfile(LOCK):
        raise SystemExit(
            "recorder.kicad_pcb is locked. Close the recorder project in "
            "KiCad 10, then run this script again. Writing the board while "
            "it is open would fight the editor."
        )


def net_of(board, name):
    info = board.FindNet(name)
    if info is None or info.GetNetCode() <= 0:
        raise SystemExit(f"board has no net {name!r}")
    return info


def pad_xy(pad):
    return mm(pad.GetPosition())


def pad_wh(pad):
    size = pad.GetSize()
    return pcbnew.ToMM(size.x), pcbnew.ToMM(size.y)


def is_npth(pad):
    return pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH


def copper_pads(board):
    out = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if is_npth(pad):
                continue
            name = pad.GetNetname()
            if not name or name.startswith("unconnected-"):
                continue
            out.append((fp, pad, name))
    return out


# ---------------------------------------------------------------------------
# Copper primitives
# ---------------------------------------------------------------------------


def add_rect_zone(board, net, layer, x0, y0, x1, y1, name, priority):
    return add_poly_zone(
        board,
        net,
        layer,
        ((x0, y0), (x1, y0), (x1, y1), (x0, y1)),
        name,
        priority,
    )


def add_poly_zone(board, net, layer, points, name, priority):
    zone = pcbnew.ZONE(board)
    zone.SetLayer(layer)
    if net is not None:
        zone.SetNet(net)
    zone.SetAssignedPriority(priority)
    zone.SetLocalClearance(pcbnew.FromMM(ZONE_CLEARANCE))
    zone.SetMinThickness(pcbnew.FromMM(0.20))
    # Solid pad connections. Thermal spokes tripped starved_thermal on every
    # pad the pour could only reach from one side, and the board is reflowed.
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    # Drop fill fragments that no pad or via reaches. On a stitched plane the
    # leftovers are slivers between via barrels, and DRC counts each one as an
    # unconnected item.
    zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    zone.SetZoneName(name)
    outline = zone.Outline()
    outline.NewOutline()
    for x, y in points:
        outline.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    board.Add(zone)
    return zone


# Copper this script placed by hand. KiCad's Specctra export writes locked
# items as "(type fix)", which freerouting honours, so the connector escape
# and the fine-pitch fanout survive the autorouter instead of being ripped up
# and left as orphan stubs. The set is also what keeps the repair loop's
# rip-up from cutting the very fanout it depends on.
PROTECTED = set()


def _seg_key(x0, y0, x1, y1, layer):
    a = (round(x0, 3), round(y0, 3))
    b = (round(x1, 3), round(y1, 3))
    return (layer,) + (a + b if a <= b else b + a)


def relock(board):
    """Re-apply protection after a Specctra round trip rebuilds the tracks."""
    count = 0
    for item in board.GetTracks():
        if isinstance(item, pcbnew.PCB_VIA):
            x, y = mm(item.GetPosition())
            key = ("via", round(x, 3), round(y, 3))
        else:
            key = _seg_key(*mm(item.GetStart()), *mm(item.GetEnd()),
                           item.GetLayer())
        if key in PROTECTED:
            item.SetLocked(True)
            count += 1
    return count


def add_track(board, net, x0, y0, x1, y1, layer, width, protect=False):
    if x0 == x1 and y0 == y1:
        return None
    if protect:
        PROTECTED.add(_seg_key(x0, y0, x1, y1, layer))
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(vec(x0, y0))
    track.SetEnd(vec(x1, y1))
    track.SetLayer(layer)
    track.SetWidth(pcbnew.FromMM(width))
    track.SetNet(net)
    board.Add(track)
    return track


def add_via(board, net, x, y, protect=False):
    if protect:
        PROTECTED.add(("via", round(x, 3), round(y, 3)))
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(vec(x, y))
    via.SetFrontWidth(pcbnew.FromMM(VIA_SIZE))
    via.SetWidth(pcbnew.F_Cu, pcbnew.FromMM(VIA_SIZE))
    via.SetWidth(pcbnew.B_Cu, pcbnew.FromMM(VIA_SIZE))
    via.SetDrill(pcbnew.FromMM(VIA_DRILL))
    via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNet(net)
    board.Add(via)
    return via


def add_via_custom(board, net, x, y, size, drill, protect=False):
    """A via smaller than the 0.6 / 0.3 default. JLC still allows 0.55 / 0.25."""
    if protect:
        PROTECTED.add(("via", round(x, 3), round(y, 3)))
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(vec(x, y))
    via.SetFrontWidth(pcbnew.FromMM(size))
    via.SetWidth(pcbnew.F_Cu, pcbnew.FromMM(size))
    via.SetWidth(pcbnew.B_Cu, pcbnew.FromMM(size))
    via.SetDrill(pcbnew.FromMM(drill))
    via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNet(net)
    board.Add(via)
    return via


def clear_copper(board, tracks=True):
    # Delete, not Remove. KiCad 10 SWIG marks vias as owned after a
    # previous SaveBoard/LoadBoard, and Remove then trips thisown.
    if tracks:
        for item in list(board.GetTracks()):
            board.Delete(item)
    for zone in list(board.Zones()):
        board.Delete(zone)


def tie_u2_ep(board):
    """Belt and braces for the ES8311 exposed pad.

    Pad 21 now has an EP pin in PSV.kicad_sym, so the netlist carries it and
    generate_pcb.py assigns it. Re-assert it here so an older board file still
    lands on AGND instead of floating.
    """
    agnd = net_of(board, "/Audio/AGND")
    for fp in board.GetFootprints():
        if fp.GetReference() != "U2":
            continue
        for pad in fp.Pads():
            if pad.GetNumber() == "21" and pad.GetNetCode() != agnd.GetNetCode():
                pad.SetNet(agnd)
                print("  tied U2 pad 21 to AGND")
            return


def tie_mk1_ring(board):
    """Connect MK1's ring pad to the AGND pour.

    Pad 5 is the 0.32 mm ring around the 0.8 mm sound port. The AGND pour
    keeps ZONE_CLEARANCE off that hole and never reaches the ring. Pad 4
    is GND and sits in the pour; pad 3 is OUT− and must stay off AGND.
    A short stub from pad 4 is the electrical path to the ring.
    Freerouting leaves MK1-4 to MK1-5 open.
    """
    mk1 = board.FindFootprintByReference("MK1")
    if mk1 is None:
        return
    pads = {pad.GetNumber(): pad for pad in mk1.Pads()}
    if "4" not in pads or "5" not in pads:
        return
    agnd = net_of(board, "/Audio/AGND")
    x0, y0 = pad_xy(pads["5"])
    x1, y1 = pad_xy(pads["4"])
    add_track(board, agnd, x0, y0, x1, y1, pcbnew.F_Cu, DEFAULT_WIDTH, protect=True)


def tie_u1_edge_gnd(board, obstacles):
    """Via out U1 pad 63 before USB and fanout can box it.

    That castellation sits on the module's north-west corner. The locked USB
    pair and the I2S fanout vias later occupy every 2 mm seat around it, and
    DRC then reports an F.Cu GND sliver. A locked stub now keeps the pad on
    the plane.
    """
    fp = board.FindFootprintByReference("U1")
    if fp is None:
        return
    gnd = net_of(board, "GND")
    for pad in fp.Pads():
        if pad.GetNumber() == "63":
            pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_INHERITED)
            x, y = pad_xy(pad)
            stitch_one(board, obstacles, gnd, x, y, protect=True)
            return


def add_inner_planes(board, half_w, half_h):
    """The two solid planes. These are what GND and VDD33 pads via down to."""
    add_rect_zone(board, net_of(board, "GND"), pcbnew.In1_Cu,
                  -half_w, -half_h, half_w, half_h, "GND_In1", 0)
    add_rect_zone(board, net_of(board, "VDD33"), pcbnew.In2_Cu,
                  -half_w, -half_h, half_w, half_h, "VDD33_In2", 0)


def add_outer_pours(board, half_w, half_h):
    gnd = net_of(board, "GND")
    vdd = net_of(board, "VDD33")
    agnd = net_of(board, "/Audio/AGND")
    ax0, ay0, ax1, ay1 = ANALOG
    add_rect_zone(board, gnd, pcbnew.B_Cu, -half_w, -half_h, half_w, half_h, "GND_B", 0)
    add_rect_zone(board, gnd, pcbnew.F_Cu, -half_w, -half_h, half_w, half_h, "GND_F", 0)
    # Higher priority, so the digital F.Cu GND pour keeps out of the island.
    add_rect_zone(board, agnd, pcbnew.F_Cu, ax0, ay0, ax1, ay1, "AGND_F", 2)
    for x0, y0, x1, y1, name in VDD33_ISLANDS:
        add_rect_zone(board, vdd, pcbnew.F_Cu, x0, y0, x1, y1, name, 4)


def fill_zones(board):
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


def seg_point_dist(x0, y0, x1, y1, px, py):
    dx, dy = x1 - x0, y1 - y0
    length2 = dx * dx + dy * dy
    if length2 == 0:
        return math.hypot(px - x0, py - y0)
    t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / length2))
    return math.hypot(px - (x0 + t * dx), py - (y0 + t * dy))


def seg_seg_dist(ax0, ay0, ax1, ay1, bx0, by0, bx1, by1):
    def cross(ox, oy, px, py, qx, qy):
        return (px - ox) * (qy - oy) - (py - oy) * (qx - ox)

    d1 = cross(bx0, by0, bx1, by1, ax0, ay0)
    d2 = cross(bx0, by0, bx1, by1, ax1, ay1)
    d3 = cross(ax0, ay0, ax1, ay1, bx0, by0)
    d4 = cross(ax0, ay0, ax1, ay1, bx1, by1)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return 0.0
    return min(
        seg_point_dist(bx0, by0, bx1, by1, ax0, ay0),
        seg_point_dist(bx0, by0, bx1, by1, ax1, ay1),
        seg_point_dist(ax0, ay0, ax1, ay1, bx0, by0),
        seg_point_dist(ax0, ay0, ax1, ay1, bx1, by1),
    )


def point_in_rect(px, py, rect):
    x0, y0, x1, y1 = rect
    return x0 <= px <= x1 and y0 <= py <= y1


def seg_rect_dist(ax0, ay0, ax1, ay1, rect):
    if point_in_rect(ax0, ay0, rect) or point_in_rect(ax1, ay1, rect):
        return 0.0
    x0, y0, x1, y1 = rect
    edges = (
        (x0, y0, x1, y0),
        (x1, y0, x1, y1),
        (x1, y1, x0, y1),
        (x0, y1, x0, y0),
    )
    return min(seg_seg_dist(ax0, ay0, ax1, ay1, *e) for e in edges)


def pad_rect(pad):
    """Axis-aligned copper extent of a pad, in mm.

    GetBoundingBox() already accounts for footprint rotation, which the old
    width/height test did not: R2/R3 and every side-pin QFN pad are rotated,
    and an unrotated size test let stitch stubs graze them.
    """
    box = pad.GetBoundingBox()
    return (
        pcbnew.ToMM(box.GetLeft()),
        pcbnew.ToMM(box.GetTop()),
        pcbnew.ToMM(box.GetRight()),
        pcbnew.ToMM(box.GetBottom()),
    )


# ---------------------------------------------------------------------------
# Obstacle test for new copper
# ---------------------------------------------------------------------------


class Obstacles:
    """Everything a new via or track has to stay clear of.

    Layer aware. A B.Cu track is not in an F.Cu track's way, and only the
    drilled part of a through-hole obstructs every layer at once.
    """

    def __init__(self, board, half_w, half_h):
        self.half_w = half_w
        self.half_h = half_h
        self.pads = []      # (rect, netcode, layerset)
        self.holes = []     # (x, y, radius)
        self.tracks = []    # (x0, y0, x1, y1, half_width, netcode, layer)
        self.vias = []      # (x, y, radius, drill_radius, netcode)
        # Board slots a footprint carries on Edge.Cuts (the mid-mount USB-C
        # J2). in_bounds() only knows the outer rectangle, so without this the
        # maze would happily route copper through the hole in the board.
        self.cutouts = []   # (x0, y0, x1, y1)
        for fp in board.GetFootprints():
            edge = [item.GetBoundingBox() for item in fp.GraphicalItems()
                    if item.GetLayer() == pcbnew.Edge_Cuts]
            if edge:
                self.cutouts.append((
                    min(pcbnew.ToMM(b.GetLeft()) for b in edge),
                    min(pcbnew.ToMM(b.GetTop()) for b in edge),
                    max(pcbnew.ToMM(b.GetRight()) for b in edge),
                    max(pcbnew.ToMM(b.GetBottom()) for b in edge),
                ))
            for pad in fp.Pads():
                x, y = pad_xy(pad)
                drill = pcbnew.ToMM(pad.GetDrillSizeX())
                if drill > 0:
                    self.holes.append((x, y, drill / 2.0,
                                       -1 if is_npth(pad) else pad.GetNetCode()))
                if is_npth(pad):
                    continue
                layers = frozenset(pad.GetLayerSet().CuStack())
                self.pads.append((pad_rect(pad), pad.GetNetCode(), layers))
        for item in board.GetTracks():
            if isinstance(item, pcbnew.PCB_VIA):
                x, y = mm(item.GetPosition())
                self.vias.append((x, y, pcbnew.ToMM(via_width(item)) / 2.0,
                                  pcbnew.ToMM(item.GetDrill()) / 2.0,
                                  item.GetNetCode()))
                continue
            x0, y0 = mm(item.GetStart())
            x1, y1 = mm(item.GetEnd())
            self.tracks.append((x0, y0, x1, y1,
                                pcbnew.ToMM(item.GetWidth()) / 2.0,
                                item.GetNetCode(), item.GetLayer()))

    # -- incremental updates so a caller can place copper and keep testing --

    def add_via(self, x, y, netcode):
        self.vias.append((x, y, VIA_SIZE / 2.0, VIA_DRILL / 2.0, netcode))
        self.holes.append((x, y, VIA_DRILL / 2.0, netcode))

    def add_track(self, x0, y0, x1, y1, width, netcode, layer=pcbnew.F_Cu):
        self.tracks.append((x0, y0, x1, y1, width / 2.0, netcode, layer))

    def has_via_near(self, x, y, netcode, radius):
        """Is this pad already stitched? Keeps re-runs from stacking barrels."""
        for vx, vy, _vr, _vdr, vnet in self.vias:
            if vnet == netcode and math.hypot(x - vx, y - vy) <= radius:
                return True
        return False

    def in_bounds(self, x, y, margin):
        return abs(x) <= self.half_w - margin and abs(y) <= self.half_h - margin

    def via_fits(self, x, y, netcode):
        return self.track_fits(x, y, x, y, VIA_SIZE, netcode, layer=None)

    def track_fits(self, x0, y0, x1, y1, width, netcode, layer=pcbnew.F_Cu):
        """Clearance test for a whole segment, not just its endpoints.

        ``layer=None`` means a through-hole via: it has copper on every layer
        and a barrel that has to respect hole-to-hole everywhere.
        """
        half = width / 2.0
        drill_r = VIA_DRILL / 2.0 if layer is None else 0.0
        if not self.in_bounds(x0, y0, EDGE_CLEAR + half):
            return False
        if not self.in_bounds(x1, y1, EDGE_CLEAR + half):
            return False
        for rect in self.cutouts:
            if seg_rect_dist(x0, y0, x1, y1, rect) < EDGE_CLEAR + half:
                return False
        for hx, hy, hr, hnet in self.holes:
            d = seg_point_dist(x0, y0, x1, y1, hx, hy)
            if drill_r and d < drill_r + hr + HOLE_TO_HOLE:
                return False
            if hnet != netcode and d < half + hr + HOLE_CLEARANCE:
                return False
        for rect, pnet, layers in self.pads:
            if pnet == netcode:
                continue
            if layer is not None and layer not in layers:
                continue
            d = seg_rect_dist(x0, y0, x1, y1, rect)
            if d < half + CLEARANCE:
                return False
            if drill_r and d < drill_r + HOLE_CLEARANCE:
                return False
        for tx0, ty0, tx1, ty1, tw, tnet, tlayer in self.tracks:
            if tnet == netcode:
                continue
            if layer is not None and layer != tlayer:
                continue
            d = seg_seg_dist(x0, y0, x1, y1, tx0, ty0, tx1, ty1)
            if d < half + tw + CLEARANCE:
                return False
            if drill_r and d < drill_r + tw + HOLE_CLEARANCE:
                return False
        for vx, vy, vr, vdr, vnet in self.vias:
            d = seg_point_dist(x0, y0, x1, y1, vx, vy)
            if drill_r and d < drill_r + vdr + HOLE_TO_HOLE:
                return False
            if vnet == netcode:
                continue
            if d < half + vr + CLEARANCE:
                return False
            if d < half + vdr + HOLE_CLEARANCE:
                return False
        return True


# ---------------------------------------------------------------------------
# Fallback maze router
# ---------------------------------------------------------------------------


class MazeRouter:
    """Grid router for the handful of connections freerouting gives up on.

    Freerouting does the bulk of the board well, but it quits on the last few
    nets in the congested corners (the USB-C pad row, the codec's 0.4 mm
    pitch power pins). Rather than leave those open, rasterise the copper on
    F.Cu and B.Cu at 0.1 mm, A* through it, then straighten the result and
    re-check every segment against the exact geometry in Obstacles.

    Only F.Cu and B.Cu are routable. In1.Cu is the GND plane and In2.Cu is
    VDD33; punching signal traces through either would cut the plane.
    """

    GRID = 0.1
    VIA_COST = 40  # grid steps, so a via has to save 4 mm to be worth it
    LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)

    def __init__(self, board, obstacles, half_w, half_h):
        self.board = board
        self.ob = obstacles
        self.half_w = half_w
        self.half_h = half_h
        self.ox = -half_w
        self.oy = -half_h
        self.nx = int(round(2 * half_w / self.GRID)) + 1
        self.ny = int(round(2 * half_h / self.GRID)) + 1
        self.xs = self.ox + np.arange(self.nx) * self.GRID
        self.ys = self.oy + np.arange(self.ny) * self.GRID

    # -- grid helpers -------------------------------------------------------

    def cell(self, x, y):
        ix = int(round((x - self.ox) / self.GRID))
        iy = int(round((y - self.oy) / self.GRID))
        return min(max(ix, 0), self.nx - 1), min(max(iy, 0), self.ny - 1)

    def point(self, ix, iy):
        return self.ox + ix * self.GRID, self.oy + iy * self.GRID

    def _span(self, lo, hi, axis):
        origin = self.ox if axis == 0 else self.oy
        count = self.nx if axis == 0 else self.ny
        i0 = max(0, int(math.ceil((lo - origin) / self.GRID - 1e-9)))
        i1 = min(count - 1, int(math.floor((hi - origin) / self.GRID + 1e-9)))
        return i0, i1

    def _mark_rect(self, arr, rect, margin):
        x0, y0, x1, y1 = rect
        ix0, ix1 = self._span(x0 - margin, x1 + margin, 0)
        iy0, iy1 = self._span(y0 - margin, y1 + margin, 1)
        if ix0 <= ix1 and iy0 <= iy1:
            arr[ix0:ix1 + 1, iy0:iy1 + 1] = True

    def _mark_capsule(self, arr, x0, y0, x1, y1, radius):
        ix0, ix1 = self._span(min(x0, x1) - radius, max(x0, x1) + radius, 0)
        iy0, iy1 = self._span(min(y0, y1) - radius, max(y0, y1) + radius, 1)
        if ix0 > ix1 or iy0 > iy1:
            return
        gx = self.xs[ix0:ix1 + 1][:, None]
        gy = self.ys[iy0:iy1 + 1][None, :]
        dx, dy = x1 - x0, y1 - y0
        length2 = dx * dx + dy * dy
        if length2 == 0:
            d2 = (gx - x0) ** 2 + (gy - y0) ** 2
        else:
            t = np.clip(((gx - x0) * dx + (gy - y0) * dy) / length2, 0.0, 1.0)
            d2 = (gx - (x0 + t * dx)) ** 2 + (gy - (y0 + t * dy)) ** 2
        arr[ix0:ix1 + 1, iy0:iy1 + 1] |= d2 < radius * radius

    def _mark_border(self, arr, margin):
        ix0, ix1 = self._span(-self.half_w + margin, self.half_w - margin, 0)
        iy0, iy1 = self._span(-self.half_h + margin, self.half_h - margin, 1)
        keep = np.zeros_like(arr)
        keep[ix0:ix1 + 1, iy0:iy1 + 1] = True
        arr |= ~keep

    # -- rasterise ----------------------------------------------------------

    def rasterise(self, netcode, width):
        """Blocked masks for a track of this net, plus one for via seats."""
        half = width / 2.0
        vr, vdr = VIA_SIZE / 2.0, VIA_DRILL / 2.0
        blocked = {layer: np.zeros((self.nx, self.ny), dtype=bool)
                   for layer in self.LAYERS}
        via_blocked = np.zeros((self.nx, self.ny), dtype=bool)
        for layer in self.LAYERS:
            self._mark_border(blocked[layer], EDGE_CLEAR + half)
        self._mark_border(via_blocked, EDGE_CLEAR + vr)
        for rect in self.ob.cutouts:
            for layer in self.LAYERS:
                self._mark_rect(blocked[layer], rect, EDGE_CLEAR + half)
            self._mark_rect(via_blocked, rect, EDGE_CLEAR + vr)

        for hx, hy, hr, hnet in self.ob.holes:
            self._mark_capsule(via_blocked, hx, hy, hx, hy,
                               max(vdr + hr + HOLE_TO_HOLE,
                                   vr + hr + HOLE_CLEARANCE if hnet != netcode else 0))
            if hnet == netcode:
                continue
            for layer in self.LAYERS:
                self._mark_capsule(blocked[layer], hx, hy, hx, hy,
                                   half + hr + HOLE_CLEARANCE)

        for rect, pnet, layers in self.ob.pads:
            if pnet == netcode:
                continue
            self._mark_rect(via_blocked, rect, max(vr + CLEARANCE,
                                                   vdr + HOLE_CLEARANCE))
            for layer in self.LAYERS:
                if layer in layers:
                    self._mark_rect(blocked[layer], rect, half + CLEARANCE)

        for x0, y0, x1, y1, tw, tnet, tlayer in self.ob.tracks:
            if tnet == netcode:
                continue
            self._mark_capsule(via_blocked, x0, y0, x1, y1,
                               max(vr + tw + CLEARANCE, vdr + tw + HOLE_CLEARANCE))
            if tlayer in blocked:
                self._mark_capsule(blocked[tlayer], x0, y0, x1, y1,
                                   half + tw + CLEARANCE)

        for vx, vy, r, dr, vnet in self.ob.vias:
            self._mark_capsule(via_blocked, vx, vy, vx, vy, vdr + dr + HOLE_TO_HOLE)
            if vnet == netcode:
                continue
            self._mark_capsule(via_blocked, vx, vy, vx, vy, vr + r + CLEARANCE)
            for layer in self.LAYERS:
                self._mark_capsule(blocked[layer], vx, vy, vx, vy,
                                   max(half + r + CLEARANCE, half + dr + HOLE_CLEARANCE))
        return blocked, via_blocked

    # -- terminals ----------------------------------------------------------

    def item_cells(self, obj):
        """Grid cells that already carry this item's copper."""
        cells = set()
        if isinstance(obj, pcbnew.PCB_VIA):
            ix, iy = self.cell(*mm(obj.GetPosition()))
            return {(ix, iy, layer) for layer in self.LAYERS}
        if isinstance(obj, pcbnew.PCB_TRACK):
            if obj.GetLayer() not in self.LAYERS:
                return cells
            x0, y0 = mm(obj.GetStart())
            x1, y1 = mm(obj.GetEnd())
            steps = max(1, int(math.hypot(x1 - x0, y1 - y0) / (self.GRID / 2)))
            for i in range(steps + 1):
                t = i / steps
                ix, iy = self.cell(x0 + t * (x1 - x0), y0 + t * (y1 - y0))
                cells.add((ix, iy, obj.GetLayer()))
            return cells
        if isinstance(obj, pcbnew.PAD):
            rect = pad_rect(obj)
            layers = [l for l in self.LAYERS if obj.IsOnLayer(l)]
            ix0, ix1 = self._span(rect[0], rect[2], 0)
            iy0, iy1 = self._span(rect[1], rect[3], 1)
            for layer in layers:
                for ix in range(ix0, ix1 + 1):
                    for iy in range(iy0, iy1 + 1):
                        cells.add((ix, iy, layer))
                if not cells:
                    ix, iy = self.cell(*pad_xy(obj))
                    cells.add((ix, iy, layer))
        return cells

    # -- search -------------------------------------------------------------

    def search(self, blocked, via_blocked, starts, goals):
        if not starts or not goals:
            return None
        index = {layer: i for i, layer in enumerate(self.LAYERS)}
        flat = {layer: blocked[layer].reshape(-1) for layer in self.LAYERS}
        via_flat = via_blocked.reshape(-1)
        ny = self.ny
        plane = self.nx * self.ny

        goal_set = set()
        gx0 = gy0 = 10 ** 9
        gx1 = gy1 = -10 ** 9
        for ix, iy, layer in goals:
            if layer not in index:
                continue
            goal_set.add(ix * ny + iy + index[layer] * plane)
            gx0, gx1 = min(gx0, ix), max(gx1, ix)
            gy0, gy1 = min(gy0, iy), max(gy1, iy)
        if not goal_set:
            return None

        def heuristic(node):
            li, rest = divmod(node, plane)
            ix, iy = divmod(rest, ny)
            return (max(gx0 - ix, 0, ix - gx1) + max(gy0 - iy, 0, iy - gy1))

        best = {}
        prev = {}
        heap = []
        for ix, iy, layer in starts:
            if layer not in index:
                continue
            node = ix * ny + iy + index[layer] * plane
            if node in best:
                continue
            best[node] = 0
            heapq.heappush(heap, (heuristic(node), 0, node))
        while heap:
            _f, g, node = heapq.heappop(heap)
            if g > best.get(node, 1 << 30):
                continue
            if node in goal_set:
                return self._unwind(prev, node)
            li, rest = divmod(node, plane)
            ix, iy = divmod(rest, ny)
            layer = self.LAYERS[li]
            for dix, diy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                jx, jy = ix + dix, iy + diy
                if not (0 <= jx < self.nx and 0 <= jy < self.ny):
                    continue
                cand = jx * ny + jy + li * plane
                if flat[layer][jx * ny + jy] and cand not in goal_set:
                    continue
                ng = g + 1
                if ng < best.get(cand, 1 << 30):
                    best[cand] = ng
                    prev[cand] = node
                    heapq.heappush(heap, (ng + heuristic(cand), ng, cand))
            if not via_flat[rest]:
                for lj in range(len(self.LAYERS)):
                    if lj == li:
                        continue
                    cand = rest + lj * plane
                    if flat[self.LAYERS[lj]][rest] and cand not in goal_set:
                        continue
                    ng = g + self.VIA_COST
                    if ng < best.get(cand, 1 << 30):
                        best[cand] = ng
                        prev[cand] = node
                        heapq.heappush(heap, (ng + heuristic(cand), ng, cand))
        return None

    def _unwind(self, prev, node):
        plane = self.nx * self.ny
        path = []
        while node is not None:
            li, rest = divmod(node, plane)
            ix, iy = divmod(rest, self.ny)
            path.append((ix, iy, self.LAYERS[li]))
            node = prev.get(node)
        path.reverse()
        return path

    # -- emit ---------------------------------------------------------------

    def _straighten(self, run, netcode, width, layer):
        """Greedy shortcut pass. A* with unit step cost gives staircases."""
        out = [run[0]]
        i = 0
        while i < len(run) - 1:
            j = len(run) - 1
            while j > i + 1:
                (x0, y0), (x1, y1) = run[i], run[j]
                if self.ob.track_fits(x0, y0, x1, y1, width, netcode, layer):
                    break
                j -= 1
            out.append(run[j])
            i = j
        return out

    def emit(self, board, net, path, width):
        """Turn a grid path into tracks and vias, checking every segment."""
        netcode = net.GetNetCode()
        runs = []
        current = [path[0]]
        for prev_cell, cell in zip(path, path[1:]):
            if cell[2] != prev_cell[2]:
                runs.append(current)
                current = [cell]
            else:
                current.append(cell)
        runs.append(current)

        placed = []
        for run in runs:
            layer = run[0][2]
            pts = [self.point(ix, iy) for ix, iy, _l in run]
            pts = self._straighten(pts, netcode, width, layer)
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                if not self.ob.track_fits(x0, y0, x1, y1, width, netcode, layer):
                    return None
                placed.append(("track", x0, y0, x1, y1, layer))
        for prev_cell, cell in zip(path, path[1:]):
            if cell[2] != prev_cell[2]:
                x, y = self.point(cell[0], cell[1])
                if not self.ob.via_fits(x, y, netcode):
                    return None
                placed.append(("via", x, y))

        for entry in placed:
            if entry[0] == "track":
                _kind, x0, y0, x1, y1, layer = entry
                add_track(board, net, x0, y0, x1, y1, layer, width)
                self.ob.add_track(x0, y0, x1, y1, width, netcode, layer)
            else:
                _kind, x, y = entry
                add_via(board, net, x, y)
                self.ob.add_via(x, y, netcode)
        return placed

    def connect(self, board, net, source, target, width):
        blocked, via_blocked = self.rasterise(net.GetNetCode(), width)
        starts = self.item_cells(source)
        goals = self.item_cells(target)
        for _attempt in range(3):
            path = self.search(blocked, via_blocked, starts, goals)
            if path is None:
                return False
            if self.emit(board, net, path, width) is not None:
                return True
            # The straightened polyline failed the exact test somewhere.
            # Block the middle of the path and let A* find another way.
            mid = path[len(path) // 2]
            blocked[mid[2]][mid[0], mid[1]] = True
        return False

    # -- rip up -------------------------------------------------------------

    def reachable(self, blocked, via_blocked, starts, cap=400_000):
        """Flood fill out of a terminal, and the wall it runs into."""
        seen = set()
        queue = collections.deque()
        for cell in starts:
            if cell[2] in blocked and cell not in seen:
                seen.add(cell)
                queue.append(cell)
        wall = set()
        while queue and len(seen) < cap:
            ix, iy, layer = queue.popleft()
            for dix, diy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                jx, jy = ix + dix, iy + diy
                if not (0 <= jx < self.nx and 0 <= jy < self.ny):
                    continue
                if blocked[layer][jx, jy]:
                    wall.add((jx, jy, layer))
                    continue
                if (jx, jy, layer) in seen:
                    continue
                seen.add((jx, jy, layer))
                queue.append((jx, jy, layer))
            if via_blocked[ix, iy]:
                continue
            for other in self.LAYERS:
                if other == layer or (ix, iy, other) in seen:
                    continue
                if blocked[other][ix, iy]:
                    continue
                seen.add((ix, iy, other))
                queue.append((ix, iy, other))
        return seen, wall

    def ripup(self, board, net, terminal, width, limit=6):
        """Delete the foreign traces that box a terminal in.

        Freerouting finishes most of the board and then paints a couple of
        pads into a pocket it cannot get back out of. Whatever it laid across
        the escape is worth less than the connection it blocked, so cut the
        wall down and let the next pass re-route both.
        """
        code = net.GetNetCode()
        blocked, via_blocked = self.rasterise(code, width)
        _seen, wall = self.reachable(blocked, via_blocked,
                                     self.item_cells(terminal))
        if not wall:
            return 0
        live = [t for t in board.GetTracks()
                if not isinstance(t, pcbnew.PCB_VIA)
                and t.GetNetCode() != code and not t.IsLocked()]
        votes = {}
        keep = {}
        for ix, iy, layer in wall:
            x, y = self.point(ix, iy)
            for track in live:
                if track.GetLayer() != layer:
                    continue
                uuid = track.m_Uuid.AsString()
                reach = (width + pcbnew.ToMM(track.GetWidth())) / 2.0 + CLEARANCE
                x0, y0 = mm(track.GetStart())
                x1, y1 = mm(track.GetEnd())
                if seg_point_dist(x0, y0, x1, y1, x, y) <= reach + self.GRID:
                    votes[uuid] = votes.get(uuid, 0) + 1
                    keep[uuid] = track
        ranked = sorted(votes, key=votes.get, reverse=True)[:limit]
        for uuid in ranked:
            board.Delete(keep[uuid])
        return len(ranked)


# ---------------------------------------------------------------------------
# Plane stitching
# ---------------------------------------------------------------------------


def stitch_pads_to_planes(board, obstacles, half_w, half_h):
    """Give every VDD33 pad, and every GND pad in the analog island, a via.

    VDD33 lives on In2 and GND on In1, so an F.Cu pad of either net needs a
    barrel to reach its plane. Digital GND pads sit in the F.Cu GND pour and
    do not. GND pads inside the analog island do, because the F.Cu copper
    there is AGND.
    """
    gnd = net_of(board, "GND")
    vdd = net_of(board, "VDD33")
    placed = 0
    for _fp, pad, name in copper_pads(board):
        x, y = pad_xy(pad)
        if name == "VDD33":
            net = vdd
        elif name == "GND" and in_analog(x, y):
            net = gnd
        else:
            continue
        if obstacles.has_via_near(x, y, net.GetNetCode(), 2.2):
            continue
        if stitch_one(board, obstacles, net, x, y):
            placed += 1
    return placed


def stitch_one(board, obstacles, net, x, y, layer=pcbnew.F_Cu, protect=False):
    """Drop a via next to (x, y) and run a stub to it.

    The stub itself is clearance-checked, not just the via seat. Checking only
    the barrel is what put a GND stub across U2 pad 4 and another across U6
    pad 8: both vias sat in clear copper and both stubs shorted a pad on the
    way there.
    """
    code = net.GetNetCode()
    for dx, dy in STITCH_OFFSETS:
        vx, vy = x + dx, y + dy
        if not obstacles.via_fits(vx, vy, code):
            continue
        stub = math.hypot(dx, dy) > 0.01
        if stub and not obstacles.track_fits(x, y, vx, vy, DEFAULT_WIDTH, code, layer):
            continue
        add_via(board, net, vx, vy, protect=protect)
        obstacles.add_via(vx, vy, code)
        if stub:
            add_track(board, net, x, y, vx, vy, layer, DEFAULT_WIDTH,
                      protect=protect)
            obstacles.add_track(x, y, vx, vy, DEFAULT_WIDTH, code, layer)
        return True
    return False


def stitch_grid(board, obstacles, half_w, half_h, pitch=6.0):
    """GND barrels tying F.Cu / B.Cu pours to the In1 plane."""
    gnd = net_of(board, "GND")
    code = gnd.GetNetCode()
    placed = 0
    x = -half_w + 3.0
    while x < half_w - 3.0:
        y = -half_h + 3.0
        while y < half_h - 3.0:
            if in_charger_keep(x, y):
                y += pitch
                continue
            if not in_analog(x, y) and obstacles.via_fits(x, y, code):
                add_via(board, gnd, x, y)
                obstacles.add_via(x, y, code)
                placed += 1
            y += pitch
        x += pitch
    return placed


def stitch_orphan_gnd_pads(board, obstacles):
    """Via out any F.Cu GND pad sitting in a pour sliver that cannot hold a via.

    Island removal keeps a fragment that still touches a pad. U1's module-edge
    GND castellations do that: the pour around the pad is smaller than a
    0.6 mm barrel, so via_in_zone cannot land, and DRC reports GND_F to itself.
    """
    gnd = net_of(board, "GND")
    zone = None
    for item in board.Zones():
        if item.GetZoneName() == "GND_F":
            zone = item
            break
    if zone is None or not zone.HasFilledPolysForLayer(pcbnew.F_Cu):
        return 0
    polys = zone.GetFilledPolysList(pcbnew.F_Cu)
    seats = [(vx, vy) for vx, vy, _r, _dr, vnet in obstacles.vias
             if vnet == gnd.GetNetCode()]
    placed = 0
    for i in range(polys.OutlineCount()):
        if any(polys.Contains(vec(vx, vy), i) for vx, vy in seats):
            continue
        for _fp, pad, name in copper_pads(board):
            if name != "GND" or not pad.IsOnLayer(pcbnew.F_Cu):
                continue
            if not polys.Contains(pad.GetPosition(), i):
                continue
            x, y = pad_xy(pad)
            if stitch_one(board, obstacles, gnd, x, y):
                placed += 1
            break
    return placed


def stitch_islands(board, obstacles, half_w, half_h):
    """One via per F.Cu VDD33 patch and a few inside the AGND island.

    The AGND pour is the analog return; it has to reach the In1 GND plane
    through Ragnd, but the pour itself also wants barrels so it is not one
    long thin sheet. Those go on AGND, not GND: AGND and GND meet only at
    Ragnd, so an AGND via lands on the AGND net and stops at F.Cu/B.Cu.
    """
    vdd = net_of(board, "VDD33")
    placed = 0
    for x0, y0, x1, y1, _name in VDD33_ISLANDS:
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        if obstacles.via_fits(cx, cy, vdd.GetNetCode()):
            add_via(board, vdd, cx, cy)
            obstacles.add_via(cx, cy, vdd.GetNetCode())
            placed += 1
    return placed


# ---------------------------------------------------------------------------
# USB-C connector escape
# ---------------------------------------------------------------------------


# STALE for the dev / USB-C variant: these numbers are the earlier top-mount
# TYPE-C-31-M-12 spin. The board now has a mid-mount TYPE-C-31-M-13C J2 at
# (7.0, -38.1) rot 180 with its contact row at y = -35.48, hand-escaped and
# locked on the board (lanes to y = -33.725, 0.8 mm fan, D+ joined on B.Cu,
# VBUS dives at y = -34.375). Re-derive these from the board before a full
# re-route; --repair-only and --finish-only never call usb_escape().
#
# Old note: J2 sat at (8.0, -39.15) rotated 180 so the mouth is on y = -42.8. The
# 16 SMD contacts are then one row at y = -35.105, already north of the
# two 0.65 mm board-lock NPTH at y = -36.55. Climb +Y; do not dive south
# through the locks. Same topology as the 64 x 86 board: climb, fan the
# 0.5 mm data row out to 0.8 mm, D- joins on F.Cu, D+ vias 0.6 mm north
# of that fan so a 0.6 mm barrel clears the other net. VBUS dives first
# so its vias are never on the CC bus.
VBUS_VIA_Y = -34.00
J2_LANE_TOP = -33.40
J2_FAN_Y = -32.90
DP_LINK_Y = -32.40
DM_WEST_Y = -31.80

# Escape lane per contact: pad number -> x the trace climbs at. On this
# rotation that x is the pad's own centre.
J2_LANES = {
    "A9": ("VBUS", 5.55),
    "B5": ("CC2", 6.25),
    "B6": ("USB_DP", 7.25),
    "A7": ("USB_DM", 7.75),
    "A6": ("USB_DP", 8.25),
    "B7": ("USB_DM", 8.75),
    "A5": ("CC1", 9.25),
    "A4": ("VBUS", 10.45),
}

# 0.8 mm fan. D+ lands on 6.70 / 8.30 (via pair). D- on 7.50 / 9.10.
J2_FAN = {"B6": 6.70, "A7": 7.50, "A6": 8.30, "B7": 9.10}

CC2_PAD = (3.825, -32.900)
CC1_PAD = (11.675, -32.600)
F1_VBUS = (15.100, -39.013)
F1_VIA = (15.100, -38.20)
U7_VBUS_VIA = (7.95, -31.00)
U7_VBUS_PAD = (7.950, -30.738)
VBUS_AROUND = 1.50


def usb_escape(board, obstacles):
    """Hand-route everything that leaves the USB-C footprint.

    J2 is rotated 180, so the contact row sits at y = -35.105, already north
    of the board-lock NPTH. VBUS dives at VBUS_VIA_Y. CC1/CC2 run out at
    J2_LANE_TOP to R2/R3. The data pair fans to 0.8 mm; D- stays on F.Cu,
    D+ joins on B.Cu. U7 is a tap the autorouter can still reach, not a
    series hop in this escape.
    """
    pads = {}
    for fp in board.GetFootprints():
        if fp.GetReference() != "J2":
            continue
        for pad in fp.Pads():
            pads.setdefault(pad.GetNumber(), pad_xy(pad))
    missing = [n for n in J2_LANES if n not in pads]
    if missing:
        print(f"  warning: J2 pads {missing} not found, skipping USB escape")
        return

    def run(net, points, layer, width):
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            add_track(board, net, x0, y0, x1, y1, layer, width, protect=True)
            obstacles.add_track(x0, y0, x1, y1, width, net.GetNetCode(), layer)

    def drop(net, x, y):
        add_via(board, net, x, y, protect=True)
        obstacles.add_via(x, y, net.GetNetCode())

    nets = {name: net_of(board, name)
            for name in ("VBUS", "CC1", "CC2", "USB_DP", "USB_DM")}
    vbus, dp, dm = nets["VBUS"], nets["USB_DP"], nets["USB_DM"]

    for number, (name, lane) in J2_LANES.items():
        px, py = pads[number]
        if name == "VBUS":
            run(vbus, [(px, py), (lane, VBUS_VIA_Y)], pcbnew.F_Cu, POWER_WIDTH)
            drop(vbus, lane, VBUS_VIA_Y)
            continue
        width = USB_WIDTH if name.startswith("USB_") else DEFAULT_WIDTH
        run(nets[name], [(px, py), (lane, J2_LANE_TOP)], pcbnew.F_Cu, width)

    run(nets["CC2"], [(J2_LANES["B5"][1], J2_LANE_TOP),
                      (CC2_PAD[0], J2_LANE_TOP), CC2_PAD],
        pcbnew.F_Cu, DEFAULT_WIDTH)
    run(nets["CC1"], [(J2_LANES["A5"][1], J2_LANE_TOP),
                      (CC1_PAD[0], J2_LANE_TOP), CC1_PAD],
        pcbnew.F_Cu, DEFAULT_WIDTH)

    vx_w, vx_e = J2_LANES["A9"][1], J2_LANES["A4"][1]
    run(vbus, [(vx_w, VBUS_VIA_Y), (vx_e, VBUS_VIA_Y),
               (F1_VIA[0], VBUS_VIA_Y), F1_VIA],
        pcbnew.B_Cu, POWER_WIDTH)
    drop(vbus, *F1_VIA)
    run(vbus, [F1_VIA, F1_VBUS], pcbnew.F_Cu, POWER_WIDTH)
    # West of R3, then east on B.Cu north of the D+ join, up to U7 pad 5.
    run(vbus, [(vx_w, VBUS_VIA_Y), (VBUS_AROUND, VBUS_VIA_Y),
               (VBUS_AROUND, U7_VBUS_VIA[1]), U7_VBUS_VIA],
        pcbnew.B_Cu, POWER_WIDTH)
    drop(vbus, *U7_VBUS_VIA)
    run(vbus, [U7_VBUS_VIA, U7_VBUS_PAD], pcbnew.F_Cu, POWER_WIDTH)

    for number, x in J2_FAN.items():
        name, lane = J2_LANES[number]
        run(nets[name], [(lane, J2_LANE_TOP), (x, J2_FAN_Y)],
            pcbnew.F_Cu, USB_WIDTH)
    run(dm, [(J2_FAN["A7"], J2_FAN_Y), (J2_FAN["A7"], DM_WEST_Y),
             (J2_FAN["B7"], DM_WEST_Y), (J2_FAN["B7"], J2_FAN_Y)],
        pcbnew.F_Cu, USB_WIDTH)
    for number in ("A6", "B6"):
        x = J2_FAN[number]
        run(dp, [(x, J2_FAN_Y), (x, DP_LINK_Y)], pcbnew.F_Cu, USB_WIDTH)
        drop(dp, x, DP_LINK_Y)
    run(dp, [(J2_FAN["A6"], DP_LINK_Y), (J2_FAN["B6"], DP_LINK_Y)],
        pcbnew.B_Cu, USB_WIDTH)


# Lanes for the long haul from the connector up to the MCU. U1's USB pads
# sit on the module's top row. D+ stays on B.Cu until it is west of U7,
# then both lines run F.Cu up the 4.80 / 5.20 pair and in along the row.
USB_PAIR_PITCH = 0.40
USB_DP_LANE = 4.80
USB_DM_LANE = 5.20
USB_DP_ROW = -9.85
USB_DM_ROW = -10.25


def usb_pair_to_mcu(board, obstacles):
    """Carry D+/D- from the connector escape to U1 as one coupled pair.

    D- westbound is north of the D+ vias, so it rides F.Cu over them. D+
    stays on the B.Cu join until the west lane. Do not cut back under U7
    on F.Cu at the TVS pad row: those pads hang to y = -31.40.
    """
    dp, dm = net_of(board, "USB_DP"), net_of(board, "USB_DM")

    def run(net, points, layer):
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            add_track(board, net, x0, y0, x1, y1, layer, USB_WIDTH, protect=True)
            obstacles.add_track(x0, y0, x1, y1, USB_WIDTH, net.GetNetCode(), layer)

    run(dp, [(J2_FAN["A6"], DP_LINK_Y), (USB_DP_LANE, DP_LINK_Y)],
        pcbnew.B_Cu)
    add_via(board, dp, USB_DP_LANE, DP_LINK_Y, protect=True)
    obstacles.add_via(USB_DP_LANE, DP_LINK_Y, dp.GetNetCode())
    run(dp, [(USB_DP_LANE, DP_LINK_Y), (USB_DP_LANE, USB_DP_ROW),
             (14.85, USB_DP_ROW), (14.85, -11.00)], pcbnew.F_Cu)

    run(dm, [(J2_FAN["B7"], J2_FAN_Y), (J2_FAN["B7"], DM_WEST_Y),
             (USB_DM_LANE, DM_WEST_Y), (USB_DM_LANE, USB_DM_ROW),
             (14.00, USB_DM_ROW), (14.00, -11.00)], pcbnew.F_Cu)


def stitch_rstat_vdd(board, obstacles):
    """Drop Rstat's VDD33 pin onto the In2 plane.

    The C1/C3 F.Cu island stops at y = -26.8. Rstat sits at y = -35.8, so
    a via next to pin 1 is shorter than a trace up that aisle.
    """
    vdd = net_of(board, "VDD33")
    pad = (24.775, -35.80)
    via = (23.55, -35.80)
    add_track(board, vdd, pad[0], pad[1], via[0], via[1],
              pcbnew.F_Cu, DEFAULT_WIDTH, protect=True)
    obstacles.add_track(pad[0], pad[1], via[0], via[1],
                        DEFAULT_WIDTH, vdd.GetNetCode(), pcbnew.F_Cu)
    add_via(board, vdd, via[0], via[1], protect=True)
    obstacles.add_via(via[0], via[1], vdd.GetNetCode())


def stitch_sw_gnd(board, obstacles):
    """Tie F.Cu and B.Cu GND in the empty south-west corner."""
    gnd = net_of(board, "GND")
    x, y = -27.2, -41.0
    if not obstacles.via_fits(x, y, gnd.GetNetCode()):
        return
    add_via(board, gnd, x, y, protect=True)
    obstacles.add_via(x, y, gnd.GetNetCode())


# ---------------------------------------------------------------------------
# Fine-pitch fanout
# ---------------------------------------------------------------------------

FANOUT_PITCH = 0.45
FANOUT_STRAIGHT = 0.35
# (splay, reach). Tried in order; the first that clears everything wins.
# 2.0 x 1.45 mm is the shape that leaves room for a via at the end. The
# shorter and straighter fallbacks are for pins with a neighbour parked in
# the landing zone, where a stub with no via still beats no escape at all.
FANOUT_SHAPES = ((2.0, 1.45), (2.5, 1.75), (1.5, 1.45), (2.0, 1.05),
                 (1.0, 1.45), (1.0, 0.9), (1.0, 0.6))


def _fanout_groups(fp):
    """Pads of one footprint bucketed by which way they point.

    Returns side -> list of (pad, outward unit vector, half length along it).
    Square pads (an exposed thermal pad) have no outward direction and are
    left out; they sit under the part and reach copper through the pour.
    """
    fx, fy = mm(fp.GetPosition())
    groups = {}
    for pad in fp.Pads():
        if is_npth(pad):
            continue
        name = pad.GetNetname()
        if not name or name.startswith("unconnected-"):
            continue
        x0, y0, x1, y1 = pad_rect(pad)
        w, h = x1 - x0, y1 - y0
        if abs(w - h) < 0.05:
            continue
        px, py = pad_xy(pad)
        if w > h:
            side = "left" if px < fx else "right"
            out = (-1.0, 0.0) if px < fx else (1.0, 0.0)
            reach = w / 2.0
        else:
            side = "bottom" if py < fy else "top"
            out = (0.0, -1.0) if py < fy else (0.0, 1.0)
            reach = h / 2.0
        groups.setdefault(side, []).append((pad, out, reach))
    return groups


def fine_pitch_footprints(board):
    for fp in board.GetFootprints():
        pads = [p for p in fp.Pads() if not is_npth(p)]
        if len(pads) < 4:
            continue
        points = [pad_xy(p) for p in pads]
        pitch = min(
            math.hypot(a[0] - b[0], a[1] - b[1])
            for i, a in enumerate(points) for b in points[i + 1:]
        )
        if pitch < FANOUT_PITCH:
            yield fp


def _already_escaped(board, pad):
    """Does a same-net trace already start on this pad?"""
    px, py = pad_xy(pad)
    code = pad.GetNetCode()
    for track in board.GetTracks():
        if isinstance(track, pcbnew.PCB_VIA) or track.GetNetCode() != code:
            continue
        for end in (track.GetStart(), track.GetEnd()):
            ex, ey = mm(end)
            if math.hypot(ex - px, ey - py) < 0.02:
                return True
    return False


def fanout_fine_pitch(board, obstacles):
    """Walk every fine-pitch pad out to a ring the autorouter can work in.

    On the ES8311's QFN-20 the pads are 0.4 mm apart, which fits a 0.15 mm
    trace and its clearance but nothing else: one foreign trace laid across
    the row walls the rest of that side into a pocket. Freerouting did
    exactly that and then called I2C_SDA, I2S_WS, AOUTP and AOUTN
    unroutable. So each pin gets escaped radially before the autorouter sees
    the board, splayed to 0.8 mm, and dropped on a via at the end. The via is
    the point: it puts all 20 codec pins on B.Cu as well, and B.Cu in this
    corner is a GND pour with almost nothing else in it.

    Safe to call again after a rip-up. Pads that still have their stub are
    skipped, so cut ones grow back.
    """
    stubs = vias = 0
    for fp in fine_pitch_footprints(board):
        for side, members in _fanout_groups(fp).items():
            axis = 1 if side in ("left", "right") else 0
            centre = sum(pad_xy(p)[axis] for p, _o, _r in members) / len(members)
            for pad, out, reach in members:
                if _already_escaped(board, pad):
                    continue
                net = board.FindNet(pad.GetNetname())
                px, py = pad_xy(pad)
                along = px if axis == 0 else py
                code = net.GetNetCode()
                knee = (px + out[0] * (reach + FANOUT_STRAIGHT),
                        py + out[1] * (reach + FANOUT_STRAIGHT))
                path = None
                for splay, extent in FANOUT_SHAPES:
                    far = centre + (along - centre) * splay
                    tip = (px + out[0] * (reach + extent),
                           py + out[1] * (reach + extent))
                    tip = (far, tip[1]) if axis == 0 else (tip[0], far)
                    candidate = [(px, py), knee, tip]
                    if all(obstacles.track_fits(a[0], a[1], b[0], b[1],
                                                DEFAULT_WIDTH, code, pcbnew.F_Cu)
                           for a, b in zip(candidate, candidate[1:])):
                        path = candidate
                        end = tip
                        break
                if path is None:
                    continue
                for a, b in zip(path, path[1:]):
                    add_track(board, net, a[0], a[1], b[0], b[1],
                              pcbnew.F_Cu, DEFAULT_WIDTH, protect=True)
                    obstacles.add_track(a[0], a[1], b[0], b[1],
                                        DEFAULT_WIDTH, code, pcbnew.F_Cu)
                stubs += 1
                if obstacles.via_fits(end[0], end[1], code):
                    add_via(board, net, end[0], end[1], protect=True)
                    obstacles.add_via(end[0], end[1], code)
                    vias += 1
    return stubs, vias


# Pin-number escapes assume rot=0. Derive the way out from the pad vs the
# body centre so a 180° rotation still leaves H2 alone.
def u3_escape_vec(px, py, fx, fy):
    dx, dy = px - fx, py - fy
    if dx > 0.7 and abs(dx) >= abs(dy) - 0.05:
        return (0.0, 1.0)
    if abs(dx) >= abs(dy):
        return (1.0 if dx > 0 else -1.0, 0.0)
    return (0.0, 1.0 if dy > 0 else -1.0)

U3_TIES = (("2", "3"), ("10", "11"))


def _lock(track):
    if track is not None:
        track.SetLocked(True)
    return track


def fanout_charger(board, obstacles, protect=False):
    """Walk the BQ24073 pads out so the pour repair can reach them.

    Ties and the EP via first, then the short links to nearby passives.
    Stubs are last, and only for pads the links did not already reach. H2
    sits 3 mm east of U3, so the east row leaves south or north instead of
    into the mounting hole. North stubs get no via: C5 leaves no 0.6 mm
    barrel. The stock ThermalVias land used 0.2 mm EP drills; this board
    holds 0.3 mm, so a single 0.6/0.3 via lands on the EP.
    """
    u3 = None
    for fp in board.GetFootprints():
        if fp.GetReference() == "U3":
            u3 = fp
            break
    if u3 is None:
        return 0, 0
    pads = {}
    for pad in u3.Pads():
        num = pad.GetNumber()
        if num:
            pads.setdefault(num, pad)

    stubs = vias = 0
    for a_num, b_num in U3_TIES:
        a, b = pads.get(a_num), pads.get(b_num)
        if a is None or b is None:
            continue
        net = board.FindNet(a.GetNetname())
        if net is None:
            continue
        ax, ay = pad_xy(a)
        bx, by = pad_xy(b)
        if obstacles.track_fits(ax, ay, bx, by, DEFAULT_WIDTH, net.GetNetCode(),
                                pcbnew.F_Cu):
            t = add_track(board, net, ax, ay, bx, by, pcbnew.F_Cu,
                          DEFAULT_WIDTH, protect=protect)
            if protect:
                _lock(t)
            obstacles.add_track(ax, ay, bx, by, DEFAULT_WIDTH,
                                net.GetNetCode(), pcbnew.F_Cu)
            stubs += 1

    gnd = net_of(board, "GND")
    cx, cy = mm(u3.GetPosition())
    if not obstacles.has_via_near(cx, cy, gnd.GetNetCode(), 1.2):
        if obstacles.via_fits(cx, cy, gnd.GetNetCode()):
            via = add_via(board, gnd, cx, cy, protect=protect)
            if protect:
                _lock(via)
            obstacles.add_via(cx, cy, gnd.GetNetCode())
            vias += 1

    linked = hand_route_charger(board, obstacles, protect)
    if linked:
        print(f"  charger links: {linked}")

    fx, fy = mm(u3.GetPosition())
    for num, pad in pads.items():
        # 4 CE and 5 EN2 are already tied to ground. 7 is PGOOD, left open.
        # 8 VSS and 17 the thermal pad are ground and already poured.
        if not num or num in ("4", "5", "7", "8", "17"):
            continue
        name = pad.GetNetname()
        if not name or name in ("GND",) or name.startswith("unconnected"):
            continue
        if _already_escaped(board, pad):
            continue
        net = board.FindNet(name)
        if net is None:
            continue
        px, py = pad_xy(pad)
        ox, oy = u3_escape_vec(px, py, fx, fy)
        x0, y0, x1, y1 = pad_rect(pad)
        reach = (x1 - x0) / 2.0 if ox else (y1 - y0) / 2.0
        end = (px + ox * (reach + 0.45), py + oy * (reach + 0.45))
        code = net.GetNetCode()
        if not obstacles.track_fits(px, py, end[0], end[1], DEFAULT_WIDTH,
                                    code, pcbnew.F_Cu):
            continue
        t = add_track(board, net, px, py, end[0], end[1], pcbnew.F_Cu,
                      DEFAULT_WIDTH, protect=protect)
        if protect:
            _lock(t)
        obstacles.add_track(px, py, end[0], end[1], DEFAULT_WIDTH, code,
                            pcbnew.F_Cu)
        stubs += 1
        if ox > 0 or oy < 0:
            continue
        if obstacles.via_fits(end[0], end[1], code):
            via = add_via(board, net, end[0], end[1], protect=protect)
            if protect:
                _lock(via)
            obstacles.add_via(end[0], end[1], code)
            vias += 1

    print(f"  charger island: {stubs} stubs, {vias} vias")
    return stubs, vias


def pad_of(board, ref, number):
    for fp in board.GetFootprints():
        if fp.GetReference() != ref:
            continue
        for pad in fp.Pads():
            if pad.GetNumber() == number:
                return pad
    return None


def _poly(board, obstacles, net, pts, width, protect, layer=None):
    if layer is None:
        layer = pcbnew.F_Cu
    code = net.GetNetCode()
    if not all(
        obstacles.track_fits(a[0], a[1], b[0], b[1], width, code, layer)
        for a, b in zip(pts, pts[1:])
    ):
        return False
    for a, b in zip(pts, pts[1:]):
        t = add_track(board, net, a[0], a[1], b[0], b[1], layer, width,
                      protect=protect)
        if protect:
            _lock(t)
        obstacles.add_track(a[0], a[1], b[0], b[1], width, code, layer)
    return True


# Rails through the charger island. VBUS climbs x=17.5 to y=-34.3, C5 sits
# at x=21, H2 at x=28.5, D2 at y=-33. Keep ISET east of the VBUS climb.
CHARGER_RAIL_X = (
    15.70, 16.00, 16.675, 18.175, 19.50, 20.175, 21.55, 21.85, 23.25,
    24.25, 24.75, 25.60, 26.30, 30.40,
)
CHARGER_RAIL_Y = (
    -41.75, -41.30, -40.50, -38.56, -37.55, -37.20, -36.85, -36.30,
    -35.50, -35.00, -34.00, -33.70, -32.80, -32.10, -31.00, -28.50,
    -27.50,
)


def _try_widths(board, obstacles, net, pts, width, protect, layer=None):
    widths = (width,) if width == DEFAULT_WIDTH else (width, DEFAULT_WIDTH)
    return any(
        _poly(board, obstacles, net, pts, w, protect, layer) for w in widths
    )


def _candidate_paths(start, end):
    ax, ay = start
    bx, by = end
    yield [start, end]
    yield [start, (bx, ay), end]
    yield [start, (ax, by), end]
    for y in CHARGER_RAIL_Y:
        yield [start, (ax, y), (bx, y), end]
    for x in CHARGER_RAIL_X:
        yield [start, (x, ay), (x, by), end]
    for x in CHARGER_RAIL_X:
        for y in CHARGER_RAIL_Y:
            yield [start, (ax, y), (x, y), (x, by), end]
            yield [start, (x, ay), (x, y), (bx, y), end]


def route_points(board, obstacles, net, start, end, width, protect):
    """F.Cu polyline search, then a same-net B.Cu hop with two vias."""
    for pts in _candidate_paths(start, end):
        if _try_widths(board, obstacles, net, pts, width, protect):
            return True
    code = net.GetNetCode()
    if obstacles.via_fits(start[0], start[1], code) and obstacles.via_fits(
        end[0], end[1], code
    ):
        for pts in _candidate_paths(start, end):
            if not _try_widths(
                board, obstacles, net, pts, width, protect, pcbnew.B_Cu
            ):
                continue
            for x, y in (start, end):
                via = add_via(board, net, x, y, protect=protect)
                if protect:
                    _lock(via)
                obstacles.add_via(x, y, code)
            return True
    return False


def _place_via(board, obstacles, net, x, y, protect):
    if not obstacles.via_fits(x, y, net.GetNetCode()):
        return False
    via = add_via(board, net, x, y, protect=protect)
    if protect:
        _lock(via)
    obstacles.add_via(x, y, net.GetNetCode())
    return True


def _via_seat(obstacles, net, x, y, radius=1.6, step=0.2):
    """Preferred XY, then a nearby ring. Keeps hop_bcu from dying on one clash."""
    code = net.GetNetCode()
    if obstacles.has_via_near(x, y, code, 0.35) or obstacles.via_fits(x, y, code):
        return (x, y)
    n = int(radius / step)
    for k in range(1, n + 1):
        for i in range(-k, k + 1):
            for j in range(-k, k + 1):
                if abs(i) != k and abs(j) != k:
                    continue
                sx, sy = x + i * step, y + j * step
                if obstacles.via_fits(sx, sy, code):
                    return (sx, sy)
    return None


def hop_bcu(board, obstacles, net, start, end, via_a, via_b, protect):
    """F.Cu to a via, B.Cu hop, F.Cu out. Used when the north F.Cu strip is full."""
    code = net.GetNetCode()
    via_a = _via_seat(obstacles, net, *via_a)
    via_b = _via_seat(obstacles, net, *via_b)
    if via_a is None or via_b is None:
        print(f"    hop {net.GetNetname()}: no via seat")
        return False
    if not obstacles.has_via_near(via_a[0], via_a[1], code, 0.35):
        if not _place_via(board, obstacles, net, via_a[0], via_a[1], protect):
            print(f"    hop {net.GetNetname()}: via A {via_a} failed")
            return False
    if not obstacles.has_via_near(via_b[0], via_b[1], code, 0.35):
        if not _place_via(board, obstacles, net, via_b[0], via_b[1], protect):
            print(f"    hop {net.GetNetname()}: via B {via_b} failed")
            return False

    def short(a, b):
        ax, ay = a
        bx, by = b
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy) or 1.0
        mid = (ax + dx / length * 0.55, ay + dy / length * 0.55)
        for pts in (
            [a, b],
            [a, mid, b],
            [a, (ax, by), b],
            [a, (bx, ay), b],
            [a, (ax, mid[1]), (bx, mid[1]), b],
        ):
            if _try_widths(board, obstacles, net, pts, DEFAULT_WIDTH, protect):
                return True
        return False

    if not short(start, via_a):
        print(f"    hop {net.GetNetname()}: F.Cu {start} -> {via_a} failed")
        return False
    if not short(via_b, end):
        print(f"    hop {net.GetNetname()}: F.Cu {via_b} -> {end} failed")
        return False
    ax, ay = via_a
    bx, by = via_b
    for pts in (
        [via_a, (ax, by), via_b],
        [via_a, (bx, ay), via_b],
        [via_a, via_b],
        [via_a, (ax, -32.0), (bx, -32.0), via_b],
        [via_a, (15.7, ay), (15.7, by), via_b],
        [via_a, (ax, -42.2), (15.7, -42.2), (15.7, by), via_b],
    ):
        if _try_widths(board, obstacles, net, pts, DEFAULT_WIDTH, protect,
                       pcbnew.B_Cu):
            return True
    print(f"    hop {net.GetNetname()}: B.Cu {via_a} -> {via_b} failed")
    return False


def hand_route_charger(board, obstacles, protect=False):
    """Short links from the BQ24073 to its nearby passives.

    U3 is rotated 180 so OUT and the programming pins face C5 and the
    resistor column. H2 still blocks the east (BAT) side. ISET stays east
    of the VBUS climb at x=17.5. Programming pins that cannot share the
    F.Cu north strip hop on B.Cu. VSYS drops onto the existing B.Cu trunk.
    VBAT follows the right-edge B.Cu channel outside the mounting-hole
    keepout, then west under the battery pads.
    """
    def xy(ref, num):
        pad = pad_of(board, ref, num)
        return None if pad is None else (pad, pad_xy(pad))

    linked = 0

    def link_pads(src, dst):
        nonlocal linked
        if src is None or dst is None:
            return False
        pad, start = src
        _dpad, end = dst
        net = board.FindNet(pad.GetNetname())
        if net is None:
            return False
        width = POWER_WIDTH if pad.GetNetname() in POWER_NETS else DEFAULT_WIDTH
        if route_points(board, obstacles, net, start, end, width, protect):
            linked += 1
            return True
        return False

    # Programming pins first, before ISET occupies the north F.Cu strip.
    u3_14, r9_1 = xy("U3", "14"), xy("R9", "1")
    if u3_14 and r9_1:
        net = board.FindNet(u3_14[0].GetNetname())
        if net is not None and hop_bcu(
            board, obstacles, net, u3_14[1], r9_1[1],
            (23.2, -36.6), (15.1, -29.1), protect,
        ):
            linked += 1
        else:
            link_pads(u3_14, r9_1)

    u3_15, r11_1 = xy("U3", "15"), xy("R11", "1")
    if u3_15 and r11_1:
        net = board.FindNet(u3_15[0].GetNetname())
        if net is not None and hop_bcu(
            board, obstacles, net, u3_15[1], r11_1[1],
            (24.6, -35.6), (19.4, -27.5), protect,
        ):
            linked += 1
        else:
            link_pads(u3_15, r11_1)

    u3_12, r8_1 = xy("U3", "12"), xy("R8", "1")
    if u3_12 and r8_1:
        net = board.FindNet(u3_12[0].GetNetname())
        if net is not None and hop_bcu(
            board, obstacles, net, u3_12[1], r8_1[1],
            (22.0, -35.2), (15.7, -31.0), protect,
        ):
            linked += 1
        else:
            link_pads(u3_12, r8_1)

    link_pads(xy("U3", "1"), xy("R10", "1"))

    u3_16, r4_1 = xy("U3", "16"), xy("R4", "1")
    if u3_16 and r4_1:
        net = board.FindNet(u3_16[0].GetNetname())
        path = [u3_16[1], (u3_16[1][0], -37.50), (r4_1[1][0], -37.50), r4_1[1]]
        if net is not None and _try_widths(
            board, obstacles, net, path, DEFAULT_WIDTH, protect
        ):
            linked += 1
        else:
            link_pads(u3_16, r4_1)

    link_pads(xy("U3", "13"), xy("C4", "1"))
    link_pads(xy("U3", "6"), xy("C4", "1"))
    link_pads(xy("U3", "7"), xy("C4", "1"))
    link_pads(xy("U3", "10"), xy("C5", "1"))
    link_pads(xy("U3", "9"), xy("D2", "2"))
    link_pads(xy("U3", "2"), xy("U3", "3"))

    vsys = net_of(board, "VSYS")
    for x, y in ((19.50, -38.56), (20.00, -38.56), (18.80, -38.56),
                 (21.00, -38.56)):
        if _place_via(board, obstacles, vsys, x, y, protect):
            c5 = xy("C5", "1")
            if c5 is not None:
                route_points(board, obstacles, vsys, c5[1], (x, y),
                             POWER_WIDTH, protect)
            u3_10 = xy("U3", "10")
            if u3_10 is not None:
                route_points(board, obstacles, vsys, u3_10[1], (x, y),
                             POWER_WIDTH, protect)
            linked += 1
            break

    vbat = net_of(board, "VBAT")
    u3_2 = xy("U3", "2")
    bt1 = xy("BT1", "1")
    via_bat = (26.20, -41.00)
    if u3_2 is not None and (
        obstacles.has_via_near(via_bat[0], via_bat[1], vbat.GetNetCode(), 0.4)
        or _place_via(board, obstacles, vbat, *via_bat, protect)
    ):
        route_points(board, obstacles, vbat, u3_2[1], via_bat, POWER_WIDTH,
                     protect)
        edge = [
            via_bat, (26.20, -42.40), (31.10, -42.40), (31.10, 32.00),
            (-23.50, 32.00), (-23.50, 34.00),
        ]
        if bt1 is not None:
            edge[-1] = bt1[1]
        if _try_widths(board, obstacles, vbat, edge, POWER_WIDTH, protect,
                       pcbnew.B_Cu) or _try_widths(
            board, obstacles, vbat, edge, DEFAULT_WIDTH, protect, pcbnew.B_Cu
        ):
            linked += 1
    return linked


# ---------------------------------------------------------------------------
# Freerouting
# ---------------------------------------------------------------------------


def find_freerouting():
    env = os.environ.get("PSV_FREEROUTING")
    if env and os.path.isfile(env):
        return env
    found = shutil.which("freerouting") or shutil.which("freerouting.exe")
    if found:
        return found
    for path in (
        os.path.expanduser("~/.local/opt/freerouting/freerouting/freerouting.exe"),
        os.path.expanduser("~/.local/opt/freerouting/bin/freerouting"),
        "/opt/freerouting/bin/freerouting",
    ):
        if os.path.isfile(path):
            return path
    raise SystemExit(
        "freerouting not found. Install it (bash scripts/setup-ubuntu.sh) or set "
        "PSV_FREEROUTING to the launcher."
    )


def run_freerouting(dsn, ses, passes=40):
    exe = find_freerouting()
    cmd = [exe, "-de", dsn, "-do", ses, "-mp", str(passes), "-mt", "1"]
    print("+", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    tail = (proc.stdout or "").strip().splitlines()[-25:]
    for line in tail:
        print("  " + line)
    if not os.path.isfile(ses):
        print(proc.stderr)
        raise SystemExit("freerouting produced no session file")


# ---------------------------------------------------------------------------
# Post-import repair
# ---------------------------------------------------------------------------


def normalise_widths(board):
    """Freerouting emits the odd sub-minimum segment. Pull them back up."""
    usb = {net_of(board, "USB_DP").GetNetCode(), net_of(board, "USB_DM").GetNetCode()}
    fixed = 0
    for track in board.GetTracks():
        if isinstance(track, pcbnew.PCB_VIA):
            continue
        floor = USB_WIDTH if track.GetNetCode() in usb else DEFAULT_WIDTH
        if track.GetWidth() < pcbnew.FromMM(floor):
            track.SetWidth(pcbnew.FromMM(floor))
            fixed += 1
    return fixed


def find_kicad_cli():
    env = os.environ.get("KICAD_CLI")
    if env and os.path.isfile(env):
        return env
    found = shutil.which("kicad-cli") or shutil.which("kicad-cli.exe")
    if found:
        return found
    sibling = os.path.join(os.path.dirname(sys.executable), "kicad-cli.exe")
    candidates = (
        sibling,
        os.path.join(os.environ.get("LOCALAPPDATA", ""),
                     "Programs", "KiCad", "10.0", "bin", "kicad-cli.exe"),
        os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"),
                     "KiCad", "10.0", "bin", "kicad-cli.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
                     "KiCad", "10.0", "bin", "kicad-cli.exe"),
    )
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def drc_json(pcb_path):
    """Read the board's DRC state, warnings included.

    This used to default to --severity-error, which made the whole repair loop
    blind to warning-level rules. Every score below compares violation counts
    before and after a change, so a rip-up or a via deletion that traded one
    error for four warnings looked like an improvement and was kept. The JLC
    pad hole-spacing rule in recorder.kicad_dru is one of those warnings.
    """
    kicad = find_kicad_cli()
    if not kicad:
        raise SystemExit("kicad-cli not found; cannot check the routed board")
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as fh:
        out = fh.name
    cmd = [kicad, "pcb", "drc", "--severity-all", "--format", "json",
           "-o", out, pcb_path]
    subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    with open(out, encoding="utf-8") as fh:
        data = json.load(fh)
    os.unlink(out)
    return data


def board_items_by_uuid(board):
    index = {}
    for track in board.GetTracks():
        index[track.m_Uuid.AsString()] = track
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            index[pad.m_Uuid.AsString()] = pad
    for zone in board.Zones():
        index[zone.m_Uuid.AsString()] = zone
    return index


SHORT_TYPES = ("shorting_items", "tracks_crossing", "solder_mask_bridge",
               "clearance", "hole_clearance", "hole_to_hole", "track_width")


def width_for(net_name):
    if net_name in ("USB_DP", "USB_DM"):
        return USB_WIDTH
    if net_name in POWER_NETS:
        return POWER_WIDTH
    return DEFAULT_WIDTH


def delete_bad_tracks(board, report):
    """Rip up any track kicad-cli calls a short, a crossing, or too tight.

    Deleting breaks the net, which the unconnected repair then re-routes
    around the obstacle it was violating. Pads and zones are never deleted:
    a pad is placement and a zone gets re-poured anyway.
    """
    index = board_items_by_uuid(board)
    doomed = {}
    for violation in report.get("violations", []):
        if violation.get("type") not in SHORT_TYPES:
            continue
        for item in violation.get("items", []):
            obj = index.get(item["uuid"])
            # Vias are tracks. A barrel sitting in a foreign pad (the NAND
            # land, the oscillator) is the same kind of short as a trace.
            if not isinstance(obj, pcbnew.PCB_TRACK):
                continue
            if obj.IsLocked():
                continue
            doomed[item["uuid"]] = obj
    for obj in doomed.values():
        board.Delete(obj)
    return len(doomed)


def repair_unconnected(board, obstacles, router, report):
    """Close whatever the pour and the autorouter left open.

    kicad-cli names both ends of each open connection with a uuid, so the
    items are easy to find again. A plane net gets a via, because the copper
    it is missing is a plane it can simply drop onto. A signal net gets a
    real path from the grid router.
    """
    planes = {net_of(board, n).GetNetCode(): net_of(board, n) for n in PLANE_NETS}
    index = board_items_by_uuid(board)
    fixed = 0
    stuck = []
    for entry in report.get("unconnected_items", []):
        items = [index.get(i["uuid"]) for i in entry.get("items", [])]
        items = [o for o in items if o is not None]
        if len(items) != 2:
            continue
        source, target = items
        net = planes.get(source.GetNetCode())
        if net is not None:
            if stitch_to_plane(board, obstacles, net, source):
                fixed += 1
                continue
            if stitch_to_plane(board, obstacles, net, target):
                fixed += 1
                continue
            # No via seat within reach of either end. Happens on the codec's
            # 0.4 mm pitch power pins, where the pad row is packed too tight
            # to drop a barrel beside it. Route out to somewhere that is.
            if router.connect(board, net, source, target, DEFAULT_WIDTH):
                print(f"    routed {source.GetNetname()} to its plane")
                fixed += 1
            else:
                stuck.append((net, source, target, DEFAULT_WIDTH))
            continue
        net = board.FindNet(source.GetNetname())
        if net is None:
            continue
        width = width_for(source.GetNetname())
        if router.connect(board, net, source, target, width):
            print(f"    routed {source.GetNetname()}")
            fixed += 1
        elif router.connect(board, net, target, source, width):
            print(f"    routed {source.GetNetname()} (reversed)")
            fixed += 1
        else:
            print(f"    could not route {source.GetNetname()}")
            stuck.append((net, source, target, width))
    return fixed, stuck


def stitch_to_plane(board, obstacles, net, obj):
    if isinstance(obj, pcbnew.PCB_VIA):
        return False
    if isinstance(obj, pcbnew.PCB_TRACK):
        return via_on_track(board, obstacles, net, obj)
    if isinstance(obj, pcbnew.PAD):
        x, y = pad_xy(obj)
        return stitch_one(board, obstacles, net, x, y)
    if isinstance(obj, pcbnew.ZONE):
        return via_in_zone(board, obstacles, net, obj)
    return False


def via_in_zone(board, obstacles, net, zone):
    """Anchor every orphan fill island of this zone to its plane.

    Island removal drops fills that nothing reaches, but a fill that touches
    one pad survives with no path to the plane underneath, and kicad-cli
    reports it as zone-to-zone open. Give each such island a barrel.
    """
    layer = zone.GetLayer()
    if layer not in (pcbnew.F_Cu, pcbnew.B_Cu):
        return False
    if not zone.HasFilledPolysForLayer(layer):
        return False
    polys = zone.GetFilledPolysList(layer)
    code = net.GetNetCode()
    seats = [(vx, vy) for vx, vy, _r, _dr, vnet in obstacles.vias if vnet == code]
    placed = 0
    for i in range(polys.OutlineCount()):
        box = polys.Outline(i).BBox()
        x0, y0 = pcbnew.ToMM(box.GetLeft()), pcbnew.ToMM(box.GetTop())
        x1, y1 = pcbnew.ToMM(box.GetRight()), pcbnew.ToMM(box.GetBottom())
        if any(polys.Contains(vec(vx, vy), i) for vx, vy in seats
               if x0 <= vx <= x1 and y0 <= vy <= y1):
            continue
        step = 0.2
        found = False
        y = y0
        while y <= y1 and not found:
            x = x0
            while x <= x1:
                if polys.Contains(vec(x, y), i) and obstacles.via_fits(x, y, code):
                    add_via(board, net, x, y)
                    obstacles.add_via(x, y, code)
                    seats.append((x, y))
                    placed += 1
                    found = True
                    break
                x += step
            y += step
    return placed > 0


def via_on_track(board, obstacles, net, track):
    """Put a via somewhere on this track's centreline."""
    x0, y0 = mm(track.GetStart())
    x1, y1 = mm(track.GetEnd())
    code = net.GetNetCode()
    steps = max(4, int(math.hypot(x1 - x0, y1 - y0) / 0.1))
    order = sorted(range(steps + 1), key=lambda i: abs(i - steps / 2.0))
    for i in order:
        t = i / steps
        x, y = x0 + t * (x1 - x0), y0 + t * (y1 - y0)
        if obstacles.via_fits(x, y, code):
            add_via(board, net, x, y)
            obstacles.add_via(x, y, code)
            return True
    return False


# ---------------------------------------------------------------------------
# Finishing
# ---------------------------------------------------------------------------


def drop_dangling_vias(board):
    """Delete vias that only land on one layer.

    The fanout pass drops an escape via next to every crowded fine-pitch pad
    before it knows which ones the router will use. Whatever the router leaves
    behind is a stub: copper and a drill hit the fab charges for, plus a
    reflection on an analog net. Locked status is ignored here on purpose,
    because these are exactly the hand-placed vias the fanout protected.
    """
    report_data = drc_json(PCB)
    index = board_items_by_uuid(board)
    doomed = []
    for violation in report_data.get("violations", []):
        if violation.get("type") != "via_dangling":
            continue
        for item in violation.get("items", []):
            obj = index.get(item["uuid"])
            if isinstance(obj, pcbnew.PCB_VIA):
                doomed.append(obj)
    if not doomed:
        return 0
    before = drc_json(PCB)
    before_score = (len(before.get("violations", [])),
                    len(before.get("unconnected_items", [])))
    with open(PCB, "rb") as fh:
        backup = fh.read()
    for via in doomed:
        board.Delete(via)
    fill_zones(board)
    save(board)
    after = drc_json(PCB)
    after_score = (len(after.get("violations", [])),
                   len(after.get("unconnected_items", [])))
    if after_score > before_score:
        # A via the checker called dangling was load bearing after all.
        print("  dangling-via cleanup broke connectivity, keeping them")
        with open(PCB, "wb") as fh:
            fh.write(backup)
        return 0
    return len(doomed)


# JLC will not drill a component pad hole closer than 0.45 mm to its
# neighbour, and plated holes carry a +0.13 / -0.08 mm tolerance, so anything
# designed under about 0.6 mm has spent its margin before the panel is drilled.
CROWDED_PAD_HOLE_MM = 0.6


def drop_vias_crowding_pads(board):
    """Delete vias that crowd a through-hole pad they only duplicate.

    A via dropped beside a through-hole pad on the same net usually adds
    nothing: the pad's own barrel already passes through every layer, so the
    via is a second drill hit buying a connection the board already has. It
    only shows up as a problem when the router parks one close enough to eat
    the pad hole-to-hole spacing. Candidates are checked one at a time and put
    back if the board needs them.
    """
    holes = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetAttribute() != pcbnew.PAD_ATTRIB_PTH:
                continue
            holes.append((pad.GetPosition(), pad.GetDrillSizeX() / 2.0,
                          pad.GetNetCode()))
    if not holes:
        return 0

    dropped = 0
    for via in [t for t in board.GetTracks() if isinstance(t, pcbnew.PCB_VIA)]:
        pos, radius, net = via.GetPosition(), via.GetDrill() / 2.0, via.GetNetCode()
        crowded = any(
            pnet == net
            and math.hypot(pcbnew.ToMM(pos.x - ppos.x),
                           pcbnew.ToMM(pos.y - ppos.y))
            - pcbnew.ToMM(radius) - pcbnew.ToMM(pradius)
            < CROWDED_PAD_HOLE_MM
            for ppos, pradius, pnet in holes
        )
        if not crowded:
            continue
        before = drc_json(PCB)
        before_score = (len(before.get("violations", [])),
                        len(before.get("unconnected_items", [])))
        with open(PCB, "rb") as fh:
            backup = fh.read()
        stubs = [t for t in board.GetTracks()
                 if not isinstance(t, pcbnew.PCB_VIA)
                 and t.GetNetCode() == net
                 and pos in (t.GetStart(), t.GetEnd())]
        board.Delete(via)
        for stub in stubs:
            board.Delete(stub)
        fill_zones(board)
        save(board)
        after = drc_json(PCB)
        after_score = (len(after.get("violations", [])),
                       len(after.get("unconnected_items", [])))
        if after_score > before_score:
            with open(PCB, "wb") as fh:
                fh.write(backup)
            board = pcbnew.LoadBoard(PCB)
            board.BuildListOfNets()
            continue
        dropped += 1
    return dropped


def hide_hole_silk(board):
    """Put Rstat's designator north of the part, off H2's silk ring.

    Moving the hole silk onto Dwgs.User made the mounting-hole footprints
    fail the library-mismatch check. Park the text instead.
    """
    for fp in board.GetFootprints():
        if fp.GetReference().startswith("H"):
            for item in fp.GraphicalItems():
                if item.GetLayer() == pcbnew.Dwgs_User:
                    item.SetLayer(pcbnew.F_SilkS)
    for fp in board.GetFootprints():
        if fp.GetReference() != "Rstat":
            continue
        ref = fp.Reference()
        ref.SetPosition(vec(24.2, -34.4))
        print("  parked Rstat silk at (24.2, -34.4)")
    for fp in board.GetFootprints():
        if fp.GetReference() != "U3":
            continue
        fp.Reference().SetPosition(vec(20.4, -42.15))
        print("  parked U3 silk at (20.4, -42.15)")
        return 1
    return 0


def _xy_near(a, b, tol=0.08):
    return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol


def _delete_via_at(board, netname, x, y):
    for item in list(board.GetTracks()):
        if not isinstance(item, pcbnew.PCB_VIA):
            continue
        if item.GetNetname() != netname:
            continue
        if _xy_near(mm(item.GetPosition()), (x, y)):
            board.Delete(item)
            return True
    return False


def _delete_seg(board, netname, a, b, layer):
    for item in list(board.GetTracks()):
        if isinstance(item, pcbnew.PCB_VIA):
            continue
        if item.GetNetname() != netname or item.GetLayer() != layer:
            continue
        start, end = mm(item.GetStart()), mm(item.GetEnd())
        if (_xy_near(start, a) and _xy_near(end, b)) or (
            _xy_near(start, b) and _xy_near(end, a)
        ):
            board.Delete(item)
            return True
    return False


def bridge_agnd(board, obstacles):
    """Join the analog return: MK1 ring/pad 4 to Ragnd, across the pour split."""
    agnd = net_of(board, "/Audio/AGND")
    mk1 = pad_of(board, "MK1", "4")
    rag = pad_of(board, "Ragnd", "1")
    if mk1 is None or rag is None:
        return 0
    if route_points(board, obstacles, agnd, pad_xy(mk1), pad_xy(rag),
                    DEFAULT_WIDTH, True):
        print("    bridged MK1-4 to Ragnd")
        return 1
    return 0


def _has_via_at(board, netname, x, y):
    for item in board.GetTracks():
        if not isinstance(item, pcbnew.PCB_VIA):
            continue
        if item.GetNetname() == netname and _xy_near(mm(item.GetPosition()), (x, y)):
            return True
    return False


def stitch_agnd_codec(board):
    """Via off U2's F.Cu island, B.Cu around I2C to the MK1/Ragnd return.

    Y1 and the I2S fanout split the analog pour, so a west-of-Y1 F.Cu run
    shorts GND and the codec pads. Stay on B.Cu east of that alley.
    """
    agnd = net_of(board, "/Audio/AGND")
    for a, b in (
        ((22.60, 19.50), (22.60, 29.80)),
        ((23.175, 19.50), (22.60, 19.50)),
        ((22.60, 29.80), (23.05, 29.80)),
    ):
        _delete_seg(board, "/Audio/AGND", a, b, pcbnew.F_Cu)
    for a, b in (
        ((22.40, 30.40), (22.40, 31.20)),
        ((22.40, 31.20), (28.50, 31.20)),
        ((28.50, 31.20), (28.50, 26.80)),
        ((28.50, 26.80), (26.40, 26.80)),
        ((22.40, 30.40), (26.40, 30.40)),
        ((26.40, 30.40), (26.40, 29.00)),
        ((26.40, 29.00), (28.60, 29.00)),
        ((28.60, 29.00), (28.60, 26.80)),
        ((28.60, 26.80), (26.40, 26.80)),
        ((26.40, 26.80), (26.40, 19.70)),
        ((26.40, 19.70), (23.175, 19.50)),
    ):
        _delete_seg(board, "/Audio/AGND", a, b, pcbnew.B_Cu)
    add_track(board, agnd, 22.275, 29.80, 22.40, 30.40, pcbnew.F_Cu,
              DEFAULT_WIDTH, protect=True)
    if not _has_via_at(board, "/Audio/AGND", 22.40, 30.40):
        add_via(board, agnd, 22.40, 30.40, protect=True)
    for a, b in (
        ((22.40, 30.40), (26.40, 30.40)),
        ((26.40, 30.40), (26.40, 29.00)),
        ((26.40, 29.00), (28.60, 29.00)),
        ((28.60, 29.00), (28.60, 26.80)),
        ((28.60, 26.80), (26.40, 26.80)),
        ((26.40, 26.80), (26.40, 19.70)),
        ((26.40, 19.70), (23.175, 19.50)),
    ):
        add_track(board, agnd, a[0], a[1], b[0], b[1], pcbnew.B_Cu,
                  DEFAULT_WIDTH, protect=True)
    print("    stitched U2 AGND on B.Cu east of Y1")
    return 1


def _delete_iterm_failed_fcu(board):
    for a, b in (
        ((21.85, -36.975), (21.85, -36.30)),
        ((21.85, -36.30), (23.20, -36.30)),
        ((23.20, -36.30), (24.00, -35.50)),
        ((24.00, -35.50), (24.00, -35.00)),
        ((21.85, -36.975), (21.85, -36.60)),
        ((21.85, -36.60), (24.11, -36.60)),
        ((24.11, -36.60), (24.11, -35.00)),
        ((24.11, -35.00), (24.00, -35.00)),
        ((21.85, -36.975), (21.85, -36.85)),
        ((21.85, -36.85), (23.50, -36.85)),
    ):
        _delete_seg(board, "/Power/ITERM", a, b, pcbnew.F_Cu)


def restore_tmr_hop(board):
    """Put TMR back on the 64 mm hop that clears TS, VDD33 and VBUS_CHG."""
    tmr = net_of(board, "/Power/TMR")
    for x, y in (
        (21.35, -36.60), (21.35, -36.975), (23.20, -36.00), (23.50, -36.85),
    ):
        _delete_via_at(board, "/Power/TMR", x, y)
    for a, b, layer in (
        ((21.35, -36.60), (15.10, -29.10), pcbnew.B_Cu),
        ((21.35, -36.975), (23.20, -36.60), pcbnew.B_Cu),
        ((23.20, -36.00), (15.10, -29.10), pcbnew.B_Cu),
        ((21.35, -36.60), (22.40, -36.00), pcbnew.F_Cu),
        ((22.40, -36.00), (23.20, -36.00), pcbnew.F_Cu),
        ((21.35, -37.862), (21.35, -36.975), pcbnew.F_Cu),
        ((21.35, -36.60), (23.20, -36.60), pcbnew.F_Cu),
        ((23.20, -36.60), (15.10, -29.10), pcbnew.B_Cu),
    ):
        _delete_seg(board, "/Power/TMR", a, b, layer)
    add_track(board, tmr, 21.35, -37.862, 21.35, -36.60, pcbnew.F_Cu,
              DEFAULT_WIDTH, protect=True)
    add_track(board, tmr, 21.35, -36.60, 23.20, -36.60, pcbnew.F_Cu,
              DEFAULT_WIDTH, protect=True)
    if not _has_via_at(board, "/Power/TMR", 23.20, -36.60):
        add_via(board, tmr, 23.20, -36.60, protect=True)
    add_track(board, tmr, 23.20, -36.60, 15.10, -29.10, pcbnew.B_Cu,
              DEFAULT_WIDTH, protect=True)
    print("    restored TMR hop")
    return 1


def stitch_charger_iterm(board):
    """Leave the charger copper alone.

    ITERM and TMR are routed. The old body put TMR back on the y=-36.6 hop
    and left U3 pin 15 open, which is how this net stayed unconnected.
    """
    del board
    print("    stitch_charger_iterm skipped; ITERM and TMR are already routed")
    return 0


def via_then_maze(board, router, obstacles, net, source, target, width):
    """Drop vias on dangling ends, then maze. Closes F.Cu-to-B.Cu leftovers."""
    code = net.GetNetCode()
    pts = []
    for obj in (source, target):
        if isinstance(obj, pcbnew.PAD):
            pts.append(pad_xy(obj))
        elif isinstance(obj, pcbnew.PCB_TRACK) and not isinstance(obj, pcbnew.PCB_VIA):
            pts.append(mm(obj.GetStart()))
            pts.append(mm(obj.GetEnd()))
    for x, y in pts:
        if obstacles.via_fits(x, y, code):
            add_via(board, net, x, y)
            obstacles.add_via(x, y, code)
    return router.connect(board, net, source, target, width)


def close_leftover_opens(board, half_w, half_h, passes=5):
    """Maze whatever finish() still has open, without ripping good copper."""
    print("closing leftover opens")
    stitch_agnd_codec(board)
    hide_hole_silk(board)
    fill_zones(board)
    save(board)
    for attempt in range(1, passes + 1):
        save(board)
        data = drc_json(PCB)
        opens = data.get("unconnected_items", [])
        print(f"  leftover pass {attempt}: {len(opens)} open, "
              f"{len(data.get('violations', []))} violations")
        if not opens:
            return pcbnew.LoadBoard(PCB)
        board = pcbnew.LoadBoard(PCB)
        board.BuildListOfNets()
        apply_board_rules(board)
        obstacles = Obstacles(board, half_w, half_h)
        router = MazeRouter(board, obstacles, half_w, half_h)
        if attempt == 1:
            bridge_agnd(board, obstacles)
        healed, stuck = repair_unconnected(board, obstacles, router, data)
        extra = 0
        for net, source, target, width in stuck:
            if via_then_maze(board, router, obstacles, net, source, target,
                             width):
                extra += 1
                print(f"    via-maze {net.GetNetname()}")
        print(f"    maze healed {healed}, via-maze {extra}, still {len(stuck) - extra}")
        fill_zones(board)
        save(board)
        if not healed and not extra and attempt > 1:
            break
    board = pcbnew.LoadBoard(PCB)
    board.BuildListOfNets()
    board, trimmed = trim_drc_danglers(board)
    return board


def trim_drc_danglers(board):
    """Delete leftover stubs DRC calls dangling, once the net is otherwise closed."""
    save(board)
    data = drc_json(PCB)
    if data.get("unconnected_items"):
        return board, 0
    index = board_items_by_uuid(board)
    doomed = []
    for violation in data.get("violations", []):
        if violation.get("type") not in ("track_dangling", "via_dangling"):
            continue
        for item in violation.get("items", []):
            obj = index.get(item["uuid"])
            if obj is None or obj.IsLocked():
                continue
            doomed.append(obj)
    for obj in doomed:
        board.Delete(obj)
    if doomed:
        print(f"  trimmed {len(doomed)} dangling stubs")
        fill_zones(board)
        save(board)
        board = pcbnew.LoadBoard(PCB)
        board.BuildListOfNets()
    return board, len(doomed)


def finish(board, half_w, half_h):
    """Last mile: drop stub vias, then find every designator a legible seat."""
    hide_hole_silk(board)
    dropped = drop_dangling_vias(board)
    if dropped:
        print(f"  dropped {dropped} dangling vias")
        board = pcbnew.LoadBoard(PCB)
        board.BuildListOfNets()
    crowding = drop_vias_crowding_pads(board)
    if crowding:
        print(f"  dropped {crowding} vias crowding a same-net through-hole pad")
        board = pcbnew.LoadBoard(PCB)
        board.BuildListOfNets()
    homeless = tuck_reference_text(board, half_w, half_h)
    save(board)
    return board, homeless


# ---------------------------------------------------------------------------
# Bookkeeping
# ---------------------------------------------------------------------------


def patch_title(routed):
    note = (
        "Planes and traces from route_pcb.py (freerouting). DRC clean."
        if routed
        else "Copper pours from route_pcb.py --planes-only."
    )
    with open(PCB, encoding="utf-8") as fh:
        text = fh.read()
    for old in (
        "First-pass placement from generate_pcb.py. Not routed.",
        "Copper pours from route_pcb.py --planes-only. Signals not routed.",
        "Copper pours from route_pcb.py --planes-only.",
        "Planes and traces from route_pcb.py. Review DRC before fab.",
        "Planes and traces from route_pcb.py (freerouting). DRC clean.",
    ):
        text = text.replace(old, note)
    with open(PCB, "w", encoding="utf-8") as fh:
        fh.write(text)


ROUTED_OPEN_ITEMS = [
    "SP1 is a KELIKING KLJ-01304T-08R07W (LCSC C18186315), a 13 x 13 x 4.0 mm "
    "SMD can that JLCPCB can place. The land is the vendor/EasyEDA "
    "BUZ-SMD_4P-L13.0-W13.0-P11.4-BL pattern: 2.0 x 2.5 mm pads, electrical "
    "pair on 11.4 mm centres toward the analog island, dummy pair toward the "
    "top edge with no pin numbers. Pad 1 is + / SPK_P at (+5.7, -4.35), "
    "bottom-right in this file's 0°. EasyEDA -BL means pin 1 is bottom-left "
    "in *their* library 0°, which is what JLC places C18186315 from. CPL "
    "rotation is 0. A left-right mismatch only inverts polarity; 180° puts "
    "the coil on the dummy pads and the speaker is open. Confirm against "
    "JLC's assembly preview before the order. The lid has a grille over this "
    "part; check polarity, volume (NS4150 on VSYS into 8 ohm, 1 W max) and "
    "the acoustic path on the first assembled board.",
    "SW1 is a side-actuated Panasonic EVQP7C01P (JLCPCB C388883), replacing "
    "the top-actuated PTS645. The record button is on the phone-left wall "
    "(left when looking at the lid), so a top "
    "plunger would have needed a case lever; this one is pressed straight "
    "through the wall aperture. Its actuator tip sits 0.6 mm inside the board "
    "edge; the case key nub spans that gap. Pin 1 carries BTN and pin 2 carries "
    "GND, the opposite of the old part: a push button's terminals are "
    "interchangeable, and pin 2 is the pad row nearest the board edge, where "
    "the F.Cu GND pour reaches it without a trace. Check the press feel on "
    "the first assembled board: 2.2 N is firmer than the 1.6 N alternatives.",
    "Download is four F.Cu pads (TP_BOOT, TP_EN, TP_GND, TP_3V3) west of the "
    "MCU. Hold GPIO0 to GND, pulse EN. No Boot/Reset switches and no UART header.",
    "USB D+/D- are not impedance controlled, on purpose: the ESP32-S3 USB "
    "peripheral is full speed only, and 90 ohm on this 0.1 mm prepreg would "
    "need traces narrower than any quick-turn fab will run. The pair is "
    "0.2 mm wide on a 0.4 mm pitch over solid In1 GND, near 75 ohm "
    "differential by first-order microstrip. Re-check if v2 ever needs "
    "high-speed USB, which would mean a thicker top prepreg.",
    "MK1's land pattern is a locally adapted copy in PSV.pretty, not the "
    "drawing in the Infineon datasheet. The ring pad and its stencil aperture "
    "were moved out to 0.95 mm so copper clears the 0.8 mm sound port by "
    "0.32 mm; the datasheet's own figure would leave 0.18 mm, which no fab "
    "will drill reliably. The datasheet also assumes solder-mask-defined "
    "pads and this land is copper-defined, inherited from the KiCad library. "
    "Check the acoustic seal on the first assembled board: an open solder "
    "ring leaks and costs low-frequency response.",
    "Pixel body and Pixelsnap ring numbers in hardware/cad/params.json are "
    "published defaults. Caliper a real phone and a real magnet ring before "
    "cutting metal.",
    "USB-C J2 is the only 5 V inlet. U3 is a BQ24073 power-path charger: OUT "
    "(VSYS) stays up from USB with BT1 open, and BAT is the pouch only. Do "
    "not strap VSYS to VBAT. Buy a protected 1S pouch; this board has no "
    "pack protector. Playback now runs the NS4150 from VSYS (~4.4 V on USB, "
    "cell voltage on pouch), still under the speaker's 1 W ceiling.",
    "kicad-cli pcb drc --schematic-parity reports 32 notes, and all of them "
    "are expected: spare ESP32-S3 castellations and NC pins (including the "
    "unused speaker outputs and PA_EN), four mounting holes, and three "
    "footprint fields the sheet leaves blank (BT1's description, J2's "
    "datasheet, J3's description). Copper DRC is clean. TD, TMR, and the "
    "magnetic-pad nets are routed.",
]


def usb_summary(board):
    """Measure the pair, so the documented geometry cannot drift from copper."""
    out = {}
    for name in ("USB_DP", "USB_DM"):
        per_layer = collections.Counter()
        vias = 0
        for track in board.GetTracks():
            if track.GetNetname() != name:
                continue
            if isinstance(track, pcbnew.PCB_VIA):
                vias += 1
            else:
                per_layer[board.GetLayerName(track.GetLayer())] += \
                    pcbnew.ToMM(track.GetLength())
        out[name] = {
            "copper_mm": {k: round(v, 2) for k, v in sorted(per_layer.items())},
            "vias": vias,
        }
    out["geometry"] = (
        f"{USB_WIDTH} mm traces on a {USB_PAIR_PITCH} mm pitch, F.Cu over the "
        "solid In1 GND plane, not impedance controlled (full-speed only)"
    )
    # Say what the number is. USB_DP and USB_DM run from USB-C J2
    # through U7 to U1. copper_mm is all copper on the net, which is longer
    # than the signal path, and is not comparable to a point-to-point length.
    out["measures"] = (
        "total copper on each net, including the U7 ESD array; not a "
        "point-to-point length"
    )
    return out


def update_placement_open_items(board, unconnected, violations):
    """Refresh routing counts in placement.json from the board on disk."""
    if not os.path.isfile(PLACEMENT):
        return
    with open(PLACEMENT, encoding="utf-8") as fh:
        data = json.load(fh)
    # The USB note was written by hand into placement.json and again into
    # params.json, and only params.json was kept up to date. The stale copy
    # still described a 0.15 mm gap pair under 20 mm long at 70 ohm, which is
    # not what is on the board, and placement.json is what the next agent reads
    # as XY truth. Copy the one in params.json rather than keep two.
    params = json.load(open(PARAMS, encoding="utf-8"))
    data.setdefault("board", {})["usb_diff_note"] = params["pcb"]["usb_diff_note"]
    tracks = [t for t in board.GetTracks() if not isinstance(t, pcbnew.PCB_VIA)]
    vias = [t for t in board.GetTracks() if isinstance(t, pcbnew.PCB_VIA)]
    length = sum(pcbnew.ToMM(t.GetLength()) for t in tracks)
    data["routing"] = {
        "router": "freerouting headless via Specctra DSN/SES, then plane "
                  "stitching and pours from route_pcb.py",
        "tracks": len(tracks),
        "vias": len(vias),
        "track_length_mm": round(length, 1),
        "zones": [z.GetZoneName() for z in board.Zones()],
        "unconnected_items": unconnected,
        "drc_violations": violations,
        "usb": usb_summary(board),
        "note": "Re-run: python3 hardware/kicad/recorder/route_pcb.py",
    }
    # Leave open_items alone. The list in this file is the pogo / NAND /
    # pouch board. ROUTED_OPEN_ITEMS still describes the old USB-C spin,
    # and copying it would wipe the notes the next route is supposed to keep.
    data["_comment"] = (
        "Generated by hardware/kicad/recorder/generate_pcb.py; the routing "
        "and open_items blocks are refreshed by route_pcb.py. Footprint XY "
        "for the recorder PCB; keep this file in sync with recorder.kicad_pcb. "
        "Origin is the magnet-ring (Pixelsnap) centre; +X phone right, +Y "
        "toward the camera bar. The board and lid were spun 180\u00b0 around "
        "that origin; on this dev / USB-C variant J2 is a mid-mount USB-C on "
        "the phone-bottom (-Y) edge at y = -42.8, and the tray clocking magnet "
        "stays at 6 o'clock. Edit both files when a part moves."
    )
    with open(PLACEMENT, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


def report(board):
    tracks = sum(1 for t in board.GetTracks() if not isinstance(t, pcbnew.PCB_VIA))
    vias = sum(1 for t in board.GetTracks() if isinstance(t, pcbnew.PCB_VIA))
    print(f"tracks:  {tracks}")
    print(f"vias:    {vias}")
    print(f"zones:   {len(list(board.Zones()))}")


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------


def load(half=False):
    params = json.load(open(PARAMS, encoding="utf-8"))
    half_w = params["pcb"]["width_mm"] / 2.0
    half_h = params["pcb"]["height_mm"] / 2.0
    board = pcbnew.LoadBoard(PCB)
    board.BuildListOfNets()
    return board, half_w, half_h


def apply_board_rules(board):
    """Stamp JLCPCB floors onto the loaded board, not only .kicad_pro.

    HEAD's board file still carries 0.25 mm hole clearance. fill_zones uses
    the board object, so a restore-and-pour would otherwise redraw every
    NPTH keepout at 0.25 and fail the 0.3 mm rule in recorder.kicad_pro.
    """
    ds = board.GetDesignSettings()
    ds.m_HoleClearance = pcbnew.FromMM(DESIGN_RULES["min_hole_clearance"])
    ds.m_HoleToHoleMin = pcbnew.FromMM(DESIGN_RULES["min_hole_to_hole"])
    ds.m_MinClearance = pcbnew.FromMM(0.15)
    ds.m_CopperEdgeClearance = pcbnew.FromMM(
        DESIGN_RULES["min_copper_edge_clearance"]
    )


def save(board):
    apply_board_rules(board)
    board.BuildConnectivity()
    pcbnew.SaveBoard(PCB, board)
    apply_project_policy(PROJECT)


def fix_via_widths(board):
    """Give every via a per-layer width. KiCad 10 asserts on the no-arg getter."""
    width = pcbnew.FromMM(VIA_SIZE)
    for item in board.GetTracks():
        if isinstance(item, pcbnew.PCB_VIA):
            item.SetFrontWidth(width)
            item.SetWidth(pcbnew.F_Cu, width)
            item.SetWidth(pcbnew.B_Cu, width)


def stage_planes(dsn_path):
    """Wipe copper, lay the two inner planes, hand-route USB, write a DSN."""
    board, half_w, half_h = load()
    print("clearing existing copper")
    clear_copper(board)
    tie_u2_ep(board)
    print("adding inner planes")
    add_inner_planes(board, half_w, half_h)
    obstacles = Obstacles(board, half_w, half_h)
    tie_u1_edge_gnd(board, obstacles)
    print("hand-routing the USB-C D+/D- escape")
    usb_escape(board, obstacles)
    usb_pair_to_mcu(board, obstacles)
    stitch_rstat_vdd(board, obstacles)
    stitch_sw_gnd(board, obstacles)
    stubs, vias = fanout_fine_pitch(board, obstacles)
    print(f"fine-pitch fanout: {stubs} stubs, {vias} vias")
    fanout_charger(board, obstacles, protect=True)
    tie_mk1_ring(board)
    print(f"protected {relock(board)} hand-routed items from the autorouter")
    fix_via_widths(board)
    fill_zones(board)
    save(board)
    if not pcbnew.ExportSpecctraDSN(board, dsn_path):
        raise SystemExit(f"could not write {dsn_path}")
    print(f"wrote {dsn_path}")
    return board


def stage_session(ses_path):
    """Apply a routing session, then pour, stitch, and repair."""
    board, half_w, half_h = load()
    if not pcbnew.ImportSpecctraSES(board, ses_path):
        raise SystemExit(f"could not read {ses_path}")
    print(f"imported {ses_path}")
    print(f"re-locked {relock(board)} hand-routed items")
    widened = normalise_widths(board)
    if widened:
        print(f"  widened {widened} sub-minimum segments")
    return stage_pour(board, half_w, half_h)


def pour(board, half_w, half_h):
    clear_copper(board, tracks=False)
    add_inner_planes(board, half_w, half_h)
    add_outer_pours(board, half_w, half_h)
    fill_zones(board)


def stage_pour(board, half_w, half_h, passes=8):
    print("pouring planes")
    clear_copper(board, tracks=False)
    add_inner_planes(board, half_w, half_h)
    add_outer_pours(board, half_w, half_h)
    obstacles = Obstacles(board, half_w, half_h)
    print(f"  pad stitch vias: {stitch_pads_to_planes(board, obstacles, half_w, half_h)}")
    print(f"  island vias:     {stitch_islands(board, obstacles, half_w, half_h)}")
    print(f"  GND grid vias:   {stitch_grid(board, obstacles, half_w, half_h)}")
    fill_zones(board)
    gnd = net_of(board, "GND")
    orphans = 0
    for zone in board.Zones():
        if zone.GetNetname() == "GND":
            orphans += int(via_in_zone(board, obstacles, gnd, zone))
    if orphans:
        print(f"  orphan GND vias: {orphans} zones")
        fill_zones(board)
    pad_orphans = stitch_orphan_gnd_pads(board, obstacles)
    if pad_orphans:
        print(f"  orphan GND pads: {pad_orphans}")
        fill_zones(board)
    obstacles = Obstacles(board, half_w, half_h)
    fanout_charger(board, obstacles, protect=False)
    save(board)

    best = None
    previous = None
    for attempt in range(1, passes + 1):
        data = drc_json(PCB)
        open_items = len(data.get("unconnected_items", []))
        violations = len(data.get("violations", []))
        score = (violations, open_items)
        print(f"  pass {attempt}: {open_items} open connections, "
              f"{violations} DRC violations")
        if best is None or score < best[0]:
            with open(PCB, "rb") as fh:
                best = (score, fh.read())
        elif previous is not None and score > previous:
            # Rip-up made the board worse, and left to itself the loop will
            # keep cutting and re-routing the same corner forever. Stop and
            # take the best pass instead.
            print("    regressed, stopping")
            break
        previous = score
        if not open_items and not violations:
            break
        ripped = delete_bad_tracks(board, data)
        if ripped:
            print(f"    ripped up {ripped} violating segments")
        obstacles = Obstacles(board, half_w, half_h)
        router = MazeRouter(board, obstacles, half_w, half_h)
        healed, stuck = repair_unconnected(board, obstacles, router, data)
        for net, source, target, width in stuck:
            for terminal in (source, target):
                cut = router.ripup(board, net, terminal, width)
                if not cut:
                    continue
                ripped += cut
                # Retry straight away on a rebuilt map. Waiting for the next
                # pass just lets the nets that were cut re-route through the
                # gap and wall the same pad in again.
                obstacles = Obstacles(board, half_w, half_h)
                router = MazeRouter(board, obstacles, half_w, half_h)
                if router.connect(board, net, source, target, width):
                    print(f"    freed and routed {net.GetNetname()} "
                          f"({cut} traces cut)")
                    healed += 1
                    break
                print(f"    cut {cut} traces around {net.GetNetname()}")
        if ripped:
            grown, seated = fanout_fine_pitch(board, obstacles)
            if grown:
                print(f"    regrew {grown} fanout stubs, {seated} vias")
        if not ripped and not healed:
            break
        pour(board, half_w, half_h)
        save(board)

    data = drc_json(PCB)
    score = (len(data.get("violations", [])),
             len(data.get("unconnected_items", [])))
    if best is not None and best[0] < score:
        # Rip-up is a gamble: cutting a wall can leave the board worse than
        # it started. Keep the best board the loop actually saw.
        print(f"  restoring the best pass ({best[0][0]} violations, "
              f"{best[0][1]} open)")
        with open(PCB, "wb") as fh:
            fh.write(best[1])
        board = pcbnew.LoadBoard(PCB)
        board.BuildListOfNets()
    return board


def stage_repair(board, half_w, half_h, passes=8):
    """Close new opens on an already-routed board.

    Keeps the stored zone outlines. Rebuilding them with add_outer_pours
    uses ZONE_CLEARANCE 0.20 and fails the 0.30 mm hole rule on every NPTH.
    Hand-link U3, refill at 0.3 mm hole clearance, maze leftovers. Do not
    rip up: TMR rip-up was cutting I2S and VBUS to free a 3 mm gap.
    """
    del passes
    print("repairing island without rebuilding planes")
    apply_board_rules(board)
    obstacles = Obstacles(board, half_w, half_h)
    fanout_charger(board, obstacles, protect=True)
    apply_board_rules(board)
    fill_zones(board)
    save(board)

    data = drc_json(PCB)
    open_items = len(data.get("unconnected_items", []))
    violations = len(data.get("violations", []))
    print(f"  after hand route: {open_items} open connections, "
          f"{violations} DRC violations")
    if open_items:
        board = pcbnew.LoadBoard(PCB)
        board.BuildListOfNets()
        apply_board_rules(board)
        obstacles = Obstacles(board, half_w, half_h)
        router = MazeRouter(board, obstacles, half_w, half_h)
        healed, stuck = repair_unconnected(board, obstacles, router, data)
        print(f"  maze healed {healed}, still open {len(stuck)}")
        apply_board_rules(board)
        fill_zones(board)
        save(board)
        board = pcbnew.LoadBoard(PCB)
        board.BuildListOfNets()
    return board


def main():
    ensure_closed()
    argv = sys.argv[1:]

    if "--planes-only" in argv:
        board, half_w, half_h = load()
        board = stage_pour(board, half_w, half_h)
        board, _ = finish(board, half_w, half_h)
        patch_title(any(True for _ in board.GetTracks()))
        report(board)
        return

    if "--finish-only" in argv:
        board, half_w, half_h = load()
        board, _ = finish(board, half_w, half_h)
        data = drc_json(PCB)
        update_placement_open_items(board,
                                    len(data.get("unconnected_items", [])),
                                    len(data.get("violations", [])))
        report(board)
        return

    if "--repair-only" in argv:
        board, half_w, half_h = load()
        board = close_leftover_opens(board, half_w, half_h)
        board, _ = finish(board, half_w, half_h)
        data = drc_json(PCB)
        update_placement_open_items(board,
                                    len(data.get("unconnected_items", [])),
                                    len(data.get("violations", [])))
        report(board)
        print(f"kicad-cli pcb drc: {len(data.get('violations', []))} violations, "
              f"{len(data.get('unconnected_items', []))} open connections")
        if data.get("violations") or data.get("unconnected_items"):
            print("not fab clean yet - fix the board, then re-run")
            raise SystemExit(2)
        print(f"wrote {PCB}")
        return

    if "--export-dsn" in argv:
        stage_planes(argv[argv.index("--export-dsn") + 1])
        return

    if "--import-ses" in argv:
        board = stage_session(argv[argv.index("--import-ses") + 1])
        patch_title(True)
        report(board)
        return

    work = tempfile.mkdtemp(prefix="psv-route-")
    dsn = os.path.join(work, "recorder.dsn")
    ses = os.path.join(work, "recorder.ses")
    stage_planes(dsn)
    run_freerouting(dsn, ses)
    board = stage_session(ses)
    params = json.load(open(PARAMS, encoding="utf-8"))
    board, _ = finish(board, params["pcb"]["width_mm"] / 2.0,
                      params["pcb"]["height_mm"] / 2.0)
    board = close_leftover_opens(board, params["pcb"]["width_mm"] / 2.0,
                                 params["pcb"]["height_mm"] / 2.0)
    board, _ = finish(board, params["pcb"]["width_mm"] / 2.0,
                      params["pcb"]["height_mm"] / 2.0)
    patch_title(True)
    report(board)

    data = drc_json(PCB)
    unconnected = len(data.get("unconnected_items", []))
    violations = len(data.get("violations", []))
    update_placement_open_items(board, unconnected, violations)
    print(f"kicad-cli pcb drc: {violations} violations, "
          f"{unconnected} open connections")
    if violations or unconnected:
        print("not fab clean yet - fix the board, then re-run")
        raise SystemExit(2)
    print(f"wrote {PCB}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
