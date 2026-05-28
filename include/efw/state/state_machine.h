#ifndef EFW_STATE_MACHINE_REGISTRY_H
#define EFW_STATE_MACHINE_REGISTRY_H

#include "efw/core/common.h"

typedef struct {
    const char *name;
    void *ctx;
    efw_status_t (*on_enter)(void *ctx);
    efw_status_t (*on_tick)(void *ctx);
    efw_status_t (*on_exit)(void *ctx);
} efw_state_machine_ops_t;

efw_status_t efw_sm_registry_init(void);
efw_status_t efw_sm_register(const efw_state_machine_ops_t *ops);
efw_status_t efw_sm_get(const char *name, const efw_state_machine_ops_t **out_ops);

#endif
