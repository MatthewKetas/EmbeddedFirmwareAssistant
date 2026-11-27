/* Temperature and humidity sensor on I2C. The sensor stretches the clock while converting, so
 * a read can time out or be NACKed when it is still busy; reads are retried. */
#include "board_pins.h"
#include "hal.h"

#define SENSOR_ADDR          0x44
#define CMD_MEASURE_HIGH     0x2400u
#define I2C_CLOCK_HZ         100000u
#define SENSOR_RETRIES       3          /* attempts after the first one */
#define SENSOR_TIMEOUT_MS    50u        /* per I2C transfer */
#define SENSOR_RETRY_GAP_MS  20u

typedef struct {
    int16_t temperature_centi;   /* 0.01 degC */
    uint16_t humidity_centi;     /* 0.01 %RH */
} env_reading_t;

static uint8_t crc8(const uint8_t *data, size_t len)
{
    uint8_t crc = 0xFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int bit = 0; bit < 8; bit++) {
            crc = (crc & 0x80u) ? (uint8_t)((crc << 1) ^ 0x31u) : (uint8_t)(crc << 1);
        }
    }
    return crc;
}

int env_sensor_init(void)
{
    return hal_i2c_open(PIN_I2C_SDA, PIN_I2C_SCL, I2C_CLOCK_HZ);
}

/* Starts a measurement and reads the result. Each transfer waits up to SENSOR_TIMEOUT_MS; on a
 * timeout, NACK or CRC error the whole exchange is repeated up to SENSOR_RETRIES more times,
 * SENSOR_RETRY_GAP_MS apart. Returns the last error if every attempt fails. */
int env_sensor_read(env_reading_t *out)
{
    const uint8_t cmd[2] = {(uint8_t)(CMD_MEASURE_HIGH >> 8), (uint8_t)CMD_MEASURE_HIGH};
    uint8_t raw[6];
    int err = HAL_ERR_TIMEOUT;

    for (int attempt = 0; attempt <= SENSOR_RETRIES; attempt++) {
        if (attempt > 0) {
            hal_delay_ms(SENSOR_RETRY_GAP_MS);
        }
        err = hal_i2c_write(SENSOR_ADDR, cmd, sizeof cmd, SENSOR_TIMEOUT_MS);
        if (err < 0) {
            continue;
        }
        err = hal_i2c_read(SENSOR_ADDR, raw, sizeof raw, SENSOR_TIMEOUT_MS);
        if (err < 0) {
            continue;
        }
        if (crc8(raw, 2) != raw[2] || crc8(raw + 3, 2) != raw[5]) {
            err = HAL_ERR_CRC;
            continue;
        }
        uint16_t t_ticks = (uint16_t)((raw[0] << 8) | raw[1]);
        uint16_t h_ticks = (uint16_t)((raw[3] << 8) | raw[4]);
        out->temperature_centi = (int16_t)(-4500 + (17500 * (int32_t)t_ticks) / 65535);
        out->humidity_centi = (uint16_t)((10000u * (uint32_t)h_ticks) / 65535u);
        return HAL_OK;
    }
    return err;
}
