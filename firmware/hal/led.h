#pragma once

#include "esp_err.h"

typedef enum {
    PSV_LED_OFF = 0,
    PSV_LED_RECORD,
    PSV_LED_PLAY,
    PSV_LED_CHARGE,
    PSV_LED_ERROR
} psv_led_mode_t;

esp_err_t led_init(void);
void led_set(psv_led_mode_t mode);
void led_tick(void);
