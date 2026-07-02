/**
 * @file    perf_test.c
 * @brief   性能测试框架实现
 */

#include "perf_test.h"
#include "mock_platform.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

/* ==================================================================
 *  内部辅助函数
 * ================================================================== */

/**
 * @brief 比较函数（用于 qsort）
 */
static int compare_uint32(const void *a, const void *b) {
    uint32_t va = *(const uint32_t *)a;
    uint32_t vb = *(const uint32_t *)b;
    if (va < vb) return -1;
    if (va > vb) return 1;
    return 0;
}

/**
 * @brief 计算百分位数
 */
static uint32_t calculate_percentile(uint32_t *values, uint32_t count, uint32_t percentile) {
    if (count == 0) return 0;
    
    /* 排序 */
    qsort(values, count, sizeof(uint32_t), compare_uint32);
    
    /* 计算索引 */
    uint32_t index = (count * percentile) / 100;
    if (index >= count) index = count - 1;
    
    return values[index];
}

/* ==================================================================
 *  测试框架实现
 * ================================================================== */

void perf_test_init(void) {
    mock_init_default();
}

void perf_test_run(
    const char *name,
    perf_test_setup_func_t setup,
    perf_test_func_t test,
    perf_test_func_t teardown,
    void *ctx,
    const perf_test_config_t *config,
    perf_test_result_t *result
) {
    if (!name || !test || !config || !result) return;
    
    /* 初始化结果 */
    memset(result, 0, sizeof(perf_test_result_t));
    /* 复制名称字符串（避免指针失效问题） */
    static char name_buffer[32][64];
    static uint32_t name_index = 0;
    uint32_t idx = name_index++ % 32;
    strncpy(name_buffer[idx], name, 63);
    name_buffer[idx][63] = '\0';
    result->name = name_buffer[idx];
    result->iterations = config->iterations;
    result->passed = true;
    
    /* 分配时间记录数组 */
    uint32_t *timestamps = (uint32_t *)malloc(config->iterations * sizeof(uint32_t));
    if (!timestamps) {
        result->passed = false;
        return;
    }
    
    /* 设置阶段 */
    if (setup) {
        setup(ctx, config);
    }
    
    /* 预热 */
    for (uint32_t i = 0; i < config->warmup_iterations; i++) {
        test(ctx);
    }
    
    /* 正式测试 */
    result->min_ns = UINT32_MAX;
    result->max_ns = 0;
    uint64_t total_ns = 0;
    
    for (uint32_t i = 0; i < config->iterations; i++) {
        /* 开始测量 */
        mock_perf_begin();
        
        /* 执行被测函数 */
        test(ctx);
        
        /* 结束测量 */
        mock_perf_end();
        
        /* 计算本次耗时 */
        mock_perf_result_t perf_result;
        mock_perf_get_result(&perf_result);
        
        uint32_t elapsed_ns = (uint32_t)(perf_result.total_ns);
        timestamps[i] = elapsed_ns;
        
        /* 更新统计 */
        total_ns += elapsed_ns;
        
        if (elapsed_ns < result->min_ns) {
            result->min_ns = elapsed_ns;
        }
        if (elapsed_ns > result->max_ns) {
            result->max_ns = elapsed_ns;
        }
        
        /* 检查阈值 */
        if (elapsed_ns > 10000) {   /* > 10us */
            result->over_10us_count++;
        }
        if (elapsed_ns > 100000) {  /* > 100us */
            result->over_100us_count++;
        }
        if (elapsed_ns > 1000000) { /* > 1ms */
            result->over_1ms_count++;
        }
        
        /* 检查是否超过最大允许延迟 */
        if (config->max_allowed_us > 0 && 
            elapsed_ns > config->max_allowed_us * 1000) {
            result->passed = false;
        }
        
        /* 重置性能测量 */
        mock_perf_reset();
    }
    
    /* 计算统计值 */
    result->total_ns = total_ns;
    result->avg_ns = (uint32_t)(total_ns / config->iterations);
    result->p50_ns = calculate_percentile(timestamps, config->iterations, 50);
    result->p95_ns = calculate_percentile(timestamps, config->iterations, 95);
    result->p99_ns = calculate_percentile(timestamps, config->iterations, 99);
    
    /* 清理阶段 */
    if (teardown) {
        teardown(ctx);
    }
    
    free(timestamps);
}

void perf_test_print_result(const perf_test_result_t *result) {
    if (!result) return;
    
    printf("\n");
    printf("══════════════════════════════════════════════════════════════\n");
    printf("  测试: %s\n", result->name);
    printf("  状态: %s\n", result->passed ? "✓ 通过" : "✗ 失败");
    printf("══════════════════════════════════════════════════════════════\n");
    printf("  迭代次数:     %u\n", result->iterations);
    printf("  总耗时:       %.3f ms\n", result->total_ns / 1000000.0);
    printf("  平均耗时:     %.3f us\n", result->avg_ns / 1000.0);
    printf("  最小耗时:     %.3f us\n", result->min_ns / 1000.0);
    printf("  最大耗时:     %.3f us\n", result->max_ns / 1000.0);
    printf("  P50:          %.3f us\n", result->p50_ns / 1000.0);
    printf("  P95:          %.3f us\n", result->p95_ns / 1000.0);
    printf("  P99:          %.3f us\n", result->p99_ns / 1000.0);
    printf("──────────────────────────────────────────────────────────────\n");
    printf("  > 10us:       %u 次 (%.1f%%)\n", 
           result->over_10us_count,
           result->over_10us_count * 100.0 / result->iterations);
    printf("  > 100us:      %u 次 (%.1f%%)\n",
           result->over_100us_count,
           result->over_100us_count * 100.0 / result->iterations);
    printf("  > 1ms:        %u 次 (%.1f%%)\n",
           result->over_1ms_count,
           result->over_1ms_count * 100.0 / result->iterations);
    printf("══════════════════════════════════════════════════════════════\n");
}

