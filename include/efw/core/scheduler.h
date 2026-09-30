#ifndef EFW_SCHEDULER_H
#define EFW_SCHEDULER_H

#include "efw/core/common.h"

#ifndef EFW_MAX_SCHEDULER_TASKS
#define EFW_MAX_SCHEDULER_TASKS 16
#endif

typedef efw_status_t (*efw_task_fn_t)(void *ctx);

typedef struct {
    const char *name;
    uint32_t period_ms;
    efw_task_fn_t fn;
    void *ctx;
} efw_scheduler_task_def_t;

typedef struct {
    const efw_scheduler_task_def_t *def;
    uint32_t last_exec_ms;
    uint8_t active;
} efw_scheduler_slot_t;

efw_status_t efw_scheduler_init(void);
efw_status_t efw_scheduler_register(const efw_scheduler_task_def_t *task);
efw_status_t efw_scheduler_unregister(const char *name);
efw_status_t efw_scheduler_pause(const char *name);
efw_status_t efw_scheduler_resume(const char *name);
efw_status_t efw_scheduler_tick(uint32_t elapsed_ms);
uint32_t efw_scheduler_task_count(void);

#endif
