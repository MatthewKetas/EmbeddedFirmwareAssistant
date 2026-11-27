/* Task watchdog. Each task checks in through watchdog_checkin(); the hardware watchdog is fed
 * only when every registered task has checked in since the last feed, so a hung task resets
 * the board even if the main loop itself keeps running. */
#include "hal.h"

#define WDT_TIMEOUT_MS     2000u
#define WDT_MAX_TASKS      4

static uint8_t registered_mask;
static uint8_t checked_in_mask;
static int task_count;

void watchdog_init(void)
{
    registered_mask = 0;
    checked_in_mask = 0;
    task_count = 0;
    hal_wdt_start(WDT_TIMEOUT_MS);
}

/* Returns a task id for watchdog_checkin(), or -1 when all slots are taken. */
int watchdog_register(void)
{
    if (task_count >= WDT_MAX_TASKS) {
        return -1;
    }
    int id = task_count++;
    registered_mask |= (uint8_t)(1u << id);
    return id;
}

void watchdog_checkin(int task_id)
{
    if (task_id >= 0 && task_id < WDT_MAX_TASKS) {
        checked_in_mask |= (uint8_t)(1u << task_id);
    }
}

/* Called once per main-loop pass. Feeds the hardware watchdog only when every registered task
 * has checked in, then starts a new round. */
void watchdog_service(void)
{
    if ((checked_in_mask & registered_mask) == registered_mask) {
        hal_wdt_feed();
        checked_in_mask = 0;
    }
}
