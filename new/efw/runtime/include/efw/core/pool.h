/**
 * @file    pool.h
 * @brief   固定块内存池 —— 调用方提供存储，O(1) 分配/释放，零碎片
 *
 * 与 ds.h 同一哲学：不使用 malloc，存储由调用方静态提供。
 * 空闲链表内嵌在每个空闲块的前 2 字节里，因此不占用额外 RAM。
 *
 * 约束：
 *   - block_size ≥ 2（空闲链表需要 2 字节存“下一个空闲块索引”）
 *   - block_count ≤ 65534
 *   - 释放时校验指针范围与块对齐；不检测二次释放（省 RAM 的取舍）
 *   - 分配/释放均为 O(1)，无搜索
 *
 * 典型用途：游戏实体、消息对象、传感器帧缓冲等大小固定的对象复用。
 */

#ifndef EFW_POOL_H
#define EFW_POOL_H

#include "efw/core/common.h"
#include <string.h>

#ifdef __cplusplus
extern "C" {
#endif

#define EFW_POOL_NONE 0xFFFFu

typedef struct {
    uint8_t *buf;           /* 调用方提供的存储区 */
    uint16_t block_size;    /* 每块字节数（≥2） */
    uint16_t block_count;   /* 块数（≤65534） */
    uint16_t free_head;     /* 空闲链表头索引 */
    uint16_t free_count;    /* 当前空闲块数 */
} efw_pool_t;

/** @brief 初始化池；会构建空闲链表（清空 buf 前若干字节）。 */
static inline efw_status_t efw_pool_init(efw_pool_t *pool, void *buf,
                                         uint16_t block_size, uint16_t block_count) {
    if (!pool || !buf || block_size < 2u || block_count == 0u ||
        block_count == EFW_POOL_NONE) {
        return EFW_ERR_INVALID;
    }
    pool->buf = (uint8_t *)buf;
    pool->block_size = block_size;
    pool->block_count = block_count;
    /* 空闲链表：块 i 的前 2 字节存“下一个空闲块索引”，尾块指向 NONE */
    for (uint16_t i = 0; i < block_count; ++i) {
        uint16_t next = (uint16_t)((i + 1u < block_count) ? (i + 1u) : EFW_POOL_NONE);
        memcpy(pool->buf + (uint32_t)i * block_size, &next, sizeof(next));
    }
    pool->free_head = 0u;
    pool->free_count = block_count;
    return EFW_OK;
}

/** @brief 分配一块；池空时返回 NULL。O(1)。 */
static inline void *efw_pool_alloc(efw_pool_t *pool) {
    if (!pool || pool->free_head == EFW_POOL_NONE) return 0;
    uint16_t idx = pool->free_head;
    uint8_t *p = pool->buf + (uint32_t)idx * pool->block_size;
    uint16_t next;
    memcpy(&next, p, sizeof(next));
    pool->free_head = next;
    pool->free_count--;
    return p;
}

/**
 * @brief 释放一块（归还空闲链表头）。O(1)。
 * 校验指针落在池内且按块对齐；不检测二次释放。
 */
static inline efw_status_t efw_pool_free(efw_pool_t *pool, void *ptr) {
    if (!pool || !ptr) return EFW_ERR_INVALID;
    uint32_t off = (uint32_t)((uint8_t *)ptr - pool->buf);
    if (off >= (uint32_t)pool->block_size * pool->block_count) return EFW_ERR_RANGE;
    if (off % pool->block_size) return EFW_ERR_RANGE;
    uint16_t idx = (uint16_t)(off / pool->block_size);
    memcpy(pool->buf + (uint32_t)idx * pool->block_size, &pool->free_head, sizeof(pool->free_head));
    pool->free_head = idx;
    pool->free_count++;
    return EFW_OK;
}

/** @brief 当前空闲块数。 */
static inline uint16_t efw_pool_free_count(const efw_pool_t *pool) {
    return pool ? pool->free_count : 0u;
}

#ifdef __cplusplus
}
#endif

#endif
