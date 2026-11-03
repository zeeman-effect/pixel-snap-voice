# Custom-board bring-up

Do this on the first SMT board **after** `python scripts/check_gates.py` is green. Do not power a board that failed ERC/DRC/envelope/`recorder_test`.

Gerbers + JLC BOM/CPL: `hardware/kicad/fab/`, `hardware/kicad/jlcpcb_bom.csv`, `jlcpcb_cpl.csv`, and `jlcpcb_extra.csv`. A green `check_gates.py` writes them from `hardware/kicad/recorder/recorder.kicad_pcb`, so order from the files that run just produced. Do not power or order from an export that still fails DRC.

## Flash

Every flash goes over a USB-C cable to a computer. What changes is how the S3 gets into download mode.

**First flash (blank chip).** Nothing to press. A blank S3 shows up as its built-in USB-Serial/JTAG port and esptool resets it into download mode itself: `idf.py -p COMx flash monitor`.

**Reflash, case closed (normal path).** Once our firmware runs, TinyUSB MSC owns native USB and esptool can no longer reset the chip by itself. The firmware has a button gesture for this (`CONFIG_PSV_BOOT_DOWNLOAD_HOLD`, on for the custom board; `firmware/hal/download_mode.c`):

1. Plug the USB-C cable into the computer.
2. Put the recorder to sleep: hold the record button about 1.5 s, until it goes dark, and let go.
3. Press the record button again and **keep holding**. The recorder wakes; after **5 s** the LED goes **solid**.
4. Let go. The S3 restarts into ROM download mode and the USB-Serial/JTAG port appears (the LED is off from here).
5. `idf.py -p COMx flash monitor`. esptool's reset at the end starts the new firmware.

LED during that hold:

| LED | Meaning |
| --- | --- |
| off, then solid at 5 s | download mode next; let go |
| fast flashing at 5 s | no computer on the cable (no USB frames seen). Let go; the recorder boots normally. Check the cable is in a computer, not a charger |
| still off, or the recorder went back to sleep | you let go before 5 s, or pressed after it had already started. Start again from step 2 |

Unplugging the USB-C cable does not reboot the recorder while a pouch is connected, which is why step 2 puts it to sleep first. With no pouch, plugging the cable in while holding the button works too.

If download mode is entered and you change your mind, pulse **TP_EN** to GND or remove every power source (cable and pouch). The ROM clears the force-download flag on its own, so the next boot is normal.

**Reflash by the pads (fallback).** Use these if the firmware is too broken to reach the gesture (a crash before `download_mode_check()`, or a build with the option off). The pads are on F.Cu, so this needs the lid off:

1. Hold **TP_BOOT** to **TP_GND** (GPIO0). TP_EN sits between them; use a short wire rather than tweezers across EN.
2. Pulse **TP_EN** to GND, then release EN.
3. Release TP_BOOT.
4. `idf.py -p COMx flash` over USB-C.

Never touch **TP_3V3** to **TP_GND**: that shorts the 3.3 V rail. TP_3V3 is for measuring the rail or feeding it from a bench supply.

There is no Boot/Reset switch and no UART header. Do not wire GPIO0 as a firmware button. SW1 stays the record control, and the download hold is a firmware gesture on it, not a strap.

## Order of tests

1. **USB serial** — native USB-Serial/JTAG or UART0. Confirm the S3 enumerates and `idf.py monitor` shows `pixel-snap-voice on custom`.
2. **Rails** — **VDD33** at U4/U5 (MCU, 3.3 V) vs **3V3A** at U8 LP5907-2.8 (~2.8 V). They must not be shorted together. **3V3A is 2.8 V on purpose**: IM73A135 VDD abs max is 3.0 V. **VSYS** at U3 OUT / U4 VIN (USB ~4.4 V or cell). **VBAT** ~3.7–4.2 V at the BT1 pads with a pouch; it must not be strapped to VSYS. VBUS ~5 V when plugged in (J2).
3. **I2C codec** — scan address 0x18. ES8311 ACK.
4. **I2S** — codec is master. Y1 drives ES8311 MCLK at 12.288 MHz. Firmware leaves GPIO14 unused so the S3 does not fight Y1. Scope MCLK/BCLK/WS. If MCLK looks like two drivers on one net, stop — the S3 is still outputting. Confirm clocks before trusting the mic.
5. **Mic capture** — short press records `/recordings/YYYYMMDD-HHMMSS.wav` at 48 kHz. Copy off via USB MSC or Wi-Fi share. Play on a desktop.
6. **SD** — 4-bit SDMMC. Logs `SD card ready (VFS via TinyUSB)` then `SD mounted at /sdcard (TinyUSB)`. Blank NAND is formatted on that first TinyUSB mount.
7. **No speaker** — dump WAVs over USB or Wi-Fi share and play them on the computer or phone.
8. **Charger** — 5 V on USB-C J2 into BQ24073 IN. Check a C-to-C cable from a USB-C charger turns VBUS on (that proves the R2 / R3 5.1 kΩ Rd). STAT / **CHG_STAT** low while charging, ~500 mA. Board runs from VSYS with BT1 open. No brownout while recording. Flip the plug once and check USB still enumerates (both D± pairs are tied).
9. **TinyUSB MSC** — plug into a PC. Recording stops and the WAV is closed; Wi-Fi turns off; TinyUSB takes the NAND exclusively (recorder VFS unmounts); the volume appears on the PC; unplug remounts VFS and returns to idle. Drop `set_time.txt` to set the RTC. This board has no VBUS-detect GPIO — if the recorder does not get the NAND back after unplug, power-cycle. After MSC owns native USB, reflash with the 5 s button hold (see **Flash**); the TP_BOOT / TP_EN pads are the fallback.
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
