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
#include "efw/core/diagnostic.h"
#include "efw/core/registry.h"
#include "efw/module/module.h"

#if EFW_ENABLE_MODULE

static const efw_module_ops_t *g_module_default_pool[EFW_MAX_MODULES];
static const efw_module_ops_t **g_modules = g_module_default_pool;
static size_t g_module_cap = EFW_MAX_MODULES;
static size_t g_module_n;

static efw_status_t module_call(const efw_module_ops_t *ops, efw_status_t (*fn)(void *ctx)) {
    return fn ? fn(ops->ctx) : EFW_OK;
}

static void insert_module_sorted(const efw_module_ops_t *ops) {
    size_t pos = g_module_n;
    for (size_t i = 0; i < g_module_n; ++i) {
        if (g_modules[i]->priority > ops->priority) {
            pos = i;
            break;
        }
    }
    for (size_t i = g_module_n; i > pos; --i) {
        g_modules[i] = g_modules[i - 1];
    }
    g_modules[pos] = ops;
    g_module_n++;
}

/* ====== 初始化 + 注册 ====== */

efw_status_t efw_module_registry_init(void) { g_modules = g_module_default_pool; g_module_cap = EFW_MAX_MODULES; g_module_n = 0; return EFW_OK; }
efw_status_t efw_module_registry_init_pool(const efw_module_ops_t **pool, size_t capacity) {
    if (!pool || capacity == 0) return EFW_ERR_INVALID;
    g_modules = pool;
    g_module_cap = capacity;
    g_module_n = 0;
    return EFW_OK;
}

efw_status_t efw_module_register(const efw_module_ops_t *ops) {
    if (!ops || !ops->name) return EFW_ERR_INVALID;
    for (size_t i = 0; i < g_module_n; ++i)
        if (efw_name_eq(g_modules[i]->name, ops->name))
            return EFW_ERR_ALREADY_EXISTS;
    if (g_module_n >= g_module_cap) return EFW_ERR_FULL;
    insert_module_sorted(ops);
    return EFW_OK;
}

efw_status_t efw_module_get(const char *name, const efw_module_ops_t **out_ops) {
    if (!name || !out_ops) return EFW_ERR_INVALID;
    for (size_t i = 0; i < g_module_n; ++i)
        if (efw_name_eq(g_modules[i]->name, name)) {
            *out_ops = g_modules[i];
            return EFW_OK;
        }
    return EFW_ERR_NOT_FOUND;
}

efw_status_t efw_module_unregister(const char *name) {
    for (size_t i = 0; i < g_module_n; ++i) {
        if (efw_name_eq(g_modules[i]->name, name)) {
            for (size_t j = i; j < g_module_n - 1; ++j) {
                g_modules[j] = g_modules[j + 1];
            }
            g_module_n--;
            return EFW_OK;
        }
    }
    return EFW_ERR_NOT_FOUND;
}

size_t efw_module_count(void) { return g_module_n; }

void efw_module_enumerate(efw_module_enumerate_fn fn, void *user) {
    if (!fn) return;
    for (size_t i = 0; i < g_module_n; ++i) {
        fn(g_modules[i], user);
    }
}

/* ====== 单模块操作 ====== */

efw_status_t efw_module_init(const char *name)  { const efw_module_ops_t *ops; efw_status_t s=efw_module_get(name,&ops); return s!=EFW_OK?s:module_call(ops,ops->init); }
efw_status_t efw_module_start(const char *name) { const efw_module_ops_t *ops; efw_status_t s=efw_module_get(name,&ops); return s!=EFW_OK?s:module_call(ops,ops->start); }
efw_status_t efw_module_stop(const char *name)  { const efw_module_ops_t *ops; efw_status_t s=efw_module_get(name,&ops); return s!=EFW_OK?s:module_call(ops,ops->stop); }
efw_status_t efw_module_poll(const char *name)  { const efw_module_ops_t *ops; efw_status_t s=efw_module_get(name,&ops); return s!=EFW_OK?s:module_call(ops,ops->poll); }

/* ====== 批量操作（按优先级排序） ====== */

efw_status_t efw_module_init_all(void) {
    efw_status_t first_err = EFW_OK;
    for (size_t i = 0; i < g_module_n; ++i) {
        efw_status_t s = module_call(g_modules[i], g_modules[i]->init);
        if (s != EFW_OK && first_err == EFW_OK) {
            first_err = s;
            efw_diag_set(s, "module", g_modules[i]->name, "init failed");
        }
    }
    return first_err;
}

efw_status_t efw_module_start_all(void) {
    efw_status_t first_err = EFW_OK;
    for (size_t i = 0; i < g_module_n; ++i) {
        efw_status_t s = module_call(g_modules[i], g_modules[i]->start);
        if (s != EFW_OK && first_err == EFW_OK) {
            first_err = s;
            efw_diag_set(s, "module", g_modules[i]->name, "start failed");
        }
    }
    return first_err;
}

efw_status_t efw_module_poll_all(void) {
    efw_status_t first_err = EFW_OK;
    for (size_t i = 0; i < g_module_n; ++i) {
        efw_status_t s = module_call(g_modules[i], g_modules[i]->poll);
        if (s != EFW_OK && first_err == EFW_OK) {
            first_err = s;
            efw_diag_set(s, "module", g_modules[i]->name, "poll failed");
        }
    }
    return first_err;
}

size_t efw_module_count_by_type(efw_module_type_t type) {
    size_t n = 0;
    for (size_t i = 0; i < g_module_n; ++i)
        if (g_modules[i]->type == type) ++n;
    return n;
}

#endif
