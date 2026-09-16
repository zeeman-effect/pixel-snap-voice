#!/usr/bin/env python
"""Export the recorder board to STEP and GLB for the Blender product path.

Reads recorder.kicad_pcb only. Does not write the board. Run while KiCad is
open is fine as long as you want the last saved file, not an unsaved editor.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
PCB = REPO / "hardware" / "kicad" / "recorder" / "recorder.kicad_pcb"
OUT = REPO / "build" / "product-renders"


def kicad_cli() -> Path:
    env = os.environ.get("KICAD_CLI")
    if env:
        return Path(env)
    found = shutil.which("kicad-cli")
    if found:
        return Path(found)
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "KiCad" / "10.0" / "bin" / "kicad-cli.exe"
    prog = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "KiCad" / "10.0" / "bin" / "kicad-cli.exe"
    for candidate in (local, prog):
        if candidate.is_file():
            return candidate
    raise SystemExit("kicad-cli not found")


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cli = str(kicad_cli())
    step = OUT / "recorder.step"
    glb = OUT / "recorder.glb"
    common = [cli, "pcb", "export"]
    shared = ["--force", "--no-dnp", "--subst-models", "--cut-vias-in-body"]
    run(common + ["step", "--output", str(step), *shared, str(PCB)])
    run(
        common
        + [
            "glb",
            "--output",
            str(glb),
            *shared,
            "--include-tracks",
            "--include-pads",
            "--include-zones",
            "--include-silkscreen",
            "--include-soldermask",
            str(PCB),
        ]
    )
    print("wrote", step, "bytes", step.stat().st_size)
    print("wrote", glb, "bytes", glb.stat().st_size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
