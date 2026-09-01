#pragma once

#include <stddef.h>
#include <stdint.h>

void host_clock_set(int year, int month, int day, int hour, int minute, int second);
void host_clock_tick_seconds(int seconds);
void host_storage_set_root(const char *root);
void host_storage_set_quota(int64_t bytes);
void host_storage_reset_quota(void);

void host_dac_reset(size_t cap_samples);
int host_dac_write(const void *pcm, size_t nbytes);
size_t host_dac_len(void);
const int16_t *host_dac_samples(void);
