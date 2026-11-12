# Manufacturing

One-off / quick-turn. Prefer JLCPCB + LCSC Basic parts. Do not send Gerbers until ERC, DRC, envelope check, and `recorder_test` pass.

## PCB (Phase 1)

| Item | Default |
| --- | --- |
| Fab | JLCPCB (PCBWay is the backup) |
| Layers | 4 (F.Cu, In1.Cu, In2.Cu, B.Cu) |
| Thickness | 0.8 mm (`params.json`). 1.6 mm only if a later envelope check still passes |
| Finish | OSP, the cheapest flat finish. Not HASL: its solder domes are risky under U2's 0.4 mm pitch and the bottom-pad parts (U1, J3, MK1). ENIG also works but buys shelf life this one-off does not need; J2's contacts are on the part, not the board. OSP lasts ~6 months bare and weakens after reflow, so JLC assembles at once; solder the BT1 pigtail within a few weeks, with flux |
| Impedance | None. Do not order the controlled-impedance option. USB is full speed only, so D+/D− are a plain 0.2 mm pair on a 0.4 mm pitch over In1 GND (~75 Ω). Reasoning in `hardware/kicad/README.md` |
| Min trace / space | 0.15 mm. Inside standard capability, so no fine-line surcharge |
| Via | 0.6 mm pad on a 0.3 mm drill, one size everywhere. 0.3 mm is JLC's preferred hole, so no small-via surcharge — do not let a re-route drop below it |
| Silkscreen | Standard font, 1.0 mm characters on a 0.15 mm stroke. Not the high-precision option |
| Assembly | JLCPCB SMT for every surface-mount part. BT1 is pads only (no wave solder). No UART header |
| Panel | Single board is fine for a one-off |

Mic: keep the acoustic port on the board edge, away from U4/U5. Storage is a soldered 512 MB SD NAND (J3, MK MKDV4GCL-ABB, C7500178), not a card socket.

See [`hardware/kicad/README.md`](../hardware/kicad/README.md) for stackup and keepouts.

## Magnet array

Buy the **totalElement N52 ring** R54X46X15MMN52-5PK (54.1 × 46 × 1.5 mm, steel plate already glued on) and use the alignment magnet from the same pack. Do not CNC magnets, and do not add a second steel disc. The phone face is a closed 0.85 mm skin; the magnets drop into blind wells and are glued on the steel face. Cases and chargers do the same: a non-ferrous skin toward the phone, adhesive behind the array, no clamp plate. A clamp would sit in the air gap under the pouch.

## Plastic prototype (Phase 1 chassis)

- Local FDM PETG is the process the live `case.scad` is written for. `check_envelope.py` is the Pixel-fit gate. `python hardware/cad/check_dfm.py --print-only` is the shop-rules gate
- Print `hardware/cad/export/tray.stl` + `lid.stl` + `button.stl` (or `plate.stl`) and a 3.3 mm dummy pouch **before** SMT. Snap-check on the phone with the real ring. The lid has a local IPEX well and an FPC tape mark; mate the W.FL / MHF III pigtail only for Wi-Fi share tests. Steps: [`hardware/cad/INTERFACE.md`](../hardware/cad/INTERFACE.md)
- JLC3DP FDM will bounce this file: their FDM line wants parts at least 10 mm thick, and these halves are 6.85 mm and 3.80 mm. Use a local printer, not JLC's FDM queue
- JLC3DP SLA / MJF will also EQ or refuse the as-is file (0.45 mm lid skirt, 0.15 mm joint). Do not upload the PETG solids and hope. The TPU pill is a local 95A print.
- Print the magnet pocket slightly loose, shim with tape, then tighten after the real ring arrives

## Metal chassis (Phase 2) — HOLD

Do not send this tray to a CNC queue yet. Pixel 10 Pixelsnap and camera-bar numbers in `params.json` are published defaults. A stuffed-board stack has not been calipered. Those measurements do not exist in this repo. Do not invent them, and do not cut 6061 on the defaults.

