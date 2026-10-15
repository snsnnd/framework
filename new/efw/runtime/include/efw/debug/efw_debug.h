/**
 * @file    efw_debug.h
 * @brief   EFW 在线调试模块 - MCU 监控点表与 LiteTune 集成基础
 *
 * 本模块维护 EFW 框架内部数据（HAL/传感器/算法/模块/状态机）和用户
 * 自定义变量的监控点表。LiteTune 参数描述和传输由集成层显式接入。
 *
 * 功能特性：
 *   - 自动采集 EFW 注册表数据
 *   - 支持用户自定义监控点
 *   - 提供 LiteTune 集成所需的遍历和快照基础
 *   - 零动态内存分配，适合裸机环境
 *
 * 使用流程：
 *   ① 调用 efw_debug_init() 初始化
 *   ② 调用 efw_debug_register_efw_*() 注册 EFW 框架数据
 *   ③ 调用 efw_debug_register_custom() 注册自定义监控点
 *   ④ 在主循环中调用 efw_debug_update() 更新数据
 *   ⑤ 由 LiteTune 集成层或应用代码导出快照/上报给 Host
 */

#ifndef EFW_DEBUG_H
#define EFW_DEBUG_H

#include "efw/core/common.h"
#include "efw/core/config.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ==================================================================
 *  配置宏
 * ================================================================== */

/** @brief 最大监控点数量 */
#ifndef EFW_MAX_DEBUG_POINTS
#define EFW_MAX_DEBUG_POINTS 64
#endif

/** @brief 监控点名称最大长度 */
#ifndef EFW_DEBUG_NAME_MAX_LEN
#define EFW_DEBUG_NAME_MAX_LEN 32
#endif

/* ==================================================================
 *  类型定义
 * ================================================================== */

/**
 * @brief 监控点数据类型枚举
 */
typedef enum {
    EFW_DEBUG_TYPE_BOOL = 0,    /**< 布尔值 */
    EFW_DEBUG_TYPE_U8,          /**< 无符号 8 位整数 */
    EFW_DEBUG_TYPE_I8,          /**< 有符号 8 位整数 */
    EFW_DEBUG_TYPE_U16,         /**< 无符号 16 位整数 */
    EFW_DEBUG_TYPE_I16,         /**< 有符号 16 位整数 */
    EFW_DEBUG_TYPE_U32,         /**< 无符号 32 位整数 */
    EFW_DEBUG_TYPE_I32,         /**< 有符号 32 位整数 */
    EFW_DEBUG_TYPE_F32,         /**< 32 位浮点数 */
    EFW_DEBUG_TYPE_F64,         /**< 64 位浮点数 */
    EFW_DEBUG_TYPE_STRING,      /**< 字符串 */
} efw_debug_type_t;

/**
 * @brief 监控点来源类型枚举
 */
typedef enum {
    EFW_DEBUG_SOURCE_HAL = 0,       /**< HAL 层数据 */
    EFW_DEBUG_SOURCE_COMM,          /**< COMM 层数据 */
    EFW_DEBUG_SOURCE_SENSOR,        /**< 传感器数据 */
    EFW_DEBUG_SOURCE_ACTUATOR,      /**< 执行器数据 */
    EFW_DEBUG_SOURCE_ALGORITHM,     /**< 算法数据 */
    EFW_DEBUG_SOURCE_MODULE,        /**< 模块数据 */
    EFW_DEBUG_SOURCE_STATE_MACHINE, /**< 状态机数据 */
    EFW_DEBUG_SOURCE_CUSTOM,        /**< 用户自定义 */
} efw_debug_source_t;

/**
 * @brief 监控点描述结构体
 */
typedef struct {
    char name[EFW_DEBUG_NAME_MAX_LEN]; /**< 监控点名称 */
    efw_debug_source_t source;          /**< 数据来源类型 */
    efw_debug_type_t type;              /**< 数据类型 */
    const void *value_ptr;              /**< 指向实际数据的指针 */
    uint16_t param_id;                  /**< LiteTune 参数 ID */
    uint8_t registered;                 /**< 是否已注册 */
} efw_debug_point_t;

/**
 * @brief 调试模块统计信息
 */
typedef struct {
    uint16_t total_points;          /**< 总监控点数 */
    uint16_t efw_points;            /**< EFW 框架监控点数 */
    uint16_t custom_points;         /**< 自定义监控点数 */
    uint32_t update_count;          /**< 更新次数 */
    uint32_t error_count;           /**< 错误次数 */
} efw_debug_stats_t;

/** @brief 调试监控点遍历回调 */
typedef void (*efw_debug_point_iter_fn)(const efw_debug_point_t *point, void *user);
typedef void (*efw_debug_event_sink_fn)(const char *event, const char *name, const char *detail, void *user);

/* ==================================================================
 *  核心 API
 * ================================================================== */

/**
 * @brief 初始化调试模块
 *
 * 必须在 efw_init() 之后调用。此函数只初始化 EFW 调试表，不初始化
 * LiteTune 协议栈。
 *
 * @return EFW_OK 成功，其他值表示失败
 */
efw_status_t efw_debug_init(void);

/**
 * @brief 更新所有监控点数据
 *
 * 应在主循环中定期调用，检查已注册监控点仍可读取并更新统计信息。
 * LiteTune 参数同步由集成层负责。
 * 调用频率取决于应用需求，通常 10ms~100ms 调用一次。
 *
 * @return EFW_OK 成功，其他值表示失败
 */
efw_status_t efw_debug_update(void);

/**
 * @brief 获取调试模块统计信息
 * @param stats 输出统计信息
 * @return EFW_OK 成功，其他值表示失败
 */
