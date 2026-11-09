/*
 * Implement Critter, an unattended temperature monitor for distributed machine
 * rooms. Return one complete, self-contained C11 source file. Keep the public
 * declarations below and implement all three functions. The caller owns the
 * sensor, buffers, and sampling schedule. Use fixed-size scratch storage and
 * the C standard library. The source must compile without a main function,
 * hardware drivers, external dependencies, or console or file I/O.
 *
 * Acquisition
 * critter_collect calls the sensor once per sample, in order, and writes raw
 * readings to samples without filtering. Collect min(requested, capacity)
 * readings and return that count. The caller provides room for that many floats.
 * If sensor or samples is NULL, or requested is zero, return zero without
 * calling the sensor or writing the output. Pass context through unchanged.
 *
 * Offline summary
 * critter_summarize accepts 1 to CRITTER_CAPACITY samples in Celsius. Ignore
 * non-finite readings and readings outside the inclusive range [-40, 125].
 * Compute the median of the remaining readings, averaging the middle two
 * when their count is even. Reject readings more than 5 degrees from that
 * median. Fill the kept count, total rejected count, and mean, minimum and
 * maximum of the kept readings. Return 1 on success. Return 0 and leave the
 * output untouched for NULL input/output, an invalid count or no kept readings.
 * Preserve the input buffer.
 *
 * HVAC forecast
 * critter_predict receives 2 to CRITTER_CAPACITY consecutive window means,
 * oldest first and evenly spaced. Fit an ordinary least-squares line with
 * sample indices 0 through count - 1 as x and the means as y. Write the
 * predicted temperature at x = count - 1 + steps, where steps is 1 through
 * CRITTER_CAPACITY. Return 1 if the forecast is at or above high_limit and
 * 0 if below. Return -1 and leave the output untouched for NULL input/output,
 * invalid count/steps or any non-finite mean, high_limit or forecast.
 * Preserve the input buffer.
 */

#include <stddef.h>

enum { CRITTER_CAPACITY = 64 };

typedef struct {
    size_t kept;
    size_t rejected;
    float mean;
    float minimum;
    float maximum;
} CritterSummary;

size_t critter_collect(float (*sensor)(void *), void *context,
                       float *samples, size_t requested);
int critter_summarize(const float *samples, size_t count, CritterSummary *summary);
int critter_predict(const float *means, size_t count, size_t steps,
                    float high_limit, float *forecast);
