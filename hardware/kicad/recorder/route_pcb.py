#!/usr/bin/env python
"""Pour planes and route traces on the existing recorder board.

Run with the KiCad 10 interpreter, which is the only one that has pcbnew:

    /c/Users/zachr/AppData/Local/Programs/KiCad/10.0/bin/python.exe route_pcb.py

This script loads recorder.kicad_pcb. It never calls CreateEmptyBoard and it
does not move footprints. Re-running it deletes tracks, vias, and zones, then
builds them again. Edge.Cuts, mounting holes, and placement stay as they are.

Close the recorder project in KiCad before running. The script refuses to
write while ~recorder.kicad_pcb.lck is present.

Coordinates are the same magnet-centred millimetres as generate_pcb.py.
"""

from __future__ import annotations

import heapq
import json
import math
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PARAMS = os.path.join(REPO, "hardware", "cad", "params.json")
PCB = os.environ.get("PSV_ROUTE_PCB", os.path.join(HERE, "recorder.kicad_pcb"))
PROJECT = os.environ.get("PSV_ROUTE_PRO", os.path.join(HERE, "recorder.kicad_pro"))
LOCK = os.path.join(HERE, "~recorder.kicad_pcb.lck")
SKIP_LOCK = os.environ.get("PSV_ROUTE_SKIP_LOCK") == "1"

# Analog island on F.Cu: AGND + 3V3A pours, no F.Cu VDD33 pour.
# U2 PVDD/DVDD/CE still sit on VDD33; those pads get a via down to In2
# and a short F.Cu stub. A board-wide F.Cu VDD33 pour is wrong: it sat
# on top of GND_F and left every digital GND pad isolated.
ANALOG = (12.0, 6.0, 32.0, 38.0)

POUR_NETS = {"GND", "VDD33", "/Audio/AGND", "3V3A"}

# Local F.Cu VDD33 around decoupling only. In2.Cu is the plane.
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

CLEARANCE = 0.13
VIA_SIZE = 0.60
VIA_DRILL = 0.30
HOLE_R = 2.1
EDGE_CLEAR = 0.40
GRID = 0.20
DEFAULT_WIDTH = 0.15
USB_WIDTH = 0.20
POWER_WIDTH = 0.35

WIDTHS = {
    "USB_DP": USB_WIDTH,
    "USB_DM": USB_WIDTH,
    "VBAT": POWER_WIDTH,
    "VBUS": POWER_WIDTH,
    "VBUS_CHG": POWER_WIDTH,
    "/Power/3V3_RAW": POWER_WIDTH,
}

# Prefer F.Cu for the USB pair (In1 is the GND reference under F.Cu).
NO_VIA_NETS = {"USB_DP", "USB_DM"}


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


def add_rect_zone(board, net, layer, x0, y0, x1, y1, name, priority):
    zone = pcbnew.ZONE(board)
    zone.SetLayer(layer)
    if net is not None:
        zone.SetNet(net)
    zone.SetAssignedPriority(priority)
    zone.SetLocalClearance(pcbnew.FromMM(0.20))
    zone.SetMinThickness(pcbnew.FromMM(0.20))
    zone.SetThermalReliefGap(pcbnew.FromMM(0.20))
    zone.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.20))
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    zone.SetZoneName(name)
    outline = zone.Outline()
    outline.NewOutline()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        outline.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    board.Add(zone)
    return zone


def add_poly_zone(board, net, layer, points, name, priority):
    zone = pcbnew.ZONE(board)
    zone.SetLayer(layer)
    if net is not None:
        zone.SetNet(net)
    zone.SetAssignedPriority(priority)
    zone.SetLocalClearance(pcbnew.FromMM(0.20))
    zone.SetMinThickness(pcbnew.FromMM(0.20))
    zone.SetThermalReliefGap(pcbnew.FromMM(0.20))
    zone.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.20))
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    zone.SetZoneName(name)
    outline = zone.Outline()
    outline.NewOutline()
    for x, y in points:
        outline.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    board.Add(zone)
    return zone


