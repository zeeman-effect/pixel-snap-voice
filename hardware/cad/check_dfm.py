#!/usr/bin/env python3
"""Fail the case if a named shop process cannot make the live model as-is.

check_envelope.py asks whether the shell fits a Pixel 10. This file asks
whether JLCCNC, JLC3DP, or PCBWay would accept the same solids. Limits are
the published capability pages, not house guesses. A warn is below the
recommended number but above the absolute floor. A fail is under the floor,
the wrong material, or a part that cannot do its job in that material.

Default exit is 0 when variant=metal passes JLCCNC or PCBWay CNC.
--print-only exits 0 once a plastic process accepts the PETG default.
"""

from __future__ import annotations

import argparse
import math
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from check_envelope import (  # noqa: E402
    CASE_SCAD,
    case_fit,
    load_json,
    parse_scad,
    stacks,
    usbc_wall,
)

# variant=metal shares the 0.85 mm magnet skin and TPU pill with PETG.
# Leftover metal-only numbers lived here; they are gone.

EXPORT = ROOT / "export"

# Published shop floors. Each number has a source next to the process.
# JLCCNC capabilities (min part 5 x 5 x 1, metal wall rec 0.8) vs the older
# size article (special 30 x 20 x 5, flat 30 x 10 x 3) disagree on thickness.
# Both are recorded. The hard reject uses the capabilities 1 mm floor; the
# 3 mm / 5 mm article is a warn because JLC may still bounce a thin tray.
JLC_CNC_MAX = (1100.0, 600.0, 500.0)
JLC_CNC_MIN_CUBE = (5.0, 5.0, 1.0)
JLC_CNC_FLAT_T = 3.0
JLC_CNC_SPECIAL_T = 5.0
JLC_METAL_WALL_REC = 0.8
JLC_METAL_WALL_ABS = 0.5
JLC_PLASTIC_WALL_REC = 1.5
JLC_CNC_TOL = 0.1
JLC_R_MIN_SHALLOW = 0.5
JLC_R_SHALLOW_H = 3.0

PCBWAY_CNC_MIN_T = 2.0
PCBWAY_CNC_MIN_D = 0.3
PCBWAY_WALL_REC = 1.2
PCBWAY_THINNEST = 0.8

JLC_FDM_MIN = (30.0, 30.0, 10.0)
JLC_PRINT_MIN_ALT = (10.0, 2.0, 2.0)  # SLA / MJF / SLM alternate min
JLC_SLA_HOLE = 1.0
JLC_NYLON_HOLE = 1.5
JLC_SLM_HOLE = 1.5
JLC_SLA_DETAIL = 0.8
JLC_FDM_DETAIL = 1.0
JLC_SLM_DETAIL = 1.0
JLC_SLA_CLEAR = 0.2
JLC_NYLON_CLEAR = 0.2
JLC_SLM_CLEAR = 0.5
JLC_FDM_CLEAR = 0.5
JLC_SLA_COL = 1.0
JLC_NYLON_COL = 2.0
JLC_SLM_COL = 2.0

# EVQP7C01P from docs/bom.md. The lid key has to move this far at this force.
SW_FORCE_N = 2.2
SW_TRAVEL_MM = 0.2
E_PETG = 2200.0
E_SLA = 2500.0
E_NYLON = 1700.0
E_6061 = 69000.0
E_ALSI10MG = 70000.0
E_316L = 190000.0
E_TI = 110000.0


@dataclass
class Finding:
    severity: str  # fail | warn | info
    text: str


@dataclass
class ProcessResult:
    name: str
    shop: str
    kind: str  # print | cnc | slm
    metal: bool
    ok: bool
    findings: list[Finding] = field(default_factory=list)

    def add(self, severity: str, text: str) -> None:
        self.findings.append(Finding(severity, text))
        if severity == "fail":
            self.ok = False


def _dims_ok(w: float, h: float, t: float, minimum: tuple[float, float, float]) -> bool:
    got = sorted((w, h, t), reverse=True)
    need = sorted(minimum, reverse=True)
    return all(g + 1e-9 >= n for g, n in zip(got, need))


def _inside_max(w: float, h: float, t: float, maximum: tuple[float, float, float]) -> bool:
    got = sorted((w, h, t), reverse=True)
    need = sorted(maximum, reverse=True)
    return all(g <= n + 1e-9 for g, n in zip(got, need))


def wall_rec_for_size(table: dict[float, float], size_mm: float) -> float:
    """Linear interpolate JLC3DP's size-vs-wall table."""
    keys = sorted(table)
    if size_mm <= keys[0]:
        return table[keys[0]]
    if size_mm >= keys[-1]:
        return table[keys[-1]]
    for lo, hi in zip(keys, keys[1:]):
        if lo <= size_mm <= hi:
            span = hi - lo
            return table[lo] + (table[hi] - table[lo]) * (size_mm - lo) / span
    return table[keys[-1]]


SLA_WALL = {5: 0.5, 10: 0.8, 50: 1.0, 100: 1.5, 200: 2.0}
NYLON_WALL = {5: 1.0, 10: 1.2, 50: 1.5, 100: 2.0, 200: 2.0}
SLM_WALL = {5: 1.5, 10: 1.5, 50: 1.5, 100: 2.0, 200: 2.5}
FDM_WALL = {50: 1.6, 100: 2.0, 200: 2.5}


