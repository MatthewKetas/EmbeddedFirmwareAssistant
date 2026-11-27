/* Motor PWM output. The gate driver accepts 5-30 kHz; 20 kHz keeps switching noise above
 * hearing while staying well inside the driver's limit. */
#include "board_pins.h"
#include "hal.h"

#define PWM_FREQUENCY_HZ   20000u
#define PWM_RESOLUTION     10u                      /* bits */
#define PWM_MAX_DUTY       ((1u << PWM_RESOLUTION) - 1u)
#define PWM_RAMP_STEP      8u                       /* duty counts per ramp tick */

static uint32_t current_duty;
static uint32_t target_duty;
static bool pwm_ready;

/* Configures the PWM pin, the direction pin and the driver enable. The driver stays disabled
 * until pwm_enable() is called, so a reset never spins the motor. */
int pwm_init(void)
{
    hal_gpio_output(PIN_MOTOR_DIR);
    hal_gpio_output(PIN_MOTOR_ENABLE);
    hal_gpio_write(PIN_MOTOR_ENABLE, 0);
    hal_gpio_write(PIN_MOTOR_DIR, 1);

    int err = hal_pwm_setup(PIN_MOTOR_PWM, PWM_FREQUENCY_HZ, PWM_RESOLUTION);
    if (err < 0) {
        return err;
    }
    hal_pwm_write(PIN_MOTOR_PWM, 0);
    current_duty = 0;
    target_duty = 0;
    pwm_ready = true;
    return HAL_OK;
}

void pwm_enable(bool on)
{
    if (!pwm_ready) {
        return;
    }
    if (!on) {
        hal_pwm_write(PIN_MOTOR_PWM, 0);
        current_duty = 0;
        target_duty = 0;
    }
    hal_gpio_write(PIN_MOTOR_ENABLE, on ? 1 : 0);
}

/* Sets the duty the ramp moves towards, in per mille of full scale (0-1000). */
void pwm_set_target(uint16_t per_mille)
{
    if (per_mille > 1000u) {
        per_mille = 1000u;
    }
    target_duty = (uint32_t)per_mille * PWM_MAX_DUTY / 1000u;
}

/* Called every control tick. Moves the duty towards the target by at most PWM_RAMP_STEP so a
 * step change in the target does not draw a current spike from the battery. */
void pwm_ramp_step(void)
{
    if (!pwm_ready) {
        return;
    }
    if (current_duty < target_duty) {
        uint32_t gap = target_duty - current_duty;
        current_duty += gap < PWM_RAMP_STEP ? gap : PWM_RAMP_STEP;
    } else if (current_duty > target_duty) {
        uint32_t gap = current_duty - target_duty;
        current_duty -= gap < PWM_RAMP_STEP ? gap : PWM_RAMP_STEP;
    }
    hal_pwm_write(PIN_MOTOR_PWM, current_duty);
}

void pwm_set_direction(bool forward)
{
    /* Reversing under load stresses the bridge: only change direction at zero duty. */
    if (current_duty != 0) {
        return;
    }
    hal_gpio_write(PIN_MOTOR_DIR, forward ? 1 : 0);
}

uint32_t pwm_current_duty(void)
{
    return current_duty;
}
