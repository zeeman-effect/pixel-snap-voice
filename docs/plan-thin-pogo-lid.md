# Thin lid: drop speaker, bond pouch, magnetic pogo, plastic lid

Living plan for the compact-final spin. The earlier drop-speaker / bond-pouch note is folded in here.

## Why

The 4 mm speaker can and the 4 mm pouch both stacked to 7.55 mm under an 8 mm shell. USB-C added a 3.2 mm jack and a wall mouth. Playback is not needed on this one-off: files leave over USB or the recorder’s own Wi-Fi share. Charge and dump can share one 4-pin magnetic face on the lid.

## Locked choices

| Item | Choice | Why |
| --- | --- | --- |
| Envelope | **62 × 88 × 10.65 mm** | Tray is 6.85 mm: 0.85 mm skin plus the 1.5 mm N52 ring plus the 3.3 mm Jauch pack. Lid is 3.80 mm. |
| Lid | **Always PETG / plastic** | Pogo magnets and the later 6061 tray must not share one metal shell. |
| Tray | PETG proto, then **6061** (`variant="metal"` is tray-only) | Blind wells for the ring and the clocking magnet stay in the phone-facing half. |
| Playback | Off on the custom board | Korvo / ESP-BOX / host sim still play. Double-press starts Wi-Fi share. |
| Pouch | **Jauch LP305166JH-PCM-2-WIRES-70MM**, 66 × 51.5 × 3.3 mm, 1200 mAh min | Taped to B.Cu at (0, 0), kapton-wrapped. PCM on the pack. Four tray posts carry the board. |
| Storage | **Zetta ZDSD32GLGEAG** 4 GB SD NAND, LGA-8 | Same SDMMC nets as the old card. Format FAT if blank. |
| Record button | Captive **TPU 95A** pill in the lid wall | SW1 is the spring. No PETG cantilever. |
| Charge + USB | **C6276862** pad on the board (Xinyangze `YZ103915020T-04025-02`) | 2.0 mm female. 4 pins: VBUS, D−, D+, GND. |
| Cable | **C5126845** male (`YZP0048-20048-04025-03`) on a USB-A lead | Same-maker 4-pin / 2.5 mm family. Click-test before a board spin. Not a finished LCSC SKU. |
| USB-C | **Gone** | No CC resistors, no edge mouth, no 6.75 mm jack stack. |
| PA / speaker | **Gone** (U6, SP1, C17–C19, R7, PA_EN) | ES8311 AOUT left open. |

## Stack (phone glass → outside)

1. Skin 0.85 + ring 1.5 + air 0.15 + tape 0.15 + pouch 3.3 + swell 0.1 + PCB 0.8 = **6.85 mm tray**
2. Lid cavity 2.60 mm: MCU 2.4 mm, pogo 2.0 mm, NAND 0.8 mm
3. Plastic back skin 1.2 mm
4. Total **10.65 mm**

The tray floor is 2.35 mm with wells down to a closed 0.85 mm skin, a 1.2 mm wall, and four 5.0 mm posts. The pouch hangs from B.Cu. F.Cu under that outline is free. BT1 is on B.Cu at **(−17, 35)**, west of J2. The pogo sits at **(0, 36)** on F.Cu, on the camera / phone-top end, opposite the tray's 6 o'clock clocking magnet. The lid stays 3.80 mm so the 2.4 mm MCU clears. Over J2 it dishes to 8.70 mm so the 2.0 mm pad is 0.15 mm proud of that local face. A through-well opens the dish. M1.6 screws come from the lid into taps in the four posts.

## Electrical

- J2 is the 4-pin magnetic pad. Pin 1 VBUS, 2 USB_DM, 3 USB_DP, 4 GND (USB-A order). Confirm on the desk; the datasheet does not name a mate or a pinout.
- U7 (USBLC6-2SC6) stays on D+/D−, moved next to J2.
- F1 → U3 BQ24074 is unchanged. No Type-C Rd (R2/R3 deleted).
- GPIO8 is unused. `PSV_PA_EN` is `GPIO_NUM_NC` on the custom board.

## Case

- Delete USB stadium, speaker grille, speaker wall reliefs, pouch pocket, pigtail channel, lid clip, LED windows, and the PETG cantilever.
- Tray: closed 0.85 mm skin, blind wells for the ring and the clocking magnet, four M1.6 posts, mic rib with a foam gap, mesh pocket, and three 0.60 mm wall holes.
- Metal tray: same wells, no 0.45 mm skirt, blind 2.5 mm taps in the posts. Screws from the lid locate the plastic lid. Glue holds the magnets.
- Plastic lid: natural translucent PETG, TPU pill hole, pogo dish + well, wave art clipped off the dish and bosses, outer CSK.

## Board work (no copper wipe)

`generate_recorder.py` owns the sheets. `generate_pcb.py` PLACE is updated but **not run**. Live `recorder.kicad_pcb` was edited by `apply_thin_pogo.py` (drop speaker/PA/USB-C, plant the pogo) and then `apply_hollow_tray.py` (BT1 to B.Cu, J3 to the 4 GB NAND). USB, VBUS, and ITERM are routed. A clean `check_gates` writes the Gerbers; do not upload the 64 × 86 mm files on `main`.

## Open / human

- Click-test C6276862 against C5126845. Freeze pinout after that.
- Land is the vendor drawing: 22.30 × 7.70 × 2.00 mm stadium, 2.54 mm pitch, circular pads. Click-test the cable before freezing pinout.
- Pixel / Pixelsnap calipers still unpublished.
- LCSC cable: Side A is **Housing** `YZP0048-20048-04025-03` only (no separate terminal). Do not put C6276862 on the cable.
