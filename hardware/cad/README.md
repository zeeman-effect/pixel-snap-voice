# CAD envelope

OpenSCAD and `params.json` must stay twins. `params.json` and `params.scad` share the same Pixel 10 + magnet-ring numbers. Change a number in both files. `check_envelope.py` fails if they drift or if the accessory hits a keepout.

```bash
python hardware/cad/check_envelope.py
openscad -o hardware/cad/case.stl hardware/cad/case.scad   # PETG
```

## Current defaults (caliper before CNC)

| Item | Value |
| --- | --- |
| Pixel 10 body | 152.8 × 72.0 × 8.6 mm |
| Camera bar | 24 mm from top, full width (measure) |
| Pixelsnap center | 85 mm from top, 36 mm from left (measure) |
| Magnet ring | OD 56 / ID 44 / 1.1 mm + 0.3 mm steel shunt |
| Accessory | 67 × 90 × 9 mm |
| PCB | 64 × 86 × 0.8 mm, 4-layer |

Print the magnet pocket slightly loose (`pocket_extra` in `case.scad`), shim, then tighten after the real ring arrives. Chassis is PETG first, 6061 later — not steel.

Shared origin, heights, and the PETG-on-Pixel checklist: [`INTERFACE.md`](INTERFACE.md).
