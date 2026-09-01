#include "recorder.h"

#include <stdio.h>
#include <string.h>

#include "clock.h"
#include "config.h"
#include "storage.h"
#include "wav.h"

static RecorderState g_state = RECORDER_IDLE;
static StorageFile *g_file;
static uint32_t g_data_bytes;
static uint32_t g_play_remain;
static char g_path[PSV_MAX_PATH];

void recorder_init(void)
{
    if (g_file) {
        storage_close(g_file);
        g_file = NULL;
    }
    g_state = RECORDER_IDLE;
    g_data_bytes = 0;
    g_play_remain = 0;
    g_path[0] = '\0';
}

RecorderState recorder_state(void)
{
    return g_state;
}

const char *recorder_last_path(void)
{
    return g_path;
}

uint32_t recorder_data_bytes(void)
{
    return g_data_bytes;
}

static RecorderStatus finalize_header(void)
{
    WavHeader hdr;
    if (!g_file) {
        return RECORDER_OK;
    }
    wav_header_init(&hdr, g_data_bytes);
    if (storage_seek(g_file, 0) != 0) {
        return RECORDER_ERR;
    }
    if (storage_write(g_file, hdr.bytes, PSV_WAV_HEADER_BYTES) != 0) {
        return RECORDER_ERR;
    }
    return RECORDER_OK;
}

static void close_file(void)
{
    if (g_file) {
        storage_close(g_file);
        g_file = NULL;
    }
    g_play_remain = 0;
}

RecorderStatus recorder_start(void)
{
    ClockCivil t;
    char stamp[32];
    WavHeader hdr;
    int64_t free_b;

    if (g_state == RECORDER_USB_MSC) {
        return RECORDER_ERR_USB;
    }
    if (g_state == RECORDER_RECORDING || g_state == RECORDER_PLAYING) {
        return RECORDER_ERR_BUSY;
    }

    if (storage_mkdir(PSV_RECORDINGS_DIR) != 0) {
        g_state = RECORDER_ERROR;
        return RECORDER_ERR;
    }

    free_b = storage_free_bytes();
    if (free_b >= 0 && free_b < (int64_t)PSV_WAV_HEADER_BYTES) {
        g_state = RECORDER_ERROR;
        return RECORDER_ERR_FULL;
    }

    clock_now(&t);
    clock_format_stamp(&t, stamp, sizeof(stamp));
    snprintf(g_path, sizeof(g_path), "%s/%s.wav", PSV_RECORDINGS_DIR, stamp);

    if (storage_open_write(g_path, &g_file) != 0) {
        g_file = NULL;
        g_state = RECORDER_ERROR;
        return RECORDER_ERR;
    }

    g_data_bytes = 0;
    wav_header_init(&hdr, 0);
    if (storage_write(g_file, hdr.bytes, PSV_WAV_HEADER_BYTES) != 0) {
        close_file();
        g_state = RECORDER_ERROR;
        return RECORDER_ERR_FULL;
    }

    g_state = RECORDER_RECORDING;
    return RECORDER_OK;
}

RecorderStatus recorder_write(const void *pcm, size_t nbytes)
{
    int64_t free_b;
    if (g_state != RECORDER_RECORDING || !g_file) {
        return RECORDER_ERR;
    }
    if (nbytes == 0) {
        return RECORDER_OK;
    }
    free_b = storage_free_bytes();
    if (free_b >= 0 && (int64_t)nbytes > free_b) {
        (void)recorder_stop();
        g_state = RECORDER_ERROR;
        return RECORDER_ERR_FULL;
    }
    if (storage_write(g_file, pcm, nbytes) != 0) {
        (void)finalize_header();
        close_file();
        g_state = RECORDER_ERROR;
        return RECORDER_ERR_FULL;
    }
    g_data_bytes += (uint32_t)nbytes;
    return RECORDER_OK;
}

RecorderStatus recorder_stop(void)
{
    RecorderStatus st = RECORDER_OK;
    if (g_state != RECORDER_RECORDING && g_state != RECORDER_ERROR) {
        return RECORDER_OK;
    }
    if (g_file) {
        st = finalize_header();
        close_file();
    }
    if (g_state != RECORDER_ERROR) {
        g_state = RECORDER_IDLE;
    }
    return st;
}

RecorderStatus recorder_play(const char *path)
{
    WavHeader hdr;
    uint32_t data_bytes = 0;
    size_t got = 0;

    if (!path || path[0] == '\0') {
        return RECORDER_ERR;
    }
    if (g_state == RECORDER_USB_MSC) {
        return RECORDER_ERR_USB;
    }
    if (g_state == RECORDER_RECORDING || g_state == RECORDER_PLAYING) {
        return RECORDER_ERR_BUSY;
    }

    if (storage_open_read(path, &g_file) != 0) {
        g_file = NULL;
        g_state = RECORDER_ERROR;
        return RECORDER_ERR;
    }

    if (storage_read(g_file, hdr.bytes, PSV_WAV_HEADER_BYTES, &got) != 0 ||
        got != PSV_WAV_HEADER_BYTES || wav_header_validate(&hdr, &data_bytes) != 0) {
        close_file();
        g_state = RECORDER_ERROR;
        return RECORDER_ERR;
    }

    snprintf(g_path, sizeof(g_path), "%s", path);
    g_data_bytes = data_bytes;
    g_play_remain = data_bytes;
    g_state = RECORDER_PLAYING;
    return RECORDER_OK;
}

RecorderStatus recorder_play_last(void)
{
    char path[PSV_MAX_PATH];
    if (g_path[0] == '\0') {
        return RECORDER_ERR;
    }
    snprintf(path, sizeof(path), "%s", g_path);
    return recorder_play(path);
}

RecorderStatus recorder_play_read(void *pcm, size_t nbytes, size_t *got)
{
    size_t want;
    size_t n = 0;

    if (got) {
        *got = 0;
    }
    if (g_state != RECORDER_PLAYING || !g_file) {
        return RECORDER_ERR;
    }
    if (nbytes == 0 || g_play_remain == 0) {
        if (g_play_remain == 0) {
            (void)recorder_play_stop();
        }
        return RECORDER_OK;
    }

    want = nbytes;
    if (want > g_play_remain) {
        want = g_play_remain;
    }
    if (storage_read(g_file, pcm, want, &n) != 0) {
        close_file();
        g_state = RECORDER_ERROR;
        return RECORDER_ERR;
    }
    g_play_remain -= (uint32_t)n;
    if (got) {
        *got = n;
    }
    if (n == 0 || g_play_remain == 0) {
        (void)recorder_play_stop();
    }
    return RECORDER_OK;
}

RecorderStatus recorder_play_stop(void)
{
    if (g_state != RECORDER_PLAYING && g_state != RECORDER_ERROR) {
        return RECORDER_OK;
    }
    close_file();
    if (g_state != RECORDER_ERROR) {
        g_state = RECORDER_IDLE;
    }
    return RECORDER_OK;
}

void recorder_on_usb_attach(void)
{
    if (g_state == RECORDER_RECORDING) {
        (void)recorder_stop();
    } else if (g_state == RECORDER_PLAYING) {
        (void)recorder_play_stop();
    }
    g_state = RECORDER_USB_MSC;
}

void recorder_on_usb_detach(void)
{
    if (g_state == RECORDER_USB_MSC) {
        g_state = RECORDER_IDLE;
    }
}
