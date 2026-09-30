/**
 * @file    efw_debug_runtime.c
 * @brief   EFW 运行时调试数据采集实现
 */

#include "efw/debug/efw_debug_runtime.h"
#include <string.h>

#if EFW_DEBUG_ENABLE

/* ==================================================================
 *  全局状态
 * ================================================================== */

static efw_debug_runtime_snapshot_t g_runtime = {0};
static uint64_t g_start_time = 0;

/* 任务计时辅助 */
typedef struct {
    uint64_t begin_time;
    uint32_t last_period;
} task_timer_t;

static task_timer_t g_task_timers[EFW_DEBUG_MAX_TASKS] = {0};

/* ==================================================================
 *  内部辅助
 * ================================================================== */

static efw_debug_task_info_t *find_task(const char *name) {
    for (uint16_t i = 0; i < g_runtime.task_count; i++) {
        if (g_runtime.tasks[i].name && strcmp(g_runtime.tasks[i].name, name) == 0) {
            return &g_runtime.tasks[i];
        }
    }
    return NULL;
}

static efw_debug_module_info_t *find_module(const char *name) {
    for (uint16_t i = 0; i < g_runtime.module_count; i++) {
        if (g_runtime.modules[i].name && strcmp(g_runtime.modules[i].name, name) == 0) {
            return &g_runtime.modules[i];
        }
    }
    return NULL;
}

static efw_debug_topic_info_t *find_topic(const char *name) {
    for (uint16_t i = 0; i < g_runtime.topic_count; i++) {
        if (g_runtime.topics[i].name && strcmp(g_runtime.topics[i].name, name) == 0) {
            return &g_runtime.topics[i];
        }
    }
    return NULL;
}

static efw_debug_dataflow_t *find_dataflow(const char *source, const char *sink) {
    for (uint16_t i = 0; i < g_runtime.dataflow_count; i++) {
        if (g_runtime.dataflows[i].source_name && g_runtime.dataflows[i].sink_name &&
            strcmp(g_runtime.dataflows[i].source_name, source) == 0 &&
            strcmp(g_runtime.dataflows[i].sink_name, sink) == 0) {
            return &g_runtime.dataflows[i];
        }
    }
    return NULL;
}

/* ==================================================================
 *  公共 API 实现
 * ================================================================== */

efw_status_t efw_debug_runtime_init(void) {
    memset(&g_runtime, 0, sizeof(g_runtime));
    memset(g_task_timers, 0, sizeof(g_task_timers));
    g_start_time = efw_debug_get_us();
    return EFW_OK;
}

efw_status_t efw_debug_register_task(const char *name, efw_task_type_t type,
                                      uint32_t expected_period_us) {
    if (!name || g_runtime.task_count >= EFW_DEBUG_MAX_TASKS) {
        return EFW_ERR_FULL;
    }
    
    efw_debug_task_info_t *task = &g_runtime.tasks[g_runtime.task_count++];
    memset(task, 0, sizeof(*task));
    
    task->name = name;
    task->type = type;
    task->state = EFW_TASK_IDLE;
    task->expected_period_us = expected_period_us;
    task->min_execution_time_us = UINT32_MAX;
    
    return EFW_OK;
}

efw_status_t efw_debug_task_begin(const char *name) {
    if (!name) return EFW_ERR_INVALID;
    
    efw_debug_task_info_t *task = find_task(name);
    if (!task) return EFW_ERR_NOT_FOUND;
    
    uint64_t now = efw_debug_get_us();
    
    /* 计算实际周期 */
    if (g_task_timers[task - g_runtime.tasks].begin_time > 0) {
        uint32_t period = (uint32_t)(now - g_task_timers[task - g_runtime.tasks].begin_time);
        task->actual_period_us = period;
        g_task_timers[task - g_runtime.tasks].last_period = period;
    }
    
    /* 记录开始时间 */
    g_task_timers[task - g_runtime.tasks].begin_time = now;
    task->state = EFW_TASK_RUNNING;
    task->last_run_time = now;
    
    return EFW_OK;
}

efw_status_t efw_debug_task_end(const char *name) {
    if (!name) return EFW_ERR_INVALID;
    
    efw_debug_task_info_t *task = find_task(name);
    if (!task) return EFW_ERR_NOT_FOUND;
    
    uint64_t now = efw_debug_get_us();
    uint64_t begin = g_task_timers[task - g_runtime.tasks].begin_time;
    
    if (begin > 0) {
        uint32_t duration = (uint32_t)(now - begin);
        task->execution_time_us = duration;
        task->total_execution_time += duration;
        task->run_count++;
        
        /* 更新最大/最小执行时间 */
        if (duration > task->max_execution_time_us) {
            task->max_execution_time_us = duration;
        }
        if (duration < task->min_execution_time_us) {
            task->min_execution_time_us = duration;
        }
        
        /* 检查超时 */
        if (task->expected_period_us > 0 && duration > task->expected_period_us) {
            task->overrun_count++;
        }
    }
    
    task->state = EFW_TASK_IDLE;
    return EFW_OK;
}

