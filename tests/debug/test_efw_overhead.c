/**
 * @file    test_efw_overhead.c
 * @brief   EFW 框架本身开销测试
 */

#include "perf_test.h"
#include "mock_platform.h"
#include "efw/core/common.h"
#include "efw/hal/hal.h"
#include "efw/device/sensor.h"
#include "efw/algorithm/registry.h"
#include "efw/state/state_machine.h"
#include <stdio.h>
#include <string.h>

/* ==================================================================
 *  模拟数据
 * ================================================================== */

static uint32_t g_hal_read_count = 0;
static float g_sensor_data[8] = {0};
static float g_algo_output = 0;

/* ==================================================================
 *  模拟 HAL 操作
 * ================================================================== */

static efw_status_t mock_hal_init(void *ctx) {
    (void)ctx;
    return EFW_OK;
}

static efw_status_t mock_hal_read(void *ctx, void *buf, uint16_t len, uint16_t *actual) {
    (void)ctx;
    if (buf && len >= 4) {
        *(uint32_t *)buf = g_hal_read_count++;
        if (actual) *actual = 4;
    }
    return EFW_OK;
}

static efw_status_t mock_hal_write(void *ctx, const void *buf, uint16_t len, uint16_t *actual) {
    (void)ctx; (void)buf; (void)len;
    if (actual) *actual = len;
    return EFW_OK;
}

/* ==================================================================
 *  模拟传感器操作
 * ================================================================== */

static efw_status_t mock_sensor_init(void *ctx) {
    (void)ctx;
    return EFW_OK;
}

static efw_status_t mock_sensor_read(void *ctx, void *out, uint16_t out_size) {
    (void)ctx;
    if (out && out_size >= sizeof(float)) {
        *(float *)out = g_sensor_data[0];
    }
    return EFW_OK;
}

/* ==================================================================
 *  模拟算法操作
 * ================================================================== */

static efw_status_t mock_algo_run(void *ctx, const void *in, uint16_t in_size, void *out, uint16_t out_size) {
    (void)ctx; (void)in; (void)in_size;
    if (out && out_size >= sizeof(float)) {
        g_algo_output += 0.1f;
        *(float *)out = g_algo_output;
    }
    return EFW_OK;
}

/* ==================================================================
 *  测试函数
 * ================================================================== */

/**
 * @brief 测试 HAL 注册表查找开销
 */
static void test_hal_lookup(void *ctx) {
    (void)ctx;
    const efw_hal_ops_t *ops;
    efw_hal_get("test_hal", &ops);
}

/**
 * @brief 测试 HAL 读取开销
 */
static void test_hal_read(void *ctx) {
    (void)ctx;
    uint32_t value;
    uint16_t actual;
    efw_hal_read("test_hal", &value, sizeof(value), &actual);
}

/**
 * @brief 测试传感器读取开销
 */
static void test_sensor_read(void *ctx) {
    (void)ctx;
    float value;
    efw_sensor_read("test_sensor", &value, sizeof(value));
}

/**
 * @brief 测试算法执行开销
 */
static void test_algo_run(void *ctx) {
    (void)ctx;
    float input = 1.0f;
    float output;
    efw_algo_run("test_algo", &input, sizeof(input), &output, sizeof(output));
}

/**
 * @brief 测试完整数据流（HAL -> Sensor -> Algo）
 */
static void test_full_pipeline(void *ctx) {
    (void)ctx;
    
    /* 1. HAL 读取 */
    uint32_t hal_value;
    uint16_t actual;
    efw_hal_read("test_hal", &hal_value, sizeof(hal_value), &actual);
    
    /* 2. 传感器读取 */
    float sensor_value;
    efw_sensor_read("test_sensor", &sensor_value, sizeof(sensor_value));
    
    /* 3. 算法执行 */
    float algo_input = sensor_value;
    float algo_output;
    efw_algo_run("test_algo", &algo_input, sizeof(algo_input), &algo_output, sizeof(algo_output));
    
    /* 4. 更新全局状态 */
    g_sensor_data[0] = algo_output;
}

/**
 * @brief 测试纯计算开销（无框架调用）
 */
static void test_pure_computation(void *ctx) {
    (void)ctx;
    
    /* 模拟相同的计算，但不通过框架 */
    uint32_t hal_value = g_hal_read_count++;
    float sensor_value = g_sensor_data[0];
    float algo_output = sensor_value + 0.1f;
    g_sensor_data[0] = algo_output;
}

/* ==================================================================
 *  Setup/Teardown
 * ================================================================== */

