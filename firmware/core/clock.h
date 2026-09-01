#pragma once

#include <stddef.h>
#include <stdint.h>

typedef struct {
    int year;  /* 2000–2099 */
    int month; /* 1–12 */
    int day;
    int hour;
    int minute;
    int second;
} ClockCivil;

void clock_now(ClockCivil *out);
void clock_format_stamp(const ClockCivil *t, char *buf, size_t buflen);
