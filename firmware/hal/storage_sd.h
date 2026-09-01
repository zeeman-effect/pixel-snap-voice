#pragma once

#include "esp_err.h"
#include "sdmmc_cmd.h"

esp_err_t storage_sd_mount(void);
esp_err_t storage_sd_unmount(void);
sdmmc_card_t *storage_sd_card(void);
const char *storage_sd_mount_point(void);
