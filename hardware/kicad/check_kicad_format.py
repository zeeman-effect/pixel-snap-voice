#!/usr/bin/env python3
"""KiCad 10 format gate for the official recorder project."""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RECORDER = HERE / "recorder"

# KiCad 10 file versions (copied from the old generator FORMAT).
SCH_VER = 20260306
PCB_VER = 20260206
GEN_VER = "10.0"

OFFICIAL_SCH = [
    "recorder.kicad_sch",
    "mcu_usb.kicad_sch",
    "audio.kicad_sch",
    "power.kicad_sch",
    "io.kicad_sch",
]


def field_int(text: str, name: str) -> int | None:
    m = re.search(rf"\({name}\s+(\d+)\)", text)
    return int(m.group(1)) if m else None


def field_str(text: str, name: str) -> str | None:
    m = re.search(rf'\({name}\s+"([^"]+)"\)', text)
    return m.group(1) if m else None


def main() -> int:
    errors: list[str] = []
    for name in OFFICIAL_SCH:
        path = RECORDER / name
        if not path.is_file():
            errors.append(f"missing recorder/{name}")
            continue
        text = path.read_text(encoding="utf-8")
        ver = field_int(text, "version")
        gen = field_str(text, "generator_version")
        if ver != SCH_VER:
            errors.append(f"recorder/{name} version {ver} != {SCH_VER}")
        if gen != GEN_VER:
            errors.append(f"recorder/{name} generator_version {gen!r} != {GEN_VER!r}")
        if "(embedded_fonts" not in text:
            errors.append(f"recorder/{name} missing embedded_fonts")

    pcb = RECORDER / "recorder.kicad_pcb"
    if pcb.is_file():
        text = pcb.read_text(encoding="utf-8")
        ver = field_int(text, "version")
        gen = field_str(text, "generator_version")
        if ver != PCB_VER:
            errors.append(f"recorder/recorder.kicad_pcb version {ver} != {PCB_VER}")
        if gen != GEN_VER:
            errors.append(f"recorder/recorder.kicad_pcb generator_version {gen!r} != {GEN_VER!r}")

    if errors:
        print("check_kicad_format: FAIL")
        for e in errors:
            print(" ", e)
        return 1
    extra = " + recorder.kicad_pcb" if pcb.is_file() else " (pcb not on disk yet)"
    print(f"check_kicad_format: ok (5 recorder sheets{extra})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
