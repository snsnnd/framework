/**
 * @file    efw_debug_fast.c
 * @brief   EFW 调试模块高性能实现
 *
 * 优化策略：
 *   1. 增量更新 - 只检测和传输变化的数据
 *   2. 双缓冲 - 读写分离，零等待
 *   3. 位图标记 - 快速定位变化点
 *   4. 批量处理 - 减少函数调用次数
 *   5. 条件编译 - Release 版本零开销
 */

#include "efw/debug/efw_debug_fast.h"
#include <string.h>

#if EFW_DEBUG_ENABLE

/* ==================================================================
 *  全局状态
 * ================================================================== */

efw_debug_fast_t g_debug_fast = {0};

/* ==================================================================
 *  内部辅助函数
 * ================================================================== */

/**
 * @brief 获取数据类型的大小
 */
static uint8_t get_type_size(uint8_t type)
{
    switch (type) {
        case 0x01: return 1;  /* bool */
        case 0x02: return 1;  /* u8 */
        case 0x03: return 1;  /* i8 */
        case 0x04: return 2;  /* u16 */
        case 0x05: return 2;  /* i16 */
        case 0x06: return 4;  /* u32 */
        case 0x07: return 4;  /* i32 */
        case 0x08: return 8;  /* u64 */
        case 0x09: return 8;  /* i64 */
        case 0x0A: return 4;  /* f32 */
        case 0x0B: return 8;  /* f64 */
        default:   return 4;
    }
}

/**
 * @brief 比较两个值是否相等
 */
static inline int value_equals(uint8_t type, const void *a, const void *b)
{
    uint8_t size = get_type_size(type);
    return memcmp(a, b, size) == 0;
}

/**
 * @brief 标记监控点为脏（已变化）
 */
static inline void mark_dirty(uint16_t index)
{
    g_debug_fast.incr.dirty_bitmap[index / 8] |= (1 << (index % 8));
}

/**
 * @brief 清除脏标记
 */
static inline void clear_dirty(uint16_t index)
{
    g_debug_fast.incr.dirty_bitmap[index / 8] &= ~(1 << (index % 8));
}

/**
 * @brief 检查监控点是否脏
 */
static inline int is_dirty(uint16_t index)
{
    return (g_debug_fast.incr.dirty_bitmap[index / 8] >> (index % 8)) & 1;
}

/**
 * @brief 读取监控点当前值
 */
static void read_point_value(uint16_t index, efw_debug_value_t *out)
{
    const efw_debug_point_desc_t *desc = &g_debug_fast.points[index];
    
    if (!desc->source_ptr || !out) {
        return;
    }
    
    /* 根据类型读取 */
    switch (desc->type) {
        case 0x01: /* bool */
        case 0x02: /* u8 */
            out->u8 = *(const uint8_t *)desc->source_ptr;
            break;
        case 0x03: /* i8 */
            out->i8 = *(const int8_t *)desc->source_ptr;
            break;
        case 0x04: /* u16 */
            out->u16 = *(const uint16_t *)desc->source_ptr;
            break;
        case 0x05: /* i16 */
            out->i16 = *(const int16_t *)desc->source_ptr;
            break;
        case 0x06: /* u32 */
            out->u32 = *(const uint32_t *)desc->source_ptr;
            break;
        case 0x07: /* i32 */
            out->i32 = *(const int32_t *)desc->source_ptr;
            break;
        case 0x0A: /* f32 */
            out->f32 = *(const float *)desc->source_ptr;
            break;
        case 0x0B: /* f64 */
            out->f64 = *(const double *)desc->source_ptr;
            break;
        default:
            out->u32 = *(const uint32_t *)desc->source_ptr;
            break;
    }
}

/**
 * @brief 将监控点数据写入缓冲区
 */
static uint16_t write_point_to_buffer(uint16_t index, uint8_t *buffer, uint16_t offset)
{
    const efw_debug_point_desc_t *desc = &g_debug_fast.points[index];
    uint8_t size = desc->size;
    
    /* 写入格式: [param_id(2B)] [size(1B)] [value(NB)] */
    if (offset + 3 + size > EFW_DEBUG_BUFFER_SIZE) {
        return offset;  /* 缓冲区满 */
    }
    
    /* 参数 ID */
    buffer[offset++] = (uint8_t)(desc->param_id & 0xFF);
    buffer[offset++] = (uint8_t)((desc->param_id >> 8) & 0xFF);
    
    /* 大小 */
    buffer[offset++] = size;
    
    /* 值 */
    memcpy(&buffer[offset], desc->source_ptr, size);
    offset += size;
    
    return offset;
}

/* ==================================================================
 *  双缓冲操作
 * ================================================================== */

/**
 * @brief 初始化双缓冲
 */
static void dbuf_init(void)
{
    g_debug_fast.dbuf.write_buffer = g_debug_fast.dbuf.buffer_a;
    g_debug_fast.dbuf.read_buffer = g_debug_fast.dbuf.buffer_b;
    g_debug_fast.dbuf.write_offset = 0;
    g_debug_fast.dbuf.read_offset = 0;
    g_debug_fast.dbuf.swap_flag = 0;
}

/**
 * @brief 交换双缓冲
 */
static void dbuf_swap(void)
{
    uint8_t *temp = g_debug_fast.dbuf.write_buffer;
    g_debug_fast.dbuf.write_buffer = g_debug_fast.dbuf.read_buffer;
    g_debug_fast.dbuf.read_buffer = temp;
    g_debug_fast.dbuf.write_offset = 0;
    g_debug_fast.dbuf.swap_flag = 0;
}

