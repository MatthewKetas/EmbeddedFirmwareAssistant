/* UART receive ring buffer, filled from the RX interrupt and drained by the main loop. */
#include <stdbool.h>
#include <stdint.h>

#define RB_SIZE 64

typedef struct {
    volatile uint8_t buf[RB_SIZE];
    volatile uint16_t head;   /* written by the ISR */
    volatile uint16_t tail;   /* written by the main loop */
} ring_t;

static ring_t rx;

/* Called from the UART RX interrupt with each received byte. */
void uart_rx_isr(uint8_t byte)
{
    uint16_t next = rx.head + 1;
    if (next > RB_SIZE) {
        next = 0;
    }
    rx.buf[rx.head] = byte;
    rx.head = next;
}

/* Returns false when no byte is waiting. */
bool uart_read(uint8_t *out)
{
    if (rx.tail == rx.head) {
        return false;
    }
    *out = rx.buf[rx.tail];
    rx.tail = (rx.tail + 1) % RB_SIZE;
    return true;
}
