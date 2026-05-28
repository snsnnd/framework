#ifndef EFW_COMM_REGISTRY_H
#define EFW_COMM_REGISTRY_H

#include "efw_common.h"
#include <stdint.h>

typedef enum {
    EFW_COMM_UART = 0,
    EFW_COMM_CAN,
    EFW_COMM_I2C,
    EFW_COMM_SPI,
    EFW_COMM_ETH,
    EFW_COMM_CUSTOM
} efw_comm_type_t;

typedef struct {
    const char *name;            /* 例如 dbg_uart, motor_can */
    efw_comm_type_t type;
    const char *hal_binding;     /* 绑定的 HAL 名称，例如 uart1 */
    void *ctx;
    efw_status_t (*open)(void *ctx);
    efw_status_t (*close)(void *ctx);
    efw_status_t (*send)(void *ctx, const uint8_t *data, uint16_t len, uint16_t *actual);
    efw_status_t (*recv)(void *ctx, uint8_t *data, uint16_t len, uint16_t *actual);
} efw_comm_ops_t;

efw_status_t efw_comm_registry_init(void);
efw_status_t efw_comm_register(const efw_comm_ops_t *ops);
efw_status_t efw_comm_get(const char *name, const efw_comm_ops_t **out_ops);
size_t efw_comm_count_by_type(efw_comm_type_t type);

#endif
