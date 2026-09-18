# Bill of materials (living)

Quantities are for **one** device plus a few passives of margin. Prefer JLCPCB SMT / LCSC Basic. Do not design around **INMP441** (EOL).

LCSC numbers below were captured from the public catalog (Aug 2026). Re-check stock and Basic vs Extended before the SMT order.

The LCSC column of the **Electrical** table is the only place order codes are typed. `hardware/kicad/recorder/generate_jlc.py` reads it, joins it to `recorder.kicad_pcb`, and writes `hardware/kicad/jlcpcb_bom.csv` and `jlcpcb_cpl.csv` during `python scripts/check_gates.py`. Do not hand-edit those two CSVs — put the number here and re-run the gates.
## Electrical

| Ref | Function | MPN | LCSC | Package | Notes | SMT |
| --- | --- | --- | --- | --- | --- | --- |
| U1 | MCU module | ESP32-S3-MINI-1U-N8 | C2980299 | 15.4 × 15.4 × 2.4 mm | Native USB; 8 MB flash; IPEX unpopulated | Extended |
| U2 | Audio codec | ES8311 | C962342 | QFN-20 3×3 | I2S master; 12.288 MHz oscillator into MCLK; analog island. No XI/XO | Extended |
| Y1 | Codec oscillator | KC3225Z12.2880C1KX00 | C1857159 | 3225 4-pin | CMOS oscillator, 1.71–3.63 V, output to ES8311 MCLK. Same land as Abracon ASE. Pin 1 OE tied high to **3V3A**. Not a crystal | Extended |
| U8 | Analog LDO | LP5907MFX-3.3/NOPB | C80670 | SOT-23-5 | Dedicated 3.3 V (**3V3A**) for AVDD + mic + Y1. Do **not** share **VDD33** | Extended |
| U4 | MCU 3.3 V | AP2112K-3.3TRG1 | C51118 | SOT-25 | First spin LDO (buck preferred later). VIN from **VSYS** | Basic |
| U5 | Load switch | AP22804AW5-7 | C3001659 | SOT-23-5 | Active-high EN. Switches U4 out onto **VDD33**; cuts sleep current. Do not substitute the B (active-low) die | Extended |
| MK1 | Analog MEMS | IM73A135V01XTSA1 | C3171831 | 4 × 3 LLGA-5 | ~73 dBA. **Hand-place** after SMT: off the JLC BOM and CPL. JLC stocks this code but lists it high-difficulty, and this land is a local adaptation around the sound port | hand |
| MK1 alt | Digital MEMS | ICS-43434 | C5656610 | 3.5 × 2.65 | 65 dBA fallback if analog capsule misses SMT | Extended |
| U6 | Class-D PA | NS4150B | C189961 | MSOP-8 | Analog-in from ES8311 AOUT (Korvo path). VCC from **VSYS**. Alt: MAX98357A I2S | Extended |
| SP1 | Speaker | KLJ-01304T-08R07W | C18186315 | 13 × 13 × 4.0 | KELIKING 8 Ω 0.7 W SMD can. JLC Extended, tape-and-reel. Sound faces the lid | Extended |
| U3 | Li-ion charger | BQ24074RGTR | C54313 | VQFN-16 3×3 | Power-path. USB 500 mA (EN1/EN2), ISET 1.8 kΩ ≈ 500 mA. OUT = **VSYS**; BAT = pouch only. JLC Extended | Extended |
| J1 | UART 1×4 | pin header | — | 2.54 mm | 3V3, U0RXD (adapter TX), U0TXD (adapter RX), GND. **Hand-solder**; off the JLC BOM and CPL | hand |
| J2 | USB-C receptacle | 16-pin mid-mount | C165948 | ~3.2 mm | 5.1 kΩ on CC1/CC2; short edge; overmold must miss the phone | Extended |
| J3 | microSD socket | TF-01 / equivalent | C91145 | low-profile | 4-bit SDMMC on the custom PCB | Basic/Ext |
| U7 | USB ESD | USBLC6-2SC6 | C7519 | SOT-23-6 | Next to J2 on D+/D−. ST part; `C8678` is an SS34 SMA Schottky, not this chip | Extended |
| BT1 | 1S battery connector | S2B-PH-K-S | C173752 | JST-PH 2.0 mm THT | Side-entry. Plug a protected 1S pouch (PHR-2). Optional: USB-C runs the board with BT1 open. On the JLC BOM for wave solder, not in the pick-and-place file | Extended |
| SW1 | Record button | Panasonic EVQP7C01P | C388883 | 3.5 × 2.9 × 1.35 mm | **Side push**: the plunger fires sideways at the left wall, so nothing has to poke through the phone-facing face. SPST, 2.2 N, 0.2 mm travel, 100k cycles, reflow. Short = record, long = power. Two moulded bosses drop into NPTH holes and take the sideways load off the solder. Was listed here as "side-fire, C318885": that code is an XKB TS-1187A-C-J-B, a 5.1 × 5.1 × 5 mm **top-actuated** switch, so the line was wrong on both the part and the direction | Extended |
| SW_BOOT / SW_RST | Boot / Reset | XKB TS-1187A-C-J-B | C318885 | 5.1 × 5.1 × 5 mm | Top-actuated SPST for prototype download. Hold Boot, tap Reset, release Boot. They strap GPIO0 and EN to GND; they are not firmware buttons. **Lid-off only** this spin | Extended |
| D1 | Status LED | 0603 red | C2286 | 0603 | Record / error (GPIO2) | Basic |
| D2 | Charge LED | 0603 | C2286 | 0603 | On U3 STAT / **CHG_STAT** | Basic |
| R1 / R7 / R10 / Rboot / Rsd0 / Rsd1 / Rsd2 / Rsd3 / Rsd4 / Rstat | Pull-ups | 10 kΩ 1% | C25804 | 0603 | EN, boot, SD CMD/DAT, PA bias, charger TS, STAT | Basic |
| R2 / R3 | CC pulldowns | 5.11 kΩ 1% | C23186 | 0603 | USB-C UFP / sink on J2 | Basic |
| R4 | Charger ISET | 1.8 kΩ 1% | C4177 | 0603 | BQ24074 ≈ 500 mA | Basic |
| R5 / R6 | I2C pull-ups | 4.7 kΩ 1% | C23162 | 0603 | SDA / SCL to **VDD33** | Basic |
| R8 / R11 | ILIM / ITERM | 3.01 kΩ 1% | C22991 | 0603 | BQ24074 USB current limit and termination | Extended |
| R9 | Charger TMR | 49.9 kΩ 1% | C23184 | 0603 | BQ24074 safety timer | Basic |
| Ragnd | AGND stitch | 0 Ω | C21189 | 0603 | Analog island return | Basic |
| Rchg / Rled | LED series | 1 kΩ 1% | C21190 | 0603 | D1 / D2 | Basic |
| C1 | VDD33 bulk | 22 µF 25 V X5R | C45783 | 0805 | At the module | Basic |
| C2 / C6 / C9 / C10 / C11 / C12 / C13 / C15 / C16 / C17 / C18 / C19 | Decoupling / DC blocks | 1 µF 50 V X5R | C15849 | 0603 | EN delay, codec, analog, PA | Basic |
| C3 / C14 | HF decoupling | 100 nF 50 V X7R | C14663 | 0603 | VDD33 at U1 and the SD rail | Basic |
| C4 / C5 | VBUS / IN | 4.7 µF 16 V X5R | C19666 | 0603 | USB inlet and charger input | Basic |
| C7 | U4 output | 2.2 µF 16 V X5R | C23630 | 0603 | AP2112 recommended Cout | Basic |
| C8 / C20 | 10 µF bulk | 10 µF 25 V X5R | C15850 | 0805 | VDD33 after U5, VBAT at the pouch | Basic |
| C21 | VBAT at U3 | 10 µF 10 V X5R | C19702 | 0603 | Local ceramic on BAT when the pouch is unplugged | Basic |
| F1 | VBUS PTC | BSMD0603-050-6V | C883095 | 0603 | 500 mA hold, 6 V, 1 A trip. Between VBUS and charger. `C37010` was a dead LCSC number, so JLC showed F1 as No Part Selected | Extended |
| MAG1 | Magnet ring | Qi2 / MagSafe accessory | — | OD 56 / ID 44 / 1.1 mm | Buy; do not machine. Pocket to the part you receive | — |
| SH1 | Steel shunt | thin plate | — | ~0.3 mm | **Behind** MAG1, away from the phone. Not the outer chassis | — |

Passives follow the BQ24074 typical app plus the Espressif module and ES8311 notes. Every assembled electrical part now has an LCSC code in the table above. `generate_jlc.py` will refuse to write the JLC CSVs if one is missing. J1 and MK1 stay off those CSVs: they are flagged `exclude_from_bom` and `exclude_from_pos_files` on the board. C21 is the 10 µF 0603 on VBAT next to U3; C20 is the 10 µF 0805 at the pouch.

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
