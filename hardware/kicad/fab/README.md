# Fab export

`kicad-cli` writes this folder from `hardware/kicad/recorder/recorder.kicad_pcb`. On this machine the binary is `%LOCALAPPDATA%\Programs\KiCad\10.0\bin\kicad-cli.exe` (not on PATH). `python scripts/check_gates.py` finds that same path.

This folder has Gerbers, PTH/NPTH drills, and `recorder-jlc.zip`. BOM/CPL sit one level up: `jlcpcb_bom.csv`, `jlcpcb_cpl.csv`.

If the board is still unrouted, do not send this folder to a board house. Export again after routing and DRC.

JLC: 4-layer, 0.8 mm, ENIG, 90 ohm USB on the documented stackup.
