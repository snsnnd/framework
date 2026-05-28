/**
 * @file    comm_registry.c
 * @brief   COMM (通信抽象层) 注册表实现
 *
 * 本文件由 EFW_ENABLE_COMM 宏控制编译。
 *
 * =========================================================================
 * HAL vs COMM 的职责划分
 * =========================================================================
 *
 *   HAL  : 怎么发一个字节 (寄存器操作、移位、等标志位)
 *   COMM : 怎么组织一次通信 (帧格式、地址、校验、超时、重传)
 *
 *   例：UART
 *     HAL  = 配置 115200-8N1，HAL_UART_Transmit(&huart2, &byte, 1, 100)
 *     COMM = 封装帧 [0xAA][LEN][PAYLOAD][CRC16]，处理分包/粘包/超时
 *
 * =========================================================================
 * ★ 注册时 HAL 绑定校验 (重要安全机制)
 * =========================================================================
 *
 *   COMM 注册时若指定 hal_name，框架立即在 HAL 表中查找。
 *   HAL 不存在 → 返回 EFW_ERR_NOT_FOUND，拒绝注册。
 *   这确保了运行时不会有 "引用了不存在的 HAL" 的隐蔽 bug。
 *
 *   若 EFW_ENABLE_HAL=0 (HAL 被完全禁用)：
 *     COMM 仍试图绑定 hal_name → 返回 EFW_ERR_INVALID
 *     因为没有 HAL 就没有物理层，绑定无意义。
 */

#include <string.h>
#include "efw/core/config.h"
#include "efw/comm/comm.h"

#if EFW_ENABLE_COMM  /**< 编译开关：0 时整个文件被跳过 */

/** COMM 注册表——全局静态指针数组 */
static const efw_comm_ops_t *g_comms[EFW_MAX_COMMS]; /**< COMM ops 指针数组 */
static size_t g_comm_n;                              /**< 已注册 COMM 数量 */

static int same_name(const char *a, const char *b) {
    return a && b && strcmp(a, b) == 0;
}

/* ====== 初始化 ====== */

efw_status_t efw_comm_registry_init(void) { g_comm_n = 0; return EFW_OK; }

/* ====== 注册 (含 HAL 绑定校验) ====== */

efw_status_t efw_comm_register(const efw_comm_ops_t *ops) {
    if (!ops || !ops->name || !ops->send || !ops->recv) return EFW_ERR_INVALID;

    /* ★ 注册时 HAL 绑定校验 */
    if (ops->hal_name) {
#if EFW_ENABLE_HAL
        const efw_hal_ops_t *hal;
        efw_status_t s = efw_hal_get(ops->hal_name, &hal);  /* 在 HAL 表中查找 */
        if (s != EFW_OK) return s;                           /* 找不到 → 拒绝注册 */
#else
        return EFW_ERR_INVALID;  /* HAL 禁用，无法绑定 */
#endif
    }

    for (size_t i = 0; i < g_comm_n; ++i)
        if (same_name(g_comms[i]->name, ops->name))
            return EFW_ERR_ALREADY_EXISTS;                    /* 名称冲突 */
    if (g_comm_n >= EFW_MAX_COMMS) return EFW_ERR_FULL;     /* 容量已满 */
    g_comms[g_comm_n++] = ops;                                /* 存入 */
    return EFW_OK;
}

/* ====== 查找 + 统计 ====== */

efw_status_t efw_comm_get(const char *name, const efw_comm_ops_t **out_ops) {
    if (!name || !out_ops) return EFW_ERR_INVALID;
    for (size_t i = 0; i < g_comm_n; ++i)
        if (same_name(g_comms[i]->name, name)) {
            *out_ops = g_comms[i];
            return EFW_OK;
        }
    return EFW_ERR_NOT_FOUND;
}

size_t efw_comm_count_by_type(efw_comm_type_t type) {
    size_t n = 0;
    for (size_t i = 0; i < g_comm_n; ++i)
        if (g_comms[i]->type == type) ++n;
    return n;
}

/* ====== HAL 绑定查询：查 COMM→查 hal_name→查 HAL ====== */

efw_status_t efw_comm_bind_hal(const char *comm_name, const efw_hal_ops_t **out_hal) {
#if EFW_ENABLE_HAL
    const efw_comm_ops_t *comm;
    efw_status_t s = efw_comm_get(comm_name, &comm);  /* 找到 COMM */
    if (s != EFW_OK) return s;
    if (!comm->hal_name) return EFW_ERR_NOT_FOUND;     /* 该 COMM 无 HAL 绑定 */
    return efw_hal_get(comm->hal_name, out_hal);       /* 通过 hal_name 查 HAL */
#else
    EFW_UNUSED(comm_name);
    EFW_UNUSED(out_hal);
    return EFW_ERR_INVALID;  /* HAL 禁用，无 HAL 可查 */
#endif
}

/* ====== 便捷操作 ====== */

efw_status_t efw_comm_open(const char *name) {
    const efw_comm_ops_t *ops;
    efw_status_t s = efw_comm_get(name, &ops);
    if (s != EFW_OK) return s;
    return ops->open ? ops->open(ops->ctx) : EFW_OK;  /* open 可空 */
}

efw_status_t efw_comm_close(const char *name) {
    const efw_comm_ops_t *ops;
    efw_status_t s = efw_comm_get(name, &ops);
    if (s != EFW_OK) return s;
    return ops->close ? ops->close(ops->ctx) : EFW_OK;  /* close 可空 */
}

/**
 * @brief 发送数据——send 必填 (注册时已校验)
 * actual 输出参数告知实际发送字节数；非阻塞模式下 len > actual 是正常的。
 */
efw_status_t efw_comm_send(const char *name, const uint8_t *data, uint16_t len, uint16_t *actual) {
    const efw_comm_ops_t *ops;
    efw_status_t s = efw_comm_get(name, &ops);
    if (s != EFW_OK) return s;
    return ops->send(ops->ctx, data, len, actual);
}

/**
 * @brief 接收数据——recv 必填 (注册时已校验)
 */
efw_status_t efw_comm_recv(const char *name, uint8_t *data, uint16_t len, uint16_t *actual) {
    const efw_comm_ops_t *ops;
    efw_status_t s = efw_comm_get(name, &ops);
    if (s != EFW_OK) return s;
    return ops->recv(ops->ctx, data, len, actual);
}

#endif /* EFW_ENABLE_COMM */
