/**
 * @file    efw_debug_runtime.h
 * @brief   EFW 运行时调试数据采集
 *
 * 采集 MCU 运行时的详细信息：
 *   - 任务执行时间和周期
 *   - 模块状态和生命周期
 *   - 事件发布/订阅活动
 *   - 数据流追踪
 *   - 资源使用情况
 */

#ifndef EFW_DEBUG_RUNTIME_H
#define EFW_DEBUG_RUNTIME_H

#include "efw/core/common.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ==================================================================
 *  配置
 * ================================================================== */

#ifndef EFW_DEBUG_MAX_TASKS
#define EFW_DEBUG_MAX_TASKS 16
#endif

#ifndef EFW_DEBUG_MAX_MODULES
#define EFW_DEBUG_MAX_MODULES 32
#endif

#ifndef EFW_DEBUG_MAX_TOPICS
#define EFW_DEBUG_MAX_TOPICS 16
#endif

#ifndef EFW_DEBUG_MAX_DATAFLOW
#define EFW_DEBUG_MAX_DATAFLOW 32
#endif

/* ==================================================================
 *  类型定义
 * ================================================================== */

/**
 * @brief 任务类型
 */
typedef enum {
    EFW_TASK_PERIODIC = 0,      /**< 周期任务 */
    EFW_TASK_EVENT_DRIVEN,      /**< 事件驱动任务 */
    EFW_TASK_ONESHOT,           /**< 一次性任务 */
} efw_task_type_t;

/**
 * @brief 任务状态
 */
typedef enum {
    EFW_TASK_IDLE = 0,          /**< 空闲 */
    EFW_TASK_RUNNING,           /**< 运行中 */
    EFW_TASK_BLOCKED,           /**< 阻塞 */
    EFW_TASK_ERROR,             /**< 错误 */
} efw_task_state_t;

/**
 * @brief 模块生命周期状态
 */
typedef enum {
    EFW_MODULE_UNINIT = 0,      /**< 未初始化 */
    EFW_MODULE_INIT,            /**< 已初始化 */
    EFW_MODULE_STARTED,         /**< 已启动 */
    EFW_MODULE_STOPPED,         /**< 已停止 */
    EFW_MODULE_ERROR,           /**< 错误 */
} efw_module_state_t;

/**
 * @brief 事件方向
 */
typedef enum {
    EFW_EVENT_PUBLISH = 0,      /**< 发布 */
    EFW_EVENT_SUBSCRIBE,        /**< 订阅 */
    EFW_EVENT_UNSUBSCRIBE,      /**< 取消订阅 */
} efw_event_direction_t;

/**
 * @brief 任务运行时统计
 */
typedef struct {
    const char *name;                   /* 任务名称 */
    efw_task_type_t type;               /* 任务类型 */
    efw_task_state_t state;             /* 当前状态 */
    
    uint32_t expected_period_us;        /* 预期周期（微秒） */
    uint32_t actual_period_us;          /* 实际周期（微秒） */
    uint32_t execution_time_us;         /* 执行时间（微秒） */
    uint32_t max_execution_time_us;     /* 最大执行时间 */
    uint32_t min_execution_time_us;     /* 最小执行时间 */
    
    uint32_t run_count;                 /* 运行次数 */
    uint32_t error_count;               /* 错误次数 */
    uint32_t overrun_count;             /* 超时次数 */
    
    uint64_t last_run_time;             /* 上次运行时间 */
    uint64_t total_execution_time;      /* 总执行时间 */
} efw_debug_task_info_t;

/**
 * @brief 模块运行时信息
 */
typedef struct {
    const char *name;                   /* 模块名称 */
    efw_module_state_t state;           /* 当前状态 */
    
    uint32_t init_time_us;              /* 初始化耗时 */
    uint32_t poll_count;                /* 轮询次数 */
    uint32_t avg_poll_time_us;          /* 平均轮询时间 */
    uint32_t max_poll_time_us;          /* 最大轮询时间 */
    
    uint32_t error_count;               /* 错误次数 */
    uint64_t last_activity_time;        /* 上次活动时间 */
} efw_debug_module_info_t;

/**
 * @brief 事件话题信息
 */
typedef struct {
    const char *name;                   /* 话题名称 */
    uint16_t topic_id;                  /* 话题 ID */
    
    uint16_t publisher_count;           /* 发布者数量 */
    uint16_t subscriber_count;          /* 订阅者数量 */
    
    uint32_t publish_count;             /* 发布次数 */
    uint32_t receive_count;             /* 接收次数 */
    uint32_t drop_count;                /* 丢弃次数 */
    
    uint64_t last_publish_time;         /* 上次发布时间 */
    uint64_t last_receive_time;         /* 上次接收时间 */
} efw_debug_topic_info_t;

