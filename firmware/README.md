# Firmware

Portable recorder core in `core/` plus an ESP-IDF app that runs on:

| Board | Capture | Playback | SD | Notes |
| --- | --- | --- | --- | --- |
| ESP32-S3-Korvo-2 | ES7210 mics | ES8311 + NS4150 | 1-bit SDMMC | Phase 0 default. I2S clocks follow Espressif (S3 master). |
| ESP-BOX / BOX-3 | ES7210 | ES8311 + PA | none on the main unit | Use Korvo if you need on-board SD. |
| Custom PCB | ES8311 ADC | ES8311 DAC + NS4150 | 4-bit SDMMC | Codec is I2S master (12.288 MHz oscillator → MCLK). Pin map: `hardware/kicad/pinmap.md`. |

## Buttons

- **Short press** — start or stop a recording (`/recordings/YYYYMMDD-HHMMSS.wav`, 48 kHz 16-bit mono PCM)
- **Double press** — play the last file (press again to stop)
- **Long press (~1.5 s)** — deep sleep; wake on the same button (custom PCB)

A host MSC mount wins. Record and play stop, TinyUSB owns the card, no new recordings until unmount. 5 V on VBUS is not that event. Phase 0 with MSC off, or no card, keeps recording on USB power.

## Time

The S3 RTC resets on battery pull. After a USB dump, put `set_time.txt` at the volume root with one line, UTC `YYYY-MM-DD HH:MM:SS`:

```
2026-08-28 18:30:00
```

The app applies it on boot and after USB unmount, then deletes the file.

## Build

ESP-IDF v5.1 or newer (`esp_codec_dev` + TinyUSB):

```bash
cd firmware
idf.py set-target esp32s3
idf.py menuconfig   # Pixel Snap Voice → board
idf.py build
idf.py -p COMx flash monitor
```

Disable `CONFIG_PSV_USB_MSC` if you only want an SD reader for Phase 0.

Host-side tests (no IDF):

```bash
cmake -S sim/host -B build/host
cmake --build build/host
```
