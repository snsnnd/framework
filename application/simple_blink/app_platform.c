/**
 * @file    app_platform.c
 * @brief   Simple Blink 示例平台层：用 GPIO HAL 和 LED Actuator 模拟一颗状态灯
 */

#include "app_platform.h"

#include "app_manifest.h"

typedef struct {
    float level;
} app_led_ctx_t;

static app_led_ctx_t g_led_ctx;

static efw_status_t led_gpio_write(void *ctx, const void *buf, uint16_t len, uint16_t *actual) {
    app_led_ctx_t *led = (app_led_ctx_t *)ctx;
    const float *level = (const float *)buf;

    if (!led || !level || len < sizeof(float)) return EFW_ERR_INVALID;
    led->level = *level;
    if (actual) *actual = (uint16_t)sizeof(float);
    return EFW_OK;
}

static efw_status_t status_led_write(void *ctx, const void *cmd) {
    app_led_ctx_t *led = (app_led_ctx_t *)ctx;
    const efw_actuator_cmd_t *led_cmd = (const efw_actuator_cmd_t *)cmd;

    if (!led || !led_cmd) return EFW_ERR_INVALID;
    return efw_hal_write(APP_LED_GPIO_HAL_NAME, &led_cmd->value, (uint16_t)sizeof(led_cmd->value), 0);
}

static efw_hal_ops_t g_led_gpio_hal = {
    .name = APP_LED_GPIO_HAL_NAME,
    .type = EFW_HAL_GPIO,
    .bus_id = 1,
    .ctx = &g_led_ctx,
    .write = led_gpio_write,
};

static efw_actuator_ops_t g_status_led = {
    .name = APP_STATUS_LED_NAME,
    .type = EFW_ACTUATOR_LED,
    .hal_name = APP_LED_GPIO_HAL_NAME,
    .ctx = &g_led_ctx,
    .write = status_led_write,
};

efw_status_t app_platform_register(void) {
    efw_status_t s = efw_hal_register(&g_led_gpio_hal);
    if (s != EFW_OK) return s;
    return efw_actuator_register(&g_status_led);
}

float app_platform_last_led_level(void) {
    return g_led_ctx.level;
}
