#!/usr/bin/env python
"""Move BT1 to B.Cu and swap J3 for the 4 GB SD NAND.

Does not wipe copper. Do not confuse this with generate_pcb.py.

Historical: BT1_XY / J3_XY in this file are from before apply_lid_180.py.
Do not re-run this on the live board.

Run with the KiCad 10 interpreter:

    /c/Users/zachr/AppData/Local/Programs/KiCad/10.0/bin/python.exe apply_hollow_tray.py
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

BT1_XY = (17.0, -35.0)
J3_XY = (-22.0, -18.0)
J3_NETS = {
    "1": "SD_D2",
    "2": "SD_D3",
    "3": "SD_CMD",
    "4": "VDD33",
    "5": "SD_CLK",
    "6": "GND",
    "7": "SD_D0",
    "8": "SD_D1",
}
BT1_NETS = {"1": "VBAT", "2": "GND"}


def vec(x_mm: float, y_mm: float):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm))


def net_of(board, name: str):
    net = board.FindNet(name)
    if net is None or net.GetNetCode() <= 0:
        net = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net)
    return net


def drop_pad_copper(board, fp) -> int:
    """Drop tracks and vias that land on this footprint's pads."""
    if fp is None:
        return 0
    slop = pcbnew.FromMM(0.35)
    pads = [pad.GetPosition() for pad in fp.Pads()]
    doomed = []
    for item in list(board.GetTracks()):
        if isinstance(item, pcbnew.PCB_VIA):
            pts = [item.GetPosition()]
        else:
            pts = [item.GetStart(), item.GetEnd()]
        hit = False
        for pad_pt in pads:
            for pt in pts:
                if abs(pt.x - pad_pt.x) <= slop and abs(pt.y - pad_pt.y) <= slop:
                    hit = True
                    break
            if hit:
                break
        if hit:
            doomed.append(item)
    for item in doomed:
        board.Delete(item)
    return len(doomed)


def assign_nets(fp, table: dict[str, str], board) -> None:
    for pad in fp.Pads():
        name = table.get(pad.GetNumber())
        if name:
            pad.SetNet(net_of(board, name))


def move_bt1(board) -> None:
    fp = board.FindFootprintByReference("BT1")
    if fp is None:
        raise SystemExit("BT1 is missing from the board")
    n = drop_pad_copper(board, fp)
    print(f"  dropped {n} track(s) on the old BT1 pads")
    fp.SetPosition(vec(*BT1_XY))
    fp.SetOrientationDegrees(180)
    if board.GetLayerName(fp.GetLayer()) != "B.Cu":
        fp.Flip(fp.GetPosition(), False)
    # Pad 1 (VBAT) must stay west after the flip.
    pad1 = next((p for p in fp.Pads() if p.GetNumber() == "1"), None)
    if pad1 is not None and pcbnew.ToMM(pad1.GetPosition().x) > 0:
        fp.SetOrientationDegrees((fp.GetOrientationDegrees() + 180) % 360)
    assign_nets(fp, BT1_NETS, board)
    pad1 = next((p for p in fp.Pads() if p.GetNumber() == "1"), None)
    if pad1 is None:
        raise SystemExit("BT1 has no pad 1")
    print(
        "  BT1 now "
        f"{board.GetLayerName(fp.GetLayer())} at ({BT1_XY[0]}, {BT1_XY[1]}) "
        f"rot {fp.GetOrientationDegrees():.0f}; pad 1 at "
        f"({pcbnew.ToMM(pad1.GetPosition().x):.2f}, "
        f"{pcbnew.ToMM(pad1.GetPosition().y):.2f})"
    )


