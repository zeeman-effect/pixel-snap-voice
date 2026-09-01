#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <direct.h>
#define MKDIR(p) _mkdir(p)
#else
#include <sys/stat.h>
#define MKDIR(p) mkdir((p), 0755)
#endif

#include "clock.h"
#include "config.h"
#include "host_hal.h"
#include "recorder.h"
#include "wav.h"

static int g_fail;

static void expect(int cond, const char *msg)
{
    if (!cond) {
        fprintf(stderr, "FAIL: %s\n", msg);
        g_fail = 1;
    }
}

static int read_header(const char *root, const char *rel, WavHeader *hdr, uint32_t *file_size)
{
    char path[768];
    FILE *fp;
    long sz;
    size_t n;

    snprintf(path, sizeof(path), "%s/%s", root, rel);
    fp = fopen(path, "rb");
    if (!fp) {
        return -1;
    }
    if (fseek(fp, 0, SEEK_END) != 0) {
        fclose(fp);
        return -1;
    }
    sz = ftell(fp);
    if (sz < (long)PSV_WAV_HEADER_BYTES) {
        fclose(fp);
        return -1;
    }
    rewind(fp);
    n = fread(hdr->bytes, 1, PSV_WAV_HEADER_BYTES, fp);
    fclose(fp);
    if (n != PSV_WAV_HEADER_BYTES) {
        return -1;
    }
    if (file_size) {
        *file_size = (uint32_t)sz;
    }
    return 0;
}

static void test_wav_header_roundtrip(void)
{
    WavHeader a, b;
    uint32_t data = 32000;
    uint32_t out = 0;
    wav_header_init(&a, data);
    expect(wav_header_validate(&a, &out) == 0, "header validates");
    expect(out == data, "data size roundtrip");
    memcpy(b.bytes, a.bytes, PSV_WAV_HEADER_BYTES);
    b.bytes[20] = 3; /* not PCM */
    expect(wav_header_validate(&b, NULL) != 0, "rejects non-PCM");
    /* Sample rate field is 48 kHz, not 16 kHz. */
    {
        uint32_t sr = (uint32_t)a.bytes[24] | ((uint32_t)a.bytes[25] << 8) |
                      ((uint32_t)a.bytes[26] << 16) | ((uint32_t)a.bytes[27] << 24);
        expect(sr == PSV_SAMPLE_RATE_HZ, "header sample rate is 48 kHz");
    }
}

static void test_start_stop_filename_and_sizes(const char *root)
{
    int16_t pcm[160];
    WavHeader hdr;
    uint32_t data = 0;
    uint32_t fsz = 0;
    memset(pcm, 0, sizeof(pcm));

    host_clock_set(2026, 8, 28, 13, 17, 42);
    recorder_init();
    expect(recorder_start() == RECORDER_OK, "start");
    expect(strcmp(recorder_last_path(), "recordings/20260828-131742.wav") == 0, "filename stamp");
    expect(recorder_write(pcm, sizeof(pcm)) == RECORDER_OK, "write");
    expect(recorder_stop() == RECORDER_OK, "stop");
    expect(recorder_state() == RECORDER_IDLE, "idle after stop");
    expect(recorder_data_bytes() == (uint32_t)sizeof(pcm), "data byte count");

    expect(read_header(root, recorder_last_path(), &hdr, &fsz) == 0, "open wav");
    expect(wav_header_validate(&hdr, &data) == 0, "file header valid");
    expect(data == (uint32_t)sizeof(pcm), "header data size");
    expect(fsz == PSV_WAV_HEADER_BYTES + sizeof(pcm), "file size = 44 + pcm");
}

static void test_disk_full(const char *root)
{
    int16_t pcm[256];
    (void)root;
    memset(pcm, 1, sizeof(pcm));
    host_storage_reset_quota();
    host_storage_set_quota(PSV_WAV_HEADER_BYTES + 100);
    recorder_init();
    expect(recorder_start() == RECORDER_OK, "start under quota");
    expect(recorder_write(pcm, sizeof(pcm)) == RECORDER_ERR_FULL, "write hits full");
    expect(recorder_state() == RECORDER_ERROR, "error state");
    host_storage_reset_quota();
}