- **Hold until a human measures** the list below, then updates `params.json` / `params.scad` / the PETG proto if the numbers move
- Quote file (not an order): `hardware/cad/export/metal/tray.step`. JLCCNC wants STEP. OpenSCAD 2021.01 only writes mesh; this STEP is a CadQuery B-rep rebuild of the live `openscad -D variant="metal" -D part="tray"` CSG (`python hardware/cad/export_metal_step.py`). FreeCAD is not installed here. Blender 5.2 cannot write STEP. The matching mesh is `hardware/cad/export/metal/tray.stl`
- **6061 tray only** at JLCCNC or PCBWay. `python hardware/cad/check_dfm.py` is green for those two CNC queues. Closed phone face, 0.85 mm skin over the magnet wells (JLCCNC's recommended metal wall is 0.8 mm; their absolute floor is 0.5 mm), four 5.0 mm posts. Glue the ring and the clocking magnet into the wells. No 0.45 mm skirt — four M1.6 screws locate the lid. Mic port is three 0.60 mm holes in a shallow recess in the tray wall, into a mesh pocket under a foam land. Do not mill a speaker grille or a battery fence
- **Lid stays natural translucent PETG.** Do not mill a metal lid. The record pill is TPU in that lid; SW1 is the spring
- **Tap M1.6 after CNC** in the 1.35 mm post drills (2.5 mm deep, above the 2.35 mm inner floor). Shops will not leave a finished thread in those holes. PETG takes a thread-former; 6061 gets a tap
- JLC3DP metal print is not a cheaper substitute. They only list 316L and titanium. 316L is steel and steals hold from the ring
- Kapton on the pouch face toward the ring. The steel plate is already on the magnet, facing the cell, not the phone
- Not steel, not 400-series stainless

### Human caliper list (no numbers until you measure)

Pixel 10, back glass up:

1. Body width, height, and thickness
2. Camera bar: distance from the top of the phone to the start of the bar, bar height, bar width, how far the bar stands proud of the back glass
3. Pixelsnap / magnet-ring center: from the top of the phone, and from the left long edge (repeat from the right to see if it is centered). CAD origin is this center

Stuffed board (PCB + pouch + kapton, then the PETG proto on the phone):

1. Board outline width, height, thickness
2. U1 height above F.Cu; J2 shell top above F.Cu (1.60 mm on paper), shell bottom below B.Cu (0.76 mm), and its front face vs the board edge (flush on paper)
3. Pouch width, height, thickness after tape and kapton; air under that wrap vs the tray floor
4. SW1 actuator tip to the phone-left board edge
5. MK1 sound-port hole to the phone-right board edge
6. Four post / hole positions vs the board corners
7. Closed PETG proto on the phone: camera bar still clear, ring on the Pixelsnap center, overall stack height, a USB-C cable latches through the wall mouth and the plug misses the phone

## Battery

Pouch is the Jauch **LP305166JH-PCM-2-WIRES-70MM** (DigiKey 13278052): 66 × 51.5 × 3.3 mm, 1200 mAh min, PCM, 70 mm leads. Tape to B.Cu at (0, 0), kapton-wrap, solder the leads to B.Cu BT1 at (−17, 35). The pack has a PCM; this board has no second protector.

## Cable

Dev / USB-C variant: J2 is a USB-C receptacle (HRO TYPE-C-31-M-13C, `C2848620`) and JLCPCB places it. Any USB-C cable with USB 2.0 data works, C-to-C or A-to-C. There is nothing custom to order. The magnetic lead recipe lives on `compact-final`.

## Order checklist

1. If you changed schematic sources, run `python hardware/kicad/recorder/generate_recorder.py` then `python hardware/kicad/recorder/verify_schematic.py`. That overwrites sheets only. It does not write `recorder.kicad_pcb`.
2. `python scripts/check_gates.py` (envelope, `recorder_test`, schematic ERC, outline/holes, MCU SKU, pins). Official copper DRC is `kicad-cli pcb drc`. A clean run writes the whole upload package in one pass: `hardware/kicad/fab/` from `kicad-cli`, and `hardware/kicad/jlcpcb_bom.csv` + `jlcpcb_cpl.csv` + `jlcpcb_extra.csv` from `generate_jlc.py`. Send them only if that run just happened. If gates or DRC fail, edit the board. Do not stop at the report.
3. Optional: ngspice `sim/spice/power_path.cir`
4. Human glance in KiCad 10: USB length/impedance, courtyard collisions, 3D vs case. Footprint XY: `hardware/kicad/recorder/placement.json`.
5. Upload `hardware/kicad/fab/recorder-jlc.zip` (the Gerbers; not the loose files) + `hardware/kicad/jlcpcb_bom.csv` + `jlcpcb_cpl.csv` from **this** `revert-to-usb-c` dev / USB-C board (59.6 × 85.6 mm). Set **0.8 mm** thickness and **OSP**; JLC defaults to 1.6 mm HASL. Tick **Confirm Parts Placement**. J2 (C2848620) has a JLC model; check its mouth sits on the board edge in the slot and the contact row is over the pads (CPL rot 180, no offset yet). In the preview, every pink pin-1 dot must sit on our pad 1. Fix a wrong one in `JLC_ROTATION_OFFSET` in `generate_jlc.py` and re-run step 2, not on the order page. Do not upload the 64 × 86 mm files on `main`. Step 2 writes those from `recorder.kicad_pcb`, so upload the files that run just produced. Do not hand-edit the CSVs: LCSC order codes come from the tables in [`docs/bom.md`](bom.md), and which parts the machine places comes from the board's own `exclude_from_pos_files` / `exclude_from_bom` flags. A missing LCSC on an assembly-BOM part fails the generator. BT1 and the download pads are copper only. **J2** is C2848620 in a 9.24 × 6.54 mm slot on the phone-bottom edge. The slot is in the Edge.Cuts Gerber; JLC routes it, so no extra option is needed. ITERM and the USB-C nets are routed; a clean `check_gates` is the go-ahead for this folder.
6. Order magnet ring and LiPo **before** locking CNC metal
7. Have a USB-C cable with data on hand. Nothing custom to order.
8. SMT board: follow [`docs/bringup-custom.md`](bringup-custom.md)
