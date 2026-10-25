#!/usr/bin/env python3
"""Fail the mechanical envelope if the accessory cannot sit on a Pixel 10."""

from __future__ import annotations

import copy
import json
import math
import re
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARAMS_JSON = ROOT / "params.json"
PARAMS_SCAD = ROOT / "params.scad"
CASE_SCAD = ROOT / "case.scad"
PLACEMENT = ROOT.parent / "kicad" / "recorder" / "placement.json"

MCU_AIR_MM = 1.0
# Air over the MCU can inside the lid (the pouch is no longer in that cavity).
MCU_LID_AIR_MM = 0.2
# A LiPo pouch swells with age. The hanging-cell stack already includes swell_mm;
# this is leftover lid budget if the cell grows past the locked thickness.
POUCH_AIR_MM = 0.3
# Thinnest PETG the lid well may leave beside the pogo body.
MIN_SKIN_MM = 0.6
# Leftover lid over J2 after the dish. Under this the rim prints as foil.
MIN_DISH_LID_MM = 1.2
# Pad may sit this far above the dish. More than that snags.
MAX_POGO_PROUD_MM = 0.3
# Clearance from MK1's NPTH to the steel shunt edge.
SHUNT_PORT_MM = 1.0
# Air between the 51.5 x 66 mm cell outline and a 5 mm tray post.
MIN_POST_CLEAR_MM = 2.0
# Air under the wrapped cell so the pouch is not a spacer.
MIN_CELL_AIR_MM = 0.10
MAX_CELL_AIR_MM = 0.40
# Leftover metal on the phone face under a blind M1.6 tap.
MIN_TAP_FLOOR_MM = 0.8
# Leftover PETG under a lid countersink.
MIN_LID_CSK_REMAIN_MM = 0.8
# Leftover PETG over the IPEX well. Wave art is clipped off this circle.
MIN_IPEX_SKIN_MM = 0.35
# Footprint geometry the case aims at. EVQP7C: actuator tip at local (0, 2.1).
# IM73A135: sound-port NPTH at local (0.68, 0).
SW1_TIP_LOCAL = (0.0, 2.1)
MK1_PORT_LOCAL = (0.68, 0.0)
# Past this the SW1 nub is a lever on the pill, not a nub.
MAX_NUB_GAP_MM = 1.5
# BT1 solder pads, not the iron-access zone.
BT1_PAD_HX = 2.2
BT1_PAD_HY = 1.75

# params.scad name -> (params.json section, key). Every number in params.scad
# has to be listed, so a stale copy of a dropped part cannot linger there.
SCAD_KEYS = {
    "phone_w": ("phone", "width_mm"),
    "phone_h": ("phone", "height_mm"),
    "phone_t": ("phone", "thickness_mm"),
    "camera_bar_from_top": ("phone", "camera_bar_from_top_mm"),
    "camera_bar_h": ("phone", "camera_bar_height_mm"),
    "camera_bar_w": ("phone", "camera_bar_width_mm"),
    "camera_bar_extra_t": ("phone", "camera_bar_extra_thickness_mm"),
    "magnet_cy_from_top": ("phone", "magnet_center_from_top_mm"),
    "magnet_cx_from_left": ("phone", "magnet_center_from_left_mm"),
    "magnet_od": ("magnet", "od_mm"),
    "magnet_id": ("magnet", "id_mm"),
    "magnet_t": ("magnet", "thickness_mm"),
    "magnet_skin": ("magnet", "skin_mm"),
    "shunt_t": ("magnet", "shunt_thickness_mm"),
    "shunt_od": ("magnet", "shunt_od_mm"),
    "adhesive_t": ("magnet", "adhesive_mm"),
    "clock_w": ("magnet", "clock_length_mm"),
    "clock_h": ("magnet", "clock_width_mm"),
    "clock_gap": ("magnet", "clock_gap_mm"),
    "acc_w": ("accessory", "width_mm"),
    "acc_h": ("accessory", "height_mm"),
    "acc_t": ("accessory", "thickness_mm"),
    "wall": ("accessory", "wall_mm"),
    "shell_back": ("accessory", "shell_back_mm"),
    "pcb_t": ("pcb", "thickness_mm"),
    "pcb_w": ("pcb", "width_mm"),
    "pcb_h": ("pcb", "height_mm"),
    "pogo_x": ("connectors", "pogo_x_mm"),
    "pogo_y": ("connectors", "pogo_y_mm"),
    "pogo_body_x": ("connectors", "pogo_body_x_mm"),
    "pogo_body_y": ("connectors", "pogo_body_y_mm"),
    "pogo_h": ("connectors", "pogo_height_mm"),
    "pogo_well_clear": ("connectors", "pogo_well_clear_mm"),
    "pogo_proud": ("connectors", "pogo_proud_mm"),
    "pogo_dish_rim": ("connectors", "pogo_dish_rim_mm"),
    "mic_y": ("connectors", "mic_y_mm"),
    "mic_npth_x": ("connectors", "mic_npth_x_mm"),
    "mic_npth_y": ("connectors", "mic_npth_y_mm"),
    "btn_x": ("connectors", "button_x_mm"),
    "btn_y": ("connectors", "button_y_mm"),
    "btn_tip_inset": ("connectors", "button_tip_inset_mm"),
    "btn_act_z": ("connectors", "button_actuator_z_mm"),
    "batt_pad_x": ("connectors", "batt_pad_x_mm"),
    "batt_pad_y": ("connectors", "batt_pad_y_mm"),
    "batt_pad_zone": ("connectors", "batt_pad_zone_mm"),
    "ipex_local_x": ("antenna", "ipex_local_x_mm"),
    "ipex_local_y": ("antenna", "ipex_local_y_mm"),
    "ipex_x": ("antenna", "ipex_x_mm"),
    "ipex_y": ("antenna", "ipex_y_mm"),
    "ipex_recess_d": ("antenna", "ipex_recess_d_mm"),
    "ipex_recess_depth": ("antenna", "ipex_recess_depth_mm"),
    "fpc_x": ("antenna", "fpc_x_mm"),
    "fpc_y": ("antenna", "fpc_y_mm"),
    "fpc_w": ("antenna", "fpc_w_mm"),
    "fpc_h": ("antenna", "fpc_h_mm"),
    "batt_t": ("battery", "max_thickness_mm"),
    "batt_w": ("battery", "pocket_width_mm"),
    "batt_h": ("battery", "pocket_height_mm"),
    "batt_off_x": ("battery", "offset_x_mm"),
    "batt_off_y": ("battery", "offset_y_mm"),
    "batt_xy_clear": ("battery", "xy_clear_mm"),
    "batt_tape": ("battery", "tape_mm"),
    "batt_swell": ("battery", "swell_mm"),
    "batt_air": ("battery", "air_mm"),
    "hole_d": ("mounting", "hole_d_mm"),
    "hole_inset": ("mounting", "hole_inset_mm"),
    "tap_d": ("mounting", "tap_d_mm"),
}

