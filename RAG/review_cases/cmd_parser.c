/* Parses single-letter commands received over the debug console. */
#include <stdint.h>
#include <stdio.h>

typedef enum { CMD_LED_ON, CMD_LED_OFF, CMD_STATUS, CMD_UNKNOWN } command_t;

extern void led_set(int on);
extern uint32_t uptime_s(void);

command_t parse_command(char c)
{
    switch (c) {
    case 'n':
        return CMD_LED_ON;
    case 'f':
        return CMD_LED_OFF;
    case 's':
        return CMD_STATUS;
    default:
        return CMD_UNKNOWN;
    }
}

/* Returns the reply text to send back to the console. */
const char *run_command(command_t cmd)
{
    char reply[32];
    switch (cmd) {
    case CMD_LED_ON:
        led_set(1);
        snprintf(reply, sizeof reply, "led on");
    case CMD_LED_OFF:
        led_set(0);
        snprintf(reply, sizeof reply, "led off");
        break;
    case CMD_STATUS:
        snprintf(reply, sizeof reply, "up %lu s", (unsigned long)uptime_s());
        break;
    default:
        snprintf(reply, sizeof reply, "unknown");
        break;
    }
    return reply;
}
