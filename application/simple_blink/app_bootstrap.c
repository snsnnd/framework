/**
 * @file    app_bootstrap.c
 * @brief   Simple Blink 示例 glue code：连接通用 runtime 与应用清单
 */

#include "app_bootstrap.h"

#include "app_components.h"
#include "app_manifest.h"
#include "app_platform.h"
#include "efw/app/runtime.h"

static const efw_hal_ops_t *g_hal_pool[APP_HAL_COUNT];
static const efw_actuator_ops_t *g_actuator_pool[APP_ACTUATOR_COUNT];

static efw_status_t app_init_pools(void) {
    efw_status_t s = efw_hal_registry_init_pool(g_hal_pool, APP_HAL_COUNT);
    if (s != EFW_OK) return s;
    return efw_actuator_registry_init_pool(g_actuator_pool, APP_ACTUATOR_COUNT);
}

static efw_status_t app_bind_handles(void) {
    efw_status_t s = efw_actuator_init_device(APP_STATUS_LED_NAME);
    if (s != EFW_OK) return s;
    s = efw_actuator_enable(APP_STATUS_LED_NAME);
    if (s != EFW_OK) return s;
    s = efw_module_init_all();
    if (s != EFW_OK) return s;
    return efw_module_start_all();
}

static efw_status_t app_update_1ms(void) {
    return efw_module_poll_all();
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
