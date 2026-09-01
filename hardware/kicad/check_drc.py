#!/usr/bin/env python3
"""Layout outline/hole check on the recorder PCB when it exists."""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
PARAMS = json.loads((REPO / "hardware" / "cad" / "params.json").read_text(encoding="utf-8"))
PCB_PATH = HERE / "recorder" / "recorder.kicad_pcb"

OUTLINE_TOL_MM = 0.5
HOLE_TOL_MM = 2.0
CENTER_TOL_MM = 1.0

_AT = re.compile(r"\(at\s+([-\d.]+)\s+([-\d.]+)")
_START = re.compile(r"\(start\s+([-\d.]+)\s+([-\d.]+)\)")
_END = re.compile(r"\(end\s+([-\d.]+)\s+([-\d.]+)\)")
_XY = re.compile(r"\(xy\s+([-\d.]+)\s+([-\d.]+)\)")
_EDGE_LAYER = re.compile(r'\(layer\s+"Edge\.Cuts"\)')


def expected_holes() -> list[tuple[float, float]]:
    pcb = PARAMS["pcb"]
    inset = float(PARAMS["mounting"]["hole_inset_mm"])
    hx = pcb["width_mm"] / 2 - inset
    hy = pcb["height_mm"] / 2 - inset
    return [(hx, hy), (-hx, hy), (hx, -hy), (-hx, -hy)]


def edge_bounds(text: str) -> tuple[float, float, float, float] | None:
    xs: list[float] = []
    ys: list[float] = []
    for m in _EDGE_LAYER.finditer(text):
        window = text[max(0, m.start() - 800) : m.end() + 80]
        if not any(tag in window for tag in ("gr_rect", "gr_line", "gr_poly", "gr_circle", "fp_rect", "fp_line")):
            continue
        for rx in (_START, _END, _XY):
            for x, y in rx.findall(window):
                xs.append(float(x))
                ys.append(float(y))
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def nearby(have: list[tuple[float, float]], want: tuple[float, float], tol: float) -> bool:
    return any(math.hypot(x - want[0], y - want[1]) <= tol for x, y in have)


def board_positions(text: str) -> list[tuple[float, float]]:
    spots: list[tuple[float, float]] = []
    for x_s, y_s in _AT.findall(text):
        x, y = float(x_s), float(y_s)
        if abs(x) > 5 or abs(y) > 5:
            spots.append((x, y))
    return spots


def main() -> int:
    if not PCB_PATH.is_file():
        print(
            "check_drc: SKIP - hardware/kicad/recorder/recorder.kicad_pcb "
            "is not on disk yet (outline/hole check waits for the PCB)."
        )
        return 0

    errors: list[str] = []
    pcb = PARAMS["pcb"]
    text = PCB_PATH.read_text(encoding="utf-8")
    bounds = edge_bounds(text)
    if bounds is None:
        errors.append("recorder.kicad_pcb has no Edge.Cuts geometry")
    else:
        x0, y0, x1, y1 = bounds
        width = abs(x1 - x0)
        height = abs(y1 - y0)
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2
        if abs(width - pcb["width_mm"]) > OUTLINE_TOL_MM:
            errors.append(f"Edge.Cuts width {width:.2f} mm != pcb.width_mm {pcb['width_mm']}")
        if abs(height - pcb["height_mm"]) > OUTLINE_TOL_MM:
            errors.append(f"Edge.Cuts height {height:.2f} mm != pcb.height_mm {pcb['height_mm']}")
        if abs(cx) > CENTER_TOL_MM or abs(cy) > CENTER_TOL_MM:
            errors.append(f"Edge.Cuts is not origin-centered (center {cx:.2f}, {cy:.2f})")

    spots = board_positions(text)
    missing: list[str] = []
    for hx, hy in expected_holes():
        if not nearby(spots, (hx, hy), HOLE_TOL_MM):
            missing.append(f"({hx:g}, {hy:g})")
    if missing:
        errors.append("missing mounting holes near " + ", ".join(missing))

    if errors:
        print("check_drc: FAIL")
        for e in errors:
            print(" ", e)
        return 1
    holes = expected_holes()
    print(
        f"check_drc: ok (Edge.Cuts ~{pcb['width_mm']}x{pcb['height_mm']} mm, "
        f"4 holes near ±{holes[0][0]:g}, ±{holes[0][1]:g})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
