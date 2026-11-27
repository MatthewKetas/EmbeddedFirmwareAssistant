/* Main loop for the MC-2 motor controller. A cooperative scheduler runs the control step every
 * tick and slower work on multiples of it; nothing in the loop may block for long, because the
 * watchdog expects every task to check in within its timeout. */
#include "board_pins.h"
#include "hal.h"

#define CONTROL_PERIOD_MS     10u      /* motor control and PWM ramp */
#define CONSOLE_PERIOD_MS     20u
#define SENSOR_PERIOD_MS      2000u
#define BATTERY_PERIOD_MS     1000u
#define LED_BLINK_MS          500u

typedef struct {
    int16_t temperature_centi;
    uint16_t humidity_centi;
} env_reading_t;

extern int pwm_init(void);
extern void pwm_ramp_step(void);
extern int uart_rx_init(void);
extern void uart_send_line(const char *text);
extern int env_sensor_init(void);
extern int env_sensor_read(env_reading_t *out);
extern void motor_control_step(uint32_t now_ms);
extern bool motor_is_faulted(void);
extern void encoder_update(uint32_t now_ms);
extern void watchdog_init(void);
extern int watchdog_register(void);
extern void watchdog_checkin(int task_id);
extern void watchdog_service(void);
extern void power_init(void);
extern void power_check_battery(void);
extern void config_load(void);
extern void console_poll(void);
extern void log_event(const char *text, int32_t value);
extern void log_dump(void);

static uint32_t due(uint32_t *last, uint32_t now, uint32_t period)
{
    if (now - *last >= period) {
        *last = now;
        return 1;
    }
    return 0;
}

int main(void)
{
    hal_gpio_output(PIN_STATUS_LED);
    hal_gpio_input(PIN_MOTOR_FAULT, true);
    hal_gpio_input(PIN_USER_BUTTON, true);

    config_load();
    watchdog_init();
    int control_task = watchdog_register();
    int console_task = watchdog_register();

    if (pwm_init() < 0) {
        log_event("pwm init", 0);
    }
    if (uart_rx_init() < 0) {
        log_event("uart init", 0);
    }
    if (env_sensor_init() < 0) {
        log_event("sensor init", 0);
    }
    power_init();

    uint32_t last_control = 0, last_console = 0, last_sensor = 0, last_battery = 0, last_led = 0;
    int led = 0;
    for (;;) {
        uint32_t now = hal_millis();

        /* Control every CONTROL_PERIOD_MS: speed, protection, then the PWM ramp. */
        if (due(&last_control, now, CONTROL_PERIOD_MS)) {
            encoder_update(now);
            motor_control_step(now);
            pwm_ramp_step();
            watchdog_checkin(control_task);
        }
        if (due(&last_console, now, CONSOLE_PERIOD_MS)) {
            console_poll();
            watchdog_checkin(console_task);
        }
        if (due(&last_battery, now, BATTERY_PERIOD_MS)) {
            power_check_battery();
        }
        if (due(&last_sensor, now, SENSOR_PERIOD_MS)) {
            env_reading_t reading;
            if (env_sensor_read(&reading) < 0) {
                log_event("sensor read", 0);
            }
            log_dump();
        }
        if (due(&last_led, now, motor_is_faulted() ? LED_BLINK_MS / 5u : LED_BLINK_MS)) {
            led = !led;
            hal_gpio_write(PIN_STATUS_LED, led);
        }
        watchdog_service();
    }
}
