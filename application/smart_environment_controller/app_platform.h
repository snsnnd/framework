/**
 * @file    app_platform.h
 * @brief   Smart Environment Controller 示例平台适配层
 */

#ifndef SMART_ENVIRONMENT_APP_PLATFORM_H
#define SMART_ENVIRONMENT_APP_PLATFORM_H

#include "app_types.h"

efw_status_t app_platform_register(void);
void app_platform_set_temperature(float temperature_c);
void app_platform_set_humidity(float humidity_pct);
void app_platform_set_imu(const efw_imu_data_t *imu);
uint8_t app_platform_fan_is_on(void);
uint8_t app_platform_alarm_is_on(void);

#endif
