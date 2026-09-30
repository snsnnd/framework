/**
 * @file    efw_debug_async.c
 * @brief   EFW 调试模块异步传输实现
 *
 * 使用环形缓冲区实现零阻塞数据传输：
 *   1. 主循环只写入环形缓冲区（< 1us）
 *   2. 后台任务从缓冲区读取并发送
 *   3. DMA 完成中断触发下一次传输
 */

#include "efw/debug/efw_debug_async.h"
#include <string.h>

/* ==================================================================
 *  全局状态
 * ================================================================== */

static efw_debug_async_t g_async = {0};

/* ==================================================================
 *  环形缓冲区操作
 * ================================================================== */

/**
 * @brief 初始化环形缓冲区
 */
static void ring_init(efw_debug_ring_t *ring)
{
    ring->write_pos = 0;
    ring->read_pos = 0;
    ring->mask = EFW_DEBUG_RING_SIZE - 1;
}

/**
 * @brief 获取可读数据长度
 */
static inline uint32_t ring_readable(const efw_debug_ring_t *ring)
{
    return ring->write_pos - ring->read_pos;
}

/**
 * @brief 获取可写空间
 */
static inline uint32_t ring_writable(const efw_debug_ring_t *ring)
{
    return EFW_DEBUG_RING_SIZE - ring_readable(ring);
}

/**
 * @brief 写入环形缓冲区
 */
static int ring_write(efw_debug_ring_t *ring, const uint8_t *data, uint32_t length)
{
    if (ring_writable(ring) < length) {
        return -1;  /* 空间不足 */
    }
    
    uint32_t pos = ring->write_pos & ring->mask;
    uint32_t to_end = EFW_DEBUG_RING_SIZE - pos;
    
    if (length <= to_end) {
        /* 一次性写入 */
        memcpy(&ring->buffer[pos], data, length);
    } else {
        /* 分两段写入 */
        memcpy(&ring->buffer[pos], data, to_end);
        memcpy(&ring->buffer[0], data + to_end, length - to_end);
    }
    
    /* 内存屏障，确保数据写入完成后再更新位置 */
#if defined(__arm__) || defined(__aarch64__)
    __asm volatile("dmb" ::: "memory");
#elif defined(__x86_64__) || defined(__i386__)
    __asm volatile("mfence" ::: "memory");
#else
    /* 通用编译器屏障 */
    __asm volatile("" ::: "memory");
#endif
    
    ring->write_pos += length;
    
    return 0;
}

/**
 * @brief 从环形缓冲区读取
 */
static int ring_read(efw_debug_ring_t *ring, uint8_t *data, uint32_t length)
{
    if (ring_readable(ring) < length) {
        return -1;  /* 数据不足 */
    }
    
    uint32_t pos = ring->read_pos & ring->mask;
    uint32_t to_end = EFW_DEBUG_RING_SIZE - pos;
    
    if (length <= to_end) {
        memcpy(data, &ring->buffer[pos], length);
    } else {
        memcpy(data, &ring->buffer[pos], to_end);
        memcpy(data + to_end, &ring->buffer[0], length - to_end);
    }
    
    ring->read_pos += length;
    
    return 0;
}

/* ==================================================================
 *  公共 API 实现
 * ================================================================== */

efw_status_t efw_debug_async_init(void)
{
    if (g_async.initialized) {
        return EFW_OK;
    }
    
    memset(&g_async, 0, sizeof(g_async));
    ring_init(&g_async.ring);
    
    /* 注册传输完成回调 */
    efw_debug_register_tx_callback(efw_debug_async_tx_complete);
    
    g_async.initialized = 1;
    
    return EFW_OK;
}

efw_status_t efw_debug_async_write(const void *data, uint16_t length)
{
    if (!g_async.initialized || !data || length == 0) {
        return EFW_ERR_INVALID;
    }
    
    /* 尝试写入环形缓冲区 */
    if (ring_write(&g_async.ring, (const uint8_t *)data, length) != 0) {
        g_async.stats.overflow_count++;
        return EFW_ERR_FULL;
    }
    
    g_async.stats.bytes_written += length;
    
    return EFW_OK;
}

