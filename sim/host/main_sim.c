#define _USE_MATH_DEFINES

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "config.h"
#include "recorder.h"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

static void fill_sine(int16_t *dst, size_t n, double freq_hz, double amp)
{
    size_t i;
    for (i = 0; i < n; i++) {
        double s = sin(2.0 * M_PI * freq_hz * (double)i / (double)PSV_SAMPLE_RATE_HZ);
        dst[i] = (int16_t)(s * amp);
    }
}

int main(void)
{
    int16_t *pcm;
    const size_t n = (size_t)PSV_SAMPLE_RATE_HZ; /* 1 second */
    RecorderStatus st;

    pcm = (int16_t *)malloc(n * sizeof(int16_t));
    if (!pcm) {
        fprintf(stderr, "alloc failed\n");
        return 1;
    }
    fill_sine(pcm, n, 440.0, 8000.0);

    recorder_init();
    st = recorder_start();
    if (st != RECORDER_OK) {
        fprintf(stderr, "start failed: %d\n", (int)st);
        free(pcm);
        return 1;
    }
    st = recorder_write(pcm, n * sizeof(int16_t));
    if (st != RECORDER_OK) {
        fprintf(stderr, "write failed: %d\n", (int)st);
        free(pcm);
        return 1;
    }
    st = recorder_stop();
    if (st != RECORDER_OK) {
        fprintf(stderr, "stop failed: %d\n", (int)st);
        free(pcm);
        return 1;
    }

    printf("wrote %s (%u data bytes, %u Hz 16-bit mono PCM)\n", recorder_last_path(),
           recorder_data_bytes(), PSV_SAMPLE_RATE_HZ);
    free(pcm);
    return 0;
}
