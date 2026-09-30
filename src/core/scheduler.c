#include "efw/core/config.h"
#include "efw/core/scheduler.h"
#include "efw/core/diagnostic.h"
#include "efw/core/registry.h"

#if EFW_ENABLE_SCHEDULER

static efw_scheduler_slot_t g_slots[EFW_MAX_SCHEDULER_TASKS];
static size_t g_task_n;
static uint8_t g_initialized;

static efw_status_t validate_task(const efw_scheduler_task_def_t *task) {
    if (!task || !task->fn) return EFW_ERR_INVALID;
    if (task->period_ms == 0) return EFW_ERR_RANGE;
    return EFW_OK;
}

efw_status_t efw_scheduler_init(void) {
    g_task_n = 0;
    g_initialized = 1;
    for (size_t i = 0; i < EFW_MAX_SCHEDULER_TASKS; ++i) {
        g_slots[i].def = 0;
        g_slots[i].last_exec_ms = 0;
        g_slots[i].active = 0;
    }
    return EFW_OK;
}

efw_status_t efw_scheduler_register(const efw_scheduler_task_def_t *task) {
    efw_status_t s = validate_task(task);
    if (s != EFW_OK) return s;
    if (!g_initialized) {
        efw_scheduler_init();
    }
    for (size_t i = 0; i < g_task_n; ++i) {
        if (efw_name_eq(g_slots[i].def->name, task->name)) {
            efw_diag_set(EFW_ERR_ALREADY_EXISTS, "scheduler", task->name, "duplicate task name");
            return EFW_ERR_ALREADY_EXISTS;
        }
    }
    if (g_task_n >= EFW_MAX_SCHEDULER_TASKS) {
        efw_diag_set(EFW_ERR_FULL, "scheduler", task->name, "task pool full");
        return EFW_ERR_FULL;
    }
    g_slots[g_task_n].def = task;
    g_slots[g_task_n].last_exec_ms = 0;
    g_slots[g_task_n].active = 1;
    g_task_n++;
    return EFW_OK;
}

efw_status_t efw_scheduler_unregister(const char *name) {
    for (size_t i = 0; i < g_task_n; ++i) {
        if (efw_name_eq(g_slots[i].def->name, name)) {
            for (size_t j = i; j < g_task_n - 1; ++j) {
                g_slots[j] = g_slots[j + 1];
            }
            g_task_n--;
            return EFW_OK;
        }
    }
    return EFW_ERR_NOT_FOUND;
}

efw_status_t efw_scheduler_pause(const char *name) {
    for (size_t i = 0; i < g_task_n; ++i) {
        if (efw_name_eq(g_slots[i].def->name, name)) {
            g_slots[i].active = 0;
            return EFW_OK;
        }
    }
    return EFW_ERR_NOT_FOUND;
}

efw_status_t efw_scheduler_resume(const char *name) {
    for (size_t i = 0; i < g_task_n; ++i) {
        if (efw_name_eq(g_slots[i].def->name, name)) {
            g_slots[i].active = 1;
            g_slots[i].last_exec_ms = 0;
            return EFW_OK;
        }
    }
    return EFW_ERR_NOT_FOUND;
}

efw_status_t efw_scheduler_tick(uint32_t elapsed_ms) {
    if (!g_initialized) return EFW_ERR_NOT_READY;
    for (size_t i = 0; i < g_task_n; ++i) {
        efw_scheduler_slot_t *slot = &g_slots[i];
        if (!slot->active) continue;
        uint32_t delta = elapsed_ms - slot->last_exec_ms;
        if (delta >= slot->def->period_ms) {
            efw_status_t s = slot->def->fn(slot->def->ctx);
            slot->last_exec_ms = elapsed_ms;
            if (s != EFW_OK) {
                efw_diag_set(s, "scheduler", slot->def->name, "task failed");
                return s;
            }
        }
    }
    return EFW_OK;
}

uint32_t efw_scheduler_task_count(void) {
    return (uint32_t)g_task_n;
}

#endif
