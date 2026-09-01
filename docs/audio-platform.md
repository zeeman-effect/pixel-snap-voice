# Audio platform (MCU + codec)

**Current pick is the ESP32-S3.** Pair it with a real codec and a better capsule. Switching MCU throws away USB-MSC + ESP-IDF already in this repo and does not raise capsule SNR. Do it only if leaving Espressif is a hard requirement.

The S3 is not the hiss or the missing speaker. The original BOM recorded from a ~65 dBA digital MEMS and had **no DAC or amp**. nRF, STM32, RP2350, and i.MX RT cannot raise ICS-43434 SNR, and they throw away USB-MSC + ESP-IDF already in this repo.

## Bottlenecks (in order)

1. **No playback path** — MEMS → I2S → MCU cannot drive a speaker or headphone.
2. **The microphone’s own ADC** — [ICS-43434](https://cdn.sparkfun.com/assets/a/9/c/9/1/DS-000069-ICS-43434-v1.2.pdf) is 65 dBA SNR. The converter lives in the capsule.
3. **Power / layout** — analog mics and codec ADCs die if they share a noisy 3.3 V buck. Give the codec a dedicated analog LDO.
4. **ESP32-S3 has no APLL** — 48 kHz from the 160 MHz PLL is slightly inexact. Fix: **ES8311 is I2S master** with a 12.288 MHz oscillator into MCLK; the S3 is slave. ~0.1% pitch error is inaudible for voice notes. The codec has no XI/XO pins.

USB full-speed is enough to dump 48 kHz / 16-bit mono (~96 kB/s). Wi-Fi stays off. Use the MINI-1U module (IPEX, no cable), not the MINI-1 PCB-antenna sibling. The antenna keepout and extra 5.1 mm of module length buy nothing on a radio-off board that sits on a steel shunt.

This product already exists: [ESP32-OpenMic](https://codeberg.org/RevK/ESP32-OpenMic) (S3 module + ICS-43434 + MAX98357A + USB MSC). Espressif voice boards use **ES8311 + analog mic + class-D**, not a different SoC: [ESP32-S3-Korvo-2](https://docs.espressif.com/projects/esp-adf/en/latest/design-guide/dev-boards/user-guide-esp32-s3-korvo-2.html), IDF [`i2s_es8311`](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/i2s.html), [`esp_codec_dev`](https://components.espressif.com/components/espressif/esp_codec_dev).

## Default (v1 custom PCB)

ESP32-S3-MINI-1U + **ES8311 as I2S master** (12.288 MHz oscillator → MCLK) + analog MEMS (**IM73A135** or **ICS-40730**, ~73–74 dBA) + **NS4150** or **MAX98357A** into a 1511 speaker, or ES8311 headphone jack if 9 mm loses.

**Fallback:** ICS-43434 into the S3 or ES8311 digital-mic pin (capture stays 65 dBA; playback still good).

Record **48 kHz, 16-bit, mono PCM WAV**. Keep 24-bit on the I2S wire if the mic provides it; store 16-bit files. whisper.cpp will resample. ~173 MB/hour.

## Ranked options

| Rank | Architecture | When |
| --- | --- | --- |
| 1 | S3-MINI-1U + ES8311 + analog MEMS + class-D / HP | Default |
| 2 | S3-MINI-1U + ICS-43434 + MAX98357A (copy OpenMic) | Fastest; dictaphone-grade capture |
| 3 | i.MX RT1010 LQFP-80 + WM8960 | Only if leaving Espressif is a hard requirement — USB HS, full firmware rewrite, no capture-SNR win |

## Families we are not using

| Family | Why it loses here |
| --- | --- |
| nRF54L | No USB on the SoC |
| nRF5340 | USB FS exists, but aQFN + Zephyr rewrite; Audio DK is LE Audio, not a recorder |
| STM32 U5/H7 | SAI + codec is fine; Cube USB-MSC rewrite for no SNR gain |
| RP2040/RP2350 | Easy PCB; USB↔I2S clock pain; no better mic |
| ESP32-P4 | USB HS unused for file dump; larger module |
| Allwinner / Rockchip | Linux + DDR + PMIC; will not fit a 9 mm wallet |
| ADAU / SHARC | DSP without USB MSC |

A 100 dB codec ADC cannot invent capsule SNR. The codec **does** buy PGA/ALC, analog-mic option, headphone, and a clean clock master.

## Firmware delta (stay on ESP-IDF)

Add `esp_codec_dev` ES8311 duplex I2S. WAV writer already parameterized via `PSV_SAMPLE_RATE_HZ`. USB MSC unchanged. Phase 0 should use a Korvo-2 / ESP-BOX / OpenMic-class board to prove playback, not Sense-only PDM.
