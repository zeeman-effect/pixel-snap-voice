# Bill of materials (living)

Quantities are for **one** device plus a few passives of margin. Prefer JLCPCB SMT / LCSC Basic. Do not design around **INMP441** (EOL).

LCSC numbers below were captured from the public catalog (Aug 2026). Re-check stock and Basic vs Extended before the SMT order.

The LCSC column of the **Electrical** table is the only place order codes are typed. `hardware/kicad/recorder/generate_jlc.py` reads it, joins it to `recorder.kicad_pcb`, and writes `hardware/kicad/jlcpcb_bom.csv` and `jlcpcb_cpl.csv` during `python scripts/check_gates.py`. Do not hand-edit those two CSVs — put the number here and re-run the gates.
## Electrical

| Ref | Function | MPN | LCSC | Package | Notes | SMT |
| --- | --- | --- | --- | --- | --- | --- |
| U1 | MCU module | ESP32-S3-MINI-1U-N8 | C2980299 | 15.4 × 15.4 × 2.4 mm | Native USB; 8 MB flash; IPEX unpopulated | Extended |
| U2 | Audio codec | ES8311 | C962342 | QFN-20 3×3 | I2S master; 12.288 MHz oscillator into MCLK; analog island. No XI/XO | Extended |
| Y1 | Codec oscillator | 12.288 MHz 4-pin | — | 3225 | Output to ES8311 MCLK; S3 is I2S slave. Not a crystal | verify stock |
| U8 | Analog LDO | LP5907MFX-3.3 | — | SOT-23-5 | Dedicated 3.3 V (**3V3A**) for AVDD + mic + Y1. Do **not** share **VDD33** | verify stock |
| U4 | MCU 3.3 V | AP2112K-3.3TRG1 | C51118 | SOT-25 | First spin LDO (buck preferred later). VIN from VBAT | Basic |
| U5 | Load switch | AP22804AW5 | — | SOT-23-5 | Switches U4 out onto **VDD33**; cuts sleep current | verify stock |
| MK1 | Analog MEMS | IM73A135 / ICS-40730 | — | 4 × 3 | ~73–74 dBA; **hand-place**; acoustic port on free long edge | hand |
| MK1 alt | Digital MEMS | ICS-43434 | C5656610 | 3.5 × 2.65 | 65 dBA fallback if analog capsule misses SMT | Extended |
| U6 | Class-D PA | NS4150B | C189961 | MSOP-8 | Analog-in from ES8311 AOUT (Korvo path). Alt: MAX98357A I2S | Extended |
| SP1 | Speaker | KLJ-01304T-08R07W | C18186315 | 13 × 13 × 4.0 | KELIKING 8 Ω 0.7 W SMD can. JLC Extended, tape-and-reel. Sound faces the lid | Extended |
| U3 | Li-ion charger | MCP73831T-2ACI/OT | C424093 | SOT-23-5 | ~500 mA (`RPROG` 2 kΩ); STAT LED | Extended |
| J1 | UART 1×4 | pin header | — | 2.54 mm | 3V3, U0RXD (adapter TX), U0TXD (adapter RX), GND | hand |
| J2 | USB-C receptacle | 16-pin mid-mount | C165948 | ~3.2 mm | 5.1 kΩ on CC1/CC2; short edge; overmold must miss the phone | Extended |
| J3 | microSD socket | TF-01 / equivalent | C91145 | low-profile | 4-bit SDMMC on the custom PCB | Basic/Ext |
| U7 | USB ESD | USBLC6-2SC6 | C8678 | SOT-23-6 | Next to J2 on D+/D− | Basic |
| BT1 | LiPo pouch | 3.7 V **500 mAh** | — | 5.0 × 30 × 40 mm class | CAD leftover ~6000 mm³ (~600 mAh est.); 500 mAh is the current pick with margin | hand |
| SW1 | Record button | Panasonic EVQP7C01P | C388883 | 3.5 × 2.9 × 1.35 mm | **Side push**: the plunger fires sideways at the left wall, so nothing has to poke through the phone-facing face. SPST, 2.2 N, 0.2 mm travel, 100k cycles, reflow. Short = record, long = power. Two moulded bosses drop into NPTH holes and take the sideways load off the solder. Was listed here as "side-fire, C318885": that code is an XKB TS-1187A-C-J-B, a 5.1 × 5.1 × 5 mm **top-actuated** switch, so the line was wrong on both the part and the direction | Extended |
| D1 | Status LED | 0603 red | C2286 | 0603 | Record / error (GPIO2) | Basic |
| D2 | Charge LED | 0603 | C2286 | 0603 | On U3 STAT / **CHG_STAT** | Basic |
| R2 / R3 | CC pulldowns | 5.11 kΩ 1% | C23186 | 0603 | USB-C UFP / sink on J2 | Basic |
| F1 | VBUS PTC | 500 mA 6 V | C37010 | 0603/1206 | Between VBUS and charger | Basic |
| MAG1 | Magnet ring | Qi2 / MagSafe accessory | — | OD 56 / ID 44 / 1.1 mm | Buy; do not machine. Pocket to the part you receive | — |
| SH1 | Steel shunt | thin plate | — | ~0.3 mm | **Behind** MAG1, away from the phone. Not the outer chassis | — |

Passives (decoupling, I2C pull-ups 4.7 kΩ, PROG, mic bias RC) follow the Espressif module hardware design guidelines plus the ES8311 and mic vendor notes. 0603 100 nF / 10 µF: C14663 / C15850 class (Basic).

## Mechanical

| Item | Candidate | Notes |
| --- | --- | --- |
| Proto shell | PETG FDM (`hardware/cad/case.scad`) | Magnet pocket 0.3 mm loose, then shim |
| Production shell | 6061-T6 CNC | **Not steel** |
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
