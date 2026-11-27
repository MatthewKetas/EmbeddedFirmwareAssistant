/* Persistent configuration in non-volatile storage. The stored block carries a version and a
 * CRC-16 so a half-written or old-format block is never used. */
#include <string.h>

#include "hal.h"

#define CONFIG_KEY        "mc2cfg"
#define CONFIG_VERSION    3u

typedef struct {
    uint16_t version;
    int32_t max_rpm;
    int32_t default_rpm;
    uint16_t telemetry_period_ms;
    uint8_t led_brightness;
    uint8_t reserved;
    uint16_t crc;
} config_t;

static config_t config;
static bool dirty;

extern void log_event(const char *text, int32_t value);
void config_save_now(void);

static uint16_t crc16_ccitt(const uint8_t *data, size_t len)
{
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= (uint16_t)data[i] << 8;
        for (int bit = 0; bit < 8; bit++) {
            crc = (crc & 0x8000u) ? (uint16_t)((crc << 1) ^ 0x1021u) : (uint16_t)(crc << 1);
        }
    }
    return crc;
}

static void config_defaults(config_t *c)
{
    memset(c, 0, sizeof *c);
    c->version = CONFIG_VERSION;
    c->max_rpm = 3000;
    c->default_rpm = 1200;
    c->telemetry_period_ms = 1000;
    c->led_brightness = 128;
}

/* Loads the stored block. If it is missing, has another version, or fails its CRC, the defaults
 * are used instead and written back at once, so the next boot finds a valid block; the reason
 * is logged. */
void config_load(void)
{
    config_t stored;
    int err = hal_nvs_read(CONFIG_KEY, &stored, sizeof stored);
    const char *problem = NULL;
    if (err < 0) {
        problem = "config missing";
    } else if (stored.version != CONFIG_VERSION) {
        problem = "config version";
    } else if (crc16_ccitt((const uint8_t *)&stored, offsetof(config_t, crc)) != stored.crc) {
        problem = "config crc";
    }

    if (problem == NULL) {
        config = stored;
        dirty = false;
        return;
    }
    log_event(problem, err);
    config_defaults(&config);
    dirty = true;
    config_save_now();
}

void config_save_now(void)
{
    if (!dirty) {
        return;
    }
    config.crc = crc16_ccitt((const uint8_t *)&config, offsetof(config_t, crc));
    if (hal_nvs_write(CONFIG_KEY, &config, sizeof config) == HAL_OK) {
        dirty = false;
    }
}

int32_t config_max_rpm(void)
{
    return config.max_rpm;
}

int32_t config_default_rpm(void)
{
    return config.default_rpm;
}

uint16_t config_telemetry_period_ms(void)
{
    return config.telemetry_period_ms;
}

void config_set_default_rpm(int32_t rpm)
{
    if (rpm < 0 || rpm > config.max_rpm) {
        return;
    }
    config.default_rpm = rpm;
    dirty = true;
}
