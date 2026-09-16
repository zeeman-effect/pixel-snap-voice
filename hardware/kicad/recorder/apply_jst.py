#!/usr/bin/env python
"""Put the real JST-PH on BT1 and add C21 next to U3.

Loads recorder.kicad_pcb. Does not wipe copper. Replaces the 7.8 mm
solder-wire land with JST_PH_S2B-PH-K, places the local BAT ceramic,
mazes C21 onto VBAT, then re-pours. Run with KiCad 10 python.exe.
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
from generate_pcb import PLACEMENT, load_netlist, vec
from route_pcb import (
    PCB,
    MazeRouter,
    Obstacles,
    POWER_WIDTH,
    add_track,
    apply_board_rules,
    drc_json,
    fill_zones,
    finish,
    pad_of,
    pad_xy,
    repair_unconnected,
    save,
    stitch_orphan_gnd_pads,
    update_placement_open_items,
)

os.environ.setdefault("PSV_ROUTE_SKIP_LOCK", "1")

REPLACE_REFS = ("BT1",)
NEW_REFS = ("C21",)


def pads_of(board, ref, number):
    out = []
    for fp in board.GetFootprints():
        if fp.GetReference() != ref:
            continue
        for pad in fp.Pads():
            if pad.GetNumber() == number:
                out.append(pad)
    return out


def maze_join(board, obstacles, half_w, half_h, net, src_ref, src_pin,
              dst_ref, dst_pin, width=POWER_WIDTH):
    sources = pads_of(board, src_ref, src_pin)
    targets = pads_of(board, dst_ref, dst_pin)
    if not sources or not targets:
        print(f"  missing pads {src_ref}.{src_pin} or {dst_ref}.{dst_pin}")
        return False
    router = MazeRouter(board, obstacles, half_w, half_h)
    for src in sources:
        for dst in targets:
            if router.connect(board, net, src, dst, width):
                return True
    return False


def lock_existing(board):
    n = 0
    for item in board.GetTracks():
        if not item.IsLocked():
            item.SetLocked(True)
            n += 1
    return n


def drop_footprint_copper(board, fps):
    """Drop copper that lands on the outgoing pads, keep the VBAT B.Cu trunk."""
    doomed = []
    for item in list(board.GetTracks()):
        if not any(touches_fp(item, fp) for fp in fps):
            continue
        if (
            not isinstance(item, pcbnew.PCB_VIA)
            and item.GetLayer() == pcbnew.B_Cu
            and item.GetNetname() == "VBAT"
        ):
            continue
        doomed.append(item)
    for item in doomed:
        board.Delete(item)
    return len(doomed)


def park_silk(board):
    """finish() could not seat Rstat once C21 took the east gap.

    Put the three labels back on known-clear centres: Rstat and Rchg at
    the seats the routed board already used, C21 south of its own body.
    """
    fps = fp_by_ref(board)
    seats = {
        "Rstat": (29.174, -29.087),
        "Rchg": (28.000, -31.027),
        "C21": (29.000, -26.500),
    }
    for ref, (x, y) in seats.items():
        fp = fps.get(ref)
        if fp is None:
            continue
        fp.Reference().SetPosition(vec(x, y))


def jumper_c21(board, obstacles, half_w, half_h, nmap):
    """C21 pad 1 is VBAT; pad 2 is GND and should hit the F.Cu pour."""
    vbat = nmap.get("VBAT") or board.FindNet("VBAT")
    ok = maze_join(
        board, obstacles, half_w, half_h, vbat,
        "C21", "1", "U3", "2", POWER_WIDTH,
    )
    print(f"  maze VBAT C21.1 -> U3.2: {'ok' if ok else 'FAIL'}")
    if not ok:
        c21 = pad_of(board, "C21", "1")
        u3 = pad_of(board, "U3", "2")
        if c21 is None or u3 is None:
            return False
        x0, y0 = pad_xy(c21)
        x1, y1 = pad_xy(u3)
        add_track(board, vbat, x0, y0, x1, y0, pcbnew.F_Cu, POWER_WIDTH)
        add_track(board, vbat, x1, y0, x1, y1, pcbnew.F_Cu, POWER_WIDTH)
        print("  fell back to an F.Cu L for C21")
        ok = True
    return ok


def main():
    comps, nets = load_netlist()
    by_ref = {c["ref"]: c for c in comps}
    pad_nets = {}
    for name, nodes in nets.items():
        for ref, pin in nodes:
            pad_nets[(ref, pin)] = name

    for ref in list(REPLACE_REFS) + list(NEW_REFS):
        if ref not in by_ref:
            raise SystemExit(f"{ref} missing from netlist")
        if ref not in PLACEMENT:
            raise SystemExit(f"{ref} missing from generate_pcb.PLACEMENT")

    board = pcbnew.LoadBoard(PCB)
    apply_board_rules(board)
    board.BuildListOfNets()
    nmap = netmap(board, list(nets))

    fps = fp_by_ref(board)
    outgoing = [fps[ref] for ref in REPLACE_REFS + NEW_REFS if ref in fps]
    if outgoing:
        n = drop_footprint_copper(board, outgoing)
        print(f"  deleted {n} track item(s) on outgoing BT1/C21 lands")
        for fp in outgoing:
            print(f"  delete {fp.GetReference()} {fp.GetFPIDAsString()}")
            board.Delete(fp)

    for ref in list(REPLACE_REFS) + list(NEW_REFS):
        print(f"  place {ref} at {PLACEMENT[ref][:3]}")
        place_one(board, ref, by_ref[ref], pad_nets, nmap)

    for fp in board.GetFootprints():
        if fp.GetReference() not in REPLACE_REFS + NEW_REFS:
            continue
        for pad in fp.Pads():
            name = pad_nets.get((fp.GetReference(), pad.GetNumber()))
            if name and name in nmap:
                pad.SetNet(nmap[name])

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

    if not jumper_c21(board, obstacles, half_w, half_h, nmap):
        raise SystemExit(2)

    obstacles = Obstacles(board, half_w, half_h)
    n_gnd = stitch_orphan_gnd_pads(board, obstacles)
    if n_gnd:
        print(f"  stitched {n_gnd} orphan GND pad(s)")
    fill_zones(board)
    save(board)

    data = drc_json(PCB)
    unconnected = len(data.get("unconnected_items", []))
    if unconnected:
        board = pcbnew.LoadBoard(PCB)
        apply_board_rules(board)
        board.BuildListOfNets()
        obstacles = Obstacles(board, half_w, half_h)
        router = MazeRouter(board, obstacles, half_w, half_h)
        healed, stuck = repair_unconnected(board, obstacles, router, data)
        print(f"  maze healed {healed}, still open {len(stuck)}")
        fill_zones(board)
        save(board)

    board, homeless = finish(board, half_w, half_h)
    if homeless:
        print(f"  {len(homeless)} designator(s) still crowded before park")
    park_silk(board)
    save(board)

    data = drc_json(PCB)
    unconnected = len(data.get("unconnected_items", []))
    violations = len(data.get("violations", []))
    board = pcbnew.LoadBoard(PCB)
    sync_placement_parts(board)
    update_placement_open_items(board, unconnected, violations)
    print(f"drc: {violations} violations, {unconnected} open")
    if violations or unconnected:
        raise SystemExit(2)
    print("apply_jst: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
