# Bill of materials (living)

Quantities are for **one** device plus a few passives of margin. Prefer JLCPCB SMT / LCSC Basic. Do not design around **INMP441** (EOL).

LCSC numbers below were captured from the public catalog (Sep 2026). Re-check stock and Basic vs Extended before the SMT order.

The LCSC column of the tables below is the only place order codes are typed. `hardware/kicad/recorder/generate_jlc.py` reads it, joins it to `recorder.kicad_pcb`, and writes `hardware/kicad/jlcpcb_bom.csv`, `jlcpcb_cpl.csv`, and `jlcpcb_extra.csv` during `python scripts/check_gates.py`. A board part on the assembly BOM with no number fails that script: JLCPCB will not machine-place an empty cell. Do not hand-edit those CSVs — put the number here and re-run the gates.

BT1 is through-hole, so it stays out of the pick-and-place file. It still needs an LCSC number: JLC wave-solders it from the assembly BOM. J1 is also through-hole, but it is flagged `exclude_from_bom`: the vertical header will not fit under the lid and the tails poke toward the phone. Keep C124378 in this table so `jlcpcb_extra.csv` still lists it — add that row under Extra Parts in the JLCPCB cart (shipped loose, not soldered) and hand-solder a header at bring-up if you need UART0. Mounting holes are mechanical and stay off all three files.

## Electrical

