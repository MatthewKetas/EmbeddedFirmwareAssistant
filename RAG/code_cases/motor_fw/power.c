/* Battery monitoring and low-battery shutdown. The pack is a 1S lithium cell read through a
 * 1:2 divider; one low reading can be load sag, so shutdown needs several in a row. */
#include "board_pins.h"
#include "hal.h"

#define DIVIDER_RATIO          2u
#define BATTERY_WARN_MV        3500u
#define BATTERY_SHUTDOWN_MV    3300u
#define SHUTDOWN_READINGS      5        /* consecutive readings below BATTERY_SHUTDOWN_MV */
#define BATTERY_FILTER_SHIFT   3        /* exponential filter, 1/8 new sample */

extern void motor_stop(void);
extern void config_save_now(void);
extern void log_event(const char *text, int32_t value);

static uint32_t filtered_mv;
static int low_count;
static bool warned;

uint32_t battery_read_mv(void)
{
    return hal_adc_read_mv(PIN_BATTERY_SENSE) * DIVIDER_RATIO;
}

void power_init(void)
{
    filtered_mv = battery_read_mv();
    low_count = 0;
    warned = false;
}

/* Called once a second. Warns once below BATTERY_WARN_MV. Below BATTERY_SHUTDOWN_MV for
 * SHUTDOWN_READINGS consecutive calls it stops the motor, saves the configuration and powers
 * the board off; any reading at or above the threshold resets the count. */
void power_check_battery(void)
{
    uint32_t sample = battery_read_mv();
    filtered_mv += (sample >> BATTERY_FILTER_SHIFT) - (filtered_mv >> BATTERY_FILTER_SHIFT);

    if (filtered_mv < BATTERY_WARN_MV && !warned) {
        warned = true;
        log_event("battery low mV", (int32_t)filtered_mv);
    }

    if (sample < BATTERY_SHUTDOWN_MV) {
        low_count++;
    } else {
        low_count = 0;
    }
    if (low_count >= SHUTDOWN_READINGS) {
        log_event("battery shutdown mV", (int32_t)sample);
        motor_stop();
        config_save_now();
        hal_power_off();
    }
}

uint32_t power_battery_mv(void)
{
    return filtered_mv;
}
