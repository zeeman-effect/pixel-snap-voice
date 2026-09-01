#!/usr/bin/env python3
"""Firmware pin map: module GPIO name, net, electrical type. Change this file, custom.h, and pinmap.md together."""

from __future__ import annotations

# GPIO <-> net on U1 (ESP32-S3-MINI-1U-N8). Keep in lockstep with
# firmware/boards/custom.h PSV_*_GPIO macros via check_pins.py.
MCU_PINS = [
    ("3V3", "3V3", "power_in"),
    ("GND", "GND", "power_in"),
    ("EN", "EN", "input"),
    ("GPIO0", "BOOT", "bidirectional"),
    ("GPIO1", "BTN", "bidirectional"),
    ("GPIO2", "LED", "bidirectional"),
    ("GPIO4", "I2C_SDA", "bidirectional"),
    ("GPIO5", "I2C_SCL", "bidirectional"),
    ("GPIO6", "SD_D0", "bidirectional"),
    ("GPIO7", "SD_CMD", "bidirectional"),
    ("GPIO8", "PA_EN", "output"),
    ("GPIO9", "CHG_STAT", "input"),
    ("GPIO10", "I2S_DIN", "input"),
    ("GPIO11", "I2S_DOUT", "output"),
    ("GPIO12", "I2S_WS", "input"),
    ("GPIO13", "I2S_BCLK", "input"),
    ("GPIO14", "I2S_MCLK", "input"),
    ("GPIO15", "SD_CLK", "output"),
    ("GPIO16", "SD_D1", "bidirectional"),
    ("GPIO17", "SD_D2", "bidirectional"),
    ("GPIO18", "SD_D3", "bidirectional"),
    ("GPIO19", "USB_DM", "bidirectional"),
    ("GPIO20", "USB_DP", "bidirectional"),
]