/**
 * @brief 写入数据到写缓冲
 */
static void dbuf_write(const uint8_t *data, uint16_t size)
{
    if (g_debug_fast.dbuf.write_offset + size <= EFW_DEBUG_BUFFER_SIZE) {
        memcpy(&g_debug_fast.dbuf.write_buffer[g_debug_fast.dbuf.write_offset], data, size);
        g_debug_fast.dbuf.write_offset += size;
    }
}

/* ==================================================================
 *  公共 API 实现
 * ================================================================== */

efw_status_t efw_debug_fast_init(void)
{
    if (g_debug_fast.initialized) {
        return EFW_OK;
    }
    
    /* 清零所有状态 */
    memset(&g_debug_fast, 0, sizeof(g_debug_fast));
    
    /* 初始化双缓冲 */
    dbuf_init();
    
    g_debug_fast.initialized = 1;
    
    return EFW_OK;
}

efw_status_t efw_debug_fast_register(const char *name, uint8_t type,
                                      const void *value_ptr, uint16_t param_id)
{
    if (!name || !value_ptr) {
        return EFW_ERR_INVALID;
    }
    
    if (g_debug_fast.point_count >= EFW_DEBUG_MAX_POINTS) {
        return EFW_ERR_FULL;
    }
    
    uint16_t index = g_debug_fast.point_count++;
    efw_debug_point_desc_t *desc = &g_debug_fast.points[index];
    
    desc->name = name;
    desc->source_ptr = value_ptr;
    desc->type = type;
    desc->size = get_type_size(type);
    desc->param_id = param_id;
    
    /* 初始化上次值 */
    read_point_value(index, &g_debug_fast.incr.prev_values[index]);
    
    return EFW_OK;
}

efw_status_t efw_debug_fast_update(void)
{
    if (!g_debug_fast.initialized) {
        return EFW_ERR_NOT_READY;
    }
    
    uint32_t start_us = efw_debug_get_us();
    
    /* 增量检测：只标记变化的监控点 */
    uint16_t dirty_count = 0;
    
    for (uint16_t i = 0; i < g_debug_fast.point_count; i++) {
        efw_debug_value_t current;
        read_point_value(i, &current);
        
        /* 与上次值比较 */
        if (!value_equals(g_debug_fast.points[i].type,
                          &current,
                          &g_debug_fast.incr.prev_values[i])) {
            /* 值已变化 */
            mark_dirty(i);
            g_debug_fast.incr.prev_values[i] = current;
            dirty_count++;
        }
    }
    
    g_debug_fast.incr.update_seq++;
    g_debug_fast.stats.dirty_count = dirty_count;
    g_debug_fast.stats.update_us = efw_debug_get_us() - start_us;
    
    return EFW_OK;
}

efw_status_t efw_debug_fast_sync(void)
{
    if (!g_debug_fast.initialized) {
        return EFW_ERR_NOT_READY;
    }
    
    /* 检查是否有变化需要同步 */
    if (g_debug_fast.incr.update_seq == g_debug_fast.incr.last_sync_seq) {
        g_debug_fast.stats.skip_count++;
        return EFW_OK;  /* 无变化，跳过 */
    }
    
    uint32_t start_us = efw_debug_get_us();
    
    /* 写入变化的数据到缓冲区 */
    for (uint16_t i = 0; i < g_debug_fast.point_count; i++) {
        if (is_dirty(i)) {
            /* 写入到当前写缓冲 */
            uint16_t new_offset = write_point_to_buffer(
                i,
                g_debug_fast.dbuf.write_buffer,
                g_debug_fast.dbuf.write_offset
            );
            
            if (new_offset > g_debug_fast.dbuf.write_offset) {
                g_debug_fast.dbuf.write_offset = new_offset;
            }
            
            /* 清除脏标记 */
            clear_dirty(i);
        }
    }
    
    /* 交换缓冲（如果有数据） */
    if (g_debug_fast.dbuf.write_offset > 0) {
        dbuf_swap();
    }
    
    g_debug_fast.incr.last_sync_seq = g_debug_fast.incr.update_seq;
    g_debug_fast.stats.sync_us = efw_debug_get_us() - start_us;
    
    return EFW_OK;
}

void efw_debug_fast_get_stats(uint32_t *update_us, uint32_t *sync_us,
                               uint32_t *dirty_count)
{
    if (update_us) *update_us = g_debug_fast.stats.update_us;
    if (sync_us) *sync_us = g_debug_fast.stats.sync_us;
    if (dirty_count) *dirty_count = g_debug_fast.stats.dirty_count;
}

#else /* EFW_DEBUG_ENABLE == 0 */

/* Release 版本：所有函数编译为空 */

efw_status_t efw_debug_fast_init(void) { return EFW_OK; }
efw_status_t efw_debug_fast_update(void) { return EFW_OK; }
efw_status_t efw_debug_fast_sync(void) { return EFW_OK; }
efw_status_t efw_debug_fast_register(const char *n, uint8_t t, const void *p, uint16_t id) {
    (void)n; (void)t; (void)p; (void)id; return EFW_OK;
}
void efw_debug_fast_get_stats(uint32_t *u, uint32_t *s, uint32_t *d) {
    if (u) *u = 0; if (s) *s = 0; if (d) *d = 0;
}

#endif /* EFW_DEBUG_ENABLE */
