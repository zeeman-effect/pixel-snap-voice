#pragma once

#include <stddef.h>
#include <stdint.h>

#include "config.h"

/* Canonical 44-byte PCM WAV header (little-endian). */

typedef struct {
    uint8_t bytes[PSV_WAV_HEADER_BYTES];
} WavHeader;

void wav_header_init(WavHeader *hdr, uint32_t data_bytes);

/* Returns 0 if hdr is 48 kHz / 16-bit / mono PCM WAV. */
int wav_header_validate(const WavHeader *hdr, uint32_t *data_bytes_out);
