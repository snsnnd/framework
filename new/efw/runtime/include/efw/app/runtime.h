/**
 * @file    runtime.h
 * @brief   Application runtime：按 manifest 执行初始化、注册、绑定和周期更新
 */

#ifndef EFW_APP_RUNTIME_H
#define EFW_APP_RUNTIME_H

#include "efw/core/common.h"

/**
 * @brief Graph/application 输入端口的运行时视图。
 *
 * data 是借用指针；valid 表示 codegen 或应用绑定阶段是否确认该端口可用，
 * expected_size 可用于在复制前做数据契约检查。
 */
typedef struct {
    const char *port;
    const char *contract;
    const char *c_type;
    const void *data;
    uint16_t size;
    uint16_t expected_size;
    uint8_t valid;
} efw_app_input_view_t;

/** @brief 一组同类输入端口及当前选中的端口。 */
typedef struct {
    const efw_app_input_view_t *ports;
    uint8_t count;
    const char *active_port;
} efw_app_multi_input_t;

/** @brief 按端口名在线性表中查找输入视图，不分配内存。 */
static inline const efw_app_input_view_t *efw_app_multi_input_get(const efw_app_multi_input_t *input, const char *port) {
    uint8_t i;
    if (!input || !port) return 0;
    for (i = 0; i < input->count; ++i) {
        const efw_app_input_view_t *item = &input->ports[i];
        const char *a = item->port;
        const char *b = port;
        if (!a) continue;
        while (*a && *b && (*a == *b)) {
            ++a;
            ++b;
        }
        if (*a == '\0' && *b == '\0') return item;
    }
    return 0;
}

/** @brief manifest 各阶段的无参数执行函数；返回错误会中止后续阶段。 */
typedef efw_status_t (*efw_app_step_fn_t)(void);

/** @brief 应用运行时使用的毫秒单调时钟。 */
typedef uint32_t (*efw_app_time_ms_fn_t)(void *user);

/**
 * @brief 应用阶段追踪回调。
 * duration_ms 为 EFW_APP_TRACE_DURATION_UNKNOWN 时表示无法测量。
 */
typedef void (*efw_app_trace_fn_t)(const char *event, const char *name, efw_status_t status, uint32_t mcu_time_ms, uint32_t duration_ms, void *user);

/** @brief 表示本次追踪事件没有可用的耗时值。 */
#define EFW_APP_TRACE_DURATION_UNKNOWN 0xFFFFFFFFu

/**
 * @brief 应用启动阶段清单。
 *
 * 固定顺序为：初始化池 -> 注册平台 HAL -> 注册组件 -> 绑定句柄。所有
 * 指针均可为空；空步骤视为成功跳过。update_1ms 由应用周期性主动调用。
 */
typedef struct {
    efw_app_step_fn_t init_pools;
    efw_app_step_fn_t register_platform;
    efw_app_step_fn_t register_components;
    efw_app_step_fn_t bind_handles;
    efw_app_step_fn_t update_1ms;
} efw_app_manifest_t;

/** @brief 执行 EFW 初始化和 manifest 启动阶段。 */
efw_status_t efw_app_init(const efw_app_manifest_t *manifest);

/** @brief 执行 manifest 的 1ms 更新步骤。 */
efw_status_t efw_app_update_1ms(const efw_app_manifest_t *manifest);

/** @brief 安装/清除应用追踪回调。 */
void efw_app_set_trace_callback(efw_app_trace_fn_t callback, void *user);

/** @brief 安装/清除应用时钟；未安装时返回 0。 */
void efw_app_set_time_provider(efw_app_time_ms_fn_t callback, void *user);

/** @brief 读取当前应用时钟。 */
uint32_t efw_app_current_time_ms(void);

/** @brief 使用当前时钟发出一个无耗时扩展字段的追踪事件。 */
void efw_app_trace_event(const char *event, const char *name, efw_status_t status);

/** @brief 发出带显式时间和耗时的追踪事件。 */
void efw_app_trace_event_ex(const char *event, const char *name, efw_status_t status, uint32_t mcu_time_ms, uint32_t duration_ms);

#endif
