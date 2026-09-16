#!/usr/bin/env python
"""Apply the BQ24074 power-path island to the existing routed board.

Loads recorder.kicad_pcb, does not wipe copper. Replaces U3, drops J4/D3
if they are still on the board, adds the charger programming resistors,
retargets load copper from VBAT to VSYS, fans the QFN out, then re-pours
and repairs. Run with KiCad 10 python.exe.

Do not wipe the USB-edge box: F1, C4 and the VBUS vias have to stay.
"""

from __future__ import annotations

import json
import math
import os
import sys

import pcbnew

try:
    import wx
except ImportError:
    wx = None
else:
    wx.DisableAsserts()

from generate_pcb import (
    NO_PICK_AND_PLACE,
    PLACEMENT,
    SUBSTITUTIONS,
    load_netlist,
    resolve_footprint,
    vec,
)
from route_pcb import (
    PCB,
    PLACEMENT as PLACEMENT_JSON,
    DEFAULT_WIDTH,
    MazeRouter,
    Obstacles,
    POWER_WIDTH,
    add_track,
    add_via,
    apply_board_rules,
    drc_json,
    fill_zones,
    finish,
    hop_bcu,
    mm,
    net_of,
    pad_of,
    pad_xy,
    repair_unconnected,
    save,
    stage_repair,
    stitch_orphan_gnd_pads,
    update_placement_open_items,
    via_in_zone,
    _lock,
    _place_via,
    _try_widths,
)

os.environ.setdefault("PSV_ROUTE_SKIP_LOCK", "1")

DELETE_REFS = ("J4", "D3")
REPLACE_REFS = ("U3",)
MOVED_REFS = ("C5", "R4")
NEW_REFS = ("R8", "R9", "R10", "R11")
U3_BOX = (21.5, -42.0, 27.0, -36.5)
CHARGER_NETS = {
    "CHG_STAT",
    "VBUS_CHG",
    "VBAT",
    "VSYS",
    "/Power/PROG",
    "PROG",
    "/Power/ISET",
    "/Power/ILIM",
    "/Power/TMR",
    "/Power/TS",
    "/Power/ITERM",
    "/Power/CHG_LED",
}


def ensure_net(board, name):
    info = board.FindNet(name)
    if info is None or info.GetNetCode() <= 0:
        board.Add(pcbnew.NETINFO_ITEM(board, name))
        board.BuildListOfNets()
        info = board.FindNet(name)
    return info


def netmap(board, names):
    out = {}
    for name in names:
        out[name] = ensure_net(board, name)
    return out


def fp_by_ref(board):
    return {fp.GetReference(): fp for fp in board.GetFootprints()}


def place_one(board, ref, comp, pad_nets, nets):
    x, y, rot, _note = PLACEMENT[ref]
    fp, _fpid, _sub = resolve_footprint(comp["footprint"])
    fp.SetReference(ref)
    fp.SetValue(comp["value"])
    fp.SetField("Datasheet", "~")
    fp.SetPosition(vec(x, y))
    if rot:
        fp.SetOrientationDegrees(rot)
    fp.SetPath(pcbnew.KIID_PATH())
    fp.SetExcludedFromBOM(False)
    fp.SetExcludedFromPosFiles(ref in NO_PICK_AND_PLACE)
    for pad in fp.Pads():
        name = pad_nets.get((ref, pad.GetNumber()))
        if name and name in nets:
            pad.SetNet(nets[name])
    board.Add(fp)
    return fp


def assign_pads(board, pad_nets, nets):
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for pad in fp.Pads():
            name = pad_nets.get((ref, pad.GetNumber()))
            if name and name in nets:
                pad.SetNet(nets[name])


def near_xy(x, y, tx, ty, r):
    return math.hypot(x - tx, y - ty) <= r


def near_battery(x, y):
    return near_xy(x, y, -16.0, 34.0, 10.0) or near_xy(x, y, -16.0, 26.0, 6.0)


def track_xy(item):
    if isinstance(item, pcbnew.PCB_VIA):
        x, y = mm(item.GetPosition())
        return x, y, x, y
    x0, y0 = mm(item.GetStart())
    x1, y1 = mm(item.GetEnd())
    return x0, y0, x1, y1


def touches_fp(item, fp, slop=0.4):
    x0, y0, x1, y1 = track_xy(item)
    for pad in fp.Pads():
        box = pad.GetBoundingBox()
        left = pcbnew.ToMM(box.GetLeft()) - slop
        top = pcbnew.ToMM(box.GetTop()) - slop
        right = pcbnew.ToMM(box.GetRight()) + slop
        bottom = pcbnew.ToMM(box.GetBottom()) + slop
        if (left <= x0 <= right and top <= y0 <= bottom) or (
            left <= x1 <= right and top <= y1 <= bottom
        ):
            return True
    return False