def add_rule_area(board, layer, x0, y0, x1, y1, name):
    """Keep F.Cu GND out of the analog island so AGND can be a local pour."""
    zone = pcbnew.ZONE(board)
    zone.SetIsRuleArea(True)
    zone.SetDoNotAllowZoneFills(True)
    zone.SetDoNotAllowPads(False)
    zone.SetDoNotAllowTracks(False)
    zone.SetDoNotAllowVias(False)
    zone.SetLayer(layer)
    zone.SetZoneName(name)
    outline = zone.Outline()
    outline.NewOutline()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        outline.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    board.Add(zone)


def add_track(board, net, x0, y0, x1, y1, layer, width):
    if x0 == x1 and y0 == y1:
        return
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(vec(x0, y0))
    track.SetEnd(vec(x1, y1))
    track.SetLayer(layer)
    track.SetWidth(pcbnew.FromMM(width))
    track.SetNet(net)
    board.Add(track)


def add_via(board, net, x, y):
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(vec(x, y))
    via.SetWidth(pcbnew.FromMM(VIA_SIZE))
    via.SetDrill(pcbnew.FromMM(VIA_DRILL))
    via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNet(net)
    board.Add(via)


def clear_copper(board):
    # Delete, not Remove. KiCad 10 SWIG marks vias as owned after a
    # previous SaveBoard/LoadBoard, and Remove then trips thisown.
    for item in list(board.GetTracks()):
        board.Delete(item)
    for zone in list(board.Zones()):
        board.Delete(zone)


def tie_u2_ep(board):
    """ES8311 exposed pad is on the land but not in the symbol. Tie it to AGND."""
    agnd = net_of(board, "/Audio/AGND")
    for fp in board.GetFootprints():
        if fp.GetReference() != "U2":
            continue
        for pad in fp.Pads():
            if pad.GetNumber() == "21":
                pad.SetNet(agnd)
                return
    print("warning: U2 pad 21 not found")


def add_zones(board, half_w, half_h):
    gnd = net_of(board, "GND")
    vdd = net_of(board, "VDD33")
    agnd = net_of(board, "/Audio/AGND")
    avdd = net_of(board, "3V3A")
    ax0, ay0, ax1, ay1 = ANALOG

    add_rect_zone(board, gnd, pcbnew.In1_Cu, -half_w, -half_h, half_w, half_h, "GND_In1", 0)
    add_rect_zone(board, vdd, pcbnew.In2_Cu, -half_w, -half_h, half_w, half_h, "VDD33_In2", 0)
    add_rect_zone(board, gnd, pcbnew.B_Cu, -half_w, -half_h, half_w, half_h, "GND_B", 0)
    add_rect_zone(board, gnd, pcbnew.F_Cu, -half_w, -half_h, half_w, half_h, "GND_F", 0)
    add_rule_area(board, pcbnew.F_Cu, ax0, ay0, ax1, ay1, "analog_no_F_GND")

    for x0, y0, x1, y1, name in VDD33_ISLANDS:
        add_rect_zone(board, vdd, pcbnew.F_Cu, x0, y0, x1, y1, name, 4)
    add_rect_zone(board, agnd, pcbnew.F_Cu, ax0, ay0, ax1, ay1, "AGND_F", 2)
    add_rect_zone(board, avdd, pcbnew.F_Cu, ax0, ay0, ax1, ay1, "3V3A_F", 3)


def hole_positions(board):
    holes = []
    for fp in board.GetFootprints():
        if fp.GetReference().startswith("H"):
            holes.append(mm(fp.GetPosition()))
        for pad in fp.Pads():
            if is_npth(pad):
                holes.append(pad_xy(pad))
    return holes


