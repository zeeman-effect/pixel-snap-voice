#include "clock.h"

static ClockCivil g_now = {
    .year = 2026,
    .month = 8,
    .day = 28,
    .hour = 13,
    .minute = 17,
    .second = 0,
};

void clock_now(ClockCivil *out)
{
    *out = g_now;
}

void host_clock_set(int year, int month, int day, int hour, int minute, int second)
{
    g_now.year = year;
    g_now.month = month;
    g_now.day = day;
    g_now.hour = hour;
    g_now.minute = minute;
    g_now.second = second;
}

void host_clock_tick_seconds(int seconds)
{
    g_now.second += seconds;
    while (g_now.second >= 60) {
        g_now.second -= 60;
        g_now.minute += 1;
    }
    while (g_now.minute >= 60) {
        g_now.minute -= 60;
        g_now.hour += 1;
    }
}
