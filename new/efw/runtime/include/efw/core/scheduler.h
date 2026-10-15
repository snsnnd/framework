#ifndef EFW_SCHEDULER_H
#define EFW_SCHEDULER_H
// 调度器模块

#include "efw/core/common.h"

#ifndef EFW_MAX_SCHEDULER_TASKS // 最大的调度任务数量
#define EFW_MAX_SCHEDULER_TASKS 16
#endif

/** @brief 一个周期任务的回调；ctx 由注册定义借用。 */
typedef efw_status_t (*efw_task_fn_t)(void *ctx);

/** @brief 提供单调递增的毫秒时钟；返回值允许 uint32_t 回绕。 */
typedef uint32_t (*efw_scheduler_time_ms_fn_t)(void *user);

/** @brief 提供单调递增的微秒时钟，用于运行时间统计。 */
typedef uint32_t (*efw_scheduler_time_us_fn_t)(void *user);

/**
 * @brief 任务定义。
 *
 * 注册时会按值拷贝一份进调度槽位，因此允许传入栈局部定义（函数返回后依然安全）。
 * name 仍是借用指针：须指向静态/常量字符串，且在任务注销前保持有效。
 * period_ms 同时是调度周期和超时统计的参考周期。
 */
typedef struct {
    const char *name;
    uint32_t period_ms;
    efw_task_fn_t fn;
    void *ctx;
} efw_scheduler_task_def_t;

/**
 * @brief 任务运行时槽位和统计信息。
 *
 * next_release_ms 使用无符号时间差比较；release_pending 用于 resume 后
 * 让任务在下一次 tick 立即获得一次释放，而不是补跑暂停期间的历史周期。
 */
typedef struct {
    efw_scheduler_task_def_t def;         /* 按值内嵌的任务定义（注册时拷贝） */
    uint32_t next_release_ms;             // 下一次任务释放(触发)的系统时间戳(ms)
    uint32_t last_exec_ms;                // 上一次开始执行的时间戳

    uint32_t run_count;                   // 总触发次数
    uint32_t missed_releases;             // 错过释放计数：调度到来时已经晚于next_release_ms，周期被错过
    uint32_t overrun_count;               // 超限计数：任务执行时长超过允许最大时限(CPU过载/任务阻塞)

    uint32_t last_start_lateness_ms;      // 上一次启动延迟：实际启动时刻 − 理论释放时刻(ms)
    uint32_t max_start_lateness_ms;       // 历史最大启动延迟，衡量调度抖动、系统负载

    uint32_t last_runtime_us;             // 上一次任务实际运行耗时(微秒)
    uint32_t max_runtime_us;              // 历史最大运行耗时(us)，用于分析最坏执行时间WCET

    uint8_t active;                       // 任务激活标志：1=启用参与调度；0=挂起不参与释放判断
    uint8_t release_pending;              // 待释放标记：resume恢复后立即触发一次，不补跑暂停丢失的周期
} efw_scheduler_slot_t;

/** @brief 遍历任务槽位的回调；回调期间不应修改调度器。 */
typedef void (*efw_scheduler_enumerate_fn)(const efw_scheduler_slot_t *slot, void *user);
// 注册回调函数
// 只要满足void回参，const efw_scheduler_slot_t *slot, void *user传参，都是efw_scheduler_enumerate_fn类型函数

/**
 * @brief 调度器追踪回调。
 * event 当前为 scheduler.task.begin 或 scheduler.task.end。
 */
typedef void (*efw_scheduler_trace_fn_t)(const char *event,
                                         const efw_scheduler_slot_t *slot,
                                         efw_status_t status,
                                          uint32_t now_ms,
                                          void *user);

/** @brief 清空任务槽位并进入可注册状态。 */
efw_status_t efw_scheduler_init(void);

/** @brief 注册任务；默认首次释放时间为当前基准时间加一个周期。 */
efw_status_t efw_scheduler_register(const efw_scheduler_task_def_t *task);

/** @brief 注册任务并显式指定首次释放的绝对毫秒时间。 */
efw_status_t efw_scheduler_register_at(const efw_scheduler_task_def_t *task, uint32_t first_release_ms);

/** @brief 注销任务；调度器正在 tick/enumerate 时不可调用。 */
efw_status_t efw_scheduler_unregister(const char *name);

/** @brief 暂停任务但保留其统计信息。 */
efw_status_t efw_scheduler_pause(const char *name);

/** @brief 恢复任务，并在下一次 tick 立即释放一次。 */
efw_status_t efw_scheduler_resume(const char *name);

/**
 * @brief 推进一次调度。
 *
 * 没有时间提供者时 elapsed_ms 被当作当前绝对时间；有 time_ms 提供者时
 * 该参数仅作为兼容性占位，实际时间来自回调。每个到期任务本次最多执行一次，
 * 被跳过的周期累加到 missed_releases。
 */
efw_status_t efw_scheduler_tick(uint32_t elapsed_ms);

/** @brief 返回当前已注册任务数。 */
uint32_t efw_scheduler_task_count(void);

/** @brief 按名称获取只读运行时槽位。 */
efw_status_t efw_scheduler_get(const char *name, const efw_scheduler_slot_t **out_slot);

/** @brief 遍历当前任务；遍历期间注册、注销和控制操作会被拒绝。 */
void efw_scheduler_enumerate(efw_scheduler_enumerate_fn callback, void *user);

/**
 * @brief 设置时间源。
 * 必须在注册任务前设置；传 NULL 表示回退到 tick 参数/不统计微秒运行时间。
 */
efw_status_t efw_scheduler_set_time_providers(efw_scheduler_time_ms_fn_t time_ms,
                                              efw_scheduler_time_us_fn_t time_us,
                                              void *user);

/** @brief 设置追踪回调；传 NULL 可关闭追踪。 */
void efw_scheduler_set_trace_callback(efw_scheduler_trace_fn_t callback, void *user);

#endif
