/* Minimal hardware abstraction layer used by the sample firmware. All functions are provided by
 * the board support package; return values below 0 are error codes. */
#ifndef HAL_H
#define HAL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define HAL_OK            0
#define HAL_ERR_TIMEOUT  -1
#define HAL_ERR_NACK     -2
#define HAL_ERR_BUSY     -3
#define HAL_ERR_CRC      -4

uint32_t hal_millis(void);
void hal_delay_ms(uint32_t ms);

void hal_gpio_output(int pin);
void hal_gpio_input(int pin, bool pull_up);
void hal_gpio_write(int pin, int level);
int hal_gpio_read(int pin);

int hal_pwm_setup(int pin, uint32_t frequency_hz, uint8_t resolution_bits);
void hal_pwm_write(int pin, uint32_t duty);

int hal_uart_open(int tx_pin, int rx_pin, uint32_t baud);
void hal_uart_write(const uint8_t *data, size_t len);

int hal_i2c_open(int sda_pin, int scl_pin, uint32_t clock_hz);
int hal_i2c_write(uint8_t addr, const uint8_t *data, size_t len, uint32_t timeout_ms);
int hal_i2c_read(uint8_t addr, uint8_t *data, size_t len, uint32_t timeout_ms);

uint32_t hal_adc_read_mv(int pin);

int hal_nvs_read(const char *key, void *data, size_t len);
int hal_nvs_write(const char *key, const void *data, size_t len);

void hal_wdt_start(uint32_t timeout_ms);
void hal_wdt_feed(void);

void hal_power_off(void);

#endif
