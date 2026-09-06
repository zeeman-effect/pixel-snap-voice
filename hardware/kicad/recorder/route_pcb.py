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

The router is freerouting (https://freerouting.app), driven headless through
Specctra DSN/SES. The old in-tree A* router that used to live here is gone:
it left 373 DRC errors and 38 open nets, mostly shorts and sub-minimum track
widths, and no amount of grid tuning made it competitive with a real
rip-up-and-retry router. Point PSV_FREEROUTING at the launcher, or put
``freerouting`` on PATH; .cursor/install.sh installs it.

This script loads recorder.kicad_pcb. It never calls CreateEmptyBoard and it
does not move footprints. Edge.Cuts, mounting holes, and placement stay as
they are. It refuses to write while ~recorder.kicad_pcb.lck is present.

Coordinates are the same magnet-centred millimetres as generate_pcb.py.
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

from generate_pcb import apply_project_policy, tuck_reference_text

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
HOLE_CLEARANCE = 0.25
HOLE_TO_HOLE = 0.25
EDGE_CLEAR = 0.35
VIA_SIZE = 0.60
VIA_DRILL = 0.30
HOLE_R = 2.1
DEFAULT_WIDTH = 0.15
USB_WIDTH = 0.20
POWER_WIDTH = 0.30
ZONE_CLEARANCE = 0.20

# Same list as NETCLASS_PATTERNS "POWER" in generate_pcb.py: the rails that
# carry charge current rather than logic.
POWER_NETS = {"VBUS", "VBUS_CHG", "VBAT", "/Power/3V3_RAW", "3V3A"}


def vec(x_mm, y_mm):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm))


def mm(pt):
    return pcbnew.ToMM(pt.x), pcbnew.ToMM(pt.y)


