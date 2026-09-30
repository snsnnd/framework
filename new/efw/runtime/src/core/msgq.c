#include "efw/core/msgq.h"
#include <string.h>

efw_status_t efw_msgq_init(efw_msgq_t *q, void *storage, uint16_t item_size,
                           uint16_t capacity, efw_msgq_policy_t policy) {
    if (!q || !storage || item_size == 0u || capacity == 0u) return EFW_ERR_INVALID;
    memset(q, 0, sizeof(*q));
    q->storage = (uint8_t *)storage;
    q->item_size = item_size;
    q->capacity = capacity;
    q->policy = (uint8_t)policy;
    return EFW_OK;
}

efw_status_t efw_msgq_push(efw_msgq_t *q, const void *item) {
    uint16_t tail;
    efw_status_t result = EFW_OK;
    if (!q || !item || !q->storage) return EFW_ERR_INVALID;
    EFW_CRITICAL_ENTER();
    if (q->count == q->capacity) {
        q->dropped++;
        if (q->policy == EFW_MSGQ_DROP_OLDEST) {
            q->head = (uint16_t)((q->head + 1u) % q->capacity);
            q->count--;
        } else {
            result = EFW_ERR_FULL;
        }
    }
    if (result == EFW_OK) {
        tail = (uint16_t)((q->head + q->count) % q->capacity);
        memcpy(q->storage + (size_t)tail * q->item_size, item, q->item_size);
        q->count++;
        q->pushed++;
        if (q->count > q->high_water) q->high_water = q->count;
    }
    EFW_CRITICAL_EXIT();
    return result;
}

efw_status_t efw_msgq_pop(efw_msgq_t *q, void *out) {
    efw_status_t result = EFW_OK;
    if (!q || !out || !q->storage) return EFW_ERR_INVALID;
    EFW_CRITICAL_ENTER();
    if (q->count == 0u) {
        result = EFW_ERR_NOT_FOUND; /* 空队列 */
    } else {
        memcpy(out, q->storage + (size_t)q->head * q->item_size, q->item_size);
        q->head = (uint16_t)((q->head + 1u) % q->capacity);
        q->count--;
        q->popped++;
    }
    EFW_CRITICAL_EXIT();
    return result;
}

uint16_t efw_msgq_count(const efw_msgq_t *q) {
    return q ? q->count : 0u;
}
