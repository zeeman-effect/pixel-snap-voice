#!/usr/bin/env python3
"""Fail the mechanical envelope if the accessory cannot sit on a Pixel 10."""

from __future__ import annotations

import copy
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARAMS_JSON = ROOT / "params.json"
PARAMS_SCAD = ROOT / "params.scad"
PLACEMENT = ROOT.parent / "kicad" / "recorder" / "placement.json"

# KELIKING general tolerance on the 13 mm can. FDM will close a sub-millimetre
# air gap, so the lid fence has to miss the worst-case body by this much more.
SPEAKER_BODY_TOL_MM = 0.5
FENCE_AIR_MM = 1.5
MCU_AIR_MM = 1.0


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

    def expanded(self, margin: float) -> "Rect":
        return Rect(self.x0 - margin, self.y0 - margin, self.x1 + margin, self.y1 + margin)

    def closest_r(self) -> float:
        """Distance from the origin to the nearest point of this rect."""
        qx = min(max(0.0, self.x0), self.x1)
        qy = min(max(0.0, self.y0), self.y1)
        return math.hypot(qx, qy)


def load_json() -> dict:
    return json.loads(PARAMS_JSON.read_text(encoding="utf-8"))


def load_placement() -> dict | None:
    if not PLACEMENT.is_file():
        return None
    return json.loads(PLACEMENT.read_text(encoding="utf-8"))


def parse_scad() -> dict[str, float]:
    text = PARAMS_SCAD.read_text(encoding="utf-8")
    out: dict[str, float] = {}
    for m in re.finditer(
        r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(-?[0-9]+(?:\.[0-9]+)?)\s*;",
        text,
        re.M,
    ):
        out[m.group(1)] = float(m.group(2))
    return out


def scad_matches(p: dict, scad: dict[str, float], errors: list[str]) -> None:
    expect = {
        "phone_w": p["phone"]["width_mm"],
        "phone_h": p["phone"]["height_mm"],
        "acc_w": p["accessory"]["width_mm"],
        "acc_h": p["accessory"]["height_mm"],
        "acc_t": p["accessory"]["thickness_mm"],
        "wall": p["accessory"]["wall_mm"],
        "magnet_od": p["magnet"]["od_mm"],
        "magnet_id": p["magnet"]["id_mm"],
        "magnet_t": p["magnet"]["thickness_mm"],
        "pcb_t": p["pcb"]["thickness_mm"],
        "pcb_w": p["pcb"]["width_mm"],
        "pcb_h": p["pcb"]["height_mm"],
        "magnet_cy_from_top": p["phone"]["magnet_center_from_top_mm"],
        "camera_bar_from_top": p["phone"]["camera_bar_from_top_mm"],
        "speaker_h": p["connectors"]["speaker_height_mm"],
        "speaker_x": p["connectors"]["speaker_x_mm"],
        "speaker_y": p["connectors"]["speaker_y_mm"],
        "speaker_od": p["connectors"]["speaker_od_mm"],
        "jst_x": p["connectors"]["jst_x_mm"],
        "jst_y": p["connectors"]["jst_y_mm"],
        "jst_h": p["connectors"]["jst_height_mm"],
        "batt_w": p["battery"]["pocket_width_mm"],
        "batt_h": p["battery"]["pocket_height_mm"],
        "batt_t": p["battery"]["max_thickness_mm"],
        "batt_off_x": p["battery"]["offset_x_mm"],
        "batt_off_y": p["battery"]["offset_y_mm"],
        "batt_xy_clear": p["battery"]["xy_clear_mm"],
    }
    for k, v in expect.items():
        if k not in scad:
            errors.append(f"params.scad missing {k}")
            continue
        if abs(scad[k] - v) > 1e-6:
            errors.append(f"params.scad {k}={scad[k]} != params.json {v}")


def jst_rect(con: dict) -> Rect:
    """S2B-PH-K housing at 0°, origin on pad 1. KiCad fab, not courtyard."""
    x = con["jst_x_mm"]
    y = con["jst_y_mm"]
    return Rect(x - 1.95, y - 1.35, x + 3.95, y + 6.25)


def speaker_rect(con: dict) -> Rect:
    return Rect(
        con["speaker_x_mm"] - con["speaker_od_mm"] / 2,
        con["speaker_y_mm"] - con["speaker_od_mm"] / 2,
        con["speaker_x_mm"] + con["speaker_od_mm"] / 2,
        con["speaker_y_mm"] + con["speaker_od_mm"] / 2,
    )


def fence_rect(p: dict) -> Rect:
    """Outer wall of battery_fence() in case.scad, not the 40×30 pouch."""
    bat = p["battery"]
    acc = p["accessory"]
    outer_w = bat["pocket_width_mm"] + 2 * bat["xy_clear_mm"] + 2 * acc["wall_mm"]
    outer_h = bat["pocket_height_mm"] + 2 * bat["xy_clear_mm"] + 2 * acc["wall_mm"]
    return Rect(
        bat["offset_x_mm"] - outer_w / 2,
        bat["offset_y_mm"] - outer_h / 2,
        bat["offset_x_mm"] + outer_w / 2,
        bat["offset_y_mm"] + outer_h / 2,
    )


