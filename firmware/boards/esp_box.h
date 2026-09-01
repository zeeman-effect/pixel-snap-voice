#pragma once

#include "driver/gpio.h"

/*
 * ESP-BOX / ESP-BOX-3 pin map (esp-bsp).
 * Playback: ES8311 + PA GPIO46. Capture: ES7210 on I2S DIN.
 */

#define PSV_BOARD_NAME "esp_box"

#define PSV_I2C_PORT I2C_NUM_0
#define PSV_I2C_SCL GPIO_NUM_18
#define PSV_I2C_SDA GPIO_NUM_8

#define PSV_I2S_MCLK GPIO_NUM_2
#define PSV_I2S_BCLK GPIO_NUM_17
#define PSV_I2S_WS GPIO_NUM_45
#define PSV_I2S_DOUT GPIO_NUM_15
#define PSV_I2S_DIN GPIO_NUM_16

#define PSV_PA_EN GPIO_NUM_46
#define PSV_CODEC_I2C_ADDR 0x18
#define PSV_ADC_I2C_ADDR 0x40

#define PSV_I2S_SLAVE 0
#define PSV_HAS_ES7210 1
#define PSV_CODEC_MASTER 0

#define PSV_SD_CLK GPIO_NUM_NC
#define PSV_SD_CMD GPIO_NUM_NC
#define PSV_SD_D0 GPIO_NUM_NC
#define PSV_SD_D1 GPIO_NUM_NC
#define PSV_SD_D2 GPIO_NUM_NC
#define PSV_SD_D3 GPIO_NUM_NC
#define PSV_SD_4BIT 0

#define PSV_BTN_GPIO GPIO_NUM_1 /* mute / function */
#define PSV_BTN_ADC 0
#define PSV_BTN_ACTIVE_LOW 1

#define PSV_LED_GPIO GPIO_NUM_NC
#define PSV_LED_ACTIVE_LOW 0

#define PSV_CHG_STAT GPIO_NUM_NC
#define PSV_WAKE_GPIO GPIO_NUM_1
