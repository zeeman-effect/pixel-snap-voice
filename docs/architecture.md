# Architecture

One-off Pixelsnap-compatible voice recorder. Copy known ESP32-S3 + codec + LiPo + USB MSC patterns. Do not invent wireless charging through the shell or on-device ASR. MCU vs codec rationale: [`audio-platform.md`](audio-platform.md).

## System

```
Pixel 10 (Pixelsnap / Qi2 magnets)
        |
   magnet ring + steel shunt  (accessory side)
        |
  analog MEMS --> ES8311 ADC --I2S--> ESP32-S3 --FAT--> microSD
  speaker/HP  <-- ES8311 DAC + PA     |                    |
                         USB 2.0 device              USB MSC
                                |
                    USB-C 5 V sink + CC 5.1k
                                |
                         LiPo charger --> 3.3 V + analog LDO
```

ES8311 is the **I2S master** (12.288 MHz oscillator into MCLK). The S3 is slave. Analog AVDD for the codec is a separate LDO (U8 LP5907) from the MCU 3.3 V rail (U4 AP2112 + U5 AP22804, net **VDD33**). A buck is preferred for battery life; this spin uses the LDO.

When USB is plugged in: stop recording, expose `/recordings` as a USB Mass Storage volume, charge. When idle: deep sleep, button wake.

## Solved references

