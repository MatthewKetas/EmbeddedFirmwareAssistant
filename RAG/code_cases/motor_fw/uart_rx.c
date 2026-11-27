/* Telemetry UART receive path. Bytes arrive in the RX interrupt and are drained by the
 * command console in the main loop. */
#include "board_pins.h"
#include "hal.h"

#define RX_BUFFER_SIZE   128u      /* power of two, so the index wraps with a mask */
#define RX_INDEX_MASK    (RX_BUFFER_SIZE - 1u)
#define TELEMETRY_BAUD   115200u

static volatile uint8_t rx_buffer[RX_BUFFER_SIZE];
static volatile uint16_t rx_head;          /* written by the ISR */
static volatile uint16_t rx_tail;          /* written by the main loop */
static volatile uint32_t rx_overruns;      /* bytes dropped because the buffer was full */

int uart_rx_init(void)
{
    rx_head = 0;
    rx_tail = 0;
    rx_overruns = 0;
    return hal_uart_open(PIN_UART_TX, PIN_UART_RX, TELEMETRY_BAUD);
}

/* Called from the UART RX interrupt for each received byte. When the buffer is full the new
 * byte is dropped and counted, so data already queued for the console is never overwritten;
 * the console reports the count with the "stat" command. */
void uart_rx_isr(uint8_t byte)
{
    uint16_t next = (uint16_t)((rx_head + 1u) & RX_INDEX_MASK);
    if (next == rx_tail) {
        rx_overruns++;
        return;
    }
    rx_buffer[rx_head] = byte;
    rx_head = next;
}

/* Returns the number of bytes copied into out, at most max. */
size_t uart_rx_read(uint8_t *out, size_t max)
{
    size_t count = 0;
    while (count < max && rx_tail != rx_head) {
        out[count++] = rx_buffer[rx_tail];
        rx_tail = (uint16_t)((rx_tail + 1u) & RX_INDEX_MASK);
    }
    return count;
}

/* Bytes waiting to be read. */
size_t uart_rx_available(void)
{
    return (size_t)((rx_head - rx_tail) & RX_INDEX_MASK);
}

uint32_t uart_rx_overruns(void)
{
    return rx_overruns;
}

void uart_send_line(const char *text)
{
    size_t len = 0;
    while (text[len] != '\0') {
        len++;
    }
    hal_uart_write((const uint8_t *)text, len);
    hal_uart_write((const uint8_t *)"\r\n", 2);
}
