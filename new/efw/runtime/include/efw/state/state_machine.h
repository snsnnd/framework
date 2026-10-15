#ifndef EFW_STATE_MACHINE_H
#define EFW_STATE_MACHINE_H

#include "efw/core/common.h"

#ifndef EFW_MAX_STATE_MACHINES
#define EFW_MAX_STATE_MACHINES 8
#endif

/**
 * @brief 状态定义。
 *
 * 状态对象通常由应用以静态或 const 方式定义，状态机只保存指针，不复制
 * 它的名称和回调。on_enter/on_tick/on_exit 都可以为空；回调返回错误时，
 * 当前状态切换或本次 tick 会停止并把错误交给调用方。
 */
typedef struct {
    const char *name;
    void *ctx;
    efw_status_t (*on_enter)(void *ctx);
    efw_status_t (*on_tick)(void *ctx);
    efw_status_t (*on_exit)(void *ctx);
} efw_state_def_t;

/** @brief 状态定义的兼容别名，便于把状态表看作状态机操作表。 */
typedef efw_state_def_t efw_state_machine_ops_t;

/**
 * @brief 一条状态转移规则。
 *
 * from 为 NULL 表示全局规则，否则只对当前状态匹配；timeout_ms 和
 * condition 任一满足即可触发。priority 越大越优先，数组中同优先级的
 * 后一条规则会覆盖前一条，因此应避免依赖未写明的顺序。
 */
typedef struct {
    const efw_state_def_t *from;
    const efw_state_def_t *to;
    int (*condition)(void);
    efw_status_t (*action)(void);
    uint32_t timeout_ms;
    uint8_t priority;
} efw_sm_transition_t;

/**
 * @brief 状态机实例的可变运行时上下文。
 *
 * transitions 指向应用提供的静态规则数组，transition_count 是元素个数。
 * elapsed_ms 不由状态机自动读取时钟，必须由应用通过 efw_sm_set_elapsed()
 * 更新时间基准；这样既适合裸机，也适合测试和 RTOS。
 */
typedef struct {
    const char *name;
    const efw_state_def_t *current;
    const efw_sm_transition_t *transitions;
    uint8_t transition_count;
    uint32_t entered_ms;
    uint32_t elapsed_ms;
} efw_sm_context_t;

/** @brief 遍历状态机注册表的回调。 */
typedef void (*efw_sm_enumerate_fn)(efw_sm_context_t *ctx, void *user);

/** @brief 状态切换追踪回调；只在成功切换后调用。 */
typedef void (*efw_sm_trace_fn_t)(const efw_sm_context_t *ctx,
                                  const char *from_state,
                                  const char *to_state,
                                  uint32_t time_in_state_ms,
                                  void *user);

/**
 * @brief 初始化实例并进入 initial 状态。
 *
 * 初始化会立即执行 initial->on_enter；它不会自动注册实例。
 */
efw_status_t efw_sm_init(efw_sm_context_t *ctx, const char *name,
                          const efw_state_def_t *initial,
                           const efw_sm_transition_t *transitions, uint8_t count);

/** @brief 执行当前状态的 on_tick，并择优执行一条满足条件的转移。 */
efw_status_t efw_sm_tick(efw_sm_context_t *ctx);

/** @brief 显式执行 exit -> 切换 current -> enter。 */
efw_status_t efw_sm_transition_to(efw_sm_context_t *ctx, const efw_state_def_t *target);

/** @brief 替换实例使用的转移表；调用方负责保证数组生命周期。 */
efw_status_t efw_sm_set_transitions(efw_sm_context_t *ctx, const efw_sm_transition_t *transitions, uint8_t count);

/** @brief 获取当前状态名称；无效上下文返回空字符串。 */
const char *efw_sm_current_state(const efw_sm_context_t *ctx);

/** @brief 获取当前状态定义指针；无效上下文返回 NULL。 */
const efw_state_def_t *efw_sm_current_def(const efw_sm_context_t *ctx);

/** @brief 返回当前时间基准与进入状态时间的差值。 */
uint32_t efw_sm_time_in_state(const efw_sm_context_t *ctx);

/** @brief 设置应用提供的当前时间，不会触发状态回调。 */
void efw_sm_set_elapsed(efw_sm_context_t *ctx, uint32_t elapsed_ms);

/** @brief 设置或清除状态切换追踪回调。 */
void efw_sm_set_trace_callback(efw_sm_trace_fn_t callback, void *user);

/** @brief 清空状态机注册表；不释放应用拥有的上下文。 */
efw_status_t efw_sm_registry_init(void);

/** @brief 注册一个已初始化的状态机上下文，名称必须全局唯一。 */
efw_status_t efw_sm_register(efw_sm_context_t *ctx);

/** @brief 按名称获取状态机上下文。 */
efw_status_t efw_sm_get(const char *name, efw_sm_context_t **out_ctx);

/** @brief 从注册表删除状态机指针，不销毁上下文。 */
efw_status_t efw_sm_unregister(const char *name);

/** @brief 返回已注册状态机数量。 */
size_t efw_sm_count(void);

/** @brief 遍历已注册状态机。 */
void efw_sm_enumerate(efw_sm_enumerate_fn fn, void *user);

#endif
