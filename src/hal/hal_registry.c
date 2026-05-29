/**
 * @file    hal_registry.c
 * @brief   HAL (硬件抽象层) 注册表实现
 *
 * 本文件实现 HAL 层的完整注册表：初始化、注册、查找、统计、便捷操作。
 * 由 EFW_ENABLE_HAL 宏控制编译。
 *
 * =========================================================================
 * 设计要点
 * =========================================================================
 *
 *   ① 静态指针数组 g_hals[EFW_MAX_HALS]——不依赖 malloc，内存可预测
 *   ② 名称字符串查找 (strcmp)——可读性 > 整数 ID，n≤16 线性扫描可接受
 *   ③ 便捷操作 = 查找 + 调用回调——efw_hal_read("adc1",...) 比先 get 再调用简洁
 *   ④ init 可空（有些 HAL 无需初始化），read/write/ioctl 不可空
 */

#include <string.h>
#include "efw/core/config.h"
#include "efw/core/diagnostic.h"
#include "efw/hal/hal.h"

#if EFW_ENABLE_HAL  /**< 编译开关：0 时整个文件被跳过 */

/** HAL 注册表——全局静态指针数组，每个元素指向用户分配的 efw_hal_ops_t */
static const efw_hal_ops_t *g_hal_default_pool[EFW_MAX_HALS];
static const efw_hal_ops_t **g_hals = g_hal_default_pool;
static size_t g_hal_cap = EFW_MAX_HALS;
static size_t g_hal_n;

/**
 * @brief 安全字符串比较：两串非空且内容相同 → 1，否则 → 0
 */
static int same_name(const char *a, const char *b) {
    return a && b && strcmp(a, b) == 0;
}

/* ====== 初始化：计数归零即清空 ====== */

efw_status_t efw_hal_registry_init(void) { g_hals = g_hal_default_pool; g_hal_cap = EFW_MAX_HALS; g_hal_n = 0; return EFW_OK; }
efw_status_t efw_hal_registry_init_pool(const efw_hal_ops_t **pool, size_t capacity) {
    if (!pool || capacity == 0) { efw_diag_set(EFW_ERR_INVALID, "hal", 0, "invalid pool"); return EFW_ERR_INVALID; }
    g_hals = pool; g_hal_cap = capacity; g_hal_n = 0; return EFW_OK;
}

/* ====== 注册：校验 → 查重 → 容量检查 → 存入 ====== */

efw_status_t efw_hal_register(const efw_hal_ops_t *ops) {
    if (!ops || !ops->name) { efw_diag_set(EFW_ERR_INVALID, "hal", 0, "invalid ops"); return EFW_ERR_INVALID; }
    for (size_t i = 0; i < g_hal_n; ++i)                     /* ② 名称冲突检查 */
        if (same_name(g_hals[i]->name, ops->name))
            { efw_diag_set(EFW_ERR_ALREADY_EXISTS, "hal", ops->name, "duplicate name"); return EFW_ERR_ALREADY_EXISTS; }
    if (g_hal_n >= g_hal_cap) { efw_diag_set(EFW_ERR_FULL, "hal", ops->name, "pool full"); return EFW_ERR_FULL; }
    g_hals[g_hal_n++] = ops;                                  /* ④ 存入数组尾部 */
    return EFW_OK;
}

/* ====== 查找：遍历 g_hals[]，strcmp 匹配，通过 out_ops 传出指针 ====== */

efw_status_t efw_hal_get(const char *name, const efw_hal_ops_t **out_ops) {
    if (!name || !out_ops) return EFW_ERR_INVALID;          /* 参数校验 */
    for (size_t i = 0; i < g_hal_n; ++i)
        if (same_name(g_hals[i]->name, name)) {
            *out_ops = g_hals[i];                            /* 找到 → 输出指针 */
            return EFW_OK;
        }
    return EFW_ERR_NOT_FOUND;                                /* 未找到 */
}

/* ====== 按类型统计 ====== */

size_t efw_hal_count_by_type(efw_hal_type_t type) {
    size_t n = 0;
    for (size_t i = 0; i < g_hal_n; ++i)
        if (g_hals[i]->type == type) ++n;
    return n;
}

/* ====== 便捷操作：查找 + 调用回调 ====== */

efw_status_t efw_hal_init_device(const char *name) {
    const efw_hal_ops_t *ops;
    efw_status_t s = efw_hal_get(name, &ops);
    if (s != EFW_OK) return s;
    return ops->init ? ops->init(ops->ctx) : EFW_OK;  /* init 可空 */
}

/**
 * @brief 通过 HAL 读取数据
 *
 * read 接收 buf(缓冲区)、len(期望)、actual(实际读取字节数，输出参数)。
 * actual 让调用方知道实际读了多少——对 UART/SPI 等流式接口很重要。
 */
efw_status_t efw_hal_read(const char *name, void *buf, uint16_t len, uint16_t *actual) {
    const efw_hal_ops_t *ops;
    efw_status_t s = efw_hal_get(name, &ops);
    if (s != EFW_OK) return s;
    if (!ops->read) return EFW_ERR_INVALID;  /* read 是核心功能，不能为空 */
    return ops->read(ops->ctx, buf, len, actual);
}

/**
 * @brief 通过 HAL 写入数据
 */
efw_status_t efw_hal_write(const char *name, const void *buf, uint16_t len, uint16_t *actual) {
    const efw_hal_ops_t *ops;
    efw_status_t s = efw_hal_get(name, &ops);
    if (s != EFW_OK) return s;
    if (!ops->write) return EFW_ERR_INVALID;
    return ops->write(ops->ctx, buf, len, actual);
}

/**
 * @brief 通过 HAL 执行 IO 控制命令
 *
 * cmd=命令码 (用户自定义)，arg=参数指针。
 * 万能控制接口——避免了为每个配置项（波特率、通道、模式）定义专用 API。
 */
efw_status_t efw_hal_ioctl(const char *name, uint32_t cmd, void *arg) {
    const efw_hal_ops_t *ops;
    efw_status_t s = efw_hal_get(name, &ops);
    if (s != EFW_OK) return s;
    if (!ops->ioctl) return EFW_ERR_INVALID;
    return ops->ioctl(ops->ctx, cmd, arg);
}

#endif /* EFW_ENABLE_HAL */
