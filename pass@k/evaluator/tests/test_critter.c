#include "critter.c"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#define CLOSE(actual, expected) assert(fabsf((actual) - (expected)) < 0.0001f)

typedef struct {
    const float *readings;
    size_t calls;
} Sensor;

static float read_sensor(void *context)
{
    Sensor *sensor = context;
    assert(sensor->calls < CRITTER_CAPACITY);
    return sensor->readings[sensor->calls++];
}

static void test_io(void)
{
    float input[CRITTER_CAPACITY];
    float output[CRITTER_CAPACITY + 1] = {0};
    for (size_t i = 0; i < CRITTER_CAPACITY; ++i)
        input[i] = 12.0f + i / 4.0f;
    input[7] = NAN;
    output[CRITTER_CAPACITY] = -999.0f;
    Sensor sensor = {input, 0};

    assert(critter_collect(NULL, &sensor, output, 3) == 0);
    assert(critter_collect(read_sensor, &sensor, NULL, 3) == 0);
    assert(critter_collect(read_sensor, &sensor, output, 0) == 0);
    assert(sensor.calls == 0);
    CLOSE(output[0], 0.0f);
    assert(critter_collect(read_sensor, &sensor, output, CRITTER_CAPACITY + 7) == CRITTER_CAPACITY);
    assert(sensor.calls == CRITTER_CAPACITY);
    for (size_t i = 0; i < CRITTER_CAPACITY; ++i) {
        if (i == 7)
            assert(isnan(output[i]));
        else
            CLOSE(output[i], input[i]);
    }
    CLOSE(output[CRITTER_CAPACITY], -999.0f);
}

static void test_summary(void)
{
    float samples[] = {100.0f, 20.0f, NAN, 25.5f, -41.0f, 22.0f, 21.0f};
    float original[7];
    memcpy(original, samples, sizeof samples);
    CritterSummary summary = {0};
    assert(critter_summarize(samples, 7, &summary) == 1);
    assert(memcmp(original, samples, sizeof samples) == 0);
    assert(summary.kept == 4 && summary.rejected == 3);
    CLOSE(summary.mean, 22.125f);
    CLOSE(summary.minimum, 20.0f);
    CLOSE(summary.maximum, 25.5f);

    const float even[] = {20.0f, 10.0f};
    assert(critter_summarize(even, 2, &summary) == 1);
    assert(summary.kept == 2 && summary.rejected == 0);
    CLOSE(summary.mean, 15.0f);
    const float invalid[] = {NAN, INFINITY, 126.0f};
    assert(critter_summarize(invalid, 3, &summary) == 0);
    assert(critter_summarize(even, 0, &summary) == 0);
    assert(critter_summarize(even, CRITTER_CAPACITY + 1, &summary) == 0);
    assert(critter_summarize(NULL, 2, &summary) == 0);
    assert(critter_summarize(even, 2, NULL) == 0);
    assert(summary.kept == 2 && summary.rejected == 0);
    CLOSE(summary.mean, 15.0f);
    CLOSE(summary.minimum, 10.0f);
    CLOSE(summary.maximum, 20.0f);
}

static void test_prediction(void)
{
    const float noisy[] = {10.0f, 14.0f, 11.0f, 13.0f};
    const float flat[] = {20.0f, 20.0f};
    const float invalid[] = {20.0f, NAN};
    float forecast = -1.0f;
    assert(critter_predict(noisy, 4, 2, 14.0f, &forecast) == 1);
    CLOSE(forecast, 14.1f);
    assert(critter_predict(noisy, 4, 1, 14.0f, &forecast) == 0);
    CLOSE(forecast, 13.5f);
    assert(critter_predict(flat, 2, 64, 20.0f, &forecast) == 1);
    CLOSE(forecast, 20.0f);
    assert(critter_predict(flat, 2, 0, 20.0f, &forecast) == -1);
    assert(critter_predict(flat, 2, 65, 20.0f, &forecast) == -1);
    assert(critter_predict(flat, 1, 1, 20.0f, &forecast) == -1);
    assert(critter_predict(flat, 65, 1, 20.0f, &forecast) == -1);
    assert(critter_predict(flat, 2, 1, INFINITY, &forecast) == -1);
    assert(critter_predict(invalid, 2, 1, 20.0f, &forecast) == -1);
    assert(critter_predict(NULL, 2, 1, 20.0f, &forecast) == -1);
    assert(critter_predict(flat, 2, 1, 20.0f, NULL) == -1);
    CLOSE(forecast, 20.0f);
}

static void test_pipeline(void)
{
    float means[3];
    for (size_t i = 0; i < 3; ++i) {
        float base = 20.0f + 2.0f * i;
        float input[] = {base - 1.0f, base, base + 1.0f, base + 40.0f};
        float samples[4];
        Sensor sensor = {input, 0};
        CritterSummary summary;
        size_t count = critter_collect(read_sensor, &sensor, samples, 4);
        assert(count == 4);
        assert(critter_summarize(samples, count, &summary) == 1);
        assert(summary.kept == 3 && summary.rejected == 1);
        means[i] = summary.mean;
    }
    float forecast;
    assert(critter_predict(means, 3, 1, 25.0f, &forecast) == 1);
    CLOSE(forecast, 26.0f);
}

int main(int argc, char **argv)
{
    if (argc != 2)
        return 2;
    const char *group = argv[1];
    if (strcmp(group, "io") == 0)
        test_io();
    else if (strcmp(group, "summary") == 0)
        test_summary();
    else if (strcmp(group, "prediction") == 0)
        test_prediction();
    else if (strcmp(group, "pipeline") == 0)
        test_pipeline();
    else
        return 2;
    printf("PASS %s\n", group);
    return 0;
}