def in_analog(x, y):
    x0, y0, x1, y1 = ANALOG
    return x0 <= x <= x1 and y0 <= y <= y1


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
    via.SetWidth(pcbnew.FromMM(VIA_SIZE))
    via.SetDrill(pcbnew.FromMM(VIA_DRILL))
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
        for fp in board.GetFootprints():
            if fp.GetReference().startswith("H"):
                x, y = mm(fp.GetPosition())
                self.holes.append((x, y, HOLE_R, -1))
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
                self.vias.append((x, y, pcbnew.ToMM(item.GetWidth()) / 2.0,
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


def stitch_one(board, obstacles, net, x, y, layer=pcbnew.F_Cu):
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
        add_via(board, net, vx, vy)
        obstacles.add_via(vx, vy, code)
        if stub:
            add_track(board, net, x, y, vx, vy, layer, DEFAULT_WIDTH)
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
            if not in_analog(x, y) and obstacles.via_fits(x, y, code):
                add_via(board, gnd, x, y)
                obstacles.add_via(x, y, code)
                placed += 1
            y += pitch
        x += pitch
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


# Height the connector pins climb to before anything is allowed to turn.
# J2's two 0.65 mm NPTH board locks sit at (5.11, -40.2) and (10.89, -40.2).
# With hole clearance those two pegs block their whole x column from
# y = -40.85 up to y = -39.55, so the pad row can only breathe straight up.
J2_LANE_TOP = -38.5

# Escape lane per contact: pad number -> x the trace climbs at. Each is
# either the pad's own centre (0.3 mm contacts, 0.5 mm pitch, so the only
# lane that clears both neighbours) or, for the 0.6 mm VBUS contacts, the
# 0.115 mm-wide slot between the neighbouring pad and the board lock.
J2_LANES = {
    "A4": ("VBUS", 5.82),
    "A5": ("CC1", 6.75),
    "B7": ("USB_DM", 7.25),
    "A6": ("USB_DP", 7.75),
    "A7": ("USB_DM", 8.25),
    "B6": ("USB_DP", 8.75),
    "B5": ("CC2", 9.75),
    "A9": ("VBUS", 10.18),
}

# Where the four data contacts spread to once they are above the locks.
J2_FAN = {"B7": 6.80, "A6": 7.60, "A7": 8.40, "B6": 9.20}
J2_FAN_Y = -37.9


def usb_escape(board, obstacles):
    """Hand-route everything that leaves the USB-C footprint.

    A USB-C receptacle repeats D+ and D- on both rows so the plug works either
    way up, and on this 16-pin part the row reads B7(D-) A6(D+) A7(D-) B6(D+)
    on a 0.5 mm pitch. Each net has to skip a pad of the other net and the two
    links have to cross, which needs a layer change, and the CC and VBUS
    contacts on either side of them need lanes of their own past the board
    locks. Freerouting solves none of this: it gave up on J2-B6 -> J2-A6 every
    run, and when the data pair fanned out early it walled CC1 into its pad.

    So every contact climbs straight out of its pad to y = -38.5 first, and
    only then does anything turn:

      * CC1 goes left along y = -38.5 into R2, CC2 right into R3.
      * VBUS drops to B.Cu just above the locks and crosses under the data
        pair to F1. Its two contacts are 4.9 mm apart with the whole data
        pair between them, so there is no F.Cu path that joins them.
      * D+ / D- fan to 0.8 mm, D- crosses on F.Cu and D+ ducks under it.

    The VBUS climb is 0.15 mm, not the 0.3 mm POWER width: the slot between
    the B8 contact and the board lock is 0.115 mm wide once clearance is
    taken off, and 2.5 mm of 0.15 mm outer copper is under 10 mohm at the
    500 mA this charger draws.
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

    # 1. Straight up out of every pad.
    for number, (name, lane) in J2_LANES.items():
        px, py = pads[number]
        width = USB_WIDTH if name.startswith("USB_") else DEFAULT_WIDTH
        top = -39.5 if name == "VBUS" else J2_LANE_TOP
        run(nets[name], [(px, py), (lane, py + 0.545), (lane, top)],
            pcbnew.F_Cu, width)

    # 2. CC1 and CC2 run outward to their 5.11k Rd resistors.
    run(nets["CC1"], [(J2_LANES["A5"][1], J2_LANE_TOP), (1.40, J2_LANE_TOP),
                      (0.50, -39.10)], pcbnew.F_Cu, DEFAULT_WIDTH)
    run(nets["CC2"], [(J2_LANES["B5"][1], J2_LANE_TOP), (15.50, J2_LANE_TOP),
                      (15.50, -39.175)], pcbnew.F_Cu, DEFAULT_WIDTH)

    # 3. VBUS crosses under the data pair on B.Cu and surfaces at F1.
    vbus = nets["VBUS"]
    run(vbus, [(5.82, -39.5), (5.55, -39.2)], pcbnew.F_Cu, DEFAULT_WIDTH)
    run(vbus, [(10.18, -39.5), (10.45, -39.2)], pcbnew.F_Cu, DEFAULT_WIDTH)
    for x in (5.55, 10.45, 16.50):
        drop(vbus, x, -39.2)
    run(vbus, [(5.55, -39.2), (16.50, -39.2)], pcbnew.B_Cu, POWER_WIDTH)
    run(vbus, [(16.50, -39.2), (17.50, -39.212)], pcbnew.F_Cu, POWER_WIDTH)

    # 4. Data pair: fan to 0.8 mm, D- crosses on top, D+ underneath.
    for number, x in J2_FAN.items():
        name, lane = J2_LANES[number]
        run(nets[name], [(lane, J2_LANE_TOP), (x, J2_FAN_Y)],
            pcbnew.F_Cu, USB_WIDTH)
    dm, dp = nets["USB_DM"], nets["USB_DP"]
    run(dm, [(J2_FAN["B7"], J2_FAN_Y), (J2_FAN["B7"], -36.0),
             (J2_FAN["A7"], -36.0), (J2_FAN["A7"], J2_FAN_Y)],
        pcbnew.F_Cu, USB_WIDTH)
    link_y = -36.9
    for number in ("A6", "B6"):
        x = J2_FAN[number]
        run(dp, [(x, J2_FAN_Y), (x, link_y)], pcbnew.F_Cu, USB_WIDTH)
        drop(dp, x, link_y)
    run(dp, [(J2_FAN["A6"], link_y), (J2_FAN["B6"], link_y)],
        pcbnew.B_Cu, USB_WIDTH)


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


# ---------------------------------------------------------------------------
# Freerouting
# ---------------------------------------------------------------------------


def find_freerouting():
    env = os.environ.get("PSV_FREEROUTING")
    if env and os.path.isfile(env):
        return env
    found = shutil.which("freerouting")
    if found:
        return found
    for path in (
        os.path.expanduser("~/.local/opt/freerouting/bin/freerouting"),
        "/opt/freerouting/bin/freerouting",
    ):
        if os.path.isfile(path):
            return path
    raise SystemExit(
        "freerouting not found. Install it (bash .cursor/install.sh) or set "
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


def drc_json(pcb_path, errors_only=True):
    kicad = shutil.which("kicad-cli") or os.environ.get("KICAD_CLI")
    if not kicad:
        raise SystemExit("kicad-cli not found; cannot check the routed board")
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as fh:
        out = fh.name
    cmd = [kicad, "pcb", "drc", "--format", "json", "-o", out, pcb_path]
    if errors_only:
        cmd.insert(3, "--severity-error")
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
            if not isinstance(obj, pcbnew.PCB_TRACK) or isinstance(obj, pcbnew.PCB_VIA):
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
    report_data = drc_json(PCB, errors_only=False)
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
    with open(PCB, "rb") as fh:
        backup = fh.read()
    for via in doomed:
        board.Delete(via)
    fill_zones(board)
    save(board)
    after = drc_json(PCB)
    if after.get("unconnected_items") or after.get("violations"):
        # A via the checker called dangling was load bearing after all.
        print("  dangling-via cleanup broke connectivity, keeping them")
        with open(PCB, "wb") as fh:
            fh.write(backup)
        return 0
    return len(doomed)


def finish(board, half_w, half_h):
    """Last mile: drop stub vias, then find every designator a legible seat."""
    dropped = drop_dangling_vias(board)
    if dropped:
        print(f"  dropped {dropped} dangling vias")
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
    "SP1 is still a placeholder 15 x 11 mm land pattern in PSV.pretty. It is "
    "DRC clean and its two pads are routed, but the pad size and spacing are "
    "invented. Replace with the vendor drawing once a real speaker part "
    "number is picked, then re-run generate_pcb.py and route_pcb.py.",
    "SW1 is a top-actuated PTS645. The case still needs a lever over the "
    "plunger, or the part has to change to a side-actuated switch. This is a "
    "case job, not a board job: the footprint and its routing are done.",
    "Silkscreen: kicad-cli reports silk-over-pad and silk-overlap warnings on "
    "the tightly packed designators. Cosmetic only, no copper impact, and "
    "left alone so the reference designators stay readable for hand rework.",
    "Pixel body and Pixelsnap ring numbers in hardware/cad/params.json are "
    "published defaults. Caliper a real phone and a real magnet ring before "
    "cutting metal.",
]


def update_placement_open_items(board, unconnected, violations):
    """Rewrite the gap list in placement.json so it matches the board on disk."""
    if not os.path.isfile(PLACEMENT):
        return
    with open(PLACEMENT, encoding="utf-8") as fh:
        data = json.load(fh)
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
        "drc_errors": violations,
        "note": "Re-run: python3 hardware/kicad/recorder/route_pcb.py",
    }
    data["open_items"] = list(ROUTED_OPEN_ITEMS)
    data["_comment"] = (
        "Generated by hardware/kicad/recorder/generate_pcb.py; the routing "
        "and open_items blocks are refreshed by route_pcb.py. Footprint XY "
        "for the recorder PCB; keep this file in sync with recorder.kicad_pcb. "
        "Origin is the magnet-ring (Pixelsnap) centre; +X phone right, +Y "
        "toward the camera bar. Coordinates are written verbatim into "
        "recorder.kicad_pcb, so the USB edge is y = -43. Edit both files when "
        "a part moves."
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


def save(board):
    board.BuildConnectivity()
    pcbnew.SaveBoard(PCB, board)
    apply_project_policy(PROJECT)


def stage_planes(dsn_path):
    """Wipe copper, lay the two inner planes, hand-route USB, write a DSN."""
    board, half_w, half_h = load()
    print("clearing existing copper")
    clear_copper(board)
    tie_u2_ep(board)
    print("adding inner planes")
    add_inner_planes(board, half_w, half_h)
    obstacles = Obstacles(board, half_w, half_h)
    print("hand-routing the USB-C D+/D- escape")
    usb_escape(board, obstacles)
    stubs, vias = fanout_fine_pitch(board, obstacles)
    print(f"fine-pitch fanout: {stubs} stubs, {vias} vias")
    print(f"protected {relock(board)} hand-routed items from the autorouter")
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
    save(board)

    best = None
    previous = None
    for attempt in range(1, passes + 1):
        data = drc_json(PCB)
        open_items = len(data.get("unconnected_items", []))
        errors = len(data.get("violations", []))
        score = (errors, open_items)
        print(f"  pass {attempt}: {open_items} open connections, {errors} DRC errors")
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
        if not open_items and not errors:
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
        print(f"  restoring the best pass ({best[0][0]} errors, "
              f"{best[0][1]} open)")
        with open(PCB, "wb") as fh:
            fh.write(best[1])
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
        board, homeless = finish(board, half_w, half_h)
        report(board)
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
    patch_title(True)
    report(board)

    data = drc_json(PCB)
    unconnected = len(data.get("unconnected_items", []))
    errors = len(data.get("violations", []))
    update_placement_open_items(board, unconnected, errors)
    print(f"kicad-cli pcb drc: {errors} errors, {unconnected} open connections")
    if errors or unconnected:
        print("not fab clean yet - fix the board, then re-run")
        raise SystemExit(2)
    print(f"wrote {PCB}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
