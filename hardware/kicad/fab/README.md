# Fab export

`python scripts/check_gates.py` writes this whole folder from `hardware/kicad/recorder/recorder.kicad_pcb`, in one pass, after running `kicad-cli pcb drc`. It needs `kicad-cli`: on Linux that is on PATH, on Windows it is `%LOCALAPPDATA%\Programs\KiCad\10.0\bin\kicad-cli.exe`.

Contents: Gerbers, PTH/NPTH Excellon drills and their map PDFs, `recorder-pos.csv` (pick and place), and `recorder-jlc.zip`. The zip holds the copper, mask, silk, outline and drills only — the Fab, Courtyard, Adhesive, Margin and User layers are internal documentation and JLCPCB should not see them. BOM/CPL sit one level up: `jlcpcb_bom.csv`, `jlcpcb_cpl.csv`.

Never hand-export part of this set. These files only mean anything together: an earlier version of the gate script refreshed the Gerbers but left the drill file at whatever date it was committed with, which described a board with none of its vias drilled.

JLC order: 4-layer, 0.8 mm, ENIG. **No controlled impedance** — USB here is full speed and the pair is deliberately uncontrolled. See `hardware/kicad/README.md`.
