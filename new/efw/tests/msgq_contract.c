#include "efw/core/msgq.h"
#include <assert.h>

int main(void) {
    uint16_t store[3];
    uint16_t v, out;
    efw_msgq_t q;
    assert(efw_msgq_init(&q, store, sizeof(uint16_t), 3, EFW_MSGQ_DROP_NEWEST) == EFW_OK);
    assert(efw_msgq_init(0, store, 2, 3, EFW_MSGQ_DROP_NEWEST) == EFW_ERR_INVALID);
    assert(efw_msgq_pop(&q, &out) == EFW_ERR_NOT_FOUND);
    for (v = 1; v <= 3; ++v) assert(efw_msgq_push(&q, &v) == EFW_OK);
    v = 4;
    assert(efw_msgq_push(&q, &v) == EFW_ERR_FULL);
    assert(q.dropped == 1 && q.pushed == 3 && q.high_water == 3);
    for (v = 1; v <= 3; ++v) { assert(efw_msgq_pop(&q, &out) == EFW_OK); assert(out == v); }
    assert(q.count == 0 && q.popped == 3);

    /* 环绕 + drop_oldest */
    assert(efw_msgq_init(&q, store, sizeof(uint16_t), 3, EFW_MSGQ_DROP_OLDEST) == EFW_OK);
    for (v = 1; v <= 5; ++v) assert(efw_msgq_push(&q, &v) == EFW_OK);
    assert(q.dropped == 2 && q.pushed == 5 && q.count == 3);
    for (v = 3; v <= 5; ++v) { assert(efw_msgq_pop(&q, &out) == EFW_OK); assert(out == v); }
    v = 9; assert(efw_msgq_push(&q, &v) == EFW_OK);
    assert(efw_msgq_pop(&q, &out) == EFW_OK && out == 9);
    return 0;
}