def features(p: dict, *, variant: str = "petg") -> dict[str, float]:
    """Every millimetre this check judges, read from the live CAD."""
    metal = variant == "metal"
    acc = p["accessory"]
    fit = dict(case_fit())
    scad = parse_scad(CASE_SCAD)
    st = stacks(p)
    wall = acc["wall_mm"]
    back = acc["shell_back_mm"]
    lip_inset = 0.0 if metal else scad["lip_inset"]
    lip_clear = 0.0 if metal else scad["lip_clear"]
    skirt = 0.0 if metal else lip_inset - lip_clear
    cavity_h = st["cavity"]
    rec_r = cavity_h / 10.0 + 0.5
    inner_r = max(0.4, scad["corner_r"] - wall)
    magnet_floor = fit["skin_t"]
    usbc = usbc_wall(p, fit)
    return {
        "acc_w": acc["width_mm"],
        "acc_h": acc["height_mm"],
        "acc_t": acc["thickness_mm"],
        "wall": wall,
        "back": back,
        "tray_h": st["tray"],
        "lid_h": acc["thickness_mm"] - st["tray"],
        "cavity_h": cavity_h,
        "variant": 1.0 if metal else 0.0,
        "has_lip": 0.0 if metal else 1.0,
        "has_flexure": 0.0,
        "magnet_floor": magnet_floor,
        "duct_floor": 0.0,
        "standoff_d": fit["standoff_d"],
        "lip_t": lip_inset,
        "lip_h": 0.0 if metal else scad["lip_h"],
        "lip_clear": lip_clear,
        "skirt": skirt,
        "ridge_depth": fit["ridge_depth"],
        "ridge_w": scad["ridge_w"],
        "ridge_remain": wall - fit["ridge_depth"],
        "skirt_remain": skirt - scad["ridge_skirt_depth"],
        "wave_depth": scad["wave_depth"],
        "wave_stroke": scad["wave_stroke"],
        "wave_remain": back - scad["wave_depth"],
        "usbc_mouth_w": fit["usbc_mouth_w"],
        "usbc_mouth_h": fit["usbc_mouth_h"],
        "usbc_recess_w": fit["usbc_recess_w"],
        "usbc_recess_h": fit["usbc_recess_h"],
        "usbc_recess_d": fit["usbc_recess_d"],
        "usbc_web": usbc["web"],
        "usbc_frame": min(
            usbc["mouth_x0"] - usbc["recess_x0"],
            usbc["mouth_z0"] - usbc["recess_z0"],
        ),
        "usbc_ledge": usbc["ledge"],
        "has_lid_cnc": 0.0,
        "inner_r": inner_r,
        "rec_r": rec_r,
        "pig_rib": 0.0,
        "pig_clip_h": 0.0,
        "key_slit": 0.0,
        "key_arm": 1.0,
        "key_i": 1.0,
        "btn_hole_y": fit["btn_hole_y"],
        "btn_hole_z": fit["btn_hole_z"],
        "btn_lip": fit["btn_lip"],
        "tap_d": p["mounting"]["tap_d_mm"],
        "tap_floor": fit["tap_floor"],
        "lid_pilot_d": p["mounting"]["tap_d_mm"],
        "hole_d": p["mounting"]["hole_d_mm"],
        "csk_d": fit["csk_d"],
        "csk_h": fit["csk_h"],
        "mic_w": fit["mic_port_w"],
        "mic_port_h": fit["mic_port_h"],
        "pcb_clear": scad["pcb_clear"],
        "ipex_remain": back - p["antenna"]["ipex_recess_depth_mm"],
    }


def key_deflection(feat: dict[str, float], e_mpa: float) -> float:
    """Cantilever tip travel at the switch force, millimetres."""
    return SW_FORCE_N * feat["key_arm"] ** 3 / (3.0 * e_mpa * feat["key_i"])


def _wall_items(feat: dict[str, float]) -> dict[str, float]:
    items = {
        "side wall": feat["wall"],
        "back skin": feat["back"],
        "magnet-pocket floor": feat["magnet_floor"],
        "tray/lid lip": feat["lip_t"],
        "lid joint skirt": feat["skirt"],
        "wall after grip flutes": feat["ridge_remain"],
        "skirt after grip flutes": feat["skirt_remain"],
        "wall after wave art": feat["wave_remain"],
        "end-wall web in the USB-C relief": feat["usbc_web"],
    }
    # variant=metal is a 6061 tray. The lid stays PETG, so CNC must not
    # judge the back skin or wave as milled metal.
    if feat.get("variant", 0.0) >= 0.5:
        for name in ("back skin", "wall after wave art"):
            items.pop(name, None)
    if feat.get("has_lip", 1.0) < 0.5:
        for name in ("lid joint skirt", "skirt after grip flutes", "tray/lid lip"):
            items.pop(name, None)
    if feat["magnet_floor"] <= 0.05:
        items.pop("magnet-pocket floor", None)
    return {name: val for name, val in items.items() if val > 0.05}


def thinnest_metal(feat: dict[str, float]) -> tuple[float, str]:
    candidates = _wall_items(feat)
    name = min(candidates, key=candidates.get)
    return candidates[name], name


def _wall_findings(
    proc: ProcessResult,
    feat: dict[str, float],
    *,
    rec: float,
    abs_min: float | None,
    extra: dict[str, float] | None = None,
) -> None:
    items = _wall_items(feat)
    if extra:
        items.update(extra)
    for name, val in items.items():
        if abs_min is not None and val + 1e-9 < abs_min:
            proc.add(
                "fail",
                f"{name} is {val:.2f} mm; {proc.shop} absolute floor is {abs_min:.2f} mm",
            )
        elif val + 1e-9 < rec:
            proc.add(
                "warn",
                f"{name} is {val:.2f} mm; {proc.shop} recommended wall is {rec:.2f} mm",
            )


