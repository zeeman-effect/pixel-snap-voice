#pragma once

#include <stdint.h>

#define PSV_SAMPLE_RATE_HZ 48000u
#define PSV_NUM_CHANNELS 1u
#define PSV_BITS_PER_SAMPLE 16u
#define PSV_BYTES_PER_SAMPLE ((PSV_BITS_PER_SAMPLE / 8u) * PSV_NUM_CHANNELS)
#define PSV_RECORDINGS_DIR "recordings"
#define PSV_MAX_PATH 256
#define PSV_WAV_HEADER_BYTES 44