def via_site_ok(x, y, pads, holes, half_w, half_h, extra=1.1):
    if abs(x) > half_w - 0.8 or abs(y) > half_h - 0.8:
        return False
    for hx, hy in holes:
        if math.hypot(x - hx, y - hy) < HOLE_R + 0.6:
            return False
    for px, py, pw, ph in pads:
        if abs(x - px) < pw / 2 + extra and abs(y - py) < ph / 2 + extra:
            return False
    return True


def track_hits(board, x, y, radius=0.55):
    for item in board.GetTracks():
        if isinstance(item, pcbnew.PCB_VIA):
            vx, vy = mm(item.GetPosition())
            if math.hypot(x - vx, y - vy) < radius + VIA_SIZE / 2.0:
                return True
            continue
        x0, y0 = mm(item.GetStart())
        x1, y1 = mm(item.GetEnd())
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy) or 1.0
        t = max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / (length * length)))
        px, py = x0 + t * dx, y0 + t * dy
        if math.hypot(x - px, y - py) < radius + pcbnew.ToMM(item.GetWidth()) / 2.0:
            return True
    return False


def place_via_near(board, net, name, px, py, pad_boxes, holes, half_w, half_h, placed):
    for dx, dy in STITCH_OFFSETS:
        x, y = px + dx, py + dy
        if not via_site_ok(x, y, pad_boxes, holes, half_w, half_h, extra=0.50):
            continue
        if track_hits(board, x, y):
            continue
        if any(math.hypot(x - ax, y - ay) < 0.75 for ax, ay, _ in placed):
            continue
        add_via(board, net, x, y)
        placed.append((x, y, name))
        return x, y
    return None


def nearest_via(px, py, name, placed, max_d):
    best = None
    for x, y, n in placed:
        if n != name:
            continue
        dist = math.hypot(x - px, y - py)
        if dist <= max_d and (best is None or dist < best[0]):
            best = (dist, x, y)
    return best


def stub_pad_to_plane(board, net, name, px, py, pad_boxes, holes, half_w, half_h, placed):
    """Tie a pad to its inner plane with a via and a short F.Cu stub."""
    hit = nearest_via(px, py, name, placed, max_d=1.8)
    if hit is None:
        via = place_via_near(
            board, net, name, px, py, pad_boxes, holes, half_w, half_h, placed
        )
        if via is not None:
            hit = (0.0, via[0], via[1])
    if hit is None:
        return False
    _, vx, vy = hit
    if math.hypot(px - vx, py - vy) > 0.05:
        add_track(board, net, px, py, vx, vy, pcbnew.F_Cu, DEFAULT_WIDTH)
    return True


def add_power_vias(board, half_w, half_h):
    gnd = net_of(board, "GND")
    vdd = net_of(board, "VDD33")
    holes = hole_positions(board)
    pad_boxes = []
    analog_gnd = []
    vdd_pads = []
    for fp, pad, name in copper_pads(board):
        x, y = pad_xy(pad)
        w, h = pad_wh(pad)
        pad_boxes.append((x, y, w, h))
        if name == "GND" and in_analog(x, y):
            analog_gnd.append((x, y))
        if name == "VDD33":
            vdd_pads.append((x, y))

    placed = []

    for x, y in analog_gnd:
        stub_pad_to_plane(
            board, gnd, "GND", x, y, pad_boxes, holes, half_w, half_h, placed
        )
    for x, y in vdd_pads:
        stub_pad_to_plane(
            board, vdd, "VDD33", x, y, pad_boxes, holes, half_w, half_h, placed
        )

    # GND stitch grid on the digital side only. Through vias in the analog
    # island would dump digital GND onto F.Cu next to the AGND pour.
    x = -half_w + 3.0
    while x < half_w - 3.0:
        y = -half_h + 3.0
        while y < half_h - 3.0:
            if (
                not in_analog(x, y)
                and via_site_ok(x, y, pad_boxes, holes, half_w, half_h, extra=1.4)
                and not track_hits(board, x, y)
            ):
                if all(math.hypot(x - ax, y - ay) > 2.4 for ax, ay, _ in placed):
                    add_via(board, gnd, x, y)
                    placed.append((x, y, "GND"))
            y += 8.0
        x += 8.0

    # One via in each local F.Cu VDD33 island so the cap copper reaches In2.
    for x0, y0, x1, y1, _name in VDD33_ISLANDS:
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        if via_site_ok(cx, cy, pad_boxes, holes, half_w, half_h, extra=0.40):
            if all(math.hypot(cx - ax, cy - ay) > 0.75 for ax, ay, _ in placed):
                add_via(board, vdd, cx, cy)
                placed.append((cx, cy, "VDD33"))
    return len(placed)


