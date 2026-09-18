# Agent notes

Keep this file in sync with the project. When the goal or the current solution changes, update the matching sections here.

## What this project is

A one-off slim voice-note recorder that snaps to the back of a Google Pixel 10 with Pixelsnap / Qi2 magnets (the same kind of ring used by MagSafe-style accessories). It records raw WAV files, charges and copies files over USB-C, and leaves transcription to a computer. This repo is hardware, firmware, simulation, and (later) a local transcription helper.

## Goal

Build one working accessory, not a product line. Prove the design in simulation and on an off-the-shelf Espressif voice board, then order a custom slim board from a quick-turn fab. Prefer known ESP32-S3 + codec + battery + USB mass-storage patterns over invented RF or ASR problems.

The device should:

- Record 48 kHz, 16-bit, mono PCM WAV to `/recordings/YYYYMMDD-HHMMSS.wav`
- Play recordings back through a speaker or headphone jack
- Appear as a USB drive when plugged into a computer (recording stops while mounted)
- Charge from USB-C 5 V; run from a single-cell LiPo
- Fit a ~67 × 90 × 9 mm envelope that does not cover the Pixel camera bar

**Out of scope for v1 unless the design forces a change:** on-device transcription, Wi-Fi, charging the phone through this accessory, MagSafe/Qi2 certification, waterproofing, and an Android app while the recorder is snapped on.

## Nothing is frozen

Every file in this repo can change if the reason is sound. That includes docs, `params.json`, `placement.json`, schematic sources, `recorder.kicad_pcb`, firmware pins, CAD, BOM numbers, and the check scripts themselves.

Words like "locked", "hand-owned", "do not re-run", and "not fab-ready" mean current status or a wipe hazard. They are not a ban on work.

When a check fails, edit the design (or the check if the check is wrong). Do not stop at a status report. Say why the old number or file was wrong in the same change.

The only tree that is not product is `hardware/kicad/example_project`. Do not treat it as truth. Do not edit it unless the user is in that lesson.

## KiCad agent skills (KiStack)

