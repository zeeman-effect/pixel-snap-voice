# Agent notes

Keep this file in sync with the project. When the goal or the current solution changes, update the matching sections here.

**How to respond:** Be brief. Prefer plain language over extra jargon. Write so a non-specialist can follow the point, without watering down the technical facts. Short sentences, define terms on first use, then keep going.

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

## Current solution

**Architecture:** ESP32-S3-MINI-1U MCU (IPEX, no cable in v1), Everest ES8311 codec as I2S master (12.288 MHz oscillator into MCLK; the S3 is slave), analog MEMS microphone, class-D speaker (or headphone jack if 9 mm is too thick), microSD, USB-C as a 5 V sink only. Analog codec power is a separate low-noise regulator from the MCU supply. Chassis is 3D-print first, then CNC 6061 aluminum. Not steel, which would steal hold from the magnet ring. The module SKU is the no-PCB-antenna MINI-1U because v1 has no radio and a steel shunt plus later aluminum shell sit next to the MCU. Full electrical and mechanical notes: `docs/architecture.md`. Why this MCU/codec pair: `docs/audio-platform.md`. U1 numbers live in `hardware/cad/params.json` under `mcu`. The product KiCad project is `hardware/kicad/recorder/` (schematic + PCB).

Those are the current choices. Change them when the envelope, parts, or bring-up says they are wrong, and update the docs in the same pass.

**Firmware:** A portable recorder core in `firmware/core` (state machine, WAV headers, timestamped files, playback). It builds two ways: `HOST_SIM` on a PC (`sim/host`) and `ESP_PLATFORM` with ESP-IDF on hardware. States: idle → recording / playing → idle. A host MSC mount forces USB mass-storage and stops record or play. VBUS alone does not.

**Transcription:** Dump WAVs over USB, then `python software/transcribe.py` (whisper.cpp) on the computer. Nothing in `software/` runs on the recorder in v1.

## Status (will go stale)

Update this section when it stops being true.

- Host sim + `recorder_test` (including playback) build from `sim/host/CMakeLists.txt`.
- Phase 0 ESP-IDF app is in `firmware/` (Korvo-2 / ESP-BOX / custom pin maps). CAD is in `hardware/cad` (`params.json` + `case.scad`, draft PETG).
- Product KiCad is `hardware/kicad/recorder/` (open `recorder.kicad_pro`). Sheets come from `generate_recorder.py`. The board file is `recorder.kicad_pcb`. Footprint XY is `hardware/kicad/recorder/placement.json`.
- The PETG tray ducts MK1's B.Cu NPTH under the board to the right-wall mic port. MK1 is on F.Cu.
- The board has Edge.Cuts, H1–H4, and copper pours. Signals are still open. That is the next design job, not a reason to stop.
- Current pouch size is 500 mAh from leftover CAD volume.
- Pixel body and Pixelsnap numbers are published defaults until someone calipers a phone.
- Computer-side whisper.cpp wrapper is `software/transcribe.py`.

Do not send Gerbers until `python scripts/check_gates.py` is clean **and** `kicad-cli` wrote `hardware/kicad/fab/` from `recorder.kicad_pcb` **and** `kicad-cli pcb drc` is clean. Those are ship gates. They are not a reason to leave the board unedited.

## How to change the hardware

Close KiCad before running the generators. Lock files look like `~recorder.kicad_pro.lck`.

| If you need to change | Edit | Then |
| --- | --- | --- |
| Nets, parts, pins on the schematic | `generate_recorder.py`, `PSV.kicad_sym` | `python hardware/kicad/recorder/generate_recorder.py` then `python hardware/kicad/recorder/verify_schematic.py`. This overwrites sheets only. It does not write the PCB. |
| Footprint XY | `placement.json` and `recorder.kicad_pcb` together | Keep them twins. Also update `hardware/cad/params.json` / `case.scad` if a wall cut or pocket moves. |
| A clean placement rebuild | `generate_pcb.py` (KiCad 10 `python.exe`, not system Python) | This **wipes** copper. Re-pour planes and re-route after. Do not run it as a status check. |
| Planes | `route_pcb.py --planes-only` (same KiCad interpreter) | Loads the existing board. Does not move parts. |
| Signal traces | `recorder.kicad_pcb` (KiCad, `route_pcb.py`, or both) | The script autorouter is experimental. Use it as a start if it helps, then fix what DRC and a glance say is wrong. Do not refuse to route. |
| Envelope / case | `params.json`, `params.scad`, `case.scad` | `python hardware/cad/check_envelope.py` |
| GPIO map | `hardware/kicad/pins.py`, `firmware/boards/custom.h`, and `pinmap.md` | `check_pins.py` is a consistency check. Change all three. |
| MCU SKU | `params.json` `mcu` | Update schematic sources and regenerate sheets. |

`scripts/check_gates.py` reads the files already on disk. It does not design the board. A red check is a todo. A green `check_gates` is not a JLCPCB go-ahead by itself.

Official DRC is `kicad-cli pcb drc` on `recorder.kicad_pcb`. The Python file named `check_drc.py` is an outline-and-hole check, not copper DRC.

Custom SMT bring-up: `docs/bringup-custom.md`.
