#pragma once

/*
 * Reflash without opening the case.
 *
 * Hold the record button through boot for PSV_DOWNLOAD_HOLD_MS with the
 * magnetic cable in a computer, and the S3 restarts into its ROM download
 * mode: the built-in USB-Serial/JTAG port comes back and `idf.py flash` works
 * as on a blank chip. Call after led_init() and button_init(), before the SD
 * card and TinyUSB start. Returns normally when the gesture is not made.
 */
void download_mode_check(void);