This repo vendors the KiCad skills from [American-Embedded/KiStack](https://github.com/American-Embedded/kistack) so Cursor agents can load them with the project.

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

Files live in `.cursor/skills/<skill-name>/`, next to this repo's existing `make-board-manufacturable` skill. Cursor Cloud Agents inject that tree at session start. Source pin: `skills-lock.json`. License: `.cursor/skills/kistack-LICENSE`.

These skills do not replace this project's generators. Product sheets still come from `generate_recorder.py`. Product copper still lives in `hardware/kicad/recorder/recorder.kicad_pcb`. If a KiStack workflow and a repo rule disagree, follow `AGENTS.md` and the `.cursor/rules` files.

## Current solution

**Architecture:** ESP32-S3-MINI-1U MCU (IPEX, no cable in v1), Everest ES8311 codec as I2S master (12.288 MHz oscillator into MCLK; the S3 is slave), analog MEMS microphone, NS4150B into a KELIKING KLJ-01304T-08R07W SMD speaker (JLCPCB C18186315), microSD, USB-C as a 5 V sink only. U3 is a BQ24074 power-path charger: **VSYS** (OUT) feeds the loads, **VBAT** is the pouch on JST-PH BT1 only. Analog codec power is a separate low-noise regulator from the MCU supply. Chassis is 3D-print first, then CNC 6061 aluminum. Not steel, which would steal hold from the magnet ring. The module SKU is the no-PCB-antenna MINI-1U because v1 has no radio and a steel shunt plus later aluminum shell sit next to the MCU. Full electrical and mechanical notes: `docs/architecture.md`. Why this MCU/codec pair: `docs/audio-platform.md`. U1 numbers live in `hardware/cad/params.json` under `mcu`. The product KiCad project is `hardware/kicad/recorder/` (schematic + PCB).

Those are the current choices. Change them when the envelope, parts, or bring-up says they are wrong, and update the docs in the same pass.

**Firmware:** A portable recorder core in `firmware/core` (state machine, WAV headers, timestamped files, playback). It builds two ways: `HOST_SIM` on a PC (`sim/host`) and `ESP_PLATFORM` with ESP-IDF on hardware. States: idle → recording / playing → idle. A host MSC mount forces USB mass-storage and stops record or play. VBUS alone does not.

**Transcription:** Dump WAVs over USB, then `python software/transcribe.py` (whisper.cpp) on the computer. Nothing in `software/` runs on the recorder in v1.

## Status (will go stale)

Update this section when it stops being true.

- Host sim + `recorder_test` (including playback) build from `sim/host/CMakeLists.txt`.
- Phase 0 ESP-IDF app is in `firmware/` (Korvo-2 / ESP-BOX / custom pin maps). CAD is in `hardware/cad` (`params.json` + `case.scad`, draft PETG).
- Product KiCad is `hardware/kicad/recorder/` (open `recorder.kicad_pro`). Sheets come from `generate_recorder.py`. The board file is `recorder.kicad_pcb`. Footprint XY is `hardware/kicad/recorder/placement.json`.
- The PETG tray ducts MK1's B.Cu NPTH under the board to the right-wall mic port. MK1 is on F.Cu.
- **The board is routed.** 752 tracks, 212 vias, ~2171 mm of copper, 8 zones. `kicad-cli pcb drc` reports zero violations at every severity and zero unconnected items, silkscreen included. Signals came from freerouting over Specctra DSN/SES; the USB-C escape, the D+/D− pair and the fine-pitch fanouts are hand-routed and locked so rip-up cannot cut them. Re-run the lot with `python hardware/kicad/recorder/route_pcb.py`.
- **The DRC rules are JLCPCB's published capability**, not house numbers. Global floors live in `DESIGN_RULES` in `generate_pcb.py`. The two checks that depend on item type live in `recorder/recorder.kicad_dru`: pad hole-to-hole at **0.6 mm** (JLC's floor is 0.45 mm; 0.6 mm keeps the +0.13 mm plated-hole tolerance), and 0.5 mm minimum non-plated hole. The board holds 0.15 mm tracks, 0.6/0.3 vias, 0.62 mm minimum pad hole spacing and 0.3 mm hole-to-copper.
- Silkscreen is 1.0 mm on a 0.15 mm stroke, JLC's standard font. It used to be 0.8 mm, which is only legal on their high-precision line and which their own capability table calls unidentifiable. Every designator still found a clear seat at the larger size.
- USB D+/D− are a plain 0.2 mm pair on a 0.4 mm pitch, **not** impedance controlled: the ESP32-S3 is full speed only. Do not order the controlled-impedance option. Reasoning in `hardware/kicad/README.md`.
- MK1's land pattern in `PSV.pretty` is adapted, not the datasheet drawing: the ring pad and its stencil sit at r=0.95 mm so copper clears the 0.8 mm sound port by 0.32 mm. Infineon's own figure leaves 0.18 mm, under JLC's 0.2 mm floor before drill tolerance. Check the acoustic seal on the first assembled board.
- Current pouch size is 500 mAh from leftover CAD volume.
- Pixel body and Pixelsnap numbers are published defaults until someone calipers a phone.
- SP1 is a KELIKING KLJ-01304T-08R07W (LCSC C18186315), 13 × 13 × 4.0 mm SMD can at (0, 36). JLC places it. The lid has a grille over the can. The 40 × 30 mm pouch sits at (0, 10) so the lid fence misses both U1 and the speaker. Confirm SP1 in JLC's assembly preview before the order: this land's pad 1 is bottom-right, JLC's library 0° is EasyEDA `-BL` (pin 1 bottom-left).
- SW1 is a **side-actuated** Panasonic EVQP7C01P (LCSC C388883, 3.5 × 2.9 × 1.35 mm, 2.2 N), not the top-actuated PTS645 it used to be. The record button is on the left wall, so a top plunger needed a case lever; this one is pressed straight through a 3 × 2.2 mm slot. Its actuator tip stops 0.9 mm short of the inner wall face, so the case still needs a moulded nub to span the gap.
- **SW_BOOT** and **SW_RST** are XKB TS-1187A-C-J-B (LCSC C318885) on the east edge. Hold Boot, tap Reset, release Boot to enter download mode after MSC owns USB-C. They are not firmware buttons. **Lid-off only** on this spin: the 5 mm actuators sit 1.65 mm under the outer skin, so a flush lid hole is not a button.
- **U3** is a BQ24074RGTR (LCSC C54313) power-path charger in VQFN-16. USB-C is the only 5 V inlet. **VSYS** (OUT) stays up from USB with BT1 open; **VBAT** is the pouch on JST-PH BT1 (C173752, land `JST_PH_S2B-PH-K`). C21 is 10 µF on VBAT next to U3 so the BAT pin has local ceramic when the pouch is unplugged. Do not put 5 V on BT1 and do not strap VSYS to VBAT. Buy a protected 1S pouch; this board has no pack protector.
- **JLC SMT assembly is sourced.** Every part on `jlcpcb_bom.csv` / `jlcpcb_cpl.csv` has an LCSC code in `docs/bom.md`. `generate_jlc.py` refuses to write those CSVs if one is missing. **F1** is BHFUSE `C883095` (0603, 500 mA hold, 6 V); the old `C37010` was not a real LCSC part, so JLC showed No Part Selected. **U7** is ST USBLC6-2SC6 `C7519` (SOT-23-6); the old `C8678` is an SS34 SMA Schottky. **Y1** is JLYE `C49207908` (12.288 MHz CMOS 3225); Kyocera `C1857159` was a JLC SMT shortfall. **J1** (UART header) and **MK1** (IM73A135) are flagged `exclude_from_bom` and `exclude_from_pos_files`; solder those by hand. **BT1** stays on the BOM for wave solder and stays out of the pick-and-place file.
- Computer-side whisper.cpp wrapper is `software/transcribe.py`.
- KiStack KiCad skills are vendored in `.cursor/skills/` (`kicad-schematic`, `kicad-pcb`, and the rest of the table above).

