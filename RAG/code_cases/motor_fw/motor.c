/* Speed control and motor protection. The control step runs from the main loop every tick;
 * speed comes from the encoder counter, current from the shunt amplifier. */
#include "board_pins.h"
#include "hal.h"

#define CURRENT_MV_PER_AMP      100u      /* shunt amplifier: 0.1 V per amp */
#define STALL_CURRENT_MA        1500u     /* above this with the motor not turning ... */
#define STALL_TIME_MS           500u      /* ... for this long counts as a stall */
#define STALL_MIN_SPEED_RPM     30
#define OVERCURRENT_MA          4000u     /* trip at once, no delay */
#define KP_PERMILLE             600       /* proportional gain x1000 */
#define KI_PERMILLE             40        /* integral gain x1000 per tick */
#define INTEGRAL_LIMIT          250000

extern void pwm_set_target(uint16_t per_mille);
extern void pwm_enable(bool on);
extern int32_t encoder_speed_rpm(void);
extern void log_event(const char *text, int32_t value);

typedef enum { MOTOR_STOPPED, MOTOR_RUNNING, MOTOR_FAULT } motor_state_t;

static motor_state_t state = MOTOR_STOPPED;
static int32_t setpoint_rpm;
static int32_t integral;
static uint32_t stall_since_ms;
static bool stall_timing;

uint32_t motor_current_ma(void)
{
    return hal_adc_read_mv(PIN_MOTOR_CURRENT) * 1000u / CURRENT_MV_PER_AMP;
}

void motor_start(int32_t rpm)
{
    if (state == MOTOR_FAULT) {
        return;               /* a fault needs motor_clear_fault() first */
    }
    setpoint_rpm = rpm;
    integral = 0;
    stall_timing = false;
    pwm_enable(true);
    state = MOTOR_RUNNING;
}

void motor_stop(void)
{
    pwm_set_target(0);
    pwm_enable(false);
    state = state == MOTOR_FAULT ? MOTOR_FAULT : MOTOR_STOPPED;
}

static void motor_fault(const char *reason, int32_t value)
{
    pwm_set_target(0);
    pwm_enable(false);
    state = MOTOR_FAULT;
    log_event(reason, value);
}

/* Stall: the current stays above STALL_CURRENT_MA while the speed is below STALL_MIN_SPEED_RPM
 * for STALL_TIME_MS without a break. The timer restarts whenever either condition clears, so a
 * hard start does not trip it. Overcurrent above OVERCURRENT_MA, or the driver's fault pin,
 * stops the motor at once. */
static void motor_check_protection(uint32_t now_ms, uint32_t current_ma, int32_t speed_rpm)
{
    if (current_ma > OVERCURRENT_MA) {
        motor_fault("overcurrent mA", (int32_t)current_ma);
        return;
    }
    if (hal_gpio_read(PIN_MOTOR_FAULT) == 0) {
        motor_fault("driver fault", 0);
        return;
    }
    bool stalled_now = current_ma > STALL_CURRENT_MA && speed_rpm < STALL_MIN_SPEED_RPM;
    if (!stalled_now) {
        stall_timing = false;
        return;
    }
    if (!stall_timing) {
        stall_timing = true;
        stall_since_ms = now_ms;
        return;
    }
    if (now_ms - stall_since_ms >= STALL_TIME_MS) {
        motor_fault("stall mA", (int32_t)current_ma);
    }
}

/* One control tick: protection first, then a PI controller on speed whose output is the PWM
 * target in per mille. The integral is clamped so a long stall cannot wind it up. */
void motor_control_step(uint32_t now_ms)
{
    if (state != MOTOR_RUNNING) {
        return;
    }
    uint32_t current_ma = motor_current_ma();
    int32_t speed_rpm = encoder_speed_rpm();
    motor_check_protection(now_ms, current_ma, speed_rpm);
    if (state != MOTOR_RUNNING) {
        return;
    }

    int32_t error = setpoint_rpm - speed_rpm;
    integral += error * KI_PERMILLE;
    if (integral > INTEGRAL_LIMIT) {
        integral = INTEGRAL_LIMIT;
    } else if (integral < -INTEGRAL_LIMIT) {
        integral = -INTEGRAL_LIMIT;
    }
    int32_t output = (error * KP_PERMILLE + integral) / 1000;
    if (output < 0) {
        output = 0;
    } else if (output > 1000) {
        output = 1000;
    }
    pwm_set_target((uint16_t)output);
}

void motor_clear_fault(void)
{
    if (state == MOTOR_FAULT && hal_gpio_read(PIN_MOTOR_FAULT) == 1) {
        state = MOTOR_STOPPED;
    }
}

bool motor_is_faulted(void)
{
    return state == MOTOR_FAULT;
}