/**
 * @brief 数据流节点
 */
typedef struct {
    const char *source_name;            /* 源名称 */
    const char *sink_name;              /* 目标名称 */
    const char *data_type;              /* 数据类型 */
    
    uint32_t transfer_count;            /* 传输次数 */
    uint32_t last_value_size;           /* 最后值大小 */
    uint8_t last_value[32];             /* 最后传输的值 */
    
    uint64_t last_transfer_time;        /* 上次传输时间 */
} efw_debug_dataflow_t;

/**
 * @brief 运行时快照（完整状态）
 */
typedef struct {
    uint64_t timestamp;                 /* 时间戳 */
    uint32_t uptime_ms;                 /* 运行时间 */
    
    /* 任务信息 */
    uint16_t task_count;
    efw_debug_task_info_t tasks[EFW_DEBUG_MAX_TASKS];
    
    /* 模块信息 */
    uint16_t module_count;
    efw_debug_module_info_t modules[EFW_DEBUG_MAX_MODULES];
    
    /* 话题信息 */
    uint16_t topic_count;
    efw_debug_topic_info_t topics[EFW_DEBUG_MAX_TOPICS];
    
    /* 数据流 */
    uint16_t dataflow_count;
    efw_debug_dataflow_t dataflows[EFW_DEBUG_MAX_DATAFLOW];
    
    /* 系统资源 */
    struct {
        uint32_t cpu_usage_percent;     /* CPU 使用率 */
        uint32_t stack_used_bytes;      /* 栈使用量 */
        uint32_t heap_used_bytes;       /* 堆使用量（如果有） */
        uint32_t isr_count;             /* 中断次数 */
        uint32_t context_switch_count;  /* 上下文切换次数 */
    } resources;
    
} efw_debug_runtime_snapshot_t;

/* ==================================================================
 *  API
 * ================================================================== */

/**
 * @brief 初始化运行时调试
 */
efw_status_t efw_debug_runtime_init(void);

/**
 * @brief 注册任务监控
 */
efw_status_t efw_debug_register_task(const char *name, efw_task_type_t type,
                                      uint32_t expected_period_us);

/**
 * @brief 任务开始执行（调用一次）
 */
efw_status_t efw_debug_task_begin(const char *name);

/**
 * @brief 任务结束执行（调用一次）
 */
efw_status_t efw_debug_task_end(const char *name);

/**
 * @brief 注册模块监控
 */
efw_status_t efw_debug_register_module(const char *name);

/**
 * @brief 更新模块状态
 */
efw_status_t efw_debug_update_module_state(const char *name, efw_module_state_t state);

/**
 * @brief 记录模块轮询
 */
efw_status_t efw_debug_module_poll(const char *name, uint32_t duration_us);

/**
 * @brief 注册事件话题
 */
efw_status_t efw_debug_register_topic(const char *name, uint16_t topic_id);

/**
 * @brief 记录事件发布
 */
efw_status_t efw_debug_event_publish(const char *topic_name, uint16_t data_size);

/**
 * @brief 记录事件接收
 */
efw_status_t efw_debug_event_receive(const char *topic_name, uint16_t data_size);

/**
 * @brief 记录数据流
 */
efw_status_t efw_debug_record_dataflow(const char *source, const char *sink,
                                        const void *data, uint16_t size);

/**
 * @brief 获取运行时快照
 */
efw_status_t efw_debug_get_runtime_snapshot(efw_debug_runtime_snapshot_t *snapshot);

/**
 * @brief 导出快照为字节流（用于 LiteTune 传输）
 */
efw_status_t efw_debug_export_runtime(uint8_t *buffer, uint16_t buffer_size,
                                       uint16_t *out_size);

/* ==================================================================
 *  便捷宏
 * ================================================================== */

/** @brief 任务计时宏 */
#define EFW_DEBUG_TASK_SCOPE(name) \
    efw_debug_task_begin(name); \
    for (uint8_t _efw_dbg_i = 1; _efw_dbg_i; _efw_dbg_i = 0, efw_debug_task_end(name))

/** @brief 模块轮询计时宏 */
#define EFW_DEBUG_MODULE_POLL(name, code) do { \
    uint32_t _start = efw_debug_get_us(); \
    code; \
    efw_debug_module_poll(name, efw_debug_get_us() - _start); \
} while(0)

#ifdef __cplusplus
}
#endif

#endif /* EFW_DEBUG_RUNTIME_H */