`python scripts/check_gates.py` is the ship gate and it now does the whole job itself: it runs `check_placement.py` when `pcbnew` is importable, runs `kicad-cli pcb drc` at every severity and with `--schematic-parity`, and then writes Gerbers, both drill files, the pick-and-place CSV, `recorder-jlc.zip` and the two JLCPCB assembly CSVs from `recorder.kicad_pcb` in one pass. Do not hand-export or hand-edit part of that set — a drill file that does not match the copper is a scrap board, and a pick-and-place row that does not match it is a misassembled one. It also runs DRC a second time with `--refill-zones` and refuses to plot if the two disagree, because `kicad-cli` plots the fill stored in the board: a stale pour would otherwise ship while DRC quietly refilled and called it clean.

`hardware/kicad/jlcpcb_bom.csv` and `jlcpcb_cpl.csv` are **generated**, by `hardware/kicad/recorder/generate_jlc.py`. They were hand-typed and had drifted: C11, C12, C17 and C18 still carried pre-route coordinates. LCSC order codes come from the table in `docs/bom.md`; which parts the machine handles comes from each footprint's own `exclude_from_pos_files` / `exclude_from_bom` flag in the board. A blank LCSC on a machine-placed part fails the generator.

DRC parity leaves 27 notes and all of them are expected: 23 module pads with no schematic pin (spare ESP32-S3 GPIO castellations, NC pins, the USB-C SBU pair, BQ24074 PGOOD) and the 4 mounting holes, which are mechanical and have no symbol. MK1's acoustic seal (hand-place after SMT) and the unpublished Pixel / Pixelsnap calipers are still on `placement.json` `open_items`.

## How to change the hardware

Close KiCad before running the generators. Lock files look like `~recorder.kicad_pro.lck`.

| If you need to change | Edit | Then |
| --- | --- | --- |
| Nets, parts, pins on the schematic | `generate_recorder.py`, `PSV.kicad_sym` | `python hardware/kicad/recorder/generate_recorder.py` then `python hardware/kicad/recorder/verify_schematic.py`. This overwrites sheets only. It does not write the PCB. |
| Boot / Reset buttons | `generate_recorder.py` then `apply_boot_buttons.py` (KiCad 10 `python.exe`) | Places SW_BOOT / SW_RST on the live board and mazes the stubs. Does **not** wipe copper. Do not run `generate_pcb.py`. |
| JST-PH BT1 / C21 BAT cap | `generate_recorder.py` then `apply_jst.py` (KiCad 10 `python.exe`) | Swaps the 7.8 mm solder-wire land for `JST_PH_S2B-PH-K`, places C21, mazes VBAT. Does **not** wipe copper. |
| Footprint XY | `placement.json` and `recorder.kicad_pcb` together | Keep them twins. `check_placement.py` now compares them part by part and fails on drift. Also update `hardware/cad/params.json` / `case.scad` if a wall cut or pocket moves. |
| An LCSC order code, or which parts JLC assembles | the LCSC column of `docs/bom.md`, or the footprint's `exclude_from_pos_files` / `exclude_from_bom` flag in the board | `python scripts/check_gates.py` rewrites `jlcpcb_bom.csv` and `jlcpcb_cpl.csv`. Never hand-edit those two. |
| A clean placement rebuild | `generate_pcb.py` (KiCad 10 `python.exe`, not system Python) | This **wipes** copper. Re-pour planes and re-route after. Do not run it as a status check. |
| Planes | `route_pcb.py --planes-only` (same KiCad interpreter) | Loads the existing board. Does not move parts. |
| Signal traces | `recorder.kicad_pcb` (KiCad, `route_pcb.py`, or both) | `route_pcb.py` with no flag clears copper, hand-routes and locks the awkward parts, then drives freerouting and repairs until DRC is clean. `--finish-only` just drops stub vias, re-seats silk and refreshes `placement.json`. |
| Envelope / case | `params.json`, `params.scad`, `case.scad` | `python hardware/cad/check_envelope.py`. That check models the lid battery fence, not just the pouch, and twins SP1 XY to `placement.json`. |
| GPIO map | `hardware/kicad/pins.py`, `firmware/boards/custom.h`, and `pinmap.md` | `check_pins.py` is a consistency check. Change all three. |
| MCU SKU | `params.json` `mcu` | Update schematic sources and regenerate sheets. |

`scripts/check_gates.py` reads the files already on disk. It does not design the board. A red check is a todo. A green `check_gates` is not a JLCPCB go-ahead by itself.

Official DRC is `kicad-cli pcb drc` on `recorder.kicad_pcb`. The Python file named `check_drc.py` is an outline-and-hole check, not copper DRC.

Custom SMT bring-up: `docs/bringup-custom.md`.
