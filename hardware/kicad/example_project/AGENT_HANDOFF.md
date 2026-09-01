# Learning schematic handoff

Continue a supervised KiCad 10 schematic lesson. Zach is drawing `hardware/kicad/example_project` by hand to compare later with `hardware/kicad/recorder/`. He does the edits. You review, correct, and give **one** next step. Do not make large unsupervised edits. Fix a section only when he asks.

This file is the brief. Do not load the full prior chat.

## Overrides

Workspace rule says do not edit `example_project`. **This lesson overrides that.** You may read and, with his OK, make small fixes there.

Do **not** edit the product tree `hardware/kicad/recorder/` as part of this lesson. Compare his sheet to `recorder/` for refs and nets. Do not treat `recorder/` as a pin-for-pin copy-paste template. Architecture truth: `docs/architecture.md`, `docs/audio-platform.md`, `docs/bom.md`, `hardware/kicad/pinmap.md`, `hardware/cad/params.json` (`mcu` = ESP32-S3-MINI-1U-N8, no radio, no PCB antenna).

v1: USB recorder, 5 V sink only, no OTG host, no PD, no Wi-Fi.

Be brief. Plain language. Define a term once. Conserve chat context: review the `.kicad_sch` (or `.history` if newer) instead of dumping sheets into the thread.

## How he works

- KiCad 10. Schematic: `hardware/kicad/example_project/example_project.kicad_sch`
- **Toolbar Save works. Ctrl+S often does not.** Check Hotkeys → Save. Local history (`.history/example_project.kicad_sch`) can be newer than the project file. If the repo file looks stale, read history and tell him to Save.
- `Q` is Place → no-connection flag, not a symbol named Q.
- Net labels (`L`) name a net only if they sit on a wire. Generic connector pin names are hidden in the library; he cannot rename `Pin_1` from properties.
- Power symbol **Value** is the net name (`VDD33`, `VBUS`, `VBUS_CHG`, `VBAT`). `Earth` ≠ `GND`.
- ERC `pin_not_connected` on unused GPIOs is expected. Do not `Q` pins he will use later (I2C, I2S, SD, button, LED).
- ERC `power_pin_not_driven` on named rails is expected until a regulator or `PWR_FLAG` exists. Do not fake-fix with `PWR_FLAG` unless you are teaching that on purpose.

## What is on the sheet (as of 2026-08-30)

**MCU**

- U1 `ESP32-S3-MINI-1` symbol, value `ESP32-S3-MINI-1U`, footprint `PCM_Espressif:ESP32-S3-MINI-1U`. Correct pairing (same pins, IPEX on module).
- Pin 3 `3V3` → `VDD33`. Stacked GND → `GND`.
- EN RC: R1 `10K`, C2 `1 µF` (datasheet §9 / Fig 9-1).
- C1 `22 µF` + C3 `0.1 µF` on `VDD33`.
- J1 UART 1×4: pin1 `3V3`, pin2 U0RXD (GPIO44), pin3 U0TXD (GPIO43), pin4 `GND`. Labels `UART_TX` / `UART_RX` plus adapter TX/RX notes. MCU TX → adapter RX.

**USB-C (J2)**

- `Connector:USB_C_Receptacle_USB2.0_16P` (keep 16P; 14P drops SBU only). Not a Plug.
- GPIO20 → D+ (A6 shorted to B6). GPIO19 → D− (A7 shorted to B7). Labels `USB_DP` / `USB_DM` on the wires (~x=233).
- CC1 and CC2 each have their own `5.11k` (R2, R3) to `GND`. Not tied together.
- SBU1 / SBU2 unused. Shield still open (OK).
- Do **not** copy Fig 9-1 OTG (no ID pin, no host VBUS out). USB-C role is CC pulldowns.

**5 V / charger** (confirmed with `kicad-cli sch export netlist`, not raw coordinates)

- J2 A4/A9/B4/B9 VBUS → F1 pin 2. F1 pin 1 → `VBUS_CHG` → C4 pin 1 and U2 pin 4 `V_{DD}`.
- U2 `MCP73831-2-OT` (BOM U3 / `MCP73831T-2ACI/OT`). VSS pin 2 → `GND`. PROG pin 5 → R4 `2k` → `GND`.
- C4 `4.7 µF` on `VBUS_CHG` to `GND`. C5 `4.7 µF` on `+BATT` to `GND`.
- The old short at `(250.19, 44.45)`–`(250.19, 48.26)` is gone. `+BATT` ≠ `VBUS_CHG`.
- `#PWR010` is `power:+BATT`, Value `+BATT`. That net is U2 pin 3 `V_{BAT}` + C5. Electrically right. Rename Value to `VBAT` so the rail matches the lesson names.
- STAT pin 1 is open. ERC `pin_not_connected` at `(276.86, 58.42)`. Put `Q` until the LED.

Do not infer U2 pin nets from file coordinates. `kicad-cli` is `%LOCALAPPDATA%\Programs\KiCad\10.0\bin\kicad-cli.exe`.

## Open defect

None that blocks new parts. Optional cleanup: Value `+BATT` → `VBAT`, and `Q` on STAT.

## Suggested next steps (one at a time)

1. Rename `+BATT` to `VBAT`, `Q` on STAT. Then the 2-pin battery connector: `VBAT` and `GND`. Not to `VDD33`.
2. Battery connector (2-pin): `VBAT` and `GND`. Not to `VDD33`.
3. MCU 3.3 V LDO (BOM U4 `AP2112K-3.3`): VIN from `VBAT` (through load switch later), VOUT = `VDD33`. This clears the “magic 3V3” rail. Do not feed the LDO from raw VBUS.
4. Load switch (BOM U5 AP22804) on 3.3 V if you want sleep current next.
5. USB ESD `USBLC6-2SC6` on D+/D−, or analog 3V3A LDO (recorder: U8 LP5907), then ES8311. Codec is I2S **master**, 12.288 MHz oscillator into MCLK. Pin map: `hardware/kicad/pinmap.md`.
6. Leave IPEX unused (no cable in v1).

Do not start the codec until `VDD33` is generated from `VBAT` and the three rails stay separate: **5 V USB / ~4.2 V cell / 3.3 V MCU**.

## KiCad facts he already hit

- MINI-1 vs MINI-1U: same pin table. 1U is IPEX, no board antenna pin.
- Table 3-1: pin 3 only `3V3`; many stacked GND; EN must not float; USB_D− = GPIO19, USB_D+ = GPIO20. S3 PHY, no 22 Ω series.
- 16P has separate A6/B6 and A7/B7. Short same-name pairs or a flipped cable has no data.
- MCP73831 needs ≥4.7 µF on VDD and on VBAT.

## Style

Review what he drew. Name concrete nets and pins. One next action. No recorder-sheet copy-paste. No large refactors.