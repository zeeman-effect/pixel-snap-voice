#include "clock.h"
#include "clock_rtc.h"

#include <stdio.h>
#include <string.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

#include "esp_log.h"
#include "storage_sd.h"

static const char *TAG = "psv.clock";

void clock_now(ClockCivil *out)
{
    time_t t = time(NULL);
    struct tm tm;
    gmtime_r(&t, &tm);
    out->year = tm.tm_year + 1900;
    if (out->year < 2000) {
        out->year = 2000;
    }
    out->month = tm.tm_mon + 1;
    out->day = tm.tm_mday;
    out->hour = tm.tm_hour;
    out->minute = tm.tm_min;
    out->second = tm.tm_sec;
}

esp_err_t clock_try_set_from_volume(void)
{
    char path[256];
    FILE *fp;
    int y, mo, d, h, mi, s;
    struct tm tm;
    struct timeval tv;

    snprintf(path, sizeof(path), "%s/set_time.txt", storage_sd_mount_point());
    fp = fopen(path, "r");
    if (!fp) {
        return ESP_ERR_NOT_FOUND;
    }
    if (fscanf(fp, "%d-%d-%d %d:%d:%d", &y, &mo, &d, &h, &mi, &s) != 6) {
        fclose(fp);
        ESP_LOGW(TAG, "set_time.txt parse failed (want YYYY-MM-DD HH:MM:SS)");
        return ESP_ERR_INVALID_ARG;
    }
    fclose(fp);

    memset(&tm, 0, sizeof(tm));
    tm.tm_year = y - 1900;
    tm.tm_mon = mo - 1;
    tm.tm_mday = d;
    tm.tm_hour = h;
    tm.tm_min = mi;
    tm.tm_sec = s;
    tv.tv_sec = mktime(&tm);
    tv.tv_usec = 0;
    if (tv.tv_sec < 0 || settimeofday(&tv, NULL) != 0) {
        return ESP_FAIL;
    }
    unlink(path);
    ESP_LOGI(TAG, "RTC set to %04d-%02d-%02d %02d:%02d:%02d UTC", y, mo, d, h, mi, s);
    return ESP_OK;
}
