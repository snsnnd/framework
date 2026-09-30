#include "efw/core/config.h"
#include "efw/core/scheduler.h"
#include "efw/core/diagnostic.h"
#include "efw/core/registry.h"

#if EFW_ENABLE_SCHEDULER

/**
 * @brief 任务运行时槽位数组池
 * 存放所有任务的运行时状态、调度统计信息；编译期静态分配，无malloc。
 * 有效任务范围：g_slots[0 ... g_task_n‑1]，其余为空闲槽位
 */
static efw_scheduler_slot_t g_slots[EFW_MAX_SCHEDULER_TASKS];

/** @brief 当前已注册的有效任务数量 */
static size_t g_task_n;

/** @brief 模块初始化标记，1：已执行 efw_scheduler_init；0：未初始化 */
static uint8_t g_initialized;

/**
 * @brief 运行保护标志
 * 1：正在执行 efw_scheduler_tick() 或者 efw_scheduler_enumerate()
 * 此时禁止注册/注销/暂停/恢复任务，防止任务数组被篡改。
 * 注意：仅软件逻辑标记，**不提供中断互斥保护**。
 */
static uint8_t g_running;

/** @brief 是否至少执行过一次 tick；用于新注册任务计算首次释放时间基准 */
static uint8_t g_has_tick;

/** @brief 上一次tick记录的毫秒时间戳，作为新注册任务时间参考 */
static uint32_t g_last_tick_ms;

/** @brief 外部注入：获取系统毫秒单调时钟回调；为NULL则使用tick入参elapsed_ms */
static efw_scheduler_time_ms_fn_t g_time_ms;

/** @brief 外部注入：获取系统微秒单调时钟回调；为NULL则不统计任务运行耗时 */
static efw_scheduler_time_us_fn_t g_time_us;

/** @brief 时间回调的用户私有上下文，原样透传给 g_time_ms / g_time_us */
static void* g_time_user;

/** @brief Trace追踪回调；任务开始、结束时触发；传NULL关闭trace功能 */
static efw_scheduler_trace_fn_t g_trace;

/** @brief Trace回调的用户私有上下文，原样透传给 g_trace */
static void* g_trace_user;


/* 计数器饱和，避免长期运行后统计值回绕成很小的数字。 */
static uint32_t saturating_add_u32(uint32_t value, uint32_t increment) {
    return increment > UINT32_MAX - value ? UINT32_MAX : value + increment;
}

// 注册任务前校验 `efw_scheduler_task_def_t` 静态定义是否合法，拦截非法参数。
static efw_status_t validate_task(const efw_scheduler_task_def_t *task) {
    if (!task || !task->fn) return EFW_ERR_INVALID;
    if (!task->name || task->period_ms == 0 || task->period_ms > (uint32_t)INT32_MAX) return EFW_ERR_RANGE;
    /*
        !task->name：任务名字为空指针，框架靠名字查找任务、打印诊断日志，不允许无名任务。
        task->period_ms == 0：周期为 0，不能做周期调度。
        task->period_ms > (uint32_t)INT32_MAX：周期不能大于 `INT32_MAX(2147483647)` ms。
    */
    return EFW_OK;
}

/* 清理槽位中的运行时状态；任务定义按值内嵌，这里仅清空字段，不涉及释放。 */
static void clear_slot(efw_scheduler_slot_t *slot) {
    slot->def.name = 0;
    slot->def.period_ms = 0;
    slot->def.fn = 0;
    slot->def.ctx = 0;
    slot->next_release_ms = 0;
    slot->last_exec_ms = 0;
    slot->run_count = 0;
    slot->missed_releases = 0;
    slot->overrun_count = 0;
    slot->last_start_lateness_ms = 0;
    slot->max_start_lateness_ms = 0;
    slot->last_runtime_us = 0;
    slot->max_runtime_us = 0;
    slot->active = 0;
    slot->release_pending = 0;
}

