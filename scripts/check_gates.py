#!/usr/bin/env python3

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RECORDER = REPO / "hardware" / "kicad" / "recorder"
PCB = RECORDER / "recorder.kicad_pcb"
FAB = REPO / "hardware" / "kicad" / "fab"


def find_kicad_cli() -> Path | None:
    env = os.environ.get("KICAD_CLI")
    if env and Path(env).is_file():
        return Path(env)
    found = shutil.which("kicad-cli")
    if found:
        return Path(found)
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "KiCad" / "10.0" / "bin" / "kicad-cli.exe",
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "KiCad" / "10.0" / "bin" / "kicad-cli.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "KiCad" / "10.0" / "bin" / "kicad-cli.exe",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def run(args: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(args))
    subprocess.check_call(args, cwd=str(cwd or REPO))


def main() -> int:
    test = REPO / "build" / "host" / "Debug" / "recorder_test.exe"
    if not test.is_file():
        test = REPO / "build" / "host" / "recorder_test"
    if not test.is_file():
        run(["cmake", "-S", "sim/host", "-B", "build/host"])
        run(["cmake", "--build", "build/host"])
        test = REPO / "build" / "host" / "Debug" / "recorder_test.exe"
        if not test.is_file():
            test = REPO / "build" / "host" / "recorder_test"
    run([str(test)], cwd=test.parent)

    run([sys.executable, str(REPO / "hardware" / "cad" / "check_envelope.py")])
    run([sys.executable, str(RECORDER / "verify_schematic.py")])
    run([sys.executable, str(REPO / "hardware" / "kicad" / "check_kicad_format.py")])
    run([sys.executable, str(REPO / "hardware" / "kicad" / "check_drc.py")])
    run([sys.executable, str(REPO / "hardware" / "kicad" / "check_mcu.py")])
    run([sys.executable, str(REPO / "hardware" / "kicad" / "check_pins.py")])

    kicad = find_kicad_cli()
    if PCB.is_file() and kicad:
        FAB.mkdir(parents=True, exist_ok=True)
        run([str(kicad), "pcb", "export", "gerbers", "-o", str(FAB), str(PCB)])
        print("kicad-cli gerbers written to", FAB)
        print("check_gates: ok")
        return 0

    reasons = []
    if not PCB.is_file():
        reasons.append("recorder.kicad_pcb not on disk yet")
    if not kicad:
        reasons.append("kicad-cli not found")
    print("kicad-cli gerber export skipped (" + "; ".join(reasons) + ").")
    print("hardware/kicad/fab/ is a stand-in outline, not a JLCPCB upload.")
    print("check_gates: ok (do not send fab/ to a board house)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print("check_gates: FAIL", exc, file=sys.stderr)
        raise SystemExit(1)