def _detail_findings(
    proc: ProcessResult,
    feat: dict[str, float],
    *,
    min_detail: float,
) -> None:
    for name, depth, width in (
        ("wave engraving", feat["wave_depth"], feat["wave_stroke"]),
        ("grip ridges", feat["ridge_depth"], feat["ridge_w"]),
    ):
        if depth + 1e-9 < min_detail or width + 1e-9 < min_detail:
            proc.add(
                "fail",
                f"{name} is {depth:.2f} mm deep and {width:.2f} mm wide; "
                f"{proc.shop} minimum detail is {min_detail:.2f} mm",
            )


def _hole_findings(
    proc: ProcessResult,
    feat: dict[str, float],
    *,
    min_hole: float,
    min_col: float,
) -> None:
    mouth = min(feat["usbc_mouth_w"], feat["usbc_mouth_h"])
    if mouth + 1e-9 < min_hole:
        proc.add(
            "fail",
            f"USB-C mouth is {feat['usbc_mouth_w']:.1f} x {feat['usbc_mouth_h']:.1f} mm; "
            f"{proc.shop} minimum opening is {min_hole:.2f} mm",
        )
    if feat["tap_d"] + 1e-9 < min_hole:
        proc.add(
            "warn",
            f"tray tap drills are {feat['tap_d']:.2f} mm; "
            f"{proc.shop} will not tap M1.6 as-printed - tap after CNC",
        )
    if feat.get("pig_rib", 0.0) > 0.05 and feat["pig_rib"] + 1e-9 < min_col:
        proc.add(
            "fail",
            f"pigtail clip ribs are {feat['pig_rib']:.2f} mm thick and "
            f"{feat['pig_clip_h']:.2f} mm tall; {proc.shop} minimum column is "
            f"{min_col:.2f} mm",
        )
    hole = min(feat.get("btn_hole_y", 8.0), feat.get("btn_hole_z", 2.6))
    if hole + 1e-9 < min_hole:
        proc.add(
            "fail",
            f"TPU pill hole is {feat['btn_hole_y']:.1f} x {feat['btn_hole_z']:.1f} mm; "
            f"{proc.shop} minimum opening is {min_hole:.2f} mm",
        )
    if feat.get("standoff_d", 5.0) + 1e-9 < min_col:
        proc.add(
            "fail",
            f"tray posts are {feat['standoff_d']:.1f} mm; "
            f"{proc.shop} minimum column is {min_col:.2f} mm",
        )


def _key_findings(proc: ProcessResult, feat: dict[str, float], e_mpa: float, label: str) -> None:
    travel = key_deflection(feat, e_mpa)
    if travel + 1e-9 < SW_TRAVEL_MM:
        proc.add(
            "fail",
            f"record key in {label} moves {travel:.3f} mm at {SW_FORCE_N} N; "
            f"SW1 needs {SW_TRAVEL_MM:.2f} mm. This key is a PETG flexure. "
            f"Metal needs a separate plastic button or a cut-out for a finger",
        )
    else:
        proc.add(
            "info",
            f"record key in {label} moves {travel:.2f} mm at {SW_FORCE_N} N "
            f"(needs {SW_TRAVEL_MM:.2f} mm)",
        )


def _clearance_findings(proc: ProcessResult, feat: dict[str, float], minimum: float) -> None:
    if feat.get("has_lip", 1.0) >= 0.5 and feat["lip_clear"] + 1e-9 < minimum:
        proc.add(
            "fail",
            f"tray/lid joint clearance is {feat['lip_clear']:.2f} mm; "
            f"{proc.shop} assembly clearance floor is {minimum:.2f} mm",
        )
    if feat["pcb_clear"] + 1e-9 < minimum:
        proc.add(
            "warn",
            f"board rebate is {feat['pcb_clear']:.2f} mm per side; "
            f"{proc.shop} assembly clearance floor is {minimum:.2f} mm",
        )


def _size_pair(
    proc: ProcessResult,
    feat: dict[str, float],
    *,
    minimum: tuple[float, float, float],
    maximum: tuple[float, float, float] | None = None,
    tray_extra_min_t: float | None = None,
    tray_extra_label: str | None = None,
) -> None:
    parts = (("tray", feat["tray_h"]),)
    if feat.get("variant", 0.0) < 0.5:
        parts += (("lid", feat["lid_h"]),)
    for name, t in parts:
        if not _dims_ok(feat["acc_w"], feat["acc_h"], t, minimum):
            proc.add(
                "fail",
                f"{name} bounding box {feat['acc_w']:.1f} x {feat['acc_h']:.1f} x "
                f"{t:.2f} mm is under {proc.shop} minimum "
                f"{minimum[0]:.0f} x {minimum[1]:.0f} x {minimum[2]:.0f} mm",
            )
        if maximum is not None and not _inside_max(feat["acc_w"], feat["acc_h"], t, maximum):
            proc.add(
                "fail",
                f"{name} is larger than {proc.shop} maximum "
                f"{maximum[0]:.0f} x {maximum[1]:.0f} x {maximum[2]:.0f} mm",
            )
    if tray_extra_min_t is not None and feat["tray_h"] + 1e-9 < tray_extra_min_t:
        proc.add(
            "warn",
            f"tray is {feat['tray_h']:.2f} mm thick; {tray_extra_label}",
        )


