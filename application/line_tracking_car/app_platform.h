/**
 * @file    app_platform.h
 * @brief   应用平台层 —— 硬件平台 (HAL/SENSOR/ACTUATOR) 的注册接口
 *
 * 本文件是循迹小车应用的三层架构中的"平台层"头文件。
 *
 * =========================================================================
 * 应用架构 (三层分离)
 * =========================================================================
 *
 *   app_line_tracking_car  (应用层) — 业务逻辑：循迹控制循环
 *   app_components         (组件层) — 算法实例：PID 控制器
 *   app_platform           (平台层) — 硬件绑定：ADC/传感器/电机
 *
 *   三层分离的好处：
 *     - 平台层负责"这个板子有什么硬件"→ 换一块板子只改平台层
 *     - 组件层负责"用什么算法"→ 调 PID 参数只改组件层
 *     - 应用层负责"做什么"→ 改变控制策略只改应用层
 *
 * =========================================================================
 * 宏定义
 * =========================================================================
 *
 *   APP_LINE_CHANNELS = 5  — 循迹传感器通道数
 *     定义了本项目使用的循迹传感器有 5 路 (常见竞赛规格)
 *     如果换用 8 路传感器，只需改这里 (或通过 -D 覆写)
 */

#ifndef APP_PLATFORM_H
#define APP_PLATFORM_H

#include <stdint.h>
#include "efw/efw.h"
#include "app_board_config.h"


/**
 * @brief 注册平台层所有硬件组件
 *
 * 内部注册：输入 HAL "line_input" + 循迹传感器 "line_sensor_5ch"
 *           + 左电机 "left_motor" + 右电机 "right_motor"
 *
 * @return EFW_OK 全部注册成功, 否则返回第一个失败的错误码
 */
efw_status_t app_platform_register(void);

/**
 * @brief 设置模拟的 ADC 读数 (用于测试/仿真)
 *
 * 真实项目中 ADC 值由硬件 DMA 自动更新，此函数仅供仿真使用。
 *
 * @param values 5 个通道的模拟值数组 (长度 = APP_LINE_CHANNELS)
 */
void app_platform_set_line_state(const uint16_t values[APP_LINE_CHANNELS]);

#endif
