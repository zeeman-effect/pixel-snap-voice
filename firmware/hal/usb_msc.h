#pragma once

#include "esp_err.h"

esp_err_t usb_msc_init(void);
int usb_msc_host_present(void);