class Grid:
    def __init__(self, half_w, half_h):
        self.x0 = -half_w + EDGE_CLEAR
        self.y0 = -half_h + EDGE_CLEAR
        self.nx = int((2 * half_w - 2 * EDGE_CLEAR) / GRID) + 1
        self.ny = int((2 * half_h - 2 * EDGE_CLEAR) / GRID) + 1
        self.blocked = [bytearray(self.nx * self.ny), bytearray(self.nx * self.ny)]

    def idx(self, gx, gy):
        return gy * self.nx + gx

    def in_range(self, gx, gy):
        return 0 <= gx < self.nx and 0 <= gy < self.ny

    def to_cell(self, x, y):
        gx = int(round((x - self.x0) / GRID))
        gy = int(round((y - self.y0) / GRID))
        gx = max(0, min(self.nx - 1, gx))
        gy = max(0, min(self.ny - 1, gy))
        return gx, gy

    def to_mm(self, gx, gy):
        return self.x0 + gx * GRID, self.y0 + gy * GRID

    def mark_rect(self, layer, x0, y0, x1, y1):
        gx0, gy0 = self.to_cell(x0, y0)
        gx1, gy1 = self.to_cell(x1, y1)
        if gx0 > gx1:
            gx0, gx1 = gx1, gx0
        if gy0 > gy1:
            gy0, gy1 = gy1, gy0
        buf = self.blocked[layer]
        for gy in range(gy0, gy1 + 1):
            row = gy * self.nx
            for gx in range(gx0, gx1 + 1):
                buf[row + gx] = 1

    def mark_circle(self, layer, x, y, r):
        self.mark_rect(layer, x - r, y - r, x + r, y + r)

    def clear_rect(self, layer, x0, y0, x1, y1):
        gx0, gy0 = self.to_cell(x0, y0)
        gx1, gy1 = self.to_cell(x1, y1)
        if gx0 > gx1:
            gx0, gx1 = gx1, gx0
        if gy0 > gy1:
            gy0, gy1 = gy1, gy0
        buf = self.blocked[layer]
        for gy in range(gy0, gy1 + 1):
            row = gy * self.nx
            for gx in range(gx0, gx1 + 1):
                buf[row + gx] = 0

    def blocked_at(self, layer, gx, gy):
        return self.blocked[layer][self.idx(gx, gy)] != 0


