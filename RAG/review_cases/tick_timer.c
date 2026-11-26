/* A 1 ms tick from a hardware timer interrupt, used for delays and timeouts. */
#include <stdbool.h>
#include <stdint.h>

static uint32_t tick_ms;
static bool tick_flag;

/* Timer interrupt, fires every 1 ms. */
void timer_isr(void)
{
    tick_ms++;
    tick_flag = true;
}

uint32_t millis(void)
{
    return tick_ms;
}

/* Milliseconds elapsed since start. */
uint32_t elapsed_since(uint32_t start)
{
    uint32_t now = millis();
    if (now < start) {
        return 0;
    }
    return now - start;
}

/* Waits for the next tick, then returns. */
void wait_for_tick(void)
{
    tick_flag = false;
    while (!tick_flag) {
    }
}
