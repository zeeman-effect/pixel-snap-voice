#include "wav.h"

#include <string.h>

static void wr_le32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v);
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}

static void wr_le16(uint8_t *p, uint16_t v)
{
    p[0] = (uint8_t)(v);
    p[1] = (uint8_t)(v >> 8);
}

static uint32_t rd_le32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

static uint16_t rd_le16(const uint8_t *p)
{
    return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}

void wav_header_init(WavHeader *hdr, uint32_t data_bytes)
{
    uint8_t *b = hdr->bytes;
    const uint32_t byte_rate =
        PSV_SAMPLE_RATE_HZ * PSV_NUM_CHANNELS * (PSV_BITS_PER_SAMPLE / 8u);
    const uint16_t block_align = (uint16_t)(PSV_NUM_CHANNELS * (PSV_BITS_PER_SAMPLE / 8u));

    memset(b, 0, PSV_WAV_HEADER_BYTES);
    memcpy(b + 0, "RIFF", 4);
    wr_le32(b + 4, 36u + data_bytes);
    memcpy(b + 8, "WAVE", 4);
    memcpy(b + 12, "fmt ", 4);
    wr_le32(b + 16, 16u);
    wr_le16(b + 20, 1u); /* PCM */
    wr_le16(b + 22, (uint16_t)PSV_NUM_CHANNELS);
    wr_le32(b + 24, PSV_SAMPLE_RATE_HZ);
    wr_le32(b + 28, byte_rate);
    wr_le16(b + 32, block_align);
    wr_le16(b + 34, (uint16_t)PSV_BITS_PER_SAMPLE);
    memcpy(b + 36, "data", 4);
    wr_le32(b + 40, data_bytes);
}

int wav_header_validate(const WavHeader *hdr, uint32_t *data_bytes_out)
{
    const uint8_t *b = hdr->bytes;
    if (memcmp(b + 0, "RIFF", 4) != 0) {
        return -1;
    }
    if (memcmp(b + 8, "WAVE", 4) != 0) {
        return -1;
    }
    if (memcmp(b + 12, "fmt ", 4) != 0) {
        return -1;
    }
    if (rd_le32(b + 16) != 16u) {
        return -1;
    }
    if (rd_le16(b + 20) != 1u) {
        return -1;
    }
    if (rd_le16(b + 22) != PSV_NUM_CHANNELS) {
        return -1;
    }
    if (rd_le32(b + 24) != PSV_SAMPLE_RATE_HZ) {
        return -1;
    }
    if (rd_le16(b + 34) != PSV_BITS_PER_SAMPLE) {
        return -1;
    }
    if (memcmp(b + 36, "data", 4) != 0) {
        return -1;
    }
    if (data_bytes_out) {
        *data_bytes_out = rd_le32(b + 40);
    }
    return 0;
}
