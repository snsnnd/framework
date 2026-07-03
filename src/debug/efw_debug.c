/**
 * @file    efw_debug.c
 * @brief   EFW 在线调试模块核心实现
 */

#include "efw/debug/efw_debug.h"
#include "efw/hal/hal.h"
#include "efw/device/sensor.h"
#include "efw/algorithm/registry.h"
#include "efw/state/state_machine.h"
#include <string.h>
#include <stdio.h>

/* ==================================================================
 *  内部数据结构
 * ================================================================== */

/** @brief 调试模块全局状态 */
static struct {
    efw_debug_point_t points[EFW_MAX_DEBUG_POINTS];
    uint16_t point_count;
    uint16_t next_param_id;
    uint32_t update_count;
    uint32_t error_count;
    uint8_t initialized;
} g_debug = {
    .point_count = 0,
    .next_param_id = 0x1000,  /* 从 0x1000 开始，避免与用户参数冲突 */
    .update_count = 0,
    .error_count = 0,
    .initialized = 0,
};

/* ==================================================================
 *  内部辅助函数
 * ================================================================== */

/**
 * @brief 查找空闲监控点槽位
 */
static efw_debug_point_t *find_free_slot(void)
{
    for (uint16_t i = 0; i < EFW_MAX_DEBUG_POINTS; i++) {
        if (!g_debug.points[i].registered) {
            return &g_debug.points[i];
        }
    }
    return NULL;
}

/**
 * @brief 按名称查找监控点
 */
static efw_debug_point_t *find_by_name(const char *name)
{
    for (uint16_t i = 0; i < EFW_MAX_DEBUG_POINTS; i++) {
        if (g_debug.points[i].registered &&
            strncmp(g_debug.points[i].name, name, EFW_DEBUG_NAME_MAX_LEN - 1) == 0) {
            return &g_debug.points[i];
        }
    }
    return NULL;
}

/**
 * @brief 注册单个监控点
 */
static efw_status_t register_point(const char *name, efw_debug_source_t source,
                                   efw_debug_type_t type, const void *value_ptr)
{
    if (!name || !value_ptr) {
        return EFW_ERR_INVALID;
    }

    /* 检查名称是否已存在 */
    if (find_by_name(name)) {
        return EFW_ERR_ALREADY_EXISTS;
    }

    /* 查找空闲槽位 */
    efw_debug_point_t *slot = find_free_slot();
    if (!slot) {
        return EFW_ERR_FULL;
    }

    /* 填充监控点 */
    memset(slot, 0, sizeof(*slot));
    strncpy(slot->name, name, EFW_DEBUG_NAME_MAX_LEN - 1);
    slot->source = source;
    slot->type = type;
    slot->value_ptr = value_ptr;
    slot->param_id = g_debug.next_param_id++;
    slot->registered = 1;

    g_debug.point_count++;

    return EFW_OK;
}

/**
 * @brief 验证监控点可读取
 *
 * 当前 MCU 端实现提供本地监控点表和快照导出；真正的 LiteTune 参数注册
 * 由 efw_debug_litetune.c 的集成层负责，不能在这里假装已写入协议栈。
 */
static efw_status_t validate_point_readable(const efw_debug_point_t *point)
{
    if (!point || !point->value_ptr) {
        return EFW_ERR_INVALID;
    }
    return EFW_OK;
}

/* ==================================================================
 *  HAL 层数据采集回调
 * ================================================================== */

#if EFW_ENABLE_HAL
static void hal_register_callback(const efw_hal_ops_t *ops, void *user)
{
    int *count = (int *)user;
    char name[EFW_DEBUG_NAME_MAX_LEN];

    /* 生成名称: "hal.{name}" */
    snprintf(name, sizeof(name), "hal.%s", ops->name);

    /* 对于 HAL，我们监控其类型和总线 ID */
    /* 注意：这里简化为监控一个静态值，实际应用中可能需要更复杂的逻辑 */
    efw_status_t ret = register_point(name, EFW_DEBUG_SOURCE_HAL,
                                       EFW_DEBUG_TYPE_U32, &ops->type);
    if (ret == EFW_OK) {
        (*count)++;
    }
}
#endif /* EFW_ENABLE_HAL */

/* ==================================================================
 *  传感器数据采集回调
 * ================================================================== */

