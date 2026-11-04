# Agent notes

Keep this file in sync with the project. When the goal or the current solution changes, update the matching sections here.

## How to respond

Be brief. Prefer plain language over jargon. Write so a non-specialist can follow the point, without watering down the technical facts. Use short sentences, define a term the first time you use it, then keep going.

Lead with what happened or what to do. Part numbers, net names, and millimetres belong after that sentence, not instead of it. Do not dump a status list of nets, vias, and acronyms unless the user asked for that level of detail.

```
Bad: VBUS_CHG maze-closed after ripping the USB-edge CHG_STAT that boxed IN.
Good: USB power now reaches the charger. A leftover charge-LED trace was blocking that path; it is gone.
```

## What this project is

A one-off slim voice-note recorder that snaps to the back of a Google Pixel 10 with Pixelsnap / Qi2 magnets (the same kind of ring used by MagSafe-style accessories). It records raw WAV files, charges and copies files over USB, can share those files over its own Wi-Fi network, and leaves transcription to a computer. This repo is hardware, firmware, simulation, and (later) a local transcription helper.

## Goal

Build one working accessory, not a product line. Prove the design in simulation and on an off-the-shelf Espressif voice board, then order a custom slim board from a quick-turn fab. Prefer known ESP32-S3 + codec + battery + USB mass-storage patterns over invented RF or ASR problems.

The device should:

- Record 48 kHz, 16-bit, mono PCM WAV to `/recordings/YYYYMMDD-HHMMSS.wav`
- Appear as a USB drive when a USB cable is plugged in (recording stops while mounted)
- Share `/recordings` over the recorder’s own Wi-Fi network (browser page plus read-only WebDAV) so a phone or computer can play or copy files without the cable
- Charge from 5 V on the USB-C receptacle (this dev branch; the 4-pin magnetic pad is on `compact-final`); run from a single-cell LiPo
- Fit a **62 × 88 × 10.65 mm** envelope that does not cover the Pixel camera bar (`main` still has the 67 × 90 × 9 prototype). The pouch sits under the board, over the magnet wells; 7.4 mm cannot hold that stack.

**Out of scope for v1 unless the design forces a change:** on-device transcription, Bluetooth file transfer, SMB, HTTPS, joining a home Wi-Fi, charging the phone through this accessory, MagSafe/Qi2 certification, waterproofing, and an Android app while the recorder is snapped on.

## Nothing is frozen

Every file in this repo can change if the reason is sound. That includes docs, `params.json`, `placement.json`, schematic sources, `recorder.kicad_pcb`, firmware pins, CAD, BOM numbers, and the check scripts themselves.

Words like "locked", "hand-owned", "do not re-run", and "not fab-ready" mean current status or a wipe hazard. They are not a ban on work.

When a check fails, edit the design (or the check if the check is wrong). Do not stop at a status report: do not end a turn by only running `check_gates.py` and repeating that the board is not ready. Say why the old number or file was wrong in the same change.

The only tree that is not product is `hardware/kicad/example_project`, a hand-made learning project. Do not read it for product truth. Do not edit, generate into, or "fix" it unless the user is in that lesson. Product KiCad work is `hardware/kicad/recorder/`.

## KiCad agent skills (KiStack)