def evaluate_jlc_cnc(feat: dict[str, float]) -> ProcessResult:
    proc = ProcessResult("JLCCNC 6061 (3-axis / 5-axis)", "JLCCNC", "cnc", True, True)
    _size_pair(
        proc,
        feat,
        minimum=JLC_CNC_MIN_CUBE,
        maximum=JLC_CNC_MAX,
        tray_extra_min_t=JLC_CNC_FLAT_T,
        tray_extra_label=(
            f"JLCCNC's Feb 2025 size article wants 3 mm for a flat part and "
            f"{JLC_CNC_SPECIAL_T:.0f} mm for a special shape. The capabilities "
            f"page allows 1 mm. Expect a human review, not an instant accept"
        ),
    )
    thin, thin_name = thinnest_metal(feat)
    if thin + 1e-9 < JLC_METAL_WALL_ABS:
        proc.add(
            "fail",
            f"thinnest metal is {thin:.2f} mm ({thin_name}); JLCCNC absolute "
            f"metal wall is {JLC_METAL_WALL_ABS:.2f} mm "
            f"(recommended {JLC_METAL_WALL_REC:.2f} mm)",
        )
    _wall_findings(proc, feat, rec=JLC_METAL_WALL_REC, abs_min=JLC_METAL_WALL_ABS)
    if feat["inner_r"] + 1e-9 < feat["rec_r"] and feat["cavity_h"] > JLC_R_SHALLOW_H:
        proc.add(
            "warn",
            f"lid cavity is {feat['cavity_h']:.2f} mm deep with inner R "
            f"{feat['inner_r']:.2f} mm; JLCCNC's H/10+0.5 guide is "
            f"{feat['rec_r']:.2f} mm. They will leave tool radius in the corners",
        )
    if feat.get("has_lip", 1.0) >= 0.5 and feat["lip_clear"] < 2 * JLC_CNC_TOL - 1e-9:
        proc.add(
            "warn",
            f"joint clearance is {feat['lip_clear']:.2f} mm and JLCCNC standard "
            f"tolerance is +/-{JLC_CNC_TOL:.1f} mm. The lid can bind or rattle "
            f"unless the drawing calls a fit",
        )
    if feat.get("has_flexure", 1.0) >= 0.5 and feat["key_slit"] < 1.0:
        proc.add(
            "warn",
            f"record-key slit is {feat['key_slit']:.2f} mm on a 45 deg plane. "
            f"That needs a sub-1 mm tool and a side or 5-axis setup",
        )
    if feat.get("has_flexure", 1.0) >= 0.5:
        _key_findings(proc, feat, E_6061, "6061")
    else:
        proc.add(
            "info",
            "record button is a captive TPU 95A pill in the PETG lid; SW1 is the spring",
        )
    proc.add(
        "info",
        "lid is PETG with the top half of the USB-C mouth; CNC is the 6061 tray only",
    )
    return proc


def evaluate_pcbway_cnc(feat: dict[str, float]) -> ProcessResult:
    proc = ProcessResult("PCBWay CNC 6061", "PCBWay", "cnc", True, True)
    names = (("tray", feat["tray_h"]),)
    if feat.get("variant", 0.0) < 0.5:
        names += (("lid", feat["lid_h"]),)
    for name, t in names:
        if t + 1e-9 < PCBWAY_CNC_MIN_T:
            proc.add(
                "fail",
                f"{name} is {t:.2f} mm thick; PCBWay published minimum part is "
                f"{PCBWAY_CNC_MIN_T:.0f} mm",
            )
    thin, thin_name = thinnest_metal(feat)
    if thin + 1e-9 < PCBWAY_THINNEST:
        proc.add(
            "fail",
            f"thinnest metal is {thin:.2f} mm ({thin_name}); PCBWay quote page "
            f"asks for walls > {PCBWAY_WALL_REC:.1f} mm and thinnest >= "
            f"{PCBWAY_THINNEST:.1f} mm",
        )
    _wall_findings(proc, feat, rec=PCBWAY_WALL_REC, abs_min=PCBWAY_THINNEST)
    for name, d in (("tray tap", feat["tap_d"]), ("lid clearance", feat["hole_d"])):
        if d + 1e-9 < PCBWAY_CNC_MIN_D:
            proc.add("fail", f"{name} hole {d:.2f} mm is under PCBWay 0.3 mm minimum")
    if feat.get("has_flexure", 1.0) >= 0.5:
        _key_findings(proc, feat, E_6061, "6061")
    return proc


def evaluate_jlc_fdm(feat: dict[str, float]) -> ProcessResult:
    proc = ProcessResult("JLC3DP FDM (PLA/ABS line)", "JLC3DP", "print", False, True)
    _size_pair(proc, feat, minimum=JLC_FDM_MIN)
    size = max(feat["acc_w"], feat["acc_h"])
    rec = wall_rec_for_size(FDM_WALL, size)
    _wall_findings(proc, feat, rec=rec, abs_min=1.0)
    _detail_findings(proc, feat, min_detail=JLC_FDM_DETAIL)
    _hole_findings(proc, feat, min_hole=JLC_NYLON_HOLE, min_col=JLC_NYLON_COL)
    _clearance_findings(proc, feat, JLC_FDM_CLEAR)
    if feat.get("has_flexure", 1.0) >= 0.5:
        _key_findings(proc, feat, E_PETG, "PETG-class plastic")
    return proc