static void test_usb_stops_recording(void)
{
    int16_t pcm[32];
    memset(pcm, 0, sizeof(pcm));
    recorder_init();
    expect(recorder_start() == RECORDER_OK, "start before usb");
    expect(recorder_write(pcm, sizeof(pcm)) == RECORDER_OK, "write before usb");
    recorder_on_usb_attach();
    expect(recorder_state() == RECORDER_USB_MSC, "usb msc");
    expect(recorder_start() == RECORDER_ERR_USB, "no record on usb");
    expect(recorder_play("recordings/x.wav") == RECORDER_ERR_USB, "no play on usb");
    recorder_on_usb_detach();
    expect(recorder_state() == RECORDER_IDLE, "idle after unplug");
}

static void test_playback_into_dummy_dac(const char *root)
{
    int16_t pcm[240];
    int16_t chunk[64];
    size_t i;
    size_t got = 0;
    char path[PSV_MAX_PATH];
    (void)root;

    for (i = 0; i < (sizeof(pcm) / sizeof(pcm[0])); i++) {
        pcm[i] = (int16_t)(i * 17 - 2000);
    }

    host_clock_set(2026, 8, 28, 14, 0, 1);
    recorder_init();
    expect(recorder_start() == RECORDER_OK, "record fixture start");
    expect(recorder_write(pcm, sizeof(pcm)) == RECORDER_OK, "record fixture pcm");
    expect(recorder_stop() == RECORDER_OK, "record fixture stop");
    snprintf(path, sizeof(path), "%s", recorder_last_path());

    host_dac_reset(sizeof(pcm) / sizeof(pcm[0]));
    expect(recorder_play(path) == RECORDER_OK, "play open");
    expect(recorder_state() == RECORDER_PLAYING, "playing");
    expect(recorder_start() == RECORDER_ERR_BUSY, "no record while playing");

    while (recorder_state() == RECORDER_PLAYING) {
        got = 0;
        expect(recorder_play_read(chunk, sizeof(chunk), &got) == RECORDER_OK, "play read");
        if (got > 0) {
            expect(host_dac_write(chunk, got) == 0, "dummy dac write");
        }
    }
    expect(recorder_state() == RECORDER_IDLE, "idle after eof");
    expect(host_dac_len() == sizeof(pcm) / sizeof(pcm[0]), "dac sample count");
    expect(memcmp(host_dac_samples(), pcm, sizeof(pcm)) == 0, "dac matches recorded pcm");

    expect(recorder_play_last() == RECORDER_OK, "play last");
    expect(recorder_play_stop() == RECORDER_OK, "play stop");
    expect(recorder_state() == RECORDER_IDLE, "idle after play stop");
    host_dac_reset(0);
}

static void test_usb_stops_playback(const char *root)
{
    int16_t pcm[64];
    int16_t chunk[16];
    size_t got = 0;
    char path[PSV_MAX_PATH];
    (void)root;
    memset(pcm, 3, sizeof(pcm));

    host_clock_set(2026, 8, 28, 14, 0, 2);
    recorder_init();
    expect(recorder_start() == RECORDER_OK, "rec for play-usb");
    expect(recorder_write(pcm, sizeof(pcm)) == RECORDER_OK, "write for play-usb");
    expect(recorder_stop() == RECORDER_OK, "stop for play-usb");
    snprintf(path, sizeof(path), "%s", recorder_last_path());

    expect(recorder_play(path) == RECORDER_OK, "play before usb");
    expect(recorder_play_read(chunk, sizeof(chunk), &got) == RECORDER_OK, "read before usb");
    expect(got == sizeof(chunk), "got a chunk");
    recorder_on_usb_attach();
    expect(recorder_state() == RECORDER_USB_MSC, "usb aborts play");
    expect(recorder_play_read(chunk, sizeof(chunk), &got) == RECORDER_ERR, "no read after usb");
    recorder_on_usb_detach();
    expect(recorder_state() == RECORDER_IDLE, "idle after usb play abort");
}

int main(void)
{
    const char *root = "sim_out";
    MKDIR(root);
    host_storage_set_root(root);
    host_storage_reset_quota();

    test_wav_header_roundtrip();
    test_start_stop_filename_and_sizes(root);
    test_disk_full(root);
    test_usb_stops_recording();
    test_playback_into_dummy_dac(root);
    test_usb_stops_playback(root);

    if (g_fail) {
        fprintf(stderr, "recorder_test: FAILED\n");
        return 1;
    }
    printf("recorder_test: ok\n");
    return 0;
}