def delete_items(board, items):
    for item in items:
        board.Delete(item)
    return len(items)


def in_box(x, y, box):
    x0, y0, x1, y1 = box
    return x0 <= x <= x1 and y0 <= y <= y1


def copper_surgery(board, doomed_fps):
    doomed = []
    vsys = ensure_net(board, "VSYS")
    for item in list(board.GetTracks()):
        name = item.GetNetname()
        x0, y0, x1, y1 = track_xy(item)
        if name in {"WALL_5V", "/Power/PROG", "PROG"}:
            doomed.append(item)
            continue
        if any(touches_fp(item, fp) for fp in doomed_fps):
            doomed.append(item)
            continue
        if name in CHARGER_NETS and (
            in_box(x0, y0, U3_BOX) or in_box(x1, y1, U3_BOX)
        ):
            if name == "VBAT" and (near_battery(x0, y0) or near_battery(x1, y1)):
                continue
            doomed.append(item)
            continue
        if not isinstance(item, pcbnew.PCB_VIA):
            if math.hypot(x1 - x0, y1 - y0) < 0.08 and name in CHARGER_NETS:
                doomed.append(item)
                continue
        if name == "VSYS" and (
            near_xy(x0, y0, -16.95, -28.775, 0.4)
            or near_xy(x1, y1, -16.95, -28.775, 0.4)
        ):
            doomed.append(item)
            continue
        if name != "VBAT":
            continue
        if item.IsLocked():
            continue
        start_bat = near_battery(x0, y0)
        end_bat = near_battery(x1, y1)
        if start_bat and end_bat:
            continue
        if not start_bat and not end_bat:
            item.SetNet(vsys)
            continue
        doomed.append(item)
    return delete_items(board, doomed)


def drop_via_crowding_iset(board):
    """HEAD parked a locked GND stitch where ISET now sits."""
    dropped = 0
    for item in list(board.GetTracks()):
        if not isinstance(item, pcbnew.PCB_VIA):
            continue
        x, y = mm(item.GetPosition())
        if math.hypot(x - 16.64, y + 34.3) < 0.4:
            board.Delete(item)
            dropped += 1
    return dropped


