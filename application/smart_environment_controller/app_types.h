/**
 * @file    app_types.h
 * @brief   Smart Environment Controller 示例共享数据结构
 */

#ifndef SMART_ENVIRONMENT_APP_TYPES_H
#define SMART_ENVIRONMENT_APP_TYPES_H

#include "efw/efw.h"

typedef enum {
    APP_ENV_STATE_IDLE = 0,
    APP_ENV_STATE_COOLING,
    APP_ENV_STATE_FAULT,
} app_env_state_t;

typedef struct {
    float temperature_c;
    float humidity_pct;
    efw_imu_data_t imu;
    efw_attitude_output_t attitude;
    app_env_state_t state;
    uint8_t fan_on;
    uint8_t alarm_on;
} app_env_sample_t;

#endif
