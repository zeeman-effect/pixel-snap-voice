# CAD envelope

OpenSCAD and `params.json` must stay twins. `params.json` and `params.scad` share the same Pixel 10 + magnet-ring numbers. Change a number in both files. `check_envelope.py` fails if they drift, if the accessory hits a keepout, if the 51.5 × 66 mm pouch outline hits a tray post, or if the pogo well XY drifts from `placement.json` J2. `check_dfm.py` asks whether JLCCNC, JLC3DP, or PCBWay can make the same solids as-is. Metal CNC is the tray only; the lid stays natural translucent PETG. The record button is a captive TPU 95A pill.

```bash
python hardware/cad/check_envelope.py
python hardware/cad/check_dfm.py --print-only   # local PETG
python hardware/cad/check_dfm.py                # 6061 copy (variant=metal)
openscad -D 'part="tray"' -o hardware/cad/export/tray.stl hardware/cad/case.scad
openscad -D 'part="lid"' -o hardware/cad/export/lid.stl hardware/cad/case.scad
openscad -D 'part="button"' -o hardware/cad/export/button.stl hardware/cad/case.scad
openscad -D 'part="pouch"' -o hardware/cad/export/dummy_pouch.stl hardware/cad/case.scad
openscad -D 'variant="metal"' -D 'part="tray"' -o hardware/cad/export/metal/tray.stl hardware/cad/case.scad
python hardware/cad/export_metal_step.py   # CSG + JLCCNC STEP. HOLD until Pixel calipers.
# One Cycles still at a time (scene library is render_metal.py):
blender --background --python hardware/cad/renders/shells_inside.py
blender --background --python hardware/cad/renders/shells_outside.py
blender --background --python hardware/cad/renders/exploded.py
blender --background --python hardware/cad/renders/top.py
blender --background --python hardware/cad/renders/button.py
blender --background --python hardware/cad/renders/grille.py
blender --background --python hardware/cad/renders/tray_magnets.py
```

## Current defaults (caliper before CNC)

| Item | Value |
| --- | --- |
| Pixel 10 body | 152.8 × 72.0 × 8.6 mm |
| Camera bar | 24 mm from top, full width (measure) |
| Pixelsnap center | 85 mm from top, 36 mm from left (measure) |
| Magnet ring | OD 54.1 / ID 46 / 1.5 mm N52, steel plate on the ring, plus a clocking magnet |
| Accessory | 62 × 88 × 10.65 mm |
| PCB | 59.6 × 85.6 × 0.8 mm, 4-layer |
| Tray | 0.85 mm closed skin, 2.35 mm inner floor, 1.2 mm wall, four 5.0 mm M1.6 posts |
| Lid | natural translucent PETG, IPEX well over U1, FPC tape mark toward the phone-bottom end (J2 is camera / phone-top) |

The magnet wells are blind and 0.3 mm loose on the ring OD. Glue the steel face; do not tape the phone side of the magnets. Default `variant` is the PETG fit part. `-D variant="metal"` is the 6061 tray. The lid is always PETG. Not steel.

Shared origin, heights, and the PETG-on-Pixel checklist: [`INTERFACE.md`](INTERFACE.md).

## Print checklist

`export/` STLs come from live `case.scad`. Print these before any Pixel snap check. This pass cannot print or snap for you.

- **PETG tray + lid.** `tray.stl` sits phone-face down. `lid.stl` is already outer-face down; leave it that way so the 0.35 mm IPEX skin is the first layers. Natural translucent PETG for the lid. Mating-face down turns the back skin into a 57 × 83 mm bridge.
- **TPU 95A pills.** Print several `button.stl` copies. The nub is meant to rest 0.1 mm on the SW1 actuator; a squashed first layer or a short nub will miss the switch.
- **Dummy pouch.** Print `dummy_pouch.stl` and stack it under a dummy board to check lid close before taping the Jauch cell.
- **Then, by hand:** glue the ring and clocking magnet steel-face up, drop a pill in from inside the lid, tape the FPC on the inner ceiling mark, mate the pigtail in the IPEX well, screw the lid on, snap it to a Pixel. Confirm the camera bar is clear, the magnetic cable seats, the mic holes are on the phone-left wall, the pill clicks and springs back, and the ridges are enough to slide it off. Caliper a real phone before any 6061 toolpath; do not treat the table above as measured.
