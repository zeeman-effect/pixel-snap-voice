#!/usr/bin/env python3
"""Fail if the MCU module fights the MINI-1U radio (IPEX lid FPC, no PCB antenna)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
PARAMS = json.loads((REPO / "hardware" / "cad" / "params.json").read_text(encoding="utf-8"))
RECORDER_MCU_SCH = HERE / "recorder" / "mcu_usb.kicad_sch"

# PCB-antenna SKU. Forbidden: that antenna sits next to the steel ring.
PCB_ANTENNA_MARKERS = (
    "ESP32-S3-MINI-1-N8",
    "C2913206",
    "antenna DNP",
    "Antenna footprint unused",
)

# Old buy text that treats first-gen U.FL as the MINI-1U jack. Historical
# "do not buy U.FL" wording is fine; these phrases are the product connector.
WRONG_JACK_PHRASES = (
    "MHF1 / U.FL",
    "MHF1 pigtail",
    "lid MHF1",
    "Mate an MHF1",
    "mate the MHF1",
    "mated MHF1",
    "antenna.connector must be MHF1",
    "U.FL on the MINI-1U",
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

    ant = PARAMS.get("antenna")
    if not isinstance(ant, dict):
        errors.append("params.json has no antenna object (lid IPEX well)")
    else:
        if ant.get("kind") != "ipex_fpc":
            errors.append("antenna.kind must be ipex_fpc")
        # MINI-1U jack is Hirose W.FL / I-PEX MHF III, not first-gen U.FL / MHF1.
        connector = str(ant.get("connector", "")).strip()
        wfl_names = {"W.FL", "WFL", "MHF3", "MHF III", "MHFIII"}
        if connector not in wfl_names:
            errors.append(
                "antenna.connector must be W.FL (I-PEX MHF III on the MINI-1U; "
                "not first-gen U.FL / MHF1)"
            )

    if mcu.get("family") != "ESP32-S3":
        errors.append("mcu.family must stay ESP32-S3")
    if not mcu.get("wifi_v1"):
        errors.append("mcu.wifi_v1 is false; Wi-Fi share is in scope")
    if not mcu.get("antenna_used_v1"):
        errors.append("mcu.antenna_used_v1 is false; the IPEX pigtail is in use")
    if mcu.get("antenna") != "ipex":
        errors.append(
            f"mcu.antenna {mcu.get('antenna')!r} must be ipex; "
            "a PCB-antenna module sits next to the steel ring"
        )
    if "MINI-1U" not in str(mcu.get("mpn", "")):
        errors.append(f"mcu.mpn {mcu.get('mpn')!r} is not a MINI-1U SKU")

    sch = RECORDER_MCU_SCH
    if not sch.is_file():
        errors.append("missing hardware/kicad/recorder/mcu_usb.kicad_sch")
    elif str(mcu.get("mpn", "")) not in sch.read_text(encoding="utf-8"):
        errors.append("recorder/mcu_usb.kicad_sch does not name mcu.mpn")

    defaults = (REPO / "firmware" / "sdkconfig.defaults").read_text(encoding="utf-8")
    if "CONFIG_ESP_WIFI_ENABLED=y" not in defaults:
        errors.append("firmware/sdkconfig.defaults does not set CONFIG_ESP_WIFI_ENABLED=y")
    if "CONFIG_ESP_WIFI_ENABLED=n" in defaults:
        errors.append("firmware/sdkconfig.defaults still disables Wi-Fi")
    if "CONFIG_BT_ENABLED=n" not in defaults:
        errors.append("firmware/sdkconfig.defaults does not set CONFIG_BT_ENABLED=n")
    if "CONFIG_BT_ENABLED=y" in defaults:
        errors.append("firmware/sdkconfig.defaults must leave Bluetooth off")

    kconfig = (REPO / "firmware" / "main" / "Kconfig.projbuild").read_text(encoding="utf-8")
    if "config PSV_WIFI_SHARE" not in kconfig:
        errors.append("firmware/main/Kconfig.projbuild has no PSV_WIFI_SHARE")

    for path in iter_scan_files():
        text = path.read_text(encoding="utf-8")
        for marker in PCB_ANTENNA_MARKERS:
            if marker in text:
                errors.append(f"{rel(path)} still has {marker!r}")
        for phrase in WRONG_JACK_PHRASES:
            if phrase in text:
                errors.append(
                    f"{rel(path)} still names {phrase!r} as the product RF jack; "
                    "MINI-1U is W.FL / I-PEX MHF III"
                )

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
