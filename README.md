# pixel-snap-voice

A one-off slim rectangular **voice-note recorder** that snaps to the back of a **Google Pixel 10** using Pixelsnap / Qi2 magnets (MagSafe-style accessory rings work). It records raw WAV files, charges and dumps data over USB-C, and leaves transcription to a computer.

This repo holds hardware, firmware, simulation, and (later) a local transcription helper. The first board is meant to be ordered from quick-turn services after the sims pass — not invented from unsolved problems.

## What it is

- ESP32-S3-MINI-1U, **ES8311 codec** (I2S master), analog MEMS mic, class-D speaker (or headphone jack if thickness loses)
- 16-bit PCM WAV, **48 kHz** mono (~173 MB/hour)
- USB Mass Storage when plugged into a computer
- No on-device transcription, no Wi-Fi in v1, no wireless charging through the accessory

MCU choice and why we did **not** switch off Espressif: [`docs/audio-platform.md`](docs/audio-platform.md).

## Repo layout

| Path | Role |
| --- | --- |
| [`docs/architecture.md`](docs/architecture.md) | Electrical + mechanical constraints |
| [`docs/audio-platform.md`](docs/audio-platform.md) | Why ESP32-S3 + codec, not a different MCU |
| [`docs/bom.md`](docs/bom.md) | Living bill of materials |
| [`docs/manufacturing.md`](docs/manufacturing.md) | JLCPCB / print / CNC |
| [`docs/phase0-bringup.md`](docs/phase0-bringup.md) | Off-the-shelf DevKit path before a custom PCB |
| [`firmware/`](firmware/) | ESP-IDF app + portable recorder/WAV core |
| [`sim/host/`](sim/host/) | `HOST_SIM` HAL, tests, PC WAV fixture |
| [`sim/spice/`](sim/spice/) | USB → charger → battery → 3.3 V model |
| [`hardware/cad/`](hardware/cad/) | Parametric envelope (OpenSCAD) + keepout checker |
| [`hardware/kicad/`](hardware/kicad/) | KiCad 10 schematic / PCB / stackup notes |
| [`software/`](software/) | Local whisper.cpp CLI (`transcribe.py`) |

## Simulate first

From the repo root, with CMake and a C compiler (MSVC, MinGW, or clang):

```bash
cmake -S sim/host -B build/host
cmake --build build/host
./build/host/recorder_test      # Windows: build/host/Debug/recorder_test.exe
./build/host/recorder_sim
```

Mechanical keepouts (Python 3, no extra packages):

```bash
python hardware/cad/check_envelope.py
```

Power path (needs [ngspice](https://ngspice.sourceforge.io/)):

```bash
ngspice -b sim/spice/power_path.cir
```

## Physical phases

0. Prove capture **and playback** on an Espressif voice board (Korvo-2 / ESP-BOX) or OpenMic; Sense is recorder-core only. See [`docs/phase0-bringup.md`](docs/phase0-bringup.md).
1. Custom slim PCB + 3D-printed chassis + bought magnet ring (JLCPCB).
2. Same PCB in CNC **6061 aluminum** (not steel).

After you change the product schematic sources, run `python hardware/kicad/recorder/generate_recorder.py` then `python hardware/kicad/recorder/verify_schematic.py`. That overwrites sheets only. It does not write `recorder.kicad_pcb`. Edit the board (or rebuild it on purpose with `generate_pcb.py`) until traces and DRC are clean. Do not order boards until `python scripts/check_gates.py` is clean **and** `kicad-cli pcb drc` is clean **and** `kicad-cli` has written Gerbers from `hardware/kicad/recorder/recorder.kicad_pcb`.

## Transcription

Dump WAVs over USB, then run a local model (whisper.cpp) on the computer:

```bash
python software/transcribe.py /path/to/recordings/20260828-181742.wav
```
