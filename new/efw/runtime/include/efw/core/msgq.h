#ifndef EFW_MSGQ_H
#define EFW_MSGQ_H
/**
 * 静态消息队列：固定条目大小、固定容量、无 malloc。
 *
 * 并发约定：单生产者（可为中断）+ 单消费者（主循环）。
 * 在 MCU 上把 EFW_CRITICAL_ENTER/EXIT 定义为开/关中断即可从 ISR 中 push。
 */
#include "efw/core/common.h"

#ifndef EFW_CRITICAL_ENTER
#define EFW_CRITICAL_ENTER() ((void)0)
#endif
#ifndef EFW_CRITICAL_EXIT
#define EFW_CRITICAL_EXIT() ((void)0)
#endif

typedef enum {
    EFW_MSGQ_DROP_NEWEST = 0, /* 满时拒绝新条目，push 返回 EFW_ERR_FULL */
    EFW_MSGQ_DROP_OLDEST = 1  /* 满时丢弃最旧条目，push 仍成功 */
} efw_msgq_policy_t;

typedef struct {
    uint8_t *storage;
    uint16_t item_size;
    uint16_t capacity;
    uint16_t head;   /* 下一个 pop 位置 */
    uint16_t count;
    uint8_t policy;
    uint32_t pushed;   /* 成功入队（含因 drop_oldest 顶掉旧条目的入队） */
    uint32_t popped;
    uint32_t dropped;  /* 被丢弃的条目数（两种策略都计） */
    uint16_t high_water;
} efw_msgq_t;

efw_status_t efw_msgq_init(efw_msgq_t *q, void *storage, uint16_t item_size,
                           uint16_t capacity, efw_msgq_policy_t policy);
efw_status_t efw_msgq_push(efw_msgq_t *q, const void *item);
efw_status_t efw_msgq_pop(efw_msgq_t *q, void *out);
uint16_t efw_msgq_count(const efw_msgq_t *q);

#endif