- Firmware / WAV-to-storage / USB mount: [ESP32-OpenMic](https://codeberg.org/RevK/ESP32-OpenMic)
- Early bring-up: ESP32-S3-Korvo-2 / ESP-BOX (ES8311 + analog mic + PA); Sense is recorder-core only
- Magnet geometry: MagSafe accessory array / Qi2 MPP ring (commodity rings), not a custom magnet design

## Electrical

| Block | Choice | Notes |
| --- | --- | --- |
| MCU | ESP32-S3-MINI-1U (≥8 MB flash) | Native USB. Same pins as MINI-1, 15.4 × 15.4 mm, no PCB antenna. **Not** the audio bottleneck. |
| Codec | Everest ES8311, I2S master, 12.288 MHz oscillator → MCLK | PGA/ALC/ADC + DAC + HP. Dedicated analog LDO (U8). No XI/XO on this codec. |
| Mic | Analog MEMS: IM73A135 or ICS-40730 (~73–74 dBA) | Fallback: ICS-43434 I2S (65 dBA). **INMP441 is EOL.** |
| Playback | NS4150B into KELIKING KLJ-01304T-08R07W (13 mm SMD, LCSC C18186315) | 8 Ω 0.7 W can JLC can place. If 9 mm loses: 3.5 mm jack on ES8311 HP |
| Storage | Low-profile microSD (FAT32) | Switch to eMMC only if CAD proves SD is too thick |
| USB-C | 5 V sink only, 5.1 kΩ CC1/CC2 pulldowns, USB 2.0 | No USB-PD |
| Charge | MCP73831 or BQ24074 class, 500 mA default | Charge LED only; no fuel gauge in v1 |
| 3.3 V | Buck preferred (efficiency); LDO this spin (U4 AP2112 + U5 AP22804 → **VDD33**) | Keep the regulator and any later switching node away from the mic |
| Battery | Single-cell LiPo pouch, size from leftover volume | See battery-life estimate below |
| Controls | 1 tactile: short = record, double = play last, long = sleep | 1 LED: record / play / charge / error |
| RF | MINI-1U IPEX, no cable in v1 | A PCB antenna would sit next to a steel shunt and later an aluminum shell. Wi-Fi off in firmware. |

### Audio format

- Container: WAV (RIFF)
- Encoding: PCM, 16-bit signed little-endian
- Rate / channels: **48 kHz**, mono (16 kHz sounds telephone-narrow on playback; codecs expect 48 k)
- Path: `/recordings/YYYYMMDD-HHMMSS.wav`
- Size: 48000 × 2 bytes/s = **96 kB/s ≈ 173 MB/hour** → ~46 hours on 8 GB
- Do not store 24-bit files; 16-bit already exceeds a 65–74 dBA capsule. Keep 24-bit on the I2S wire if the mic provides it.

### Power budget (v1 estimate)

MCU-only 126 mA was optimistic. With codec and SD, PA off, the working number is about 160 mA from the cell. Current pouch is **500 mAh** from leftover CAD volume (~3.1 h). Change the pouch if leftover volume or measured current changes. Re-measure on the SMT board. Idle deep-sleep is dominated by the charger IC and any always-on LDOs. Keep a true load switch on the 3.3 V rail.

### USB-C

- CC1 and CC2 each 5.1 kΩ to GND (UFP / sink)
- VBUS to charger input through a PTC or ideal-diode as the reference design allows
- D+/D− to ESP32-S3 USB PHY (or USB-Serial/JTAG pins per module datasheet)
- Do not implement PD sink for v1

## Mechanical — Pixel 10 + Pixelsnap

Sources: GSMArena / Google store for body size; WPC Qi2 / MagSafe accessory practice for the ring. **Magnet center on the Pixel 10 must be calipered** before a metal shell is cut; CAD parameters live in [`hardware/cad/envelope.scad`](../hardware/cad/envelope.scad).

| Item | Value | Status |
| --- | --- | --- |
| Phone body | 152.8 × 72 × 8.6 mm | Published |
| Camera bar extra thickness | ~3.4 mm | Published (Pixel 9-class bar; confirm on device) |
| Camera bar length along height | parameterized, default 24 mm from top | **Measure** |
| Qi2 / MagSafe accessory ring | OD ~56 mm, ID ~44 mm, thick ~1.0–1.2 mm | Commodity part |
| MagSafe accessory array (Apple-style) | often OD 54 × ID 46 × 1.1 mm | Accept either; pocket to the part you buy |
| Steel shunt | thin plate **behind** the ring (away from the phone) | Required for hold strength |
| Accessory envelope (v1 target) | 67 × 90 × 9 mm | Current numbers in `hardware/cad/params.json`. Edit them if the case needs to move. |
| Pixelsnap center | 85 mm from top, 36 mm from left | **Caliper before CNC** |
| Chassis | 3D-print first; CNC **6061 aluminum** later | **Not steel** — steel shorts the magnetic path |

### Stack (phone glass → outside)

1. Magnet ring + adhesive
2. Steel shunt
3. PCB (MCU, codec, mic, PA, USB-C, SD)
4. LiPo pouch
5. Back shell (plastic proto / 6061)

### Keepouts (enforced by `hardware/cad/check_envelope.py`)

- Accessory outline must **not overlap the camera bar** in the XY plane when snapped.
- USB-C on a **short edge**; overmold keepout must not intersect the phone body.
- Mic acoustic port on a **free long edge**, not into the glass, or recordings go muffled.
- Magnet ring must stay inside the accessory outline.
- Analog codec island and mic bias stay off **VDD33**; PA LC/ferrite away from the magnet ring.

### Metal / magnets / OIS

Use an **aluminum or plastic** shell. Put ferromagnetic material only as the designed shunt behind the ring. The phone already expects a MagSafe-style ring at the Pixelsnap location; do not add extra magnets near the camera bar (OIS / magnetometer).

## Firmware split

Portable core (`firmware/core`) builds two ways:

- `HOST_SIM` — POSIX files, fixture WAV or generated PCM, tests in `sim/host`
- `ESP_PLATFORM` — ESP-IDF `app_main`, ES8311 duplex I2S (`esp_codec_dev`), SD, USB MSC, deep sleep

State machine: `IDLE` → `RECORDING` or `PLAYING` → `IDLE`. A host **MSC mount** forces `USB_MSC` (record and play stop). VBUS alone does not. No card, or `CONFIG_PSV_USB_MSC` off, means USB power does not take the card.

## Out of scope

- On-device transcription
- Wi-Fi
- Charging the phone through this accessory
- MagSafe / Qi2 certification
- Waterproofing
- Android app while snapped on (USB-OTG geometry is awkward)
