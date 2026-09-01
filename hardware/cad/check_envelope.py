#!/usr/bin/env python3
"""Fail the mechanical envelope if the accessory cannot sit on a Pixel 10."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARAMS_JSON = ROOT / "params.json"
PARAMS_SCAD = ROOT / "params.scad"


class Rect:
    def __init__(self, x0: float, y0: float, x1: float, y1: float):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1

    def overlaps(self, other: "Rect") -> bool:
        return not (
            self.x1 <= other.x0 or other.x1 <= self.x0 or self.y1 <= other.y0 or other.y1 <= self.y0
        )

    def contains_rect(self, other: "Rect") -> bool:
        return self.x0 <= other.x0 and self.y0 <= other.y0 and self.x1 >= other.x1 and self.y1 >= other.y1

    def contains_circle(self, cx: float, cy: float, r: float) -> bool:
        return (
            cx - r >= self.x0
            and cx + r <= self.x1
            and cy - r >= self.y0
            and cy + r <= self.y1
        )


def load_json() -> dict:
    return json.loads(PARAMS_JSON.read_text(encoding="utf-8"))


def parse_scad() -> dict[str, float]:
    text = PARAMS_SCAD.read_text(encoding="utf-8")
    out: dict[str, float] = {}
    for m in re.finditer(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*;", text, re.M):
        out[m.group(1)] = float(m.group(2))
    return out


def scad_matches(p: dict, scad: dict[str, float], errors: list[str]) -> None:
    expect = {
        "phone_w": p["phone"]["width_mm"],
        "phone_h": p["phone"]["height_mm"],
        "acc_w": p["accessory"]["width_mm"],
        "acc_h": p["accessory"]["height_mm"],
        "acc_t": p["accessory"]["thickness_mm"],
        "magnet_od": p["magnet"]["od_mm"],
        "magnet_id": p["magnet"]["id_mm"],
        "magnet_t": p["magnet"]["thickness_mm"],
        "pcb_t": p["pcb"]["thickness_mm"],
        "pcb_w": p["pcb"]["width_mm"],
        "pcb_h": p["pcb"]["height_mm"],
        "magnet_cy_from_top": p["phone"]["magnet_center_from_top_mm"],
        "camera_bar_from_top": p["phone"]["camera_bar_from_top_mm"],
    }
    for k, v in expect.items():
        if k not in scad:
            errors.append(f"params.scad missing {k}")
            continue
        if abs(scad[k] - v) > 1e-6:
            errors.append(f"params.scad {k}={scad[k]} != params.json {v}")


def check(p: dict) -> list[str]:
    errors: list[str] = []
    phone = p["phone"]
    mag = p["magnet"]
    acc = p["accessory"]
    pcb = p["pcb"]
    con = p["connectors"]
    bat = p["battery"]

    # Accessory coords: origin = magnet center, +Y toward camera bar.
    acc_rect = Rect(-acc["width_mm"] / 2, -acc["height_mm"] / 2, acc["width_mm"] / 2, acc["height_mm"] / 2)

    phone_top = phone["magnet_center_from_top_mm"]
    phone_bottom = phone["magnet_center_from_top_mm"] - phone["height_mm"]
    phone_left = -phone["magnet_center_from_left_mm"]
    phone_right = phone_left + phone["width_mm"]
    phone_rect = Rect(phone_left, phone_bottom, phone_right, phone_top)

    bar = Rect(
        phone_left,
        phone_top - phone["camera_bar_from_top_mm"],
        phone_left + phone["camera_bar_width_mm"],
        phone_top,
    )
    if acc_rect.overlaps(bar):
        errors.append("accessory outline overlaps the camera bar in XY when snapped")

    if not phone_rect.contains_rect(acc_rect):
        errors.append("accessory outline extends past the phone body")

    r = mag["od_mm"] / 2
    if not acc_rect.contains_circle(0.0, 0.0, r):
        errors.append("magnet ring sits outside the accessory outline")

    if con["usb_edge"] != "bottom":
        errors.append("USB must be on the accessory short (bottom) edge")
    over = Rect(
        con["usb_offset_x_mm"] - con["usb_overmold_width_mm"] / 2,
        acc_rect.y0 - con["usb_overmold_len_mm"],
        con["usb_offset_x_mm"] + con["usb_overmold_width_mm"] / 2,
        acc_rect.y0,
    )
    if over.y0 < phone_rect.y0 or over.x0 < phone_rect.x0 or over.x1 > phone_rect.x1:
        errors.append("USB overmold keepout intersects the phone body / falls off the back")

    # MK1 stays on F.Cu. case.scad mic_duct() takes the B.Cu NPTH out the
    # right wall. Do not flip this flag to silence a muffled-mic fail.
    if con["mic_faces_glass"]:
        errors.append("mic port faces the glass — recordings will be muffled")
    if con["mic_edge"] not in ("left", "right"):
        errors.append("mic acoustic port must be on a free long edge")

    usb_stack = (
        mag["adhesive_mm"]
        + mag["thickness_mm"]
        + mag["shunt_thickness_mm"]
        + pcb["thickness_mm"]
        + con["usb_height_mm"]
        + acc["shell_back_mm"]
    )
    batt_stack = (
        mag["adhesive_mm"]
        + mag["thickness_mm"]
        + mag["shunt_thickness_mm"]
        + pcb["thickness_mm"]
        + bat["max_thickness_mm"]
        + acc["shell_back_mm"]
    )
    spk_stack = (
        mag["adhesive_mm"]
        + mag["thickness_mm"]
        + mag["shunt_thickness_mm"]
        + pcb["thickness_mm"]
        + con["speaker_height_mm"]
        + acc["shell_back_mm"]
    )
    limit = acc["thickness_mm"]
    if usb_stack > limit + 1e-6:
        errors.append(f"USB height stack {usb_stack:.2f} mm exceeds {limit} mm envelope")
    if batt_stack > limit + 1e-6:
        errors.append(f"battery height stack {batt_stack:.2f} mm exceeds {limit} mm envelope")
    if spk_stack > limit + 1e-6:
        errors.append(
            f"speaker height stack {spk_stack:.2f} mm exceeds {limit} mm — drop the 1511 and use the ES8311 HP jack"
        )

    if pcb["width_mm"] + 2 * acc["wall_mm"] > acc["width_mm"] + 1e-6:
        errors.append("PCB does not fit inside accessory walls in X")
    if pcb["height_mm"] + 2 * acc["wall_mm"] > acc["height_mm"] + 1e-6:
        errors.append("PCB does not fit inside accessory walls in Y")

    return errors


def leftover_mah(p: dict) -> tuple[float, int]:
    bat = p["battery"]
    vol_mm3 = bat["pocket_width_mm"] * bat["pocket_height_mm"] * bat["max_thickness_mm"]
    # ~100 mAh per cm³ is a conservative thin-pouch figure.
    est = vol_mm3 / 1000.0 * 100.0
    return vol_mm3, int(round(est))


def fit_report(p: dict) -> str:
    mag = p["magnet"]
    pcb = p["pcb"]
    acc = p["accessory"]
    bat = p["battery"]
    con = p["connectors"]
    vol, est = leftover_mah(p)
    usb_stack = (
        mag["adhesive_mm"]
        + mag["thickness_mm"]
        + mag["shunt_thickness_mm"]
        + pcb["thickness_mm"]
        + con["usb_height_mm"]
        + acc["shell_back_mm"]
    )
    batt_stack = (
        mag["adhesive_mm"]
        + mag["thickness_mm"]
        + mag["shunt_thickness_mm"]
        + pcb["thickness_mm"]
        + bat["max_thickness_mm"]
        + acc["shell_back_mm"]
    )
    bar_gap = (
        p["phone"]["magnet_center_from_top_mm"]
        - acc["height_mm"] / 2
        - p["phone"]["camera_bar_from_top_mm"]
    )
    lines = [
        "Pixel Snap Voice - envelope / PETG fit report",
        f"  origin: magnet center, +Y toward camera bar",
        f"  accessory: {acc['width_mm']} x {acc['height_mm']} x {acc['thickness_mm']} mm",
        f"  magnet ring: OD {mag['od_mm']} / ID {mag['id_mm']} / {mag['thickness_mm']} mm",
        f"  camera-bar XY gap: {bar_gap:.2f} mm (must be > 0)",
        f"  USB stack (phone->shell): {usb_stack:.2f} mm",
        f"  battery stack: {batt_stack:.2f} mm",
        f"  battery pocket: {bat['pocket_width_mm']} x {bat['pocket_height_mm']} x {bat['max_thickness_mm']} mm "
        f"= {vol:.0f} mm3 -> ~{est} mAh (current pick {bat['locked_mah']} mAh)",
        "  PETG checklist (physical, after print):",
        "    [ ] camera bar not covered when snapped",
        "    [ ] USB-C plug + overmold miss the phone body",
        "    [ ] mic port on the long edge, not against glass",
        "    [ ] side button reachable while snapped",
        "    [ ] ring + shunt in the phone-side pockets; snap hold feels OK",
    ]
    return "\n".join(lines)


def main() -> int:
    if not PARAMS_JSON.is_file():
        print("FAIL: params.json missing", file=sys.stderr)
        return 1
    p = load_json()
    errors = check(p)
    if PARAMS_SCAD.is_file():
        scad_matches(p, parse_scad(), errors)
    print(fit_report(p))
    if errors:
        print("FAIL:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("check_envelope: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
