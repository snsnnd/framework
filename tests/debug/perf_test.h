/**
 * @file    perf_test.h
 * @brief   性能测试框架
 *
 * 提供统一的测试接口，用于比较不同调试方案的性能。
 */

#ifndef PERF_TEST_H
#define PERF_TEST_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ==================================================================
 *  测试结果结构
 * ================================================================== */

/** @brief 单项测试结果 */
typedef struct {
    const char *name;               /* 测试名称 */
    uint32_t iterations;            /* 迭代次数 */
    
    /* 时间统计（纳秒） */
    uint64_t total_ns;
    uint32_t min_ns;
    uint32_t max_ns;
    uint32_t avg_ns;
    uint32_t p50_ns;                /* 中位数 */
    uint32_t p95_ns;                /* 95 分位 */
    uint32_t p99_ns;                /* 99 分位 */
    
    /* 性能指标 */
    uint32_t over_10us_count;       /* 超过 10us 的次数 */
    uint32_t over_100us_count;      /* 超过 100us 的次数 */
    uint32_t over_1ms_count;        /* 超过 1ms 的次数 */
    
    /* 数据统计 */
    uint32_t bytes_transferred;     /* 传输字节数 */
    uint32_t points_updated;        /* 更新的监控点数 */
    
    bool passed;                    /* 是否通过 */
} perf_test_result_t;

/** @brief 测试套件结果 */
typedef struct {
    const char *suite_name;
    uint32_t test_count;
    uint32_t passed_count;
    uint32_t failed_count;
    perf_test_result_t results[32]; /* 最多 32 个测试 */
} perf_test_suite_t;

/* ==================================================================
 *  测试配置
 * ================================================================== */

/** @brief 测试配置 */
typedef struct {
    uint32_t iterations;            /* 迭代次数 */
    uint32_t warmup_iterations;     /* 预热次数 */
    uint32_t point_count;           /* 监控点数量 */
    uint32_t change_rate_percent;   /* 数据变化率（0-100） */
    uint32_t max_allowed_us;        /* 最大允许延迟（微秒） */
    bool measure_sync;              /* 是否测量同步时间 */
} perf_test_config_t;

/* ==================================================================
 *  测试 API
 * ================================================================== */

/**
 * @brief 初始化测试框架
 */
void perf_test_init(void);

/**
 * @brief 运行单个测试
 *
 * @param name 测试名称
 * @param setup_func 初始化函数
 * @param test_func 被测函数
 * @param teardown_func 清理函数
 * @param config 测试配置
 * @param result 输出结果
 */
typedef void (*perf_test_func_t)(void *ctx);
typedef void (*perf_test_setup_func_t)(void *ctx, const perf_test_config_t *config);

void perf_test_run(
    const char *name,
    perf_test_setup_func_t setup,
    perf_test_func_t test,
    perf_test_func_t teardown,
    void *ctx,
    const perf_test_config_t *config,
    perf_test_result_t *result
);

/**
 * @brief 打印测试结果
 */
void perf_test_print_result(const perf_test_result_t *result);

/**
 * @brief 打印测试套件结果
 */
void perf_test_print_suite(const perf_test_suite_t *suite);

/**
 * @brief 导出结果为 CSV
 */
void perf_test_export_csv(const perf_test_suite_t *suite, const char *filename);

/**
 * @brief 导出结果为 JSON
 */
void perf_test_export_json(const perf_test_suite_t *suite, const char *filename);

/* ==================================================================
 *  断言宏
 * ================================================================== */

#define PERF_ASSERT(condition) do { \
    if (!(condition)) { \
        result->passed = false; \
        return; \
    } \
} while(0)

#define PERF_ASSERT_LESS_THAN(value, max) do { \
    if ((value) >= (max)) { \
        result->passed = false; \
        return; \
    } \
} while(0)

#define PERF_ASSERT_GREATER_THAN(value, min) do { \
    if ((value) <= (min)) { \
        result->passed = false; \
        return; \
    } \
} while(0)

#ifdef __cplusplus
}
#endif

#endif /* PERF_TEST_H */
