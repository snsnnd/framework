/**
 * @file    app_bootstrap.c
 * @brief   循迹小车应用 glue code：连接通用 runtime 与本应用 manifest
 */

#include "app_bootstrap.h"

#include "app_components.h"
#include "app_manifest.h"
#include "app_platform.h"
#include "efw/app/runtime.h"

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

static efw_line_follower_t g_line_follower;
static const float g_line_weights[APP_LINE_CHANNELS] = { -2.0f, -1.0f, 0.0f, 1.0f, 2.0f };

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

    return EFW_OK;
}

static efw_status_t app_bind_handles(void) {
    const efw_line_follower_config_t config = {
        .sensor_name = APP_LINE_SENSOR_NAME,
        .pid_name = APP_LINE_PID_NAME,
        .left_motor = APP_LEFT_MOTOR_NAME,
        .right_motor = APP_RIGHT_MOTOR_NAME,
        .weights = g_line_weights,
        .base_speed = APP_LINE_BASE_SPEED,
        .min_speed = APP_LINE_MIN_SPEED,
        .max_speed = APP_LINE_MAX_SPEED,
        .dt = APP_LINE_DT_SECONDS,
        .active_value = APP_LINE_ACTIVE_VALUE,
        .binary_mode = APP_LINE_FOLLOWER_BINARY,
    };

    return efw_line_follower_bind_config(&g_line_follower, &config);
}

static efw_status_t app_update_1ms(void) {
    return efw_line_follower_update(&g_line_follower, 0, 0);
}

static const efw_app_manifest_t g_app_manifest = {
    .init_pools = app_init_pools,
    .register_platform = app_platform_register,
    .register_components = app_components_register,
    .bind_handles = app_bind_handles,
    .update_1ms = app_update_1ms,
};

efw_status_t app_init(void) {
    return efw_app_init(&g_app_manifest);
}

efw_status_t app_loop_1ms(void) {
    return efw_app_update_1ms(&g_app_manifest);
}
