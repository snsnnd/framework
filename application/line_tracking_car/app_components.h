/**
 * @file    app_components.h
 * @brief   应用组件层 —— 算法实例 (PID 控制器) 的注册接口
 *
 * 本文件是循迹小车三层架构中的"组件层"头文件。
 *
 * 组件层负责：
 *   - 创建和配置算法实例 (PID)
 *   - 注册算法到框架注册表
 *
 * 与平台层的区别：
 *   平台层注册的是"硬件相关"的东西 (HAL/传感器/执行器)
 *   组件层注册的是"纯算法"的东西 (PID/滤波器等)
 *
 * 分离的好处：
 *   如果想换用不同的控制算法 (如模糊控制替代 PID)，
 *   只需要修改本文件——平台层和应用层不受影响。
 */

#ifndef APP_COMPONENTS_H
#define APP_COMPONENTS_H

#include "efw/efw.h"

/**
 * @brief 注册组件层所有算法实例
 *
 * 内部注册：PID 控制器 "line_pid" (Kp=18, Ki=0, Kd=2.5, 限幅±60)
 *
 * @return EFW_OK 注册成功, 否则返回错误码
 */
efw_status_t app_components_register(void);

#endif
