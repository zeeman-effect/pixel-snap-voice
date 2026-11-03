# Firmware

Portable recorder core in `core/` plus an ESP-IDF app that runs on:

| Board | Capture | Playback | SD | Notes |
| --- | --- | --- | --- | --- |
| ESP32-S3-Korvo-2 | ES7210 mics | ES8311 + NS4150 | 1-bit SDMMC | Phase 0 default. I2S clocks follow Espressif (S3 master). |
| ESP-BOX / BOX-3 | ES7210 | ES8311 + PA | none on the main unit | Use Korvo if you need on-board SD. |
| Custom PCB | ES8311 ADC | none (USB or Wi-Fi dump) | 4-bit SDMMC (soldered 512 MB NAND) | Codec is I2S master (12.288 MHz oscillator → MCLK). Formats FAT if the chip is blank. Double-press toggles Wi-Fi share. Pin map: `hardware/kicad/pinmap.md`. |

## Buttons

- **Short press** — start or stop a recording (`/recordings/YYYYMMDD-HHMMSS.wav`, 48 kHz 16-bit mono PCM)
- **Double press** — play the last file on Korvo / ESP-BOX (press again to stop). On the custom board it starts or stops Wi-Fi share. On Korvo, merge `sdkconfig.korvo_wifi_share` (or menuconfig **Double-press toggles Wi-Fi share**) to prove `http://192.168.4.1` on that board’s antenna.
- **Long press (~1.5 s)** — deep sleep; wake on the same button (custom PCB)

A host MSC mount wins. Record, play, and Wi-Fi stop. TinyUSB unmounts VFS and owns the NAND exclusively; unplug remounts VFS. 5 V on VBUS is not that event. Phase 0 with MSC off, or no card, keeps recording on USB power.

Wi-Fi share is the recorder’s own network **PixelSnapVoice** / **voicenote1**. Join it, then open `http://192.168.4.1` for the file page (play and download) or a read-only WebDAV folder. The radio stays off until this gesture. Do not transmit on the custom board with the IPEX unmated.

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

On the custom board, the first flash needs nothing pressed. After that, TinyUSB owns native USB, so put the recorder in download mode first: with the cable in the computer, long-press to sleep, then press and hold the record button 5 s until the LED goes solid, and let go (`CONFIG_PSV_BOOT_DOWNLOAD_HOLD`, `hal/download_mode.c`). The TP_BOOT / TP_EN pads are the fallback. Full steps: [`docs/bringup-custom.md`](../docs/bringup-custom.md#flash).

Disable `CONFIG_PSV_USB_MSC` if you only want an SD reader for Phase 0.

### Korvo SoftAP prove-out (before the custom PCB)

Default Korvo still **plays** on double-press. This overlay switches that gesture to SoftAP share and leaves MSC off so Korvo USB-Serial/JTAG keeps the native port (Korvo D+/D− are reserved). Custom-board MSC uses `TINYUSB_MSC_EVENT_MOUNT_CHANGED`.

```bash
cd firmware
# Isolated config — does not overwrite a normal Phase 0 sdkconfig
idf.py -B build/korvo-share \
  -D SDKCONFIG="$PWD/build/korvo-share/sdkconfig" \
  -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.korvo_wifi_share" \
  set-target esp32s3
idf.py -B build/korvo-share \
  -D SDKCONFIG="$PWD/build/korvo-share/sdkconfig" \
  build
# Flash only if a Korvo is on the port:
# idf.py -B build/korvo-share -D SDKCONFIG="$PWD/build/korvo-share/sdkconfig" -p COMx flash monitor
```

Or keep the default `sdkconfig` and use the menu:

```bash
cd firmware
idf.py set-target esp32s3
idf.py menuconfig
# Pixel Snap Voice → Double-press toggles Wi-Fi share = Y
# Pixel Snap Voice → TinyUSB mass storage on the SD volume = N
idf.py build
```

Then: record a WAV (short press), double-press any Korvo key, join **PixelSnapVoice** / **voicenote1**, open `http://192.168.4.1`.

Host-side tests (no IDF):

```bash
cmake -S sim/host -B build/host
cmake --build build/host
```
