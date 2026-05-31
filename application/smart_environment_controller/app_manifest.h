/**
 * @file    app_manifest.h
 * @brief   Smart Environment Controller 示例：多 HAL/传感器/算法/执行器/状态机应用清单
 */

#ifndef SMART_ENVIRONMENT_APP_MANIFEST_H
#define SMART_ENVIRONMENT_APP_MANIFEST_H

#define APP_USE_HAL                 1
#define APP_USE_SENSOR              1
#define APP_USE_ACTUATOR            1
#define APP_USE_ALGORITHM           1
#define APP_USE_MODULE              1
#define APP_USE_STATE_MACHINE       1
#define APP_USE_EVENT               1

#define APP_HAL_COUNT               3
#define APP_SENSOR_COUNT            3
#define APP_ACTUATOR_COUNT          2
#define APP_ALGO_COUNT              2
#define APP_MODULE_COUNT            2
#define APP_STATE_COUNT             3

#define APP_ENV_ADC_HAL_NAME        "env_adc"
#define APP_IMU_I2C_HAL_NAME        "imu_i2c"
#define APP_RELAY_GPIO_HAL_NAME     "relay_gpio"

#define APP_TEMP_SENSOR_NAME        "temperature_sensor"
#define APP_HUMIDITY_SENSOR_NAME    "humidity_sensor"
#define APP_IMU_SENSOR_NAME         "imu_sensor"

#define APP_TEMP_FILTER_NAME        "temperature_filter"
#define APP_ATTITUDE_FILTER_NAME    "attitude_filter"

#define APP_FAN_RELAY_NAME          "fan_relay"
#define APP_ALARM_LED_NAME          "alarm_led"

#define APP_SAMPLER_MODULE_NAME     "sampler_module"
#define APP_CONTROL_MODULE_NAME     "control_module"

#define APP_STATE_IDLE_NAME         "state_idle"
#define APP_STATE_COOLING_NAME      "state_cooling"
#define APP_STATE_FAULT_NAME        "state_fault"

#define APP_TOPIC_ENV_SAMPLE        1u
#define APP_TEMP_HIGH_C             30.0f
#define APP_TEMP_LOW_C              27.0f
#define APP_TILT_FAULT_DEG          35.0f

#endif
