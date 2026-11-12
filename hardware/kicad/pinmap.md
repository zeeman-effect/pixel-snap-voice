# Custom PCB pin map

Human table. Matches `firmware/boards/custom.h` and `hardware/kicad/recorder/` refs.
Not generated. Origin and heights: [`../cad/INTERFACE.md`](../cad/INTERFACE.md). Footprint XY: [`recorder/placement.json`](recorder/placement.json).

U1 is ESP32-S3-MINI-1U-N8 (`params.json` `mcu`). ES8311 is I2S **master**; S3 is slave.
Y1 is a 12.288 MHz oscillator into ES8311 **MCLK**. The codec has no XI/XO pins.
Strapping GPIO0 / GPIO45 / GPIO46 are not used as I2S or SD.

## ESP32-S3-MINI-1U-N8

| GPIO | Net | Direction | Goes to |
| --- | --- | --- | --- |
| 3V3 / GND | **VDD33** / GND | power | U5 AP22804 / pour |
| GPIO19 / GPIO20 | USB_DM / USB_DP | USB PHY | U7 USBLC6-2, **J2** |
| GPIO4 / GPIO5 | I2C_SDA / I2C_SCL | open-drain | U2 ES8311 CDATA / CCLK |
| GPIO14 | I2S_MCLK | input | U2 MCLK + Y1 out |
| GPIO13 | I2S_BCLK | input | U2 BCLK |
| GPIO12 | I2S_WS | input | U2 LRCK |
| GPIO10 | I2S_DIN | input | U2 ASDOUT |
| GPIO11 | I2S_DOUT | output | U2 DSDIN |
| GPIO8 | — | unused | No PA on this spin |
| GPIO15 | SD_CLK | output | **J3** pin 3 (MKDV4GCL-ABB) |
| GPIO7 | SD_CMD | bidirectional | **J3** pin 5 |
| GPIO6 / 16 / 17 / 18 | SD_D0–D3 | bidirectional | **J3** 4-bit SDMMC |
| GPIO0 | BOOT | strapping, pull-up | Rboot 10k plus **TP_BOOT**. Ground this pad and pulse EN to enter download if USB MSC owns the port and the firmware's 5 s button hold cannot run |
| GPIO1 | BTN | input, pull-up | SW1 to GND |
| GPIO2 | LED | output | D1 |
| GPIO9 | CHG_STAT | input | U3 STAT (D2 charge LED on this net) |
| GPIO43 / GPIO44 | UART_TX / UART_RX | UART0 | Labeled on U1 only. No header. Flash over USB-C |
| EN | EN | module enable | R1 10k / C2 plus **TP_EN** |

## Other

| Net | Notes |
| --- | --- |
| J2 | C2848620 USB-C (dev variant). A4/A9/B4/B9 VBUS, A6/B6 USB_DP, A7/B7 USB_DM, A5 CC1 (R2 5.1k), B5 CC2 (R3 5.1k), A8/B8 SBU open, A1/A12/B1/B12 + shell GND |
| **VDD33** | U4 AP2112 → U5 AP22804. MCU digital rail |
| 3V3A | U8 LP5907-2.8 from **VSYS** (~2.8 V); star return to AGND; no digital return through MK1. Named 3V3A; it is not 3.3 V |
| J3 | MK MKDV4GCL-ABB 512 MB SD NAND, LGA-8. Pins: 3 CLK, 4 VSS, 5 CMD, 6 DAT0, 7 DAT1, 8 VDD. Format FAT if blank |
| VBAT | LiPo pouch pigtail on B.Cu BT1 pads at (−17, 35); U3 BQ24073 BAT plus C21 at the QFN. Do not strap to VSYS |
| TP_BOOT / TP_EN / TP_GND / TP_3V3 | F.Cu pads: fallback download path. Normal reflash is the 5 s record-button hold (`firmware/hal/download_mode.c`) |
| VSYS | U3 OUT. USB or cell, whichever is up. Feeds U4, U8 |
| RF | MINI-1U IPEX. Lid W.FL / MHF III pigtail + FPC (Inventek B24P-W). Not a PCB-antenna module |
