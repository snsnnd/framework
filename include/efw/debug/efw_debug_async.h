/**
 * @file    efw_debug_async.h
 * @brief   EFW 调试模块异步传输版本
 *
 * 使用 DMA 或中断驱动实现后台数据传输，
 * 完全不阻塞主循环。
 *
 * 适用场景：
 *   - 高频率控制循环（1kHz+）
 *   - 对时序要求极严格的应用
 *   - 有空闲 DMA 通道的 MCU
 */

#ifndef EFW_DEBUG_ASYNC_H
#define EFW_DEBUG_ASYNC_H

#include "efw/core/common.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ==================================================================
 *  配置
 * ================================================================== */

/** @brief 环形缓冲区大小（必须是 2 的幂） */
#ifndef EFW_DEBUG_RING_SIZE
#define EFW_DEBUG_RING_SIZE 1024
#endif

/** @brief 单次传输最大字节数 */
#ifndef EFW_DEBUG_BATCH_SIZE
#define EFW_DEBUG_BATCH_SIZE 64
#endif

/* ==================================================================
 *  数据结构
 * ================================================================== */

/**
 * @brief 环形缓冲区
 */
typedef struct {
    uint8_t buffer[EFW_DEBUG_RING_SIZE];
    volatile uint32_t write_pos;    /* 写入位置（主循环更新） */
    volatile uint32_t read_pos;     /* 读取位置（ISR/DMA 更新） */
    uint32_t mask;                  /* 掩码，用于快速取模 */
} efw_debug_ring_t;

/**
 * @brief 传输描述符
 */
typedef struct {
    const uint8_t *data;        /* 数据指针 */
    uint16_t length;            /* 数据长度 */
    volatile uint8_t complete;  /* 传输完成标志 */
} efw_debug_transfer_t;

/**
 * @brief 异步调试模块状态
 */
typedef struct {
    efw_debug_ring_t ring;          /* 环形缓冲区 */
    efw_debug_transfer_t transfer;  /* 当前传输 */
    
    volatile uint8_t tx_busy;       /* 传输忙标志 */
    uint8_t *tx_buffer;             /* 传输缓冲区（DMA 使用） */
    
    /* 回调函数 */
    void (*tx_complete_callback)(void);
    void (*error_callback)(int error_code);
    
    /* 统计 */
    struct {
        uint32_t bytes_written;
        uint32_t bytes_sent;
        uint32_t overflow_count;
        uint32_t tx_count;
    } stats;
    
    volatile uint8_t initialized;
} efw_debug_async_t;

/* ==================================================================
 *  API
 * ================================================================== */

/**
 * @brief 初始化异步调试模块
 * @return EFW_OK 成功
 */
efw_status_t efw_debug_async_init(void);

/**
 * @brief 写入数据到环形缓冲区（非阻塞）
 *
 * 此函数在主循环中调用，执行时间 < 1us
 *
 * @param data 数据指针
 * @param length 数据长度
 * @return EFW_OK 成功，EFW_ERR_FULL 缓冲区满
 */
efw_status_t efw_debug_async_write(const void *data, uint16_t length);

/**
 * @brief 触发后台传输
 *
 * 此函数应在定时器中断或 DMA 完成中断中调用
 * 如果当前有传输在进行，会跳过本次
 *
 * @return EFW_OK 成功，EFW_ERR_BUSY 传输忙
 */
efw_status_t efw_debug_async_flush(void);

/**
 * @brief DMA 传输完成回调
 *
 * 用户需要在 DMA 完成中断中调用此函数
 */
void efw_debug_async_tx_complete(void);

/**
 * @��检查是否有待传输数据
 * @return 1 有数据，0 无数据
 */
int efw_debug_async_has_data(void);

/**
 * @brief 获取缓冲区使用率
 * @return 使用百分比 (0-100)
 */
uint8_t efw_debug_async_usage(void);

/* ==================================================================
 *  平台相关接口（需要用户实现）
 * ================================================================== */

/**
 * @brief 启动 DMA 传输
 *
 * 用户需要实现此函数，启动 DMA 将数据发送到 UART
 *
 * @param data 数据指针
 * @param length 数据长度
 * @return EFW_OK 成功
 */
efw_status_t efw_debug_start_dma(const uint8_t *data, uint16_t length);

/**
 * @brief 注册 DMA 完成回调
 *
 * 用户需要实现此函数，注册 DMA 传输完成的回调
 *
 * @param callback 回调函数
 */
void efw_debug_register_tx_callback(void (*callback)(void));

#ifdef __cplusplus
}
#endif

#endif /* EFW_DEBUG_ASYNC_H */
