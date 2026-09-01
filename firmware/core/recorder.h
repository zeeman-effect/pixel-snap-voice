#pragma once

#include <stddef.h>
#include <stdint.h>

typedef enum {
    RECORDER_IDLE = 0,
    RECORDER_RECORDING,
    RECORDER_PLAYING,
    RECORDER_USB_MSC,
    RECORDER_ERROR
} RecorderState;

typedef enum {
    RECORDER_OK = 0,
    RECORDER_ERR = -1,
    RECORDER_ERR_BUSY = -2,
    RECORDER_ERR_FULL = -3,
    RECORDER_ERR_USB = -4
} RecorderStatus;

void recorder_init(void);
RecorderState recorder_state(void);
const char *recorder_last_path(void);
uint32_t recorder_data_bytes(void);

/* Start a new file recordings/YYYYMMDD-HHMMSS.wav */
RecorderStatus recorder_start(void);
RecorderStatus recorder_write(const void *pcm, size_t nbytes);
RecorderStatus recorder_stop(void);

/* Play a 48 kHz 16-bit mono WAV. USB attach aborts playback. */
RecorderStatus recorder_play(const char *path);
RecorderStatus recorder_play_last(void);
RecorderStatus recorder_play_read(void *pcm, size_t nbytes, size_t *got);
RecorderStatus recorder_play_stop(void);

/* USB attach: stop record/play and enter MSC (no new recordings). */
void recorder_on_usb_attach(void);
void recorder_on_usb_detach(void);
