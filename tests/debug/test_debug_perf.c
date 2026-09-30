/**
 * @file    test_debug_perf.c
 * @brief   调试模块性能测试
 *
 * 测试各种调试方案的性能：
 *   1. 原始实现（全量更新）
 *   2. 增量更新
 *   3. 双缓冲
 *   4. 异步/DMA
 *   5. 条件编译（Release）
 */

#include "perf_test.h"
#include "mock_platform.h"
#include "efw/debug/efw_debug.h"
#include "efw/debug/efw_debug_fast.h"
#include "efw/debug/efw_debug_async.h"
#include <stdio.h>
#include <string.h>

/* ==================================================================
 *  测试数据
 * ================================================================== */

/** @brief 模拟的 EFW 框架数据 */
static struct {
    uint32_t hal_value[16];
    float sensor_value[32];
    uint32_t algo_value[16];
    uint32_t state_value[8];
    uint32_t custom_value[32];
} g_test_data = {0};

/** @brief 数据变化控制 */
static uint32_t g_change_counter = 0;
static uint32_t g_change_rate = 10;  /* 10% 变化率 */

/* ==================================================================
 *  辅助函数
 * ================================================================== */

/**
 * @brief 模拟数据变化
 */
static void simulate_data_change(void) {
    g_change_counter++;
    
    /* 根据变化率更新数据 */
    if (g_change_counter % (100 / g_change_rate) == 0) {
        /* 随机更新一个值 */
        uint32_t idx = g_change_counter % 32;
        g_test_data.sensor_value[idx] += 0.1f;
        
        idx = g_change_counter % 16;
        g_test_data.hal_value[idx]++;
    }
}

/**
 * @brief 重置测试数据
 */
static void reset_test_data(void) {
    memset(&g_test_data, 0, sizeof(g_test_data));
    g_change_counter = 0;
}

/* ==================================================================
 *  测试 1：原始实现（全量更新）
 * ================================================================== */

static void test_original_setup(void *ctx, const perf_test_config_t *config) {
    (void)ctx;
    reset_test_data();
    
    /* 初始化原始调试模块 */
    efw_debug_init();
    
    /* 注册监控点 */
    char name[32];
    for (uint32_t i = 0; i < config->point_count && i < 16; i++) {
        snprintf(name, sizeof(name), "hal_%u", i);
        efw_debug_register_custom(name, EFW_DEBUG_TYPE_U32, &g_test_data.hal_value[i]);
    }
    for (uint32_t i = 0; i < config->point_count - 16 && i < 32; i++) {
        snprintf(name, sizeof(name), "sensor_%u", i);
        efw_debug_register_custom(name, EFW_DEBUG_TYPE_F32, &g_test_data.sensor_value[i]);
    }
}

static void test_original_update(void *ctx) {
    (void)ctx;
    simulate_data_change();
    efw_debug_update();
}

static void test_original_teardown(void *ctx) {
    (void)ctx;
}

/* ==================================================================
 *  测试 2：增量更新
 * ================================================================== */

static void test_incremental_setup(void *ctx, const perf_test_config_t *config) {
    (void)ctx;
    reset_test_data();
    
    /* 初始化高性能调试模块 */
    efw_debug_fast_init();
    
    /* 注册监控点 */
    char name[32];
    uint16_t param_id = 0x1000;
    
    for (uint32_t i = 0; i < config->point_count && i < 16; i++) {
        snprintf(name, sizeof(name), "hal_%u", i);
        efw_debug_fast_register(name, 0x06, &g_test_data.hal_value[i], param_id++);
    }
    for (uint32_t i = 0; i < config->point_count - 16 && i < 32; i++) {
        snprintf(name, sizeof(name), "sensor_%u", i);
        efw_debug_fast_register(name, 0x0A, &g_test_data.sensor_value[i], param_id++);
    }
}

static void test_incremental_update(void *ctx) {
    (void)ctx;
    simulate_data_change();
    efw_debug_fast_update();
}

static void test_incremental_sync(void *ctx) {
    (void)ctx;
    simulate_data_change();
    efw_debug_fast_update();
    efw_debug_fast_sync();
}

static void test_incremental_teardown(void *ctx) {
    (void)ctx;
}

/* ==================================================================
 *  测试 3：异步/DMA
 * ================================================================== */

static void test_async_setup(void *ctx, const perf_test_config_t *config) {
    (void)ctx;
    reset_test_data();
    
    /* 初始化异步调试模块 */
    efw_debug_fast_init();
    efw_debug_async_init();
    
    /* 注册监控点 */
    char name[32];
    uint16_t param_id = 0x1000;
    
    for (uint32_t i = 0; i < config->point_count && i < 16; i++) {
        snprintf(name, sizeof(name), "hal_%u", i);
        efw_debug_fast_register(name, 0x06, &g_test_data.hal_value[i], param_id++);
    }
}

static void test_async_update(void *ctx) {
    (void)ctx;
    simulate_data_change();
    efw_debug_fast_update();
}

static void test_async_full(void *ctx) {
    (void)ctx;
    simulate_data_change();
    efw_debug_fast_update();
    efw_debug_fast_sync();
    
    /* 模拟 DMA 完成 */
    mock_dma_complete();
    efw_debug_async_flush();
}

