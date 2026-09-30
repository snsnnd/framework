/**
 * @file    efw_debug.c
 * @brief   EFW 在线调试模块核心实现
 */

#include "efw/debug/efw_debug.h"
#include "efw/app/runtime.h"
#include "efw/hal/hal.h"
#include "efw/device/sensor.h"
#include "efw/algorithm/registry.h"
#include "efw/state/state_machine.h"
#if EFW_ENABLE_SCHEDULER
#include "efw/core/scheduler.h"
#endif
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

static efw_debug_event_sink_fn g_debug_event_sink;
static void *g_debug_event_user;

#if EFW_ENABLE_ALGORITHM
typedef struct {
    uint32_t type;
    uint32_t ctx_addr;
} efw_debug_algo_snapshot_t;

static efw_debug_algo_snapshot_t g_algo_debug[EFW_MAX_ALGOS];
static uint16_t g_algo_debug_count;
#endif

#if EFW_ENABLE_STATE_MACHINE
typedef struct {
    efw_sm_context_t *ctx;
    uint32_t state_hash;
    uint32_t time_ms;
} efw_debug_sm_snapshot_t;

static efw_debug_sm_snapshot_t g_sm_debug[EFW_MAX_STATE_MACHINES];
static uint16_t g_sm_debug_count;
#endif

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

#if EFW_ENABLE_STATE_MACHINE
static uint32_t debug_hash_string(const char *text)
{
    uint32_t hash = 2166136261u;
    if (!text) {
        return 0u;
    }
    while (*text) {
        hash ^= (uint8_t)(*text++);
        hash *= 16777619u;
    }
    return hash;
}
#endif

#if EFW_ENABLE_ALGORITHM
static uint32_t debug_ptr_to_u32(const void *ptr)
{
    uintptr_t value = (uintptr_t)ptr;
    uint32_t hash = (uint32_t)value;
#if UINTPTR_MAX > UINT32_MAX
    hash ^= (uint32_t)(value >> 32);
#endif
    return hash;
}
#endif

static void update_dynamic_debug_points(void)
{
#if EFW_ENABLE_STATE_MACHINE
    for (uint16_t i = 0; i < g_sm_debug_count; ++i) {
        efw_sm_context_t *ctx = g_sm_debug[i].ctx;
        if (!ctx) {
            continue;
        }
        g_sm_debug[i].state_hash = debug_hash_string(efw_sm_current_state(ctx));
        g_sm_debug[i].time_ms = efw_sm_time_in_state(ctx);
    }
#endif
}

static void debug_app_trace_callback(const char *event,
                                     const char *name,
                                     efw_status_t status,
                                     uint32_t mcu_time_ms,
                                     uint32_t duration_ms,
                                     void *user)
{
    char detail[96];
    (void)user;
    if (duration_ms == EFW_APP_TRACE_DURATION_UNKNOWN) {
        snprintf(detail, sizeof(detail), "status=%d mcu_time_ms=%lu duration_ms=unknown", (int)status, (unsigned long)mcu_time_ms);
    } else {
        snprintf(detail, sizeof(detail), "status=%d mcu_time_ms=%lu duration_ms=%lu", (int)status, (unsigned long)mcu_time_ms, (unsigned long)duration_ms);
    }
    efw_debug_emit_event(event, name, detail);
}

#if EFW_ENABLE_SCHEDULER
static void debug_scheduler_trace_callback(const char *event,
                                           const efw_scheduler_slot_t *slot,
                                           efw_status_t status,
                                           uint32_t now_ms,
                                           void *user)
{
    char detail[128];
    (void)user;
    if (!slot || !slot->def.fn) return;
    snprintf(detail, sizeof(detail),
             "status=%d mcu_time_ms=%lu lateness_ms=%lu runtime_us=%lu missed=%lu overruns=%lu",
             (int)status,
             (unsigned long)now_ms,
             (unsigned long)slot->last_start_lateness_ms,
             (unsigned long)slot->last_runtime_us,
             (unsigned long)slot->missed_releases,
             (unsigned long)slot->overrun_count);
    efw_debug_emit_event(event, slot->def.name, detail);
}
#endif

#if EFW_ENABLE_STATE_MACHINE
static void debug_sm_trace_callback(const efw_sm_context_t *ctx,
                                    const char *from_state,
                                    const char *to_state,
                                    uint32_t time_in_state_ms,
                                    void *user)
{
    char name[EFW_DEBUG_NAME_MAX_LEN];
    char detail[96];
    (void)user;
    snprintf(name, sizeof(name), "sm.%s", (ctx && ctx->name) ? ctx->name : "unknown");
    snprintf(detail, sizeof(detail), "from=%s to=%s mcu_time_ms=%lu duration_ms=%lu time_in_state_ms=%lu",
             from_state ? from_state : "",
             to_state ? to_state : "",
             ctx ? (unsigned long)ctx->elapsed_ms : 0ul,
             (unsigned long)time_in_state_ms,
             (unsigned long)time_in_state_ms);
    efw_debug_emit_event("sm.transition", name, detail);
}
#endif

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

