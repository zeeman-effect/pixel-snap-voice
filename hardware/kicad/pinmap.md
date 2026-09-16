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
| GPIO8 | PA_EN | output | U6 NS4150 CTRL |
| GPIO15 | SD_CLK | output | **J3** |
| GPIO7 | SD_CMD | bidirectional | **J3** |
| GPIO6 / 16 / 17 / 18 | SD_D0–D3 | bidirectional | **J3** 4-bit SDMMC |
| GPIO1 | BTN | input, pull-up | SW1 to GND |
| GPIO2 | LED | output | D1 |
| GPIO9 | CHG_STAT | input | U3 STAT (D2 charge LED on this net) |
| GPIO43 / GPIO44 | UART_TX / UART_RX | UART0 | **J1** 1×4 (3V3, U0RXD, U0TXD, GND) |

## Other

| Net | Notes |
| --- | --- |
| CC1 / CC2 | R2 / R3 5.11 kΩ to GND (UFP) on J2 |
| **VDD33** | U4 AP2112 → U5 AP22804. MCU digital rail |
| 3V3A | U8 LP5907 from **VSYS**; star return to AGND; no digital return through MK1 |
| VBAT | LiPo pouch on BT1; U3 BQ24074 BAT pin only. Do not strap to VSYS |
| VSYS | U3 OUT. USB or cell, whichever is up. Feeds U4, U8, U6 |
| RF | MINI-1U IPEX connector, no cable in v1 |
