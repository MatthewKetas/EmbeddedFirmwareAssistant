/* Quadrature encoder on the motor shaft, 256 pulses per revolution. The capture interrupt
 * counts edges; speed is computed from the count over a 100 ms window. */
#include "hal.h"

#define ENCODER_PPR           256
#define ENCODER_EDGES_PER_REV (ENCODER_PPR * 4)
#define SPEED_WINDOW_MS       100u

static volatile int32_t edge_count;
static int32_t last_count;
static uint32_t last_window_ms;
static int32_t speed_rpm;

void encoder_edge_isr(bool forward)
{
    edge_count += forward ? 1 : -1;
}

/* Called every tick; updates the speed once per SPEED_WINDOW_MS. */
void encoder_update(uint32_t now_ms)
{
    uint32_t elapsed = now_ms - last_window_ms;
    if (elapsed < SPEED_WINDOW_MS) {
        return;
    }
    int32_t count = edge_count;
    int32_t edges = count - last_count;
    speed_rpm = (int32_t)((int64_t)edges * 60000 / ((int64_t)ENCODER_EDGES_PER_REV * (int64_t)elapsed));
    last_count = count;
    last_window_ms = now_ms;
}

int32_t encoder_speed_rpm(void)
{
    return speed_rpm;
}