static void setup_with_registration(void *ctx, const perf_test_config_t *config) {
    (void)ctx; (void)config;
    
    /* 注册 HAL */
    static efw_hal_ops_t hal_ops = {
        .name = "test_hal",
        .type = EFW_HAL_GPIO,
        .bus_id = 0,
        .ctx = NULL,
        .init = mock_hal_init,
        .read = mock_hal_read,
        .write = mock_hal_write,
        .ioctl = NULL,
    };
    efw_hal_register(&hal_ops);
    
    /* 注册传感器 */
    static efw_sensor_ops_t sensor_ops = {
        .name = "test_sensor",
        .type = EFW_SENSOR_CUSTOM,
        .channel_count = 1,
        .hal_name = "test_hal",
        .comm_name = NULL,
        .ctx = NULL,
        .init = mock_sensor_init,
        .read = mock_sensor_read,
    };
    efw_sensor_register(&sensor_ops);
    
    /* 注册算法 */
    static efw_algo_ops_t algo_ops = {
        .name = "test_algo",
        .type = EFW_ALGO_FILTER,
        .ctx = NULL,
        .run = mock_algo_run,
    };
    efw_algo_register(&algo_ops);
}

static void teardown_noop(void *ctx) {
    (void)ctx;
}

/* ==================================================================
 *  主测试函数
 * ================================================================== */

int main(int argc, char *argv[]) {
    printf("\n");
    printf("╔══════════════════════════════════════════════════════════════╗\n");
    printf("║           EFW 框架开销测试                                 ║\n");
    printf("╚══════════════════════════════════════════════════════════════╝\n");
    
    /* 初始化 */
    perf_test_init();
    efw_hal_registry_init();
    efw_sensor_registry_init();
    efw_algo_registry_init();
    
    /* 测试套件 */
    perf_test_suite_t suite = {
        .suite_name = "EFW 框架开销",
        .test_count = 0,
        .passed_count = 0,
        .failed_count = 0,
    };
    
    perf_test_config_t config = {
        .iterations = 100000,
        .warmup_iterations = 1000,
        .point_count = 1,
        .change_rate_percent = 100,
        .max_allowed_us = 10,
        .measure_sync = false,
    };
    
    /* 注册组件 */
    setup_with_registration(NULL, &config);
    
    /* 测试各个操作 */
    perf_test_run("HAL 查找", NULL, test_hal_lookup, teardown_noop, NULL, &config, &suite.results[suite.test_count++]);
    perf_test_run("HAL 读取", NULL, test_hal_read, teardown_noop, NULL, &config, &suite.results[suite.test_count++]);
    perf_test_run("传感器读取", NULL, test_sensor_read, teardown_noop, NULL, &config, &suite.results[suite.test_count++]);
    perf_test_run("算法执行", NULL, test_algo_run, teardown_noop, NULL, &config, &suite.results[suite.test_count++]);
    perf_test_run("完整流水线", NULL, test_full_pipeline, teardown_noop, NULL, &config, &suite.results[suite.test_count++]);
    perf_test_run("纯计算", NULL, test_pure_computation, teardown_noop, NULL, &config, &suite.results[suite.test_count++]);
    
    /* 统计 */
    for (uint32_t i = 0; i < suite.test_count; i++) {
        if (suite.results[i].passed) {
            suite.passed_count++;
        } else {
            suite.failed_count++;
        }
    }
    
    /* 打印结果 */
    perf_test_print_suite(&suite);
    
    /* 打印详细结果 */
    printf("\n══════════════════════════════════════════════════════════════\n");
    printf("  分析\n");
    printf("══════════════════════════════════════════════════════════════\n");
    
    /* 计算框架开销 */
    uint32_t pure_ns = suite.results[5].avg_ns;
    uint32_t pipeline_ns = suite.results[4].avg_ns;
    uint32_t overhead_ns = pipeline_ns - pure_ns;
    
    printf("\n");
    printf("  纯计算耗时:      %u ns\n", pure_ns);
    printf("  完整流水线耗时:   %u ns\n", pipeline_ns);
    printf("  框架开销:         %u ns\n", overhead_ns);
    printf("  开销占比:         %.1f%%\n", overhead_ns * 100.0 / pipeline_ns);
    
    printf("\n");
    printf("  各组件开销:\n");
    printf("    HAL 查找:       %u ns\n", suite.results[0].avg_ns);
    printf("    HAL 读取:       %u ns\n", suite.results[1].avg_ns);
    printf("    传感器读取:     %u ns\n", suite.results[2].avg_ns);
    printf("    算法执行:       %u ns\n", suite.results[3].avg_ns);
    
    return (suite.failed_count > 0) ? 1 : 0;
}