def build_grid(board, netname, width, half_w, half_h, clearance=CLEARANCE):
    grid = Grid(half_w, half_h)
    inflate = clearance + width / 2.0
    via_r = VIA_SIZE / 2.0 + CLEARANCE

    for fp in board.GetFootprints():
        if fp.GetReference().startswith("H"):
            x, y = mm(fp.GetPosition())
            for layer in (0, 1):
                grid.mark_circle(layer, x, y, HOLE_R + inflate)
        for pad in fp.Pads():
            x, y = pad_xy(pad)
            if is_npth(pad):
                for layer in (0, 1):
                    grid.mark_circle(layer, x, y, 0.55 + inflate)
                continue
            if pad.GetNetname() == netname:
                continue
            w, h = pad_wh(pad)
            layers = (0, 1)
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
                layers = (0,)
            for layer in layers:
                grid.mark_rect(
                    layer,
                    x - w / 2 - inflate,
                    y - h / 2 - inflate,
                    x + w / 2 + inflate,
                    y + h / 2 + inflate,
                )

    for item in board.GetTracks():
        if item.GetNetname() == netname:
            continue
        if isinstance(item, pcbnew.PCB_VIA):
            x, y = mm(item.GetPosition())
            for layer in (0, 1):
                grid.mark_circle(layer, x, y, via_r)
            continue
        x0, y0 = mm(item.GetStart())
        x1, y1 = mm(item.GetEnd())
        layer = 0 if item.GetLayer() == pcbnew.F_Cu else 1
        t_inf = pcbnew.ToMM(item.GetWidth()) / 2.0 + clearance + width / 2.0
        steps = max(1, int(math.hypot(x1 - x0, y1 - y0) / (GRID * 0.5)))
        for i in range(steps + 1):
            t = i / steps
            grid.mark_circle(layer, x0 + t * (x1 - x0), y0 + t * (y1 - y0), t_inf)

    # Punch last so neighbour pads and nearby tracks cannot seal a pad shut.
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if is_npth(pad) or pad.GetNetname() != netname:
                continue
            x, y = pad_xy(pad)
            w, h = pad_wh(pad)
            grid.clear_rect(
                0,
                x - max(w / 2, 0.15),
                y - max(h / 2, 0.15),
                x + max(w / 2, 0.15),
                y + max(h / 2, 0.15),
            )
            escape = 2.2 if fp.GetReference() == "U1" else 1.6
            ex, ey = fanout(fp, pad, half_w, half_h, length=escape)
            steps = max(1, int(math.hypot(ex - x, ey - y) / (GRID * 0.5)))
            for i in range(steps + 1):
                t = i / steps
                px = x + t * (ex - x)
                py = y + t * (ey - y)
                grid.clear_rect(0, px - 0.14, py - 0.14, px + 0.14, py + 0.14)
    return grid


def fanout(fp, pad, half_w, half_h, length=0.90):
    """Step off the pad into free board, not off the outline.

    Library pads on J2 / MK1 / D1 sit on the edge side of the footprint.
    Walking further that way leaves the board. Prefer an on-board candidate.
    """
    fx, fy = mm(fp.GetPosition())
    px, py = pad_xy(pad)
    ax, ay = px - fx, py - fy
    an = math.hypot(ax, ay) or 1.0
    ox, oy = -px, -py
    on = math.hypot(ox, oy) or 1.0
    candidates = (
        (px + length * ax / an, py + length * ay / an),
        (px + length * ox / on, py + length * oy / on),
        (px - length * ax / an, py - length * ay / an),
        (px, py),
    )
    for x, y in candidates:
        if abs(x) <= half_w - 0.8 and abs(y) <= half_h - 0.8:
            return x, y
    return px, py


def segment_clear(grid, layer, x0, y0, x1, y1):
    steps = max(1, int(math.hypot(x1 - x0, y1 - y0) / (GRID * 0.5)))
    for i in range(steps + 1):
        t = i / steps
        gx, gy = grid.to_cell(x0 + t * (x1 - x0), y0 + t * (y1 - y0))
        if not grid.in_range(gx, gy) or grid.blocked_at(layer, gx, gy):
            return False
    return True


def try_l(grid, x0, y0, x1, y1):
    """Return a list of F.Cu points if an L-path is free."""
    if segment_clear(grid, 0, x0, y0, x1, y0) and segment_clear(grid, 0, x1, y0, x1, y1):
        return [(x0, y0, 0), (x1, y0, 0), (x1, y1, 0)]
    if segment_clear(grid, 0, x0, y0, x0, y1) and segment_clear(grid, 0, x0, y1, x1, y1):
        return [(x0, y0, 0), (x0, y1, 0), (x1, y1, 0)]
    return None


