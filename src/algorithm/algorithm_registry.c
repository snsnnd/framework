/**
 * @file    algorithm_registry.c
 * @brief   算法注册表实现
 *
 * 管理所有算法实例的注册、查找和运行。
 * 由 EFW_ENABLE_ALGORITHM 宏控制编译。
 *
 * =========================================================================
 * 算法注册表的目的
 * =========================================================================
 *
 *   让用户通过名称字符串引用算法，而不需要持有指针。
 *   模块 A 注册 PID "motor_pid"，模块 B 通过名称找到它并调用。
 *
 *   所有算法遵循统一接口：run(ctx, in, out) → efw_status_t
 *
 * =========================================================================
 * 性能提示
 * =========================================================================
 *
 *   efw_algo_run("name", in, out) 内部做两次操作：
 *     O(n) 名称查找 + 调用 run 回调。
 *   高频调用时可预取 ops 指针省去查找：
 *     efw_algo_get("pid", &ops);  // 初始化时取一次
 *     ops->run(ops->ctx, &in, &out);  // 循环中直接调用 (无查找开销)
 */

#include <string.h>
#include "efw/core/config.h"
#include "efw/core/diagnostic.h"
#include "efw/algorithm/registry.h"

#if EFW_ENABLE_ALGORITHM  /**< 编译开关 */

static const efw_algo_ops_t *g_algo_default_pool[EFW_MAX_ALGOS];
static const efw_algo_ops_t **g_algos = g_algo_default_pool;
static size_t g_algo_cap = EFW_MAX_ALGOS;
static size_t g_algo_n;

static int same_name(const char *a, const char *b) {
    return a && b && strcmp(a, b) == 0;
}

/* ====== 初始化 + 注册 ====== */

efw_status_t efw_algo_registry_init(void) { g_algos = g_algo_default_pool; g_algo_cap = EFW_MAX_ALGOS; g_algo_n = 0; return EFW_OK; }
efw_status_t efw_algo_registry_init_pool(const efw_algo_ops_t **pool, size_t capacity) {
    if (!pool || capacity == 0) { efw_diag_set(EFW_ERR_INVALID, "algo", 0, "invalid pool"); return EFW_ERR_INVALID; }
    g_algos = pool; g_algo_cap = capacity; g_algo_n = 0; return EFW_OK;
}

efw_status_t efw_algo_register(const efw_algo_ops_t *ops) {
    if (!ops || !ops->name || !ops->run) { efw_diag_set(EFW_ERR_INVALID, "algo", 0, "invalid ops"); return EFW_ERR_INVALID; }
    for (size_t i = 0; i < g_algo_n; ++i)
        if (same_name(g_algos[i]->name, ops->name))
            { efw_diag_set(EFW_ERR_ALREADY_EXISTS, "algo", ops->name, "duplicate name"); return EFW_ERR_ALREADY_EXISTS; }
    if (g_algo_n >= g_algo_cap) { efw_diag_set(EFW_ERR_FULL, "algo", ops->name, "pool full"); return EFW_ERR_FULL; }
    g_algos[g_algo_n++] = ops;                                      /* 存入 */
    return EFW_OK;
}

/* ====== 查找 ====== */

efw_status_t efw_algo_get(const char *name, const efw_algo_ops_t **out_ops) {
    if (!name || !out_ops) return EFW_ERR_INVALID;
    for (size_t i = 0; i < g_algo_n; ++i)
        if (same_name(g_algos[i]->name, name)) {
            *out_ops = g_algos[i];
            return EFW_OK;
        }
    return EFW_ERR_NOT_FOUND;
}

/* ====== 运行算法 (最常用的高层 API) ====== */

/**
 * @brief 按名称运行算法 = 查找 + 调用 run
 * @param name 算法名称
 * @param in   输入数据 (void* → 算法内部解释为具体类型)
 * @param out  输出数据 (void* → 结果写回)
 */
efw_status_t efw_algo_run(const char *name, const void *in, void *out) {
    const efw_algo_ops_t *ops;
    efw_status_t s = efw_algo_get(name, &ops);  /* ① 查找 */
    if (s != EFW_OK) return s;
    return ops->run(ops->ctx, in, out);          /* ② 执行 */
}

#endif /* EFW_ENABLE_ALGORITHM */
