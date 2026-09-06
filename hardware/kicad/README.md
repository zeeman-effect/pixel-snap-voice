# KiCad — custom slim PCB

4-layer **0.8 mm**, ENIG. Origin = magnet-ring center (same as CAD). USB is full speed and deliberately **not** impedance controlled — see [Stackup](#stackup-jlc-4-layer-08-mm).

Two trees only:

- **Product:** `recorder/` — schematic + PCB. Open `recorder.kicad_pro`.
- **Learning:** `example_project/` — hand-made KiCad 10 sandbox. Not product truth. Leave it alone unless you are in that lesson.

```bash
python hardware/kicad/recorder/generate_recorder.py
python hardware/kicad/recorder/verify_schematic.py
python hardware/kicad/recorder/route_pcb.py --planes-only   # needs pcbnew
python scripts/check_gates.py
```

`route_pcb.py` and `generate_pcb.py` need an interpreter that can `import pcbnew`. On Linux that is the system `python3`; on Windows use `%LOCALAPPDATA%\Programs\KiCad\10.0\bin\python.exe`.

`generate_recorder.py` overwrites the recorder sheets. It does not write `recorder.kicad_pcb`. `route_pcb.py --planes-only` loads that board and pours copper. It does not move parts. Close the recorder project in KiCad before running either script.

`generate_pcb.py` rebuilds the board from scratch and wipes copper. Run it only when you intend a placement reset, then pour and route again. `route_pcb.py` with no flag does the whole job: it clears copper, lays the planes, hand-routes the parts an autorouter cannot do (the USB-C escape, the D+/D− pair, the fine-pitch fanouts), locks them, hands the rest to freerouting over Specctra DSN/SES, then pours, stitches and repairs until `kicad-cli pcb drc` is clean. Footprint XY: [`recorder/placement.json`](recorder/placement.json). Keep it in sync with the board. CAD envelope is `hardware/cad/params.json` + `case.scad`. Those numbers can move when the case or board moves.

`check_gates.py` checks the files that are already on disk. It does not regenerate.

Sheets: `mcu_usb`, `audio`, `power`, `io` (global labels join them). Pin map: [`pinmap.md`](pinmap.md).

Before a fab upload, land patterns must be datasheet footprints, `kicad-cli pcb drc` must be clean, and `kicad-cli` must write `fab/` from `recorder.kicad_pcb`. `check_gates.py` now does the last two itself. SP1 is still an invented land pattern, so that first condition is not met yet.

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

USB pair: 0.20 mm traces on a 0.40 mm pitch, F.Cu over the solid In1 GND plane. **Not impedance controlled, and no controlled-impedance option needs ordering.** The ESP32-S3 USB peripheral is full speed only (12 Mbps, no high-speed PHY), and 90 Ω on this 0.1 mm top prepreg would need roughly 0.06 mm traces, half what a quick-turn fab will run. The geometry above lands near 75 Ω differential by first-order microstrip, which is fine at full-speed edge rates. If a later revision ever needs high-speed USB, thicken the top prepreg first.

The pair is long for USB — 45.8 mm on D+, 44.2 mm on D−, 1.65 mm skew (~11 ps). That is placement, not sloppiness: U1's USB pads sit on the module's top row, the far side of a 15.9 mm module from J2, and the castellations leave 0.05 mm between pads, so the pair has to go around the module rather than under it. It runs up the 3.3 mm channel between J1 and U1.

## Keepouts

- No tall parts on B.Cu (phone / shunt side)
- Mic on the right long edge, away from U4 / U5
- USB-C (**J2**) on the bottom short edge, offset +8 mm
- Analog island (U2, U8, MK1, Y1) off **VDD33**
- PA LC away from the magnet circle (comment layer)
- MINI-1U module (15.4 × 15.4 mm). No PCB-antenna keepout. IPEX unpopulated
- 4× M1.6 holes. No fiducials on this first pass.

Gerbers: `fab/` after `scripts/check_gates.py`, which runs `kicad-cli pcb drc` first and then writes the Gerbers, both drill files, the pick-and-place CSV and `recorder-jlc.zip` in one pass from `recorder.kicad_pcb`. Do not hand-export only part of that set: a drill file that does not match the copper is a scrap board.

Open `recorder/recorder.kicad_pro` in KiCad 10. ERC/DRC in KiCad is the last human glance. The Python checks are the repo gate.

U1 comes from `hardware/cad/params.json` `mcu`. Change the module there, then update the recorder schematic sources and regenerate the sheets.
