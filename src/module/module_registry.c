/**
 * @file    module_registry.c
 * @brief   Module (模块生命周期层) 注册表实现
 *
 * 管理模块的完整生命周期 (init→start→poll→stop)，
 * 提供单模块操作和批量操作 (init_all/start_all/poll_all)。
 * 由 EFW_ENABLE_MODULE 宏控制编译。
 *
 * =========================================================================
 * 模块生命周期
 * =========================================================================
 *
 *   init ──→ start ──→ poll (循环) ──→ stop
 *
 *   ① init  : 初始化 (分配资源、注册子组件) → init_all 启动时调用一次
 *   ② start : 启动 (使能中断/DMA/定时器) → start_all 跟随 init_all
 *   ③ poll  : 轮询 (感知→决策→执行的主循环) → poll_all 在 while(1) 中反复调用
 *   ④ stop  : 停止 (关闭中断、释放资源、安全保存) → 按需逐个调用
 *
 * =========================================================================
 * 典型主循环
 * =========================================================================
 *
 *   efw_init();
 *   // 注册 HAL→COMM→SENSOR→ACTUATOR→ALGO→MODULE
 *   efw_module_init_all();
 *   efw_module_start_all();
 *   while (1) { efw_module_poll_all(); }  // ★ 核心驱动循环
 */

#include <string.h>
#include "efw/core/config.h"
#include "efw/module/module.h"

#if EFW_ENABLE_MODULE  /**< 编译开关 */

static const efw_module_ops_t *g_modules[EFW_MAX_MODULES]; /**< Module ops 指针数组 */
static size_t g_module_n;                                  /**< 已注册模块数量 */

static int same_name(const char *a, const char *b) {
    return a && b && strcmp(a, b) == 0;
}

/**
 * @brief 统一的可空回调调用——fn 为 NULL 时跳过并返回 OK
 */
static efw_status_t module_call(const efw_module_ops_t *ops, efw_status_t (*fn)(void *ctx)) {
    return fn ? fn(ops->ctx) : EFW_OK;  /* 回调为空 → 合法跳过 */
}

/* ====== 初始化 + 注册 ====== */

efw_status_t efw_module_registry_init(void) { g_module_n = 0; return EFW_OK; }

efw_status_t efw_module_register(const efw_module_ops_t *ops) {
    if (!ops || !ops->name) return EFW_ERR_INVALID;             /* 参数校验 */
    for (size_t i = 0; i < g_module_n; ++i)
        if (same_name(g_modules[i]->name, ops->name))
            return EFW_ERR_ALREADY_EXISTS;                       /* 名称冲突 */
    if (g_module_n >= EFW_MAX_MODULES) return EFW_ERR_FULL;    /* 容量已满 */
    g_modules[g_module_n++] = ops;                               /* 存入 */
    return EFW_OK;
}

/* ====== 查找 ====== */

efw_status_t efw_module_get(const char *name, const efw_module_ops_t **out_ops) {
    if (!name || !out_ops) return EFW_ERR_INVALID;
    for (size_t i = 0; i < g_module_n; ++i)
        if (same_name(g_modules[i]->name, name)) {
            *out_ops = g_modules[i];
            return EFW_OK;
        }
    return EFW_ERR_NOT_FOUND;
}

/* ====== 单模块操作：查找 → module_call ====== */

efw_status_t efw_module_init(const char *name)  { const efw_module_ops_t *ops; efw_status_t s=efw_module_get(name,&ops); return s!=EFW_OK?s:module_call(ops,ops->init); }
efw_status_t efw_module_start(const char *name) { const efw_module_ops_t *ops; efw_status_t s=efw_module_get(name,&ops); return s!=EFW_OK?s:module_call(ops,ops->start); }
efw_status_t efw_module_stop(const char *name)  { const efw_module_ops_t *ops; efw_status_t s=efw_module_get(name,&ops); return s!=EFW_OK?s:module_call(ops,ops->stop); }
efw_status_t efw_module_poll(const char *name)  { const efw_module_ops_t *ops; efw_status_t s=efw_module_get(name,&ops); return s!=EFW_OK?s:module_call(ops,ops->poll); }

/* ====== 批量操作：遍历全部模块，fail-fast ====== */

efw_status_t efw_module_init_all(void) {
    for (size_t i = 0; i < g_module_n; ++i) {
        efw_status_t s = module_call(g_modules[i], g_modules[i]->init);
        if (s != EFW_OK) return s;  /* 任一失败 → 立即返回 */
    }
    return EFW_OK;
}

efw_status_t efw_module_start_all(void) {
    for (size_t i = 0; i < g_module_n; ++i) {
        efw_status_t s = module_call(g_modules[i], g_modules[i]->start);
        if (s != EFW_OK) return s;
    }
    return EFW_OK;
}

/**
 * @brief 轮询所有已注册模块 ★ 主循环最核心的调用
 *
 * 每个 poll 中包含 感知→决策→执行 的完整链路。
 */
efw_status_t efw_module_poll_all(void) {
    for (size_t i = 0; i < g_module_n; ++i) {
        efw_status_t s = module_call(g_modules[i], g_modules[i]->poll);
        if (s != EFW_OK) return s;
    }
    return EFW_OK;
}

size_t efw_module_count_by_type(efw_module_type_t type) {
    size_t n = 0;
    for (size_t i = 0; i < g_module_n; ++i)
        if (g_modules[i]->type == type) ++n;
    return n;
}

#endif /* EFW_ENABLE_MODULE */