This repo vendors the KiCad skills from [American-Embedded/KiStack](https://github.com/American-Embedded/kistack) so Claude Code and Cursor agents can load them with the project.

| Skill | Use when |
| --- | --- |
| `kicad-schematic` | Wiring or reviewing schematics |
| `kicad-pcb` | Placement, routing, layout review |
| `kicad-symbol` / `kicad-footprint` | New library parts |
| `kicad-bom` | Exact part numbers and manufacturer fields |
| `kicad-export` | `kicad-cli` ERC, DRC, Gerbers, BOM, 3D |
| `kicad-gerbers` | Visual Gerber inspection |
| `kicad-panelize` | KiKit panelization |
| `pcb-product-render` | Blender product shots of the board |

Files live in `.claude/skills/<skill-name>/`, next to this repo's own `make-board-manufacturable` and `show-image` skills. `/show-image <path.png>` opens a render in the Windows viewer with `explorer.exe "$(wslpath -a -w <path>)"`. Claude Code discovers skills there; Cursor also scans `.claude/skills/`. If a Cursor build or Cloud Agent stops seeing them, that is the first thing to check. Source pin: `skills-lock.json`. License: `.claude/skills/kistack-LICENSE`.

These skills do not replace this project's generators. Product sheets still come from `generate_recorder.py`. Product copper still lives in `hardware/kicad/recorder/recorder.kicad_pcb`. If a KiStack workflow and a repo rule disagree, follow `AGENTS.md`.

## Current solution

**Architecture:** ESP32-S3-MINI-1U MCU (IPEX plus a lid-taped 2.4 GHz W.FL / I-PEX MHF III FPC, Inventek B24P-W), Everest ES8311 codec as I2S master (12.288 MHz oscillator into MCLK; the S3 is slave), analog MEMS microphone, soldered SD NAND (512 MB on the prototype), no on-device speaker. Charge and USB MSC share one USB-C receptacle (J2, HRO TYPE-C-31-M-13C, LCSC C2848620, mid-mount) on the phone-bottom edge. That is the **dev / USB-C variant** on branch `revert-to-usb-c`; `compact-final` keeps the 4-pin magnetic pad, which added too much cable and click-test work for a dev board. U3 is a BQ24073 power-path charger: **VSYS** (OUT) feeds the loads, **VBAT** is the Jauch pouch pigtail on B.Cu BT1 pads only. Analog codec power is a separate 2.8 V low-noise LDO (U8 LP5907-2.8, net **3V3A**) from the MCU 3.3 V supply, because IM73A135 VDD abs max is 3.0 V. Lid is always natural translucent PETG so the radio can leave the case; a local well over U1’s IPEX swallows the mated pigtail. Tray is PETG first, then CNC 6061 (`variant="metal"` is tray-only): closed 0.85 mm phone-side skin, blind wells for the N52 ring and the clocking magnet, four 5.0 mm M1.6 posts. The Jauch pouch is taped to B.Cu and wrapped in kapton. Not steel, which would steal hold from the magnet ring. The module SKU is the no-PCB-antenna MINI-1U because a PCB antenna would sit next to the ring’s steel plate and the aluminum tray. Full electrical and mechanical notes: `docs/architecture.md`. Why this MCU/codec pair: `docs/audio-platform.md`. The thin-lid plan is `docs/plan-thin-pogo-lid.md` (magnetic-pad variant only; historical on this branch). U1 numbers live in `hardware/cad/params.json` under `mcu`. The product KiCad project is `hardware/kicad/recorder/` (schematic + PCB).

Those are the current choices. Change them when the envelope, parts, or bring-up says they are wrong, and update the docs in the same pass.

**Firmware:** A portable recorder core in `firmware/core` (state machine, WAV headers, timestamped files, playback). It builds two ways: `HOST_SIM` on a PC (`sim/host`) and `ESP_PLATFORM` with ESP-IDF on hardware. States: idle → recording / playing → idle. Custom board has `PSV_HAS_PLAYBACK 0`; double-press toggles Wi-Fi share (SoftAP, browser file page, read-only WebDAV). Korvo / ESP-BOX / host sim still play. `firmware/sdkconfig.korvo_wifi_share` turns on `CONFIG_PSV_WIFI_SHARE_DOUBLE` for a Korvo antenna prove (MSC off: Korvo native USB D+/D− are reserved). A host MSC mount forces USB mass-storage, stops record or play, and turns the radio off. TinyUSB takes exclusive NAND access (VFS unmounts) while the host is mounted. VBUS alone does not. The radio stays off until share starts. Bluetooth stays off. Custom codec-master leaves I2S MCLK unused so the S3 does not fight Y1 on GPIO14.

**Transcription:** Dump WAVs over USB, then `python software/transcribe.py` (whisper.cpp) on the computer. Nothing in `software/` runs on the recorder in v1.

## Status (will go stale)

Update this section when it stops being true.

- Host sim + `recorder_test` (including playback and the Wi-Fi share state) build from `sim/host/CMakeLists.txt`.
- Wi-Fi share: SoftAP `PixelSnapVoice` / `voicenote1`, `http://192.168.4.1`, radio off until double-press. Korvo prove overlay is `firmware/sdkconfig.korvo_wifi_share` (`CONFIG_PSV_WIFI_SHARE_DOUBLE=y`, `CONFIG_PSV_USB_MSC` off). Mate the lid W.FL / MHF III pigtail before transmitting on the custom board. Bluetooth stays off.
- Phase 0 ESP-IDF app is in `firmware/` (Korvo-2 / ESP-BOX / custom pin maps). CAD is in `hardware/cad` (`params.json` + `case.scad`, draft PETG).
- Product KiCad is `hardware/kicad/recorder/` (open `recorder.kicad_pro`). Sheets come from `generate_recorder.py`. The board file is `recorder.kicad_pcb`. Footprint XY is `hardware/kicad/recorder/placement.json`.
- This branch (`compact-final`) is the 62 × 88 × 10.65 mm / 59.6 × 85.6 mm spin. `main` stays the routed 67 × 90 / 64 × 86 prototype. Do not upload `main` Gerbers for this order.
- The tray is a closed 0.85 mm phone-face skin, a 2.35 mm inner floor, a 1.2 mm wall, and four 5.0 mm M1.6 posts. The N52 ring (54.1 × 46 × 1.5 mm, steel already on it) and a 12 × 5 mm clocking magnet sit in blind wells, glued steel-face up. The clocking block's long side points at 6 o'clock (−Y). The board and lid are spun 180° on that tray. On this branch J2 is a USB-C on the phone-bottom (−Y) end wall, over the clocking magnet's end. MK1 is on F.Cu at (27.5, 17); a rib under the B.Cu NPTH stops 0.40 mm short of the board for a foam frame, with a mesh pocket and three 0.60 mm holes in the phone-right wall. The record pill is on the phone-left wall when the accessory is snapped on. Print STLs are in `hardware/cad/export/` (tray, lid, TPU `button`). The 6061 copy is `openscad -D variant="metal"`: tray only, same blind wells, no skirt, 2.5 mm blind tap in each post. The lid is always natural translucent PETG (flat top, TPU pill with a flush rounded bezel and a proud press pad, screws from the outside). `check_dfm.py` treats CNC as the tray. JLC SLM is still 316L / titanium only.
- Case styling (CAD only): lid corners are solid — M1.6 clearance plus a 3.2 mm outer CSK; each tray post is a 1.35 mm tap that stops above the 2.35 mm inner floor. The 0.85 mm magnet skin stays closed. Lid back has two-focus wave engraving clipped off the IPEX well and the screw bosses. Long walls have 18° grip ridges on tray and lid (they skip the pill and the mic). The −Y end wall has the USB-C mouth: 9.5 × 3.7 mm round-ended, centred on J2 at x = 7.0, z 5.02–8.72, split across tray and lid, inside a 12.8 × 6.7 mm overmold relief 0.7 mm deep (z 3.52–10.22) that leaves a 0.5 mm web, so a plug overmold lands 0.5 mm off the shell face and latches. That web is JLCCNC's metal floor and under PCBWay's 0.8 mm, so the 6061 tray is a JLCCNC part. No speaker grille, no side LED windows. Do not print threads in PETG.
- **This branch (`revert-to-usb-c`) is the dev / USB-C variant, and it is routed**, including ITERM (U3 pin 15 to R11) and a mid-mount USB-C J2 on the phone-bottom (−Y) edge. The magnetic pad, speaker and PA are gone. The case (`case.scad`) cuts the wall mouth from the `usbc_*` keys in `params.json`; the pogo dish and the `pogo_*` keys are gone. Do not upload `main` Gerbers for this order. Do not run `generate_pcb.py` unless you intend a copper wipe. Do not run a full `route_pcb.py` until its hand-stitch coordinates match this lid 180° spin.
- **The DRC rules are JLCPCB's published capability**, not house numbers. Global floors live in `DESIGN_RULES` in `generate_pcb.py`. The two checks that depend on item type live in `recorder/recorder.kicad_dru`: pad hole-to-hole at **0.6 mm** (JLC's floor is 0.45 mm; 0.6 mm keeps the +0.13 mm plated-hole tolerance), and 0.5 mm minimum non-plated hole. The board holds 0.15 mm tracks, 0.6/0.3 vias, 0.62 mm minimum pad hole spacing and 0.3 mm hole-to-copper.
- Silkscreen is 1.0 mm on a 0.15 mm stroke, JLC's standard font. It used to be 0.8 mm, which is only legal on their high-precision line and which their own capability table calls unidentifiable. Every designator still found a clear seat at the larger size.
- USB D+/D− are a plain 0.2 mm pair on a 0.4 mm pitch, **not** impedance controlled: the ESP32-S3 is full speed only. Do not order the controlled-impedance option. Reasoning in `hardware/kicad/README.md`.
- MK1's land pattern in `PSV.pretty` is adapted, not the datasheet drawing: the ring pad and its stencil sit at r=0.95 mm so copper clears the 0.8 mm sound port by 0.32 mm. Infineon's own figure leaves 0.18 mm, under JLC's 0.2 mm floor before drill tolerance. Check the acoustic seal on the first assembled board.
- Current pouch is a Jauch LP305166JH-PCM-2-WIRES-70MM (DigiKey 13278052), 66 × 51.5 × 3.3 mm, 1200 mAh min, taped to B.Cu at (0, 0) and wrapped in kapton. The pack has a PCM. BT1 is on B.Cu at (−17, 35), just north of the cell, pad 1 VBAT on the west land.
- **J3** is MK MKDV4GCL-ABB (LCSC C7500178) 4 Gbit / 512 MB SD NAND, LGA-8 8.0 × 6.0 mm at (−22, −18), about 1.4 h of 48 kHz mono. Prototype pick: the 4 GB CS CSNP32GCR01-AOW (C2841139) cost $46 a chip at JLC against $14. Capacity is a cost choice for now; size it to a full pouch (~2.5 GB) for a final product. Pin order is CLK on 3, ground on 4, CMD on 5, power on 8 (the Zetta order, not a microSD socket). Datasheet top view: pin 1 top-left, 1–4 down the left side, VCC (8) top-right. Until 1 Nov 2026 the land was mirrored and had its pad columns 5.4 mm apart on the long sides; the real chips are 8 mm wide with the columns on the short ends, about 7 mm apart. The land now covers CS, Zetta and MK LGA-8 SD NAND. Check new parts against the datasheet package drawing, not against an older board. Custom firmware sets `PSV_SD_FORMAT_IF_BLANK`.
- Pixel body and Pixelsnap numbers are published defaults until someone calipers a phone. The 6061 tray is on HOLD. Quote STEP is `hardware/cad/export/metal/tray.step` (`.venv/bin/python hardware/cad/export_metal_step.py`; needs CadQuery and an `openscad` on PATH — on WSL, a wrapper that passes Windows paths to `openscad.com`). It includes the USB-C mouth. Tap M1.6 after CNC. The lid stays PETG.
- J2 is an HRO TYPE-C-31-M-13C (LCSC C2848620) mid-mount 16-pin USB 2.0 receptacle at (7.0, −38.1), rot 180, mouth flush with the phone-bottom edge (y = −42.8). It sits in a 9.24 × 6.54 mm board slot carried in its footprint, 1.60 mm above F.Cu and 0.76 mm below B.Cu, so it fits the 2.6 mm lid cavity without growing the case. A top-mount C receptacle (3.26 mm) does not. USB sink: R2 / R3 5.1 kΩ Rd on CC1 / CC2, both D± pairs tied, SBU open, shell to GND. U7 sits just north of it. The 16 contact heels are 0.20 mm from the slot, JLC's floor; `recorder.kicad_dru` scopes that exception to J2's pads. Case interface is the `usbc_*` keys in `params.json`.
- SW1 is a **side-actuated** Panasonic EVQP7C01P (LCSC C388883, 3.5 × 2.9 × 1.35 mm, 2.2 N). Centre at (−27.1, 12), rot 270, phone-left wall when snapped on. A captive TPU 95A pill in the lid wall is the finger target; the switch is the spring.
- Reflash is the USB-C port. First flash needs nothing pressed. After TinyUSB owns USB, hold the record button 5 s from wake with the cable in a computer: `firmware/hal/download_mode.c` sees USB frames and restarts the S3 into ROM download mode (`CONFIG_PSV_BOOT_DOWNLOAD_HOLD`, custom board only). Fallback is **TP_BOOT / TP_EN / TP_GND / TP_3V3** on F.Cu (lid off). No Boot/Reset switches and no UART header.
- **U3** is a BQ24073RGTR (LCSC C15220) power-path charger in VQFN-16. Pin 6 is EN1, pin 7 is power-good and left open, pin 8 is ground. USB-C J2 is the only 5 V inlet. **VSYS** (OUT) stays up from USB with the pouch off; **VBAT** is the pouch pigtail on BT1 pads. C21 is 10 µF on VBAT next to U3 so the BAT pin has local ceramic when the pouch is unplugged. Do not put 5 V on BT1 and do not strap VSYS to VBAT. The Jauch pack has a PCM; this board has no second protector. Charge at 500 mA stays under the pack's 0.5 C / 600 mA ceiling.
- **JLC order LCSC swaps.** **F1** is `C883095` (the old `C37010` is not a real part). **U7** is ST USBLC6-2SC6 `C7519` (the old `C8678` is an SS34 Schottky). **Y1** is YXC `C5203546` (OT2EL4C4JI-111OLP-12.288, 1.8–3.3 V CMOS). It replaced JLYE `C49207908`, a JLC shop part with no preview model, so its pin 1 could not be checked; Kyocera `C1857159` before that was a JLC SMT shortfall. Do not substitute a 3.3 V-only oscillator: **3V3A** is 2.8 V.
- Computer-side whisper.cpp wrapper is `software/transcribe.py`.
- Toolchain setup on Ubuntu 24.04 (dev box, CI, container, cloud agent) is `bash scripts/setup-ubuntu.sh`: KiCad 10 + `pcbnew`, ngspice, CMake, freerouting in `/opt/freerouting`, then the host sim build. Windows and macOS steps are in the README under "Set up a machine". Keep both in sync when a tool or version changes.
- KiStack KiCad skills are vendored in `.claude/skills/` (`kicad-schematic`, `kicad-pcb`, and the rest of the table above).
- Current render stills are tracked in `docs/renders/` (`board/`, `case/`). Render scripts still write to `build/product-renders/` and `build/case-renders/`; `python3 scripts/sync_renders.py` copies the PNGs across. `.githooks/pre-push` runs it with `--check` and blocks a push while the tracked copies are behind. Enable it once per clone with `git config core.hooksPath .githooks`.

