#pragma once

#include "esp_err.h"

esp_err_t power_init(void);
void power_deep_sleep(void);
int power_charging(void);
