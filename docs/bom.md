# Bill of materials (living)

Quantities are for **one** device plus a few passives of margin. Prefer JLCPCB SMT / LCSC Basic. Do not design around **INMP441** (EOL).

LCSC numbers below were captured from the public catalog (Sep 2026). Every assembly code, plus the cable housing, USB-A plug and ICS-43434 alt, was re-checked against the JLCPCB parts library on 25 Oct 2026: all in stock at JLC, MPNs match, Basic vs Extended matches the SMT column. Thinnest JLC stock that day: J2 `C6276862` 135, J3 `C2841139` 389, U1 `C2980299` 639. Re-check again before the SMT order.

The LCSC column of the tables below is the only place order codes are typed. `hardware/kicad/recorder/generate_jlc.py` reads it, joins it to `recorder.kicad_pcb`, and writes `hardware/kicad/jlcpcb_bom.csv`, `jlcpcb_cpl.csv`, and `jlcpcb_extra.csv` during `python scripts/check_gates.py`. A board part on the assembly BOM with no number fails that script: JLCPCB will not machine-place an empty cell. Do not hand-edit those CSVs — put the number here and re-run the gates.

BT1 is two SMT pads for a pouch pigtail (`PSV:Battery_Pigtail_2P`). There is no connector to place, so it stays off the assembly BOM and the pick-and-place file. Download is four F.Cu pads (TP_BOOT, TP_EN, TP_GND, TP_3V3), also off both files. Mounting holes are mechanical and stay off all three files. Do not order a JST-PH or a UART header for this spin.

## Electrical

