/**
 * @file    mock_platform.c
 * @brief   MCU 平台模拟层实现
 */

#include "mock_platform.h"
#include "efw/core/common.h"
#include <string.h>
#include <time.h>

#ifdef _WIN32
#include <windows.h>
#else
#include <sys/time.h>
#endif

/* ==================================================================
 *  内部状态
 * ================================================================== */

static struct {
    /* 定时器 */
    uint64_t timer_start_ns;
    uint32_t clock_mhz;
    
    /* DMA */
    struct {
        bool busy;
        uint32_t delay_us;
        mock_dma_callback_t callback;
        uint8_t buffer[4096];
        uint16_t length;
    } dma;
    
    /* UART */
    struct {
        uint32_t baud;
        uint8_t tx_buffer[4096];
        uint16_t tx_length;
        uint16_t tx_pos;
    } uart;
    
    /* 性能测量 */
    struct {
        uint64_t begin_ns;
        uint64_t total_ns;
        uint32_t min_ns;
        uint32_t max_ns;
        uint32_t count;
        uint32_t over_limit_count;
        uint32_t threshold_ns;
    } perf;
    
} g_mock = {0};

/* ==================================================================
 *  平台相关时间函数
 * ================================================================== */

#ifdef _WIN32

static uint64_t get_time_ns_win32(void) {
    static LARGE_INTEGER freq = {0};
    LARGE_INTEGER counter;
    
    if (freq.QuadPart == 0) {
        QueryPerformanceFrequency(&freq);
    }
    
    QueryPerformanceCounter(&counter);
    return (uint64_t)(counter.QuadPart * 1000000000ULL / freq.QuadPart);
}

#else