`python scripts/check_gates.py` is the ship gate and it now does the whole job itself: it runs `check_placement.py` when `pcbnew` is importable, runs `kicad-cli pcb drc` at every severity and with `--schematic-parity`, and then writes Gerbers, both drill files, the pick-and-place CSV, `recorder-jlc.zip` and the two JLCPCB assembly CSVs from `recorder.kicad_pcb` in one pass. Do not hand-export or hand-edit part of that set — a drill file that does not match the copper is a scrap board, and a pick-and-place row that does not match it is a misassembled one. It also runs DRC a second time with `--refill-zones` and refuses to plot if the two disagree, because `kicad-cli` plots the fill stored in the board: a stale pour would otherwise ship while DRC quietly refilled and called it clean.

`hardware/kicad/jlcpcb_bom.csv` and `jlcpcb_cpl.csv` are **generated**, by `hardware/kicad/recorder/generate_jlc.py`. LCSC order codes come from the tables in `docs/bom.md`; a board part on the assembly BOM with no number there fails the generator, because JLCPCB will not place a blank cell. Which parts the machine handles comes from each footprint's own `exclude_from_pos_files` / `exclude_from_bom` flag in the board. BT1 and the download pads are copper only and stay off both CSVs.

Copper DRC is clean and the USB-C nets are routed. MK1's acoustic seal, the unpublished Pixel / Pixelsnap calipers, and the USB-C slot / cable-latch check are still on `placement.json` `open_items`. JLC's preview of J2 (C2848620) has not been checked yet. Caliper a phone and a stuffed board before paying for the 6061 tray. The quote file is already at `hardware/cad/export/metal/tray.step`; that is not an order.