// 初始化调度器
efw_status_t efw_scheduler_init(void) {
    g_task_n = 0;
    g_initialized = 1;
    g_running = 0;
    g_has_tick = 0;
    g_last_tick_ms = 0;
    g_time_ms = 0;
    g_time_us = 0;
    g_time_user = 0;
    for (size_t i = 0; i < EFW_MAX_SCHEDULER_TASKS; ++i) {
        clear_slot(&g_slots[i]);
    }
    return EFW_OK;
}


efw_status_t efw_scheduler_register(const efw_scheduler_task_def_t *task) {
    /* 默认采用“注册后一个周期”作为首次释放点，避免注册瞬间突发执行。 */
    uint32_t first_release_ms = task ? task->period_ms : 0u;
    // 如果没有时间源、也从未跑过 tick，兜底：第一次触发时间 = task->period_ms

    if (task && g_time_ms) {
        // 已经注入毫秒时间源 g_time_ms
        first_release_ms = g_time_ms(g_time_user) + task->period_ms;

    } else if (task && g_has_tick) {
        // 没有注入时间源，但已经执行过至少一次 tick
        first_release_ms = g_last_tick_ms + task->period_ms;
    }
    return efw_scheduler_register_at(task, first_release_ms); // 自动计算第一次触发的时间点
}

// 实际注册
efw_status_t efw_scheduler_register_at(const efw_scheduler_task_def_t *task, uint32_t first_release_ms) {
    efw_status_t s = validate_task(task);
    if (s != EFW_OK) return s;
    // 校验任务的静态定义是否有问题

    if (g_running) return EFW_ERR_NOT_READY;
    // 运行时保护：tick /enumerate 执行中禁止注册

    if (!g_initialized) {
        efw_scheduler_init();
    }
    // 调度器没有初始化过

    for (size_t i = 0; i < g_task_n; ++i) {
        if (efw_name_eq(g_slots[i].def.name, task->name)) {
            efw_diag_set(EFW_ERR_ALREADY_EXISTS, "scheduler", task->name, "duplicate task name");
            return EFW_ERR_ALREADY_EXISTS;
        }
    }
    // 查重，遍历已注册任务，用名字比对；名字重复返回`EFW_ERR_ALREADY_EXISTS`，同时写入诊断日志。

    if (g_task_n >= EFW_MAX_SCHEDULER_TASKS) {
        efw_diag_set(EFW_ERR_FULL, "scheduler", task->name, "task pool full");
        return EFW_ERR_FULL;
    }
    // 查看注册任务数量是否达到上限

    clear_slot(&g_slots[g_task_n]);
    // 清空新槽位，避免旧数据残留


    // 按值拷贝任务定义进槽位：栈局部定义在函数返回后依然安全（name 仍须为静态字符串）
    g_slots[g_task_n].def = *task;
    // 设置首次触发绝对时间戳
    g_slots[g_task_n].next_release_ms = first_release_ms;
    // 注册完成直接激活任务
    g_slots[g_task_n].active = 1;
    // 有效任务计数自增
    g_task_n++;

    return EFW_OK;
}

// 注销任务
efw_status_t efw_scheduler_unregister(const char *name) {
    if (g_running) return EFW_ERR_NOT_READY;
    // 在运行时禁止操作

    for (size_t i = 0; i < g_task_n; ++i) {
        if (efw_name_eq(g_slots[i].def.name, name)) {
            for (size_t j = i; j < g_task_n - 1; ++j) {
                g_slots[j] = g_slots[j + 1];
            }
            // 找到下标i，数组前移：把后面任务全部往前挪一位，覆盖i位置

            g_task_n--;
            clear_slot(&g_slots[g_task_n]);
            return EFW_OK;
        }
    }
    return EFW_ERR_NOT_FOUND;
}

// 暂停任务
efw_status_t efw_scheduler_pause(const char *name) {
    if (g_running) return EFW_ERR_NOT_READY;

    for (size_t i = 0; i < g_task_n; ++i) {
        if (efw_name_eq(g_slots[i].def.name, name)) {
            g_slots[i].active = 0;
            // 激活状态调为0
            return EFW_OK;
        }
    }
    return EFW_ERR_NOT_FOUND;
}