| Ref | Function | MPN | LCSC | Package | Notes | SMT |
| --- | --- | --- | --- | --- | --- | --- |
| U1 | MCU module | ESP32-S3-MINI-1U-N8 | C2980299 | 15.4 × 15.4 × 2.4 mm | Native USB; 8 MB flash; IPEX unpopulated | Extended |
| U2 | Audio codec | ES8311 | C962342 | QFN-20 3×3 | I2S master; 12.288 MHz oscillator into MCLK; analog island. No XI/XO | Extended |
| Y1 | Codec oscillator | KC3225Z12.2880C1KX00 | C1857159 | 3225 4-pin | Kyocera CMOS oscillator into ES8311 MCLK; S3 is I2S slave. 1.71–3.63 V, same pinout as the Abracon ASE land (1=OE, 2=GND, 3=OUT, 4=VDD). OE is strapped to **3V3A** (2.8 V). Not a crystal | Extended |
| U8 | Analog LDO | LP5907MFX-2.8/NOPB | C186700 | SOT-23-5 | Dedicated 2.8 V (**3V3A**) for AVDD + mic + Y1. Do **not** share **VDD33**. IM73A135 VDD abs max is 3.0 V (typ 2.75 V); ES8311 AVDD is 1.7–3.6 V so 2.8 V is legal on both. Same SOT-23-5 pinout as the 3.3 V SKU. TI part, JLC Extended | Extended |
| U4 | MCU 3.3 V | AP2112K-3.3TRG1 | C51118 | SOT-25 | First spin LDO (buck preferred later). VIN from **VSYS** | Basic |
| U5 | Load switch | AP22804AW5-7 | C3001659 | SOT-25 | Switches U4 out onto **VDD33**; cuts sleep current | Extended |
| MK1 | Analog MEMS | IM73A135V01XTSA1 | C3171831 | LLGA-5 4×3 | ~73 dBA. Infineon: 1=OUT+ 2=VDD 3=OUT− 4=GND 5=GND. Single-ended: C15 couples OUT+; OUT− is open; codec MIC_N via C16 to AGND. VDD is 2.8 V (**3V3A**). JLC Extended SMT (they flag assembly as High). Acoustic port on the free long edge | Extended |
| MK1 alt | Digital MEMS | ICS-43434 | C5656610 | 3.5 × 2.65 | 65 dBA fallback if analog capsule misses SMT | Extended |
| U6 | Class-D PA | NS4150B | C189961 | MSOP-8 | Analog-in from ES8311 AOUT (Korvo path). VCC from **VSYS**. Alt: MAX98357A I2S | Extended |
| SP1 | Speaker | KLJ-01304T-08R07W | C18186315 | 13 × 13 × 4.0 | KELIKING 8 Ω 0.7 W SMD can. JLC Extended, tape-and-reel. Sound faces the lid | Extended |
| U3 | Li-ion charger | BQ24074RGTR | C54313 | VQFN-16 3×3 | Power-path. USB 500 mA (EN1/EN2), ISET 1.8 kΩ ≈ 500 mA. OUT = **VSYS**; BAT = pouch only. JLC Extended | Extended |
| J1 | UART 1×4 | B-2100S04P-A110 | C124378 | 2.54 mm 1×4 THT | Vertical 1×4. 3V3, U0RXD (adapter TX), U0TXD (adapter RX), GND. **Do not assemble**: 8.54 mm tall in a ~5.45 mm lid cavity, tails poke B.Cu toward the phone, no UART window in the case. Keep the LCSC so JLC can ship it as extra parts; hand-solder at bring-up | Extra |
| J2 | USB-C receptacle | 16-pin mid-mount | C165948 | ~3.2 mm | 5.1 kΩ on CC1/CC2; short edge; overmold must miss the phone | Extended |
| J3 | microSD socket | TF-01 / equivalent | C91145 | low-profile | 4-bit SDMMC on the custom PCB | Basic/Ext |
| U7 | USB ESD | USBLC6-2SC6 | C8678 | SOT-23-6 | Next to J2 on D+/D− | Basic |
| BT1 | 1S battery connector | S2B-PH-K-S | C173752 | JST-PH 2.0 mm THT | Side-entry. Plug a protected 1S pouch (PHR-2). USB-C runs the board with BT1 open. JLC wave-solders; not in the CPL | Wave |
| SW1 | Record button | Panasonic EVQP7C01P | C388883 | 3.5 × 2.9 × 1.35 mm | **Side push**: the plunger fires sideways at the left wall, so nothing has to poke through the phone-facing face. SPST, 2.2 N, 0.2 mm travel, 100k cycles, reflow. Short = record, long = power. Two moulded bosses drop into NPTH holes and take the sideways load off the solder. Was listed here as "side-fire, C318885": that code is an XKB TS-1187A-C-J-B, a 5.1 × 5.1 × 5 mm **top-actuated** switch, so the line was wrong on both the part and the direction | Extended |
| SW_BOOT / SW_RST | Boot / Reset | XKB TS-1187A-C-J-B | C318885 | 5.1 × 5.1 × 5 mm | Top-actuated SPST for prototype download. Hold Boot, tap Reset, release Boot. They strap GPIO0 and EN to GND; they are not firmware buttons. **Lid-off only** this spin | Extended |
| D1 | Status LED | 0603 red | C2286 | 0603 | Record / error (GPIO2) | Basic |
| D2 | Charge LED | 0603 | C2286 | 0603 | On U3 STAT / **CHG_STAT** | Basic |
| R2 / R3 | CC pulldowns | 0603WAF5101T5E | C23186 | 0603 5.1 kΩ 1% | USB-C UFP Rd on J2. Schematic value is 5.11 kΩ; this Basic part is 5.1 kΩ (the Type-C number) | Basic |
| F1 | VBUS PTC | 500 mA 6 V | C37010 | 0603/1206 | Between VBUS and charger | Basic |
| MAG1 | Magnet ring | Qi2 / MagSafe accessory | — | OD 56 / ID 44 / 1.1 mm | Buy; do not machine. Pocket to the part you receive | — |
| SH1 | Steel shunt | thin plate | — | ~0.3 mm | **Behind** MAG1, away from the phone. Not the outer chassis | — |

## Passives

Same column order as **Electrical**, so `generate_jlc.py` can read the LCSC codes. Values and packages match the schematic. Ceramics are X5R/X7R at ≥10 V so 5 V USB and 4.2 V on the pouch stay inside a sensible derating. Audio coupling is still X5R: a 1 µF C0G in 0603 is not a JLC Basic part.