def sync_placement_parts(board):
    comps, _nets = load_netlist()
    by_ref = {c["ref"]: c for c in comps}
    rows = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        x = round(pcbnew.ToMM(fp.GetPosition().x), 3)
        y = round(pcbnew.ToMM(fp.GetPosition().y), 3)
        rot = round(fp.GetOrientationDegrees()) % 360
        if ref.startswith("H"):
            rows.append(
                {
                    "ref": ref,
                    "value": fp.GetValue(),
                    "sheet": "mechanical",
                    "x_mm": x,
                    "y_mm": y,
                    "rot_deg": rot,
                    "layer": "F.Cu",
                    "footprint": fp.GetFPIDAsString(),
                    "footprint_in_schematic": None,
                    "substitution_reason": None,
                    "note": "mechanical only, not in the schematic",
                }
            )
            continue
        comp = by_ref.get(ref, {})
        note = PLACEMENT[ref][3] if ref in PLACEMENT else ""
        rows.append(
            {
                "ref": ref,
                "value": fp.GetValue(),
                "sheet": comp.get("sheet", ""),
                "x_mm": x,
                "y_mm": y,
                "rot_deg": rot,
                "layer": "F.Cu",
                "footprint": fp.GetFPIDAsString(),
                "footprint_in_schematic": comp.get("footprint"),
                "substitution_reason": None,
                "note": note,
            }
        )
    with open(PLACEMENT_JSON, encoding="utf-8") as fh:
        data = json.load(fh)
    data["parts"] = sorted(rows, key=lambda r: r["ref"])
    data["footprint_substitutions"] = {
        k: {"placed": v[0], "reason": v[1]} for k, v in SUBSTITUTIONS.items()
    }
    with open(PLACEMENT_JSON, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


def drop_usb_edge_chg_stat(board):
    """Maze routed CHG_STAT under U3 and boxed VBUS_CHG in."""
    dropped = 0
    for item in list(board.GetTracks()):
        if item.GetNetname() != "CHG_STAT" or item.IsLocked():
            continue
        if isinstance(item, pcbnew.PCB_VIA):
            x, y = mm(item.GetPosition())
            if y < -40.0:
                board.Delete(item)
                dropped += 1
            continue
        x0, y0, x1, y1 = track_xy(item)
        if y0 < -40.0 or y1 < -40.0:
            board.Delete(item)
            dropped += 1
    return dropped


def drop_charger_crumbs(board):
    dropped = 0
    for item in list(board.GetTracks()):
        if isinstance(item, pcbnew.PCB_VIA):
            continue
        if item.GetNetname() not in CHARGER_NETS:
            continue
        x0, y0, x1, y1 = track_xy(item)
        if math.hypot(x1 - x0, y1 - y0) < 0.08:
            board.Delete(item)
            dropped += 1
    return dropped


def maze_pads(board, obstacles, half_w, half_h, net, src, dst, width=DEFAULT_WIDTH):
    if src is None or dst is None:
        return False
    router = MazeRouter(board, obstacles, half_w, half_h)
    return router.connect(board, net, src, dst, width)


def lock_net_tracks(board, netname):
    n = 0
    for item in board.GetTracks():
        if item.GetNetname() != netname or item.IsLocked():
            continue
        _lock(item)
        n += 1
    return n


def delete_tracks_near(board, netname, x, y, slop=0.15):
    dropped = 0
    for item in list(board.GetTracks()):
        if isinstance(item, pcbnew.PCB_VIA) or item.GetNetname() != netname:
            continue
        x0, y0, x1, y1 = track_xy(item)
        if near_xy(x0, y0, x, y, slop) or near_xy(x1, y1, x, y, slop):
            board.Delete(item)
            dropped += 1
    return dropped


def drop_dangling_stubs(board, report):
    """Remove fanout stubs DRC calls dangling when the net has no pad open."""
    open_nets = set()
    for entry in report.get("unconnected_items", []):
        for item in entry.get("items", []):
            desc = item.get("description", "")
            if "Pad " in desc or "Zone " in desc:
                if "[" in desc:
                    open_nets.add(desc.split("[", 1)[1].split("]")[0])
    index = {}
    for track in board.GetTracks():
        index[track.m_Uuid.AsString()] = track
    dropped = 0
    for violation in report.get("violations", []):
        if violation.get("type") != "track_dangling":
            continue
        for item in violation.get("items", []):
            obj = index.get(item["uuid"])
            if obj is None or isinstance(obj, pcbnew.PCB_VIA):
                continue
            name = obj.GetNetname()
            if name in open_nets:
                continue
            board.Delete(obj)
            dropped += 1
    return dropped


def close_remaining(board, half_w, half_h):
    """Join leftover charger nets and drop dangling stubs."""
    apply_board_rules(board)
    n = drop_charger_crumbs(board)
    if n:
        print(f"  dropped {n} charger crumbs")
    n = drop_usb_edge_chg_stat(board)
    if n:
        print(f"  dropped {n} USB-edge CHG_STAT maze track(s)")
    n = delete_tracks_near(board, "VSYS", -16.95, -28.775, 0.5)
    if n:
        print(f"  dropped {n} orphan VSYS fragment(s)")

    obstacles = Obstacles(board, half_w, half_h)
    vchg = net_of(board, "VBUS_CHG")
    if maze_pads(
        board, obstacles, half_w, half_h, vchg,
        pad_of(board, "U3", "7"), pad_of(board, "C4", "1"),
    ):
        print("  VBUS_CHG maze pin 7 to C4")
        lock_net_tracks(board, "VBUS_CHG")
    else:
        print("  VBUS_CHG maze failed")

    obstacles = Obstacles(board, half_w, half_h)
    vbat = net_of(board, "VBAT")
    for y_edge in (36.40, 36.80, 37.00, 37.20):
        edge = [
            (26.20, -41.00), (26.20, -42.40), (31.10, -42.40),
            (31.10, y_edge), (-23.50, y_edge), (-23.50, 34.00),
        ]
        if _try_widths(board, obstacles, vbat, edge, POWER_WIDTH, True,
                       pcbnew.B_Cu):
            print(f"  VBAT right-edge hop y={y_edge:.2f}")
            break
    else:
        print("  VBAT right-edge hop failed")

    obstacles = Obstacles(board, half_w, half_h)
    chg = net_of(board, "CHG_STAT")
    if maze_pads(
        board, obstacles, half_w, half_h, chg,
        pad_of(board, "U3", "9"), pad_of(board, "D2", "2"),
    ):
        print("  CHG_STAT maze pin 9 to D2")
        lock_net_tracks(board, "CHG_STAT")
    else:
        u3_9 = pad_of(board, "U3", "9")
        d2_2 = pad_of(board, "D2", "2")
        if u3_9 is not None and d2_2 is not None and hop_bcu(
            board, obstacles, chg, pad_xy(u3_9), pad_xy(d2_2),
            (22.00, -40.60), (25.50, -32.40), True,
        ):
            print("  CHG_STAT B.Cu hop")
        else:
            print("  CHG_STAT maze failed")

    obstacles = Obstacles(board, half_w, half_h)
    gnd = net_of(board, "GND")
    orphans = 0
    for zone in board.Zones():
        if zone.GetNetname() == "GND":
            orphans += int(via_in_zone(board, obstacles, gnd, zone))
    pad_orphans = stitch_orphan_gnd_pads(board, obstacles)
    if orphans or pad_orphans:
        print(f"  GND stitches: {orphans} zone, {pad_orphans} pad")

    apply_board_rules(board)
    fill_zones(board)
    save(board)
    data = drc_json(PCB)
    board = pcbnew.LoadBoard(PCB)
    board.BuildListOfNets()
    n = drop_dangling_stubs(board, data)
    if n:
        print(f"  dropped {n} dangling stubs")
        apply_board_rules(board)
        fill_zones(board)
        save(board)
        board = pcbnew.LoadBoard(PCB)
        board.BuildListOfNets()
        data = drc_json(PCB)
    open_items = len(data.get("unconnected_items", []))
    if open_items:
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
        data = drc_json(PCB)
        n = drop_dangling_stubs(board, data)
        if n:
            print(f"  dropped {n} dangling stubs after maze")
            save(board)
            board = pcbnew.LoadBoard(PCB)
            board.BuildListOfNets()
    return board


def board_extents():
    params = json.load(
        open(
            os.path.join(os.path.dirname(PCB), "..", "..", "cad", "params.json"),
            encoding="utf-8",
        )
    )
    return params["pcb"]["width_mm"] / 2.0, params["pcb"]["height_mm"] / 2.0


def main():
    if "--finish-opens" in sys.argv:
        half_w, half_h = board_extents()
        board = pcbnew.LoadBoard(PCB)
        apply_board_rules(board)
        board.BuildListOfNets()
        board = close_remaining(board, half_w, half_h)
        board, _ = finish(board, half_w, half_h)
        data = drc_json(PCB)
        unconnected = len(data.get("unconnected_items", []))
        violations = len(data.get("violations", []))
        sync_placement_parts(board)
        update_placement_open_items(board, unconnected, violations)
        print(f"drc: {violations} violations, {unconnected} open")
        if violations or unconnected:
            raise SystemExit(2)
        print("apply_power_path --finish-opens: ok")
        return 0

    source = os.environ.get("PSV_RESTORE_PCB", PCB)
    comps, nets = load_netlist()
    by_ref = {c["ref"]: c for c in comps}
    pad_nets = {}
    for name, nodes in nets.items():
        for ref, pin in nodes:
            pad_nets[(ref, pin)] = name

    board = pcbnew.LoadBoard(source)
    if source != PCB:
        print(f"loaded {source}")
    apply_board_rules(board)
    board.BuildListOfNets()
    nmap = netmap(board, list(nets))

    fps = fp_by_ref(board)
    outgoing = list(DELETE_REFS) + list(REPLACE_REFS) + list(MOVED_REFS)
    outgoing += [ref for ref in NEW_REFS if ref in fps]
    doomed = [fps[ref] for ref in outgoing if ref in fps]
    print(f"removing copper on {len(doomed)} outgoing footprints")
    n = copper_surgery(board, doomed)
    print(f"  deleted/retargeted {n} track items before the swap")
    nvia = drop_via_crowding_iset(board)
    if nvia:
        print(f"  dropped {nvia} GND stitch via(s) under ISET")

    for ref in outgoing:
        fp = fp_by_ref(board).get(ref)
        if fp is not None:
            print(f"  delete {ref}")
            board.Delete(fp)

    for ref in list(REPLACE_REFS) + list(MOVED_REFS) + list(NEW_REFS):
        comp = by_ref.get(ref)
        if comp is None:
            raise SystemExit(f"{ref} missing from netlist")
        print(f"  place {ref} at {PLACEMENT[ref][:3]}")
        place_one(board, ref, comp, pad_nets, nmap)

    assign_pads(board, pad_nets, nmap)
    board.BuildListOfNets()
    board.BuildConnectivity()
    locked = 0
    for item in board.GetTracks():
        if not item.IsLocked():
            item.SetLocked(True)
            locked += 1
    print(f"  locked {locked} existing tracks so island repair cannot rip them")
    save(board)

    params = json.load(
        open(
            os.path.join(os.path.dirname(PCB), "..", "..", "cad", "params.json"),
            encoding="utf-8",
        )
    )
    half_w = params["pcb"]["width_mm"] / 2.0
    half_h = params["pcb"]["height_mm"] / 2.0
    board = pcbnew.LoadBoard(PCB)
    board.BuildListOfNets()
    board = stage_repair(board, half_w, half_h, passes=8)
    board, _ = finish(board, half_w, half_h)
    data = drc_json(PCB)
    unconnected = len(data.get("unconnected_items", []))
    violations = len(data.get("violations", []))
    sync_placement_parts(board)
    update_placement_open_items(board, unconnected, violations)
    print(f"drc: {violations} violations, {unconnected} open")
    if violations or unconnected:
        raise SystemExit(2)
    print("apply_power_path: ok")


if __name__ == "__main__":
    sys.exit(main())
