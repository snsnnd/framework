/**
 * @file    main.c
 * @brief   Smart Environment Controller 示例入口：模拟温度升高和倾斜故障
 */

#include "app_bootstrap.h"
#include "app_platform.h"

int main(void) {
    efw_imu_data_t tilted = { .ay = 0.8f, .az = 0.6f };
    const app_env_sample_t *sample;

    if (app_init() != EFW_OK) return 1;

    app_platform_set_temperature(31.5f);
    for (uint16_t i = 0; i < 120u; ++i) {
        if (app_loop_1ms() != EFW_OK) return 2;
    }
    if (!app_platform_fan_is_on()) return 3;

    app_platform_set_imu(&tilted);
    for (uint16_t i = 0; i < 20u; ++i) {
        if (app_loop_1ms() != EFW_OK) return 4;
    }
    if (!app_platform_alarm_is_on()) return 5;

    sample = app_current_sample();
    return sample && sample->state == APP_ENV_STATE_FAULT ? 0 : 6;
}