// 恢复任务
efw_status_t efw_scheduler_resume(const char *name) {
    if (g_running) return EFW_ERR_NOT_READY;

    for (size_t i = 0; i < g_task_n; ++i) {
        if (efw_name_eq(g_slots[i].def.name, name)) {
            if (g_slots[i].active) return EFW_OK;
            g_slots[i].active = 1;

            g_slots[i].release_pending = 1;
            // 强制更新next_release_ms为当前 tick 时间 + 周期，重置调度计时
            // 防止补跑过去错过的周期
            return EFW_OK;
        }
    }
    return EFW_ERR_NOT_FOUND;
}

// 调度器的核心
efw_status_t efw_scheduler_tick(uint32_t elapsed_ms) {
    if (!g_initialized) return EFW_ERR_NOT_READY;
    if (g_running) return EFW_ERR_NOT_READY;

    /* tick 参数和外部时钟均为绝对毫秒时间，与公共头文件及生成器一致。 */
    if (g_time_ms) {
        g_last_tick_ms = g_time_ms(g_time_user);
    } else {
        g_last_tick_ms = elapsed_ms;
    }
    g_has_tick = 1;
    // 标记已经执行过 tick，新注册任务可以以此作为时间基准
    g_running = 1;
    // 进入运行态
    /* g_running 同时是重入保护和回调期间禁止修改任务表的状态标记。 */
    
    for (size_t i = 0; i < g_task_n; ++i) {
        // 开始执行任务表

        efw_scheduler_slot_t *slot = &g_slots[i];

        if (!slot->active) continue;
        // 未激活，继续下一个任务

        uint32_t now_ms = g_time_ms ? g_time_ms(g_time_user) : g_last_tick_ms;
        /* 每次任务使用同一绝对时间基准；有外部时钟时允许更新。 */
        if (slot->release_pending) {
            slot->next_release_ms = now_ms;
            // 周期基于理论到期时刻，不跟随任务结束时间，虽然当次运行可能推迟，但不会导致越跑越慢，后续的运行周期更固定
            slot->release_pending = 0;
        }

        int32_t lateness = (int32_t)(now_ms - slot->next_release_ms);
        // 当前时间 − 任务下次到期时间。
        if (lateness < 0) continue;
        // 没到执行时间，跳过本次任务

        /* 如果 tick 迟到多个周期，只执行一次，把其余释放记为 skipped。 */
        uint32_t skipped = (uint32_t)lateness / slot->def.period_ms;
        slot->missed_releases = saturating_add_u32(slot->missed_releases, skipped);

        slot->last_start_lateness_ms = (uint32_t)lateness;
        if (slot->last_start_lateness_ms > slot->max_start_lateness_ms) {
            slot->max_start_lateness_ms = slot->last_start_lateness_ms;
        }
        // 记录本次任务迟到多少 ms，更新最大迟到统计

        slot->next_release_ms += (skipped + 1u) * slot->def.period_ms;
        // 计算下一次到期时间：跳过已经错过的skipped个周期，再前进 1 个周期

        slot->last_exec_ms = now_ms;
        slot->run_count = saturating_add_u32(slot->run_count, 1u);
        // 上一次执行时间并计数

        if (g_trace) g_trace("scheduler.task.begin", slot, EFW_OK, now_ms, g_trace_user);
        // 开启 trace 时，抛出任务开始事件，可以做日志、性能观测

        uint32_t start_us = g_time_us ? g_time_us(g_time_user) : 0u;
        efw_status_t s = slot->def.fn(slot->def.ctx);
        slot->last_runtime_us = g_time_us ? (g_time_us(g_time_user) - start_us) : 0u;
        if (slot->last_runtime_us > slot->max_runtime_us) {
            slot->max_runtime_us = slot->last_runtime_us;
        }
        // 执行用户任务回调，测量运行耗时

        if ((uint64_t)slot->last_runtime_us >= (uint64_t)slot->def.period_ms * 1000u) {
            slot->overrun_count = saturating_add_u32(slot->overrun_count, 1u);
        }
        // 任务运行耗时 ≥ 任务周期（ms 转 us），说明任务执行时间超过分配周期，CPU 负载过高；超限计数器 + 1。
       
        if (g_trace) g_trace("scheduler.task.end", slot, s, now_ms, g_trace_user);
        // 结束 trace

        if (s != EFW_OK) {
            efw_diag_set(s, "scheduler", slot->def.name, "task failed");
            g_running = 0;
            return s;
        }
    }
    g_running = 0;
    return EFW_OK;
}