def part_xy(placement: dict, ref: str) -> tuple[float, float] | None:
    for row in placement.get("parts", []):
        if row.get("ref") == ref:
            return float(row["x_mm"]), float(row["y_mm"])
    return None


def check(p: dict, placement: dict | None = None) -> list[str]:
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
            f"speaker height stack {spk_stack:.2f} mm exceeds {limit} mm — use the ES8311 HP jack"
        )

    spk = speaker_rect(con)
    pcb_rect = Rect(
        -pcb["width_mm"] / 2,
        -pcb["height_mm"] / 2,
        pcb["width_mm"] / 2,
        pcb["height_mm"] / 2,
    )
    if not pcb_rect.contains_rect(spk):
        errors.append("speaker body extends past the PCB outline")

    fence = fence_rect(p)
    # The 4 mm can occupies z = 2.35–6.35 mm. The fence hangs from the lid at
    # z = 4.3–7.8 mm, so they overlap in height. XY has to miss, including
    # KELIKING's ±0.5 mm body and FDM wall error. Checking the 40×30 pouch
    # alone used to print ok while the wall sat 0.7 mm from the can.
    hit = spk.expanded(SPEAKER_BODY_TOL_MM + FENCE_AIR_MM)
    if hit.overlaps(fence):
        errors.append(
            "speaker body overlaps the battery fence "
            f"(can y={spk.y0:.1f}…{spk.y1:.1f}, fence y={fence.y0:.1f}…{fence.y1:.1f}; "
            "drop batt_off_y or notch the +Y wall — do not slide SP1 toward Edge.Cuts)"
        )
    if spk.expanded(SPEAKER_BODY_TOL_MM).closest_r() < mag["od_mm"] / 2:
        errors.append("speaker body intersects the magnet ring")

    jst = jst_rect(con)
    if not pcb_rect.contains_rect(jst):
        errors.append("JST-PH housing extends past the PCB outline")
    if jst.expanded(0.4).overlaps(spk.expanded(SPEAKER_BODY_TOL_MM)):
        errors.append("JST-PH housing overlaps the speaker")
    if jst.expanded(0.4).overlaps(fence):
        errors.append(
            "JST-PH housing overlaps the battery fence "
            f"(JST y={jst.y0:.1f}…{jst.y1:.1f}, fence y={fence.y0:.1f}…{fence.y1:.1f})"
        )
    # Lid cavity above the PCB is 5.45 mm. The side-entry PH is 6.0 mm, so
    # case.scad cuts a window through shell_back and the housing does not
    # have to clear the 1.2 mm skin.
    jst_stack = (
        mag["adhesive_mm"]
        + mag["thickness_mm"]
        + mag["shunt_thickness_mm"]
        + pcb["thickness_mm"]
        + con["jst_height_mm"]
    )
    if jst_stack > limit + 1e-6:
        errors.append(
            f"JST-PH height stack {jst_stack:.2f} mm exceeds {limit} mm envelope "
            "(lid window already omits shell_back)"
        )

    if pcb["width_mm"] + 2 * acc["wall_mm"] > acc["width_mm"] + 1e-6:
        errors.append("PCB does not fit inside accessory walls in X")
    if pcb["height_mm"] + 2 * acc["wall_mm"] > acc["height_mm"] + 1e-6:
        errors.append("PCB does not fit inside accessory walls in Y")

    if placement is not None:
        sp1 = part_xy(placement, "SP1")
        if sp1 is None:
            errors.append("placement.json has no SP1; lid grille has nothing to twin")
        else:
            sx, sy = sp1
            if abs(sx - con["speaker_x_mm"]) > 0.01 or abs(sy - con["speaker_y_mm"]) > 0.01:
                errors.append(
                    f"CAD speaker ({con['speaker_x_mm']}, {con['speaker_y_mm']}) "
                    f"!= placement.json SP1 ({sx}, {sy}) — lid grille would miss the can"
                )
        bt1 = part_xy(placement, "BT1")
        if bt1 is None:
            errors.append("placement.json has no BT1; lid JST window has nothing to twin")
        else:
            bx, by = bt1
            if abs(bx - con["jst_x_mm"]) > 0.01 or abs(by - con["jst_y_mm"]) > 0.01:
                errors.append(
                    f"CAD JST ({con['jst_x_mm']}, {con['jst_y_mm']}) "
                    f"!= placement.json BT1 ({bx}, {by}) — lid window would miss the housing"
                )
        u1 = part_xy(placement, "U1")
        if u1 is None:
            errors.append("placement.json has no U1; cannot tell if the battery fence hits the module")
        else:
            mx, my = u1
            mcu = p["mcu"]
            u1_rect = Rect(
                mx - mcu["width_mm"] / 2,
                my - mcu["height_mm"] / 2,
                mx + mcu["width_mm"] / 2,
                my + mcu["height_mm"] / 2,
            )
            # Module is 2.4 mm (z = 2.35–4.75). Fence starts at z = 4.3, so
            # they overlap by ~0.45 mm. 1 mm of XY air is enough for FDM.
            if u1_rect.expanded(MCU_AIR_MM).overlaps(fence):
                errors.append(
                    "battery fence overlaps U1 "
                    f"(module y={u1_rect.y0:.1f}…{u1_rect.y1:.1f}, "
                    f"fence y={fence.y0:.1f}…{fence.y1:.1f})"
                )

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
    spk = speaker_rect(con)
    fence = fence_rect(p)
    fence_gap = spk.y0 - fence.y1
    lines = [
        "Pixel Snap Voice - envelope / PETG fit report",
        f"  origin: magnet center, +Y toward camera bar",
        f"  accessory: {acc['width_mm']} x {acc['height_mm']} x {acc['thickness_mm']} mm",
        f"  magnet ring: OD {mag['od_mm']} / ID {mag['id_mm']} / {mag['thickness_mm']} mm",
        f"  camera-bar XY gap: {bar_gap:.2f} mm (must be > 0)",
        f"  USB stack (phone->shell): {usb_stack:.2f} mm",
        f"  battery stack: {batt_stack:.2f} mm",
        f"  speaker stack: {mag['adhesive_mm'] + mag['thickness_mm'] + mag['shunt_thickness_mm'] + pcb['thickness_mm'] + con['speaker_height_mm'] + acc['shell_back_mm']:.2f} mm "
        f"(SP1 {con['speaker_od_mm']:.1f} mm at {con['speaker_x_mm']:.1f}, {con['speaker_y_mm']:.1f})",
        f"  JST-PH: {con['jst_height_mm']:.1f} mm housing at ({con['jst_x_mm']:.1f}, {con['jst_y_mm']:.1f}), "
        f"stack {mag['adhesive_mm'] + mag['thickness_mm'] + mag['shunt_thickness_mm'] + pcb['thickness_mm'] + con['jst_height_mm']:.2f} mm through the lid window",
        f"  battery fence: {fence.x1 - fence.x0:.1f} x {fence.y1 - fence.y0:.1f} mm at "
        f"({bat['offset_x_mm']:.1f}, {bat['offset_y_mm']:.1f}), +Y face y={fence.y1:.1f}, "
        f"{fence_gap:.1f} mm of air to SP1 body",
        f"  battery pocket: {bat['pocket_width_mm']} x {bat['pocket_height_mm']} x {bat['max_thickness_mm']} mm "
        f"= {vol:.0f} mm3 -> ~{est} mAh (current pick {bat['locked_mah']} mAh)",
        "  PETG checklist (physical, after print):",
        "    [ ] camera bar not covered when snapped",
        "    [ ] USB-C plug + overmold miss the phone body",
        "    [ ] mic port on the long edge, not against glass",
        "    [ ] side button reachable while snapped",
        "    [ ] ring + shunt in the phone-side pockets; snap hold feels OK",
        "    [ ] lid grille sits over SP1; fence wall does not hit the can",
    ]
    return "\n".join(lines)


