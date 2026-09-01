#include "led.h"

#include "board.h"
#include "driver/gpio.h"
#include "esp_timer.h"
#include "power.h"

static psv_led_mode_t s_mode;
static int s_level;

esp_err_t led_init(void)
{
    if (PSV_LED_GPIO == GPIO_NUM_NC) {
        return ESP_OK;
    }
    gpio_config_t io = {
        .pin_bit_mask = 1ULL << PSV_LED_GPIO,
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config(&io);
    gpio_set_level(PSV_LED_GPIO, PSV_LED_ACTIVE_LOW ? 1 : 0);
    return ESP_OK;
}

void led_set(psv_led_mode_t mode)
{
    s_mode = mode;
}

void led_tick(void)
{
    int on = 0;
    int64_t ms = esp_timer_get_time() / 1000;
    if (power_charging() && s_mode != PSV_LED_ERROR && s_mode != PSV_LED_RECORD) {
        s_mode = PSV_LED_CHARGE;
    }
    switch (s_mode) {
    case PSV_LED_RECORD:
        on = 1;
        break;
    case PSV_LED_PLAY:
        on = (ms / 200) % 2;
        break;
    case PSV_LED_CHARGE:
        on = (ms / 500) % 2;
        break;
    case PSV_LED_ERROR:
        on = (ms / 80) % 2;
        break;
    default:
        on = 0;
        break;
    }
    if (PSV_LED_GPIO == GPIO_NUM_NC) {
        return;
    }
    s_level = on;
    gpio_set_level(PSV_LED_GPIO, PSV_LED_ACTIVE_LOW ? !on : on);
}
