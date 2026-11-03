#include "download_mode.h"

#include "board.h"
#include "button.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "led.h"
#include "sdkconfig.h"

#if CONFIG_PSV_BOOT_DOWNLOAD_HOLD
#include "soc/rtc_cntl_reg.h"
#include "soc/soc.h"
#include "soc/usb_serial_jtag_reg.h"
#endif

static const char *TAG = "psv.dl";

#define PSV_DOWNLOAD_HOLD_MS 5000

#if CONFIG_PSV_BOOT_DOWNLOAD_HOLD && !PSV_BTN_ADC

/*
 * A computer on the other end of the cable sends a USB start-of-frame every
 * millisecond, and the S3's USB-Serial/JTAG block counts them. TinyUSB has not
 * taken the port yet at this point, so a moving counter means a host is there.
 * This board has no VBUS-sense GPIO, and download mode on battery power with
 * nothing to talk to would just sit there until a TP_EN reset.
 */
static int usb_host_attached(void)
{
    uint32_t first = REG_GET_FIELD(USB_SERIAL_JTAG_FRAM_NUM_REG, USB_SERIAL_JTAG_SOF_FRAME_INDEX);
    for (int i = 0; i < 50; i++) {
        vTaskDelay(pdMS_TO_TICKS(2));
        if (REG_GET_FIELD(USB_SERIAL_JTAG_FRAM_NUM_REG, USB_SERIAL_JTAG_SOF_FRAME_INDEX) != first) {
            return 1;
        }
    }
    return 0;
}

static void wait_release(void)
{
    while (button_held()) {
        led_tick();
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

void download_mode_check(void)
{
    if (!button_held()) {
        return;
    }

    /*
     * A deep-sleep wake also starts with the button down, so only a long,
     * unbroken hold counts. Letting go early is an ordinary boot.
     */
    int64_t start = esp_timer_get_time();
    while (button_held()) {
        if (esp_timer_get_time() - start >= PSV_DOWNLOAD_HOLD_MS * 1000LL) {
            break;
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
    if (!button_held()) {
        return;
    }

    if (!usb_host_attached()) {
        ESP_LOGW(TAG, "download hold seen, but no USB host on the cable; booting normally");
        led_set(PSV_LED_ERROR);
        wait_release();
        led_set(PSV_LED_OFF);
        led_tick();
        return;
    }

    ESP_LOGW(TAG, "download hold: restarting into ROM download mode (USB-Serial/JTAG)");
    led_set(PSV_LED_RECORD); /* solid on: release the button, then flash */
    led_tick();
    wait_release();

    /* The ROM reads this on the next boot, enters download mode and clears it. */
    REG_WRITE(RTC_CNTL_OPTION1_REG, RTC_CNTL_FORCE_DOWNLOAD_BOOT);
    esp_restart();
}

#else

void download_mode_check(void)
{
    (void)TAG;
}

#endif
