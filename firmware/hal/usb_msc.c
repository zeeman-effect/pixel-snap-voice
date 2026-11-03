#include "usb_msc.h"

#include "board.h"
#include "esp_log.h"
#include "esp_vfs_fat.h"
#include "recorder.h"
#include "sdkconfig.h"
#include "storage_sd.h"

#if CONFIG_PSV_USB_MSC
#include "tinyusb.h"
#include "tusb_msc_storage.h"
#endif

static const char *TAG = "psv.usb";
static volatile int s_host;
#if CONFIG_PSV_USB_MSC
static int s_inited;
#endif

#if CONFIG_PSV_USB_MSC

/*
 * IDF 5.1 / esp_tinyusb 1.4: TINYUSB_MSC_EVENT_MOUNT_CHANGED.
 * is_mounted means the recorder VFS owns the NAND, not the USB host.
 * TinyUSB unmounts VFS in tud_mount_cb and remounts in tud_umount_cb.
 * Do not also keep esp_vfs_fat_sdmmc_mount on the same card.
 */
static void msc_event(tinyusb_msc_event_t *event)
{
    int host;

    if (!event) {
        return;
    }

    if (event->type == TINYUSB_MSC_EVENT_PREMOUNT_CHANGED) {
        /* FAT is still in VFS. Close the WAV before TinyUSB unregisters it. */
        if (event->mount_changed_data.is_mounted) {
            s_host = 1;
            recorder_on_usb_attach();
        }
        return;
    }

    if (event->type != TINYUSB_MSC_EVENT_MOUNT_CHANGED) {
        return;
    }

    host = event->mount_changed_data.is_mounted ? 0 : 1;
    s_host = host;
    if (host) {
        recorder_on_usb_attach();
        ESP_LOGI(TAG, "USB host mounted MSC");
    } else {
        recorder_on_usb_detach();
        ESP_LOGI(TAG, "USB host unmounted MSC");
    }
}

esp_err_t usb_msc_init(void)
{
    sdmmc_card_t *card = storage_sd_card();
    const char *mount = storage_sd_mount_point();
    esp_err_t err;

    if (!card) {
        ESP_LOGW(TAG, "MSC skipped (no SD card)");
        return ESP_ERR_INVALID_STATE;
    }

    const tinyusb_msc_sdmmc_config_t msc_cfg = {
        .card = card,
        .callback_mount_changed = msc_event,
        .callback_premount_changed = msc_event,
        .mount_config =
            {
                .format_if_mount_failed = PSV_SD_FORMAT_IF_BLANK,
                .max_files = 8,
                .allocation_unit_size = 16 * 1024,
            },
    };
    err = tinyusb_msc_storage_init_sdmmc(&msc_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "MSC storage init: %s", esp_err_to_name(err));
        return err;
    }

    err = tinyusb_msc_storage_mount(mount);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "MSC VFS mount: %s", esp_err_to_name(err));
        return err;
    }
    ESP_LOGI(TAG, "SD mounted at %s (TinyUSB)", mount);

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
    s_inited = 1;
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
#if CONFIG_PSV_USB_MSC
    if (s_inited && tinyusb_msc_storage_in_use_by_usb_host()) {
        return 1;
    }
#endif
    return s_host;
}
