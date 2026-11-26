/* Reads measurement registers from an I2C temperature and humidity sensor. */
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#define SENSOR_ADDR 0x44
#define REG_MEASURE 0xE0

/* Both return 0 on success and a negative error code on failure. */
extern int i2c_write(uint8_t addr, const uint8_t *data, size_t len);
extern int i2c_read(uint8_t addr, uint8_t *data, size_t len);

int sensor_read(uint8_t reg, uint8_t *out, size_t len)
{
    uint8_t buf[4];
    i2c_write(SENSOR_ADDR, &reg, 1);
    int err = i2c_read(SENSOR_ADDR, buf, len);
    if (err < 0) {
        return err;
    }
    memcpy(out, buf, len);
    return 0;
}

int sensor_temperature_centi(int32_t *out)
{
    uint8_t raw[2];
    int err = sensor_read(REG_MEASURE, raw, sizeof raw);
    if (err < 0) {
        return err;
    }
    uint16_t ticks = (uint16_t)((raw[0] << 8) | raw[1]);
    *out = -4500 + (17500 * (int32_t)ticks) / 65535;
    return 0;
}
