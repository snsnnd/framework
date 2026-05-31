/**
 * @file    app_components.c
 * @brief   Simple Blink 示例业务层：注册一个周期翻转 LED 的 module
 */

#include "app_components.h"

#include "app_manifest.h"

typedef struct {
    uint32_t tick;
    uint8_t led_on;
} app_blink_ctx_t;

static app_blink_ctx_t g_blink_ctx;

static efw_status_t blink_poll(void *ctx) {
    app_blink_ctx_t *blink = (app_blink_ctx_t *)ctx;
    efw_actuator_cmd_t cmd;

    if (!blink) return EFW_ERR_INVALID;
    blink->tick++;
    if ((blink->tick % APP_BLINK_PERIOD_TICKS) != 0u) return EFW_OK;

    blink->led_on = (uint8_t)!blink->led_on;
    cmd.value = blink->led_on ? 1.0f : 0.0f;
    return efw_actuator_write(APP_STATUS_LED_NAME, &cmd);
}

static efw_module_ops_t g_blink_module = {
    .name = APP_BLINK_MODULE_NAME,
    .type = EFW_MODULE_APP,
    .ctx = &g_blink_ctx,
    .poll = blink_poll,
};

efw_status_t app_components_register(void) {
    return efw_module_register(&g_blink_module);
}
