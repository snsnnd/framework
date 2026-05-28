/**
 * @file    init.c
 * @brief   EFW 框架统一初始化入口 efw_init()
 *
 * 本文件只有一个函数 efw_init()，按依赖顺序初始化全部已启用的注册表。
 *
 * =========================================================================
 * 初始化顺序（精心设计、不可随意调换）
 * =========================================================================
 *
 *   ① HAL           — 最底层硬件抽象，其他层依赖它
 *   ② COMM          — 在 HAL 之上封装协议，SENSOR/ACTUATOR 可能绑定
 *   ③ MODULE        — 在设备层之前，模块 init 可能注册子组件
 *   ④ SENSOR        — 可能引用 HAL/COMM (hal_name/comm_name 绑定校验)
 *   ⑤ ACTUATOR      — 同上
 *   ⑥ ALGORITHM     — 独立，无 HAL/COMM 依赖
 *   ⑦ STATE_MACHINE — 通常依赖所有上述层就绪
 *
 * =========================================================================
 * 条件编译：每个步骤包裹在 #if EFW_ENABLE_* 中
 * =========================================================================
 *
 *   禁用的模块不参与编译。当所有 EFW_ENABLE_* 都为 0 时，efw_init()
 *   简化为 "return EFW_OK;"。EFW_UNUSED(s) 用于消除此时的编译警告。
 *
 * =========================================================================
 * 失败策略：Fail-Fast
 * =========================================================================
 *
 *   任一步失败立即返回，不继续后续初始化。
 *   这是正确的选择——如果 HAL 初始化失败，后续 COMM 注册必然失败，
 *   与其级联失败不如第一时间报错。
 */

#include "efw/efw.h"

efw_status_t efw_init(void) {
    efw_status_t s;            /* 暂存每步 _init 的返回值 */
    EFW_UNUSED(s);             /* 防止 "unused variable" 警告 (所有开关=0 时触发) */

/* 第1步：HAL —— 最底层，必须最先 */
#if EFW_ENABLE_HAL
    s = efw_hal_registry_init();      /* 清空 HAL 注册表 (g_hal_n=0) */
    if (s != EFW_OK) return s;
#endif

/* 第2步：COMM —— 依赖 HAL (注册时校验 hal_name) */
#if EFW_ENABLE_COMM
    s = efw_comm_registry_init();     /* 清空 COMM 注册表 */
    if (s != EFW_OK) return s;
#endif

/* 第3步：MODULE —— 在设备/算法之前 (模块 init 可能注册子组件) */
#if EFW_ENABLE_MODULE
    s = efw_module_registry_init();   /* 清空 MODULE 注册表 */
    if (s != EFW_OK) return s;
#endif

/* 第4步：SENSOR —— 依赖 HAL/COMM */
#if EFW_ENABLE_SENSOR
    s = efw_sensor_registry_init();   /* 清空 SENSOR 注册表 */
    if (s != EFW_OK) return s;
#endif

/* 第5步：ACTUATOR —— 依赖 HAL/COMM */
#if EFW_ENABLE_ACTUATOR
    s = efw_actuator_registry_init(); /* 清空 ACTUATOR 注册表 */
    if (s != EFW_OK) return s;
#endif

/* 第6步：ALGORITHM —— 独立，无 IO 依赖 */
#if EFW_ENABLE_ALGORITHM
    s = efw_algo_registry_init();     /* 清空 ALGO 注册表 */
    if (s != EFW_OK) return s;
#endif

/* 第7步：STATE_MACHINE —— 最后初始化 */
#if EFW_ENABLE_STATE_MACHINE
    s = efw_sm_registry_init();       /* 清空 SM 注册表 */
    if (s != EFW_OK) return s;
#endif

    return EFW_OK;
}
