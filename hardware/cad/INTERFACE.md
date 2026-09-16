# CAD ↔ PCB interface

One origin, one height map. If a number moves, change CAD and the board together. Do not leave a second copy only in KiCad.

## Origin

Phone-facing view of the accessory.

- **(0, 0)** = center of the magnet ring = Pixel Pixelsnap axis
- **+X** = phone right
- **+Y** = toward the camera bar (phone top)
- **+Z** = away from the glass (out of the phone)

The KiCad board origin matches. Edge.Cuts is the 64 × 86 mm PCB, not the 67 × 90 mm shell.

## Height map (phone glass → outside)

| Layer | Z span (mm) | Notes |
| --- | --- | --- |
| Adhesive | 0.00–0.15 | Ring stock / VHB, phone-facing |
| Magnet ring | 0.15–1.25 | Ferromagnetic only here + shunt |
| Steel shunt | 1.25–1.55 | Behind the ring, away from the phone |
| PCB | 1.55–2.35 | 0.8 mm; **B.Cu** is the flat phone-facing side |
| Tray / lid split | 2.35 | `tray_h` = adhesive + magnet + shunt + PCB = 2.35 mm. `lid_h` = 6.65 mm |
| Tall parts | 2.35–5.55 | USB-C 3.2 mm, module 2.4 mm, SD on **F.Cu**. In the lid |
| LiPo pocket | 2.35–7.35 | 5.0 mm pouch at (0, 10), +Y of U1/J2 and −Y of SP1 |
| Speaker (SP1) | 2.35–6.35 | 4.0 mm KELIKING can on F.Cu. Sound faces the lid |
| Back shell | 7.80–9.00 | 1.2 mm PETG (`shell_back`). `speaker_grille()` opens the skin over SP1 |

Envelope budget is **9.0 mm**. USB stack is 6.75 mm. Speaker stack is 7.55 mm. Battery stack is 8.55 mm.

`case.scad` puts a 0.4 mm PETG floor under the magnet ring so it cannot fall through. That floor is a print trick. It does not change the stack numbers in `params.json`. Edit those if the stack changes. After the real ring arrives, shim, then tighten the pocket.

The tray also leaves a 0.5 mm PETG floor on the phone face under MK1. A 3 mm collector under the B.Cu NPTH at (30.00, 9.32) and a 3 mm channel in +X take that hole out the right wall, where it joins `mic_port()`. MK1 is on F.Cu. A port that faces the glass muffles recordings. If you move MK1, move the duct and the wall hole with it.

SW_BOOT / SW_RST are 5.1 × 5.1 × 5.0 mm top-actuated parts on F.Cu. Lid cavity above the PCB is 5.45 mm, so the actuators sit 1.65 mm under the outer skin. **Lid-off only** this spin: a flush hole in 1.2 mm PETG does not reach them.

## XY locations (magnet-centered)

Edge features are the wall or board edge (PCB is 64 × 86 mm, so the long edges are ±32 mm and the short edges are ±43 mm). Footprint centers are inset.

The official board is `hardware/kicad/recorder/recorder.kicad_pcb`. Footprint XY lives in `hardware/kicad/recorder/placement.json`.

The table below is the CAD wall-cut contract from `params.json`. Change the case cuts when you move a part or caliper a phone and a stuffed board.

