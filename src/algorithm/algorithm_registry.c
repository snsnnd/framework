#include <string.h>
#include "efw/core/config.h"
#include "efw/core/diagnostic.h"
#include "efw/core/registry.h"
#include "efw/algorithm/registry.h"

#if EFW_ENABLE_ALGORITHM

static const efw_algo_ops_t *g_algo_default_pool[EFW_MAX_ALGOS];
static const efw_algo_ops_t **g_algos = g_algo_default_pool;
static size_t g_algo_cap = EFW_MAX_ALGOS;
static size_t g_algo_n;

efw_status_t efw_algo_registry_init(void) { g_algos = g_algo_default_pool; g_algo_cap = EFW_MAX_ALGOS; g_algo_n = 0; return EFW_OK; }
efw_status_t efw_algo_registry_init_pool(const efw_algo_ops_t **pool, size_t capacity) {
    if (!pool || capacity == 0) { efw_diag_set(EFW_ERR_INVALID, "algo", 0, "invalid pool"); return EFW_ERR_INVALID; }
    g_algos = pool; g_algo_cap = capacity; g_algo_n = 0; return EFW_OK;
}

efw_status_t efw_algo_register(const efw_algo_ops_t *ops) {
    if (!ops || !ops->name || !ops->run) { efw_diag_set(EFW_ERR_INVALID, "algo", 0, "invalid ops"); return EFW_ERR_INVALID; }
    for (size_t i = 0; i < g_algo_n; ++i)
        if (efw_name_eq(g_algos[i]->name, ops->name))
            { efw_diag_set(EFW_ERR_ALREADY_EXISTS, "algo", ops->name, "duplicate name"); return EFW_ERR_ALREADY_EXISTS; }
    if (g_algo_n >= g_algo_cap) { efw_diag_set(EFW_ERR_FULL, "algo", ops->name, "pool full"); return EFW_ERR_FULL; }
    g_algos[g_algo_n++] = ops;
    return EFW_OK;
}

efw_status_t efw_algo_get(const char *name, const efw_algo_ops_t **out_ops) {
    if (!name || !out_ops) return EFW_ERR_INVALID;
    for (size_t i = 0; i < g_algo_n; ++i)
        if (efw_name_eq(g_algos[i]->name, name)) {
            *out_ops = g_algos[i];
            return EFW_OK;
        }
    return EFW_ERR_NOT_FOUND;
}

efw_status_t efw_algo_unregister(const char *name) {
    for (size_t i = 0; i < g_algo_n; ++i) {
        if (efw_name_eq(g_algos[i]->name, name)) {
            g_algos[i] = g_algos[--g_algo_n];
            return EFW_OK;
        }
    }
    return EFW_ERR_NOT_FOUND;
}

size_t efw_algo_count(void) { return g_algo_n; }

efw_status_t efw_algo_run(const char *name, const void *in, uint16_t in_size, void *out, uint16_t out_size) {
    const efw_algo_ops_t *ops;
    efw_status_t s = efw_algo_get(name, &ops);
    if (s != EFW_OK) return s;
    return ops->run(ops->ctx, in, in_size, out, out_size);
}

#endif
