/**
 * @file    registry.h
 * @brief   算法注册表接口
 *
 * 本层管理所有算法实例的生命周期和调用。
 *
 * 框架将算法按用途分为 5 类 (efw_algo_type_t)：
 *   ┌──────────────────┬──────────────────────────────────────────┐
 *   │ EFW_ALGO_CONTROL  │ 控制算法：PID、LQR、MPC、模糊控制等        │
 *   │ EFW_ALGO_FILTER   │ 滤波算法：移动平均、卡尔曼滤波、互补滤波等  │
 *   │ EFW_ALGO_MAPPING  │ 映射/变换：线性映射、标定曲线查表、坐标变换 │
 *   │ EFW_ALGO_PLANNING  │ 规划算法：轨迹生成、速度规划、路径平滑      │
 *   │ EFW_ALGO_CUSTOM   │ 自定义算法                               │
 *   └──────────────────┴──────────────────────────────────────────┘
 *
 * 框架内置了两个算法的实现（见 algorithms.h）：
 *   ① PID 控制器    — 属于 EFW_ALGO_CONTROL 类型
 *   ② 滑动均值滤波   — 属于 EFW_ALGO_FILTER 类型
 *
 * 算法的统一接口：
 *   所有算法都通过 efw_algo_ops_t.run(ctx, in, out) 调用。
 *   in/out 是 void* 类型——具体指向什么结构体由各算法定义。
 *   例如 PID 要求 in 指向 efw_pid_input_t，out 指向 efw_pid_output_t。
 *
 * 调用方式：
 *   efw_algo_run("motor_pid", &input, &output);  // 按名称查找并执行
 *   或先 get 拿到 ops 再直接调用 run 回调（省去一次查找开销）
 */

#ifndef EFW_ALGORITHM_REGISTRY_H
#define EFW_ALGORITHM_REGISTRY_H

#include "efw/core/common.h"

/**
 * @brief 算法类型枚举
 */
typedef enum {
    EFW_ALGO_CONTROL   = 0, /**< 控制类算法：PID、模型预测控制、前馈控制等 */
    EFW_ALGO_FILTER,        /**< 滤波类算法：移动平均、低通/高通滤波、卡尔曼滤波等 */
    EFW_ALGO_MAPPING,       /**< 映射/变换类：标定曲线插值、坐标系变换、死区映射 */
    EFW_ALGO_PLANNING,      /**< 规划类算法：梯形速度规划、S 曲线、A* 路径搜索 */
    EFW_ALGO_CUSTOM         /**< 用户自定义：不属于以上四类的特殊算法 */
} efw_algo_type_t;

/**
 * @brief 算法操作接口结构体
 *
 * 所有算法都遵循统一的三参数接口：ctx (算法状态) → in (输入数据) → out (输出结果)
 *
 * @field name 全局唯一名称 (如 "left_pid", "gyro_filter", "speed_planner")
 *              运行时通过此名称查找并调用算法
 * @field type 算法类型 (efw_algo_type_t)，用于分类和统计
 * @field ctx  算法上下文指针 (如指向 efw_pid_t 或 efw_moving_avg_t 的指针)
 *              不同算法 ctx 指向不同的结构体，框架完全不关心内部结构
 * @field run  算法执行函数指针 (必填)
 *              签名: run(ctx=算法状态, in=输入数据, out=输出结果) → efw_status_t
 *              in 和 out 是 void* 类型，调用方需确保类型匹配
 */
typedef struct {
    const char *name;       /**< 全局唯一名称 */
    efw_algo_type_t type;   /**< 算法类型 */
    void *ctx;              /**< 算法上下文 (私有状态数据) */
    efw_status_t (*run)(void *ctx, const void *in, void *out); /**< 执行函数 */
} efw_algo_ops_t;

/* ====== 算法注册表 API ====== */

efw_status_t efw_algo_registry_init(void);
efw_status_t efw_algo_registry_init_pool(const efw_algo_ops_t **pool, size_t capacity);
efw_status_t efw_algo_register(const efw_algo_ops_t *ops);
efw_status_t efw_algo_get(const char *name, const efw_algo_ops_t **out_ops);
efw_status_t efw_algo_run(const char *name, const void *in, void *out);

#endif
