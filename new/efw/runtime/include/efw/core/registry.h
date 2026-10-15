#ifndef EFW_REGISTRY_H
#define EFW_REGISTRY_H
// 注册表工具，实际的注册内容根据不同角色单独实现

#include "efw/core/common.h"
#include <string.h>

/**
 * @brief 比较两个组件名称是否相同。
 *
 * 注册表只保存调用方提供的指针，不复制名称字符串，因此名称必须在
 * 组件仍注册期间保持有效。NULL 名称不会被视为相等。
 */
static inline bool efw_name_eq(const char *a, const char *b) {
    /* 快速路径：同一字面量指针 O(1) 命中；首字符不同直接否决。
     * 线性扫描 32 条目时省去绝大多数整串 strcmp 的调用开销。 */
    if (a == b) return 1;
    if (!a || !b || a[0] != b[0]) return 0;
    return strcmp(a, b) == 0;
}

/**
 * @brief 在“指针数组形式”的注册表中按名称查找对象。
 *
 * @param pool        对象指针数组；每个对象的第一个字段不一定是 name
 * @param count       当前有效元素数量，而不是数组容量
 * @param name        待查找名称
 * @param name_offset name 字段相对于对象首地址的字节偏移
 * @param out_ptr     实际类型为“对象指针输出变量”的地址
 *
 * 这是给内部注册表复用的偏移访问辅助函数。它假定 pool 中的每个元素
 * 都是有效对象，并且 name_offset 指向一个 const char * 字段；公共层的
 * 各注册表通常直接实现查找，以便保留更清晰的类型信息。
 */
static inline efw_status_t efw_registry_find_by_name(const void *const *pool, size_t count,
                                                      const char *name, size_t name_offset,
                                                      void *out_ptr) {
    if (!name || !out_ptr) return EFW_ERR_INVALID;
    const char **out = (const char **)out_ptr;
    for (size_t i = 0; i < count; ++i) {
        const char *entry_name = *(const char *const *)((const char *)pool[i] + name_offset);
        if (efw_name_eq(entry_name, name)) {
            *out = (const char *)pool[i];
            return EFW_OK;
        }
    }
    return EFW_ERR_NOT_FOUND;
}

/**
 * @brief 检查名称是否已存在。
 *
 * 返回 EFW_OK 表示可以继续注册，返回 EFW_ERR_ALREADY_EXISTS 表示名称
 * 冲突。该函数不检查 name 是否为 NULL，调用方应先完成对象参数校验。
 */
static inline efw_status_t efw_registry_check_duplicate(const void *const *pool, size_t count,
                                                          const char *name, size_t name_offset) {
    for (size_t i = 0; i < count; ++i) {
        const char *entry_name = *(const char *const *)((const char *)pool[i] + name_offset);
        if (efw_name_eq(entry_name, name)) return EFW_ERR_ALREADY_EXISTS;
    }
    return EFW_OK;
}

#endif