# Print-fit numbers this check reads straight out of case.scad instead of
# keeping a hand-typed copy.
CASE_KEYS = (
    "boss_d",
    "standoff_d",
    "floor_t",
    "skin_t",
    "pocket_extra",
    "clock_clear",
    "clock_rib",
    "nub_pretravel",
    "btn_head_y",
    "btn_head_z",
    "btn_r",
    "btn_border",
    "btn_bezel_t",
    "btn_proud",
    "btn_lip",
    "btn_hole_y",
    "btn_hole_z",
    "mic_port_w",
    "mic_port_h",
    "tap_depth",
    "tap_floor",
    "csk_d",
    "csk_h",
    "ridge_depth",
)
# Side ridges must leave this much of the 1.2 mm wall.
MIN_RIDGE_WALL_MM = 0.85


class Rect:
    def __init__(self, x0: float, y0: float, x1: float, y1: float):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1

    def overlaps(self, other: "Rect") -> bool:
        return not (
            self.x1 <= other.x0 or other.x1 <= self.x0 or self.y1 <= other.y0 or other.y1 <= self.y0
        )

    def contains_rect(self, other: "Rect") -> bool:
        return self.x0 <= other.x0 and self.y0 <= other.y0 and self.x1 >= other.x1 and self.y1 >= other.y1

    def contains_point(self, x: float, y: float) -> bool:
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1

    def contains_circle(self, cx: float, cy: float, r: float) -> bool:
        return (
            cx - r >= self.x0
            and cx + r <= self.x1
            and cy - r >= self.y0
            and cy + r <= self.y1
        )

    def expanded(self, margin: float) -> "Rect":
        return Rect(self.x0 - margin, self.y0 - margin, self.x1 + margin, self.y1 + margin)

    def gap(self, other: "Rect") -> float:
        """Air between two rects, 0 if they touch or overlap."""
        dx = max(0.0, other.x0 - self.x1, self.x0 - other.x1)
        dy = max(0.0, other.y0 - self.y1, self.y0 - other.y1)
        return math.hypot(dx, dy)

    def closest_r(self) -> float:
        """Distance from the origin to the nearest point of this rect."""
        qx = min(max(0.0, self.x0), self.x1)
        qy = min(max(0.0, self.y0), self.y1)
        return math.hypot(qx, qy)


def centred(cx: float, cy: float, hx: float, hy: float) -> Rect:
    return Rect(cx - hx, cy - hy, cx + hx, cy + hy)


def load_json() -> dict:
    return json.loads(PARAMS_JSON.read_text(encoding="utf-8"))


def load_placement() -> dict | None:
    if not PLACEMENT.is_file():
        return None
    return json.loads(PLACEMENT.read_text(encoding="utf-8"))


def parse_scad(path: Path = PARAMS_SCAD) -> dict[str, float]:
    text = path.read_text(encoding="utf-8")
    out: dict[str, float] = {}
    for m in re.finditer(
        r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(-?[0-9]+(?:\.[0-9]+)?)\s*;",
        text,
        re.M,
    ):
        out[m.group(1)] = float(m.group(2))
    return out


@lru_cache(maxsize=1)
def case_fit() -> dict[str, float]:
    found = parse_scad(CASE_SCAD)
    missing = [k for k in CASE_KEYS if k not in found]
    if missing:
        raise KeyError(f"case.scad no longer sets {', '.join(missing)} as plain numbers")
    return {k: found[k] for k in CASE_KEYS}


def scad_matches(p: dict, scad: dict[str, float], errors: list[str]) -> None:
    for name, (section, key) in SCAD_KEYS.items():
        if name not in scad:
            errors.append(f"params.scad missing {name}")
            continue
        want = p[section][key]
        if abs(scad[name] - want) > 1e-6:
            errors.append(f"params.scad {name}={scad[name]} != params.json {section}.{key} {want}")
    for name in sorted(set(scad) - set(SCAD_KEYS)):
        errors.append(f"params.scad sets {name}, which params.json does not carry")


def part_row(placement: dict, ref: str) -> dict | None:
    for row in placement.get("parts", []):
        if row.get("ref") == ref:
            return row
    return None


def part_xy(placement: dict, ref: str) -> tuple[float, float] | None:
    row = part_row(placement, ref)
    if row is None:
        return None
    return float(row["x_mm"]), float(row["y_mm"])


def to_board(row: dict, local: tuple[float, float]) -> tuple[float, float]:
    """Footprint-local offset to board XY. KiCad turns clockwise in this +Y-up frame."""
    t = math.radians(float(row.get("rot_deg", 0)))
    lx, ly = local
    return (
        float(row["x_mm"]) + lx * math.cos(t) + ly * math.sin(t),
        float(row["y_mm"]) - lx * math.sin(t) + ly * math.cos(t),
    )


def outline_matches(p: dict, placement: dict) -> bool:
    """True once placement.json describes the board outline params.json locks."""
    board = placement.get("board", {})
    try:
        w = float(board["width_mm"])
        h = float(board["height_mm"])
    except (KeyError, TypeError, ValueError):
        return False
    return abs(w - p["pcb"]["width_mm"]) < 0.01 and abs(h - p["pcb"]["height_mm"]) < 0.01


def pcb_rect(p: dict) -> Rect:
    return centred(0.0, 0.0, p["pcb"]["width_mm"] / 2, p["pcb"]["height_mm"] / 2)


def inner_rect(p: dict) -> Rect:
    acc = p["accessory"]
    return centred(0.0, 0.0, acc["width_mm"] / 2 - acc["wall_mm"], acc["height_mm"] / 2 - acc["wall_mm"])


def pogo_rect(con: dict) -> Rect:
    return centred(
        con["pogo_x_mm"],
        con["pogo_y_mm"],
        con["pogo_body_x_mm"] / 2,
        con["pogo_body_y_mm"] / 2,
    )


def pogo_well_rect(con: dict) -> Rect:
    extra = con["pogo_well_clear_mm"]
    return centred(
        con["pogo_x_mm"],
        con["pogo_y_mm"],
        con["pogo_body_x_mm"] / 2 + extra,
        con["pogo_body_y_mm"] / 2 + extra,
    )


