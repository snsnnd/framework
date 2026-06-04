/**
 * @file    app_bootstrap.c
 * @brief   Generated runtime glue, flow bind, and 1 ms scheduler.
 */

#include "app_bootstrap.h"

#include "app_components.h"
#include "app_manifest.h"
#include "app_platform.h"
#include "efw/app/runtime.h"
#include <string.h>

#if APP_USE_HAL
static const efw_hal_ops_t *g_hal_pool[APP_HAL_COUNT];
#endif
#if APP_USE_SENSOR
static const efw_sensor_ops_t *g_sensor_pool[APP_SENSOR_COUNT];
#endif
#if APP_USE_ACTUATOR
static const efw_actuator_ops_t *g_actuator_pool[APP_ACTUATOR_COUNT];
#endif
#if APP_USE_ALGORITHM
static const efw_algo_ops_t *g_algo_pool[APP_ALGO_COUNT];
#endif
#if APP_USE_MODULE
static const efw_module_ops_t *g_module_pool[APP_MODULE_COUNT];
#endif

static uint32_t g_app_elapsed_ms;
static const char *g_app_event_name;
static uint16_t g_app_event_topic_id;
static const void *g_app_event_data;
static uint16_t g_app_event_size;

#define APP_EVENT_QUEUE_CAPACITY 8u
typedef struct {
    const char *event_name;
    uint16_t topic_id;
    const void *data;
    uint16_t size;
} app_pending_event_t;

static app_pending_event_t g_app_event_queue[APP_EVENT_QUEUE_CAPACITY];
static uint8_t g_app_event_head;
static uint8_t g_app_event_tail;
static uint8_t g_app_event_count;

typedef union {
    uint8_t raw[APP_DATAFLOW_BUFFER_SIZE];
    float align_f;
    uint32_t align_u32;
    void *align_ptr;
} app_dataflow_buffer_t;

$CONTRACT_SIZE_CHECKS$STATE_LOGIC_BLOCKS$DATAFLOW_PIPELINES$LINE_FOLLOWER_DEFS$PUBLISHER_RUNTIME$EXTERNS
static efw_status_t app_init_pools(void) {
    efw_status_t s;
#if APP_USE_HAL
    s = efw_hal_registry_init_pool(g_hal_pool, APP_HAL_COUNT);
    if (s != EFW_OK) return s;
#endif
#if APP_USE_SENSOR
    s = efw_sensor_registry_init_pool(g_sensor_pool, APP_SENSOR_COUNT);
    if (s != EFW_OK) return s;
#endif
#if APP_USE_ACTUATOR
    s = efw_actuator_registry_init_pool(g_actuator_pool, APP_ACTUATOR_COUNT);
    if (s != EFW_OK) return s;
#endif
#if APP_USE_ALGORITHM
    s = efw_algo_registry_init_pool(g_algo_pool, APP_ALGO_COUNT);
    if (s != EFW_OK) return s;
#endif
#if APP_USE_MODULE
    s = efw_module_registry_init_pool(g_module_pool, APP_MODULE_COUNT);
    if (s != EFW_OK) return s;
#endif
    return EFW_OK;
}

$BIND_HANDLES$SCHEDULER_RUNTIME
static const efw_app_manifest_t g_app_manifest = {
    .init_pools = app_init_pools,
    .register_platform = app_platform_register,
    .register_components = app_components_register,
    .bind_handles = app_bind_handles,
    .update_1ms = app_update_1ms,
};

efw_status_t app_init(void) {
    efw_status_t s = efw_app_init(&g_app_manifest);
    if (s != EFW_OK) return s;
#if APP_USE_MODULE
    s = efw_module_init_all();
    if (s != EFW_OK) return s;
    s = efw_module_start_all();
    if (s != EFW_OK) return s;
#endif
    return EFW_OK;
}

efw_status_t app_loop_tick(void) {
    return efw_app_update_1ms(&g_app_manifest);
}

efw_status_t app_loop_1ms(void) {
    return app_loop_tick();
}

$EVENT_QUEUE_RUNTIME
efw_status_t app_poll_forever(void) {
    for (;;) {
        efw_status_t s = app_loop_tick();
        if (s != EFW_OK) return s;
    }
}

efw_status_t app_main(void) {
    efw_status_t s = app_init();
    if (s != EFW_OK) return s;
    return app_poll_forever();
}
