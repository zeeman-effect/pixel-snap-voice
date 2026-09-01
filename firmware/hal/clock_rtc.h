#pragma once

#include "esp_err.h"

/* Apply /sdcard/set_time.txt if present (YYYY-MM-DD HH:MM:SS). */
esp_err_t clock_try_set_from_volume(void);
