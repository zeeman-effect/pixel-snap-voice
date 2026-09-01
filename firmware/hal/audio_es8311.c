#include "audio.h"

#include <string.h>

#include "board.h"
#include "config.h"
#include "driver/i2c_master.h"
#include "driver/i2s_std.h"
#include "esp_check.h"
#include "esp_codec_dev.h"
#include "esp_codec_dev_defaults.h"
#include "esp_log.h"
#include "es8311_codec.h"

#if PSV_HAS_ES7210
#include "es7210_adc.h"
#endif

static const char *TAG = "psv.audio";

static i2c_master_bus_handle_t s_i2c;
static i2s_chan_handle_t s_tx;
static i2s_chan_handle_t s_rx;
static esp_codec_dev_handle_t s_play;
static esp_codec_dev_handle_t s_rec;
static int s_open_play;
static int s_open_rec;

static esp_err_t init_i2c(void)
{
    i2c_master_bus_config_t cfg = {
        .i2c_port = PSV_I2C_PORT,
        .sda_io_num = PSV_I2C_SDA,
        .scl_io_num = PSV_I2C_SCL,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags = {.enable_internal_pullup = true},
    };
    return i2c_new_master_bus(&cfg, &s_i2c);
}

static esp_err_t init_i2s(void)
{
    i2s_chan_config_t chan = I2S_CHANNEL_DEFAULT_CONFIG(
        I2S_NUM_0, PSV_I2S_SLAVE ? I2S_ROLE_SLAVE : I2S_ROLE_MASTER);
    chan.auto_clear = true;
    ESP_ERROR_CHECK(i2s_new_channel(&chan, &s_tx, &s_rx));

    i2s_std_config_t std = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(PSV_SAMPLE_RATE_HZ),
        .slot_cfg = I2S_STD_PHILIP_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT,
                                                        I2S_SLOT_MODE_MONO),
        .gpio_cfg =
            {
                .mclk = PSV_I2S_MCLK,
                .bclk = PSV_I2S_BCLK,
                .ws = PSV_I2S_WS,
                .dout = PSV_I2S_DOUT,
                .din = PSV_I2S_DIN,
                .invert_flags = {0},
            },
    };
    ESP_RETURN_ON_ERROR(i2s_channel_init_std_mode(s_tx, &std), TAG, "tx std");
    ESP_RETURN_ON_ERROR(i2s_channel_init_std_mode(s_rx, &std), TAG, "rx std");
    return ESP_OK;
}

static const audio_codec_data_if_t *make_i2s_data(void)
{
    audio_codec_i2s_cfg_t i2s_cfg = {
        .port = I2S_NUM_0,
        .rx_handle = s_rx,
        .tx_handle = s_tx,
    };
    return audio_codec_new_i2s_data(&i2s_cfg);
}

static const audio_codec_ctrl_if_t *make_i2c_ctrl(uint8_t addr)
{
    audio_codec_i2c_cfg_t i2c_cfg = {
        .port = PSV_I2C_PORT,
        .addr = addr,
        .bus_handle = s_i2c,
    };
    return audio_codec_new_i2c_ctrl(&i2c_cfg);
}

static esp_err_t init_es8311(const audio_codec_data_if_t *data_if)
{
    const audio_codec_gpio_if_t *gpio_if = audio_codec_new_gpio();
    const audio_codec_ctrl_if_t *ctrl = make_i2c_ctrl(PSV_CODEC_I2C_ADDR);
    if (!gpio_if || !ctrl) {
        return ESP_FAIL;
    }

    es8311_codec_cfg_t es = {
        .ctrl_if = ctrl,
        .gpio_if = gpio_if,
        .codec_mode = PSV_HAS_ES7210 ? ESP_CODEC_DEV_WORK_MODE_DAC
                                     : ESP_CODEC_DEV_WORK_MODE_BOTH,
        .pa_pin = PSV_PA_EN,
        .pa_reverted = false,
        .master_mode = PSV_CODEC_MASTER ? true : false,
        .use_mclk = true,
        .hw_gain =
            {
                .pa_voltage = 5.0,
                .codec_dac_voltage = 3.3,
            },
    };
    const audio_codec_if_t *codec = es8311_codec_new(&es);
    if (!codec) {
        return ESP_FAIL;
    }

    esp_codec_dev_cfg_t dev_cfg = {
        .dev_type = PSV_HAS_ES7210 ? ESP_CODEC_DEV_TYPE_OUT : ESP_CODEC_DEV_TYPE_IN_OUT,
        .codec_if = codec,
        .data_if = data_if,
    };
    s_play = esp_codec_dev_new(&dev_cfg);
    if (!PSV_HAS_ES7210) {
        s_rec = s_play;
    }
    return s_play ? ESP_OK : ESP_FAIL;
}

