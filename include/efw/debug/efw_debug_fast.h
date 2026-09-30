/**
 * @file    efw_debug_fast.h
 * @brief   EFW 调试模块高性能版本
 *
 * 针对实时性要求高的场景优化：
 *   - 增量更新：只传输变化的数据
 *   - 双缓冲：读写分离，零等待
 *   - DMA/中断驱动：后台传输
 *   - 环形缓冲：批量处理
 *   - 条件编译：Release 版本零开销
 */

#ifndef EFW_DEBUG_FAST_H
#define EFW_DEBUG_FAST_H

#include "efw/core/common.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ==================================================================
 *  编译期开关 - Release 版本完全禁用
 * ================================================================== */

#ifndef EFW_DEBUG_ENABLE
    #ifdef NDEBUG
        #define EFW_DEBUG_ENABLE 0      /* Release 版本禁用 */
    #else
        #define EFW_DEBUG_ENABLE 1      /* Debug 版本启用 */
    #endif
#endif

/* 零开销宏 - Release 版本编译为空 */
#if EFW_DEBUG_ENABLE
    #define EFW_DEBUG_CALL(expr) (expr)
#else
    #define EFW_DEBUG_CALL(expr) ((void)0)
#endif

/* ==================================================================
 *  配置参数
 * ================================================================== */

/** @brief 最大监控点数量 */
#ifndef EFW_DEBUG_MAX_POINTS
#define EFW_DEBUG_MAX_POINTS 64
#endif

/** @brief 双缓冲大小（字节） */
#ifndef EFW_DEBUG_BUFFER_SIZE
#define EFW_DEBUG_BUFFER_SIZE 512
#endif

/** @brief 变化检测位图大小 */
#ifndef EFW_DEBUG_DIRTY_BITMAP_SIZE
#define EFW_DEBUG_DIRTY_BITMAP_SIZE (EFW_DEBUG_MAX_POINTS / 8 + 1)
#endif

/* ==================================================================
 *  高性能数据结构
 * ================================================================== */

/**
 * @brief 值联合体 - 避免类型转换开销
 */
typedef union {
    uint8_t  u8;
    int8_t   i8;
    uint16_t u16;
    int16_t  i16;
    uint32_t u32;
    int32_t  i32;
    float    f32;
    uint64_t u64;
    double   f64;
    void    *ptr;
} efw_debug_value_t;

/**
 * @brief 监控点描述（只读，初始化后不变）
 */
typedef struct {
    const char *name;           /* 名称 */
    const void *source_ptr;     /* 源数据指针 */
    uint8_t type;               /* 数据类型 */
    uint8_t size;               /* 数据大小 */
    uint16_t param_id;          /* LiteTune 参数 ID */
} efw_debug_point_desc_t;

/**
 * @brief 双缓冲状态
 */
typedef struct {
    uint8_t buffer_a[EFW_DEBUG_BUFFER_SIZE];
    uint8_t buffer_b[EFW_DEBUG_BUFFER_SIZE];
    uint8_t *write_buffer;      /* 当前写入缓冲 */
    uint8_t *read_buffer;       /* 当前读取缓冲 */
    uint16_t write_offset;      /* 写入偏移 */
    uint16_t read_offset;       /* 读取偏移 */
    volatile uint8_t swap_flag; /* 交换标志 */
} efw_debug_double_buffer_t;

/**
 * @brief 增量更新状态
 */
typedef struct {
    uint8_t dirty_bitmap[EFW_DEBUG_DIRTY_BITMAP_SIZE];  /* 变化位图 */
    efw_debug_value_t prev_values[EFW_DEBUG_MAX_POINTS]; /* 上次值缓存 */
    uint32_t update_seq;        /* 更新序列号 */
    uint32_t last_sync_seq;     /* 上次同步序列号 */
} efw_debug_incremental_t;

/**
 * @brief 高性能调试模块状态
 */
typedef struct {
    efw_debug_point_desc_t points[EFW_DEBUG_MAX_POINTS];
    uint16_t point_count;
    
    efw_debug_double_buffer_t dbuf;
    efw_debug_incremental_t incr;
    
    /* 性能统计 */
    struct {
        uint32_t update_us;         /* 更新耗时（微秒） */
        uint32_t sync_us;           /* 同步耗时（微秒） */
        uint32_t dirty_count;       /* 变化点数量 */
        uint32_t skip_count;        /* 跳过的更新次数 */
    } stats;
    
    volatile uint8_t initialized;
} efw_debug_fast_t;

/* ==================================================================
 *  核心 API
 * ================================================================== */

/**
 * @brief 初始化高性能调试模块
 * @return EFW_OK 成功
 */
efw_status_t efw_debug_fast_init(void);

/**
 * @brief 快速更新 - 只检测变化的监控点
 *
 * 此函数设计为在主循环中频繁调用，执行时间 < 10us（典型情况）
 *
 * @return EFW_OK 成功
 */
efw_status_t efw_debug_fast_update(void);

/**
 * @brief 后台同步 - 将变化的数据发送到 LiteTune
 *
 * 此函数应在低优先级任务中调用，或在主循环空闲时调用
 *
 * @return EFW_OK 成功
 */
efw_status_t efw_debug_fast_sync(void);

/**
 * @brief 注册监控点（高性能版本）
 */
efw_status_t efw_debug_fast_register(const char *name, uint8_t type,
                                      const void *value_ptr, uint16_t param_id);

/**
 * @brief 获取性能统计
 */
void efw_debug_fast_get_stats(uint32_t *update_us, uint32_t *sync_us,
                               uint32_t *dirty_count);

/* ==================================================================
 *  便捷宏
 * ================================================================== */

/**
 * @brief 注册变量的便捷宏
 */
#define EFW_DEBUG_FAST_REGISTER(name, var, param_id) \
    efw_debug_fast_register(name, _Generic((var), \
        _Bool: 0x01, uint8_t: 0x02, int8_t: 0x03, \
        uint16_t: 0x04, int16_t: 0x05, \
        uint32_t: 0x06, int32_t: 0x07, \
        float: 0x0A, double: 0x0B, \
        default: 0x06 \
    ), &(var), param_id)

/**
 * @brief 快速更新宏 - 包含时间测量
 */
#define EFW_DEBUG_FAST_UPDATE_TIMED() do { \
    uint32_t _start = efw_debug_get_us(); \
    efw_debug_fast_update(); \
    g_debug_fast.stats.update_us = efw_debug_get_us() - _start; \
} while(0)

/* ==================================================================
 *  平台相关函数（需要用户实现）
 * ================================================================== */

/**
 * @brief 获取当前时间（微秒）
 *
 * 用户需要根据具体平台实现此函数
 * 示例（STM32 + DWT）：
 *   uint32_t efw_debug_get_us(void) {
 *       return DWT->CYCCNT / (SystemCoreClock / 1000000);
 *   }
 */
uint32_t efw_debug_get_us(void);

#ifdef __cplusplus
}
#endif

#endif /* EFW_DEBUG_FAST_H */
