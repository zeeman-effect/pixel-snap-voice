# Phase 0 — DevKit bring-up (before a custom PCB)

Prove **capture, playback, WAV headers, and storage** on off-the-shelf hardware. You can still design the custom board in parallel. Do not send Gerbers until this path has recorded a playable 48 kHz WAV, unless you accept spinning the board.

MCU stays ESP32-S3. The missing pieces on a Sense-only board are the **codec and amp**. Prefer a voice-oriented Espressif board for Phase 0.

## Preferred board

**ESP32-S3-Korvo-2** or **ESP-BOX** (ES8311 + analog mic + class-D PA). This is the same audio path as the custom PCB.

Close second: [ESP32-OpenMic](https://codeberg.org/RevK/ESP32-OpenMic) (S3 module + ICS-43434 + MAX98357A + microSD + USB MSC). Faster MSC, slightly worse capture SNR.

**Seeed XIAO ESP32-S3 Sense** is only for the portable recorder core (buttons, WAV writer, SD). It cannot prove headphone/speaker quality.

## What “done” means

1. Button starts and stops a recording.
2. File appears as `/recordings/YYYYMMDD-HHMMSS.wav`.
3. WAV is **48 kHz**, 16-bit, mono PCM and plays in a desktop player.
4. Device can play that file (or a fixture WAV) through the board speaker or HP jack.
5. USB-C: pull the SD card at first; TinyUSB MSC comes after the core is stable.
6. Battery: runs from LiPo and charges from USB-C without browning out while recording or playing.

On-device transcription, Bluetooth, and the magnet shell are **not** Phase 0. Wi-Fi share can be proven on Korvo-2 using that board’s antenna (recipe below). The custom PCB still needs the lid pigtail.

## Toolchain

See [`firmware/README.md`](../firmware/README.md) for board Kconfig, buttons, and `set_time.txt`.

```bash
cd firmware
idf.py set-target esp32s3
idf.py build
idf.py -p COMx flash monitor
```

### Korvo SoftAP prove-out

Prove SoftAP + `http://192.168.4.1` on Korvo-2 **before** the custom PCB. Default Phase 0 Korvo still plays on double-press; this overlay flips that gesture to share.

MSC is **off** on the overlay so Korvo keeps USB-Serial/JTAG (native D+/D− are reserved). Custom-board MSC uses `TINYUSB_MSC_EVENT_MOUNT_CHANGED` and exclusive NAND. Pull the SD card and use a reader for this prove.

```bash
cd firmware
idf.py -B build/korvo-share \
  -D SDKCONFIG="$PWD/build/korvo-share/sdkconfig" \
  -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.korvo_wifi_share" \
  set-target esp32s3
idf.py -B build/korvo-share \
  -D SDKCONFIG="$PWD/build/korvo-share/sdkconfig" \
  build
# Flash only if a Korvo is plugged in:
# idf.py -B build/korvo-share -D SDKCONFIG="$PWD/build/korvo-share/sdkconfig" -p COMx flash monitor
```

Same flags via menuconfig on a normal `sdkconfig`: **Pixel Snap Voice → Double-press toggles Wi-Fi share**, and unset **TinyUSB mass storage**.

On the board: short press records, double-press any Korvo key starts **PixelSnapVoice** / **voicenote1**. Join that network and open `http://192.168.4.1`.

Use `esp_codec_dev` + the Korvo/ESP-BOX ES8311 example for duplex I2S. Host-side iteration (no hardware):

```bash
cmake -S sim/host -B build/host
cmake --build build/host
./build/host/recorder_test
./build/host/recorder_sim
```

## Korvo-2 / ESP-BOX

Follow Espressif’s user guide for I2C to ES8311, I2S pins, PA enable, and analog mic bias. Set the codec as **I2S master** if the board clock allows; otherwise match the Espressif example and accept S3-generated clocks for Phase 0 only. Custom PCB must use the 12.288 MHz oscillator into ES8311 MCLK in [`audio-platform.md`](audio-platform.md).

## Sense (recorder core only)

| Function | Sense (typical — check current wiki) |
| --- | --- |
| PDM clock / data | Sense mic header |
| microSD | On-board SPI SD |
| Record button | D1 (GPIO1) to GND, pull-up |
| USB / battery | On-board USB-C, BAT± |

Leave Bluetooth off. Enable Wi-Fi share on Korvo only to prove the file page.

## USB Mass Storage

Phase 0 can skip MSC and use an SD reader. When the portable core is stable, enable ESP-IDF TinyUSB MSC (OpenMic `sdusb`): recording disabled while mounted.

## Power notes

- USB 5 V and LiPo at once is normal on XIAO / Korvo.
- Measure record **and playback** current; codec + PA are extra vs the MCU-only estimate in architecture.
- If the board resets when the mic + SD + PA start, fix the cable/hub first, then decoupling on the custom PCB.

## What Phase 0 does not prove

- Magnet alignment on a Pixel 10
- Camera-bar clearance
- USB-C plug vs phone body while snapped on
- Analog LDO / ES8311 master clock as laid out on the custom PCB
- 6061 chassis

After a playable WAV exists **and** on-board playback works, move to CAD fit and KiCad — still no fab order.
