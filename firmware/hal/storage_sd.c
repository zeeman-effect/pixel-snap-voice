#include "storage.h"
#include "storage_sd.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include "board.h"
#include "esp_log.h"
#include "esp_vfs_fat.h"
#include "ff.h"
#include "sdmmc_cmd.h"

struct StorageFile {
    FILE *fp;
};

static const char *TAG = "psv.sd";
static sdmmc_card_t *g_card;
static char g_mount[64] = "/sdcard";

static void join_path(char *out, size_t n, const char *rel)
{
    if (!rel || rel[0] == '\0') {
        snprintf(out, n, "%s", g_mount);
        return;
    }
    snprintf(out, n, "%s/%s", g_mount, rel);
}

esp_err_t storage_sd_mount(void)
{
    snprintf(g_mount, sizeof(g_mount), "%s", PSV_SD_MOUNT);

    if (PSV_SD_CLK == GPIO_NUM_NC || PSV_SD_CMD == GPIO_NUM_NC || PSV_SD_D0 == GPIO_NUM_NC) {
        ESP_LOGE(TAG, "no SD pins on %s — use Korvo-2 or the custom PCB", PSV_BOARD_NAME);
        return ESP_ERR_NOT_SUPPORTED;
    }

    esp_vfs_fat_sdmmc_mount_config_t mount_cfg = {
        .format_if_mount_failed = false,
        .max_files = 8,
        .allocation_unit_size = 16 * 1024,
    };
    sdmmc_host_t host = SDMMC_HOST_DEFAULT();
    host.max_freq_khz = SDMMC_FREQ_HIGHSPEED;

    sdmmc_slot_config_t slot = SDMMC_SLOT_CONFIG_DEFAULT();
    slot.width = PSV_SD_4BIT ? 4 : 1;
    slot.clk = PSV_SD_CLK;
    slot.cmd = PSV_SD_CMD;
    slot.d0 = PSV_SD_D0;
    if (PSV_SD_4BIT) {
        slot.d1 = PSV_SD_D1;
        slot.d2 = PSV_SD_D2;
        slot.d3 = PSV_SD_D3;
    }
    slot.flags |= SDMMC_SLOT_FLAG_INTERNAL_PULLUP;

    esp_err_t err = esp_vfs_fat_sdmmc_mount(g_mount, &host, &slot, &mount_cfg, &g_card);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "SD mount failed: %s", esp_err_to_name(err));
        return err;
    }
    ESP_LOGI(TAG, "SD mounted at %s", g_mount);
    return ESP_OK;
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
    esp_err_t err = esp_vfs_fat_sdcard_unmount(g_mount, g_card);
    g_card = NULL;
    return err;
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