def pogo_dish_rect(con: dict) -> Rect:
    extra = con["pogo_well_clear_mm"] + con["pogo_dish_rim_mm"]
    return centred(
        con["pogo_x_mm"],
        con["pogo_y_mm"],
        con["pogo_body_x_mm"] / 2 + extra,
        con["pogo_body_y_mm"] / 2 + extra,
    )


def pouch_rect(p: dict) -> Rect:
    bat = p["battery"]
    return centred(
        bat["offset_x_mm"],
        bat["offset_y_mm"],
        bat["pocket_width_mm"] / 2,
        bat["pocket_height_mm"] / 2,
    )


def pad_zone(con: dict) -> Rect:
    half = con["batt_pad_zone_mm"] / 2
    return centred(con["batt_pad_x_mm"], con["batt_pad_y_mm"], half, half)


def pad_body(con: dict) -> Rect:
    return centred(con["batt_pad_x_mm"], con["batt_pad_y_mm"], BT1_PAD_HX, BT1_PAD_HY)


def post_centres(p: dict) -> list[tuple[float, float, float]]:
    """Tray M1.6 posts: hole centres and standoff radius."""
    pcb = p["pcb"]
    inset = p["mounting"]["hole_inset_mm"]
    r = case_fit()["standoff_d"] / 2
    hx = pcb["width_mm"] / 2 - inset
    hy = pcb["height_mm"] / 2 - inset
    return [(sx * hx, sy * hy, r) for sx in (-1, 1) for sy in (-1, 1)]


def circle_rect_clearance(cx: float, cy: float, r: float, rect: Rect) -> float:
    """Air from a circle to a rect. Negative if they overlap."""
    qx = min(max(cx, rect.x0), rect.x1)
    qy = min(max(cy, rect.y0), rect.y1)
    return math.hypot(cx - qx, cy - qy) - r


def boss_rects(p: dict) -> list[Rect]:
    """Lid standoffs (boss_solids() in case.scad) around the four screw holes."""
    pcb = p["pcb"]
    inset = p["mounting"]["hole_inset_mm"]
    half = case_fit()["boss_d"] / 2
    hx = pcb["width_mm"] / 2 - inset
    hy = pcb["height_mm"] / 2 - inset
    return [centred(sx * hx, sy * hy, half, half) for sx in (-1, 1) for sy in (-1, 1)]


def circle_hits_rect(x: float, y: float, r: float, rect: Rect) -> bool:
    qx = min(max(x, rect.x0), rect.x1)
    qy = min(max(y, rect.y0), rect.y1)
    return math.hypot(x - qx, y - qy) < r


def mic_port(con: dict) -> Rect:
    """NPTH plus a short local seal, not a long under-board duct."""
    return centred(con["mic_npth_x_mm"], con["mic_npth_y_mm"], 1.5, 1.5)


def antenna_fpc_rect(p: dict) -> Rect:
    ant = p["antenna"]
    return centred(ant["fpc_x_mm"], ant["fpc_y_mm"], ant["fpc_w_mm"] / 2, ant["fpc_h_mm"] / 2)


def ipex_world_from_u1(placement: dict, p: dict) -> tuple[float, float] | None:
    row = part_row(placement, "U1")
    if row is None:
        return None
    ant = p["antenna"]
    return to_board(row, (ant["ipex_local_x_mm"], ant["ipex_local_y_mm"]))


def u1_rect(p: dict, placement: dict) -> Rect | None:
    xy = part_xy(placement, "U1")
    if xy is None:
        return None
    mcu = p["mcu"]
    return centred(xy[0], xy[1], mcu["width_mm"] / 2, mcu["height_mm"] / 2)


def stacks(p: dict) -> dict[str, float]:
    """Heights from the phone glass. `tray` is the board top, where the lid starts."""
    mag = p["magnet"]
    acc = p["accessory"]
    con = p["connectors"]
    bat = p["battery"]
    floor = mag["skin_mm"] + mag["thickness_mm"] + mag["shunt_thickness_mm"]
    shunt_top = floor
    air = bat.get("air_mm", 0.15)
    pouch_z0 = shunt_top + air
    pouch_top = (
        pouch_z0
        + bat.get("tape_mm", 0.0)
        + bat["max_thickness_mm"]
        + bat.get("swell_mm", 0.0)
    )
    tray = pouch_top + p["pcb"]["thickness_mm"]
    back = acc["shell_back_mm"]
    proud = con["pogo_proud_mm"]
    pogo = tray + con["pogo_height_mm"]
    return {
        "skin": mag["skin_mm"],
        "floor": floor,
        "shunt_top": shunt_top,
        "air": air,
        "pouch_z0": pouch_z0,
        "tray": tray,
        "cavity": acc["thickness_mm"] - back - tray,
        "pogo": pogo,
        "pogo_outer": pogo - proud,
        "pogo_proud": proud,
        "dish_t": con["pogo_height_mm"] - proud,
        "pouch": pouch_top,
    }


def button_tip_x(p: dict) -> float:
    half = p["pcb"]["width_mm"] / 2
    inset = p["connectors"]["button_tip_inset_mm"]
    if p["connectors"].get("button_edge") == "right":
        return half - inset
    return -half + inset


def clock_well(p: dict, fit: dict[str, float]) -> Rect:
    """Blind pocket for the alignment magnet, 6 o'clock, long side along -Y."""
    mag = p["magnet"]
    ring_r = (mag["od_mm"] + fit["pocket_extra"]) / 2.0
    well_w = mag["clock_width_mm"] + 2.0 * fit["clock_clear"]
    well_h = mag["clock_length_mm"] + 2.0 * fit["clock_clear"]
    cy = -(ring_r + fit["clock_rib"] + well_h / 2.0)
    return centred(0.0, cy, well_w / 2.0, well_h / 2.0)


def button_gap(p: dict) -> float:
    """Inner wall face to the SW1 actuator tip: what the pill nub spans."""
    acc = p["accessory"]
    inner = acc["width_mm"] / 2 - acc["wall_mm"]
    tip = button_tip_x(p)
    if tip >= 0:
        return inner - tip
    return tip - (-inner)