/* ==================================================================
 *  算法数据采集回调
 * ================================================================== */

#if EFW_ENABLE_ALGORITHM
static void algo_register_callback(const efw_algo_ops_t *ops, void *user)
{
    int *count = (int *)user;
    char name[EFW_DEBUG_NAME_MAX_LEN];
    efw_status_t ret;

    if (!ops || g_algo_debug_count >= EFW_MAX_ALGOS) {
        return;
    }

    g_algo_debug[g_algo_debug_count].type = (uint32_t)ops->type;
    g_algo_debug[g_algo_debug_count].ctx_addr = debug_ptr_to_u32(ops->ctx);

    snprintf(name, sizeof(name), "algo.%s.type", ops->name);
    ret = register_point(name, EFW_DEBUG_SOURCE_ALGORITHM,
                         EFW_DEBUG_TYPE_U32, &g_algo_debug[g_algo_debug_count].type);
    if (ret == EFW_OK) {
        (*count)++;
    }

    snprintf(name, sizeof(name), "algo.%s.ctx", ops->name);
    ret = register_point(name, EFW_DEBUG_SOURCE_ALGORITHM,
                         EFW_DEBUG_TYPE_U32, &g_algo_debug[g_algo_debug_count].ctx_addr);
    if (ret == EFW_OK) {
        (*count)++;
    }

    g_algo_debug_count++;
}
#endif /* EFW_ENABLE_ALGORITHM */

/* ==================================================================
 *  状态机数据采集
 * ================================================================== */

#if EFW_ENABLE_STATE_MACHINE
static void sm_register_callback(efw_sm_context_t *ctx, void *user)
{
    int *count = (int *)user;
    char name[EFW_DEBUG_NAME_MAX_LEN];
    efw_status_t ret;

    if (!ctx || !ctx->name || g_sm_debug_count >= EFW_MAX_STATE_MACHINES) {
        return;
    }

    g_sm_debug[g_sm_debug_count].ctx = ctx;
    g_sm_debug[g_sm_debug_count].state_hash = debug_hash_string(efw_sm_current_state(ctx));
    g_sm_debug[g_sm_debug_count].time_ms = efw_sm_time_in_state(ctx);

    snprintf(name, sizeof(name), "sm.%s.state_hash", ctx->name);
    ret = register_point(name, EFW_DEBUG_SOURCE_STATE_MACHINE,
                         EFW_DEBUG_TYPE_U32, &g_sm_debug[g_sm_debug_count].state_hash);
    if (ret == EFW_OK) {
        (*count)++;
    }

    snprintf(name, sizeof(name), "sm.%s.time_ms", ctx->name);
    ret = register_point(name, EFW_DEBUG_SOURCE_STATE_MACHINE,
                         EFW_DEBUG_TYPE_U32, &g_sm_debug[g_sm_debug_count].time_ms);
    if (ret == EFW_OK) {
        (*count)++;
    }

    g_sm_debug_count++;
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
#if EFW_ENABLE_ALGORITHM
    g_algo_debug_count = 0;
    memset(g_algo_debug, 0, sizeof(g_algo_debug));
#endif
#if EFW_ENABLE_STATE_MACHINE
    g_sm_debug_count = 0;
    memset(g_sm_debug, 0, sizeof(g_sm_debug));
#endif

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

    update_dynamic_debug_points();

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

void efw_debug_set_event_sink(efw_debug_event_sink_fn sink, void *user)
{
    g_debug_event_sink = sink;
    g_debug_event_user = user;
}

void efw_debug_emit_event(const char *event, const char *name, const char *detail)
{
    if (g_debug_event_sink) {
        g_debug_event_sink(event ? event : "event", name ? name : "", detail ? detail : "", g_debug_event_user);
    }
}

void efw_debug_attach_runtime_trace(void)
{
    efw_app_set_trace_callback(debug_app_trace_callback, NULL);
#if EFW_ENABLE_SCHEDULER
    efw_scheduler_set_trace_callback(debug_scheduler_trace_callback, NULL);
#endif
#if EFW_ENABLE_STATE_MACHINE
    efw_sm_set_trace_callback(debug_sm_trace_callback, NULL);
#endif
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
    /* Sensor output type/storage is not described by efw_sensor_ops_t. */
    return 0;
}

efw_status_t efw_debug_register_sensor_value(const char *sensor_name,
                                             efw_debug_type_t type,
                                             const void *latest_value)
{
    char name[EFW_DEBUG_NAME_MAX_LEN];
    if (!sensor_name || !latest_value) {
        return EFW_ERR_INVALID;
    }
    (void)snprintf(name, sizeof(name), "sensor.%s", sensor_name);
    return register_point(name, EFW_DEBUG_SOURCE_SENSOR, type, latest_value);
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
    int count = 0;
    efw_sm_enumerate(sm_register_callback, &count);
    return count;
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