def astar(grid, x0, y0, x1, y1, allow_via):
    s = (*grid.to_cell(x0, y0), 0)
    g = (*grid.to_cell(x1, y1), 0)
    if grid.blocked_at(0, s[0], s[1]):
        s = nearest_free(grid, s[0], s[1], 0)
    if grid.blocked_at(0, g[0], g[1]):
        g = nearest_free(grid, g[0], g[1], 0)
    if s is None or g is None:
        return None

    via_cost = 25 if allow_via else 10_000
    def h(gx, gy):
        return abs(gx - g[0]) + abs(gy - g[1])

    # heap entries are (f, g_cost, state). Do not compare f to g_cost.
    heap = [(h(*s[:2]), 0, s)]
    came = {s: None}
    cost = {s: 0}
    dirs = ((1, 0), (-1, 0), (0, 1), (0, -1))
    limit = 280_000
    seen = 0

    while heap and seen < limit:
        _f, gcost, (gx, gy, layer) = heapq.heappop(heap)
        if gcost != cost[(gx, gy, layer)]:
            continue
        if gx == g[0] and gy == g[1] and layer == 0:
            node = (gx, gy, layer)
            path = []
            while node is not None:
                path.append(node)
                node = came[node]
            path.reverse()
            return path
        seen += 1
        for dx, dy in dirs:
            nx, ny = gx + dx, gy + dy
            if not grid.in_range(nx, ny) or grid.blocked_at(layer, nx, ny):
                continue
            nc = gcost + 1
            state = (nx, ny, layer)
            if nc < cost.get(state, 1e18):
                cost[state] = nc
                came[state] = (gx, gy, layer)
                heapq.heappush(heap, (nc + h(nx, ny), nc, state))
        if allow_via:
            other = 1 - layer
            if not grid.blocked_at(other, gx, gy):
                nc = gcost + via_cost
                state = (gx, gy, other)
                if nc < cost.get(state, 1e18):
                    cost[state] = nc
                    came[state] = (gx, gy, layer)
                    heapq.heappush(heap, (nc + h(gx, gy), nc, state))
    return None


def nearest_free(grid, gx, gy, layer, radius=10):
    if grid.in_range(gx, gy) and not grid.blocked_at(layer, gx, gy):
        return gx, gy, layer
    for r in range(1, radius + 1):
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if abs(dx) != r and abs(dy) != r:
                    continue
                nx, ny = gx + dx, gy + dy
                if grid.in_range(nx, ny) and not grid.blocked_at(layer, nx, ny):
                    return nx, ny, layer
    return None


def compress(cells, grid):
    """Turn grid cells into (x, y, layer) corners, dropping collinear points."""
    if not cells:
        return []
    pts = [(*grid.to_mm(gx, gy), layer) for gx, gy, layer in cells]
    if len(pts) < 3:
        return pts
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        x0, y0, l0 = out[-1]
        x1, y1, l1 = pts[i]
        x2, y2, l2 = pts[i + 1]
        if l0 != l1 or l1 != l2:
            out.append(pts[i])
            continue
        if (x1 - x0) * (y2 - y1) == (y1 - y0) * (x2 - x1):
            continue
        out.append(pts[i])
    out.append(pts[-1])
    return out


def commit_path(board, net, points, width):
    layers = (pcbnew.F_Cu, pcbnew.B_Cu)
    for i in range(len(points) - 1):
        x0, y0, l0 = points[i]
        x1, y1, l1 = points[i + 1]
        if l0 != l1:
            add_via(board, net, x0, y0)
            continue
        add_track(board, net, x0, y0, x1, y1, layers[l0], width)


def mst(nodes):
    n = len(nodes)
    if n < 2:
        return []
    used = {0}
    edges = []
    while len(used) < n:
        best = None
        for i in used:
            xi, yi = nodes[i][0], nodes[i][1]
            for j in range(n):
                if j in used:
                    continue
                d = math.hypot(nodes[j][0] - xi, nodes[j][1] - yi)
                if best is None or d < best[0]:
                    best = (d, i, j)
        edges.append((nodes[best[1]], nodes[best[2]]))
        used.add(best[2])
    return edges