def board_checks(p: dict, placement: dict) -> list[str]:
    """Part checks that only mean something once placement.json is on this outline."""
    out: list[str] = []
    con = p["connectors"]

    mk1 = part_row(placement, "MK1")
    if mk1 is None:
        out.append("placement.json has no MK1; the tray mic seal has nothing to aim at")
    else:
        px, py = to_board(mk1, MK1_PORT_LOCAL)
        if abs(px - con["mic_npth_x_mm"]) > 0.05 or abs(py - con["mic_npth_y_mm"]) > 0.05:
            out.append(
                f"MK1 port NPTH ({px:.2f}, {py:.2f}) from placement.json != CAD mic_npth "
                f"({con['mic_npth_x_mm']}, {con['mic_npth_y_mm']}): the tray seal would miss the hole"
            )

    sw1 = part_row(placement, "SW1")
    if sw1 is None:
        out.append("placement.json has no SW1; the TPU pill nub has nothing to press")
    else:
        tx, ty = to_board(sw1, SW1_TIP_LOCAL)
        want = button_tip_x(p)
        if abs(tx - want) > 0.1 or abs(ty - con["button_y_mm"]) > 0.2:
            out.append(
                f"SW1 actuator tip ({tx:.2f}, {ty:.2f}) from placement.json != CAD "
                f"({want:.2f}, {con['button_y_mm']}): the pill nub is sized for the CAD tip"
            )

    return out


def pending(p: dict, placement: dict | None) -> list[str]:
    """board_checks() findings held back while placement.json is still the old outline."""
    if placement is None or outline_matches(p, placement):
        return []
    return board_checks(p, placement)


