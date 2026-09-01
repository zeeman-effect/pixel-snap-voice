#include "usb_msc.h"

#include "board.h"
#include "esp_log.h"
#include "recorder.h"
#include "sdkconfig.h"
#include "storage_sd.h"

static const char *TAG = "psv.usb";
static volatile int s_host;

#if CONFIG_PSV_USB_MSC

#include "tinyusb.h"
#include "tusb_msc_storage.h"

static void msc_event(tinyusb_msc_event_t *event)
{
    if (!event) {
        return;
    }
    if (event->type == TINYUSB_MSC_EVENT_MOUNT) {
        s_host = 1;
        recorder_on_usb_attach();
        ESP_LOGI(TAG, "USB host mounted MSC");
    } else if (event->type == TINYUSB_MSC_EVENT_UNMOUNT) {
        s_host = 0;
        recorder_on_usb_detach();
        ESP_LOGI(TAG, "USB host unmounted MSC");
    }
}

esp_err_t usb_msc_init(void)
{
    sdmmc_card_t *card = storage_sd_card();
    if (!card) {
        ESP_LOGW(TAG, "MSC skipped (no SD card)");
        return ESP_ERR_INVALID_STATE;
    }

    const tinyusb_msc_sdmmc_config_t msc_cfg = {
        .card = card,
        .callback_mount_changed = msc_event,
    };
    esp_err_t err = tinyusb_msc_storage_init_sdmmc(&msc_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "MSC storage init: %s", esp_err_to_name(err));
        return err;
    }

    const tinyusb_config_t tusb_cfg = {
        .device_descriptor = NULL,
        .string_descriptor = NULL,
        .external_phy = false,
        .configuration_descriptor = NULL,
    };
    err = tinyusb_driver_install(&tusb_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "tinyusb install: %s", esp_err_to_name(err));
        return err;
    }
    ESP_LOGI(TAG, "TinyUSB MSC ready");
    return ESP_OK;
}

#else

esp_err_t usb_msc_init(void)
{
    ESP_LOGI(TAG, "MSC disabled (CONFIG_PSV_USB_MSC=n) — use an SD reader for Phase 0");
    return ESP_OK;
}

#endif

int usb_msc_host_present(void)
{
    return s_host;
}
