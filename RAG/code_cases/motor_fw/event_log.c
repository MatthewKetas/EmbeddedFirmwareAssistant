/* A small in-RAM event log, sent over telemetry with each status report. */
#include <stdio.h>

#include "hal.h"

#define LOG_ENTRIES   16

typedef struct {
    uint32_t time_ms;
    const char *text;
    int32_t value;
} log_entry_t;

static log_entry_t entries[LOG_ENTRIES];
static unsigned next_entry;
static unsigned entry_count;

extern void uart_send_line(const char *text);

/* Records an event; the oldest entry is overwritten once the log is full. text must point to a
 * string that lives for the whole program, such as a literal. */
void log_event(const char *text, int32_t value)
{
    entries[next_entry].time_ms = hal_millis();
    entries[next_entry].text = text;
    entries[next_entry].value = value;
    next_entry = (next_entry + 1u) % LOG_ENTRIES;
    if (entry_count < LOG_ENTRIES) {
        entry_count++;
    }
}

void log_dump(void)
{
    char line[64];
    unsigned first = (next_entry + LOG_ENTRIES - entry_count) % LOG_ENTRIES;
    for (unsigned i = 0; i < entry_count; i++) {
        const log_entry_t *e = &entries[(first + i) % LOG_ENTRIES];
        snprintf(line, sizeof line, "log %lu %s %ld", (unsigned long)e->time_ms, e->text, (long)e->value);
        uart_send_line(line);
    }
}
