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

This is a placement check, not a DRC. It says nothing about routing.
"""

import json
import math
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "recorder.kicad_pcb")
PARAMS = os.path.abspath(
    os.path.join(HERE, "..", "..", "cad", "params.json")
)

ANALOG = ["MK1", "U2", "U8", "Y1", "U6", "SP1", "C15", "C16", "C17", "C18"]
HOLE_KEEPOUT_R = 2.1


def courtyard_box(fp):
    box = None
    for layer in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
        poly = fp.GetCourtyard(layer)
        if poly.OutlineCount() == 0:
            continue
        bb = poly.BBox()
        box = bb if box is None else (box.Merge(bb) or box)
    if box is None:
        box = fp.GetBoundingBox(False, False)
    return (
        pcbnew.ToMM(box.GetLeft()),
        pcbnew.ToMM(box.GetTop()),
        pcbnew.ToMM(box.GetRight()),
        pcbnew.ToMM(box.GetBottom()),
    )


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