| Ref | Function | MPN | LCSC | Package | Notes | SMT |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | VDD33 bulk at U1 | CL21A226MAQNNNE | C45783 | 0805 22 µF 25 V X5R | 3.3 V rail | Basic |
| C2, C6, C9, C10, C11, C12, C13, C15, C16, C17, C18, C19 | 1 µF decouple / couple | CL10A105KB8NNNC | C15849 | 0603 1 µF 50 V X5R | Codec, mic, PA, LDOs | Basic |
| C3, C14 | 100 nF decouple | CC0603KRX7R9BB104 | C14663 | 0603 100 nF 50 V X7R | U1 and SD rail | Basic |
| C4, C5 | Charger IN / OUT | CL10A475KO8NNNC | C19666 | 0603 4.7 µF 16 V X5R | VBUS_CHG and VSYS next to U3 | Basic |
| C7 | U4 output | CL10A225KO8NNNC | C23630 | 0603 2.2 µF 16 V X5R | AP2112 typical app | Basic |
| C8, C20 | 10 µF bulk 0805 | CL21A106KAYNNNE | C15850 | 0805 10 µF 25 V X5R | C8 is VDD33 at U5; C20 is VBAT at the pouch | Basic |
| C21 | VBAT at U3 | CL10A106MA8NRNC | C96446 | 0603 10 µF 25 V X5R | Local ceramic when BT1 is open. 25 V so 4.2 V on the pouch keeps more capacitance than a 10 V part | Basic |
| R1, R7, R10, Rboot, Rsd0, Rsd1, Rsd2, Rsd3, Rsd4, Rstat | 10 kΩ | 0603WAF1002T5E | C25804 | 0603 10 kΩ 1% | EN, PA bias, TS, boot, SD, STAT pull-ups | Basic |
| R4 | Charger ISET | 0603WAF1801T5E | C4177 | 0603 1.8 kΩ 1% | ≈500 mA charge | Basic |
| R5 / R6 | I2C pull-ups | 0603WAF4701T5E | C23162 | 0603 4.7 kΩ 1% | SDA / SCL to **VDD33** | Basic |
| R8 / R11 | Charger ILIM / ITERM | 0603WAF3011T5E | C22991 | 0603 3.01 kΩ 1% | BQ24074 typical app. Extended; 3.00 kΩ Basic would move the current a hair | Extended |
| R9 | Charger TMR | 0603WAF4992T5E | C23184 | 0603 49.9 kΩ 1% | Fast-charge timer | Basic |
| Ragnd | AGND stitch | 0603WAF0000T5E | C21189 | 0603 0 Ω | Analog island to GND | Basic |
| Rchg / Rled | LED series | 0603WAF1001T5E | C21190 | 0603 1 kΩ 1% | D2 and D1 | Basic |

## Mechanical

| Item | Candidate | Notes |
| --- | --- | --- |
| Proto shell | PETG FDM (`hardware/cad/case.scad`) | Magnet pocket 0.3 mm loose, then shim |
| Production shell | 6061-T6 CNC | **Not steel** |
| LiPo pouch | 3.7 V **500 mAh**, 5.0 × 30 × 40 mm class | Plugs into BT1 (JST-PH). CAD leftover ~6000 mm³; 500 mAh is the current pick with margin. Buy a **protected** 1S pack |
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

Current pouch is **500 mAh** after the first height-stack / pocket check (`hardware/cad/check_envelope.py`). Change it if leftover volume or measured current changes. MCU-only 126 mA was optimistic.

Record (MCU + ES8311 + mic + SD, **PA off**): ~160 mA from the cell → **~3.1 h**.

Playback (PA on): higher; measure on Korvo and the first SMT board. Idle deep-sleep is dominated by U3 + always-on LDOs — U5 must actually cut the 3.3 V rail.

| Pouch | Record time (codec, PA off) |
| --- | --- |
| 500 mAh (current) | ~3.1 h |
| 600 mAh (pocket max est.) | ~3.8 h |

Re-measure record current on the custom board and update this table before a metal shell.

## Software (computer, not on device)

| Item | Notes |
| --- | --- |
| whisper.cpp | `software/transcribe.py` wraps it on dumped 48 kHz WAVs |
