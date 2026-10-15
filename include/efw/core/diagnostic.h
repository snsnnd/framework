#ifndef EFW_DIAGNOSTIC_H
#define EFW_DIAGNOSTIC_H

#include "efw/core/common.h"

#ifndef EFW_ERROR_HISTORY_SIZE
#define EFW_ERROR_HISTORY_SIZE 4
#endif

/**
 * @brief 一条诊断记录。
 *
 * module、name 和 message 都是借用的 const char *，诊断模块不会复制文本。
 * 因此建议传入字符串常量，或保证相关字符串在整个诊断记录有效期内存在。
 */
typedef struct {
    efw_status_t code;
    const char *module;
    const char *name;
    const char *message;
} efw_error_t;

/** @brief 清空最近错误、错误历史和累计错误计数。 */
void efw_diag_clear(void);

/**
 * @brief 写入一条错误诊断。
 *
 * 历史数组按环形方式覆盖最旧记录；last_error 始终指向本次写入的记录。
 */
void efw_diag_set(efw_status_t code, const char *module, const char *name, const char *message);

/** @brief 获取最近一次错误；尚无错误时其 code 为 EFW_OK。 */
const efw_error_t *efw_diag_last_error(void);

/** @brief 获取自清空以来累计写入的错误数量，可能大于历史容量。 */
uint32_t efw_diag_error_count(void);

/** @brief 获取历史数组的容量。 */
uint8_t efw_diag_history_size(void);

/**
 * @brief 按物理槽位读取历史记录。
 *
 * index 是底层环形数组下标，不是“距当前错误的相对序号”；超出容量返回
 * NULL。调用方不能修改返回的记录。
 */
const efw_error_t *efw_diag_history_entry(uint8_t index);

/**
 * @brief 诊断钩子：每写入一条错误时同步调用（在历史记录更新之后）。
 *
 * 典型用途：调试构建里断言/点灯/串口打印，让“返回错误码+写诊断”的模式
 * 拥有一个统一的观察点。钩子内禁止再调用 efw_diag_set（会递归）。
 */
typedef void (*efw_diag_hook_fn)(const efw_error_t *err);

/** @brief 设置/清除（传 NULL）诊断钩子；随时可调用。 */
void efw_diag_set_hook(efw_diag_hook_fn hook);

#endif