void perf_test_print_suite(const perf_test_suite_t *suite) {
    if (!suite) return;
    
    printf("\n");
    printf("╔══════════════════════════════════════════════════════════════╗\n");
    printf("║  测试套件: %-48s ║\n", suite->suite_name);
    printf("╠══════════════════════════════════════════════════════════════╣\n");
    printf("║  总测试数: %-48u ║\n", suite->test_count);
    printf("║  通过:     %-48u ║\n", suite->passed_count);
    printf("║  失败:     %-48u ║\n", suite->failed_count);
    printf("╚══════════════════════════════════════════════════════════════╝\n");
    
    /* 打印对比表格 */
    printf("\n");
    printf("┌─────────────────────────────┬───────────┬───────────┬───────────┬───────────┬───────────┐\n");
    printf("│ 测试名称                     │ 平均 (us) │ P50 (us)  │ P95 (us)  │ 最大 (us) │ 状态      │\n");
    printf("├─────────────────────────────┼───────────┼───────────┼───────────┼───────────┼───────────┤\n");
    
    for (uint32_t i = 0; i < suite->test_count; i++) {
        const perf_test_result_t *r = &suite->results[i];
        printf("│ %-27s │ %9.3f │ %9.3f │ %9.3f │ %9.3f │ %-9s │\n",
               r->name,
               r->avg_ns / 1000.0,
               r->p50_ns / 1000.0,
               r->p95_ns / 1000.0,
               r->max_ns / 1000.0,
               r->passed ? "✓ 通过" : "✗ 失败");
    }
    
    printf("└─────────────────────────────┴───────────┴───────────┴───────────┴───────────┴───────────┘\n");
}

void perf_test_export_csv(const perf_test_suite_t *suite, const char *filename) {
    if (!suite || !filename) return;
    
    FILE *f = fopen(filename, "w");
    if (!f) return;
    
    /* 写入表头 */
    fprintf(f, "test_name,iterations,total_ms,avg_us,min_us,max_us,p50_us,p95_us,p99_us,over_10us,over_100us,over_1ms,passed\n");
    
    /* 写入数据 */
    for (uint32_t i = 0; i < suite->test_count; i++) {
        const perf_test_result_t *r = &suite->results[i];
        fprintf(f, "%s,%u,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%u,%u,%u,%s\n",
                r->name,
                r->iterations,
                r->total_ns / 1000000.0,
                r->avg_ns / 1000.0,
                r->min_ns / 1000.0,
                r->max_ns / 1000.0,
                r->p50_ns / 1000.0,
                r->p95_ns / 1000.0,
                r->p99_ns / 1000.0,
                r->over_10us_count,
                r->over_100us_count,
                r->over_1ms_count,
                r->passed ? "true" : "false");
    }
    
    fclose(f);
    printf("已导出 CSV: %s\n", filename);
}

void perf_test_export_json(const perf_test_suite_t *suite, const char *filename) {
    if (!suite || !filename) return;
    
    FILE *f = fopen(filename, "w");
    if (!f) return;
    
    fprintf(f, "{\n");
    fprintf(f, "  \"suite_name\": \"%s\",\n", suite->suite_name);
    fprintf(f, "  \"test_count\": %u,\n", suite->test_count);
    fprintf(f, "  \"passed_count\": %u,\n", suite->passed_count);
    fprintf(f, "  \"failed_count\": %u,\n", suite->failed_count);
    fprintf(f, "  \"results\": [\n");
    
    for (uint32_t i = 0; i < suite->test_count; i++) {
        const perf_test_result_t *r = &suite->results[i];
        fprintf(f, "    {\n");
        fprintf(f, "      \"name\": \"%s\",\n", r->name);
        fprintf(f, "      \"iterations\": %u,\n", r->iterations);
        fprintf(f, "      \"total_ns\": %llu,\n", (unsigned long long)r->total_ns);
        fprintf(f, "      \"avg_ns\": %u,\n", r->avg_ns);
        fprintf(f, "      \"min_ns\": %u,\n", r->min_ns);
        fprintf(f, "      \"max_ns\": %u,\n", r->max_ns);
        fprintf(f, "      \"p50_ns\": %u,\n", r->p50_ns);
        fprintf(f, "      \"p95_ns\": %u,\n", r->p95_ns);
        fprintf(f, "      \"p99_ns\": %u,\n", r->p99_ns);
        fprintf(f, "      \"passed\": %s\n", r->passed ? "true" : "false");
        fprintf(f, "    }%s\n", (i < suite->test_count - 1) ? "," : "");
    }
    
    fprintf(f, "  ]\n");
    fprintf(f, "}\n");
    
    fclose(f);
    printf("已导出 JSON: %s\n", filename);
}