static void test_async_teardown(void *ctx) {
    (void)ctx;
}

/* ==================================================================
 *  测试 4：空操作（基准）
 * ================================================================== */

static void test_noop_setup(void *ctx, const perf_test_config_t *config) {
    (void)ctx;
    (void)config;
    reset_test_data();
}

static void test_noop_update(void *ctx) {
    (void)ctx;
    simulate_data_change();
    /* 不调用任何调试函数 */
}

static void test_noop_teardown(void *ctx) {
    (void)ctx;
}

/* ==================================================================
 *  主测试函数
 * ================================================================== */

int main(int argc, char *argv[]) {
    printf("\n");
    printf("╔══════════════════════════════════════════════════════════════╗\n");
    printf("║           EFW 调试模块性能测试                              ║\n");
    printf("╚══════════════════════════════════════════════════════════════╝\n");
    
    /* 初始化测试框架 */
    perf_test_init();
    
    /* 测试套件 */
    perf_test_suite_t suite = {
        .suite_name = "调试模块性能对比",
        .test_count = 0,
        .passed_count = 0,
        .failed_count = 0,
    };
    
    /* 测试配置 */
    perf_test_config_t configs[] = {
        /* 8 个监控点 */
        {
            .iterations = 10000,
            .warmup_iterations = 100,
            .point_count = 8,
            .change_rate_percent = 10,
            .max_allowed_us = 100,
            .measure_sync = true,
        },
        /* 32 个监控点 */
        {
            .iterations = 10000,
            .warmup_iterations = 100,
            .point_count = 32,
            .change_rate_percent = 10,
            .max_allowed_us = 200,
            .measure_sync = true,
        },
        /* 64 个监控点 */
        {
            .iterations = 10000,
            .warmup_iterations = 100,
            .point_count = 64,
            .change_rate_percent = 10,
            .max_allowed_us = 500,
            .measure_sync = true,
        },
    };
    
    const char *config_names[] = {"8 点", "32 点", "64 点"};
    uint32_t config_count = sizeof(configs) / sizeof(configs[0]);
    
    /* 运行测试 */
    for (uint32_t c = 0; c < config_count; c++) {
        printf("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");
        printf("  测试配置: %s\n", config_names[c]);
        printf("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");
        
        char test_name[64];
        
        /* 测试 1：基准（空操作） */
        snprintf(test_name, sizeof(test_name), "基准_%s", config_names[c]);
        perf_test_run(
            test_name,
            test_noop_setup,
            test_noop_update,
            test_noop_teardown,
            NULL,
            &configs[c],
            &suite.results[suite.test_count]
        );
        suite.test_count++;
        
        /* 测试 2：原始实现 */
        snprintf(test_name, sizeof(test_name), "原始_%s", config_names[c]);
        perf_test_run(
            test_name,
            test_original_setup,
            test_original_update,
            test_original_teardown,
            NULL,
            &configs[c],
            &suite.results[suite.test_count]
        );
        suite.test_count++;
        
        /* 测试 3：增量更新 */
        snprintf(test_name, sizeof(test_name), "增量_%s", config_names[c]);
        perf_test_run(
            test_name,
            test_incremental_setup,
            test_incremental_update,
            test_incremental_teardown,
            NULL,
            &configs[c],
            &suite.results[suite.test_count]
        );
        suite.test_count++;
        
        /* 测试 4：增量更新 + 同步 */
        snprintf(test_name, sizeof(test_name), "增量+同步_%s", config_names[c]);
        perf_test_run(
            test_name,
            test_incremental_setup,
            test_incremental_sync,
            test_incremental_teardown,
            NULL,
            &configs[c],
            &suite.results[suite.test_count]
        );
        suite.test_count++;
        
        /* 测试 5：异步更新 */
        snprintf(test_name, sizeof(test_name), "异步_%s", config_names[c]);
        perf_test_run(
            test_name,
            test_async_setup,
            test_async_update,
            test_async_teardown,
            NULL,
            &configs[c],
            &suite.results[suite.test_count]
        );
        suite.test_count++;
        
        /* 测试 6：异步完整流程 */
        snprintf(test_name, sizeof(test_name), "异步完整_%s", config_names[c]);
        perf_test_run(
            test_name,
            test_async_setup,
            test_async_full,
            test_async_teardown,
            NULL,
            &configs[c],
            &suite.results[suite.test_count]
        );
        suite.test_count++;
    }
    
    /* 统计通过/失败 */
    for (uint32_t i = 0; i < suite.test_count; i++) {
        if (suite.results[i].passed) {
            suite.passed_count++;
        } else {
            suite.failed_count++;
        }
    }
    
    /* 打印结果 */
    perf_test_print_suite(&suite);
    
    /* 导出结果 */
    perf_test_export_csv(&suite, "tests/debug/perf_results.csv");
    perf_test_export_json(&suite, "tests/debug/perf_results.json");
    
    /* 打印详细结果 */
    printf("\n\n══════════════════════════════════════════════════════════════\n");
    printf("  详细测试结果\n");
    printf("══════════════════════════════════════════════════════════════\n");
    
    for (uint32_t i = 0; i < suite.test_count; i++) {
        perf_test_print_result(&suite.results[i]);
    }
    
    return (suite.failed_count > 0) ? 1 : 0;
}