| Feature | X (mm) | Y (mm) | Max Z above PCB |
| --- | --- | --- | --- |
| USB-C edge / overmold | +8.0 | −45.0 (accessory bottom wall) | 3.2 mm (F.Cu) |
| USB-C footprint (J2) | +8.0 | −37.6 | 3.2 mm (F.Cu). Mouth at y=−43. Rectangular wall slot this pass |
| Mic port (wall) | +33.5 (right long wall) | +10.0 | 3 × 2 mm hole at the tray/lid split (`mic_port()`). Tray `mic_duct()` joins this hole. |
| Mic capsule (MK1) | +30.0 | +10.0 | IM73A135 on **F.Cu**, rot 90°. Bottom-port NPTH is at (30.00, 9.32) on **B.Cu**. Port must not face glass. The tray ducts that hole under the PCB to the right wall. |
| Button edge | −33.5 (left long wall) | +12.0 | 3 × 2.2 mm press-through slot (`button_hole()`). Needs a moulded nub to span the 0.9 mm from the inner wall face to the actuator tip. |
| Button (SW1) | −29.3 | +12.0 | side-actuated Panasonic EVQP7C01P, rot 270° so the actuator faces the left wall. Tip 0.6 mm inside the board edge; copper 1.46 mm off it. |
| LED (D1) | −29.0 | +18.0 | side window in the lid wall, not through the back |
| SD slot (J3) | see placement.json |  | no mouth in this pass |
| Speaker (SP1) | 0.0 | +36.0 | 4.0 mm KELIKING KLJ-01304T on F.Cu. Sound faces the lid; `speaker_grille()` opens the back skin |
| JST-PH (BT1) | −23.5 | +34.0 | S2B-PH-K-S, 6.0 mm tall. Pad 1 (VBAT) at this XY; cable toward y=+43. `jst_window()` cuts shell_back over the housing |
| LiPo pocket | 0.0 | +10.0 | 40 × 30 × 5 mm pouch. Lid `battery_fence()` outer is 43.6 × 33.6 mm around this. Was y=12; that put the +Y wall 0.7 mm from SP1. |
| MCU module (U1) | +14.0 | −18.0 | 2.4 mm, next to USB; MINI-1U, IPEX unused |
| Mounting holes | ±(32−3.5), ±(43−3.5) | M1.6 clearance |

### Recorder designators

These are the recorder project names. Do not keep the old generated-board map.

| Ref | What |
| --- | --- |
| J2 | USB-C receptacle |
| J3 | microSD |
| J1 | UART header |
| U8 | analog LDO (codec / mic) |
| VDD33 | MCU 3.3 V rail |
| U1 | ESP32-S3-MINI-1U |
| BT1 | JST-PH S2B-PH-K-S (pad 1 at −23.5, 34) |

Export KiCad STEP (`File → Export → STEP`) and import next to `case.scad` (OpenSCAD cannot import STEP; use the STL from `case.scad` plus the KiCad 3D view, or Fusion/Onshape for a boolean). `check_envelope.py` is the automated gate; a 3D collision pass is visual.

## PETG print fit on a Pixel 10

`case.scad` already lays the two parts on one plate: tray at the origin, lid shifted +X.

1. Print in PETG. Tray sits phone-face down. Lid sits mating-face down (the rabbet groove is on the bed).
2. Magnet pocket is 0.3 mm loose on OD. Drop in the bought ring + steel shunt (shunt **behind** the ring, away from the phone). Shim with tape. Do not chase a tight magnet until the real ring is on the desk. Isolate the shunt from any later metal lid with tape.
3. M1.6 screws. `hole_d` 1.7 mm and the boss bore are **clearance**, not a tap. Do not thread PETG. Nuts or heat-set inserts come later. Keep screw heads off the phone glass.
4. Drop in a dummy PCB (or the first fab) and a 5 mm dummy pouch. The pouch pocket is 40 × 30 × 5 mm at (0, 10), clear of U1, J2 and SP1. Confirm the lid grille sits over the speaker and the fence wall does not hit the can.
5. Snap to the Pixel. Confirm:
   - camera bar not covered
   - USB-C cable overmold misses the phone
   - mic port is on the long edge, not against glass
   - button reachable while snapped
   - snap hold feels OK (add or remove tape shims)
   - tray and lid still locate on the lip after a few open/close cycles
6. Only then order SMT, or order PCB+SMT in parallel if this 3D check is clean and you accept a spin.

Assembly order: ring adhesive on glass side → ring → shunt → PCB (flat to shunt) → pouch → lid. Screws plus the mating lip hold it. No snap-fit this pass.

Pixel body and Pixelsnap center stay the published defaults until you caliper a real phone. **Caliper before any 6061 toolpath.** Chassis is PETG first, then 6061, never steel.

## If 9 mm loses

SP1 is a 4.0 mm SMD can. The speaker stack is 7.55 mm under a 9.0 mm envelope. If a stuffed board still blows the stack, use the ES8311 3.5 mm jack and drop the PA. That decision belongs at this height-stack check, not after fab.
