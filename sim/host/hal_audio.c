#include "host_hal.h"

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

static int16_t *g_dac;
static size_t g_dac_cap;
static size_t g_dac_len;

void host_dac_reset(size_t cap_samples)
{
    free(g_dac);
    g_dac = NULL;
    g_dac_cap = 0;
    g_dac_len = 0;
    if (cap_samples == 0) {
        return;
    }
    g_dac = (int16_t *)calloc(cap_samples, sizeof(int16_t));
    if (g_dac) {
        g_dac_cap = cap_samples;
    }
}

int host_dac_write(const void *pcm, size_t nbytes)
{
    size_t n;
    if (!pcm || nbytes == 0) {
        return 0;
    }
    if (!g_dac) {
        return -1;
    }
    n = nbytes / sizeof(int16_t);
    if (g_dac_len + n > g_dac_cap) {
        return -1;
    }
    memcpy(g_dac + g_dac_len, pcm, n * sizeof(int16_t));
    g_dac_len += n;
    return 0;
}

size_t host_dac_len(void)
{
    return g_dac_len;
}

const int16_t *host_dac_samples(void)
{
    return g_dac;
}
