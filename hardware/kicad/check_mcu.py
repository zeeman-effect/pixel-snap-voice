#!/usr/bin/env python3
"""Fail if the MCU module fights v1 (USB recorder, no radio)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
PARAMS = json.loads((REPO / "hardware" / "cad" / "params.json").read_text(encoding="utf-8"))
RECORDER_MCU_SCH = HERE / "recorder" / "mcu_usb.kicad_sch"

# PCB-antenna SKU. Forbidden while Wi-Fi is out of scope.
PCB_ANTENNA_MARKERS = (
    "ESP32-S3-MINI-1-N8",
    "C2913206",
    "antenna DNP",
    "Antenna footprint unused",
)

SKIP_DIR_NAMES = frozenset(
    {
        "example_project",
        ".history",
        "build",
        ".git",
        ".audit",
        "__pycache__",
    }
)

SCAN_SUFFIXES = frozenset({".md", ".py", ".csv", ".json", ".defaults", ".c", ".h", ".kicad_sch"})
SCAN_NAMES = frozenset({"sdkconfig.defaults", "AGENTS.md", "README.md"})


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def skip(path: Path) -> bool:
    if any(part in SKIP_DIR_NAMES for part in path.parts):
        return True
    return False


def iter_scan_files() -> list[Path]:
    out: list[Path] = []
    roots = [
        REPO / "AGENTS.md",
        REPO / "README.md",
        REPO / "docs",
        REPO / "firmware",
        REPO / "hardware" / "cad",
        REPO / "hardware" / "kicad",
        REPO / "scripts",
    ]
    recorder = HERE / "recorder"
    if recorder.is_dir() and recorder not in roots:
        roots.append(recorder)
    for root in roots:
        if root.is_file():
            out.append(root)
            continue
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or skip(path):
                continue
            if path.name == "check_mcu.py":
                continue
            if path.suffix in SCAN_SUFFIXES or path.name in SCAN_NAMES:
                out.append(path)
    return out


def main() -> int:
    errors: list[str] = []
    mcu = PARAMS.get("mcu")
    if not isinstance(mcu, dict):
        errors.append("hardware/cad/params.json has no mcu object (U1 lives there)")
        print("check_mcu: FAIL")
        for e in errors:
            print(" ", e)
        return 1

    for key in (
        "family",
        "mpn",
        "lcsc",
        "footprint",
        "width_mm",
        "height_mm",
        "thickness_mm",
        "antenna",
        "antenna_used_v1",
        "wifi_v1",
    ):
        if key not in mcu:
            errors.append(f"params.json mcu missing {key}")

    if mcu.get("family") != "ESP32-S3":
        errors.append("mcu.family must stay ESP32-S3")
    if mcu.get("wifi_v1"):
        errors.append("mcu.wifi_v1 is true; v1 has Wi-Fi out of scope")
    if mcu.get("antenna_used_v1"):
        errors.append("mcu.antenna_used_v1 is true; v1 does not use a radio")
    if not mcu.get("wifi_v1") and mcu.get("antenna") == "pcb":
        errors.append("pcb-trace antenna module while Wi-Fi is out of scope; use MINI-1U (ipex) or a no-antenna part")
    if mcu.get("antenna") not in {"ipex", "none"}:
        errors.append(f"mcu.antenna {mcu.get('antenna')!r} is not ipex or none")
    if "MINI-1U" not in str(mcu.get("mpn", "")):
        errors.append(f"mcu.mpn {mcu.get('mpn')!r} is not a MINI-1U SKU")

    sch = RECORDER_MCU_SCH
    if not sch.is_file():
        errors.append("missing hardware/kicad/recorder/mcu_usb.kicad_sch")
    elif str(mcu.get("mpn", "")) not in sch.read_text(encoding="utf-8"):
        errors.append("recorder/mcu_usb.kicad_sch does not name mcu.mpn")

    defaults = (REPO / "firmware" / "sdkconfig.defaults").read_text(encoding="utf-8")
    if "CONFIG_ESP_WIFI_ENABLED=n" not in defaults:
        errors.append("firmware/sdkconfig.defaults does not set CONFIG_ESP_WIFI_ENABLED=n")
    if "CONFIG_BT_ENABLED=n" not in defaults:
        errors.append("firmware/sdkconfig.defaults does not set CONFIG_BT_ENABLED=n")

    for path in iter_scan_files():
        text = path.read_text(encoding="utf-8")
        for marker in PCB_ANTENNA_MARKERS:
            if marker in text:
                errors.append(f"{rel(path)} still has {marker!r}")

    if errors:
        print("check_mcu: FAIL")
        for e in errors:
            print(" ", e)
        return 1
    print(
        f"check_mcu: ok ({mcu['mpn']} {mcu['width_mm']}x{mcu['height_mm']} mm, "
        f"antenna={mcu['antenna']}, wifi_v1={mcu['wifi_v1']})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