efw_status_t efw_debug_register_module(const char *name) {
    if (!name || g_runtime.module_count >= EFW_DEBUG_MAX_MODULES) {
        return EFW_ERR_FULL;
    }
    
    efw_debug_module_info_t *mod = &g_runtime.modules[g_runtime.module_count++];
    memset(mod, 0, sizeof(*mod));
    
    mod->name = name;
    mod->state = EFW_MODULE_UNINIT;
    mod->last_activity_time = efw_debug_get_us();
    
    return EFW_OK;
}

efw_status_t efw_debug_update_module_state(const char *name, efw_module_state_t state) {
    if (!name) return EFW_ERR_INVALID;
    
    efw_debug_module_info_t *mod = find_module(name);
    if (!mod) return EFW_ERR_NOT_FOUND;
    
    mod->state = state;
    mod->last_activity_time = efw_debug_get_us();
    
    return EFW_OK;
}

efw_status_t efw_debug_module_poll(const char *name, uint32_t duration_us) {
    if (!name) return EFW_ERR_INVALID;
    
    efw_debug_module_info_t *mod = find_module(name);
    if (!mod) return EFW_ERR_NOT_FOUND;
    
    mod->poll_count++;
    mod->last_activity_time = efw_debug_get_us();
    
    /* 更新平均轮询时间（滑动平均） */
    if (mod->poll_count == 1) {
        mod->avg_poll_time_us = duration_us;
    } else {
        mod->avg_poll_time_us = (mod->avg_poll_time_us * 7 + duration_us) / 8;
    }
    
    /* 更新最大轮询时间 */
    if (duration_us > mod->max_poll_time_us) {
        mod->max_poll_time_us = duration_us;
    }
    
    return EFW_OK;
}

efw_status_t efw_debug_register_topic(const char *name, uint16_t topic_id) {
    if (!name || g_runtime.topic_count >= EFW_DEBUG_MAX_TOPICS) {
        return EFW_ERR_FULL;
    }
    
    efw_debug_topic_info_t *topic = &g_runtime.topics[g_runtime.topic_count++];
    memset(topic, 0, sizeof(*topic));
    
    topic->name = name;
    topic->topic_id = topic_id;
    
    return EFW_OK;
}

efw_status_t efw_debug_event_publish(const char *topic_name, uint16_t data_size) {
    (void)data_size;
    if (!topic_name) return EFW_ERR_INVALID;
    
    efw_debug_topic_info_t *topic = find_topic(topic_name);
    if (!topic) return EFW_ERR_NOT_FOUND;
    
    topic->publish_count++;
    topic->last_publish_time = efw_debug_get_us();
    
    return EFW_OK;
}

efw_status_t efw_debug_event_receive(const char *topic_name, uint16_t data_size) {
    (void)data_size;
    if (!topic_name) return EFW_ERR_INVALID;
    
    efw_debug_topic_info_t *topic = find_topic(topic_name);
    if (!topic) return EFW_ERR_NOT_FOUND;
    
    topic->receive_count++;
    topic->last_receive_time = efw_debug_get_us();
    
    return EFW_OK;
}

efw_status_t efw_debug_record_dataflow(const char *source, const char *sink,
                                        const void *data, uint16_t size) {
    if (!source || !sink) return EFW_ERR_INVALID;
    
    /* 查找或创建数据流记录 */
    efw_debug_dataflow_t *flow = find_dataflow(source, sink);
    if (!flow) {
        if (g_runtime.dataflow_count >= EFW_DEBUG_MAX_DATAFLOW) {
            return EFW_ERR_FULL;
        }
        flow = &g_runtime.dataflows[g_runtime.dataflow_count++];
        memset(flow, 0, sizeof(*flow));
        flow->source_name = source;
        flow->sink_name = sink;
    }
    
    flow->transfer_count++;
    flow->last_transfer_time = efw_debug_get_us();
    
    /* 保存最后传输的值 */
    if (data && size > 0) {
        uint16_t copy_size = (size > 32) ? 32 : size;
        memcpy(flow->last_value, data, copy_size);
        flow->last_value_size = size;
    }
    
    return EFW_OK;
}

efw_status_t efw_debug_get_runtime_snapshot(efw_debug_runtime_snapshot_t *snapshot) {
    if (!snapshot) return EFW_ERR_INVALID;
    
    memcpy(snapshot, &g_runtime, sizeof(g_runtime));
    snapshot->timestamp = efw_debug_get_us();
    snapshot->uptime_ms = (uint32_t)((snapshot->timestamp - g_start_time) / 1000);
    
    return EFW_OK;
}