| Ref | Function | MPN | LCSC | Package | Notes | SMT |
| --- | --- | --- | --- | --- | --- | --- |
| U1 | MCU module | ESP32-S3-MINI-1U-N8 | C2980299 | 15.4 × 15.4 × 2.4 mm | Native USB; 8 MB flash; IPEX takes a lid W.FL / I-PEX MHF III pigtail | Extended |
| U2 | Audio codec | ES8311 | C962342 | QFN-20 3×3 | I2S master; 12.288 MHz oscillator into MCLK; analog island. No XI/XO | Extended |
| Y1 | Codec oscillator | Y322512.288MNCCZ | C49207908 | 3225 4-pin | JLYE CMOS oscillator into ES8311 MCLK; S3 is I2S slave. 1.8–3.3 V, same pinout as the Abracon ASE land (1=OE, 2=GND, 3=OUT, 4=VDD). OE and VDD are on **3V3A** (2.8 V). Not a crystal. Replaces Kyocera `C1857159`, a JLC SMT shortfall. Do **not** substitute a 3.3 V-only can such as Lucki `C5917271` (2.97 V min) | Extended |
| U8 | Analog LDO | LP5907MFX-2.8/NOPB | C186700 | SOT-23-5 | Dedicated 2.8 V (**3V3A**) for AVDD + mic + Y1. Do **not** share **VDD33**. IM73A135 VDD abs max is 3.0 V (typ 2.75 V); ES8311 AVDD is 1.7–3.6 V so 2.8 V is legal on both. Same SOT-23-5 pinout as the 3.3 V SKU. TI part, JLC Extended | Extended |
| U4 | MCU 3.3 V | AP2112K-3.3TRG1 | C51118 | SOT-25 | First spin LDO (buck preferred later). VIN from **VSYS** | Basic |
| U5 | Load switch | AP22804AW5-7 | C3001659 | SOT-25 | Switches U4 out onto **VDD33**; cuts sleep current | Extended |
| MK1 | Analog MEMS | IM73A135V01XTSA1 | C3171831 | LLGA-5 4×3 | ~73 dBA. Infineon: 1=OUT+ 2=VDD 3=OUT− 4=GND 5=GND. Single-ended: C15 couples OUT+; OUT− is open; codec MIC_N via C16 to AGND. VDD is 2.8 V (**3V3A**). JLC Extended SMT (they flag assembly as High). Acoustic port on the free long edge | Extended |
| MK1 alt | Digital MEMS | ICS-43434 | C5656610 | 3.5 × 2.65 | 65 dBA fallback if analog capsule misses SMT | Extended |
| U3 | Li-ion charger | BQ24073RGTR | C15220 | VQFN-16 3×3 | Power-path. USB 500 mA (EN1 pin 6 high, EN2 pin 5 low), ISET 1.8 kΩ ≈ 500 mA. OUT = **VSYS** at 4.4 V; BAT = pouch only. Pin 15 is TD, held low by R11 so termination stays at the default 10%. Pin 8 is VSS. Replaces BQ24074RGTR `C54313`, which JLCPCB was short. JLC Extended | Extended |
| J2 | Magnetic pad | YZ103915020T-04025-02 | C6276862 | 22.3 × 7.7 × 2.0 stadium | 4-pin female on the lid face. Vendor drawing: capsule with full-radius ends, 2.54 mm pitch. Pin 1 VBUS, 2 D−, 3 D+, 4 GND until a click-test. No CC | Extended |
| Cable | Magnetic USB-A lead | YZP0048-20048-04025-03 | C5126845 | 4.8 mm male housing | **Not a finished lead.** LCSC lists a housing (26 in stock, min 1, 25 Oct 2026). Order 2 custom sets on [lcsccable.com/customize](https://lcsccable.com/customize): Terminal Harness, Side A **Housing only** `C5126845` (no Terminal), Side B USB-A 2.0 male `C2765195`, 1000 mm, pin 1–4 = VBUS / D− / D+ / GND. Extra pads: **3× C6276862** from the LCSC parts cart (min 1). Cable MOQ is 1 set. Do not put C6276862 on the cable. Do not buy Amazon MagSafe lookalikes. Recipe below | — |
| J3 | SD NAND | CSNP32GCR01-AOW | C2841139 | LGA-8 8.0 × 6.2 × 0.75 mm | CS 32 Gbit (4 GB), SD 2.0 1-bit and 4-bit. Pin order is 1 DAT2, 2 DAT3, 3 CLK, 4 VSS, 5 CMD, 6 DAT0, 7 DAT1, 8 VDD. Same land as Zetta ZDSD32GLGEAG (`C5188571`), which was out of stock. Not the microSD socket order. Firmware formats FAT if blank. Do not buy the 8 Gbit grade | Extended |
| U7 | USB ESD | USBLC6-2SC6 | C7519 | SOT-23-6 | Next to J2 on D+/D−. ST part; `C8678` is an SS34 SMA Schottky, not this chip | Extended |
| BT1 | 1S pouch pads | — | — | two SMT pads on B.Cu | Solder the Jauch 70 mm pigtail at (−17, 35): pad 1 VBAT (west), pad 2 GND. Tape the cell on and kapton the joints. The magnetic pad runs the board with the pouch off. No LCSC — nothing for JLC to place | Off |
| SW1 | Record button | Panasonic EVQP7C01P | C388883 | 3.5 × 2.9 × 1.35 mm | **Side push**: the plunger fires sideways at the phone-left wall when the accessory is snapped on, so nothing has to poke through the phone-facing face. SPST, 2.2 N, 0.2 mm travel, 100k cycles, reflow. Short = record, long = power. Two moulded bosses drop into NPTH holes and take the sideways load off the solder. Was listed here as "side-fire, C318885": that code is an XKB TS-1187A-C-J-B, a 5.1 × 5.1 × 5 mm **top-actuated** switch, so the line was wrong on both the part and the direction | Extended |
| D1 | Status LED | 0603 red | C2286 | 0603 | Record / error (GPIO2) | Basic |
| D2 | Charge LED | 0603 | C2286 | 0603 | On U3 STAT / **CHG_STAT** | Basic |
| F1 | VBUS PTC | BSMD0603-050-6V | C883095 | 0603 | 500 mA hold, 6 V, 1 A trip. Between VBUS and charger. `C37010` was a dead LCSC number, so JLC showed F1 as No Part Selected | Extended |
| MAG1 | Magnet ring | totalElement R54X46X15MMN52 | — | OD 54.1 / ID 46 / 1.5 mm | N52 ring, steel plate already glued on. Blind well behind a 0.85 mm skin. Glue the steel face | — |
| MAG2 | Clocking magnet | same pack | — | 12 × 5 × 1.5 mm, long side toward 6 o'clock | Alignment magnet from the ring pack, on the phone-bottom side of the ring, so the case cannot spin. Same well depth, same skin | — |

### Magnetic USB-A lead (order this)

`C5126845` is the Xinyangze male housing (`YZP0048-20048-04025-03`). It is 4.8 mm tall, 4 pins at 2.5 mm, 12 V / 1 A. LCSC will not ship a USB-A cable if you only Add-to-Cart that number. J2 on the board is the female pad `C6276862`; JLCPCB places that one. Extra pads for a click-test come from the LCSC parts cart — JLC will not mail unused SMT extras.

Checked on LCSC 25 Oct 2026: housing 26 in stock, min 1, Custom Cables MOQ 1 set. Female pad 135 in stock, min 1, multiple 1. Quote in 24–48 h. Custom cables cannot be returned or cancelled.

| What | Qty | Where | Notes |
| --- | --- | --- | --- |
| Finished lead | **2 sets** | [lcsccable.com/customize](https://lcsccable.com/customize) | MOQ 1. Two because a custom lead is no-return |
| Male housing `C5126845` | **2** | Pulled by the cable shop | One per set. Do **not** also Add-to-Cart two housings |
| USB-A 2.0 male `C2765195` | **2** | Pulled by the cable shop | Molex `48037-2200`, wire-solder, 1591 in stock. Engineer may swap an equivalent overmolded USB-A 2.0 male. No Type-C, no CC |
| Extra female pads `C6276862` | **3** | LCSC parts cart | Loose mates for the click-test. JLC already places J2 |

Configurator (Consumer Electronics → **Terminal Harness** → Shape **Single**):

- Side A tip: **Housing** (not Housing & Terminal). Source **MPN**. Type `YZP0048-20048-04025-03` or `C5126845`. Leave Terminal empty.
- Side B tip: **Housing**. MPN `48037-2200` / `C2765195`.
- Wire: 4-core USB 2.0, black, **1000 mm** (their length box excludes the housings). 24 AWG on VBUS/GND and 28 AWG on D+/D− if the AWG list allows it; otherwise ask the engineer for a USB 2.0 4-core. Twisted = **No** (that toggle is a ribbon twist).
- Pinout: **Other Pinout**. Paste this in More Requirements:

```
USB-A 2.0 male (no Type-C, no CC) to C5126845 magnetic male.
USB-A 1 red  VBUS  →  housing pin 1
USB-A 2 white D−   →  housing pin 2
USB-A 3 green D+   →  housing pin 3
USB-A 4 black GND  →  housing pin 4
Do not put C6276862 on this cable. Pin order is assumed until a click-test on a loose C6276862 pad.
```

Production Volume: **2** Sets. Save to Cart. Tick the cable (it starts unticked) and Request for Quote. After the quote, open Cable Orders, confirm, pay. Cart clicks are in [`docs/manufacturing.md`](manufacturing.md).

## Passives

Same column order as **Electrical**, so `generate_jlc.py` can read the LCSC codes. Values and packages match the schematic. Ceramics are X5R/X7R at ≥10 V so 5 V USB and 4.2 V on the pouch stay inside a sensible derating. Audio coupling is still X5R: a 1 µF C0G in 0603 is not a JLC Basic part.

| Ref | Function | MPN | LCSC | Package | Notes | SMT |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | VDD33 bulk at U1 | CL21A226MAQNNNE | C45783 | 0805 22 µF 25 V X5R | 3.3 V rail | Basic |
| C2, C6, C9, C10, C11, C12, C13, C15, C16 | 1 µF decouple / couple | CL10A105KB8NNNC | C15849 | 0603 1 µF 50 V X5R | Codec, mic, LDOs | Basic |
| C3, C14 | 100 nF decouple | CC0603KRX7R9BB104 | C14663 | 0603 100 nF 50 V X7R | U1 and SD rail | Basic |
| C4, C5 | Charger IN / OUT | CL10A475KO8NNNC | C19666 | 0603 4.7 µF 16 V X5R | VBUS_CHG and VSYS next to U3 | Basic |
| C7 | U4 output | CL10A225KO8NNNC | C23630 | 0603 2.2 µF 16 V X5R | AP2112 typical app | Basic |
| C8, C20 | 10 µF bulk 0805 | CL21A106KAYNNNE | C15850 | 0805 10 µF 25 V X5R | C8 is VDD33 at U5; C20 is VBAT at the pouch | Basic |
| C21 | VBAT at U3 | CL10A106MA8NRNC | C96446 | 0603 10 µF 25 V X5R | Local ceramic when BT1 is open. 25 V so 4.2 V on the pouch keeps more capacitance than a 10 V part | Basic |
| R1, R10, Rboot, Rsd0, Rsd1, Rsd2, Rsd3, Rsd4, Rstat | 10 kΩ | 0603WAF1002T5E | C25804 | 0603 10 kΩ 1% | EN, TS, boot, SD, STAT pull-ups | Basic |
| R4 | Charger ISET | 0603WAF1801T5E | C4177 | 0603 1.8 kΩ 1% | ≈500 mA charge | Basic |
| R5 / R6 | I2C pull-ups | 0603WAF4701T5E | C23162 | 0603 4.7 kΩ 1% | SDA / SCL to **VDD33** | Basic |
| R8 / R11 | Charger ILIM / TD | 0603WAF3011T5E | C22991 | 0603 3.01 kΩ 1% | R8 is ILIM. R11 holds BQ24073 TD low so charge termination stays enabled. Extended; 3.00 kΩ Basic would move ILIM a hair | Extended |
| R9 | Charger TMR | 0603WAF4992T5E | C23184 | 0603 49.9 kΩ 1% | Fast-charge timer | Basic |
| Ragnd | AGND stitch | 0603WAF0000T5E | C21189 | 0603 0 Ω | Analog island to GND | Basic |
| Rchg / Rled | LED series | 0603WAF1001T5E | C21190 | 0603 1 kΩ 1% | D2 and D1 | Basic |

## Mechanical

| Item | Candidate | Notes |
| --- | --- | --- |
| Proto shell | PETG FDM (`hardware/cad/case.scad`) | Magnet pocket 0.3 mm loose, then shim |
| Production tray | 6061-T6 CNC (`variant="metal"`) | Tray only. Lid stays PETG. **Not steel** |
| LiPo pouch | Jauch **LP305166JH-PCM-2-WIRES-70MM** (DigiKey 13278052) | 3.7 V, 1200 mAh min / 1220 mAh typ, 66 × 51.5 × 3.3 mm, PCM, 70 mm leads, ~20.5 g. Tape to B.Cu at (0, 0). Wrap in kapton, including the shunt face. Solder the leads to B.Cu BT1 at (−17, 35). The pack has a PCM; this board has no second protector. Charge 500 mA is under the pack's 0.5 C / 600 mA max. [DigiKey](https://www.digikey.com/en/products/detail/jauch-quartz/LP305166JH-PCM-2-WIRES-70MM/13278052) |
| Record pill | TPU 95A (`part="button"`) | Captive in the lid wall. SW1 is the spring |
| Wi-Fi antenna | Inventek **B24P-W** (DigiKey 1475-B24P-W-ND) | 2.4 GHz 50 Ω adhesive 30 × 5 × 0.5 mm polymer patch, **W.FL / I-PEX MHF III** plug, 102 mm Ø0.81 mm coax. Mates the MINI-1U third-gen jack. Do **not** buy a first-generation U.FL plug. Hand-fit in the PETG lid; mate only when sharing. Tape at (2, 33) on the 30 × 5 mm mark, long axis along +X. Do not enlarge the 7 mm IPEX well. Coil slack in the 2.60 mm lid cavity. Off SMT. [DigiKey](https://www.digikey.com/en/products/detail/inventek-systems/B24P-W/11306874) |
| Adhesive | 3M VHB or ring stock tape | Phone-facing per vendor |
| Screws | M1.6 | Four bosses; or snap-fit on plastic |

## Phase 0 (no custom PCB)

| Item | Part |
| --- | --- |
| Dev board | ESP32-S3-Korvo-2 (preferred) or ESP-BOX |
| Storage | microSD on Korvo |
| Battery | 3.7 V LiPo on the board battery socket |
| Cable | USB for serial; MSC after the core is stable |

## Battery life (CAD leftover, codec included)

Current pouch is the Jauch **1200 mAh** pack taped to B.Cu (`hardware/cad/check_envelope.py`). MCU-only 126 mA was optimistic.

Record (MCU + ES8311 + mic + SD): ~160 mA from the cell → **~7.5 h**.

No on-device playback on the custom board. Idle deep-sleep is dominated by U3 + always-on LDOs — U5 must actually cut the 3.3 V rail.

| Pouch | Record time |
| --- | --- |
| 1200 mAh (Jauch LP305166JH, current) | ~7.5 h |

Re-measure record current on the custom board and update this table before a metal shell.

## Software (computer, not on device)

| Item | Notes |
| --- | --- |
| whisper.cpp | `software/transcribe.py` wraps it on dumped 48 kHz WAVs |