def check(p: dict, placement: dict | None = None) -> list[str]:
    errors: list[str] = []
    phone = p["phone"]
    mag = p["magnet"]
    acc = p["accessory"]
    pcb = p["pcb"]
    con = p["connectors"]
    bat = p["battery"]
    fit = case_fit()

    # Accessory coords: origin = magnet center, +Y toward camera bar.
    acc_rect = centred(0.0, 0.0, acc["width_mm"] / 2, acc["height_mm"] / 2)
    board = pcb_rect(p)
    inner = inner_rect(p)

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

    if not acc_rect.contains_circle(0.0, 0.0, mag["od_mm"] / 2):
        errors.append("magnet ring sits outside the accessory outline")
    if mag["shunt_od_mm"] + 2 * acc["wall_mm"] > acc["width_mm"] + 1e-6:
        errors.append("shunt pocket leaves less than one wall to the long sides")

    # MK1 stays on F.Cu. case.scad takes the B.Cu NPTH out a short tray-wall
    # pill. Do not flip this flag to silence a muffled-mic fail.
    if con["mic_faces_glass"]:
        errors.append("mic port faces the glass — recordings will be muffled")
    mic_side = "right" if con["mic_npth_x_mm"] >= 0 else "left"
    if con["mic_edge"] != mic_side:
        errors.append(
            f"case.scad puts the mic on the {mic_side} long wall from mic_npth_x; "
            f"mic_edge is {con['mic_edge']!r}"
        )
    port = mic_port(con)
    if not board.contains_rect(port):
        errors.append(
            f"mic NPTH ({con['mic_npth_x_mm']}, {con['mic_npth_y_mm']}) is not under the "
            f"{pcb['width_mm']} x {pcb['height_mm']} board: the seal would aim at a hole off the PCB"
        )
    shunt_clear = port.closest_r() - mag["shunt_od_mm"] / 2
    if shunt_clear < SHUNT_PORT_MM:
        errors.append(
            f"mic NPTH ({con['mic_npth_x_mm']}, {con['mic_npth_y_mm']}) sits over the steel shunt "
            f"({shunt_clear:.2f} mm off the shunt edge, needs {SHUNT_PORT_MM}): the shunt "
            "blocks the port; move MK1 to a larger |y|"
        )
    if abs(con["mic_y_mm"] - con["mic_npth_y_mm"]) > 1.5:
        errors.append(
            f"mic wall port at y={con['mic_y_mm']} misses the NPTH at "
            f"y={con['mic_npth_y_mm']}"
        )

    st = stacks(p)
    limit = acc["thickness_mm"]
    lid_need = p["mcu"]["thickness_mm"] + MCU_LID_AIR_MM + acc["shell_back_mm"]
    if st["pogo"] > limit + 1e-6:
        errors.append(f"pogo height stack {st['pogo']:.2f} mm exceeds {limit} mm envelope")
    if st["pogo_proud"] < -1e-6:
        errors.append(
            f"pogo proud {st['pogo_proud']:.2f} mm is recessed in the dish; "
            "raise the local lid or lower the pad"
        )
    if st["pogo_proud"] > MAX_POGO_PROUD_MM + 1e-6:
        errors.append(
            f"pogo proud {st['pogo_proud']:.2f} mm is more than {MAX_POGO_PROUD_MM:.2f} mm; "
            "the cable overmold will snag"
        )
    if st["dish_t"] + 1e-6 < MIN_DISH_LID_MM:
        errors.append(
            f"pogo dish leaves {st['dish_t']:.2f} mm of lid; need {MIN_DISH_LID_MM:.1f} mm"
        )
    if st["tray"] + lid_need > limit + 1e-6:
        errors.append(
            f"battery height stack {st['pouch']:.2f} mm lifts the board to {st['tray']:.2f} mm; "
            f"MCU plus lid skin needs {lid_need:.2f} mm more and exceeds {limit} mm"
        )
    if st["cavity"] + 1e-6 < p["mcu"]["thickness_mm"] + MCU_LID_AIR_MM:
        errors.append(
            f"lid cavity {st['cavity']:.2f} mm is shorter than the {p['mcu']['thickness_mm']:.1f} mm "
            f"module plus {MCU_LID_AIR_MM:.1f} mm air"
        )
    _, est = leftover_mah(p)
    if bat["locked_mah"] > est:
        errors.append(
            f"locked_mah {bat['locked_mah']} is more than the {bat['pocket_width_mm']} x "
            f"{bat['pocket_height_mm']} x {bat['max_thickness_mm']} mm pocket holds (~{est} mAh)"
        )

    if acc.get("lid_material") != "plastic":
        errors.append("lid_material must be plastic; the lid is always PETG")
    finish = str(acc.get("lid_finish", "")).lower()
    if "translucent" not in finish:
        errors.append(
            "lid_finish must be natural translucent PETG so D1 and D2 read through the lid"
        )
    if bat.get("bond") != "board":
        errors.append("battery bond must be board; the pouch is taped to the board underside")
    inner_floor = mag["skin_mm"] + mag["thickness_mm"] + mag["shunt_thickness_mm"]
    if abs(fit["skin_t"] - mag["skin_mm"]) > 1e-6:
        errors.append(
            f"case.scad skin {fit['skin_t']:.2f} mm != params skin {mag['skin_mm']:.2f} mm"
        )
    if mag["skin_mm"] + 1e-9 < 0.80 or mag["skin_mm"] > 0.90 + 1e-9:
        errors.append(
            f"magnet skin is {mag['skin_mm']:.2f} mm; the phone-side web must be "
            f"0.80–0.90 mm of non-ferrous material"
        )
    if abs(fit["floor_t"] - inner_floor) > 1e-6:
        errors.append(
            f"tray inner floor {fit['floor_t']:.2f} mm must be skin + ring + shunt "
            f"({inner_floor:.2f} mm)"
        )
    if fit["clock_rib"] + 1e-9 < 0.8:
        errors.append(
            f"rib between the magnet wells is {fit['clock_rib']:.2f} mm; "
            f"JLCCNC's recommended metal wall is 0.80 mm"
        )
    clock = clock_well(p, fit)
    if not inner.contains_rect(clock):
        errors.append("clocking-magnet well runs into a tray wall")
    if clock.closest_r() < mag["od_mm"] / 2:
        errors.append("clocking-magnet well cuts into the ring seat")
    if st["air"] + 1e-9 < MIN_CELL_AIR_MM or st["air"] > MAX_CELL_AIR_MM + 1e-9:
        errors.append(
            f"air under the wrapped cell is {st['air']:.2f} mm; "
            f"want {MIN_CELL_AIR_MM:.2f}–{MAX_CELL_AIR_MM:.2f} mm so the pouch is not a spacer"
        )

    pogo = pogo_rect(con)
    well = pogo_well_rect(con)
    dish = pogo_dish_rect(con)
    pouch = pouch_rect(p)
    if not board.contains_rect(pogo):
        errors.append("pogo body extends past the PCB outline")
    if not board.contains_rect(pouch):
        errors.append("pouch outline extends past the PCB outline")
    if well.x0 < inner.x0 + MIN_SKIN_MM or well.x1 > inner.x1 - MIN_SKIN_MM:
        errors.append("pogo well leaves under 0.6 mm of lid wall on a long side")
    if well.y1 > inner.y1 - MIN_SKIN_MM + 1e-6:
        errors.append("pogo well leaves under 0.6 mm of lid wall at the top edge")
    if well.y0 < inner.y0 + MIN_SKIN_MM - 1e-6:
        errors.append("pogo well leaves under 0.6 mm of lid wall at the bottom edge")
    if dish.x0 < inner.x0 or dish.x1 > inner.x1:
        errors.append("pogo dish cuts into a lid wall")
    if dish.y1 > inner.y1 + 1e-6:
        errors.append("pogo dish cuts into the top lid wall")
    if dish.y0 < inner.y0 - 1e-6:
        errors.append("pogo dish cuts into the bottom lid wall")
    if pogo.closest_r() < mag["od_mm"] / 2:
        errors.append("pogo body intersects the magnet ring")
    for cx, cy, pr in post_centres(p):
        gap = circle_rect_clearance(cx, cy, pr, pouch)
        if gap < MIN_POST_CLEAR_MM:
            errors.append(
                f"pouch outline is {gap:.2f} mm from a {2 * pr:.1f} mm post at "
                f"({cx:.1f}, {cy:.1f}); need {MIN_POST_CLEAR_MM:.1f} mm"
            )

    # BT1 is flat B.Cu pads just south of the cell. No lid clip.
    pads = pad_zone(con)
    body = pad_body(con)
    bosses = boss_rects(p)
    if not board.contains_rect(pads):
        errors.append("BT1 pad zone extends past the PCB outline")
    if body.overlaps(pouch):
        errors.append("BT1 pads sit under the pouch: the joints cannot be taped over")
    if any(pads.overlaps(b) for b in bosses):
        errors.append("BT1 pads sit under a lid standoff")
    for cx, cy, pr in post_centres(p):
        if circle_hits_rect(cx, cy, pr + 0.5, body):
            errors.append(
                f"BT1 pads hit a {2 * pr:.1f} mm post at ({cx:.1f}, {cy:.1f})"
            )
    if fit["btn_lip"] + 1e-6 > p["connectors"]["button_tip_inset_mm"]:
        errors.append(
            f"TPU pill lip {fit['btn_lip']:.2f} mm is thicker than the "
            f"{p['connectors']['button_tip_inset_mm']:.2f} mm wall-to-tip gap"
        )
    if fit["btn_hole_y"] + 0.4 > fit["btn_head_y"]:
        errors.append("TPU pill head must be larger than the lid-wall hole or it can fall out")
    if fit["btn_border"] + 0.35 > min(fit["btn_head_y"], fit["btn_head_z"]) / 2:
        errors.append("TPU pill flush border leaves no press pad")
    if fit["btn_proud"] < 0.35:
        errors.append("TPU pill press pad must stand proud of the flush bezel")

    if pcb["width_mm"] + 2 * acc["wall_mm"] > acc["width_mm"] + 1e-6:
        errors.append("PCB does not fit inside accessory walls in X")
    if pcb["height_mm"] + 2 * acc["wall_mm"] > acc["height_mm"] + 1e-6:
        errors.append("PCB does not fit inside accessory walls in Y")

    gap = button_gap(p)
    if gap < fit["nub_pretravel"]:
        errors.append(
            f"SW1 actuator tip x={button_tip_x(p):.2f} is {gap:.2f} mm from the inner wall face: "
            "the pill would hold it pressed"
        )
    if gap > MAX_NUB_GAP_MM:
        errors.append(
            f"SW1 actuator tip is {gap:.2f} mm behind the inner wall face; the pill nub tops out "
            f"at {MAX_NUB_GAP_MM} mm"
        )

    if acc["wall_mm"] - fit["ridge_depth"] < MIN_RIDGE_WALL_MM - 1e-6:
        errors.append(
            f"side ridges leave {acc['wall_mm'] - fit['ridge_depth']:.2f} mm of wall, "
            f"need {MIN_RIDGE_WALL_MM}"
        )
    lid_h = acc["thickness_mm"] - st["tray"]
    if lid_h - fit["csk_h"] < MIN_LID_CSK_REMAIN_MM - 1e-6:
        errors.append(
            f"lid countersink leaves {lid_h - fit['csk_h']:.2f} mm of PETG, "
            f"need {MIN_LID_CSK_REMAIN_MM}"
        )
    if fit["csk_h"] + 0.4 > lid_h + 1e-6:
        errors.append(
            f"lid countersink {fit['csk_h']:.2f} mm is too deep for the {lid_h:.2f} mm lid"
        )
    if fit["tap_floor"] < MIN_TAP_FLOOR_MM - 1e-6:
        errors.append(
            f"tray tap leaves {fit['tap_floor']:.2f} mm on the phone face, "
            f"need {MIN_TAP_FLOOR_MM}"
        )
    if fit["tap_floor"] + 1e-6 < st["floor"]:
        errors.append(
            f"tray tap starts at z={fit['tap_floor']:.2f} mm, inside the "
            f"{st['floor']:.2f} mm phone-face floor"
        )
    if fit["tap_floor"] + fit["tap_depth"] > st["pouch"] + 0.2:
        errors.append(
            f"tray tap {fit['tap_depth']:.2f} mm from a {fit['tap_floor']:.2f} mm floor "
            f"breaks past the {st['pouch']:.2f} mm board seat"
        )
    tap_d = p["mounting"]["tap_d_mm"]
    if tap_d >= p["mounting"]["hole_d_mm"] - 1e-6:
        errors.append("tray tap drill should be tighter than the lid clearance hole")
    if fit["csk_d"] <= p["mounting"]["hole_d_mm"] + 1e-6:
        errors.append("lid countersink must be wider than the screw clearance hole")

    if placement is not None:
        j2 = part_xy(placement, "J2")
        if j2 is None:
            errors.append("placement.json has no J2; the lid pogo well has nothing to twin")
        else:
            jx, jy = j2
            if abs(jx - con["pogo_x_mm"]) > 0.01 or abs(jy - con["pogo_y_mm"]) > 0.01:
                errors.append(
                    f"CAD pogo ({con['pogo_x_mm']}, {con['pogo_y_mm']}) "
                    f"!= placement.json J2 ({jx}, {jy}) — lid well would miss the pad"
                )
        bt1 = part_xy(placement, "BT1")
        if bt1 is None:
            errors.append("placement.json has no BT1; the B.Cu pigtail pads have nothing to twin")
        else:
            bx, by = bt1
            if abs(bx - con["batt_pad_x_mm"]) > 0.01 or abs(by - con["batt_pad_y_mm"]) > 0.01:
                errors.append(
                    f"CAD BT1 pads ({con['batt_pad_x_mm']}, {con['batt_pad_y_mm']}) "
                    f"!= placement.json BT1 ({bx}, {by})"
                )
            layer = (part_row(placement, "BT1") or {}).get("layer", "")
            if layer and layer != "B.Cu":
                errors.append(f"BT1 must sit on B.Cu; placement.json says {layer}")
        u1 = u1_rect(p, placement)
        if u1 is None:
            errors.append("placement.json has no U1; cannot tell if the lid cavity covers the module")
        if outline_matches(p, placement):
            errors += board_checks(p, placement)

    ant = p.get("antenna")
    if not isinstance(ant, dict):
        errors.append("params.json has no antenna object (lid IPEX well and FPC tape zone)")
    else:
        remain = acc["shell_back_mm"] - ant["ipex_recess_depth_mm"]
        if remain + 1e-6 < MIN_IPEX_SKIN_MM:
            errors.append(
                f"IPEX well leaves {remain:.2f} mm of PETG; need {MIN_IPEX_SKIN_MM:.2f} mm"
            )
        if ant["ipex_recess_depth_mm"] + 1e-6 > acc["shell_back_mm"]:
            errors.append("IPEX well is deeper than the lid skin")
        ipex_pt = (ant["ipex_x_mm"], ant["ipex_y_mm"])
        if not inner.contains_circle(*ipex_pt, ant["ipex_recess_d_mm"] / 2):
            errors.append("IPEX well runs into a lid wall")
        fpc = antenna_fpc_rect(p)
        if not inner.contains_rect(fpc):
            errors.append("FPC tape zone runs into a lid wall")
        dish = pogo_dish_rect(con)
        if fpc.overlaps(dish):
            errors.append("FPC tape zone overlaps the pogo dish")
        if circle_hits_rect(*ipex_pt, ant["ipex_recess_d_mm"] / 2, dish):
            errors.append("IPEX well overlaps the pogo dish")
        for boss in boss_rects(p):
            if fpc.overlaps(boss):
                errors.append("FPC tape zone overlaps a lid boss")
            if circle_hits_rect(*ipex_pt, ant["ipex_recess_d_mm"] / 2, boss):
                errors.append("IPEX well overlaps a lid boss")
        if placement is not None:
            u1 = u1_rect(p, placement)
            want = ipex_world_from_u1(placement, p)
            if want is None:
                errors.append("placement.json has no U1; the IPEX well has nothing to twin")
            else:
                wx, wy = want
                if abs(wx - ant["ipex_x_mm"]) > 0.05 or abs(wy - ant["ipex_y_mm"]) > 0.05:
                    errors.append(
                        f"CAD IPEX well ({ant['ipex_x_mm']}, {ant['ipex_y_mm']}) "
                        f"!= U1 IPEX ({wx:.2f}, {wy:.2f}) — lid well would miss the connector"
                    )
                if u1 is not None and not u1.contains_point(*ipex_pt):
                    errors.append("IPEX well is not over U1")
                if u1 is not None and fpc.overlaps(u1):
                    errors.append(
                        "FPC tape zone overlaps the 2.4 mm module; move it toward the phone-top end"
                    )

    return errors


