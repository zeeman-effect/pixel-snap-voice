# Custom-board bring-up

Do this on the first SMT board **after** `python scripts/check_gates.py` is green. Do not power a board that failed ERC/DRC/envelope/`recorder_test`.

Gerbers + JLC BOM/CPL: `hardware/kicad/fab/`, `hardware/kicad/jlcpcb_bom.csv` and `jlcpcb_cpl.csv`. A green `check_gates.py` writes all three from `hardware/kicad/recorder/recorder.kicad_pcb`, so order from the files that run just produced. Do not power or order from an export that still fails DRC.

## Flash

USB-C is the first-flash path (ESP32-S3 USB-Serial/JTAG). After TinyUSB MSC takes the USB-C port, use the two top-actuated buttons **with the lid off**:

1. Hold **Boot** (SW_BOOT, GPIO0 to GND).
2. Tap **Reset** (SW_RST, EN to GND), then release Reset.
3. Release Boot.
4. `idf.py -p COMx flash` over USB-C, or UART0 on J1 (3V3, U0RXD, U0TXD, GND).

The 5 mm actuators sit 1.65 mm under the outer skin. A hole in 1.2 mm PETG does not reach them. Do not wire GPIO0 as a firmware button. SW1 stays the record control.

## Order of tests

1. **USB serial** — native USB-Serial/JTAG or UART0. Confirm the S3 enumerates and `idf.py monitor` shows `pixel-snap-voice on custom`.
2. **Rails** — **VDD33** at U4/U5 (MCU) vs **3V3A** at U8 LP5907. They must not be shorted together. **VSYS** at U3 OUT / U4 VIN (USB ~4.4 V or cell). **VBAT** ~3.7–4.2 V at BT1 with a pouch; it must not be strapped to VSYS. VBUS ~5 V when plugged in (J2).
3. **I2C codec** — scan address 0x18. ES8311 ACK.
4. **I2S** — codec is master. Y1 is the 12.288 MHz oscillator into ES8311 MCLK. Scope MCLK/BCLK/WS. Play a tone / loopback before trusting the mic.
5. **Mic capture** — short press records `/recordings/YYYYMMDD-HHMMSS.wav` at 48 kHz. Copy off via SD reader if MSC is not up yet. Play on a desktop.
6. **SD** — 4-bit SDMMC. `storage_sd_mount` log line.
7. **Playback** — double-press plays last file through NS4150 / SP1 (KELIKING KLJ-01304T). Check the lid grille is over the can. NS4150B runs from **VSYS**; at ~4.4 V on USB or 4.2 V on a full pouch into 8 Ω the PA can sit on the speaker's 1 W max. Firmware still advertises `pa_voltage = 5.0`, which keeps digital gain down. Confirm polarity (a left-right JLC mismatch only inverts phase; a 180° mismatch is silent) and that playback volume is comfortable, not a copper change.
8. **Charger** — USB-C 5 V into BQ24074 IN. STAT / **CHG_STAT** low while charging, ~500 mA. Board runs from VSYS with BT1 open. No brownout while recording or playing.
9. **TinyUSB MSC** — plug into a PC; recording stops; volume mounts; unplug returns to idle. Drop `set_time.txt` to set the RTC.
10. **Sleep** — long press; current should drop (U5 off). Wake on the record button.

Measure record current (PA off) and playback current. Update [`docs/bom.md`](bom.md) hours from `mAh / measured_mA`. Current pouch is **500 mAh** (~3.1 h at 160 mA) from leftover CAD volume. If measured current is worse, update the BOM and the pouch pick before a metal shell is cut.

## Time

`set_time.txt` at the volume root, one line `YYYY-MM-DD HH:MM:SS` (UTC). Applied on boot and after unmount.

## If something is dead

| Symptom | First check |
| --- | --- |
| No 3.3 V | U4, U5, solder on the module |
| Codec NACK | 3V3A (U8), I2C pull-ups, Y1 output on MCLK |
| Hiss / no mic | Analog island, mic port not against glass, MK1 bias |
| No MSC | TinyUSB config, SD still mounted by VFS, USB D+/D− swap |
| Brownout on play | USB cable, PA supply from VSYS, decoupling |
