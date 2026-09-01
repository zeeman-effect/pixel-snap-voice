#include <dirent.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

#include "audio.h"
#include "board.h"
#include "button.h"
#include "clock_rtc.h"
#include "config.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "led.h"
#include "nvs_flash.h"
#include "power.h"
#include "recorder.h"
#include "storage_sd.h"
#include "usb_msc.h"

static const char *TAG = "psv";

/*
 * Buttons (one tactile on the custom board; Korvo ladder = any key):
 *   short press  — start / stop recording
 *   double press — play last file
 *   long press   — deep sleep (wake on the same button)
 *
 * USB attach always wins: record and play stop, TinyUSB MSC owns the card.
 */

static uint8_t s_pcm[4096];

static void led_from_state(void)
{
    switch (recorder_state()) {
    case RECORDER_RECORDING:
        led_set(PSV_LED_RECORD);
        break;
    case RECORDER_PLAYING:
        led_set(PSV_LED_PLAY);
        break;
    case RECORDER_ERROR:
        led_set(PSV_LED_ERROR);
        break;
    case RECORDER_USB_MSC:
        led_set(PSV_LED_CHARGE);
        break;
    default:
        led_set(PSV_LED_OFF);
        break;
    }
}

static void toggle_record(void)
{
    if (recorder_state() == RECORDER_RECORDING) {
        (void)recorder_stop();
        (void)audio_stop();
        ESP_LOGI(TAG, "stopped %s (%u bytes)", recorder_last_path(), recorder_data_bytes());
        return;
    }
    if (audio_start_record() != ESP_OK) {
        ESP_LOGE(TAG, "audio record start failed");
        return;
    }
    RecorderStatus st = recorder_start();
    if (st != RECORDER_OK) {
        (void)audio_stop();
        ESP_LOGE(TAG, "recorder_start: %d", (int)st);
        return;
    }
    ESP_LOGI(TAG, "recording %s", recorder_last_path());
}

static int newest_recording(char *out, size_t n)
{
    char dirpath[256];
    DIR *d;
    struct dirent *e;
    const char *best = NULL;
    char bestbuf[256];

    snprintf(dirpath, sizeof(dirpath), "%s/%s", storage_sd_mount_point(), PSV_RECORDINGS_DIR);
    d = opendir(dirpath);
    if (!d) {
        return -1;
    }
    bestbuf[0] = '\0';
    while ((e = readdir(d)) != NULL) {
        size_t len = strlen(e->d_name);
        if (len < 5 || strcmp(e->d_name + len - 4, ".wav") != 0) {
            continue;
        }
        if (bestbuf[0] == '\0' || strcmp(e->d_name, bestbuf) > 0) {
            snprintf(bestbuf, sizeof(bestbuf), "%s", e->d_name);
            best = bestbuf;
        }
    }
    closedir(d);
    if (!best) {
        return -1;
    }
    snprintf(out, n, "%s/%s", PSV_RECORDINGS_DIR, best);
    return 0;
}

static void play_last(void)
{
    char path[PSV_MAX_PATH];
    RecorderStatus st;

    if (recorder_state() == RECORDER_PLAYING) {
        (void)recorder_play_stop();
        (void)audio_stop();
        return;
    }
    if (audio_start_play() != ESP_OK) {
        ESP_LOGE(TAG, "audio play start failed");
        return;
    }
    st = recorder_play_last();
    if (st != RECORDER_OK && newest_recording(path, sizeof(path)) == 0) {
        st = recorder_play(path);
    }
    if (st != RECORDER_OK) {
        (void)audio_stop();
        ESP_LOGE(TAG, "play last: %d", (int)st);
        return;
    }
    ESP_LOGI(TAG, "playing %s", recorder_last_path());
}

void app_main(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    }

    ESP_LOGI(TAG, "pixel-snap-voice on %s, %u Hz 16-bit mono", PSV_BOARD_NAME, PSV_SAMPLE_RATE_HZ);

    ESP_ERROR_CHECK(power_init());
    ESP_ERROR_CHECK(led_init());
    ESP_ERROR_CHECK(button_init());

    err = storage_sd_mount();
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "SD not mounted — recording will fail until a card is present");
    } else {
        (void)clock_try_set_from_volume();
    }

    err = audio_init();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "audio_init failed: %s", esp_err_to_name(err));
        led_set(PSV_LED_ERROR);
    }

    (void)usb_msc_init();
    recorder_init();

    int usb_was = 0;
    for (;;) {
        int usb = usb_msc_host_present();
        if (usb && !usb_was) {
            (void)audio_stop();
            led_set(PSV_LED_CHARGE);
        } else if (!usb && usb_was) {
            (void)clock_try_set_from_volume();
        }
        usb_was = usb;

        psv_btn_event_t ev = button_poll();
        if (!usb) {
            if (ev == PSV_BTN_SHORT) {
                toggle_record();
            } else if (ev == PSV_BTN_DOUBLE) {
                play_last();
            } else if (ev == PSV_BTN_LONG) {
                (void)recorder_stop();
                (void)recorder_play_stop();
                (void)audio_stop();
                power_deep_sleep();
            }
        }

        if (recorder_state() == RECORDER_RECORDING) {
            int n = audio_read(s_pcm, sizeof(s_pcm));
            if (n > 0) {
                RecorderStatus st = recorder_write(s_pcm, (size_t)n);
                if (st != RECORDER_OK) {
                    (void)audio_stop();
                    ESP_LOGE(TAG, "write failed: %d", (int)st);
                }
            }
        } else if (recorder_state() == RECORDER_PLAYING) {
            size_t got = 0;
            if (recorder_play_read(s_pcm, sizeof(s_pcm), &got) != RECORDER_OK) {
                (void)audio_stop();
            } else if (got > 0) {
                (void)audio_write(s_pcm, got);
            } else {
                (void)audio_stop();
            }
        }

        led_from_state();
        led_tick();
        vTaskDelay(pdMS_TO_TICKS(5));
    }
}
