/* Text commands on the telemetry UART: "run <rpm>", "stop", "stat", "clear", "save". Lines
 * end with CR or LF; longer lines than the buffer are discarded whole. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "hal.h"

#define LINE_MAX_LEN   48

extern size_t uart_rx_read(uint8_t *out, size_t max);
extern uint32_t uart_rx_overruns(void);
extern void uart_send_line(const char *text);
extern void motor_start(int32_t rpm);
extern void motor_stop(void);
extern void motor_clear_fault(void);
extern bool motor_is_faulted(void);
extern uint32_t motor_current_ma(void);
extern int32_t encoder_speed_rpm(void);
extern uint32_t power_battery_mv(void);
extern int32_t config_max_rpm(void);
extern void config_set_default_rpm(int32_t rpm);
extern void config_save_now(void);

static char line[LINE_MAX_LEN];
static size_t line_len;
static bool line_too_long;

static void console_execute(char *text)
{
    char reply[64];
    if (strncmp(text, "run ", 4) == 0) {
        long rpm = strtol(text + 4, NULL, 10);
        if (rpm <= 0 || rpm > config_max_rpm()) {
            uart_send_line("err rpm");
            return;
        }
        motor_start((int32_t)rpm);
        config_set_default_rpm((int32_t)rpm);
        uart_send_line("ok");
    } else if (strcmp(text, "stop") == 0) {
        motor_stop();
        uart_send_line("ok");
    } else if (strcmp(text, "stat") == 0) {
        snprintf(reply, sizeof reply, "rpm %ld mA %lu bat %lu ovr %lu%s",
                 (long)encoder_speed_rpm(), (unsigned long)motor_current_ma(),
                 (unsigned long)power_battery_mv(), (unsigned long)uart_rx_overruns(),
                 motor_is_faulted() ? " FAULT" : "");
        uart_send_line(reply);
    } else if (strcmp(text, "clear") == 0) {
        motor_clear_fault();
        uart_send_line(motor_is_faulted() ? "err fault active" : "ok");
    } else if (strcmp(text, "save") == 0) {
        config_save_now();
        uart_send_line("ok");
    } else {
        uart_send_line("err unknown");
    }
}

/* Called from the main loop. Collects received bytes into a line and runs it at CR or LF. */
void console_poll(void)
{
    uint8_t chunk[16];
    size_t n;
    while ((n = uart_rx_read(chunk, sizeof chunk)) > 0) {
        for (size_t i = 0; i < n; i++) {
            char c = (char)chunk[i];
            if (c == '\r' || c == '\n') {
                if (line_len > 0 && !line_too_long) {
                    line[line_len] = '\0';
                    console_execute(line);
                }
                line_len = 0;
                line_too_long = false;
            } else if (line_len < LINE_MAX_LEN - 1) {
                line[line_len++] = c;
            } else {
                line_too_long = true;
            }
        }
    }
}
