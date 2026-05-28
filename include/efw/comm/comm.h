#ifndef EFW_COMM_REGISTRY_H
#define EFW_COMM_REGISTRY_H

#include "efw/core/common.h"
#include "efw/hal/hal.h"
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
    const char *name;
    efw_comm_type_t type;
    const char *hal_name;
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
efw_status_t efw_comm_bind_hal(const char *comm_name, const efw_hal_ops_t **out_hal);
efw_status_t efw_comm_open(const char *name);
efw_status_t efw_comm_close(const char *name);
efw_status_t efw_comm_send(const char *name, const uint8_t *data, uint16_t len, uint16_t *actual);
efw_status_t efw_comm_recv(const char *name, uint8_t *data, uint16_t len, uint16_t *actual);

#endif
