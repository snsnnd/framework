/**
 * @file    module.h
 * @brief   Module (模块生命周期层) 注册表接口
 *
 * 本层管理软件模块的完整生命周期。模块是最高层次的抽象，代表一个
 * 有独立功能的软件单元（驱动封装、后台服务、应用任务等）。
 *
 * 模块类型 (efw_module_type_t)：
 *   EFW_MODULE_DRIVER  — 驱动封装模块 (如电机驱动、显示屏驱动)
 *   EFW_MODULE_SERVICE — 后台服务模块 (如日志系统、参数存储服务)
 *   EFW_MODULE_APP     — 应用任务模块 (如循迹任务、避障任务)
 *   EFW_MODULE_CUSTOM  — 自定义类型模块
 *
 * 模块生命周期（四阶段）：
 *   init ──→ start ──→ poll (循环) ──→ stop
 *
 *   ① init  : 模块初始化（分配资源、注册子组件、初始化内部状态）
 *             → 框架提供 efw_module_init_all() 一次性初始化所有模块
 *   ② start : 模块启动（开始运行，使能中断，启动定时器）
 *             → 框架提供 efw_module_start_all() 一次性启动所有模块
 *   ③ poll  : 模块轮询（在主循环中周期性调用，处理数据、更新状态）
 *             → 它是框架的核心运行机制：main 循环中反复调用 efw_module_poll_all()
 *   ④ stop  : 模块停止（关闭中断、释放资源、安全停机）
 *             → 逐个调用 efw_module_stop("name")
 *
 * 注意：
 *   所有回调都是可空的——如果某个模块不需要 start 阶段，将其设为 NULL 即可，
 *   module_call 内部会对 NULL 回调返回 EFW_OK 跳过。
 */

#ifndef EFW_MODULE_REGISTRY_H
#define EFW_MODULE_REGISTRY_H

#include "efw/core/common.h"

/**
 * @brief 模块类型枚举
 */
typedef enum {
    EFW_MODULE_DRIVER  = 0, /**< 驱动封装：电机驱动、显示驱动、存储芯片驱动 */
    EFW_MODULE_SERVICE,     /**< 后台服务：日志、参数存储、看门狗喂狗、心跳 */
    EFW_MODULE_APP,         /**< 应用任务：循迹控制、避障决策、遥控解析 */
    EFW_MODULE_CUSTOM       /**< 自定义：不属于以上分类的模块 */
} efw_module_type_t;

/**
 * @brief 模块操作接口结构体
 *
 * @field name  全局唯一名称 (如 "motor_drv", "logger", "line_tracker")
 * @field type  模块类型 (efw_module_type_t)
 * @field ctx   用户私有上下文 (指向模块内部状态结构体)
 * @field init  初始化回调 (可空)
 *              典型操作：注册子组件、初始化数据结构、设置默认参数
 * @field start 启动回调 (可空)
 *              典型操作：使能外设中断、启动 DMA、开始定时器
 * @field stop  停止回调 (可空)
 *              典型操作：关闭中断、停止 DMA、安全保存参数、进入低功耗
 * @field poll  轮询回调 (可空，但通常需要实现)
 *              在主循环中被反复调用。典型操作：
 *              - 读取传感器 → 运行算法 → 控制执行器
 *              - 检查通信缓冲区 → 解析协议帧 → 更新系统状态
 */
typedef struct {
    const char *name;       /**< 全局唯一名称 */
    efw_module_type_t type; /**< 模块类型 */
    uint8_t priority;       /**< 轮询优先级 (0=最高, 255=最低, 默认0) */
    void *ctx;              /**< 用户私有上下文 */
    efw_status_t (*init)(void *ctx);   /**< 初始化回调 (可空) */
    efw_status_t (*start)(void *ctx);  /**< 启动回调 (可空) */
    efw_status_t (*stop)(void *ctx);   /**< 停止回调 (可空) */
    efw_status_t (*poll)(void *ctx);   /**< 轮询回调 (可空) */
} efw_module_ops_t;

/* ====== 模块生命周期 API ====== */

efw_status_t efw_module_registry_init(void);
efw_status_t efw_module_registry_init_pool(const efw_module_ops_t **pool, size_t capacity);
efw_status_t efw_module_register(const efw_module_ops_t *ops);
efw_status_t efw_module_get(const char *name, const efw_module_ops_t **out_ops);
efw_status_t efw_module_unregister(const char *name);
size_t efw_module_count(void);
typedef void (*efw_module_enumerate_fn)(const efw_module_ops_t *ops, void *user);
void efw_module_enumerate(efw_module_enumerate_fn fn, void *user);

/* 单模块操作：按名称操作指定模块 */
efw_status_t efw_module_init(const char *name);
efw_status_t efw_module_start(const char *name);
efw_status_t efw_module_stop(const char *name);
efw_status_t efw_module_poll(const char *name);

/* 批量操作：遍历所有已注册模块，按注册顺序依次执行 */
efw_status_t efw_module_init_all(void);
efw_status_t efw_module_start_all(void);
efw_status_t efw_module_poll_all(void);

size_t efw_module_count_by_type(efw_module_type_t type);

#endif
