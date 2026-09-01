# Custom-board bring-up

Do this on the first SMT board **after** `python scripts/check_gates.py` is green. Do not power a board that failed ERC/DRC/envelope/`recorder_test`.

Gerbers + JLC BOM/CPL: `hardware/kicad/fab/` and `hardware/kicad/jlcpcb_bom.csv`. Prefer a `kicad-cli` export from `hardware/kicad/recorder/recorder.kicad_pcb` when KiCad is installed. Do not power or order from an export that still fails DRC.

## Order of tests

1. **USB serial** — native USB-Serial/JTAG or UART0. Confirm the S3 enumerates and `idf.py monitor` shows `pixel-snap-voice on custom`.
2. **Rails** — **VDD33** at U4/U5 (MCU) vs **3V3A** at U8 LP5907. They must not be shorted together. VBAT ~3.7–4.2 V with a pouch. VBUS ~5 V when plugged in (J2).
3. **I2C codec** — scan address 0x18. ES8311 ACK.
4. **I2S** — codec is master. Y1 is the 12.288 MHz oscillator into ES8311 MCLK. Scope MCLK/BCLK/WS. Play a tone / loopback before trusting the mic.
5. **Mic capture** — short press records `/recordings/YYYYMMDD-HHMMSS.wav` at 48 kHz. Copy off via SD reader if MSC is not up yet. Play on a desktop.
6. **SD** — 4-bit SDMMC. `storage_sd_mount` log line.
7. **Playback** — double-press plays last file through NS4150 / speaker (or HP jack if the 1511 was dropped).
8. **Charger** — USB-C 5 V, MCP73831 STAT, ~500 mA. No brownout while recording or playing.
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
| Brownout on play | USB cable, PA supply from VBAT, decoupling |
