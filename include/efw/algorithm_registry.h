#ifndef EFW_ALGORITHM_REGISTRY_H
#define EFW_ALGORITHM_REGISTRY_H

#include "efw_common.h"

typedef enum {
    EFW_ALGO_CONTROL = 0,
    EFW_ALGO_FILTER,
    EFW_ALGO_MAPPING,
    EFW_ALGO_PLANNING
} efw_algo_type_t;

typedef struct {
    const char *name;
    efw_algo_type_t type;
    void *ctx;
    efw_status_t (*run)(void *ctx, const void *in, void *out);
} efw_algo_ops_t;

efw_status_t efw_algo_registry_init(void);
efw_status_t efw_algo_register(const efw_algo_ops_t *ops);
efw_status_t efw_algo_get(const char *name, const efw_algo_ops_t **out_ops);

#endif
