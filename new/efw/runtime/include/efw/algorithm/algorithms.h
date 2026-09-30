/**
 * @file    algorithms.h
 * @brief   内置算法分发头文件
 *
 * 本文件本身不定义任何算法结构或函数，只做条件分发：
 *   - 若 EFW_ENABLE_ALGO_PID=1      → 引入 efw/algorithm/control/pid.h
 *   - 若 EFW_ENABLE_ALGO_MOVING_AVG=1 → 引入 efw/algorithm/filter/moving_average.h
 *
 * 这样做的好处：
 *   用户只需 #include "efw/algorithm/algorithms.h" 即可获得所有启用的内置算法，
 *   不需要关心每个算法具体在哪个子目录中。
 *
 * 添加新算法时：
 *   ① 在 efw/algorithm/<类别>/ 下创建 xxx.h 和对应的 src/algorithm/<类别>/xxx.c
 *   ② 在 config.h 中新增 EFW_ENABLE_ALGO_XXX 开关
 *   ③ 在本文件中添加对应的 #if / #include
 */

#ifndef EFW_ALGORITHMS_H
#define EFW_ALGORITHMS_H

#include "efw/core/config.h"

#if EFW_ENABLE_ALGO_PID
#include "efw/algorithm/control/pid.h"        /**< PID 控制器 (位置式并行PID) */
#endif

#if EFW_ENABLE_ALGO_MOVING_AVG
#include "efw/algorithm/filter/moving_average.h" /**< 滑动均值滤波器 (O(1) 环形缓冲) */
#endif

#if EFW_ENABLE_ALGO_LOW_PASS
#include "efw/algorithm/filter/low_pass.h"
#endif

#if EFW_ENABLE_ALGO_RAMP
#include "efw/algorithm/control/ramp.h"
#endif

#if EFW_ENABLE_ALGO_ENCODER_SPEED
#include "efw/algorithm/estimator/encoder_speed.h"
#endif

#if EFW_ENABLE_ALGO_ATTITUDE_COMPLEMENTARY
#include "efw/algorithm/estimator/attitude_complementary.h"
#endif

#endif
