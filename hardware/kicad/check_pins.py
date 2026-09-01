#!/usr/bin/env python3
"""Fail if firmware/boards/custom.h drifts from pins.MCU_PINS."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from pins import MCU_PINS

HERE = Path(__file__).resolve().parent
CUSTOM = HERE.parent.parent / "firmware" / "boards" / "custom.h"

NET_TO_MACRO = {
    "I2C_SDA": "PSV_I2C_SDA",
    "I2C_SCL": "PSV_I2C_SCL",
    "I2S_MCLK": "PSV_I2S_MCLK",
    "I2S_BCLK": "PSV_I2S_BCLK",
    "I2S_WS": "PSV_I2S_WS",
    "I2S_DOUT": "PSV_I2S_DOUT",
    "I2S_DIN": "PSV_I2S_DIN",
    "PA_EN": "PSV_PA_EN",
    "SD_CLK": "PSV_SD_CLK",
    "SD_CMD": "PSV_SD_CMD",
    "SD_D0": "PSV_SD_D0",
    "SD_D1": "PSV_SD_D1",
    "SD_D2": "PSV_SD_D2",
    "SD_D3": "PSV_SD_D3",
    "BTN": "PSV_BTN_GPIO",
    "LED": "PSV_LED_GPIO",
    "CHG_STAT": "PSV_CHG_STAT",
}


def gpio_from_pin(name: str) -> int | None:
    if not name.startswith("GPIO"):
        return None
    return int(name[4:])


def parse_custom(text: str) -> dict[str, int]:
    found: dict[str, int] = {}
    for m in re.finditer(r"#define\s+(PSV_\w+)\s+GPIO_NUM_(\d+)\b", text):
        found[m.group(1)] = int(m.group(2))
    return found


def main() -> int:
    errors: list[str] = []
    custom = parse_custom(CUSTOM.read_text(encoding="utf-8"))
    for pin, net, _ in MCU_PINS:
        gpio = gpio_from_pin(pin)
        macro = NET_TO_MACRO.get(net)
        if gpio is None or macro is None:
            continue
        have = custom.get(macro)
        if have is None:
            errors.append(f"{macro} missing in custom.h (want GPIO{gpio} for {net})")
        elif have != gpio:
            errors.append(f"{macro} is GPIO{have} in custom.h, pin table has GPIO{gpio} ({net})")

    if "PSV_WAKE_GPIO" in custom and custom.get("PSV_BTN_GPIO") != custom.get("PSV_WAKE_GPIO"):
        errors.append("PSV_WAKE_GPIO must match PSV_BTN_GPIO")

    if errors:
        print("check_pins: FAIL")
        for e in errors:
            print(" ", e)
        return 1
    print(f"check_pins: ok ({len(NET_TO_MACRO)} GPIOs match custom.h)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
