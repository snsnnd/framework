/**
 * @file    app_manifest.h
 * @brief   Simple Blink 示例：最小 HAL + Actuator + Module 应用清单
 */

#ifndef SIMPLE_BLINK_APP_MANIFEST_H
#define SIMPLE_BLINK_APP_MANIFEST_H

#define APP_USE_HAL                 1
#define APP_USE_ACTUATOR            1
#define APP_USE_MODULE              1

#define APP_HAL_COUNT               1
#define APP_ACTUATOR_COUNT          1
#define APP_MODULE_COUNT            1

#define APP_LED_GPIO_HAL_NAME       "led_gpio"
#define APP_STATUS_LED_NAME         "status_led"
#define APP_BLINK_MODULE_NAME       "blink_module"

#define APP_BLINK_PERIOD_TICKS      250u

#endif
