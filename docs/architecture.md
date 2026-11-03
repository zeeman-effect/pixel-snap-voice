# Architecture

One-off Pixelsnap-compatible voice recorder. Copy known ESP32-S3 + codec + LiPo + USB MSC patterns. Do not invent wireless charging through the shell or on-device ASR. MCU vs codec rationale: [`audio-platform.md`](audio-platform.md).

## System

```
Pixel 10 (Pixelsnap / Qi2 magnets)
        |
   magnet ring + clocking magnet  (behind a 0.85 mm skin)
        |
  analog MEMS --> ES8311 ADC --I2S--> ESP32-S3 --FAT--> SD NAND
                         USB 2.0 device              USB MSC
                                |                      Wi-Fi SoftAP
                 4-pin magnetic pad (VBUS / D- / D+ / GND)
                                                   browser + WebDAV
                                |
                         BQ24073 power-path
                           |           |
                         VSYS        VBAT (pouch)
                           |
                    3.3 V digital + 2.8 V analog LDO
```

ES8311 is the **I2S master** (12.288 MHz oscillator into MCLK). The S3 is slave. Analog AVDD for the codec and the MEMS mic is a separate 2.8 V LDO (U8 LP5907-2.8, net **3V3A**) from the MCU 3.3 V rail (U4 AP2112 + U5 AP22804, net **VDD33**). The analog rail is 2.8 V because IM73A135 VDD abs max is 3.0 V; ES8311 AVDD is 1.7–3.6 V. A buck is preferred for battery life; this spin uses the LDO.

When USB is plugged in: stop recording, turn Wi-Fi off, expose `/recordings` as a USB Mass Storage volume, charge. Double-press on the custom board starts a WPA2 access point and serves the same folder in a browser (and read-only WebDAV). When idle: deep sleep, button wake. The radio stays off until that share gesture.

## Solved references