def replace_j3(board) -> None:
    old = board.FindFootprintByReference("J3")
    n = drop_pad_copper(board, old)
    print(f"  dropped {n} track(s) on the old J3 pads")
    if old is not None:
        board.Delete(old)
    fp = pcbnew.FootprintLoad(PRETTY, "ZDSD32GLGEAG")
    if fp is None:
        raise SystemExit(f"could not load ZDSD32GLGEAG from {PRETTY}")
    fp.SetFPID(pcbnew.LIB_ID("PSV", "ZDSD32GLGEAG"))
    fp.SetReference("J3")
    fp.SetValue("ZDSD32GLGEAG")
    fp.SetField("Datasheet", "~")
    fp.SetPosition(vec(*J3_XY))
    fp.SetOrientationDegrees(0)
    fp.SetExcludedFromBOM(False)
    fp.SetExcludedFromPosFiles(False)
    assign_nets(fp, J3_NETS, board)
    board.Add(fp)
    print(f"  J3 is now PSV:ZDSD32GLGEAG at ({J3_XY[0]}, {J3_XY[1]})")


def refresh_placement(board) -> None:
    with open(PLACEMENT, encoding="utf-8") as fh:
        data = json.load(fh)
    rows = {row["ref"]: row for row in data.get("parts", [])}
    bt1 = board.FindFootprintByReference("BT1")
    j3 = board.FindFootprintByReference("J3")
    if bt1 is not None:
        rows["BT1"] = {
            **rows.get("BT1", {}),
            "ref": "BT1",
            "value": "pigtail 1S",
            "sheet": rows.get("BT1", {}).get("sheet", "Power"),
            "x_mm": round(pcbnew.ToMM(bt1.GetPosition().x), 3),
            "y_mm": round(pcbnew.ToMM(bt1.GetPosition().y), 3),
            "rot_deg": round(bt1.GetOrientationDegrees()) % 360,
            "layer": board.GetLayerName(bt1.GetLayer()),
            "footprint": bt1.GetFPIDAsString(),
            "footprint_in_schematic": "PSV:Battery_Pigtail_2P",
            "substitution_reason": None,
            "note": "B.Cu pouch pigtail pads east of J2, pad 1 VBAT (east), pad 2 GND",
        }
    if j3 is not None:
        rows["J3"] = {
            **rows.get("J3", {}),
            "ref": "J3",
            "value": "ZDSD32GLGEAG",
            "sheet": rows.get("J3", {}).get("sheet", "IO"),
            "x_mm": round(pcbnew.ToMM(j3.GetPosition().x), 3),
            "y_mm": round(pcbnew.ToMM(j3.GetPosition().y), 3),
            "rot_deg": round(j3.GetOrientationDegrees()) % 360,
            "layer": board.GetLayerName(j3.GetLayer()),
            "footprint": j3.GetFPIDAsString(),
            "footprint_in_schematic": "PSV:ZDSD32GLGEAG",
            "substitution_reason": None,
            "note": "Zetta 4 GB SD NAND, LGA-8 8.0 x 6.2 x 0.8 mm, C5188571",
        }
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
    opens = [
        item
        for item in data.get("open_items", [])
        if "pouch sits in the tray" not in item
        and "Pigtail wraps" not in item
        and "microSD" not in item
    ]
    opens.append(
        "The Jauch LP305166JH-PCM-2-WIRES-70MM pack (66 x 51.5 x 3.3 mm, "
        "1200 mAh min) is taped to B.Cu at (0, 0) and wrapped in kapton, "
        "including the face toward the shunt. About 0.15 mm of air under "
        "the wrapped cell so the pouch is not a spacer. BT1 is B.Cu at "
        "(17, -35), east of J2 and just south of the cell, pad 1 VBAT on "
        "the east land. Four 5.0 mm posts carry the board."
    )
    opens.append(
        "J3 is Zetta ZDSD32GLGEAG (LCSC C5188571) 32 Gbit / 4 GB SD NAND, "
        "LGA-8 8.0 x 6.2 x 0.8 mm at (22, 18). Pin numbers match a microSD "
        "socket. Firmware formats FAT on first mount if the chip is blank. "
        "Any 32 Gbit LGA-8 with the same pad map is the substitute; do not "
        "drop to the 8 Gbit grade."
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
    move_bt1(board)
    replace_j3(board)
    board.BuildListOfNets()
    pcbnew.SaveBoard(PCB, board)
    refresh_placement(board)
    print("placement.json refreshed; copper was not wiped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
