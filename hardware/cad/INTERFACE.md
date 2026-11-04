# CAD ↔ PCB interface

One origin, one height map. If a number moves, change CAD and the board together. Do not leave a second copy only in KiCad.

## Origin

Phone-facing view of the accessory.

- **(0, 0)** = center of the magnet ring = Pixel Pixelsnap axis
- **+X** = phone right
- **+Y** = toward the camera bar (phone top)
- **+Z** = away from the glass (out of the phone)

The KiCad board origin matches. Edge.Cuts is the 59.6 × 85.6 mm PCB, not the 62 × 88 mm shell. The board fills the shell to exactly one 1.2 mm wall per side, so **the inner wall face is the board edge**. Nothing on the board may overhang Edge.Cuts.

## Height map (phone glass → outside)

| Layer | Z span (mm) | Notes |
| --- | --- | --- |
| Phone-side skin | 0.00–0.85 | Closed 6061 or PETG. No hole. This is the non-ferrous gap Apple uses when it measures accessory flux |
| Magnet ring | 0.85–2.35 | Blind annular well, 54.1 mm OD / 46 mm ID / 1.5 mm. Steel plate is already on the ring, facing the pouch |
| Clocking magnet | 0.85–2.35 | Blind 5 × 12 mm well on **−Y** (6 o'clock, long side toward the phone bottom), 1.2 mm of metal between it and the ring well |
| Air under cell | 2.35–2.50 | About 0.15 mm so the wrapped pouch is not a spacer |
| LiPo pouch | 2.50–6.05 | 3.3 mm Jauch pack + 0.15 mm tape + 0.1 mm swell, taped to **B.Cu** at (0, 0). Four 5.0 mm posts carry the board |
| PCB | 6.05–6.85 | 0.8 mm; **B.Cu** faces the pouch and the magnet backs. BT1 is on B.Cu west of J2, just north of the cell |
| Tray / lid split | 6.85 | `tray_h` is 6.85 mm. `lid_h` stays 3.80 mm |
| Joint | 6.85–8.20 | PETG: 0.6 mm tray lip inside a 0.45 mm lid skirt. Metal tray has no lip; screws locate the plastic lid |
| Tall parts | 6.85–9.25 | Module 2.4 mm, 0.8 mm SD NAND on **F.Cu**. In the lid |
| USB-C (J2) | 5.29–8.45 | HRO TYPE-C-31-M-13C, mid-mount in a 9.24 × 6.54 mm board slot: shell 1.60 above F.Cu, 0.76 below B.Cu. Mouth centre z = 6.87, on the tray / lid seam. 1.0 mm under the lid ceiling |
| USB-C wall mouth | 5.02–8.72 | 9.5 × 3.7 mm round-ended, through the −Y end wall, split across tray and lid |
| USB-C overmold relief | 3.52–10.22 | 12.8 × 6.7 mm, r 1.0, 0.7 mm deep into the 1.2 mm wall: 0.5 mm web, 0.43 mm ledge under the lid top |
| Back shell | 9.45–10.65 | 1.2 mm natural translucent PETG (`shell_back`). Flat top. Wave engraving into the skin, clipped off the IPEX well and bosses. D1 and D2 read through this lid |

Envelope budget is **10.65 mm**. The DigiKey pack is 0.1 mm thicker than the old 3.2 mm cell, so the tray grew with it. The lid cavity over the board is still 2.60 mm.

The tray floor is 2.35 mm, with wells milled from the inside down to the 0.85 mm skin. The outer wall is 1.2 mm up to the lid split, and four 5.0 mm M1.6 posts stand at the hole centres. There is no pouch pocket, no pigtail channel, and no lid clip. Glue holds the magnets. A clamp plate would sit in the 0.15 mm air under the pouch.

MK1's bottom-port NPTH is at (27.50, 16.32) on B.Cu. A rib under that hole stops 0.40 mm short of the board. A foam frame sits in the gap (land about 3.6 × 6.0 mm, 2 mm hole, 0.8 mm closed-cell compressed to 0.40 mm). A 3.4 × 3.6 mm pocket in the rib top holds a 3 mm mesh disk on a shoulder 0.80 mm below the land. Three 0.60 mm holes, 1.10 mm apart, pass through the phone-right wall into that pocket, inside a 4.2 × 1.8 mm recess 0.35 mm deep. The pouch ends at x = 25.75, so the land cannot grow inboard of x = 26.15. MK1 is on F.Cu. A port that faces the glass muffles recordings.

## XY locations (magnet-centered)

Edge features are the wall or board edge. The PCB is 59.6 × 85.6 mm, so its long edges are ±29.8 mm and its short edges are ±42.8 mm. The case outer is ±31 / ±44 mm.

The official board is `hardware/kicad/recorder/recorder.kicad_pcb`. Footprint XY lives in `hardware/kicad/recorder/placement.json` on this 59.6 × 85.6 mm outline. `check_envelope.py` twins MK1, SW1, J2, BT1 and the keepouts below to that file.

The table below is the CAD wall-cut contract from `params.json`. Change the case cuts when you move a part or caliper a phone and a stuffed board.

| Feature | X (mm) | Y (mm) | Max Z above PCB / notes |
| --- | --- | --- | --- |
| USB-C (J2) | +7.0 | −38.1 (face on −42.8) | HRO TYPE-C-31-M-13C (C2848620), rot 180°, mouth −Y. Shell 8.94 × 3.16 mm, face flush with the board edge = inner wall face. Wall mouth 9.5 × 3.7 mm (x 2.25–11.75) in a 12.8 × 6.7 mm overmold relief (x 0.6–13.4), 0.5 mm web. USB-IF max overmold 12.35 × 6.5 mm; a plug is ~6.65 mm overmold-to-tip against a 6.20 mm shell, so the overmold must land within ~0.5 mm of the face. Nothing in the tray under the slot |
| Mic port (wall) | +31.0 (phone-right long wall) | +16.32 | Three 0.60 mm holes at 1.10 mm pitch, in a 4.2 × 1.8 mm recess. Foam land and mesh pocket are inside the tray, below the seam |
| Mic capsule (MK1) | +27.5 | +17.0 | IM73A135 on **F.Cu**, rot 90°. Bottom-port NPTH is at (27.50, 16.32) on **B.Cu**. Port must not face glass |
| Record pill (wall) | −31.0 (phone-left long wall) | +12.0 | Captive TPU 95A in the lid. Flush 10 × 3.2 mm rounded bezel, 0.65 mm proud press pad. Left side when the accessory is snapped on the phone. Install from inside |
| Button (SW1) | −27.1 | +12.0 | Side-actuated Panasonic EVQP7C01P, rot 270° so the actuator faces the phone-left wall. Tip at x = −29.2, 0.6 mm inside the board edge. The switch is the spring |
| LED (D1, D2) | ≈ −29 / phone-left wall | +18.0 / charger is the phone-bottom end | Face the lid. No side windows. Lid is natural translucent PETG |
| SD NAND (J3) | −22.0 | −18.0 | MKDV4GCL-ABB, 8.0 × 6.0 mm LGA-8 on F.Cu. No wall slot |
| Side ridges | ±31.0 (both long walls, tray and lid) | skip pill and mic | 0.35 mm × 0.6 mm flutes at 1.6 mm pitch, tilted 18° from vertical. Same cut on both halves so they read as one strip when closed |
| Lid wave art | ±18.0 | 0.0 | Two foci, concentric rings that run off the lid. 0.35 mm into `shell_back`. Clipped off the IPEX well and the four boss footprints |
| IPEX well | +17.9 | −13.0 | 7.0 mm well, 0.85 mm into the 1.2 mm lid skin over U1’s W.FL / MHF III jack. Leaves 0.35 mm of PETG. Print the lid outer-face down so that skin is the first layer |
| Antenna tape | −2.0 | −33.0 | 30 × 5 mm mark, 0.2 mm into the inner ceiling, phone-bottom end, long axis along +X. Matches Inventek B24P-W. Do not enlarge the IPEX well. Clear of U1, J2, the button, and the bosses |
| Battery pads (BT1) | −17.0 | +35.0 | Two flat **B.Cu** pads for the pouch pigtail, west of J2 and just north of the cell. Pad 1 VBAT (west), pad 2 GND. Tape the cell on and kapton the joints |
| LiPo pouch | 0.0 | 0.0 | Jauch LP305166JH pack, 66 × 51.5 × 3.3 mm, 1200 mAh min, taped to B.Cu. 70 mm leads. Clears the four posts by about 3.8 mm |
| MCU module (U1) | +14.0 | −18.0 | 2.4 mm; MINI-1U, IPEX toward the lid well. On F.Cu; may overlap the pouch in XY |
| Mounting posts | ±26.3 | ±39.3 | Four 5.0 mm cylinders. Lid is clearance plus a 3.2 mm outer CSK. Tray tap is 1.35 mm, 2.5 mm deep, and stops above the 2.35 mm inner floor. The 0.85 mm skin stays closed. No printed threads |

### Board keepouts the case sets

- **Pouch:** the cell is under B.Cu. F.Cu under the 51.5 × 66 mm outline at (0, 0) may take parts. Posts stay clear of that outline.
- **Lid standoffs:** nothing within 2 mm of a hole centre. `check_placement.py` already keeps courtyards 2.1 mm off.

### Recorder designators

These are the recorder project names. Do not keep the old generated-board map.

| Ref | What |
| --- | --- |
| J2 | USB-C receptacle (HRO TYPE-C-31-M-13C, C2848620) |
| J3 | MKDV4GCL-ABB 512 MB SD NAND |
| U8 | analog LDO (codec / mic) |
| VDD33 | MCU 3.3 V rail |
| U1 | ESP32-S3-MINI-1U |
| BT1 | Pouch pigtail solder pads on B.Cu at (−17, 35) |

Export KiCad STEP (`File → Export → STEP`) and import next to `case.scad` (OpenSCAD cannot import STEP; use the STL from `case.scad` plus the KiCad 3D view, or Fusion/Onshape for a boolean). `check_envelope.py` is the automated gate; a 3D collision pass is visual.

## PETG print fit on a Pixel 10

`case.scad` writes each part already in print orientation:

```bash
cd hardware/cad
openscad -D 'part="tray"' -o export/tray.stl case.scad
openscad -D 'part="lid"' -o export/lid.stl case.scad
openscad -D 'part="button"' -o export/button.stl case.scad
openscad -D 'part="pouch"' -o export/dummy_pouch.stl case.scad
openscad -o export/plate.stl case.scad    # tray + lid + TPU pill on one plate
# 6061 tray (blind magnet wells, no skirt). Lid stays PETG:
openscad -D 'variant="metal"' -D 'part="tray"' -o export/metal/tray.stl case.scad
openscad -D 'part="lid"' -o export/metal/lid.stl case.scad
# Worn-orientation STLs for the 6061 shots (metal tray, fn=96):
openscad -D 'variant="metal"' -D 'part="tray"' -D render_fn=96 -o ../../build/case-renders/tray_worn.stl case.scad
openscad -D 'part="lid_worn"' -D render_fn=96 -o ../../build/case-renders/lid_worn.stl case.scad
openscad -D 'part="button_worn"' -D render_fn=96 -o ../../build/case-renders/button_worn.stl case.scad
# Board GLB (from repo root; also writes build/product-renders/recorder.glb):
python ../../hardware/kicad/recorder/product_renders/export_board_3d.py
# One still per script. render_metal.py is the scene library, not a batch.
# blender --background --python renders/shells_inside.py    # empty interiors
# blender --background --python renders/shells_outside.py   # empty exteriors
# blender --background --python renders/exploded.py         # lid, PCB, pouch, magnets, tray
# blender --background --python renders/top.py              # closed stack, CSK screws, J2 at camera end
# blender --background --python renders/button.py           # TPU pill side
# blender --background --python renders/grille.py           # mic holes
# blender --background --python renders/tray_magnets.py     # tray wells with ring seated
# PNGs land in build/case-renders/case-6061-<name>.png
# Orbit the same closed case (GLB + HTML, no PNG render):
# blender --background --python export_case_viewer.py
# python -m http.server 8765 --directory ../../build/case-renders
# open http://127.0.0.1:8765/case-6061.html
# Lid in those shots is natural translucent PETG; the tray stays 6061.
# The board sits on the four posts. J2 is KiCad's USB-C STEP, facing
# the −Y wall mouth. U1 / J3 / MK1 / Y1 are boxes when KiCad has no STEP.
```

1. Print the tray and lid in PETG. Print the record pill in TPU 95A. The tray sits phone-face down. The lid sits outer-face down, with the cavity up. Printing the lid mating-face down makes the back skin one 57 × 83 mm bridge.
2. The ring well is 0.3 mm loose on the OD. Drop in the N52 ring, steel face up, and the clocking magnet in the −Y well. Glue those faces. Do not put tape between the magnets and the phone-side skin.
3. M1.6 screws from the lid. Lid holes are clearance (`hole_d` 1.7 mm) with a shallow CSK in the outer skin. Each tray post is a 1.35 mm **tap drill**, 2.5 mm deep, that stops above the 2.35 mm inner floor. The 0.85 mm skin stays closed — tap M1.6 in 6061; PETG takes a thread-former. Do not print threads. The metal copy has no mating lip, so the screws are what locate the lid. The phone face has no screw heads.
4. Drop the TPU pill into the lid from the inside before the board goes in. Solder the pigtail to B.Cu BT1, tape the cell to the board underside, wrap it in kapton including the face toward the magnets. Seat a dummy PCB (or the first fab) on the four posts. Confirm about 0.15 mm of air under the wrapped cell and that the lid closes flat.
5. Snap to the Pixel. Confirm:
   - camera bar not covered
   - a USB-C cable latches through the −Y wall mouth (try a slim and a fat overmold) and the plug misses the phone
   - mic port is three holes in a recess on the phone-right long edge, not against glass
   - the TPU pill clicks SW1 and the switch pushes it back out
   - the side ridges give enough grip to slide it off the ring
   - snap hold feels OK (add or remove tape shims)
   - D1 / D2 read through the natural PETG lid
   - IPEX well sits over U1 and the FPC mark is on the inner ceiling toward the phone-bottom end
6. Only then order SMT, or order PCB+SMT in parallel if this 3D check is clean and you accept a spin.

Assembly order: glue the ring and the clocking magnet into the wells, steel face up → TPU pill in the lid → tape the 2.4 GHz FPC onto the lid ceiling mark and route the W.FL / MHF III pigtail to the IPEX well → solder BT1, tape and kapton the pouch on B.Cu → PCB onto the four posts → mate the pigtail to U1. Close the lid. Screws from the lid into the tapped posts. No snap-fit this pass. Do not run Wi-Fi with the IPEX open.

Pixel body and Pixelsnap center stay the published defaults until you caliper a real phone. **Caliper before any 6061 toolpath.** Chassis is PETG first (`variant` default), then the 6061 copy (`-D variant="metal"`), never steel. The metal tray has blind wells and a closed 0.85 mm skin. Glue holds the magnets. The metal lid has no 0.45 mm skirt; four M1.6 screws locate it. Print `part="button"` in TPU 95A and drop it in from the inside. The quote STEP is `export/metal/tray.step` from `python hardware/cad/export_metal_step.py` (HOLD). Tap M1.6 after CNC. The lid stays PETG. `python hardware/cad/check_dfm.py` is the shop-rules gate.