def route_pair(grid, a, b, allow_via):
    """Try L-paths then A* from pad centres and on-board fanouts."""
    pairs = (
        (a[0], a[1], b[0], b[1]),
        (a[2], a[3], b[2], b[3]),
        (a[0], a[1], b[2], b[3]),
        (a[2], a[3], b[0], b[1]),
    )
    for x0, y0, x1, y1 in pairs:
        path = try_l(grid, x0, y0, x1, y1)
        if path:
            return path
    for x0, y0, x1, y1 in pairs:
        cells = astar(grid, x0, y0, x1, y1, allow_via)
        if cells:
            path = compress(cells, grid)
            path[0] = (x0, y0, path[0][2])
            path[-1] = (x1, y1, path[-1][2])
            return path
    return None


def route_net(board, name, half_w, half_h):
    width = WIDTHS.get(name, DEFAULT_WIDTH)
    net = net_of(board, name)
    nodes = []
    for fp, pad, nname in copper_pads(board):
        if nname != name:
            continue
        x, y = pad_xy(pad)
        fx, fy = fanout(fp, pad, half_w, half_h)
        nodes.append((x, y, fx, fy, fp, pad))
    if len(nodes) < 2:
        return 0, []

    failed = []
    routed = 0
    allow_via = name not in NO_VIA_NETS
    for a, b in mst(nodes):
        grid = build_grid(board, name, width, half_w, half_h)
        path = route_pair(grid, a, b, allow_via)
        if path is None and name in NO_VIA_NETS:
            path = route_pair(grid, a, b, True)
        if path is None:
            failed.append((name, a, b))
            continue
        if path[0][0] != a[0] or path[0][1] != a[1]:
            add_track(board, net, a[0], a[1], path[0][0], path[0][1], pcbnew.F_Cu, width)
        if path[-1][0] != b[0] or path[-1][1] != b[1]:
            add_track(board, net, path[-1][0], path[-1][1], b[0], b[1], pcbnew.F_Cu, width)
        commit_path(board, net, path, width)
        routed += 1
    return routed, failed


def route_signals(board, half_w, half_h):
    names = sorted(
        {
            name
            for _, _, name in copper_pads(board)
            if name not in POUR_NETS and not name.startswith("unconnected-")
        }
    )
    # MCU buses first so they can cross the empty magnet interior. USB next.
    # Power last — VBAT would otherwise draw a highway across the board.
    def rank(name):
        if name.startswith("I2S") or name.startswith("I2C") or name.startswith("SD_"):
            return (0, name)
        if name in ("PA_EN", "BTN", "LED", "CHG_STAT"):
            return (1, name)
        if name.startswith("USB") or name.startswith("/MCU_USB/") or name.startswith("CC"):
            return (2, name)
        if name.startswith("/Audio/") or name.startswith("/IO/") or name == "MIC_P":
            return (3, name)
        return (4, name)

    names.sort(key=rank)
    routed = 0
    failed = []
    for name in names:
        n, miss = route_net(board, name, half_w, half_h)
        routed += n
        failed.extend(miss)
        print(f"  {name}: {n} segments" + (f"  FAIL {len(miss)}" if miss else ""))

    if failed:
        print("retrying leftovers at 0.12 mm")
        leftover = []
        for name, a, b in failed:  # noqa: keep leftover for unrouted report
            width = 0.12
            net = net_of(board, name)
            grid = build_grid(board, name, width, half_w, half_h, clearance=0.08)
            path = route_pair(grid, a, b, True)
            if path is None:
                add_track(board, net, a[0], a[1], a[2], a[3], pcbnew.F_Cu, width)
                add_track(board, net, b[0], b[1], b[2], b[3], pcbnew.F_Cu, width)
                add_via(board, net, a[2], a[3])
                add_via(board, net, b[2], b[3])
                add_track(board, net, a[2], a[3], b[2], b[3], pcbnew.B_Cu, width)
                routed += 1
                print(f"  retry {name}: B.Cu hop")
                continue
            if path[0][0] != a[0] or path[0][1] != a[1]:
                add_track(board, net, a[0], a[1], path[0][0], path[0][1], pcbnew.F_Cu, width)
            if path[-1][0] != b[0] or path[-1][1] != b[1]:
                add_track(board, net, path[-1][0], path[-1][1], b[0], b[1], pcbnew.F_Cu, width)
            commit_path(board, net, path, width)
            routed += 1
            print(f"  retry {name}: ok")
        failed = leftover
    else:
        failed = []
    return routed, failed