- Firmware / WAV-to-storage / USB mount: [ESP32-OpenMic](https://codeberg.org/RevK/ESP32-OpenMic)
- Early bring-up: ESP32-S3-Korvo-2 / ESP-BOX (ES8311 + analog mic + PA); Sense is recorder-core only
- Magnet geometry: MagSafe accessory array / Qi2 MPP ring (commodity rings), not a custom magnet design

## Electrical

| Block | Choice | Notes |
| --- | --- | --- |
| MCU | ESP32-S3-MINI-1U (≥8 MB flash) | Native USB. Same pins as MINI-1, 15.4 × 15.4 mm, no PCB antenna. **Not** the audio bottleneck. |
| Codec | Everest ES8311, I2S master, 12.288 MHz oscillator → MCLK | PGA/ALC/ADC + DAC + HP. Dedicated analog LDO (U8). No XI/XO on this codec. |
| Mic | Analog MEMS: IM73A135 (~73 dBA) | Pin 3 is OUT−, left open; C15 couples OUT+. VDD 2.8 V. Fallback: ICS-43434 I2S (65 dBA). **INMP441 is EOL.** |
| Playback | None on the custom board | Dump WAVs over USB. Korvo / ESP-BOX / host sim still play. ES8311 AOUT is open |
| Storage | MK MKDV4GCL-ABB 512 MB SD NAND (FAT) | LGA-8, 8.0 × 6.0 mm, LCSC C7500178. Pin order is CLK on 3, VSS on 4, CMD on 5, VDD on 8; CS and Zetta parts use the same order and fit the same land. Firmware formats FAT if the chip is blank. Prototype capacity, picked on cost |
| Charge + USB | C6276862 4-pin magnetic pad (J2) | 2.0 mm female. Lid dishes over the pad so the gold is 0.15 mm proud of that local face. Pins 1 VBUS, 2 D−, 3 D+, 4 GND. Cable male C5126845. No CC / Rd. No USB-PD |
| Charge | BQ24073RGTR, USB500 ~500 mA (EN1/EN2, ISET 1.8 kΩ) | Power-path: **VSYS** = OUT at 4.4 V, **VBAT** = pouch only. Pin 8 is ground. Pin 15 TD is held low. Charge LED on STAT. No fuel gauge |
| 3.3 V | Buck preferred (efficiency); LDO this spin (U4 AP2112 + U5 AP22804 → **VDD33**) | U4 VIN from **VSYS**. Keep the regulator and any later switching node away from the mic |
| Battery | Jauch LP305166JH pack, pigtail soldered to B.Cu BT1 pads | DigiKey `LP305166JH-PCM-2-WIRES-70MM` (13278052): 66 × 51.5 × 3.3 mm, 3.7 V, 1200 mAh min / 1220 mAh typ, PCM and 70 mm leads. Taped to the board underside at (0, 0), kapton-wrapped. Four tray posts carry the board. The pack has a PCM; this board has no second protector |
| Controls | 1 user tactile (SW1): short = record, double = Wi-Fi share on the custom board (play on Korvo), long = sleep. Download is TP_BOOT / TP_EN / GND / 3V3 pads | 1 LED: record / share / charge / error |
| RF | MINI-1U IPEX + lid FPC | W.FL / I-PEX MHF III pigtail (Inventek B24P-W) into a lid well over U1. Adhesive 2.4 GHz 30 × 5 mm patch on the PETG ceiling, phone-bottom end, away from J2. Tape mark is 30 × 5 mm at (−2, −33); do not enlarge the 7 mm well. Keep the PCB-antenna MINI-1 off this board. SoftAP, WPA2, TX capped near 10 dBm. Bluetooth stays off. |

### Audio format

- Container: WAV (RIFF)
- Encoding: PCM, 16-bit signed little-endian
- Rate / channels: **48 kHz**, mono (16 kHz sounds telephone-narrow on playback; codecs expect 48 k)
- Path: `/recordings/YYYYMMDD-HHMMSS.wav`
- Size: 48000 × 2 bytes/s = **96 kB/s ≈ 5.5 MB/min**. A full pouch (~7.5 h) is about 2.5 GB. The prototype's 4 Gbit / 512 MB NAND holds about 1.4 h, so it fills before the pouch empties; a final product wants 32 Gbit / 4 GB.
- Do not store 24-bit files; 16-bit already exceeds a 65–74 dBA capsule. Keep 24-bit on the I2S wire if the mic provides it.

### Power budget (v1 estimate)

MCU-only 126 mA was optimistic. With codec and SD the working number is about 160 mA from the cell. Current pouch is the Jauch **1200 mAh** pack taped to B.Cu (~7.5 h). Wi-Fi share adds transmit peaks of a few hundred milliamps on U4 (AP2112, 600 mA). Firmware caps TX near 10 dBm and turns the codec off while sharing. Re-measure on the SMT board. Idle deep-sleep is dominated by the charger IC and any always-on LDOs. Keep a true load switch on the 3.3 V rail. The buck already preferred on this 3.3 V rail is the follow-up if share browns out on a low cell.

### Magnetic pad

- J2 is C6276862 (YZ103915020T-04025-02), a 22.30 × 7.70 × 2.00 mm stadium, 4 pins. No CC resistors: the cable is USB-A.
- VBUS to charger IN through a PTC. The pad is the only 5 V inlet.
- **BT1** is two SMT pads on **B.Cu** at (−17, 35) for a 1S pouch pigtail on VBAT, west of J2. Pad 1 is the west land. Do not put 5 V on BT1. Do not strap **VSYS** (charger OUT) to VBAT. C21 (10 µF) sits on VBAT next to U3 so BAT has local ceramic when the pouch is off.
- D+/D− to ESP32-S3 USB PHY through U7
- Click-test C5126845 before freezing the pinout. Do not implement PD sink for v1

## Mechanical — Pixel 10 + Pixelsnap

Sources: GSMArena / Google store for body size; WPC Qi2 / MagSafe accessory practice for the ring. **Magnet center on the Pixel 10 must be calipered** before a metal shell is cut; CAD parameters live in [`hardware/cad/params.json`](../hardware/cad/params.json).

| Item | Value | Status |
| --- | --- | --- |
| Phone body | 152.8 × 72 × 8.6 mm | Published |
| Camera bar extra thickness | ~3.4 mm | Published (Pixel 9-class bar; confirm on device) |
| Camera bar length along height | parameterized, default 24 mm from top | **Measure** |
| Qi2 / MagSafe accessory ring | OD 54.1 / ID 46 / 1.5 mm N52, steel plate already on the ring | totalElement R54X46X15MMN52-5PK |
| Clocking magnet | 12 × 5 × 1.5 mm block in a 5 × 12 mm well, long side toward 6 o'clock | Same pack. Stops the case spinning |
| Phone-side skin | 0.85 mm aluminum or PETG, no hole | Apple measures accessory flux at 0.85 mm. JLCCNC's recommended metal wall is 0.8 mm |
| Accessory envelope (compact-final) | 62 × 88 × 10.65 mm | Current numbers in `hardware/cad/params.json`. PCB is 59.6 × 85.6 mm. Lid is natural translucent PETG, 3.80 mm. Tray is 6.85 mm: 0.85 mm skin, blind magnet wells, four M1.6 posts (PETG then 6061). The pouch hangs from B.Cu. `main` still holds the 67 × 90 × 9 prototype. |
| Pixelsnap center | 85 mm from top, 36 mm from left | **Caliper before CNC** |
| Chassis | Local PETG first; CNC **6061** copy is `variant=metal` in `case.scad` | `check_dfm.py` is green for JLCCNC / PCBWay CNC. **Not steel** — steel shorts the magnetic path |

### Stack (phone glass → outside)

1. 0.85 mm non-ferrous skin, closed. The magnets sit in blind wells behind it
2. N52 ring (steel plate already glued on) and the clocking magnet, glued steel-face up
3. ~0.15 mm air, then the kapton-wrapped pouch taped to B.Cu
4. PCB on four 5.0 mm M1.6 posts (MCU, codec, mic, magnetic pad, SD NAND)
5. Natural translucent PETG lid over the F.Cu parts; TPU pill in the phone-left wall when snapped on. IPEX well over U1; FPC taped to the inner ceiling toward the phone-bottom end (J2 is the camera end)

### Keepouts (enforced by `hardware/cad/check_envelope.py`)

- Accessory outline must **not overlap the camera bar** in the XY plane when snapped.
- Magnetic pad on the **lid face**; the cable must miss the phone body.
- Mic acoustic port on a **free long edge**, not into the glass, or recordings go muffled.
- Magnet ring must stay inside the accessory outline.
- Analog codec island and mic bias stay off **VDD33**.

### Metal / magnets / OIS

Use an **aluminum or plastic** shell. The only steel is the plate already glued to the bought ring, on the side away from the phone. The clocking magnet sits on the bottom of the ring, away from the camera bar (OIS / magnetometer).

## Firmware split

Portable core (`firmware/core`) builds two ways:

- `HOST_SIM` — POSIX files, fixture WAV or generated PCM, tests in `sim/host`
- `ESP_PLATFORM` — ESP-IDF `app_main`, ES8311 duplex I2S (`esp_codec_dev`), SD, USB MSC, Wi-Fi share, deep sleep

State machine: `IDLE` → `RECORDING` or `PLAYING` or `WIFI_SHARE` → `IDLE`. A host **MSC mount** forces `USB_MSC` (record, play, and Wi-Fi stop). VBUS alone does not. No storage, or `CONFIG_PSV_USB_MSC` off, means USB power does not take the volume. The custom board formats the soldered NAND if it has no FAT. Share is the recorder’s own network at `http://192.168.4.1`. It does not join a home Wi-Fi.

## Out of scope

- On-device transcription
- Bluetooth file transfer (this S3 is BLE-only; leave `CONFIG_BT_ENABLED=n`)
- SMB, HTTPS, joining a home Wi-Fi
- Deleting files from the phone, streaming while recording, a phone app
- Charging the phone through this accessory
- MagSafe / Qi2 certification
- Waterproofing
- Android app while snapped on (USB-OTG geometry is awkward)