efw_status_t efw_debug_async_flush(void)
{
    if (!g_async.initialized) {
        return EFW_ERR_NOT_READY;
    }
    
    /* 检查是否有数据且当前无传输 */
    if (g_async.tx_busy || ring_readable(&g_async.ring) == 0) {
        return EFW_OK;
    }
    
    /* 计算本次传输长度 */
    uint32_t available = ring_readable(&g_async.ring);
    uint16_t tx_length = (available > EFW_DEBUG_BATCH_SIZE) 
                         ? EFW_DEBUG_BATCH_SIZE 
                         : (uint16_t)available;
    
    /* 读取数据到传输缓冲区 */
    /* 注意：这里简化处理，实际可能需要使用静态缓冲区 */
    static uint8_t tx_buffer[EFW_DEBUG_BATCH_SIZE];
    
    if (ring_read(&g_async.ring, tx_buffer, tx_length) != 0) {
        return EFW_ERR_IO;
    }
    
    /* 启动 DMA 传输 */
    g_async.tx_busy = 1;
    g_async.tx_buffer = tx_buffer;
    
    efw_status_t ret = efw_debug_start_dma(tx_buffer, tx_length);
    if (ret != EFW_OK) {
        g_async.tx_busy = 0;
        return ret;
    }
    
    g_async.stats.bytes_sent += tx_length;
    g_async.stats.tx_count++;
    
    return EFW_OK;
}

void efw_debug_async_tx_complete(void)
{
    /* DMA 传输完成，清除忙标志 */
    g_async.tx_busy = 0;
    
    /* 可以立即触发下一次传输 */
    /* efw_debug_async_flush(); */
}

int efw_debug_async_has_data(void)
{
    return ring_readable(&g_async.ring) > 0;
}

uint8_t efw_debug_async_usage(void)
{
    uint32_t used = ring_readable(&g_async.ring);
    return (uint8_t)((used * 100) / EFW_DEBUG_RING_SIZE);
}

/* ==================================================================
 *  示例：STM32 平台实现
 * ================================================================== */

/*
#include "stm32f4xx_hal.h"

// DMA 传输缓冲区
static uint8_t dma_buffer[EFW_DEBUG_BATCH_SIZE];
static DMA_HandleTypeDef hdma_uart_tx;

efw_status_t efw_debug_start_dma(const uint8_t *data, uint16_t length)
{
    if (length > EFW_DEBUG_BATCH_SIZE) {
        return EFW_ERR_RANGE;
    }
    
    // 拷贝到 DMA 缓冲区
    memcpy(dma_buffer, data, length);
    
    // 启动 DMA 传输
    HAL_StatusTypeDef status = HAL_UART_Transmit_DMA(&huart2, dma_buffer, length);
    
    return (status == HAL_OK) ? EFW_OK : EFW_ERR_IO;
}

void efw_debug_register_tx_callback(void (*callback)(void))
{
    // 注册到 UART DMA 传输完成回调
    // 在 HAL_UART_TxCpltCallback 中调用 callback()
}

// UART DMA 传输完成回调
void HAL_UART_TxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart == &huart2) {
        efw_debug_async_tx_complete();
    }
}

// 定时器中断中触发刷新
void TIM2_IRQHandler(void)
{
    if (__HAL_TIM_GET_FLAG(&htim2, TIM_FLAG_UPDATE)) {
        __HAL_TIM_CLEAR_FLAG(&htim2, TIM_FLAG_UPDATE);
        efw_debug_async_flush();
    }
}
*/

/* ==================================================================
 *  示例：ESP32 平台实现
 * ================================================================== */

/*
#include "driver/uart.h"
#include "driver/gptimer.h"

static QueueHandle_t uart_queue;

efw_status_t efw_debug_start_dma(const uint8_t *data, uint16_t length)
{
    // ESP32 UART 异步发送
    int written = uart_write_bytes(UART_NUM_1, data, length);
    return (written >= 0) ? EFW_OK : EFW_ERR_IO;
}

// UART 事件任务
void uart_event_task(void *pvParameters)
{
    uart_event_t event;
    while (true) {
        if (xQueueReceive(uart_queue, &event, portMAX_DELAY)) {
            switch (event.type) {
                case UART_DATA_DONE:
                    efw_debug_async_tx_complete();
                    break;
                default:
                    break;
            }
        }
    }
}
*/

/* ==================================================================
 *  示例：通用裸机实现（轮询模式）
 * ================================================================== */

/*
// 如果没有 DMA，可以使用轮询模式
// 在主循环空闲时调用 efw_debug_async_flush()

void main_loop(void)
{
    // 1. 执行控制逻辑
    control_update();
    
    // 2. 更新调试数据（非阻塞）
    efw_debug_fast_update();
    
    // 3. 尝试发送调试数据（非阻塞）
    efw_debug_async_flush();
    
    // 4. 其他任务
    // ...
}
*/