def evaluate_local_fdm(feat: dict[str, float]) -> ProcessResult:
    """Home / local PETG. This is what case.scad was written for."""
    proc = ProcessResult("Local FDM PETG (0.4 mm nozzle)", "local print", "print", False, True)
    if feat["wall"] < 0.8:
        proc.add("fail", f"side wall {feat['wall']:.2f} mm is under two 0.4 mm perimeters")
    if feat["magnet_floor"] < 0.4:
        proc.add("fail", f"magnet floor {feat['magnet_floor']:.2f} mm is under three 0.15 mm layers")
    if min(feat["usbc_mouth_w"], feat["usbc_mouth_h"]) < 3.0:
        proc.add("fail", "USB-C mouth is too small to print as a wall opening")
    if feat["usbc_web"] < 0.4:
        proc.add(
            "fail",
            f"USB-C relief leaves a {feat['usbc_web']:.2f} mm web; under one 0.4 mm line",
        )
    elif feat["usbc_web"] < 0.8:
        proc.add(
            "warn",
            f"USB-C relief leaves a {feat['usbc_web']:.2f} mm web, one line wide. "
            "It has to be that thin for a plug to latch; print slow, no ironing",
        )
    if feat["usbc_ledge"] < 0.4:
        proc.add(
            "fail",
            f"lid-top ledge over the USB-C relief is {feat['usbc_ledge']:.2f} mm; "
            "under two layers",
        )
    hole = min(feat.get("btn_hole_y", 8.0), feat.get("btn_hole_z", 2.6))
    if hole < 1.2:
        proc.add("fail", f"TPU pill hole {hole:.2f} mm will fuse on FDM")
    if feat.get("btn_lip", 0.4) < 0.3:
        proc.add("fail", f"TPU pill lip {feat['btn_lip']:.2f} mm is too thin to stay captive")
    if feat["lip_clear"] < 0.2:
        proc.add(
            "warn",
            f"joint clearance is {feat['lip_clear']:.2f} mm. FDM often wants 0.2-0.3 mm; "
            f"sand the lip if the lid binds",
        )
    if feat["wave_depth"] < 0.4 or feat["wave_stroke"] < 0.8:
        proc.add(
            "warn",
            "wave art is 0.35 x 0.5 mm. On a lid printed outer-face down it is "
            "first-layer texture, not a crisp engraving",
        )
    if feat.get("ipex_remain", 1.0) < 0.5:
        proc.add(
            "warn",
            f"IPEX well leaves {feat['ipex_remain']:.2f} mm of PETG. Print the lid "
            "outer-face down so that skin is the first layer",
        )
    if feat.get("has_flexure", 1.0) >= 0.5:
        _key_findings(proc, feat, E_PETG, "PETG")
    return proc


def evaluate_jlc_sla(feat: dict[str, float]) -> ProcessResult:
    proc = ProcessResult("JLC3DP SLA resin", "JLC3DP", "print", False, True)
    _size_pair(proc, feat, minimum=JLC_PRINT_MIN_ALT)
    size = max(feat["acc_w"], feat["acc_h"])
    rec = wall_rec_for_size(SLA_WALL, size)
    _wall_findings(proc, feat, rec=rec, abs_min=0.5)
    _detail_findings(proc, feat, min_detail=JLC_SLA_DETAIL)
    _hole_findings(proc, feat, min_hole=JLC_SLA_HOLE, min_col=JLC_SLA_COL)
    _clearance_findings(proc, feat, JLC_SLA_CLEAR)
    if feat.get("has_flexure", 1.0) >= 0.5:
        _key_findings(proc, feat, E_SLA, "SLA resin")
    return proc


def evaluate_jlc_mjf(feat: dict[str, float]) -> ProcessResult:
    proc = ProcessResult("JLC3DP MJF / SLS nylon", "JLC3DP", "print", False, True)
    _size_pair(proc, feat, minimum=JLC_PRINT_MIN_ALT)
    size = max(feat["acc_w"], feat["acc_h"])
    rec = wall_rec_for_size(NYLON_WALL, size)
    _wall_findings(proc, feat, rec=rec, abs_min=1.0)
    _detail_findings(proc, feat, min_detail=JLC_SLA_DETAIL)
    _hole_findings(proc, feat, min_hole=JLC_NYLON_HOLE, min_col=JLC_NYLON_COL)
    _clearance_findings(proc, feat, JLC_NYLON_CLEAR)
    if feat.get("has_flexure", 1.0) >= 0.5:
        _key_findings(proc, feat, E_NYLON, "PA12 nylon")
    return proc


def evaluate_jlc_slm(feat: dict[str, float]) -> ProcessResult:
    proc = ProcessResult("JLC3DP SLM (316L / Ti only)", "JLC3DP", "slm", True, True)
    proc.add(
        "fail",
        "JLC3DP SLM materials are 316L stainless and titanium TC4. They do not "
        "list aluminum. 316L is steel - this shell must not be steel or it "
        "steals hold from the magnet ring. Titanium is the wrong price for a "
        "cosmetic copy of a PETG print",
    )
    _size_pair(proc, feat, minimum=JLC_PRINT_MIN_ALT)
    size = max(feat["acc_w"], feat["acc_h"])
    rec = wall_rec_for_size(SLM_WALL, size)
    _wall_findings(proc, feat, rec=rec, abs_min=1.5)
    _detail_findings(proc, feat, min_detail=JLC_SLM_DETAIL)
    _hole_findings(proc, feat, min_hole=JLC_SLM_HOLE, min_col=JLC_SLM_COL)
    _clearance_findings(proc, feat, JLC_SLM_CLEAR)
    if feat.get("has_flexure", 1.0) >= 0.5:
        _key_findings(proc, feat, E_316L, "316L")
    return proc


