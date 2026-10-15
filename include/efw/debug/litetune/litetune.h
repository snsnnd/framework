#ifndef LITETUNE_H
#define LITETUNE_H

/*
 * LiteTune MCU 端统一门面。
 *
 * Usage:
 *   // 仅在一个编译单元中定义实现
 *   #define LITETUNE_IMPLEMENTATION
 *   #include "efw/debug/litetune/litetune.h"
 *
 *   // 其他编译单元只包含头文件
 *   #include "efw/debug/litetune/litetune.h"
 *
 * 中断驱动端口在编译 LiteTune 实现时，必须按 include/lt_config.h 的说明成对
 * 定义 LT_CRITICAL_ENTER/EXIT 临界区钩子。
 */

#include "include/lt_config.h"
#include "include/lt_common.h"
#include "include/lt_utils.h"
#include "include/lt_cobs.h"
#include "include/lt_frame.h"
#include "include/lt_state.h"
#include "include/lt_registry.h"
#include "include/lt_tx.h"
#include "include/lt_runtime.h"
#include "include/lt_init.h"
#include "include/lt_telemetry.h"
#include "include/lt_params.h"
#include "include/lt_cmd.h"
#include "include/lt_rx.h"
#include "include/lt_processor.h"

#endif /* LITETUNE_H */