def leftover_mah(p: dict) -> tuple[float, int]:
    bat = p["battery"]
    vol_mm3 = bat["pocket_width_mm"] * bat["pocket_height_mm"] * bat["max_thickness_mm"]
    # ~110 mAh per cm³ covers this Jauch 1200 mAh pack (~107 mAh/cm³ at the
    # DigiKey envelope) and still refuses a fantasy claim well above the cell.
    est = vol_mm3 / 1000.0 * 110.0
    return vol_mm3, int(round(est))


def fit_report(p: dict, placement: dict | None = None) -> str:
    mag = p["magnet"]
    pcb = p["pcb"]
    acc = p["accessory"]
    bat = p["battery"]
    con = p["connectors"]
    st = stacks(p)
    vol, est = leftover_mah(p)
    bar_gap = (
        p["phone"]["magnet_center_from_top_mm"]
        - acc["height_mm"] / 2
        - p["phone"]["camera_bar_from_top_mm"]
    )
    pogo = pogo_rect(con)
    pouch = pouch_rect(p)
    pouch_z0 = st["pouch_z0"]
    recess = acc["thickness_mm"] - st["pogo"]
    gap = button_gap(p)
    lid = acc.get("lid_material", "?")
    proud = st["pogo_proud"]
    lines = [
        "Pixel Snap Voice - envelope / PETG fit report",
        "  origin: magnet center, +Y toward camera bar",
        f"  accessory: {acc['width_mm']} x {acc['height_mm']} x {acc['thickness_mm']} mm; "
        f"PCB {pcb['width_mm']} x {pcb['height_mm']} x {pcb['thickness_mm']} mm leaves "
        f"{(acc['width_mm'] - pcb['width_mm']) / 2:.2f} mm per side for a {acc['wall_mm']} mm wall; "
        f"lid {lid} ({acc.get('lid_finish', 'PETG')}), tray PETG then 6061",
        f"  magnet ring: OD {mag['od_mm']} / ID {mag['id_mm']} / {mag['thickness_mm']} mm "
        f"behind a {mag['skin_mm']:.2f} mm skin; clocking magnet "
        f"{mag['clock_width_mm']:.0f} x {mag['clock_length_mm']:.0f} mm, "
        f"long side toward 6 o'clock",
        f"  camera-bar XY gap: {bar_gap:.2f} mm (must be > 0)",
        f"  stacks (phone->shell, limit {acc['thickness_mm']} mm): tray {st['tray']:.2f}, "
        f"pogo face {st['pogo']:.2f} ({proud:.2f} mm proud of the {st['pogo_outer']:.2f} mm dish; "
        f"{recess:.2f} mm under the outer skin), "
        f"battery {st['pouch']:.2f} mm; lid cavity {st['cavity']:.2f} mm",
        f"  battery pocket: {bat['pocket_width_mm']} x {bat['pocket_height_mm']} x {bat['max_thickness_mm']} mm "
        f"= {vol:.0f} mm3 -> ~{est} mAh (current pick {bat['locked_mah']} mAh), taped to the board",
        f"  pouch: {pouch.x1 - pouch.x0:.1f} x {pouch.y1 - pouch.y0:.1f} mm at "
        f"({bat['offset_x_mm']:.1f}, {bat['offset_y_mm']:.1f}), z {pouch_z0:.2f}-"
        f"{st['pouch']:.2f} (under the board, {st['air']:.2f} mm air to the magnet backs); "
        f"{pouch.gap(pogo):.1f} mm from the cell to the pogo",
        f"  pogo: J2 {con['pogo_body_x_mm']:.1f} x {con['pogo_body_y_mm']:.1f} x "
        f"{con['pogo_height_mm']:.1f} mm pad at ({con['pogo_x_mm']:.1f}, {con['pogo_y_mm']:.1f}); "
        f"lid dishes to {st['pogo_outer']:.2f} mm ({st['dish_t']:.2f} mm local lid) so the pad "
        f"is {proud:.2f} mm proud; well is through that dish",
        f"  BT1: B.Cu pigtail solder pads at ({con['batt_pad_x_mm']:.1f}, {con['batt_pad_y_mm']:.1f}), "
        f"no lid window or wrap",
        f"  mic: NPTH ({con['mic_npth_x_mm']:.2f}, {con['mic_npth_y_mm']:.2f}) -> {con['mic_edge']}-wall port "
        f"y={con['mic_y_mm']:.1f}; {mic_port(con).closest_r() - mag['shunt_od_mm'] / 2:.2f} mm "
        "off the shunt edge",
        f"  SW1: actuator tip x={button_tip_x(p):.2f}, {gap:.2f} mm behind the inner wall face; "
        f"TPU pill nub {gap - case_fit()['nub_pretravel']:.2f} mm",
        f"  screws: M1.6 from the lid into {case_fit()['standoff_d']:.1f} mm posts, "
        f"{p['mounting']['tap_d_mm']:.2f} mm tap",
        f"  antenna: IPEX well {p['antenna']['ipex_recess_d_mm']:.1f} mm at "
        f"({p['antenna']['ipex_x_mm']:.1f}, {p['antenna']['ipex_y_mm']:.1f}), "
        f"{p['antenna']['ipex_recess_depth_mm']:.2f} mm into the "
        f"{acc['shell_back_mm']:.2f} mm lid skin; FPC tape "
        f"{p['antenna']['fpc_w_mm']:.0f} x {p['antenna']['fpc_h_mm']:.0f} mm at "
        f"({p['antenna']['fpc_x_mm']:.1f}, {p['antenna']['fpc_y_mm']:.1f})",
        "  PETG checklist (physical, after print):",
        "    [ ] camera bar not covered when snapped",
        "    [ ] magnetic cable seats on the lid pad and the plug misses the phone body",
        f"    [ ] mic port on the phone-{con['mic_edge']} long edge, not against glass",
        "    [ ] TPU pill clicks SW1 and springs back",
        "    [ ] side ridges give enough grip to slide it off the ring",
        "    [ ] ring and clocking magnet sit in the wells and the case does not spin",
        "    [ ] lid dish sits over J2 and the pad is flush or a hair proud",
        "    [ ] taped dummy pouch clears the posts and the board still seats",
        "    [ ] IPEX well sits over U1 and the FPC mark is on the inner ceiling",
    ]
    held = pending(p, placement)
    if held:
        b = placement.get("board", {}) if placement is not None else {}
        lines.append(
            f"  waiting on the PCB re-place (placement.json is the {b.get('width_mm')} x "
            f"{b.get('height_mm')} board; these fail once it is on {pcb['width_mm']} x {pcb['height_mm']}):"
        )
        lines += [f"    - {e}" for e in held]
    return "\n".join(lines)


