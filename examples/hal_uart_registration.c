#include "efw/hal_registry.h"
#include "efw/comm_registry.h"

static efw_status_t uart_init(void *ctx) { (void)ctx; return EFW_OK; }
static efw_status_t uart_read(void *ctx, void *buf, uint16_t len, uint16_t *actual) {
    (void)ctx; (void)buf; if (actual) *actual = len; return EFW_OK;
}
static efw_status_t uart_write(void *ctx, const void *buf, uint16_t len, uint16_t *actual) {
    (void)ctx; (void)buf; if (actual) *actual = len; return EFW_OK;
}
static efw_status_t uart_ioctl(void *ctx, uint32_t cmd, void *arg) {
    (void)ctx; (void)cmd; (void)arg; return EFW_OK;
}

static efw_status_t comm_open(void *ctx) { (void)ctx; return EFW_OK; }
static efw_status_t comm_close(void *ctx) { (void)ctx; return EFW_OK; }
static efw_status_t comm_send(void *ctx, const uint8_t *data, uint16_t len, uint16_t *actual) {
    (void)ctx; (void)data; if (actual) *actual = len; return EFW_OK;
}
static efw_status_t comm_recv(void *ctx, uint8_t *data, uint16_t len, uint16_t *actual) {
    (void)ctx; (void)data; if (actual) *actual = len; return EFW_OK;
}

static efw_hal_ops_t uart1_hal = {
    .name = "uart1", .type = EFW_HAL_UART, .bus_id = 1, .ctx = 0,
    .init = uart_init, .read = uart_read, .write = uart_write, .ioctl = uart_ioctl
};

static efw_comm_ops_t dbg_uart = {
    .name = "dbg_uart", .type = EFW_COMM_UART, .hal_binding = "uart1", .ctx = 0,
    .open = comm_open, .close = comm_close, .send = comm_send, .recv = comm_recv
};

void register_uart_stack_example(void) {
    efw_hal_registry_init();
    efw_comm_registry_init();

    efw_hal_register(&uart1_hal);
    efw_comm_register(&dbg_uart);
}
