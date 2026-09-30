#include "efw/core/scheduler.h"
#include <assert.h>
#include <stdint.h>

static unsigned calls;
static efw_status_t run(void *ctx) { (void)ctx; ++calls; return EFW_OK; }

int main(void) {
    const efw_scheduler_slot_t *slot;
    const efw_scheduler_task_def_t task = { "ten_ms", 10u, run, 0 };
    assert(efw_scheduler_init() == EFW_OK);
    assert(efw_scheduler_register(&task) == EFW_OK);
    for (uint32_t now = 1; now <= 100; ++now) assert(efw_scheduler_tick(now) == EFW_OK);
    assert(calls == 10);
    assert(efw_scheduler_tick(145u) == EFW_OK);
    assert(calls == 11);
    assert(efw_scheduler_get("ten_ms", &slot) == EFW_OK);
    assert(slot->missed_releases == 3);
    assert(slot->next_release_ms == 150u);
    assert(efw_scheduler_init() == EFW_OK);
    calls = 0;
    assert(efw_scheduler_register_at(&task, UINT32_MAX - 4u) == EFW_OK);
    assert(efw_scheduler_tick(UINT32_MAX - 5u) == EFW_OK);
    assert(calls == 0);
    assert(efw_scheduler_tick(UINT32_MAX - 4u) == EFW_OK);
    assert(calls == 1);
    assert(efw_scheduler_tick(5u) == EFW_OK);
    assert(calls == 2);
    return 0;
}
