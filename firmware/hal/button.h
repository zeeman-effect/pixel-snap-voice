#pragma once

#include "esp_err.h"

typedef enum {
    PSV_BTN_NONE = 0,
    PSV_BTN_SHORT,
    PSV_BTN_DOUBLE,
    PSV_BTN_LONG
} psv_btn_event_t;

esp_err_t button_init(void);
psv_btn_event_t button_poll(void);
