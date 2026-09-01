#pragma once

#include <stddef.h>
#include <stdint.h>

#include "esp_err.h"

esp_err_t audio_init(void);
esp_err_t audio_start_record(void);
esp_err_t audio_start_play(void);
esp_err_t audio_stop(void);
int audio_read(void *pcm, size_t nbytes);
int audio_write(const void *pcm, size_t nbytes);
