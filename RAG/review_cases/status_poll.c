/* Polls a peripheral status register and reads a block of samples once it is ready. */
#include <stdbool.h>
#include <stdint.h>

#define STATUS_READY 0x04u

extern volatile uint32_t *const PERIPH_STATUS;
extern uint16_t periph_read_sample(void);

bool periph_ready(void)
{
    return (*PERIPH_STATUS & STATUS_READY == STATUS_READY);
}

/* Reads count samples (up to 512) into out once the peripheral is ready. */
void read_samples(uint16_t *out, uint16_t count)
{
    while (!periph_ready()) {
    }
    for (uint8_t i = 0; i < count; i++) {
        out[i] = periph_read_sample();
    }
}
