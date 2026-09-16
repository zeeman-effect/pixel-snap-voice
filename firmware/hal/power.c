#include "power.h"

#include "board.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_sleep.h"

static const char *TAG = "psv.pwr";

esp_err_t power_init(void)
{
    if (PSV_CHG_STAT == GPIO_NUM_NC) {
        return ESP_OK;
    }
    gpio_config_t io = {
        .pin_bit_mask = 1ULL << PSV_CHG_STAT,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    return gpio_config(&io);
}

int power_charging(void)
{
    /* BQ24074 CHG is open-drain, low while charging. */
    if (PSV_CHG_STAT == GPIO_NUM_NC) {
        return 0;
    }
    return gpio_get_level(PSV_CHG_STAT) == 0;
}

void power_deep_sleep(void)
{
    ESP_LOGI(TAG, "deep sleep; wake on GPIO %d low", (int)PSV_WAKE_GPIO);
    if (PSV_WAKE_GPIO != GPIO_NUM_NC && !PSV_BTN_ADC) {
        esp_sleep_enable_ext0_wakeup(PSV_WAKE_GPIO, 0);
    } else {
        esp_sleep_enable_timer_wakeup(60ULL * 1000000ULL);
    }
    esp_deep_sleep_start();
}
