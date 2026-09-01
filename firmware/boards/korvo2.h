#pragma once

#include "driver/gpio.h"
#include "hal/adc_types.h"

/*
 * ESP32-S3-Korvo-2 V3.0 / V3.1 pin map (Espressif user guide).
 *
 * Capture is ES7210 (on-board mics). Playback is ES8311 + NS4150.
 * ES8311 ASDOUT is not wired to the S3 — do not expect codec-ADC capture here.
 * I2S clocks follow Espressif's example (S3 as I2S master) for Phase 0 only.
 */

#define PSV_BOARD_NAME "korvo2"

#define PSV_I2C_PORT I2C_NUM_0
#define PSV_I2C_SCL GPIO_NUM_18
#define PSV_I2C_SDA GPIO_NUM_17

#define PSV_I2S_MCLK GPIO_NUM_16
#define PSV_I2S_BCLK GPIO_NUM_9
#define PSV_I2S_WS GPIO_NUM_45
#define PSV_I2S_DOUT GPIO_NUM_8  /* S3 → ES8311 DSDIN */
#define PSV_I2S_DIN GPIO_NUM_10  /* ES7210 SDOUT → S3 */

#define PSV_PA_EN GPIO_NUM_48
#define PSV_CODEC_I2C_ADDR 0x18
#define PSV_ADC_I2C_ADDR 0x40 /* ES7210 typical 8-bit 0x80 → 7-bit 0x40 */

#define PSV_I2S_SLAVE 0 /* S3 is I2S master on this board */

#define PSV_HAS_ES7210 1
#define PSV_CODEC_MASTER 0

#define PSV_SD_CLK GPIO_NUM_15
#define PSV_SD_CMD GPIO_NUM_7
#define PSV_SD_D0 GPIO_NUM_4
#define PSV_SD_D1 GPIO_NUM_NC
#define PSV_SD_D2 GPIO_NUM_NC
#define PSV_SD_D3 GPIO_NUM_NC
#define PSV_SD_4BIT 0

#define PSV_BTN_GPIO GPIO_NUM_5 /* analog key ladder; ADC1_CH4 */
#define PSV_BTN_ADC 1
#define PSV_BTN_ADC_CHANNEL ADC_CHANNEL_4
#define PSV_BTN_ACTIVE_LOW 1

#define PSV_LED_GPIO GPIO_NUM_NC /* LEDs sit on the TCA9554 expander */
#define PSV_LED_ACTIVE_LOW 0

#define PSV_CHG_STAT GPIO_NUM_NC
#define PSV_WAKE_GPIO GPIO_NUM_5