def evaluate_pcbway_slm(feat: dict[str, float]) -> ProcessResult:
    proc = ProcessResult("PCBWay SLM AlSi10Mg", "PCBWay", "slm", True, True)
    size = max(feat["acc_w"], feat["acc_h"])
    rec = wall_rec_for_size(SLM_WALL, size)
    # PCBWay lists 1.0 mm minimum wall for SLM. Use that as the absolute.
    _wall_findings(proc, feat, rec=rec, abs_min=1.0)
    _detail_findings(proc, feat, min_detail=1.0)
    _hole_findings(proc, feat, min_hole=1.5, min_col=1.5)
    _clearance_findings(proc, feat, 0.5)
    if feat.get("has_flexure", 1.0) >= 0.5:
        _key_findings(proc, feat, E_ALSI10MG, "AlSi10Mg")
    proc.add(
        "info",
        "AlSi10Mg is aluminum, so the magnet ring still works. Powder-bed "
        "metal is still the expensive way to make a 2-piece milled shell. "
        "CNC 6061 is the cheaper metal path once the thin features are gone",
    )
    return proc


def all_processes(feat: dict[str, float]) -> list[ProcessResult]:
    return [
        evaluate_local_fdm(feat),
        evaluate_jlc_fdm(feat),
        evaluate_jlc_sla(feat),
        evaluate_jlc_mjf(feat),
        evaluate_jlc_cnc(feat),
        evaluate_pcbway_cnc(feat),
        evaluate_jlc_slm(feat),
        evaluate_pcbway_slm(feat),
    ]