#if PSV_HAS_ES7210
static esp_err_t init_es7210(const audio_codec_data_if_t *data_if)
{
    const audio_codec_ctrl_if_t *ctrl = make_i2c_ctrl(PSV_ADC_I2C_ADDR);
    if (!ctrl) {
        return ESP_FAIL;
    }
    es7210_codec_cfg_t adc = {
        .ctrl_if = ctrl,
        .master_mode = false,
        .mic_selected = ES7210_SEL_MIC1 | ES7210_SEL_MIC2,
    };
    const audio_codec_if_t *codec = es7210_codec_new(&adc);
    if (!codec) {
        return ESP_FAIL;
    }
    esp_codec_dev_cfg_t dev_cfg = {
        .dev_type = ESP_CODEC_DEV_TYPE_IN,
        .codec_if = codec,
        .data_if = data_if,
    };
    s_rec = esp_codec_dev_new(&dev_cfg);
    return s_rec ? ESP_OK : ESP_FAIL;
}
#endif

esp_err_t audio_init(void)
{
    const audio_codec_data_if_t *data_if;
    ESP_RETURN_ON_ERROR(init_i2c(), TAG, "i2c");
    ESP_RETURN_ON_ERROR(init_i2s(), TAG, "i2s");
    data_if = make_i2s_data();
    if (!data_if) {
        return ESP_FAIL;
    }
    ESP_RETURN_ON_ERROR(init_es8311(data_if), TAG, "es8311");
#if PSV_HAS_ES7210
    ESP_RETURN_ON_ERROR(init_es7210(data_if), TAG, "es7210");
#endif
    ESP_LOGI(TAG, "audio ready on %s (codec master=%d)", PSV_BOARD_NAME, PSV_CODEC_MASTER);
    return ESP_OK;
}

static esp_err_t open_dev(esp_codec_dev_handle_t dev, int *flag)
{
    esp_codec_dev_sample_info_t fs = {
        .bits_per_sample = PSV_BITS_PER_SAMPLE,
        .channel = PSV_NUM_CHANNELS,
        .channel_mask = 0,
        .sample_rate = PSV_SAMPLE_RATE_HZ,
        .mclk_multiple = 256,
    };
    if (*flag) {
        return ESP_OK;
    }
    esp_err_t err = esp_codec_dev_open(dev, &fs);
    if (err == ESP_OK) {
        *flag = 1;
    }
    return err;
}

esp_err_t audio_start_record(void)
{
    if (!s_rec) {
        return ESP_ERR_INVALID_STATE;
    }
    return open_dev(s_rec, &s_open_rec);
}

esp_err_t audio_start_play(void)
{
    if (!s_play) {
        return ESP_ERR_INVALID_STATE;
    }
    return open_dev(s_play, &s_open_play);
}

esp_err_t audio_stop(void)
{
    if (s_play == s_rec) {
        if ((s_open_rec || s_open_play) && s_play) {
            (void)esp_codec_dev_close(s_play);
        }
        s_open_rec = 0;
        s_open_play = 0;
        return ESP_OK;
    }
    if (s_open_rec && s_rec) {
        (void)esp_codec_dev_close(s_rec);
        s_open_rec = 0;
    }
    if (s_open_play && s_play) {
        (void)esp_codec_dev_close(s_play);
        s_open_play = 0;
    }
    return ESP_OK;
}

int audio_read(void *pcm, size_t nbytes)
{
    if (!s_rec || !s_open_rec) {
        return -1;
    }
    if (esp_codec_dev_read(s_rec, pcm, (int)nbytes) != ESP_OK) {
        return -1;
    }
    return (int)nbytes;
}

int audio_write(const void *pcm, size_t nbytes)
{
    if (!s_play || !s_open_play) {
        return -1;
    }
    if (esp_codec_dev_write(s_play, (void *)pcm, (int)nbytes) != ESP_OK) {
        return -1;
    }
    return (int)nbytes;
}
