#ifndef EFW_SENSOR_REGISTRY_H
#define EFW_SENSOR_REGISTRY_H

#include "efw_common.h"

typedef enum {
    EFW_SENSOR_LINE_TRACKING = 0,
    EFW_SENSOR_IMU,
    EFW_SENSOR_ENCODER,
    EFW_SENSOR_ULTRASONIC,
    EFW_SENSOR_CUSTOM
} efw_sensor_type_t;

typedef struct {
    const char *name;
    efw_sensor_type_t type;
    uint8_t channel_count; /* 例如 4 路/8 路循迹 */
    void *ctx;
    efw_status_t (*init)(void *ctx);
    efw_status_t (*read)(void *ctx, void *out);
} efw_sensor_ops_t;

efw_status_t efw_sensor_registry_init(void);
efw_status_t efw_sensor_register(const efw_sensor_ops_t *ops);
efw_status_t efw_sensor_get(const char *name, const efw_sensor_ops_t **out_ops);
size_t efw_sensor_count_by_type(efw_sensor_type_t type);

#endif
