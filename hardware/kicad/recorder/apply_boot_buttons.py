#!/usr/bin/env python
"""Add SW_BOOT and SW_RST to the existing routed board.

Loads recorder.kicad_pcb. Does not wipe copper and does not run the
full autorouter. Places the two XKB TS-1187A lands east of the Rboot
column, mazes short BOOT and EN stubs, then re-pours. Run with KiCad 10
python.exe.
"""

from __future__ import annotations

import os
import sys

import pcbnew

try:
    import wx
except ImportError:
    wx = None
else:
    wx.DisableAsserts()

from apply_power_path import (
    board_extents,
    fp_by_ref,
    netmap,
    place_one,
    sync_placement_parts,
    touches_fp,
)
from generate_pcb import PLACEMENT, load_netlist
from route_pcb import (
    PCB,
    DEFAULT_WIDTH,
    MazeRouter,
    Obstacles,
    add_track,
    apply_board_rules,
    drc_json,
    fill_zones,
    finish,
    pad_xy,
    save,
    stitch_orphan_gnd_pads,
    update_placement_open_items,
)

os.environ.setdefault("PSV_ROUTE_SKIP_LOCK", "1")

NEW_REFS = ("SW_BOOT", "SW_RST")
# Local MCU-sheet nets. The board already carries these from U1 / Rboot / R1.
SIGNAL_JOINS = (
    ("/MCU_USB/BOOT", "SW_BOOT", "1", "Rboot", "2"),
    ("/MCU_USB/EN", "SW_RST", "1", "R1", "2"),
)


def pads_of(board, ref, number):
    out = []
    for fp in board.GetFootprints():
        if fp.GetReference() != ref:
            continue
        for pad in fp.Pads():
            if pad.GetNumber() == number:
                out.append(pad)
    return out


def maze_join(board, obstacles, half_w, half_h, net, src_ref, src_pin, dst_ref, dst_pin):
    sources = pads_of(board, src_ref, src_pin)
    targets = pads_of(board, dst_ref, dst_pin)
    if not sources or not targets:
        print(f"  missing pads {src_ref}.{src_pin} or {dst_ref}.{dst_pin}")
        return False
    router = MazeRouter(board, obstacles, half_w, half_h)
    for src in sources:
        for dst in targets:
            if router.connect(board, net, src, dst, DEFAULT_WIDTH):
                return True
    return False


def lock_existing(board):
    n = 0
    for item in board.GetTracks():
        if not item.IsLocked():
            item.SetLocked(True)
            n += 1
    return n


def drop_switch_copper(board, fps):
    doomed = []
    for item in list(board.GetTracks()):
        if any(touches_fp(item, fp) for fp in fps):
            doomed.append(item)
            continue
        # Last pass left maze crumbs whose mid-segments miss the pads.
        if item.IsLocked():
            continue
        if item.GetNetname() in {"/MCU_USB/BOOT", "/MCU_USB/EN"}:
            doomed.append(item)
    for item in doomed:
        board.Delete(item)
    return len(doomed)


def jumper_duplicate_pads(board):
    """The TS-1187A land has two pads per pin and they are not jumpers."""
    n = 0
    for ref in NEW_REFS:
        fp = fp_by_ref(board).get(ref)
        if fp is None:
            continue
        grouped = {}
        for pad in fp.Pads():
            grouped.setdefault(pad.GetNumber(), []).append(pad)
        for pads in grouped.values():
            if len(pads) < 2:
                continue
            net = pads[0].GetNet()
            x0, y0 = pad_xy(pads[0])
            x1, y1 = pad_xy(pads[1])
            add_track(board, net, x0, y0, x1, y1, pcbnew.F_Cu, DEFAULT_WIDTH)
            n += 1
    return n


def main():
    comps, nets = load_netlist()
    by_ref = {c["ref"]: c for c in comps}
    pad_nets = {}
    for name, nodes in nets.items():
        for ref, pin in nodes:
            pad_nets[(ref, pin)] = name

    for ref in NEW_REFS:
        if ref not in by_ref:
            raise SystemExit(f"{ref} missing from netlist")
        if ref not in PLACEMENT:
            raise SystemExit(f"{ref} missing from generate_pcb.PLACEMENT")

    board = pcbnew.LoadBoard(PCB)
    apply_board_rules(board)
    board.BuildListOfNets()
    nmap = netmap(board, list(nets))

    fps = fp_by_ref(board)
    outgoing = [fps[ref] for ref in NEW_REFS if ref in fps]
    if outgoing:
        n = drop_switch_copper(board, outgoing)
        print(f"  deleted {n} track item(s) on existing Boot/Reset lands")
        for fp in outgoing:
            print(f"  delete {fp.GetReference()}")
            board.Delete(fp)

    for ref in NEW_REFS:
        print(f"  place {ref} at {PLACEMENT[ref][:3]}")
        place_one(board, ref, by_ref[ref], pad_nets, nmap)

    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref not in NEW_REFS:
            continue
        for pad in fp.Pads():
            name = pad_nets.get((ref, pad.GetNumber()))
            if name and name in nmap:
                pad.SetNet(nmap[name])

    n_j = jumper_duplicate_pads(board)
    print(f"  jumpered {n_j} same-number pad pair(s)")
    board.BuildListOfNets()
    board.BuildConnectivity()
    locked = lock_existing(board)
    print(f"  locked {locked} existing tracks")
    save(board)

    half_w, half_h = board_extents()
    board = pcbnew.LoadBoard(PCB)
    apply_board_rules(board)
    board.BuildListOfNets()
    nmap = netmap(board, list(nets))
    fill_zones(board)
    obstacles = Obstacles(board, half_w, half_h)

    for netname, src_ref, src_pin, dst_ref, dst_pin in SIGNAL_JOINS:
        net = nmap.get(netname) or board.FindNet(netname)
        if net is None or net.GetNetCode() <= 0:
            raise SystemExit(f"board has no net {netname!r}")
        ok = maze_join(
            board, obstacles, half_w, half_h, net, src_ref, src_pin, dst_ref, dst_pin
        )
        print(f"  maze {netname} {src_ref}.{src_pin} -> {dst_ref}.{dst_pin}: "
              f"{'ok' if ok else 'FAIL'}")
        if not ok:
            raise SystemExit(2)
        obstacles = Obstacles(board, half_w, half_h)

    n_gnd = stitch_orphan_gnd_pads(board, obstacles)
    if n_gnd:
        print(f"  stitched {n_gnd} orphan GND pad(s)")
    fill_zones(board)
    save(board)

    board, homeless = finish(board, half_w, half_h)
    if homeless:
        print(f"  {len(homeless)} designator(s) still crowded")

    data = drc_json(PCB)
    unconnected = len(data.get("unconnected_items", []))
    violations = len(data.get("violations", []))
    board = pcbnew.LoadBoard(PCB)
    sync_placement_parts(board)
    update_placement_open_items(board, unconnected, violations)
    print(f"drc: {violations} violations, {unconnected} open")
    if violations or unconnected:
        raise SystemExit(2)
    print("apply_boot_buttons: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
