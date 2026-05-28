#ifndef EFW_HAL_REGISTRY_H
#define EFW_HAL_REGISTRY_H

#include "efw/core/common.h"
#include <stdint.h>

typedef enum {
    EFW_HAL_GPIO = 0,
    EFW_HAL_I2C,
    EFW_HAL_SPI,
    EFW_HAL_UART,
    EFW_HAL_TIMER,
    EFW_HAL_PWM,
    EFW_HAL_ADC,
    EFW_HAL_CUSTOM
} efw_hal_type_t;

typedef struct {
    const char *name;
    efw_hal_type_t type;
    uint8_t bus_id;
    void *ctx;
    efw_status_t (*init)(void *ctx);
    efw_status_t (*read)(void *ctx, void *buf, uint16_t len, uint16_t *actual);
    efw_status_t (*write)(void *ctx, const void *buf, uint16_t len, uint16_t *actual);
    efw_status_t (*ioctl)(void *ctx, uint32_t cmd, void *arg);
} efw_hal_ops_t;

efw_status_t efw_hal_registry_init(void);
efw_status_t efw_hal_register(const efw_hal_ops_t *ops);
efw_status_t efw_hal_get(const char *name, const efw_hal_ops_t **out_ops);
size_t efw_hal_count_by_type(efw_hal_type_t type);
efw_status_t efw_hal_init_device(const char *name);
efw_status_t efw_hal_read(const char *name, void *buf, uint16_t len, uint16_t *actual);
efw_status_t efw_hal_write(const char *name, const void *buf, uint16_t len, uint16_t *actual);
efw_status_t efw_hal_ioctl(const char *name, uint32_t cmd, void *arg);

#endif
