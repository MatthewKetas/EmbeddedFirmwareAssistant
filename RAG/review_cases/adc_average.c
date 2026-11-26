/* Averages 12-bit ADC samples for a battery voltage reading. */
#include <stddef.h>
#include <stdint.h>

#define SAMPLES 64
#define ADC_FULL_SCALE 4095u
#define VREF_MV 3300u

extern uint16_t adc_read_raw(void);   /* returns 0..4095 */

uint16_t adc_average(size_t count)
{
    uint16_t sum = 0;
    for (size_t i = 0; i < count; i++) {
        sum += adc_read_raw();
    }
    return sum / count;
}

uint32_t battery_mv(void)
{
    uint32_t raw = adc_average(SAMPLES);
    return raw * VREF_MV / ADC_FULL_SCALE;
}
