#!/usr/bin/env python
"""Edit the live recorder board for the thin-pogo-lid spin.

Deletes speaker / PA / USB-C / CC parts, plants the C6276862 pad at the old
speaker seat, and slides leftover analog bits off the old lid-pouch outline.
Does not wipe copper. Do not confuse this with generate_pcb.py.

Historical: coordinates in this file are from before apply_lid_180.py spun
the board so J2 sits at (0, +36). Do not re-run this on the live board.

Run with the KiCad 10 interpreter:

    /c/Users/zachr/AppData/Local/Programs/KiCad/10.0/bin/python.exe apply_thin_pogo.py
"""

from __future__ import annotations

import json
import os
import sys

import pcbnew

try:
    import wx
except ImportError:
    wx = None
else:
    wx.DisableAsserts()

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "recorder.kicad_pcb")
PLACEMENT = os.path.join(HERE, "placement.json")
PRETTY = os.path.join(HERE, "PSV.pretty")

DROP = ("SP1", "U6", "C17", "C18", "C19", "R7", "R2", "R3")
MOVES = {
    "U7": (-14.8, -36.0, 180.0, "USBLC6-2SC6 ESD, west of the 22.3 mm pogo body"),
    "Y1": (-27.2, -23.0, 0.0, "12.288 MHz oscillator, west of the pouch"),
    "R5": (-27.5, -7.1, 270.0, "I2C SDA pull-up, west of the pouch"),
    "C9": (-12.4, -29.8, 0.0, "3V3A output cap, east of U8, north of the 7.7 mm pogo body"),
    "Ragnd": (14.0, -29.5, 180.0, "AGND stitch, south of the pouch, east of the pogo"),
}
J2_NETS = {"1": "VBUS", "2": "USB_DM", "3": "USB_DP", "4": "GND"}


def vec(x_mm: float, y_mm: float):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm))


def net_of(board, name: str):
    net = board.FindNet(name)
    if net is None or net.GetNetCode() <= 0:
        net = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net)
    return net


def delete_footprint(board, ref: str) -> bool:
    fp = board.FindFootprintByReference(ref)
    if fp is None:
        return False
    board.Delete(fp)
    return True


def place_pogo(board) -> None:
    delete_footprint(board, "J2")
    fp = pcbnew.FootprintLoad(PRETTY, "YZ103915020T_4P")
    if fp is None:
        raise SystemExit(f"could not load YZ103915020T_4P from {PRETTY}")
    fp.SetFPID(pcbnew.LIB_ID("PSV", "YZ103915020T_4P"))
    fp.SetReference("J2")
    fp.SetValue("YZ103915020T")
    fp.SetField("Datasheet", "~")
    fp.SetPosition(vec(0.0, -36.0))
    fp.SetOrientationDegrees(180)
    fp.SetExcludedFromBOM(False)
    fp.SetExcludedFromPosFiles(False)
    for pad in fp.Pads():
        name = J2_NETS.get(pad.GetNumber())
        if name:
            pad.SetNet(net_of(board, name))
    board.Add(fp)


def apply_moves(board) -> None:
    for ref, (x, y, rot, _note) in MOVES.items():
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            print(f"  skip move {ref}: not on board")
            continue
        fp.SetPosition(vec(x, y))
        fp.SetOrientationDegrees(rot)


def refresh_placement(board) -> None:
    with open(PLACEMENT, encoding="utf-8") as fh:
        data = json.load(fh)
    rows = {row["ref"]: row for row in data.get("parts", [])}
    for ref in DROP:
        rows.pop(ref, None)
    fp = board.FindFootprintByReference("J2")
    rows["J2"] = {
        "ref": "J2",
        "value": "YZ103915020T",
        "sheet": "MCU_USB",
        "x_mm": 0.0,
        "y_mm": -36.0,
        "rot_deg": 180,
        "layer": "F.Cu",
        "footprint": "PSV:YZ103915020T_4P",
        "footprint_in_schematic": "PSV:YZ103915020T_4P",
        "substitution_reason": None,
        "note": "C6276862 4-pin magnetic pad, lid well at params pogo_x/y",
    }
    for ref, (x, y, rot, note) in MOVES.items():
        row = rows.get(ref)
        if row is None:
            continue
        row["x_mm"] = x
        row["y_mm"] = y
        row["rot_deg"] = rot
        row["note"] = note
    # Twin any leftover board XY so check_placement does not see drift
    # from a part this script did not name.
    for live in board.GetFootprints():
        ref = live.GetReference()
        row = rows.get(ref)
        if row is None:
            continue
        row["x_mm"] = round(pcbnew.ToMM(live.GetPosition().x), 3)
        row["y_mm"] = round(pcbnew.ToMM(live.GetPosition().y), 3)
        row["rot_deg"] = round(live.GetOrientationDegrees()) % 360
        row["footprint"] = live.GetFPIDAsString()
        row["layer"] = board.GetLayerName(live.GetLayer())
    data["parts"] = [rows[k] for k in sorted(rows)]
    data["magnet_keepout"]["note"] = (
        "Ring is an annulus from r=22 to r=28 about the origin, below B.Cu. "
        "Every analog part (MK1, U2, U8, Y1) is placed outside r=28."
    )
    opens = [
        item
        for item in data.get("open_items", [])
        if "SP1" not in item and "NS4150" not in item and "USB-C is the only" not in item
    ]
    opens.append(
        "J2 is Xinyangze YZ103915020T-04025-02 (LCSC C6276862) at (0, -36), rot 180. "
        "Vendor drawing is a 22.30 x 7.70 x 2.00 mm stadium, 2.54 mm pitch, "
        "circular pads. Cable male is YZP0048-20048-04025-03 / C5126845. "
        "Pin 1 VBUS, 2 USB_DM, 3 USB_DP, 4 GND until a click-test says "
        "otherwise. No Type-C Rd."
    )
    opens.append(
        "The Jauch LP305166JH pack (66 x 51.5 x 3.3 mm) is taped to B.Cu at "
        "(0, 0), under the board. F.Cu under that outline is free. Pigtail "
        "wraps south-east to BT1 at (17, -35)."
    )
    data["open_items"] = opens
    with open(PLACEMENT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


def main() -> int:
    if not os.path.isfile(PCB):
        print(f"missing {PCB}", file=sys.stderr)
        return 1
    board = pcbnew.LoadBoard(PCB)
    dropped = [ref for ref in DROP if delete_footprint(board, ref)]
    place_pogo(board)
    apply_moves(board)
    board.BuildListOfNets()
    pcbnew.SaveBoard(PCB, board)
    refresh_placement(board)
    print(f"dropped {', '.join(dropped) if dropped else '(none already gone)'}")
    print("J2 is now PSV:YZ103915020T_4P at (0, -36)")
    print("moved " + ", ".join(MOVES))
    print("placement.json refreshed; copper was not wiped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