// 获取注册任务数量
uint32_t efw_scheduler_task_count(void) {
    return (uint32_t)g_task_n;
}

// 判读这个任务是否注册
efw_status_t efw_scheduler_get(const char *name, const efw_scheduler_slot_t **out_slot) {
    if (!name || !out_slot) return EFW_ERR_INVALID;
    for (size_t i = 0; i < g_task_n; ++i) {
        if (efw_name_eq(g_slots[i].def.name, name)) {
            *out_slot = &g_slots[i];
            return EFW_OK;
        }
    }
    *out_slot = 0;
    return EFW_ERR_NOT_FOUND;
}

/**
 * @brief 遍历所有已注册任务，调用用户回调
 * @param callback 遍历回调函数，接收slot指针与user上下文，不能为NULL
 * @param user 用户自定义上下文，透传给callback
 * @note 复用g_running互斥锁：tick运行时直接返回；遍历期间禁止调用register/unregister/pause/resume/tick
 * @note 回调内拿到的是原始slot指针；禁止在回调中执行会修改任务表的接口
 */
void efw_scheduler_enumerate(efw_scheduler_enumerate_fn callback, void* user) {
    // 回调为空 或者 tick正在执行，直接返回，不执行遍历
    if (!callback || g_running) return;

    // 置保护标记，锁住任务表，禁止外部修改任务、禁止进入tick
    g_running = 1;
    // 按注册顺序遍历全部有效任务
    for (size_t i = 0; i < g_task_n; ++i) {
        callback(&g_slots[i], user);
    }
    // 遍历完成，释放保护标记
    g_running = 0;
}


/**
 * @brief 设置调度器时间源回调，提供ms/us时间。
 * @param time_ms 毫秒回调，传NULL则使用tick入参elapsed_ms
 * @param time_us 微秒回调，传NULL关闭任务耗时统计
 * @param user 透传给时间回调的用户上下文
 * @retval EFW_OK 设置成功
 * @retval EFW_ERR_NOT_READY tick正在运行 或者 已经存在注册任务，禁止修改时间源
 * @note 必须在尚未注册任何任务的初始化阶段调用；运行时切换时间源会破坏任务时间戳
 */
efw_status_t efw_scheduler_set_time_providers(efw_scheduler_time_ms_fn_t time_ms,
    efw_scheduler_time_us_fn_t time_us,
    void* user) {
    // 调度正在运行，或者已经存在任务，禁止更换时间基准
    if (g_running || g_task_n != 0u)
        return EFW_ERR_NOT_READY;

    g_time_ms = time_ms;
    g_time_us = time_us;
    g_time_user = user;
    return EFW_OK;
}

/**
 * @brief 设置trace事件钩子，接收任务begin/end事件；callback传NULL关闭trace
 * @param callback trace回调函数
 * @param user 用户上下文，透传给trace回调
 * @note 当前原版无保护：tick运行时修改存在函数指针撕裂风险；建议改为返回efw_status_t并增加g_running判断
 */
void efw_scheduler_set_trace_callback(efw_scheduler_trace_fn_t callback, void* user) {
    g_trace = callback;
    g_trace_user = user;
}

#endif