static uint64_t get_time_ns_posix(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

#endif

static uint64_t get_time_ns(void) {
#ifdef _WIN32
    return get_time_ns_win32();
#else
    return get_time_ns_posix();
#endif
}

/* ==================================================================
 *  定时器实现
 * ================================================================== */

uint32_t mock_get_time_us(void) {
    uint64_t ns = get_time_ns() - g_mock.timer_start_ns;
    return (uint32_t)(ns / 1000);
}

uint64_t mock_get_time_ns(void) {
    return get_time_ns() - g_mock.timer_start_ns;
}

void mock_timer_reset(void) {
    g_mock.timer_start_ns = get_time_ns();
}

void mock_set_clock_mhz(uint32_t mhz) {
    g_mock.clock_mhz = mhz;
}

/* ==================================================================
 *  DMA 模拟实现
 * ================================================================== */

void mock_dma_init(void) {
    g_mock.dma.busy = false;
    g_mock.dma.callback = NULL;
    g_mock.dma.length = 0;
    g_mock.dma.delay_us = 10;  /* 默认 10us */
}

int mock_dma_start(const uint8_t *data, uint16_t length, mock_dma_callback_t callback) {
    if (g_mock.dma.busy) {
        return -1;  /* DMA 忙 */
    }
    
    if (length > sizeof(g_mock.dma.buffer)) {
        return -1;  /* 缓冲区溢出 */
    }
    
    /* 拷贝数据到 DMA 缓冲区 */
    memcpy(g_mock.dma.buffer, data, length);
    g_mock.dma.length = length;
    g_mock.dma.callback = callback;
    g_mock.dma.busy = true;
    
    return 0;
}

void mock_dma_complete(void) {
    if (g_mock.dma.busy && g_mock.dma.callback) {
        g_mock.dma.callback();
    }
    g_mock.dma.busy = false;
}

bool mock_dma_is_busy(void) {
    return g_mock.dma.busy;
}

void mock_dma_set_delay_us(uint32_t delay) {
    g_mock.dma.delay_us = delay;
}

/* ==================================================================
 *  UART 模拟实现
 * ================================================================== */

void mock_uart_init(void) {
    g_mock.uart.baud = 115200;
    g_mock.uart.tx_length = 0;
    g_mock.uart.tx_pos = 0;
}

int mock_uart_send(const uint8_t *data, uint16_t length) {
    /* 计算传输延迟：字节数 * 10 bits / 波特率 */
    uint32_t byte_time_us = (10 * 1000000) / g_mock.uart.baud;
    uint32_t total_delay_us = length * byte_time_us;
    
    /* 模拟延迟 */
    uint64_t start = get_time_ns();
    while ((get_time_ns() - start) < (uint64_t)total_delay_us * 1000) {
        /* 忙等待 */
    }
    
    /* 保存发送数据 */
    uint16_t copy_len = (length < sizeof(g_mock.uart.tx_buffer) - g_mock.uart.tx_length) 
                        ? length 
                        : sizeof(g_mock.uart.tx_buffer) - g_mock.uart.tx_length;
    
    memcpy(&g_mock.uart.tx_buffer[g_mock.uart.tx_length], data, copy_len);
    g_mock.uart.tx_length += copy_len;
    
    return copy_len;
}

int mock_uart_get_sent(uint8_t *buffer, uint16_t max_length) {
    uint16_t copy_len = (g_mock.uart.tx_length < max_length) 
                        ? g_mock.uart.tx_length 
                        : max_length;
    
    memcpy(buffer, g_mock.uart.tx_buffer, copy_len);
    return copy_len;
}

void mock_uart_flush(void) {
    g_mock.uart.tx_length = 0;
    g_mock.uart.tx_pos = 0;
}

void mock_uart_set_baud(uint32_t baud) {
    g_mock.uart.baud = baud;
}

/* ==================================================================
 *  性能测量实现
 * ================================================================== */

void mock_perf_begin(void) {
    g_mock.perf.begin_ns = get_time_ns();
}

void mock_perf_end(void) {
    uint64_t elapsed = get_time_ns() - g_mock.perf.begin_ns;
    
    g_mock.perf.total_ns += elapsed;
    g_mock.perf.count++;
    
    if (g_mock.perf.count == 1) {
        g_mock.perf.min_ns = (uint32_t)elapsed;
        g_mock.perf.max_ns = (uint32_t)elapsed;
    } else {
        if ((uint32_t)elapsed < g_mock.perf.min_ns) {
            g_mock.perf.min_ns = (uint32_t)elapsed;
        }
        if ((uint32_t)elapsed > g_mock.perf.max_ns) {
            g_mock.perf.max_ns = (uint32_t)elapsed;
        }
    }
    
    if (elapsed > g_mock.perf.threshold_ns) {
        g_mock.perf.over_limit_count++;
    }
}

void mock_perf_get_result(mock_perf_result_t *result) {
    if (!result) return;
    
    result->total_ns = g_mock.perf.total_ns;
    result->min_ns = g_mock.perf.min_ns;
    result->max_ns = g_mock.perf.max_ns;
    result->count = g_mock.perf.count;
    result->over_limit_count = g_mock.perf.over_limit_count;
    
    if (g_mock.perf.count > 0) {
        result->avg_ns = (uint32_t)(g_mock.perf.total_ns / g_mock.perf.count);
    } else {
        result->avg_ns = 0;
    }
}

void mock_perf_reset(void) {
    memset(&g_mock.perf, 0, sizeof(g_mock.perf));
}

void mock_perf_set_threshold_us(uint32_t threshold_us) {
    g_mock.perf.threshold_ns = threshold_us * 1000;
}

/* ==================================================================
 *  初始化
 * ================================================================== */

void mock_init_default(void) {
    mock_config_t config = {
        .clock_mhz = 168,           /* STM32F4 典型频率 */
        .uart_baud = 115200,
        .dma_delay_us = 10,
        .perf_threshold_us = 100,   /* 100us 阈值 */
        .enable_dma = true,
        .enable_interrupt = true,
    };
    
    mock_init(&config);
}

void mock_init(const mock_config_t *config) {
    if (!config) return;
    
    memset(&g_mock, 0, sizeof(g_mock));
    
    g_mock.clock_mhz = config->clock_mhz;
    g_mock.uart.baud = config->uart_baud;
    g_mock.dma.delay_us = config->dma_delay_us;
    g_mock.perf.threshold_ns = config->perf_threshold_us * 1000;
    
    mock_timer_reset();
}

void mock_get_config(mock_config_t *config) {
    if (!config) return;
    
    config->clock_mhz = g_mock.clock_mhz;
    config->uart_baud = g_mock.uart.baud;
    config->dma_delay_us = g_mock.dma.delay_us;
    config->perf_threshold_us = g_mock.perf.threshold_ns / 1000;
    config->enable_dma = true;
    config->enable_interrupt = true;
}

/* ==================================================================
 *  平台 API 实现（供 efw_debug_fast.c 使用）
 * ================================================================== */

/**
 * @brief 获取当前时间（微秒）- 实现 efw_debug_fast.h 中声明的函数
 */
uint32_t efw_debug_get_us(void) {
    return mock_get_time_us();
}

/**
 * @brief 启动 DMA 传输 - 实现 efw_debug_async.h 中声明的函数
 */
efw_status_t efw_debug_start_dma(const uint8_t *data, uint16_t length) {
    int ret = mock_dma_start(data, length, NULL);
    return (ret == 0) ? EFW_OK : EFW_ERR_IO;
}

/**
 * @brief 注册传输完成回调 - 实现 efw_debug_async.h 中声明的函数
 */
void efw_debug_register_tx_callback(void (*callback)(void)) {
    /* 在测试中，我们手动调用回调 */
    (void)callback;
}
