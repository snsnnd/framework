#ifndef EFW_H
#define EFW_H

/**
 * @file efw.h
 * @brief EFW 面向应用的聚合入口。
 *
 * 这里按 config.h 的编译开关选择性引入各层公共 API。应用通常只需包含
 * 本文件；底层库和单元测试也可以直接包含具体模块头文件，以减少依赖。
 */

#include "efw/core/common.h"
#include "efw/core/config.h"
#include "efw/core/diagnostic.h"
#include "efw/core/registry.h"
#include "efw/core/ds.h"
#include "efw/core/pool.h"
#include "efw/app/runtime.h"
#if EFW_ENABLE_EVENT
#include "efw/core/event.h"
#endif
#if EFW_ENABLE_SCHEDULER
#include "efw/core/scheduler.h"
#endif

#if EFW_ENABLE_DEBUG
#include "efw/debug/efw_debug.h"
#if EFW_ENABLE_DEBUG_FAST
#include "efw/debug/efw_debug_fast.h"
#endif
#if EFW_ENABLE_DEBUG_ASYNC
#include "efw/debug/efw_debug_async.h"
#endif
#if EFW_ENABLE_DEBUG_RUNTIME
#include "efw/debug/efw_debug_runtime.h"
#endif
#endif

#if EFW_ENABLE_DEBUG && EFW_ENABLE_LITETUNE
#include "efw/debug/efw_debug_litetune.h"
#endif

#if EFW_ENABLE_HAL
#include "efw/hal/hal.h"
#endif

#if EFW_ENABLE_COMM
#include "efw/comm/comm.h"
#endif

#if EFW_ENABLE_MODULE
#include "efw/module/module.h"
#endif

#if EFW_ENABLE_SENSOR
#include "efw/device/sensor.h"
#if EFW_ENABLE_SENSOR_LINE_TRACKING
#include "efw/device/sensor/line_tracking.h"
#endif
#if EFW_ENABLE_SENSOR_IMU
#include "efw/device/sensor/imu.h"
#endif
#if EFW_ENABLE_SENSOR_ENCODER
#include "efw/device/sensor/encoder.h"
#endif
#if EFW_ENABLE_SENSOR_ULTRASONIC
#include "efw/device/sensor/ultrasonic.h"
#endif
#if EFW_ENABLE_SENSOR_CUSTOM
#include "efw/device/sensor/custom.h"
#endif
#endif

#if EFW_ENABLE_ACTUATOR
#include "efw/device/actuator.h"
#if EFW_ENABLE_ACTUATOR_MOTOR
#include "efw/device/actuator/motor.h"
#endif
#endif

#if EFW_ENABLE_ALGORITHM
#include "efw/algorithm/registry.h"
#endif

#if EFW_ENABLE_ALGO_PID || EFW_ENABLE_ALGO_MOVING_AVG || EFW_ENABLE_ALGO_LOW_PASS || EFW_ENABLE_ALGO_RAMP || EFW_ENABLE_ALGO_ENCODER_SPEED || EFW_ENABLE_ALGO_ATTITUDE_COMPLEMENTARY
#include "efw/algorithm/algorithms.h"
#endif

#if EFW_ENABLE_STATE_MACHINE
#include "efw/state/state_machine.h"
#endif

/**
 * @brief 初始化 EFW 全局注册表和核心服务。
 *
 * 初始化顺序体现层次依赖：HAL -> COMM -> MODULE/SENSOR/ACTUATOR/ALGORITHM
 * -> STATE MACHINE -> EVENT -> SCHEDULER。函数只清空框架状态，不注册任何
 * 用户对象；用户应在其后按依赖顺序执行注册和绑定。
 */
efw_status_t efw_init(void);

#endif
