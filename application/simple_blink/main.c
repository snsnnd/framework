/**
 * @file    main.c
 * @brief   Simple Blink 示例入口：运行 250 个 1ms tick，观察 LED 状态被翻转
 */

#include "app_bootstrap.h"
#include "app_platform.h"

int main(void) {
    if (app_init() != EFW_OK) return 1;

    for (uint16_t i = 0; i < 250u; ++i) {
        if (app_loop_1ms() != EFW_OK) return 2;
    }

    return app_platform_last_led_level() > 0.5f ? 0 : 3;
}