def current_outline(p: dict, placement: dict) -> dict:
    out = copy.deepcopy(placement)
    out.setdefault("board", {})["width_mm"] = p["pcb"]["width_mm"]
    out["board"]["height_mm"] = p["pcb"]["height_mm"]
    return out


def moved(placement: dict, ref: str, **fields: float) -> dict:
    out = copy.deepcopy(placement)
    for row in out.get("parts", []):
        if row.get("ref") == ref:
            row.update(fields)
    return out


def self_test() -> list[str]:
    """Synthetic cases so a stay-green check cannot hide a collision."""
    p = load_json()
    placement = load_placement()
    failures: list[str] = []

    def expect(label: str, err: list[str], *words: str) -> None:
        if not any(all(w in e for w in words) for e in err):
            failures.append(f"{label} should fail with {words!r}, got {err}")

    live = check(p, placement)
    if live:
        failures.append(f"live params should pass, got {live}")

    scad = parse_scad()
    drift = dict(scad, acc_w=scad["acc_w"] + 1.0)
    errs: list[str] = []
    scad_matches(p, drift, errs)
    expect("params.scad acc_w drift", errs, "acc_w")
    stray = dict(scad, jst_h=6.0)
    errs = []
    scad_matches(p, stray, errs)
    expect("params.scad leftover jst_h", errs, "jst_h")

    old = copy.deepcopy(p)
    old["battery"]["offset_y_mm"] = 22.0
    expect("offset_y=22", check(old, placement), "pouch", "post")

    ring = copy.deepcopy(p)
    ring["connectors"]["pogo_y_mm"] = 0.0
    expect("pogo at origin", check(ring, None), "magnet ring")

    wall = copy.deepcopy(p)
    wall["connectors"]["pogo_y_mm"] = 41.0
    expect("J2 at y=41", check(wall, None), "top edge")

    shunt = copy.deepcopy(p)
    shunt["connectors"]["mic_npth_x_mm"] = 26.5
    shunt["connectors"]["mic_npth_y_mm"] = 9.32
    expect("mic NPTH at (26.5, 9.32)", check(shunt, None), "shunt")

    offboard = copy.deepcopy(p)
    offboard["connectors"]["mic_npth_x_mm"] = 30.0
    offboard["connectors"]["mic_npth_y_mm"] = 9.32
    expect("mic NPTH at the 64 mm board's (30, 9.32)", check(offboard, None), "off the PCB")

    thick = copy.deepcopy(p)
    thick["battery"]["max_thickness_mm"] = 5.0
    expect("5 mm pouch", check(thick, None), "battery height stack")

    greedy = copy.deepcopy(p)
    greedy["battery"]["locked_mah"] = 2000
    expect("2000 mAh in this pocket", check(greedy, None), "locked_mah")

    buried = copy.deepcopy(p)
    buried["connectors"]["batt_pad_x_mm"] = 0.0
    buried["connectors"]["batt_pad_y_mm"] = -10.0
    expect("BT1 pads at (0, -10)", check(buried, None), "BT1 pads", "pouch")

    metal_lid = copy.deepcopy(p)
    metal_lid["accessory"]["lid_material"] = "aluminum"
    expect("aluminum lid", check(metal_lid, None), "lid_material")

    hanging = copy.deepcopy(p)
    hanging["battery"]["bond"] = "tray"
    expect("tray-bonded pouch", check(hanging, None), "bond")

    opaque = copy.deepcopy(p)
    opaque["accessory"]["lid_finish"] = "black PETG"
    expect("opaque lid", check(opaque, None), "translucent")

    recessed = copy.deepcopy(p)
    recessed["connectors"]["pogo_proud_mm"] = -0.5
    expect("recessed pad", check(recessed, None), "proud")

    thin_dish = copy.deepcopy(p)
    thin_dish["connectors"]["pogo_proud_mm"] = 1.0
    expect("1 mm proud pad", check(thin_dish, None), "dish")

    flush = copy.deepcopy(p)
    flush["connectors"]["button_tip_inset_mm"] = -0.2
    expect("SW1 tip in the wall", check(flush, None), "SW1", "pressed")

    deep_ipex = copy.deepcopy(p)
    deep_ipex["antenna"]["ipex_recess_depth_mm"] = p["accessory"]["shell_back_mm"]
    expect("IPEX well through the lid", check(deep_ipex, None), "IPEX well")

    fpc_pogo = copy.deepcopy(p)
    fpc_pogo["antenna"]["fpc_x_mm"] = p["connectors"]["pogo_x_mm"]
    fpc_pogo["antenna"]["fpc_y_mm"] = p["connectors"]["pogo_y_mm"]
    expect("FPC on the pogo dish", check(fpc_pogo, None), "FPC", "pogo")

    if placement is not None:
        mismatch = moved(placement, "J2", y_mm=99.0)
        expect("J2 XY drift", check(p, mismatch), "J2", "placement.json")

        ipex_off = copy.deepcopy(p)
        ipex_off["antenna"]["ipex_x_mm"] = 0.0
        ipex_off["antenna"]["ipex_y_mm"] = 0.0
        expect("IPEX well at origin", check(ipex_off, placement), "IPEX well")

        pad_drift = moved(placement, "BT1", x_mm=-23.5)
        expect("BT1 XY drift", check(p, pad_drift), "BT1", "placement.json")

        off = copy.deepcopy(p)
        off["battery"]["offset_y_mm"] = 40.0
        expect("offset_y=40", check(off, placement), "pouch", "PCB")

        # The 64 x 86 board's MK1 / SW1 seats, synthesised so this keeps
        # testing something once the live file is on the new outline. On an
        # old outline they must only be pending; on this one they must fail.
        stale = current_outline(p, placement)
        stale = moved(stale, "MK1", x_mm=30.0, y_mm=10.0, rot_deg=90)
        stale = moved(stale, "SW1", x_mm=-29.3, y_mm=12.0, rot_deg=270)
        old_outline = copy.deepcopy(stale)
        old_outline["board"]["width_mm"] = 64.0
        old_outline["board"]["height_mm"] = 86.0
        if not any("MK1" in e for e in pending(p, old_outline)):
            failures.append(f"stale MK1 should be pending, got {pending(p, old_outline)}")
        if any("MK1" in e for e in check(p, old_outline)):
            failures.append("stale MK1 on the old outline should be pending, not an error")
        here = stale
        err = check(p, here)
        expect("MK1 off the seal on this outline", err, "MK1", "seal")
        expect("SW1 off the nub on this outline", err, "SW1", "nub")

        con = p["connectors"]
        lx, ly = MK1_PORT_LOCAL
        fixed = moved(here, "MK1", x_mm=con["mic_npth_x_mm"], y_mm=con["mic_npth_y_mm"] + lx, rot_deg=90)
        fixed = moved(fixed, "SW1", x_mm=button_tip_x(p) + SW1_TIP_LOCAL[1], y_mm=con["button_y_mm"], rot_deg=270)
        err = check(p, fixed)
        for ref in ("MK1", "SW1"):
            if any(ref in e for e in err):
                failures.append(f"{ref} at the CAD target should pass, got {err}")

    return failures


def main() -> int:
    if not PARAMS_JSON.is_file():
        print("FAIL: params.json missing", file=sys.stderr)
        return 1
    try:
        case_fit()
    except KeyError as exc:
        print(f"FAIL: {exc.args[0]}", file=sys.stderr)
        return 1
    test_errors = self_test()
    if test_errors:
        print("FAIL: check_envelope self-test", file=sys.stderr)
        for e in test_errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    p = load_json()
    placement = load_placement()
    errors = check(p, placement)
    if PARAMS_SCAD.is_file():
        scad_matches(p, parse_scad(), errors)
    print(fit_report(p, placement))
    if errors:
        print("FAIL:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("check_envelope: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