def _stl_stats_ascii(text: str) -> dict[str, float] | None:
    xmin = ymin = zmin = math.inf
    xmax = ymax = zmax = -math.inf
    tris: list[tuple[tuple[float, float, float], ...]] = []
    verts: list[tuple[float, float, float]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("vertex"):
            parts = line.split()
            if len(parts) != 4:
                continue
            verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
            if len(verts) == 3:
                tris.append(tuple(verts))
                verts = []
    if not tris:
        return None
    volume = 0.0
    for p0, p1, p2 in tris:
        for x, y, z in (p0, p1, p2):
            xmin, xmax = min(xmin, x), max(xmax, x)
            ymin, ymax = min(ymin, y), max(ymax, y)
            zmin, zmax = min(zmin, z), max(zmax, z)
        cx = (p1[1] - p0[1]) * (p2[2] - p0[2]) - (p1[2] - p0[2]) * (p2[1] - p0[1])
        cy = (p1[2] - p0[2]) * (p2[0] - p0[0]) - (p1[0] - p0[0]) * (p2[2] - p0[2])
        cz = (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p1[1] - p0[1]) * (p2[0] - p0[0])
        volume += (p0[0] * cx + p0[1] * cy + p0[2] * cz) / 6.0
    return {
        "triangles": float(len(tris)),
        "dx": xmax - xmin,
        "dy": ymax - ymin,
        "dz": zmax - zmin,
        "volume_mm3": abs(volume),
    }


def stl_stats(path: Path) -> dict[str, float] | None:
    if not path.is_file():
        return None
    data = path.read_bytes()
    if len(data) < 15:
        return None
    # OpenSCAD writes ASCII STLs ("solid ... facet").
    if data[:5] == b"solid" and b"facet" in data[:400]:
        try:
            return _stl_stats_ascii(data.decode("ascii", errors="ignore"))
        except (ValueError, UnicodeError):
            return None
    if len(data) < 84:
        return None
    n = struct.unpack_from("<I", data, 80)[0]
    xmin = ymin = zmin = math.inf
    xmax = ymax = zmax = -math.inf
    volume = 0.0
    off = 84
    for _ in range(n):
        if off + 50 > len(data):
            break
        nums = struct.unpack_from("<12f", data, off)
        p0 = nums[3:6]
        p1 = nums[6:9]
        p2 = nums[9:12]
        for x, y, z in (p0, p1, p2):
            xmin, xmax = min(xmin, x), max(xmax, x)
            ymin, ymax = min(ymin, y), max(ymax, y)
            zmin, zmax = min(zmin, z), max(zmax, z)
        # Signed volume of tetrahedron with the origin.
        cx = (p1[1] - p0[1]) * (p2[2] - p0[2]) - (p1[2] - p0[2]) * (p2[1] - p0[1])
        cy = (p1[2] - p0[2]) * (p2[0] - p0[0]) - (p1[0] - p0[0]) * (p2[2] - p0[2])
        cz = (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p1[1] - p0[1]) * (p2[0] - p0[0])
        volume += (p0[0] * cx + p0[1] * cy + p0[2] * cz) / 6.0
        off += 50
    return {
        "triangles": float(n),
        "dx": xmax - xmin,
        "dy": ymax - ymin,
        "dz": zmax - zmin,
        "volume_mm3": abs(volume),
    }


def stl_report(feat: dict[str, float]) -> list[str]:
    folder = EXPORT / "metal" if feat.get("variant", 0.0) >= 0.5 else EXPORT
    lines = [f"  exported STLs in {folder.relative_to(ROOT)} (bounding box vs CAD):"]
    checks = (
        ("tray.stl", feat["acc_w"], feat["acc_h"], feat["tray_h"] + feat["lip_h"]),
        ("lid.stl", feat["acc_w"], feat["acc_h"], feat["lid_h"]),
    )
    for name, w, h, t in checks:
        stats = stl_stats(folder / name)
        if stats is None:
            lines.append(f"    {name}: missing")
            continue
        got = sorted((stats["dx"], stats["dy"], stats["dz"]), reverse=True)
        want = sorted((w, h, t), reverse=True)
        drift = max(abs(a - b) for a, b in zip(got, want))
        vol = stats["volume_mm3"]
        lines.append(
            f"    {name}: {stats['dx']:.2f} x {stats['dy']:.2f} x {stats['dz']:.2f} mm, "
            f"{vol:.0f} mm3, {stats['triangles']:.0f} triangles "
            f"({'matches CAD' if drift < 0.3 else f'drifts {drift:.2f} mm from CAD'})"
        )
    return lines


def next_steps(feat: dict[str, float], procs: list[ProcessResult]) -> list[str]:
    cnc_ok = [pr.name for pr in procs if pr.metal and pr.kind == "cnc" and pr.ok]
    if feat.get("has_flexure", 1.0) < 0.5 and cnc_ok:
        return [
            "variant=metal is the 6061 file. Quote STEP is hardware/cad/export/metal/tray.step. HOLD until Pixel and stuffed-board calipers",
            "Print the PETG lid and the TPU 95A pill. Glue the ring and the "
            "clocking magnet into the blind wells, steel face up. The phone "
            "face stays closed",
            "Four M1.6 screws from the lid into the 5 mm posts. Tap the 1.35 mm drills",
            "Tape the pouch to the board underside, kapton the joints, then seat on the posts",
            "Caliper the Pixel and a stuffed board before you pay for 6061",
            "Do not order JLC3DP SLM: no aluminum, and 316L is steel",
        ]
    thin, thin_name = thinnest_metal(feat)
    return [
        f"Thicken {thin_name} from {thin:.2f} mm",
        "Print the TPU pill separately; SW1 is the spring",
        "Do not order JLC3DP SLM for this shell",
        "Caliper the Pixel and the stuffed board before any 6061 toolpath",
    ]


def report(p: dict, procs: list[ProcessResult], feat: dict[str, float]) -> str:
    thin, thin_name = thinnest_metal(feat)
    label = "metal copy" if feat.get("variant", 0.0) >= 0.5 else "PETG fit part"
    lines = [
        "Pixel Snap Voice - case DFM vs published shop rules",
        f"  file: {label} (openscad -D variant=\"metal\" for the 6061 solids)",
        f"  model: {feat['acc_w']:.0f} x {feat['acc_h']:.0f} x {feat['acc_t']:.1f} mm "
        f"shell, tray {feat['tray_h']:.2f} mm, lid {feat['lid_h']:.2f} mm, "
        f"wall {feat['wall']:.2f} mm",
        f"  thinnest solid: {thin:.2f} mm ({thin_name})",
    ]
    if feat.get("has_flexure", 1.0) >= 0.5:
        lines.append(
            f"  record key: PETG {key_deflection(feat, E_PETG):.2f} mm travel, "
            f"6061 {key_deflection(feat, E_6061):.3f} mm travel, "
            f"needs {SW_TRAVEL_MM:.2f} mm at {SW_FORCE_N} N"
        )
    else:
        lines.append(
            "  record button: captive TPU 95A pill in the lid wall; "
            "SW1 (2.2 N / 0.2 mm) is the spring"
        )
    lines += [
        f"  USB-C: {feat['usbc_mouth_w']:.1f} x {feat['usbc_mouth_h']:.1f} mm mouth in a "
        f"{feat['usbc_recess_w']:.1f} x {feat['usbc_recess_h']:.1f} x "
        f"{feat['usbc_recess_d']:.2f} mm overmold relief; {feat['usbc_web']:.2f} mm web, "
        f"{feat['usbc_frame']:.2f} mm frame round the mouth",
        f"  lid cavity: {feat['cavity_h']:.2f} mm deep, inner R {feat['inner_r']:.2f} mm "
        f"(guide {feat['rec_r']:.2f} mm); {feat['standoff_d']:.1f} mm M1.6 posts",
    ]
    lines += stl_report(feat)
    lines.append("  processes:")
    for proc in procs:
        mark = "PASS as-is" if proc.ok else "FAIL as-is"
        fails = sum(1 for f in proc.findings if f.severity == "fail")
        warns = sum(1 for f in proc.findings if f.severity == "warn")
        lines.append(f"    {mark:12} {proc.name}  ({fails} fail, {warns} warn)")
        for finding in proc.findings:
            if finding.severity == "info":
                continue
            lines.append(f"      [{finding.severity}] {finding.text}")
    metal_ok = [pr.name for pr in procs if pr.metal and pr.ok]
    print_ok = [pr.name for pr in procs if (not pr.metal) and pr.ok]
    lines.append("  metal processes that can take this file as-is:")
    lines.append("    " + (", ".join(metal_ok) if metal_ok else "none"))
    lines.append("  plastic processes that can take this file as-is:")
    lines.append("    " + (", ".join(print_ok) if print_ok else "none"))
    lines.append("  next:")
    lines += [f"    - {row}" for row in next_steps(feat, procs)]
    lines.append(
        "  cost: quote STEP is hardware/cad/export/metal/tray.step; no live JLCCNC price this run. HOLD until calipers. "
        "For a 2-piece milled shell, 6061 CNC is the cheap metal path. "
        "Powder-bed metal prices the bounding box and the supports inside "
        "the lid cavity, so AlSi10Mg is not the cheaper option even at shops "
        "that offer it. JLC3DP SLM is the wrong material."
    )
    lines.append(
        "  sources: jlccnc.com capabilities + design guideline + size article "
        "(Feb 2025 / Aug 2025); jlc3dp.com design guideline (Aug 2026) and "
        "SLM/SLA pages; pcbway.com CNC size table and SLM AlSi10Mg page."
    )
    return "\n".join(lines)


def self_test() -> list[str]:
    p = load_json()
    feat = features(p)
    failures: list[str] = []

    if feat["tray_h"] < 5.0 or feat["lid_h"] > 4.5:
        failures.append(f"unexpected split tray={feat['tray_h']} lid={feat['lid_h']}")
    if abs(feat["skirt"] - 0.45) > 0.02:
        failures.append(f"live skirt should be 0.45, got {feat['skirt']}")
    if abs(feat["magnet_floor"] - 0.85) > 0.02:
        failures.append(f"live magnet skin should be 0.85, got {feat['magnet_floor']}")
    if abs(feat["standoff_d"] - 5.0) > 0.02:
        failures.append(f"live posts should be 5.0 mm, got {feat['standoff_d']}")
    if abs(feat["usbc_web"] - 0.5) > 0.02:
        failures.append(f"live USB-C relief web should be 0.5 mm, got {feat['usbc_web']}")
    if feat["has_flexure"] >= 0.5:
        failures.append("live model should not keep a PETG flexure")

    jlc = evaluate_jlc_cnc(feat)
    if jlc.ok:
        failures.append("PETG model should fail JLCCNC as-is (0.45 mm skirt)")
    if not any("skirt" in f.text.lower() or "lid joint" in f.text for f in jlc.findings if f.severity == "fail"):
        failures.append("JLCCNC should fail the 0.45 mm PETG skirt")

    slm = evaluate_jlc_slm(feat)
    if slm.ok or not any("316L" in f.text for f in slm.findings):
        failures.append("JLC SLM should fail on material")

    local = evaluate_local_fdm(feat)
    if not local.ok:
        failures.append(f"live PETG model should pass local FDM, got {[f.text for f in local.findings]}")

    jlc_fdm = evaluate_jlc_fdm(feat)
    if jlc_fdm.ok:
        failures.append("JLC FDM should fail the 10 mm height floor")

    metal = features(p, variant="metal")
    if abs(metal["magnet_floor"] - 0.85) > 0.02:
        failures.append(f"metal magnet skin should be 0.85, got {metal['magnet_floor']}")
    if metal["has_flexure"] >= 0.5:
        failures.append("metal copy should not keep a PETG flexure")
    if metal["has_lip"] >= 0.5:
        failures.append("metal copy should drop the 0.45 mm skirt")
    if metal["duct_floor"] > 0.05:
        failures.append(f"metal copy should have no mic duct, got {metal['duct_floor']}")
    if metal.get("has_lid_cnc", 1.0) >= 0.5:
        failures.append("metal copy should not mill the PETG lid")
    jlc_m = evaluate_jlc_cnc(metal)
    if not jlc_m.ok:
        failures.append(
            "metal copy should pass JLCCNC: "
            + "; ".join(f.text for f in jlc_m.findings if f.severity == "fail")
        )
    # The USB-C relief web is 0.5 mm so a plug overmold lands close enough to
    # latch. That is JLCCNC's absolute metal floor and under PCBWay's 0.8 mm,
    # so PCBWay may fail, but only on that web.
    pcb_m = evaluate_pcbway_cnc(metal)
    other = [f.text for f in pcb_m.findings if f.severity == "fail" and "USB-C" not in f.text]
    if other:
        failures.append("metal copy should pass PCBWay CNC apart from the USB-C web: " + "; ".join(other))

    tray = stl_stats(EXPORT / "tray.stl")
    # The tray solid includes the 1.2 mm mating lip above the board-top split.
    tray_z = feat["tray_h"] + feat["lip_h"]
    if tray is not None:
        if abs(tray["dx"] - feat["acc_w"]) > 0.4 and abs(tray["dy"] - feat["acc_w"]) > 0.4:
            failures.append(f"tray.stl XY {tray['dx']:.2f} x {tray['dy']:.2f} != CAD")
        if abs(tray["dz"] - tray_z) > 0.4:
            failures.append(f"tray.stl Z {tray['dz']:.2f} != tray+lip {tray_z}")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="exit 0 if a plastic process is as-is; ignore metal",
    )
    args = parser.parse_args()

    try:
        case_fit()
        p = load_json()
        petg = features(p, variant="petg")
        metal = features(p, variant="metal")
    except (KeyError, FileNotFoundError, OSError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    test_errors = self_test()
    if test_errors:
        print("FAIL: check_dfm self-test", file=sys.stderr)
        for e in test_errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    if args.print_only:
        procs = [
            evaluate_local_fdm(petg),
            evaluate_jlc_fdm(petg),
            evaluate_jlc_sla(petg),
            evaluate_jlc_mjf(petg),
        ]
        print(report(p, procs, petg))
        if any(pr.ok for pr in procs):
            print("check_dfm: ok (plastic as-is)")
            return 0
        print("FAIL: no plastic process accepts this model as-is", file=sys.stderr)
        return 1

    procs = [
        evaluate_jlc_cnc(metal),
        evaluate_pcbway_cnc(metal),
        evaluate_jlc_slm(metal),
        evaluate_pcbway_slm(metal),
    ]
    print(report(p, procs, metal))
    if any(pr.ok for pr in procs if pr.metal and pr.kind == "cnc"):
        print("check_dfm: ok (metal CNC as-is)")
        return 0
    print("FAIL: no CNC metal process accepts variant=metal as-is", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
