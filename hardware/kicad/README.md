# KiCad — custom slim PCB

4-layer **0.8 mm**, ENIG, USB 2.0 D+/D− ~90 Ω. Origin = magnet-ring center (same as CAD).

Two trees only:

- **Product:** `recorder/` — schematic + PCB. Open `recorder.kicad_pro`.
- **Learning:** `example_project/` — hand-made KiCad 10 sandbox. Not product truth. Leave it alone unless you are in that lesson.

```bash
python hardware/kicad/recorder/generate_recorder.py
python hardware/kicad/recorder/verify_schematic.py
/c/Users/zachr/AppData/Local/Programs/KiCad/10.0/bin/python.exe hardware/kicad/recorder/route_pcb.py --planes-only
python scripts/check_gates.py
```

`generate_recorder.py` overwrites the recorder sheets. It does not write `recorder.kicad_pcb`. `route_pcb.py --planes-only` loads that board and pours copper. It does not move parts. Close the recorder project in KiCad before running either script.

`generate_pcb.py` rebuilds the board from scratch and wipes copper. Run it only when you intend a placement reset, then pour and route again. The signal autoroute (same `route_pcb.py`, no flag) is experimental. Use it as a start if it helps, then fix what DRC says is wrong. Footprint XY: [`recorder/placement.json`](recorder/placement.json). Keep it in sync with the board. CAD envelope is `hardware/cad/params.json` + `case.scad`. Those numbers can move when the case or board moves.

`check_gates.py` checks the files that are already on disk. It does not regenerate.

Sheets: `mcu_usb`, `audio`, `power`, `io` (global labels join them). Pin map: [`pinmap.md`](pinmap.md).

Before a fab upload, land patterns must be datasheet footprints, `kicad-cli pcb drc` must be clean, and `kicad-cli` must write `fab/` from `recorder.kicad_pcb`. Until then, keep editing the board.

## Stackup (JLC 4-layer 0.8 mm)

| Layer | Role | Copper |
| --- | --- | --- |
| F.Cu | signals, tall parts (battery side) | 1 oz |
| prepreg | ~0.10 mm | |
| In1.Cu | GND plane | 0.5 oz |
| core | ~0.53 mm | |
| In2.Cu | **VDD33** pour | 0.5 oz |
| prepreg | ~0.10 mm | |
| B.Cu | GND, **flat toward the shunt / phone** | 1 oz |

USB pair: 0.20 mm width, 0.15 mm gap on F.Cu over In1 GND. Confirm with the JLC impedance calculator before SMT.

## Keepouts

- No tall parts on B.Cu (phone / shunt side)
- Mic on the right long edge, away from U4 / U5
- USB-C (**J2**) on the bottom short edge, offset +8 mm
- Analog island (U2, U8, MK1, Y1) off **VDD33**
- PA LC away from the magnet circle (comment layer)
- MINI-1U module (15.4 × 15.4 mm). No PCB-antenna keepout. IPEX unpopulated
- 4× M1.6 holes. No fiducials on this first pass.

Gerbers: `fab/` after `scripts/check_gates.py`. If the board is still unrouted, that folder is not a JLCPCB upload. Export again from `recorder/recorder.kicad_pcb` after routing and DRC.

Open `recorder/recorder.kicad_pro` in KiCad 10. ERC/DRC in KiCad is the last human glance. The Python checks are the repo gate.

U1 comes from `hardware/cad/params.json` `mcu`. Change the module there, then update the recorder schematic sources and regenerate the sheets.
