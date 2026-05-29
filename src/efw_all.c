/**
 * @file    efw_all.c
 * @brief   Keil/裸机聚合编译入口：只添加本文件，由 EFW_ENABLE_* 宏裁剪模块
 *
 * CMake 工程不使用本文件，仍按源码列表编译。Keil 用户可以只把本文件加入工程，
 * 然后在工程宏定义里关闭不用的 EFW_ENABLE_*，未启用模块不会进入编译单元。
 */

#include "core/init.c"
#include "core/diagnostic.c"
#include "app/runtime.c"
#include "debug/pid_scope.c"

#if EFW_ENABLE_EVENT
#include "core/event.c"
#endif

#if EFW_ENABLE_HAL
#define same_name efw_hal_same_name
#include "hal/hal_registry.c"
#undef same_name
#endif

#if EFW_ENABLE_COMM
#define same_name efw_comm_same_name
#include "comm/comm_registry.c"
#undef same_name
#endif

#if EFW_ENABLE_MODULE
#define same_name efw_module_same_name
#include "module/module_registry.c"
#undef same_name
#endif

#if EFW_ENABLE_SENSOR
#define same_name efw_sensor_same_name
#include "device/sensor_registry.c"
#undef same_name
#if EFW_ENABLE_SENSOR_LINE_TRACKING
#include "device/sensor/line_tracking.c"
#endif
#if EFW_ENABLE_SENSOR_IMU
#include "device/sensor/imu.c"
#endif
#if EFW_ENABLE_SENSOR_ENCODER
#include "device/sensor/encoder.c"
#endif
#if EFW_ENABLE_SENSOR_ULTRASONIC
#include "device/sensor/ultrasonic.c"
#endif
#if EFW_ENABLE_SENSOR_CUSTOM
#include "device/sensor/custom.c"
#endif
#endif

#if EFW_ENABLE_ACTUATOR
#define same_name efw_actuator_same_name
#include "device/actuator_registry.c"
#undef same_name
#if EFW_ENABLE_ACTUATOR_MOTOR
#define clamp_float efw_motor_clamp_float
#include "device/actuator/motor.c"
#undef clamp_float
#endif
#endif

#if EFW_ENABLE_ALGORITHM
#define same_name efw_algo_same_name
#include "algorithm/algorithm_registry.c"
#undef same_name
#endif

#if EFW_ENABLE_ALGO_PID
#define clamp_float efw_pid_clamp_float
#include "algorithm/control/pid.c"
#undef clamp_float
#endif

#if EFW_ENABLE_ALGO_MOVING_AVG
#include "algorithm/filter/moving_average.c"
#endif

#if EFW_ENABLE_ALGO_LOW_PASS
#include "algorithm/filter/low_pass.c"
#endif

#if EFW_ENABLE_ALGO_RAMP
#include "algorithm/control/ramp.c"
#endif

#if EFW_ENABLE_ALGO_ENCODER_SPEED
#include "algorithm/estimator/encoder_speed.c"
#endif

#if EFW_ENABLE_ALGO_ATTITUDE_COMPLEMENTARY
#include "algorithm/estimator/attitude_complementary.c"
#endif

#if EFW_ENABLE_STATE_MACHINE
#define same_name efw_state_machine_same_name
#include "state/state_machine_registry.c"
#undef same_name
#endif
