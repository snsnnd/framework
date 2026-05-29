/**
 * @file    diagnostic.c
 * @brief   诊断系统实现 —— 全局"最后一次错误"记录
 *
 * 本文件只有一个静态全局变量 g_last_error 和三个函数。
 * 由于使用静态全局变量，诊断系统本身是单实例的——整个程序只有一个错误槽位。
 *
 * =========================================================================
 * 实现细节
 * =========================================================================
 *
 *   g_last_error 是 static 变量，仅本文件可见。
 *   线程安全：裸机/单线程环境下天然安全。RTOS 多任务环境需外部加锁。
 *
 *   efw_diag_set 直接覆盖上一次错误——不做历史记录。
 *   如果需要追踪多次错误，在上层用 efw_diag_last_error() 读取后自行保存。
 */

#include "efw/core/diagnostic.h"

/** @brief 全局最后一次错误记录 (static，仅本文件可见) */
static efw_error_t g_last_error;

/**
 * @brief 清除诊断状态
 *
 * code=EFW_OK, module=NULL, name=NULL, message=NULL
 * 代表"没有错误"的初始状态。
 */
void efw_diag_clear(void) {
    g_last_error.code = EFW_OK;         /* 状态码 = 成功 (无错误) */
    g_last_error.module = 0;            /* 模块名 = NULL (不指向任何模块) */
    g_last_error.name = 0;              /* 组件名 = NULL */
    g_last_error.message = 0;           /* 错误描述 = NULL */
}

/**
 * @brief 设置诊断错误
 *
 * 所有字段直接赋值为传入的指针/值。module/name/message 应指向字符串字面量
 * 或静态缓冲区——本函数不做拷贝，只保存指针。
 *
 * @param code    错误码 (来自 API 返回值)
 * @param module  模块标识字符串 (如 "sensor")
 * @param name    组件名 (如 "line5")，无名称传 NULL
 * @param message 错误描述 (如 "pool full")
 */
void efw_diag_set(efw_status_t code, const char *module, const char *name, const char *message) {
    g_last_error.code = code;           /* 错误码 */
    g_last_error.module = module;       /* 模块名 (字符串字面量指针) */
    g_last_error.name = name;           /* 组件名 (字符串字面量指针) */
    g_last_error.message = message;     /* 错误描述 (字符串字面量指针) */
}

/**
 * @brief 获取最后一次错误
 *
 * 返回指向静态 g_last_error 的指针。指针生命周期 = 整个程序运行期。
 * 调用方不应释放此指针，也不应修改其内容。
 *
 * @return 始终有效的 efw_error_t 指针 (不会返回 NULL)
 */
const efw_error_t *efw_diag_last_error(void) {
    return &g_last_error;               /* 返回静态变量的地址 */
}
