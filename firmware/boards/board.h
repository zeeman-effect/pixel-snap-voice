#pragma once

#include "sdkconfig.h"

#if defined(CONFIG_PSV_BOARD_KORVO2)
#include "korvo2.h"
#elif defined(CONFIG_PSV_BOARD_ESP_BOX)
#include "esp_box.h"
#else
#include "custom.h"
#endif

#ifndef PSV_SD_MOUNT
#define PSV_SD_MOUNT CONFIG_PSV_SD_MOUNT_POINT
#endif
