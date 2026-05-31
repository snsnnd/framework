/**
 * @file    app_platform.h
 * @brief   Simple Blink 示例平台适配层
 */

#ifndef SIMPLE_BLINK_APP_PLATFORM_H
#define SIMPLE_BLINK_APP_PLATFORM_H

#include "efw/efw.h"

efw_status_t app_platform_register(void);
float app_platform_last_led_level(void);

#endif
