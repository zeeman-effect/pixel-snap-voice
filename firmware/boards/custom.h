#pragma once

#include "driver/gpio.h"

/*
 * Custom slim PCB (hardware/kicad/pinmap.md; matches recorder/ refs).
 * ES8311 is I2S master (12.288 MHz oscillator into MCLK). S3 is I2S slave.
 * Analog MEMS into ES8311 ADC. NS4150 on ES8311 AOUT.
 *
 * Strapping pins GPIO0 / GPIO45 / GPIO46 are left alone.
 */

#define PSV_BOARD_NAME "custom"

#define PSV_I2C_PORT I2C_NUM_0
#define PSV_I2C_SCL GPIO_NUM_5
#define PSV_I2C_SDA GPIO_NUM_4

#define PSV_I2S_MCLK GPIO_NUM_14 /* from codec MCLK */
#define PSV_I2S_BCLK GPIO_NUM_13
#define PSV_I2S_WS GPIO_NUM_12
#define PSV_I2S_DOUT GPIO_NUM_11 /* S3 → ES8311 DSDIN */
#define PSV_I2S_DIN GPIO_NUM_10  /* ES8311 ASDOUT → S3 */

#define PSV_PA_EN GPIO_NUM_8
#define PSV_CODEC_I2C_ADDR 0x18
#define PSV_ADC_I2C_ADDR 0x18

#define PSV_I2S_SLAVE 1
#define PSV_HAS_ES7210 0
#define PSV_CODEC_MASTER 1

#define PSV_SD_CLK GPIO_NUM_15
#define PSV_SD_CMD GPIO_NUM_7
#define PSV_SD_D0 GPIO_NUM_6
#define PSV_SD_D1 GPIO_NUM_16
#define PSV_SD_D2 GPIO_NUM_17
#define PSV_SD_D3 GPIO_NUM_18
#define PSV_SD_4BIT 1

#define PSV_BTN_GPIO GPIO_NUM_1
#define PSV_BTN_ADC 0
#define PSV_BTN_ACTIVE_LOW 1

#define PSV_LED_GPIO GPIO_NUM_2
#define PSV_LED_ACTIVE_LOW 0

#define PSV_CHG_STAT GPIO_NUM_9
#define PSV_WAKE_GPIO GPIO_NUM_1