efw_status_t efw_debug_get_stats(efw_debug_stats_t *stats);
void efw_debug_set_event_sink(efw_debug_event_sink_fn sink, void *user);
void efw_debug_emit_event(const char *event, const char *name, const char *detail);
void efw_debug_attach_runtime_trace(void);

/**
 * @brief 获取已注册监控点数量
 * @return 监控点数量
 */
uint16_t efw_debug_point_count(void);

/**
 * @brief 遍历所有已注册监控点
 *
 * 集成层不得访问调试模块内部静态状态；需要查看监控点时通过此 API。
 */
void efw_debug_foreach_point(efw_debug_point_iter_fn callback, void *user);

/* ==================================================================
 *  EFW 框架数据注册 API
 * ================================================================== */

/**
 * @brief 注册所有 HAL 层数据为监控点
 *
 * 自动遍历 HAL 注册表，为每个已注册的 HAL 实例创建监控点。
 * 监控点名称格式: "hal.{name}"
 *
 * @return 成功注册的监控点数量，负值表示错误
 */
int efw_debug_register_efw_hal(void);

/**
 * @brief 注册所有传感器数据为监控点
 *
 * 传感器输出类型和存储不属于 efw_sensor_ops_t，故本函数不会把 opaque
 * ops->ctx 猜测为 float 读数，也不会自动创建虚假监控点。应用应在持有
 * 最新值存储时调用 efw_debug_register_sensor_value()。
 *
 * @return 成功注册的监控点数量，负值表示错误
 */
int efw_debug_register_efw_sensors(void);

/**
 * @brief 注册应用拥有的传感器最新值。
 *
 * 传感器 ctx 是不透明的，调试模块不会把它当作读数解释；应用负责更新
 * latest_value，并保证该地址在监控点注销前一直有效。
 */
efw_status_t efw_debug_register_sensor_value(const char *sensor_name,
                                             efw_debug_type_t type,
                                             const void *latest_value);

/**
 * @brief 注册所有算法数据为监控点
 *
 * 自动遍历算法注册表，为每个已注册的算法创建监控点。
 * 监控点名称格式: "algo.{name}.type", "algo.{name}.ctx"
 *
 * @return 成功注册的监控点数量，负值表示错误
 */
int efw_debug_register_efw_algorithms(void);

/**
 * @brief 注册所有状态机数据为监控点
 *
 * 自动遍历状态机注册表，为每个已注册的状态机创建监控点。
 * 监控点名称格式: "sm.{name}.state_hash", "sm.{name}.time_ms"
 *
 * @return 成功注册的监控点数量，负值表示错误
 */
int efw_debug_register_efw_state_machines(void);

/**
 * @brief 注册所有 EFW 框架数据
 *
 * 等效于依次调用：
 *   efw_debug_register_efw_hal();
 *   efw_debug_register_efw_sensors();
 *   efw_debug_register_efw_algorithms();
 *   efw_debug_register_efw_state_machines();
 *
 * 其中传感器需要应用通过 efw_debug_register_sensor_value() 显式描述
 * 最新值类型和地址。
 *
 * @return 总共注册的监控点数量，负值表示错误
 */
int efw_debug_register_all_efw(void);

/* ==================================================================
 *  自定义监控点注册 API
 * ================================================================== */

/**
 * @brief 注册自定义监控点
 *
 * 将用户定义的变量注册为监控点，Host 端可通过快照导出或 LiteTune
 * 集成层读取。
 *
 * @param name      监控点名称（全局唯一）
 * @param type      数据类型
 * @param value_ptr 指向实际数据的指针（必须保持有效直到调试模块反初始化）
 * @return EFW_OK 成功，其他值表示失败
 */
efw_status_t efw_debug_register_custom(const char *name, efw_debug_type_t type, const void *value_ptr);

/**
 * @brief 批量注册自定义监控点
 *
 * @param points    监控点数组
 * @param count     数组元素数量
 * @return 成功注册的数量，负值表示错误
 */
int efw_debug_register_custom_batch(const efw_debug_point_t *points, uint16_t count);

/**
 * @brief 注销监控点
 *
 * @param name 监控点名称
 * @return EFW_OK 成功，其他值表示失败
 */
efw_status_t efw_debug_unregister(const char *name);

/**
 * @brief 查找监控点
 *
 * @param name      监控点名称
 * @param out_point 输出监控点指针
 * @return EFW_OK 成功，其他值表示失败
 */
efw_status_t efw_debug_find(const char *name, const efw_debug_point_t **out_point);

/* ==================================================================
 *  便捷宏
 * ================================================================== */

/**
 * @brief 注册变量为监控点的便捷宏
 *
 * 用法：EFW_DEBUG_REGISTER_VAR("motor_speed", motor_speed_var);
 */
#define EFW_DEBUG_REGISTER_VAR(name, var) \
    efw_debug_register_custom(name, _Generic((var), \
        _Bool: EFW_DEBUG_TYPE_BOOL, \
        uint8_t: EFW_DEBUG_TYPE_U8, \
        int8_t: EFW_DEBUG_TYPE_I8, \
        uint16_t: EFW_DEBUG_TYPE_U16, \
        int16_t: EFW_DEBUG_TYPE_I16, \
        uint32_t: EFW_DEBUG_TYPE_U32, \
        int32_t: EFW_DEBUG_TYPE_I32, \
        float: EFW_DEBUG_TYPE_F32, \
        double: EFW_DEBUG_TYPE_F64, \
        default: EFW_DEBUG_TYPE_U32 \
    ), &(var))

#ifdef __cplusplus
}
#endif

#endif /* EFW_DEBUG_H */
