#include "clock.h"

#include <stdio.h>

void clock_format_stamp(const ClockCivil *t, char *buf, size_t buflen)
{
    snprintf(buf, buflen, "%04d%02d%02d-%02d%02d%02d", t->year, t->month, t->day,
             t->hour, t->minute, t->second);
}
