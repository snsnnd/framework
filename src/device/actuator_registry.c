/**
 * @file    actuator_registry.c
 * @brief   Actuator (执行器设备层) 注册表实现
 *
 * 本文件由 EFW_ENABLE_ACTUATOR 宏控制编译。
 *
 * =========================================================================
 * Actuator vs Sensor (对称设计)
 * =========================================================================
 *
 *   Sensor   感知 (read)  — 从物理世界获取数据
 *   Actuator 执行 (write) — 向物理世界施加控制
 *
 *   两者结构高度对称：都有 init、绑定 HAL/COMM、注册时校验。
 *   区别：Actuator 多了 enable/disable 操作。
 *
 * =========================================================================
 * 为什么需要 enable/disable？
 * =========================================================================
 *
 *   "输出为 0" ≠ "完全关闭"：
 *     - 电机 speed=0 ≠ 驱动器断电 (断电后电机可自由转动)
 *     - 舵机 angle=0° ≠ 舵机断电 (断电后释放力矩)
 *
 *   分离 enable/disable 与 write 使安全逻辑清晰：
 *     启动：enable → write(初值)
 *     运行：write... write...
 *     急停：disable (跳过 write，直接断电)
 *     关闭：write(安全值) → disable
 */

#include <string.h>
#include "efw/core/config.h"
#include "efw/core/diagnostic.h"
#include "efw/device/actuator.h"

#if EFW_ENABLE_ACTUATOR  /**< 编译开关 */

static const efw_actuator_ops_t *g_actuator_default_pool[EFW_MAX_ACTUATORS];
static const efw_actuator_ops_t **g_actuators = g_actuator_default_pool;
static size_t g_actuator_cap = EFW_MAX_ACTUATORS;
static size_t g_actuator_n;

static int same_name(const char *a, const char *b) {
    return a && b && strcmp(a, b) == 0;
}

/* ====== 初始化 + 注册 ====== */

efw_status_t efw_actuator_registry_init(void) { g_actuators = g_actuator_default_pool; g_actuator_cap = EFW_MAX_ACTUATORS; g_actuator_n = 0; return EFW_OK; }
efw_status_t efw_actuator_registry_init_pool(const efw_actuator_ops_t **pool, size_t capacity) {
    if (!pool || capacity == 0) { efw_diag_set(EFW_ERR_INVALID, "actuator", 0, "invalid pool"); return EFW_ERR_INVALID; }
    g_actuators = pool; g_actuator_cap = capacity; g_actuator_n = 0; return EFW_OK;
}

efw_status_t efw_actuator_register(const efw_actuator_ops_t *ops) {
    if (!ops || !ops->name || !ops->write) { efw_diag_set(EFW_ERR_INVALID, "actuator", 0, "invalid ops"); return EFW_ERR_INVALID; }

    /* HAL 绑定校验 */
    if (ops->hal_name) {
#if EFW_ENABLE_HAL
        const efw_hal_ops_t *hal;
        efw_status_t s = efw_hal_get(ops->hal_name, &hal);
        if (s != EFW_OK) return s;
#else
        return EFW_ERR_INVALID;
#endif
    }

    /* COMM 绑定校验 */
    if (ops->comm_name) {
#if EFW_ENABLE_COMM
        const efw_comm_ops_t *comm;
        efw_status_t s = efw_comm_get(ops->comm_name, &comm);
        if (s != EFW_OK) return s;
#else
        return EFW_ERR_INVALID;
#endif
    }

    for (size_t i = 0; i < g_actuator_n; ++i)
        if (same_name(g_actuators[i]->name, ops->name))
            { efw_diag_set(EFW_ERR_ALREADY_EXISTS, "actuator", ops->name, "duplicate name"); return EFW_ERR_ALREADY_EXISTS; }
    if (g_actuator_n >= g_actuator_cap) { efw_diag_set(EFW_ERR_FULL, "actuator", ops->name, "pool full"); return EFW_ERR_FULL; }
    g_actuators[g_actuator_n++] = ops;                           /* 存入 */
    return EFW_OK;
}

/* ====== 查找 + 统计 ====== */

efw_status_t efw_actuator_get(const char *name, const efw_actuator_ops_t **out_ops) {
    if (!name || !out_ops) return EFW_ERR_INVALID;
    for (size_t i = 0; i < g_actuator_n; ++i)
        if (same_name(g_actuators[i]->name, name)) {
            *out_ops = g_actuators[i];
            return EFW_OK;
        }
    return EFW_ERR_NOT_FOUND;
}

size_t efw_actuator_count_by_type(efw_actuator_type_t type) {
    size_t n = 0;
    for (size_t i = 0; i < g_actuator_n; ++i)
        if (g_actuators[i]->type == type) ++n;
    return n;
}

/* ====== IO 绑定查询 ====== */

efw_status_t efw_actuator_bind_hal(const char *actuator_name, const efw_hal_ops_t **out_hal) {
#if EFW_ENABLE_HAL
    const efw_actuator_ops_t *actuator;
    efw_status_t s = efw_actuator_get(actuator_name, &actuator);
    if (s != EFW_OK) return s;
    if (!actuator->hal_name) return EFW_ERR_NOT_FOUND;
    return efw_hal_get(actuator->hal_name, out_hal);
#else
    EFW_UNUSED(actuator_name); EFW_UNUSED(out_hal);
    return EFW_ERR_INVALID;
#endif
}

efw_status_t efw_actuator_bind_comm(const char *actuator_name, const efw_comm_ops_t **out_comm) {
#if EFW_ENABLE_COMM
    const efw_actuator_ops_t *actuator;
    efw_status_t s = efw_actuator_get(actuator_name, &actuator);
    if (s != EFW_OK) return s;
    if (!actuator->comm_name) return EFW_ERR_NOT_FOUND;
    return efw_comm_get(actuator->comm_name, out_comm);
#else
    EFW_UNUSED(actuator_name); EFW_UNUSED(out_comm);
    return EFW_ERR_INVALID;
#endif
}

/* ====== 便捷操作 ====== */

efw_status_t efw_actuator_init_device(const char *name) {  /* init 可空 */
    const efw_actuator_ops_t *ops;
    efw_status_t s = efw_actuator_get(name, &ops);
    if (s != EFW_OK) return s;
    return ops->init ? ops->init(ops->ctx) : EFW_OK;
}

efw_status_t efw_actuator_enable(const char *name) {  /* enable 可空 */
    const efw_actuator_ops_t *ops;
    efw_status_t s = efw_actuator_get(name, &ops);
    if (s != EFW_OK) return s;
    return ops->enable ? ops->enable(ops->ctx) : EFW_OK;
}

efw_status_t efw_actuator_disable(const char *name) {  /* disable 可空 */
    const efw_actuator_ops_t *ops;
    efw_status_t s = efw_actuator_get(name, &ops);
    if (s != EFW_OK) return s;
    return ops->disable ? ops->disable(ops->ctx) : EFW_OK;
}

/**
 * @brief 写入执行器控制指令 ★ 最常用 API
 * cmd 指向控制结构体 (efw_actuator_cmd_t / efw_motor_cmd_t / 自定义)
 */
efw_status_t efw_actuator_write(const char *name, const void *cmd) {
    const efw_actuator_ops_t *ops;
    efw_status_t s = efw_actuator_get(name, &ops);
    if (s != EFW_OK) return s;
    if (!cmd) return EFW_ERR_INVALID;       /* cmd 不能为空——必须指定控制值 */
    return ops->write(ops->ctx, cmd);
}

#endif /* EFW_ENABLE_ACTUATOR */
