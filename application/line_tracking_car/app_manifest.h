/**
 * @file    app_manifest.h
 * @brief   循迹小车应用清单：统一决定启用功能、容量、注册名称和控制参数
 *
 * 应用代码只改这个清单和 app_board_config.h，不需要手动声明 registry pool
 * 或 line follower handle。app_bootstrap.c 会根据这些宏完成初始化、注册和绑定。
 */

#ifndef APP_MANIFEST_H
#define APP_MANIFEST_H

#include "app_board_config.h"

/* ====== 功能清单：用于 CMake/Keil 宏和应用运行时初始化 ====== */

#define APP_USE_HAL                 1
#define APP_USE_SENSOR              1
#define APP_USE_LINE_TRACKING       1
#define APP_USE_ACTUATOR            1
#define APP_USE_MOTOR               1
#define APP_USE_ALGORITHM           1
#define APP_USE_PID                 1

/* ====== 应用实际容量：app_bootstrap.c 据此分配最小 pool ====== */

#define APP_HAL_COUNT               1
#define APP_SENSOR_COUNT            1
#define APP_ACTUATOR_COUNT          2
#define APP_ALGO_COUNT              1

/* ====== 注册名称：字符串只在注册和 bind 阶段使用 ====== */

#define APP_LINE_INPUT_HAL_NAME     "line_input"
#define APP_LINE_SENSOR_NAME        "line_sensor_5ch"
#define APP_LINE_PID_NAME           "line_pid"
#define APP_LEFT_MOTOR_NAME         "left_motor"
#define APP_RIGHT_MOTOR_NAME        "right_motor"

/* ====== 控制策略：正式控制循环通过 handle update，不做字符串查找 ====== */

#define APP_LINE_FOLLOWER_BINARY    1

#endif
