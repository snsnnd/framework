#ifndef EFW_STATE_MACHINE_H
#define EFW_STATE_MACHINE_H

#include "efw/core/common.h"

#ifndef EFW_MAX_STATE_MACHINES
#define EFW_MAX_STATE_MACHINES 8
#endif

typedef struct {
    const char *name;
    void *ctx;
    efw_status_t (*on_enter)(void *ctx);
    efw_status_t (*on_tick)(void *ctx);
    efw_status_t (*on_exit)(void *ctx);
} efw_state_def_t;

typedef efw_state_def_t efw_state_machine_ops_t;

typedef struct {
    const efw_state_def_t *from;
    const efw_state_def_t *to;
    int (*condition)(void);
    efw_status_t (*action)(void);
    uint32_t timeout_ms;
    uint8_t priority;
} efw_sm_transition_t;

typedef struct {
    const char *name;
    const efw_state_def_t *current;
    const efw_sm_transition_t *transitions;
    uint8_t transition_count;
    uint32_t entered_ms;
    uint32_t elapsed_ms;
} efw_sm_context_t;

efw_status_t efw_sm_init(efw_sm_context_t *ctx, const char *name,
                          const efw_state_def_t *initial,
                          const efw_sm_transition_t *transitions, uint8_t count);
efw_status_t efw_sm_tick(efw_sm_context_t *ctx);
efw_status_t efw_sm_transition_to(efw_sm_context_t *ctx, const efw_state_def_t *target);
efw_status_t efw_sm_set_transitions(efw_sm_context_t *ctx, const efw_sm_transition_t *transitions, uint8_t count);
const char *efw_sm_current_state(const efw_sm_context_t *ctx);
const efw_state_def_t *efw_sm_current_def(const efw_sm_context_t *ctx);
uint32_t efw_sm_time_in_state(const efw_sm_context_t *ctx);
void efw_sm_set_elapsed(efw_sm_context_t *ctx, uint32_t elapsed_ms);

efw_status_t efw_sm_registry_init(void);
efw_status_t efw_sm_register(efw_sm_context_t *ctx);
efw_status_t efw_sm_get(const char *name, efw_sm_context_t **out_ctx);
efw_status_t efw_sm_unregister(const char *name);
size_t efw_sm_count(void);

#endif
