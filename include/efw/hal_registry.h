#ifndef EFW_HAL_REGISTRY_H
#define EFW_HAL_REGISTRY_H

#include "efw_common.h"
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
    const char *name;         /* 例如 uart1, i2c2, spi1 */
    efw_hal_type_t type;
    uint8_t bus_id;           /* 总线/外设编号 */
    void *ctx;                /* BSP 句柄 */
    efw_status_t (*init)(void *ctx);
    efw_status_t (*read)(void *ctx, void *buf, uint16_t len, uint16_t *actual);
    efw_status_t (*write)(void *ctx, const void *buf, uint16_t len, uint16_t *actual);
    efw_status_t (*ioctl)(void *ctx, uint32_t cmd, void *arg);
} efw_hal_ops_t;

efw_status_t efw_hal_registry_init(void);
efw_status_t efw_hal_register(const efw_hal_ops_t *ops);
efw_status_t efw_hal_get(const char *name, const efw_hal_ops_t **out_ops);
size_t efw_hal_count_by_type(efw_hal_type_t type);

#endif
