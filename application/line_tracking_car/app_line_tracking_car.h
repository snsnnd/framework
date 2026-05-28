/**
 * @file    app_line_tracking_car.h
 * @brief   应用层 —— 循迹小车的主控制逻辑
 *
 * 本文件是三层架构中的"应用层"头文件，定义循迹小车整体的初始化和主循环。
 *
 * 职责：
 *   - app_line_tracking_car_init()  → 调用 efw_init + 平台层注册 + 组件层注册
 *   - app_line_tracking_car_loop_1ms() → 每 1ms 执行一次完整的循迹控制链路
 *
 * =========================================================================
 * 完整初始化顺序
 * =========================================================================
 *
 *   efw_init()                         ← 初始化 7 个注册表
 *   app_platform_register()            ← 注册 ADC + 传感器 + 电机
 *   app_components_register()          ← 注册 PID 算法
 *
 * =========================================================================
 * 主循环控制链路 (每 1ms)
 * =========================================================================
 *
 *   使用框架内置的高层函数 efw_line_tracking_follow_diff() 一步完成：
 *     → 读取 5 通道循迹传感器数据
 *     → 计算加权误差 (weights = {-2,-1,0,1,2})
 *     → PID 运算 (setpoint=0, dt=1ms)
 *     → 差速驱动左右电机 (base_speed=45)
 *
 *   这个函数将 "感知→计算→决策→执行" 封装为一次调用，极大简化了应用层代码。
 */

#ifndef APP_LINE_TRACKING_CAR_H
#define APP_LINE_TRACKING_CAR_H

#include "efw/efw.h"

/**
 * @brief 循迹小车初始化 —— 按顺序初始化框架、平台和组件
 *
 * @return EFW_OK 全部成功, 否则返回第一个失败的错误码
 */
efw_status_t app_line_tracking_car_init(void);

/**
 * @brief 循迹小车主循环 —— 1ms 周期执行完整的感知→决策→执行链路
 *
 * ★ 嵌入式项目中应在 1ms 定时器中断中调用此函数。
 *
 * @return EFW_OK 成功, 否则返回错误码
 */
efw_status_t app_line_tracking_car_loop_1ms(void);

#endif
