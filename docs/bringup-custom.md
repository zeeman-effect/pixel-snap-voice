# Custom-board bring-up

Do this on the first SMT board **after** `python scripts/check_gates.py` is green. Do not power a board that failed ERC/DRC/envelope/`recorder_test`.

Gerbers + JLC BOM/CPL: `hardware/kicad/fab/`, `hardware/kicad/jlcpcb_bom.csv`, `jlcpcb_cpl.csv`, and `jlcpcb_extra.csv`. A green `check_gates.py` writes them from `hardware/kicad/recorder/recorder.kicad_pcb`, so order from the files that run just produced. Do not power or order from an export that still fails DRC.

## Flash

The magnetic cable is the first-flash path (ESP32-S3 USB-Serial/JTAG). After TinyUSB MSC takes the port, use the F.Cu pads:

1. Hold **TP_BOOT** to **TP_GND** (GPIO0).
2. Pulse **TP_EN** to GND, then release EN.
3. Release TP_BOOT.
4. `idf.py -p COMx flash` over the magnetic USB.

There is no Boot/Reset switch and no UART header. Do not wire GPIO0 as a firmware button. SW1 stays the record control.

## Order of tests

1. **USB serial** — native USB-Serial/JTAG or UART0. Confirm the S3 enumerates and `idf.py monitor` shows `pixel-snap-voice on custom`.
2. **Rails** — **VDD33** at U4/U5 (MCU, 3.3 V) vs **3V3A** at U8 LP5907-2.8 (~2.8 V). They must not be shorted together. **3V3A is 2.8 V on purpose**: IM73A135 VDD abs max is 3.0 V. **VSYS** at U3 OUT / U4 VIN (USB ~4.4 V or cell). **VBAT** ~3.7–4.2 V at the BT1 pads with a pouch; it must not be strapped to VSYS. VBUS ~5 V when plugged in (J2).
3. **I2C codec** — scan address 0x18. ES8311 ACK.
4. **I2S** — codec is master. Y1 drives ES8311 MCLK at 12.288 MHz. Firmware leaves GPIO14 unused so the S3 does not fight Y1. Scope MCLK/BCLK/WS. If MCLK looks like two drivers on one net, stop — the S3 is still outputting. Confirm clocks before trusting the mic.
5. **Mic capture** — short press records `/recordings/YYYYMMDD-HHMMSS.wav` at 48 kHz. Copy off via USB MSC or Wi-Fi share. Play on a desktop.
6. **SD** — 4-bit SDMMC. Logs `SD card ready (VFS via TinyUSB)` then `SD mounted at /sdcard (TinyUSB)`. Blank NAND is formatted on that first TinyUSB mount.
7. **No speaker** — dump WAVs over USB or Wi-Fi share and play them on the computer or phone.
8. **Charger** — 5 V on the magnetic pad into BQ24073 IN. STAT / **CHG_STAT** low while charging, ~500 mA. Board runs from VSYS with BT1 open. No brownout while recording. Click-test C6276862 against C5126845 before you trust the pinout.
9. **TinyUSB MSC** — plug into a PC. Recording stops and the WAV is closed; Wi-Fi turns off; TinyUSB takes the NAND exclusively (recorder VFS unmounts); the volume appears on the PC; unplug remounts VFS and returns to idle. Drop `set_time.txt` to set the RTC. This board has no VBUS-detect GPIO — if the recorder does not get the NAND back after unplug, power-cycle. After MSC owns native USB, later flashes use the TP_BOOT / TP_EN pads.
10. **Wi-Fi share** — mate the W.FL / MHF III pigtail first (human step; there is no IPEX-detect GPIO). Double-press starts a WPA2 network **PixelSnapVoice** / **voicenote1**. Join from a phone or computer, then open `http://192.168.4.1`. Play or download a WAV in the browser. iOS Files, macOS Finder, or a Windows network location can also copy the folder over WebDAV when that OS allows it. The LED double-blips. Double-press again to stop. Do not start share with the IPEX open. If VDD33 sags on a low cell, stop share and note it — the buck already preferred on this rail is the follow-up.
11. **Sleep** — long press; current should drop (U5 off, radio off). Wake on the record button.

Measure record current. Update [`docs/bom.md`](bom.md) hours from `mAh / measured_mA`. Current pouch is the Jauch **1200 mAh** pack (~7.5 h at 160 mA). If measured current is worse, update the BOM before a metal tray is cut.

## Time

`set_time.txt` at the volume root, one line `YYYY-MM-DD HH:MM:SS` (UTC). Applied on boot and after unmount.

## If something is dead

| Symptom | First check |
| --- | --- |
| No 3.3 V | U4, U5, solder on the module |
| Codec NACK | 3V3A at U8 (~2.8 V), I2C pull-ups, Y1 output on MCLK |
| Hiss / no mic | Analog island, mic port not against glass, MK1 bias at 2.8 V, OUT− not shorted to AGND. MCLK fight: GPIO14 must stay an input; Y1 is the only MCLK driver |
| No MSC | TinyUSB config, USB D+/D− swap, cable not seated. Firmware no longer leaves VFS and TinyUSB both on the NAND |
| No Wi-Fi network | Pigtail not mated, IPEX well empty, `CONFIG_ESP_WIFI_ENABLED`, double-press vs USB still plugged in |
| Brownout on share | Cell voltage, U4 600 mA LDO, TX cap at 10 dBm, codec still running |
| Brownout on play | USB cable, PA supply from VSYS, decoupling |
