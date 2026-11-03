#include "storage.h"
#include "storage_sd.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include "board.h"
#include "driver/sdmmc_host.h"
#include "esp_log.h"
#include "esp_vfs_fat.h"
#include "ff.h"
#include "sdkconfig.h"
#include "sdmmc_cmd.h"

struct StorageFile {
    FILE *fp;
};

static const char *TAG = "psv.sd";
static sdmmc_card_t *g_card;
static int g_vfs_self;
static char g_mount[64] = "/sdcard";
#if CONFIG_PSV_USB_MSC
static sdmmc_host_t g_host;
#endif

static void join_path(char *out, size_t n, const char *rel)
{
    if (!rel || rel[0] == '\0') {
        snprintf(out, n, "%s", g_mount);
        return;
    }
    snprintf(out, n, "%s/%s", g_mount, rel);
}

static void fill_slot(sdmmc_slot_config_t *slot)
{
    *slot = SDMMC_SLOT_CONFIG_DEFAULT();
    slot->width = PSV_SD_4BIT ? 4 : 1;
    slot->clk = PSV_SD_CLK;
    slot->cmd = PSV_SD_CMD;
    slot->d0 = PSV_SD_D0;
    if (PSV_SD_4BIT) {
        slot->d1 = PSV_SD_D1;
        slot->d2 = PSV_SD_D2;
        slot->d3 = PSV_SD_D3;
    }
    slot->flags |= SDMMC_SLOT_FLAG_INTERNAL_PULLUP;
}

#if CONFIG_PSV_USB_MSC
/*
 * Init the SDMMC card only. TinyUSB mounts FAT to VFS and takes the NAND
 * exclusively while a USB host is mounted (Espressif tusb_msc SDMMC example).
 */
static esp_err_t init_sdmmc_card(void)
{
    sdmmc_slot_config_t slot;
    esp_err_t err;

    g_host = SDMMC_HOST_DEFAULT();
    g_host.max_freq_khz = SDMMC_FREQ_HIGHSPEED;
    fill_slot(&slot);

    g_card = (sdmmc_card_t *)calloc(1, sizeof(*g_card));
    if (!g_card) {
        return ESP_ERR_NO_MEM;
    }

    err = (*g_host.init)();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "SD host init: %s", esp_err_to_name(err));
        free(g_card);
        g_card = NULL;
        return err;
    }

    err = sdmmc_host_init_slot(g_host.slot, &slot);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "SD slot init: %s", esp_err_to_name(err));
        goto fail;
    }
    err = sdmmc_card_init(&g_host, g_card);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "SD card init: %s", esp_err_to_name(err));
        goto fail;
    }
    ESP_LOGI(TAG, "SD card ready (VFS via TinyUSB)");
    return ESP_OK;

fail:
    if (g_host.flags & SDMMC_HOST_FLAG_DEINIT_ARG) {
        g_host.deinit_p(g_host.slot);
    } else if (g_host.deinit) {
        (*g_host.deinit)();
    }
    free(g_card);
    g_card = NULL;
    return err;
}
#else
static esp_err_t mount_vfs_sdmmc(void)
{
    esp_vfs_fat_sdmmc_mount_config_t mount_cfg = {
        .format_if_mount_failed = PSV_SD_FORMAT_IF_BLANK,
        .max_files = 8,
        .allocation_unit_size = 16 * 1024,
    };
    sdmmc_host_t host = SDMMC_HOST_DEFAULT();
    sdmmc_slot_config_t slot;
    esp_err_t err;

    host.max_freq_khz = SDMMC_FREQ_HIGHSPEED;
    fill_slot(&slot);
    err = esp_vfs_fat_sdmmc_mount(g_mount, &host, &slot, &mount_cfg, &g_card);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "SD mount failed: %s", esp_err_to_name(err));
        return err;
    }
    g_vfs_self = 1;
    ESP_LOGI(TAG, "SD mounted at %s", g_mount);
    return ESP_OK;
}
#endif

esp_err_t storage_sd_mount(void)
{
    snprintf(g_mount, sizeof(g_mount), "%s", PSV_SD_MOUNT);

    if (PSV_SD_CLK == GPIO_NUM_NC || PSV_SD_CMD == GPIO_NUM_NC || PSV_SD_D0 == GPIO_NUM_NC) {
        ESP_LOGE(TAG, "no SD pins on %s — use Korvo-2 or the custom PCB", PSV_BOARD_NAME);
        return ESP_ERR_NOT_SUPPORTED;
    }

    if (PSV_SD_FORMAT_IF_BLANK) {
        ESP_LOGI(TAG, "soldered NAND: format if the volume has no FAT");
    }

#if CONFIG_PSV_USB_MSC
    return init_sdmmc_card();
#else
    return mount_vfs_sdmmc();
#endif
}

sdmmc_card_t *storage_sd_card(void)
{
    return g_card;
}

const char *storage_sd_mount_point(void)
{
    return g_mount;
}

esp_err_t storage_sd_unmount(void)
{
    if (!g_card) {
        return ESP_OK;
    }
    if (g_vfs_self) {
        esp_err_t err = esp_vfs_fat_sdcard_unmount(g_mount, g_card);
        g_card = NULL;
        g_vfs_self = 0;
        return err;
    }
    /* TinyUSB owns FAT. Leave the card and host up. */
    return ESP_OK;
}

int storage_mkdir(const char *path)
{
    char full[768];
    join_path(full, sizeof(full), path);
    if (mkdir(full, 0755) != 0 && errno != EEXIST) {
        return -1;
    }
    return 0;
}

static int open_mode(const char *path, const char *mode, StorageFile **out)
{
    char full[768];
    StorageFile *f;
    FILE *fp;

    join_path(full, sizeof(full), path);
    fp = fopen(full, mode);
    if (!fp) {
        return -1;
    }
    f = (StorageFile *)calloc(1, sizeof(*f));
    if (!f) {
        fclose(fp);
        return -1;
    }
    f->fp = fp;
    *out = f;
    return 0;
}

int storage_open_write(const char *path, StorageFile **out)
{
    return open_mode(path, "wb+", out);
}

int storage_open_read(const char *path, StorageFile **out)
{
    return open_mode(path, "rb", out);
}

int storage_write(StorageFile *f, const void *data, size_t len)
{
    if (!f || !f->fp) {
        return -1;
    }
    return fwrite(data, 1, len, f->fp) == len ? 0 : -1;
}

int storage_read(StorageFile *f, void *data, size_t len, size_t *got)
{
    size_t n;
    if (got) {
        *got = 0;
    }
    if (!f || !f->fp || !data) {
        return -1;
    }
    n = fread(data, 1, len, f->fp);
    if (got) {
        *got = n;
    }
    if (n < len && ferror(f->fp)) {
        return -1;
    }
    return 0;
}

int storage_seek(StorageFile *f, long offset)
{
    if (!f || !f->fp) {
        return -1;
    }
    return fseek(f->fp, offset, SEEK_SET) == 0 ? 0 : -1;
}

int storage_close(StorageFile *f)
{
    if (!f) {
        return 0;
    }
    if (f->fp) {
        fclose(f->fp);
    }
    free(f);
    return 0;
}

int64_t storage_free_bytes(void)
{
    FATFS *fs = NULL;
    DWORD nclst = 0;
    if (!g_card) {
        return -1;
    }
    if (f_getfree("0:", &nclst, &fs) != FR_OK || !fs) {
        return -1;
    }
    return (int64_t)nclst * (int64_t)fs->csize * 512;
}