def self_test() -> list[str]:
    """Synthetic cases so a stay-green check cannot hide a fence collision."""
    p = load_json()
    placement = load_placement()
    failures: list[str] = []

    live = check(p, placement)
    if live:
        failures.append(f"live params should pass, got {live}")

    old = copy.deepcopy(p)
    old["battery"]["offset_y_mm"] = 12.0
    err = check(old, placement)
    if not any("fence" in e for e in err):
        failures.append(f"offset_y=12 should hit the speaker fence, got {err}")

    ring = copy.deepcopy(p)
    ring["connectors"]["speaker_y_mm"] = 0.0
    err = check(ring, None)
    if not any("magnet" in e for e in err):
        failures.append(f"speaker at origin should hit the magnet ring, got {err}")

    if placement is not None:
        mismatch = copy.deepcopy(placement)
        for row in mismatch.get("parts", []):
            if row.get("ref") == "SP1":
                row["y_mm"] = 99.0
        err = check(p, mismatch)
        if not any("grille" in e or "SP1" in e for e in err):
            failures.append(f"SP1 XY drift should fail, got {err}")

        jst_drift = copy.deepcopy(placement)
        for row in jst_drift.get("parts", []):
            if row.get("ref") == "BT1":
                row["x_mm"] = 0.0
        err = check(p, jst_drift)
        if not any("JST" in e or "BT1" in e for e in err):
            failures.append(f"BT1 XY drift should fail, got {err}")

        south = copy.deepcopy(p)
        south["battery"]["offset_y_mm"] = -5.0
        err = check(south, placement)
        if not any("U1" in e for e in err):
            failures.append(f"offset_y=-5 should hit U1, got {err}")

    return failures


def main() -> int:
    if not PARAMS_JSON.is_file():
        print("FAIL: params.json missing", file=sys.stderr)
        return 1
    test_errors = self_test()
    if test_errors:
        print("FAIL: check_envelope self-test", file=sys.stderr)
        for e in test_errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    p = load_json()
    errors = check(p, load_placement())
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
