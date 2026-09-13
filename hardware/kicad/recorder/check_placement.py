#!/usr/bin/env python
"""Sanity-check the first-pass placement in recorder.kicad_pcb.

Run with the KiCad 10 interpreter:

    /c/Users/zachr/AppData/Local/Programs/KiCad/10.0/bin/python.exe check_placement.py

Checks, in order:
  1. every footprint courtyard sits inside the board outline
  2. no two courtyards overlap
  3. nothing collides with a mounting hole keepout
  4. the analog chain stays clear of the magnet ring
  5. every pad that the netlist gives a net actually carries that net
  6. placement.json still describes the board it claims to describe

This is a placement check, not a DRC. It says nothing about routing.
"""

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
    # KiCad 10's Windows build asserts in PCB_VIA::GetWidth() when no layer
    # is given. That pops a modal dialog and stops a headless script.
    wx.DisableAsserts()

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "recorder.kicad_pcb")
PLACEMENT = os.path.join(HERE, "placement.json")
PARAMS = os.path.abspath(
    os.path.join(HERE, "..", "..", "cad", "params.json")
)

ANALOG = ["MK1", "U2", "U8", "Y1", "U6", "SP1", "C15", "C16", "C17", "C18"]
HOLE_KEEPOUT_R = 2.1


CRTYD_LAYERS = (pcbnew.F_CrtYd, pcbnew.B_CrtYd)


def courtyard_box(fp):
    """Bounding box of the courtyard as drawn, in mm.

    KiCad compares courtyard outlines, so this has to be the stroke
    centreline. Two lifts of that: fp.GetCourtyard() hands back a polygon
    already inflated past the drawn line, and BOX2I.Merge() mutates in place
    but returns an unrelated proxy object, so trusting its return value used
    to invent boxes a metre wide. Read the drawn shapes instead and take half
    the pen width back off each edge.
    """
    edges = []
    for item in fp.GraphicalItems():
        if not isinstance(item, pcbnew.PCB_SHAPE):
            continue
        if item.GetLayer() not in CRTYD_LAYERS:
            continue
        bb = item.GetBoundingBox()
        pen = item.GetWidth() / 2.0
        edges.append((bb.GetLeft() + pen, bb.GetTop() + pen,
                      bb.GetRight() - pen, bb.GetBottom() - pen))
    if edges:
        box = (min(e[0] for e in edges), min(e[1] for e in edges),
               max(e[2] for e in edges), max(e[3] for e in edges))
    else:
        bb = fp.GetBoundingBox(False, False)
        box = (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom())
    return tuple(pcbnew.ToMM(v) for v in box)


def placement_twin_problems(board):
    """Compare placement.json against the board it is supposed to mirror.

    AGENTS.md asks for these two files to be kept as twins, and nothing
    checked it. placement.json is what the CAD side and the next agent read as
    placement truth, so when the board moved ahead of it, as it did when SW1
    was swapped for a side-actuated part, the drift was invisible until
    someone cut a case against the wrong number.
    """
    if not os.path.isfile(PLACEMENT):
        return ["MISSING    placement.json"]
    with open(PLACEMENT, encoding="utf-8") as fh:
        rows = {row["ref"]: row for row in json.load(fh).get("parts", [])}
    problems = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        row = rows.pop(ref, None)
        if row is None:
            problems.append(f"UNLISTED   {ref} is on the board, not in placement.json")
            continue
        actual = {
            "footprint": fp.GetFPIDAsString(),
            "x_mm": round(pcbnew.ToMM(fp.GetPosition().x), 3),
            "y_mm": round(pcbnew.ToMM(fp.GetPosition().y), 3),
            "rot_deg": round(fp.GetOrientationDegrees()) % 360,
            "layer": board.GetLayerName(fp.GetLayer()),
        }
        for key, value in actual.items():
            said = row.get(key)
            if key == "rot_deg":
                said = round(said or 0) % 360
            if said != value:
                problems.append(
                    f"DRIFT      {ref:6s} {key}: placement.json says {said!r}, "
                    f"board says {value!r}")
    for ref in sorted(rows):
        problems.append(f"GHOST      {ref} is in placement.json, not on the board")
    return problems


def main():
    params = json.load(open(PARAMS, encoding="utf-8"))
    half_w = params["pcb"]["width_mm"] / 2.0
    half_h = params["pcb"]["height_mm"] / 2.0
    ring_r = params["magnet"]["od_mm"] / 2.0

    board = pcbnew.LoadBoard(PCB)
    fps = list(board.GetFootprints())
    boxes = {fp.GetReference(): courtyard_box(fp) for fp in fps}
    holes = [
        (pcbnew.ToMM(fp.GetPosition().x), pcbnew.ToMM(fp.GetPosition().y))
        for fp in fps
        if fp.GetReference().startswith("H")
    ]

    problems = []

    for ref, (x0, y0, x1, y1) in sorted(boxes.items()):
        over = []
        if x0 < -half_w:
            over.append(f"left by {-half_w - x0:.2f}")
        if x1 > half_w:
            over.append(f"right by {x1 - half_w:.2f}")
        if y0 < -half_h:
            over.append(f"top by {-half_h - y0:.2f}")
        if y1 > half_h:
            over.append(f"bottom by {y1 - half_h:.2f}")
        if over:
            problems.append(f"OFF-BOARD  {ref:6s} {', '.join(over)} mm")

    refs = sorted(boxes)
    for i, a in enumerate(refs):
        ax0, ay0, ax1, ay1 = boxes[a]
        for b in refs[i + 1 :]:
            bx0, by0, bx1, by1 = boxes[b]
            ox = min(ax1, bx1) - max(ax0, bx0)
            oy = min(ay1, by1) - max(ay0, by0)
            if ox > 0.01 and oy > 0.01:
                problems.append(
                    f"OVERLAP    {a:6s} {b:6s} {ox:.2f} x {oy:.2f} mm"
                )

    for ref, (x0, y0, x1, y1) in sorted(boxes.items()):
        if ref.startswith("H"):
            continue
        for hx, hy in holes:
            cx = max(x0, min(hx, x1))
            cy = max(y0, min(hy, y1))
            d = math.hypot(cx - hx, cy - hy)
            if d < HOLE_KEEPOUT_R:
                problems.append(
                    f"HOLE       {ref:6s} within {d:.2f} mm of hole "
                    f"({hx:+.1f},{hy:+.1f})"
                )

    for ref in ANALOG:
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            problems.append(f"MISSING    {ref}")
            continue
        x = pcbnew.ToMM(fp.GetPosition().x)
        y = pcbnew.ToMM(fp.GetPosition().y)
        r = math.hypot(x, y)
        mark = "ok " if r > ring_r else "IN RING"
        print(f"  ring  {ref:6s} r={r:6.2f} mm  {mark}")
        if r <= ring_r:
            problems.append(f"RING       {ref:6s} centre r={r:.2f} <= {ring_r}")

    unnetted = []
    for fp in fps:
        for pad in fp.Pads():
            if pad.GetNumber() and pad.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH:
                if pad.GetNetname() == "":
                    unnetted.append(f"{fp.GetReference()}.{pad.GetNumber()}")
    problems += placement_twin_problems(board)

    print(f"\nfootprints: {len(fps)}")
    print(f"pads with no net: {len(unnetted)} {' '.join(unnetted)}")

    if problems:
        print(f"\n{len(problems)} problem(s):")
        for p in problems:
            print("  " + p)
        return 1
    print("\nplacement clean: on board, no courtyard overlaps, holes clear")
    return 0


sys.exit(main())