#if EFW_ENABLE_SENSOR
static void sensor_register_callback(const efw_sensor_ops_t *ops, void *user)
{
    int *count = (int *)user;
    char name[EFW_DEBUG_NAME_MAX_LEN];

    /* 生成名称: "sensor.{name}" */
    snprintf(name, sizeof(name), "sensor.%s", ops->name);

    /* 对于传感器，我们需要获取其最新读数
     * 注意：这里需要一个地方存储传感器的最新值
     * 实际实现中，可以在 efw_sensor_read() 时自动更新调试模块
     */
    efw_status_t ret = register_point(name, EFW_DEBUG_SOURCE_SENSOR,
                                       EFW_DEBUG_TYPE_F32, ops->ctx);
    if (ret == EFW_OK) {
        (*count)++;
    }
}
#endif /* EFW_ENABLE_SENSOR */

/* ==================================================================
 *  算法数据采集回调
 * ================================================================== */

#if EFW_ENABLE_ALGORITHM
static void algo_register_callback(const efw_algo_ops_t *ops, void *user)
{
    int *count = (int *)user;
    char name[EFW_DEBUG_NAME_MAX_LEN];

    /* 生成名称: "algo.{name}" */
    snprintf(name, sizeof(name), "algo.%s", ops->name);

    /* 对于算法，我们监控其上下文（可能包含内部状态） */
    efw_status_t ret = register_point(name, EFW_DEBUG_SOURCE_ALGORITHM,
                                       EFW_DEBUG_TYPE_U32, ops->ctx);
    if (ret == EFW_OK) {
        (*count)++;
    }
}
#endif /* EFW_ENABLE_ALGORITHM */

/* ==================================================================
 *  状态机数据采集
 * ================================================================== */

#if EFW_ENABLE_STATE_MACHINE
/**
 * @brief 状态机监控点的特殊读取函数
 *
 * 由于状态机的当前状态是动态变化的，我们需要一个包装器
 */
typedef struct {
    const efw_sm_context_t *sm_ctx;
    char state_name[EFW_DEBUG_NAME_MAX_LEN];
} efw_debug_sm_wrapper_t;

static efw_status_t sm_state_reader(const efw_debug_sm_wrapper_t *wrapper,
                                     char *out_name, uint16_t out_size)
{
    if (!wrapper || !wrapper->sm_ctx || !out_name) {
        return EFW_ERR_INVALID;
    }

    const char *current = efw_sm_current_state(wrapper->sm_ctx);
    if (current) {
        strncpy(out_name, current, out_size - 1);
        out_name[out_size - 1] = '\0';
    } else {
        strncpy(out_name, "UNKNOWN", out_size - 1);
        out_name[out_size - 1] = '\0';
    }

    return EFW_OK;
}
#endif /* EFW_ENABLE_STATE_MACHINE */

/* ==================================================================
 *  公共 API 实现
 * ================================================================== */

efw_status_t efw_debug_init(void)
{
    if (g_debug.initialized) {
        return EFW_OK;  /* 已初始化 */
    }

    /* 清零所有监控点 */
    memset(g_debug.points, 0, sizeof(g_debug.points));
    g_debug.point_count = 0;
    g_debug.next_param_id = 0x1000;
    g_debug.update_count = 0;
    g_debug.error_count = 0;

    g_debug.initialized = 1;

    return EFW_OK;
}

efw_status_t efw_debug_update(void)
{
    if (!g_debug.initialized) {
        return EFW_ERR_NOT_READY;
    }

    uint16_t synced = 0;
    uint16_t errors = 0;

    /* 检查所有已注册监控点仍可读取。LiteTune 上报由集成层显式调用。 */
    for (uint16_t i = 0; i < EFW_MAX_DEBUG_POINTS; i++) {
        if (!g_debug.points[i].registered) {
            continue;
        }

        efw_status_t ret = validate_point_readable(&g_debug.points[i]);
        if (ret == EFW_OK) {
            synced++;
        } else {
            errors++;
        }
    }

    g_debug.update_count++;
    g_debug.error_count += errors;

    return (errors == 0) ? EFW_OK : EFW_ERR_IO;
}

