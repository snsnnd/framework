/**
 * @file    state_machine.h
 * @brief   State Machine (状态机层) 注册表接口
 *
 * 本层提供简单的状态机抽象。每个状态机代表一个状态，包含三个回调：
 *
 *   on_enter — 进入该状态时调用一次（初始化状态环境、启动动作）
 *   on_tick  — 状态保持期间周期性调用（核心逻辑：检查转移条件、执行持续动作）
 *   on_exit  — 离开该状态时调用一次（清理资源、保存数据）
 *
 * 这是基本的状态单元，上层需要在 on_tick 中自行维护状态转移图。
 * 框架只提供状态实例的管理，不提供自动状态转移引擎。
 * 多态组合（多个 efw_state_machine_ops_t 实例）可构成完整的状态机。
 *
 * 典型使用模式：
 *   定义一个枚举表示所有状态 (STATE_IDLE, STATE_RUNNING, STATE_ERROR...)
 *   在主循环中根据 current_state 调用对应状态机的 on_tick，
 *   在 on_tick 中判断转移条件并切换 current_state。
 */

#ifndef EFW_STATE_MACHINE_REGISTRY_H
#define EFW_STATE_MACHINE_REGISTRY_H

#include "efw/core/common.h"

/**
 * @brief 状态机操作接口结构体（每个实例代表一个状态）
 *
 * @field name     全局唯一名称 (如 "state_idle", "state_running", "state_error")
 * @field ctx      用户私有上下文 (如指向完整状态机管理器的指针)
 * @field on_enter 进入状态回调 (可空)：状态转移进入时调用一次
 * @field on_tick  状态保持回调 (必填，注册时校验)：在状态内周期性执行
 * @field on_exit  离开状态回调 (可空)：状态转出时调用一次，用于清理
 */
typedef struct {
    const char *name;       /**< 全局唯一名称 */
    void *ctx;              /**< 用户私有上下文 */
    efw_status_t (*on_enter)(void *ctx); /**< 进入状态回调 (可空) */
    efw_status_t (*on_tick)(void *ctx);  /**< 状态保持回调 (必填) */
    efw_status_t (*on_exit)(void *ctx);  /**< 离开状态回调 (可空) */
} efw_state_machine_ops_t;

/* ====== 状态机注册表 API ====== */

efw_status_t efw_sm_registry_init(void);
efw_status_t efw_sm_register(const efw_state_machine_ops_t *ops);
efw_status_t efw_sm_get(const char *name, const efw_state_machine_ops_t **out_ops);

#endif
