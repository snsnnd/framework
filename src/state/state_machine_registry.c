/**
 * @file    state_machine_registry.c
 * @brief   StateMachine (状态机) 注册表实现
 *
 * 管理所有状态机实例的注册和查找。
 * 由 EFW_ENABLE_STATE_MACHINE 宏控制编译。
 *
 * =========================================================================
 * 状态机模型
 * =========================================================================
 *
 *   每个状态机实例代表一个状态 (而非整个状态图)。
 *   多个 efw_state_machine_ops_t 实例组合成完整的多状态状态机。
 *
 *   每个状态有三个回调：
 *     on_enter — 进入状态时调用一次 (初始化状态环境、启动动作)
 *     on_tick  — 状态保持期间周期性调用 (核心逻辑、检查转移条件) ← 必填
 *     on_exit  — 离开状态时调用一次 (清理、保存、释放资源)
 *
 *   状态转移由用户在上层 on_tick 中自行管理，框架不做自动转移。
 */

#include <string.h>
#include "efw/core/config.h"
#include "efw/state/state_machine.h"

#if EFW_ENABLE_STATE_MACHINE  /**< 编译开关 */

/** 状态机注册表——全局静态指针数组 */
static const efw_state_machine_ops_t *g_sms[EFW_MAX_STATE_MACHINES]; /**< SM ops 数组 */
static size_t g_sm_n;       /**< 已注册状态机数量 */

static int same_name(const char *a, const char *b) {
    return a && b && strcmp(a, b) == 0;
}

/* ====== 初始化 ====== */

efw_status_t efw_sm_registry_init(void) { g_sm_n = 0; return EFW_OK; }

/* ====== 注册 ====== */

efw_status_t efw_sm_register(const efw_state_machine_ops_t *ops) {
    if (!ops || !ops->name || !ops->on_tick) return EFW_ERR_INVALID;  /* on_tick 必填 */
    for (size_t i = 0; i < g_sm_n; ++i)
        if (same_name(g_sms[i]->name, ops->name))
            return EFW_ERR_ALREADY_EXISTS;                               /* 名称冲突 */
    if (g_sm_n >= EFW_MAX_STATE_MACHINES) return EFW_ERR_FULL;         /* 容量已满 */
    g_sms[g_sm_n++] = ops;                                               /* 存入 */
    return EFW_OK;
}

/* ====== 查找 ====== */

efw_status_t efw_sm_get(const char *name, const efw_state_machine_ops_t **out_ops) {
    if (!name || !out_ops) return EFW_ERR_INVALID;
    for (size_t i = 0; i < g_sm_n; ++i)
        if (same_name(g_sms[i]->name, name)) {
            *out_ops = g_sms[i];
            return EFW_OK;
        }
    return EFW_ERR_NOT_FOUND;
}

#endif /* EFW_ENABLE_STATE_MACHINE */
