/**
 * @file    sensor_registry.c
 * @brief   Sensor (传感器设备层) 注册表实现
 *
 * 本文件由 EFW_ENABLE_SENSOR 宏控制编译。
 *
 * =========================================================================
 * ★ 注册时双重 IO 绑定校验 (核心安全机制)
 * =========================================================================
 *
 *   传感器可绑定 HAL (如 ADC 读电压) 和/或 COMM (如 I2C 读寄存器)。
 *   注册时立即验证引用的 hal_name/comm_name 是否在对应注册表中存在：
 *
 *     - HAL 存在 → 注册继续；不存在 → EFW_ERR_NOT_FOUND，拒绝注册
 *     - COMM 存在 → 注册继续；不存在 → 同上
 *     - HAL 禁用 (EFW_ENABLE_HAL=0) 但传感器绑定 hal_name → EFW_ERR_INVALID
 *     - COMM 禁用 (EFW_ENABLE_COMM=0) 但传感器绑定 comm_name → 同上
 *     - 两者都不绑 → 纯虚拟传感器，跳过校验，允许注册
 *
 *   这种"注册时校验"比"运行时校验"好得多：
 *   如果注册时发现 HAL 不存在，报错就在注册代码那一行——
 *   而运行时报错可能埋在深层的调用链里，调试极其痛苦。
 *
 *   因此初始化顺序必须是：HAL → COMM → SENSOR
 */

#include <string.h>
#include "efw/core/config.h"
#include "efw/core/diagnostic.h"
#include "efw/core/registry.h"
#include "efw/device/sensor.h"

#if EFW_ENABLE_SENSOR

static const efw_sensor_ops_t *g_sensor_default_pool[EFW_MAX_SENSORS];
static const efw_sensor_ops_t **g_sensors = g_sensor_default_pool;
static size_t g_sensor_cap = EFW_MAX_SENSORS;
static size_t g_sensor_n;

efw_status_t efw_sensor_registry_init(void) { g_sensors = g_sensor_default_pool; g_sensor_cap = EFW_MAX_SENSORS; g_sensor_n = 0; return EFW_OK; }
efw_status_t efw_sensor_registry_init_pool(const efw_sensor_ops_t **pool, size_t capacity) {
    if (!pool || capacity == 0) { efw_diag_set(EFW_ERR_INVALID, "sensor", 0, "invalid pool"); return EFW_ERR_INVALID; }
    g_sensors = pool; g_sensor_cap = capacity; g_sensor_n = 0; return EFW_OK;
}

efw_status_t efw_sensor_register(const efw_sensor_ops_t *ops) {
    if (!ops || !ops->name || !ops->read) { efw_diag_set(EFW_ERR_INVALID, "sensor", 0, "invalid ops"); return EFW_ERR_INVALID; }
    if (ops->hal_name) {
#if EFW_ENABLE_HAL
        const efw_hal_ops_t *hal;
        efw_status_t s = efw_hal_get(ops->hal_name, &hal);
        if (s != EFW_OK) return s;
#else
        return EFW_ERR_INVALID;
#endif
    }
    if (ops->comm_name) {
#if EFW_ENABLE_COMM
        const efw_comm_ops_t *comm;
        efw_status_t s = efw_comm_get(ops->comm_name, &comm);
        if (s != EFW_OK) return s;
#else
        return EFW_ERR_INVALID;
#endif
    }
    for (size_t i = 0; i < g_sensor_n; ++i)
        if (efw_name_eq(g_sensors[i]->name, ops->name))
            { efw_diag_set(EFW_ERR_ALREADY_EXISTS, "sensor", ops->name, "duplicate name"); return EFW_ERR_ALREADY_EXISTS; }
    if (g_sensor_n >= g_sensor_cap) { efw_diag_set(EFW_ERR_FULL, "sensor", ops->name, "pool full"); return EFW_ERR_FULL; }
    g_sensors[g_sensor_n++] = ops;
    return EFW_OK;
}

efw_status_t efw_sensor_get(const char *name, const efw_sensor_ops_t **out_ops) {
    if (!name || !out_ops) return EFW_ERR_INVALID;
    for (size_t i = 0; i < g_sensor_n; ++i)
        if (efw_name_eq(g_sensors[i]->name, name)) {
            *out_ops = g_sensors[i];
            return EFW_OK;
        }
    return EFW_ERR_NOT_FOUND;
}

efw_status_t efw_sensor_unregister(const char *name) {
    for (size_t i = 0; i < g_sensor_n; ++i) {
        if (efw_name_eq(g_sensors[i]->name, name)) {
            g_sensors[i] = g_sensors[--g_sensor_n];
            return EFW_OK;
        }
    }
    return EFW_ERR_NOT_FOUND;
}

size_t efw_sensor_count(void) { return g_sensor_n; }

size_t efw_sensor_count_by_type(efw_sensor_type_t type) {
    size_t n = 0;
    for (size_t i = 0; i < g_sensor_n; ++i)
        if (g_sensors[i]->type == type) ++n;
    return n;
}

void efw_sensor_enumerate(efw_sensor_enumerate_fn fn, void *user) {
    if (!fn) return;
    for (size_t i = 0; i < g_sensor_n; ++i) {
        fn(g_sensors[i], user);
    }
}

/* ====== IO 绑定查询：传感器名 → HAL/COMM ====== */

efw_status_t efw_sensor_bind_hal(const char *sensor_name, const efw_hal_ops_t **out_hal) {
#if EFW_ENABLE_HAL
    const efw_sensor_ops_t *sensor;
    efw_status_t s = efw_sensor_get(sensor_name, &sensor);
    if (s != EFW_OK) return s;
    if (!sensor->hal_name) return EFW_ERR_NOT_FOUND;
    return efw_hal_get(sensor->hal_name, out_hal);
#else
    EFW_UNUSED(sensor_name); EFW_UNUSED(out_hal);
    return EFW_ERR_INVALID;
#endif
}

efw_status_t efw_sensor_bind_comm(const char *sensor_name, const efw_comm_ops_t **out_comm) {
#if EFW_ENABLE_COMM
    const efw_sensor_ops_t *sensor;
    efw_status_t s = efw_sensor_get(sensor_name, &sensor);
    if (s != EFW_OK) return s;
    if (!sensor->comm_name) return EFW_ERR_NOT_FOUND;
    return efw_comm_get(sensor->comm_name, out_comm);
#else
    EFW_UNUSED(sensor_name); EFW_UNUSED(out_comm);
    return EFW_ERR_INVALID;
#endif
}

/* ====== 便捷操作 ====== */

/** 初始化传感器 (init 可空) */
efw_status_t efw_sensor_init_device(const char *name) {
    const efw_sensor_ops_t *ops;
    efw_status_t s = efw_sensor_get(name, &ops);
    if (s != EFW_OK) return s;
    return ops->init ? ops->init(ops->ctx) : EFW_OK;
}

/**
 * @brief 读取传感器数据 ★ 最常用 API
 * 按名称查找传感器 → 调用 read 回调 → 结果写入 out。
 */
efw_status_t efw_sensor_read(const char *name, void *out, uint16_t out_size) {
    const efw_sensor_ops_t *ops;
    efw_status_t s = efw_sensor_get(name, &ops);
    if (s != EFW_OK) return s;
    return ops->read(ops->ctx, out, out_size);
}

#endif /* EFW_ENABLE_SENSOR */
