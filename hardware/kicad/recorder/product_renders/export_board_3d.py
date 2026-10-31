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


def run(cmd: list[str], out: Path) -> None:
    """Run one export. kicad-cli 10 exits 2 when a 3D model file is missing
    but still writes the file; build_product_scene.py boxes those parts, so a
    fresh output with missing-model warnings is fine. No output is not."""
    print("+", " ".join(cmd), flush=True)
    out.unlink(missing_ok=True)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        if not out.is_file():
            raise SystemExit(f"kicad-cli exited {result.returncode} and wrote no {out.name}")
        print(f"kicad-cli exited {result.returncode} (missing 3D models); kept {out.name}", flush=True)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cli = str(kicad_cli())
    # A Windows kicad-cli run outside the KiCad GUI does not always resolve
    # this variable, and then every library model reads as missing.
    models = Path(cli).parents[1] / "share" / "kicad" / "3dmodels"
    if models.is_dir():
        os.environ.setdefault("KICAD10_3DMODEL_DIR", str(models))
    step = OUT / "recorder.step"
    glb = OUT / "recorder.glb"
    common = [cli, "pcb", "export"]
    shared = ["--force", "--no-dnp", "--subst-models", "--cut-vias-in-body"]
    run(common + ["step", "--output", str(step), *shared, str(PCB)], step)
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
        ],
        glb,
    )
    case_glb = REPO / "build" / "case-renders" / "board.glb"
    case_glb.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(glb, case_glb)
    print("wrote", step, "bytes", step.stat().st_size)
    print("wrote", glb, "bytes", glb.stat().st_size)
    print("wrote", case_glb, "bytes", case_glb.stat().st_size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
