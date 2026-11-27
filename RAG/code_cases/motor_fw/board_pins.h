/* Pin assignments for the MC-2 motor controller board (sample firmware for code_check.py). */
#ifndef BOARD_PINS_H
#define BOARD_PINS_H

/* Motor bridge */
#define PIN_MOTOR_PWM        18   /* high-side PWM to the gate driver */
#define PIN_MOTOR_DIR        19   /* direction: 1 = forward */
#define PIN_MOTOR_ENABLE     23   /* gate driver enable, active high */
#define PIN_MOTOR_FAULT      34   /* driver fault output, input-only pin, active low */

/* Current and battery sensing (ADC1) */
#define PIN_MOTOR_CURRENT    35   /* shunt amplifier output, 0.1 V per amp */
#define PIN_BATTERY_SENSE    36   /* battery divider, 1:2 */

/* Telemetry UART */
#define PIN_UART_TX          17
#define PIN_UART_RX          16

/* Temperature and humidity sensor */
#define PIN_I2C_SDA          21
#define PIN_I2C_SCL          22

/* User interface */
#define PIN_STATUS_LED        2
#define PIN_USER_BUTTON       0   /* also a strapping pin: do not hold low at reset */

#endif
