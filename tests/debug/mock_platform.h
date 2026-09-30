/**
 * @file    mock_platform.h
 * @brief   MCU 平台模拟层 - 用于主机端测试
 *
 * 模拟 STM32/ESP32 等 MCU 的关键功能：
 *   - 高精度定时器（微秒级）
 *   - DMA 传输
 *   - 中断控制器
 *   - UART 串口
 */

#ifndef MOCK_PLATFORM_H
#define MOCK_PLATFORM_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ==================================================================
 *  定时器模拟
 * ================================================================== */

/**
 * @brief 获取当前时间（微秒）- 模拟 DWT/SysTick
 */
uint32_t mock_get_time_us(void);

/**
 * @brief 获取当前时间（纳秒）- 用于高精度测量
 */
uint64_t mock_get_time_ns(void);

/**
 * @brief 重置定时器
 */
void mock_timer_reset(void);

/**
 * @brief 设置模拟时钟频率（MHz）
 */
void mock_set_clock_mhz(uint32_t mhz);

/* ==================================================================
 *  DMA 模拟
 * ================================================================== */

/** @brief DMA 传输完成回调类型 */
typedef void (*mock_dma_callback_t)(void);

/**
 * @brief 初始化 DMA 模拟
 */
void mock_dma_init(void);

/**
 * @brief 启动 DMA 传输（模拟）
 *
 * 模拟 DMA 传输延迟，完成后自动调用回调
 *
 * @param data 数据指针
 * @param length 数据长度
 * @param callback 完成回调
 * @return 0 成功，-1 失败
 */
int mock_dma_start(const uint8_t *data, uint16_t length, mock_dma_callback_t callback);

/**
 * @brief 模拟 DMA 传输完成（手动触发）
 */
void mock_dma_complete(void);

/**
 * @brief 检查 DMA 是否忙
 */
bool mock_dma_is_busy(void);

/**
 * @brief 设置模拟 DMA 延迟（微秒）
 */
void mock_dma_set_delay_us(uint32_t delay);

/* ==================================================================
 *  UART 模拟
 * ================================================================== */

/**
 * @brief 初始化 UART 模拟
 */
void mock_uart_init(void);

/**
 * @brief 发送数据（模拟）
 *
 * 模拟 UART 发送延迟：115200 波特率 ≈ 87us/字节
 *
 * @param data 数据指针
 * @param length 数据长度
 * @return 实际发送字节数
 */
int mock_uart_send(const uint8_t *data, uint16_t length);

/**
 * @brief 获取已发送数据
 *
 * 用于验证发送的数据内容
 *
 * @param buffer 输出缓冲区
 * @param max_length 缓冲区大小
 * @return 实际数据长度
 */
int mock_uart_get_sent(uint8_t *buffer, uint16_t max_length);

/**
 * @brief 清空发送缓冲区
 */
void mock_uart_flush(void);

/**
 * @brief 设置 UART 波特率（用于计算延迟）
 */
void mock_uart_set_baud(uint32_t baud);

/* ==================================================================
 *  性能测量工具
 * ================================================================== */

/** @brief 性能测量结果 */
typedef struct {
    uint64_t total_ns;          /* 总耗时（纳秒） */
    uint32_t min_ns;            /* 最小耗时 */
    uint32_t max_ns;            /* 最大耗时 */
    uint32_t avg_ns;            /* 平均耗时 */
    uint32_t count;             /* 测量次数 */
    uint32_t over_limit_count;  /* 超过阈值的次数 */
} mock_perf_result_t;

/**
 * @brief 开始性能测量
 */
void mock_perf_begin(void);

/**
 * @brief 结束性能测量并记录
 */
void mock_perf_end(void);

/**
 * @brief 获取性能测量结果
 */
void mock_perf_get_result(mock_perf_result_t *result);

/**
 * @brief 重置性能测量
 */
void mock_perf_reset(void);

/**
 * @brief 设置性能阈值（超过此值会记录）
 */
void mock_perf_set_threshold_us(uint32_t threshold_us);

/* ==================================================================
 *  模拟场景配置
 * ================================================================== */

/** @brief 模拟场景配置 */
typedef struct {
    uint32_t clock_mhz;            /* CPU 时钟频率 */
    uint32_t uart_baud;            /* UART 波特率 */
    uint32_t dma_delay_us;         /* DMA 传输延迟 */
    uint32_t perf_threshold_us;    /* 性能告警阈值 */
    bool enable_dma;               /* 是否启用 DMA */
    bool enable_interrupt;         /* 是否启用中断模拟 */
} mock_config_t;

/**
 * @brief 使用默认配置初始化
 *
 * 默认配置：
 *   - 时钟：168 MHz（STM32F4 典型）
 *   - UART：115200 波特率
 *   - DMA 延迟：10 us
 *   - 性能阈值：100 us
 */
void mock_init_default(void);

/**
 * @brief 使用自定义配置初始化
 */
void mock_init(const mock_config_t *config);

/**
 * @brief 获取当前配置
 */
void mock_get_config(mock_config_t *config);

#ifdef __cplusplus
}
#endif

#endif /* MOCK_PLATFORM_H */