efw_status_t efw_debug_get_stats(efw_debug_stats_t *stats)
{
    if (!stats) {
        return EFW_ERR_INVALID;
    }

    stats->total_points = g_debug.point_count;
    stats->update_count = g_debug.update_count;
    stats->error_count = g_debug.error_count;

    /* 统计各类监控点数量 */
    stats->efw_points = 0;
    stats->custom_points = 0;

    for (uint16_t i = 0; i < EFW_MAX_DEBUG_POINTS; i++) {
        if (!g_debug.points[i].registered) {
            continue;
        }

        if (g_debug.points[i].source == EFW_DEBUG_SOURCE_CUSTOM) {
            stats->custom_points++;
        } else {
            stats->efw_points++;
        }
    }

    return EFW_OK;
}

uint16_t efw_debug_point_count(void)
{
    return g_debug.point_count;
}

void efw_debug_foreach_point(efw_debug_point_iter_fn callback, void *user)
{
    if (!callback) {
        return;
    }

    for (uint16_t i = 0; i < EFW_MAX_DEBUG_POINTS; i++) {
        if (g_debug.points[i].registered) {
            callback(&g_debug.points[i], user);
        }
    }
}

/* ==================================================================
 *  EFW 框架数据注册实现
 * ================================================================== */

int efw_debug_register_efw_hal(void)
{
#if EFW_ENABLE_HAL
    int count = 0;
    efw_hal_enumerate(hal_register_callback, &count);
    return count;
#else
    return 0;
#endif
}

int efw_debug_register_efw_sensors(void)
{
#if EFW_ENABLE_SENSOR
    int count = 0;
    efw_sensor_enumerate(sensor_register_callback, &count);
    return count;
#else
    return 0;
#endif
}

int efw_debug_register_efw_algorithms(void)
{
#if EFW_ENABLE_ALGORITHM
    int count = 0;
    efw_algo_enumerate(algo_register_callback, &count);
    return count;
#else
    return 0;
#endif
}

int efw_debug_register_efw_state_machines(void)
{
#if EFW_ENABLE_STATE_MACHINE
    /* 状态机当前状态是计算值；这里只提供遍历入口，具体快照字段
     * 需要后续引入动态 reader 后再自动注册。
     */
    (void)sm_state_reader;
    (void)efw_sm_enumerate;
    return 0;
#else
    return 0;
#endif
}

int efw_debug_register_all_efw(void)
{
    int total = 0;

    total += efw_debug_register_efw_hal();
    total += efw_debug_register_efw_sensors();
    total += efw_debug_register_efw_algorithms();
    total += efw_debug_register_efw_state_machines();

    return total;
}

/* ==================================================================
 *  自定义监控点注册实现
 * ================================================================== */

efw_status_t efw_debug_register_custom(const char *name, efw_debug_type_t type,
                                        const void *value_ptr)
{
    return register_point(name, EFW_DEBUG_SOURCE_CUSTOM, type, value_ptr);
}

int efw_debug_register_custom_batch(const efw_debug_point_t *points, uint16_t count)
{
    if (!points) {
        return -1;
    }

    int registered = 0;

    for (uint16_t i = 0; i < count; i++) {
        efw_status_t ret = register_point(
            points[i].name,
            EFW_DEBUG_SOURCE_CUSTOM,
            points[i].type,
            points[i].value_ptr
        );
        if (ret == EFW_OK) {
            registered++;
        }
    }

    return registered;
}

efw_status_t efw_debug_unregister(const char *name)
{
    if (!name) {
        return EFW_ERR_INVALID;
    }

    efw_debug_point_t *point = find_by_name(name);
    if (!point) {
        return EFW_ERR_NOT_FOUND;
    }

    /* 清除监控点 */
    point->registered = 0;
    memset(point->name, 0, sizeof(point->name));
    point->value_ptr = NULL;

    if (g_debug.point_count > 0) {
        g_debug.point_count--;
    }

    return EFW_OK;
}

efw_status_t efw_debug_find(const char *name, const efw_debug_point_t **out_point)
{
    if (!name || !out_point) {
        return EFW_ERR_INVALID;
    }

    const efw_debug_point_t *point = find_by_name(name);
    if (!point) {
        *out_point = NULL;
        return EFW_ERR_NOT_FOUND;
    }

    *out_point = point;
    return EFW_OK;
}
