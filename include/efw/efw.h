#ifndef EFW_H
#define EFW_H

#include "efw/core/common.h"
#include "efw/core/config.h"
#include "efw/core/diagnostic.h"
#include "efw/core/registry.h"
#include "efw/core/ds.h"
#include "efw/app/runtime.h"
#if EFW_ENABLE_EVENT
#include "efw/core/event.h"
#endif
#if EFW_ENABLE_SCHEDULER
#include "efw/core/scheduler.h"
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

efw_status_t efw_init(void);

#endif