efw_status_t efw_debug_export_runtime(uint8_t *buffer, uint16_t buffer_size,
                                       uint16_t *out_size) {
    if (!buffer || !out_size) return EFW_ERR_INVALID;
    
    /* 简化的二进制格式导出 */
    uint16_t offset = 0;
    
    /* 头部 */
    if (buffer_size < 32) return EFW_ERR_RANGE;
    
    /* 时间戳 (8B) */
    uint64_t timestamp = efw_debug_get_us();
    memcpy(&buffer[offset], &timestamp, 8);
    offset += 8;
    
    /* 运行时间 (4B) */
    uint32_t uptime = (uint32_t)((timestamp - g_start_time) / 1000);
    memcpy(&buffer[offset], &uptime, 4);
    offset += 4;
    
    /* 任务数量 (2B) */
    memcpy(&buffer[offset], &g_runtime.task_count, 2);
    offset += 2;
    
    /* 模块数量 (2B) */
    memcpy(&buffer[offset], &g_runtime.module_count, 2);
    offset += 2;
    
    /* 话题数量 (2B) */
    memcpy(&buffer[offset], &g_runtime.topic_count, 2);
    offset += 2;
    
    /* 数据流数量 (2B) */
    memcpy(&buffer[offset], &g_runtime.dataflow_count, 2);
    offset += 2;
    
    /* 任务详情 */
    for (uint16_t i = 0; i < g_runtime.task_count && offset + 32 <= buffer_size; i++) {
        efw_debug_task_info_t *task = &g_runtime.tasks[i];
        
        /* 任务 ID (2B) */
        uint16_t task_id = i;
        memcpy(&buffer[offset], &task_id, 2);
        offset += 2;
        
        /* 状态 (1B) */
        buffer[offset++] = (uint8_t)task->state;
        
        /* 实际周期 (4B) */
        memcpy(&buffer[offset], &task->actual_period_us, 4);
        offset += 4;
        
        /* 执行时间 (4B) */
        memcpy(&buffer[offset], &task->execution_time_us, 4);
        offset += 4;
        
        /* 运行次数 (4B) */
        memcpy(&buffer[offset], &task->run_count, 4);
        offset += 4;
        
        /* 超时次数 (4B) */
        memcpy(&buffer[offset], &task->overrun_count, 4);
        offset += 4;
    }
    
    /* 模块详情 */
    for (uint16_t i = 0; i < g_runtime.module_count && offset + 16 <= buffer_size; i++) {
        efw_debug_module_info_t *mod = &g_runtime.modules[i];
        
        /* 模块 ID (2B) */
        uint16_t mod_id = i;
        memcpy(&buffer[offset], &mod_id, 2);
        offset += 2;
        
        /* 状态 (1B) */
        buffer[offset++] = (uint8_t)mod->state;
        
        /* 轮询次数 (4B) */
        memcpy(&buffer[offset], &mod->poll_count, 4);
        offset += 4;
        
        /* 平均轮询时间 (4B) */
        memcpy(&buffer[offset], &mod->avg_poll_time_us, 4);
        offset += 4;
    }
    
    *out_size = offset;
    return EFW_OK;
}

#else /* EFW_DEBUG_ENABLE == 0 */

/* Release 版本：所有函数编译为空 */
efw_status_t efw_debug_runtime_init(void) { return EFW_OK; }
efw_status_t efw_debug_register_task(const char *n, efw_task_type_t t, uint32_t p) { 
    (void)n; (void)t; (void)p; return EFW_OK; 
}
efw_status_t efw_debug_task_begin(const char *n) { (void)n; return EFW_OK; }
efw_status_t efw_debug_task_end(const char *n) { (void)n; return EFW_OK; }
efw_status_t efw_debug_register_module(const char *n) { (void)n; return EFW_OK; }
efw_status_t efw_debug_update_module_state(const char *n, efw_module_state_t s) { 
    (void)n; (void)s; return EFW_OK; 
}
efw_status_t efw_debug_module_poll(const char *n, uint32_t d) { (void)n; (void)d; return EFW_OK; }
efw_status_t efw_debug_register_topic(const char *n, uint16_t id) { (void)n; (void)id; return EFW_OK; }
efw_status_t efw_debug_event_publish(const char *n, uint16_t s) { (void)n; (void)s; return EFW_OK; }
efw_status_t efw_debug_event_receive(const char *n, uint16_t s) { (void)n; (void)s; return EFW_OK; }
efw_status_t efw_debug_record_dataflow(const char *s, const char *d, const void *v, uint16_t sz) {
    (void)s; (void)d; (void)v; (void)sz; return EFW_OK;
}
efw_status_t efw_debug_get_runtime_snapshot(efw_debug_runtime_snapshot_t *s) {
    if (s) memset(s, 0, sizeof(*s));
    return EFW_OK;
}
efw_status_t efw_debug_export_runtime(uint8_t *b, uint16_t bs, uint16_t *os) {
    (void)b; (void)bs; if (os) *os = 0; return EFW_OK;
}

#endif /* EFW_DEBUG_ENABLE */
