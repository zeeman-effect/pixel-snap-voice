#pragma once

#include "esp_err.h"

esp_err_t wifi_share_start(void);
void wifi_share_stop(void);
int wifi_share_active(void);