## How to change the hardware

Close KiCad before running the generators. Lock files look like `~recorder.kicad_pro.lck`.

| If you need to change | Edit | Then |
| --- | --- | --- |
| Nets, parts, pins on the schematic | `generate_recorder.py`, `PSV.kicad_sym` | `python hardware/kicad/recorder/generate_recorder.py` then `python hardware/kicad/recorder/verify_schematic.py`. This overwrites sheets only. It does not write the PCB. |
| Download pads / pouch pads | `generate_recorder.py` | TP_BOOT / TP_EN / TP_GND / TP_3V3 and BT1 pigtail land. Live BT1/J3 edits are `apply_hollow_tray.py` (does **not** wipe copper; historical, do not re-run after `apply_lid_180.py`). `generate_pcb.py` wipes copper; the old `apply_boot_buttons.py` / `apply_jst.py` paths are for the 67 × 90 board on `main`. |
| Board/lid 180° vs tray | already done by `apply_lid_180.py` | Spins copper around the magnet origin so (then) the magnetic J2 was phone-top and SW1 is phone-left. The USB-C J2 was placed after the spin. Tray magnets stay at 6 o'clock. Do not run it twice. Does not wipe copper. |
| Footprint XY | `placement.json` and `recorder.kicad_pcb` together | Keep them twins. `check_placement.py` now compares them part by part and fails on drift. Also update `hardware/cad/params.json` / `case.scad` if a wall cut or pocket moves. |
| An LCSC order code, or which parts JLC assembles | the LCSC column of `docs/bom.md`, or the footprint's `exclude_from_pos_files` / `exclude_from_bom` flag in the board | `python scripts/check_gates.py` rewrites `jlcpcb_bom.csv`, `jlcpcb_cpl.csv`, and `jlcpcb_extra.csv`. Never hand-edit those. |
| A clean placement rebuild | `generate_pcb.py` (KiCad 10 `python.exe`, not system Python) | This **wipes** copper. Re-pour planes and re-route after. Do not run it as a status check. |
| Planes | `route_pcb.py --planes-only` (same KiCad interpreter) | Loads the existing board. Does not move parts. |
| Signal traces | `recorder.kicad_pcb` (KiCad, `route_pcb.py`, or both) | `route_pcb.py` with no flag clears copper, hand-routes and locks the awkward parts, then drives freerouting and repairs until DRC is clean. `--finish-only` just drops stub vias, re-seats silk and refreshes `placement.json`. |
| Envelope / case | `params.json`, `params.scad`, `case.scad` | `python hardware/cad/check_envelope.py` for Pixel fit. `python hardware/cad/check_dfm.py` for JLCCNC / JLC3DP / PCBWay published limits. Do not add the metal DFM check to `check_gates.py`: a red metal case must not block PCB Gerbers. |
| GPIO map | `hardware/kicad/pins.py`, `firmware/boards/custom.h`, and `pinmap.md` | `check_pins.py` is a consistency check. Change all three. |
| MCU SKU | `params.json` `mcu` | Update schematic sources and regenerate sheets. |

`scripts/check_gates.py` reads the files already on disk. It does not design the board. A red check is a todo. A green `check_gates` is not a JLCPCB go-ahead by itself.

Official DRC is `kicad-cli pcb drc` on `recorder.kicad_pcb`. The Python file named `check_drc.py` is an outline-and-hole check, not copper DRC.

Custom SMT bring-up: `docs/bringup-custom.md`.
