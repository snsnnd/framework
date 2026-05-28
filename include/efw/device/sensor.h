#ifndef EFW_SENSOR_REGISTRY_H
#define EFW_SENSOR_REGISTRY_H

#include "efw/core/common.h"
#include "efw/hal/hal.h"
#include "efw/comm/comm.h"

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
    uint8_t channel_count;
    const char *hal_name;
    const char *comm_name;
    void *ctx;
    efw_status_t (*init)(void *ctx);
    efw_status_t (*read)(void *ctx, void *out);
} efw_sensor_ops_t;

efw_status_t efw_sensor_registry_init(void);
efw_status_t efw_sensor_register(const efw_sensor_ops_t *ops);
efw_status_t efw_sensor_get(const char *name, const efw_sensor_ops_t **out_ops);
size_t efw_sensor_count_by_type(efw_sensor_type_t type);
efw_status_t efw_sensor_bind_hal(const char *sensor_name, const efw_hal_ops_t **out_hal);
efw_status_t efw_sensor_bind_comm(const char *sensor_name, const efw_comm_ops_t **out_comm);
efw_status_t efw_sensor_init_device(const char *name);
efw_status_t efw_sensor_read(const char *name, void *out);

#endif
