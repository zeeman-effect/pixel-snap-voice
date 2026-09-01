#include "button.h"

#include "board.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"

#if PSV_BTN_ADC
#include "esp_adc/adc_oneshot.h"
#endif

static const char *TAG = "psv.btn";

#define DEBOUNCE_US 30000
#define LONG_US 1500000
#define DOUBLE_US 400000

static int s_down;
static int64_t s_down_at;
static int64_t s_short_up_at;
static int s_waiting_double;

#if PSV_BTN_ADC
static adc_oneshot_unit_handle_t s_adc;
#endif

static int raw_pressed(void)
{
#if PSV_BTN_ADC
    int mv = 3300;
    if (s_adc) {
        (void)adc_oneshot_read(s_adc, PSV_BTN_ADC_CHANNEL, &mv);
        /* Korvo ladder: idle is ~3.3 V. Any key pulls it well below 2.8 V. */
        return mv < 2800;
    }
    return 0;
#else
    int level = gpio_get_level(PSV_BTN_GPIO);
    return PSV_BTN_ACTIVE_LOW ? (level == 0) : (level != 0);
#endif
}

esp_err_t button_init(void)
{
#if PSV_BTN_ADC
    adc_oneshot_unit_init_cfg_t unit = {.unit_id = ADC_UNIT_1};
    ESP_ERROR_CHECK(adc_oneshot_new_unit(&unit, &s_adc));
    adc_oneshot_chan_cfg_t ch = {
        .bitwidth = ADC_BITWIDTH_DEFAULT,
        .atten = ADC_ATTEN_DB_12,
    };
    ESP_ERROR_CHECK(adc_oneshot_config_channel(s_adc, PSV_BTN_ADC_CHANNEL, &ch));
#else
    gpio_config_t io = {
        .pin_bit_mask = 1ULL << PSV_BTN_GPIO,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = PSV_BTN_ACTIVE_LOW ? GPIO_PULLUP_ENABLE : GPIO_PULLUP_DISABLE,
        .pull_down_en = PSV_BTN_ACTIVE_LOW ? GPIO_PULLDOWN_DISABLE : GPIO_PULLDOWN_ENABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&io));
#endif
    ESP_LOGI(TAG, "button on GPIO %d (%s)", (int)PSV_BTN_GPIO, PSV_BTN_ADC ? "adc ladder" : "gpio");
    return ESP_OK;
}

psv_btn_event_t button_poll(void)
{
    int64_t now = esp_timer_get_time();
    int pressed = raw_pressed();

    if (pressed && !s_down) {
        s_down = 1;
        s_down_at = now;
        return PSV_BTN_NONE;
    }
    if (pressed && s_down) {
        if ((now - s_down_at) >= LONG_US) {
            s_down = 0;
            s_waiting_double = 0;
            return PSV_BTN_LONG;
        }
        return PSV_BTN_NONE;
    }
    if (!pressed && s_down) {
        int64_t held = now - s_down_at;
        s_down = 0;
        if (held < DEBOUNCE_US) {
            return PSV_BTN_NONE;
        }
        if (s_waiting_double && (now - s_short_up_at) < DOUBLE_US) {
            s_waiting_double = 0;
            return PSV_BTN_DOUBLE;
        }
        s_waiting_double = 1;
        s_short_up_at = now;
        return PSV_BTN_NONE;
    }
    if (s_waiting_double && (now - s_short_up_at) >= DOUBLE_US) {
        s_waiting_double = 0;
        return PSV_BTN_SHORT;
    }
    return PSV_BTN_NONE;
}
