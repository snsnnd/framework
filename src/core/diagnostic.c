#include "efw/core/diagnostic.h" // 诊断模块
#include "efw/core/config.h"

static efw_error_t g_last_error;
static efw_error_t g_error_history[EFW_ERROR_HISTORY_SIZE];
static uint8_t g_history_idx;
static uint32_t g_error_count;
static efw_diag_hook_fn g_diag_hook;

/* 诊断信息只保存指针，不复制文本，因此适合使用字符串常量。 */
void efw_diag_clear(void) {
    g_last_error.code = EFW_OK;
    g_last_error.module = 0;
    g_last_error.name = 0;
    g_last_error.message = 0;
    g_history_idx = 0;
    g_error_count = 0;
    for (uint8_t i = 0; i < EFW_ERROR_HISTORY_SIZE; ++i) {
        g_error_history[i].code = EFW_OK;
        g_error_history[i].module = 0;
        g_error_history[i].name = 0;
        g_error_history[i].message = 0;
    }
}

/**
 * @brief 设置诊断错误信息，更新最新错误与环形错误历史
 * @param code 错误状态码
 * @param module 所属模块名字符串(必须为静态/常量字符串)
 * @param name 出错对象名称(必须为静态/常量字符串)
 * @param message 错误描述文本(必须为静态/常量字符串)
 * @note 本函数仅保存指针，不拷贝字符串；禁止传入栈临时字符串
 */
void efw_diag_set(efw_status_t code, const char* module, const char* name, const char* message) {
    /* 当前错误单独保存，历史槽位按环形顺序覆盖；两者共享同一条值语义。 */
    // 更新全局“最后一次错误”
    g_last_error.code = code;
    g_last_error.module = module;
    g_last_error.name = name;
    g_last_error.message = message;

    // 将本次错误存入环形历史缓冲区的当前位置
    g_error_history[g_history_idx] = g_last_error;
    // 环形索引步进，达到缓冲区大小后绕回0，旧记录被新记录覆盖
    g_history_idx = (uint8_t)((g_history_idx + 1u) % EFW_ERROR_HISTORY_SIZE);
    // 全局错误发生总计数
    g_error_count++;

    /* 统一观察点：应用可在此断言/点灯/上报。禁止在钩子里再写诊断（递归）。 */
    if (g_diag_hook) g_diag_hook(&g_last_error);
}

void efw_diag_set_hook(efw_diag_hook_fn hook) {
    g_diag_hook = hook;
}


const efw_error_t *efw_diag_last_error(void) {
    return &g_last_error;
}

uint32_t efw_diag_error_count(void) {
    return g_error_count;
}

uint8_t efw_diag_history_size(void) {
    return EFW_ERROR_HISTORY_SIZE;
}

const efw_error_t *efw_diag_history_entry(uint8_t index) {
    if (index >= EFW_ERROR_HISTORY_SIZE) return 0;
    return &g_error_history[index];
}