def fill_zones(board):
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())


def restore_usb_class():
    """Put the USB net class back. Schematic generate wipes it from .kicad_pro."""
    data = json.load(open(PROJECT, encoding="utf-8"))
    classes = data.setdefault("net_settings", {}).setdefault("classes", [])
    if not any(c.get("name") == "USB" for c in classes):
        default = next((c for c in classes if c.get("name") == "Default"), {})
        usb = dict(default)
        usb.update(
            {
                "name": "USB",
                "clearance": 0.15,
                "track_width": USB_WIDTH,
                "diff_pair_width": USB_WIDTH,
                "diff_pair_gap": 0.15,
                "priority": 0,
            }
        )
        classes.append(usb)
    data["net_settings"]["netclass_patterns"] = [
        {"pattern": "USB_DP", "netclass": "USB"},
        {"pattern": "USB_DM", "netclass": "USB"},
    ]
    with open(PROJECT, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


def patch_title():
    text = open(PCB, encoding="utf-8").read()
    planes_only = "--planes-only" in sys.argv
    note = (
        "Copper pours from route_pcb.py --planes-only. Signals not routed."
        if planes_only
        else "Planes and traces from route_pcb.py. Review DRC before fab."
    )
    text = text.replace(
        "First-pass placement from generate_pcb.py. Not routed.",
        note,
    )
    text = text.replace(
        "Planes and traces from route_pcb.py. Review DRC before fab.",
        note,
    )
    with open(PCB, "w", encoding="utf-8") as fh:
        fh.write(text)


def main():
    ensure_closed()
    params = json.load(open(PARAMS, encoding="utf-8"))
    half_w = params["pcb"]["width_mm"] / 2.0
    half_h = params["pcb"]["height_mm"] / 2.0

    board = pcbnew.LoadBoard(PCB)
    board.BuildListOfNets()

    print("clearing existing copper")
    clear_copper(board)
    tie_u2_ep(board)
    print("adding zones")
    add_zones(board, half_w, half_h)
    planes_only = "--planes-only" in sys.argv
    routed, failed = 0, []
    if planes_only:
        print("planes only: skipping signal autoroute")
    else:
        print("routing signal nets")
        routed, failed = route_signals(board, half_w, half_h)
    vias = add_power_vias(board, half_w, half_h)
    print(f"power vias: {vias}")
    print("filling zones")
    fill_zones(board)

    board.BuildConnectivity()
    pcbnew.SaveBoard(PCB, board)
    patch_title()
    restore_usb_class()

    tracks = sum(1 for t in board.GetTracks() if not isinstance(t, pcbnew.PCB_VIA))
    vias_n = sum(1 for t in board.GetTracks() if isinstance(t, pcbnew.PCB_VIA))
    print(f"tracks:  {tracks}")
    print(f"vias:    {vias_n}")
    print(f"zones:   {len(list(board.Zones()))}")
    print(f"routed:  {routed} MST edges")
    if failed:
        print("UNROUTED:")
        for row in failed:
            print(" ", row)
        print(f"wrote {PCB} with {len(failed)} open ratsnest edges")
        raise SystemExit(2)
    print(f"wrote {PCB}")
    print("USB 90 ohm is still a placeholder (0.20 / 0.15 on 0.1 mm prepreg).")
    print("Do not send fab/ until kicad-cli pcb drc is clean.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
