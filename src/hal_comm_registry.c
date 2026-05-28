#include <string.h>
#include "efw/hal_registry.h"
#include "efw/comm_registry.h"

#define EFW_MAX_HALS 32
#define EFW_MAX_COMMS 32

static const efw_hal_ops_t *g_hals[EFW_MAX_HALS];
static size_t g_hal_n;

static const efw_comm_ops_t *g_comms[EFW_MAX_COMMS];
static size_t g_comm_n;

static int same_name(const char *a, const char *b) {
    return a && b && strcmp(a, b) == 0;
}

efw_status_t efw_hal_registry_init(void) { g_hal_n = 0; return EFW_OK; }
efw_status_t efw_comm_registry_init(void) { g_comm_n = 0; return EFW_OK; }

efw_status_t efw_hal_register(const efw_hal_ops_t *ops) {
    if (!ops || !ops->name) return EFW_ERR_INVALID;
    for (size_t i = 0; i < g_hal_n; ++i) if (same_name(g_hals[i]->name, ops->name)) return EFW_ERR_ALREADY_EXISTS;
    if (g_hal_n >= EFW_MAX_HALS) return EFW_ERR_FULL;
    g_hals[g_hal_n++] = ops;
    return EFW_OK;
}

efw_status_t efw_comm_register(const efw_comm_ops_t *ops) {
    if (!ops || !ops->name || !ops->send || !ops->recv) return EFW_ERR_INVALID;
    for (size_t i = 0; i < g_comm_n; ++i) if (same_name(g_comms[i]->name, ops->name)) return EFW_ERR_ALREADY_EXISTS;
    if (g_comm_n >= EFW_MAX_COMMS) return EFW_ERR_FULL;
    g_comms[g_comm_n++] = ops;
    return EFW_OK;
}

efw_status_t efw_hal_get(const char *name, const efw_hal_ops_t **out_ops) {
    if (!name || !out_ops) return EFW_ERR_INVALID;
    for (size_t i = 0; i < g_hal_n; ++i) if (same_name(g_hals[i]->name, name)) { *out_ops = g_hals[i]; return EFW_OK; }
    return EFW_ERR_NOT_FOUND;
}

efw_status_t efw_comm_get(const char *name, const efw_comm_ops_t **out_ops) {
    if (!name || !out_ops) return EFW_ERR_INVALID;
    for (size_t i = 0; i < g_comm_n; ++i) if (same_name(g_comms[i]->name, name)) { *out_ops = g_comms[i]; return EFW_OK; }
    return EFW_ERR_NOT_FOUND;
}

size_t efw_hal_count_by_type(efw_hal_type_t type) {
    size_t n = 0;
    for (size_t i = 0; i < g_hal_n; ++i) if (g_hals[i]->type == type) ++n;
    return n;
}

size_t efw_comm_count_by_type(efw_comm_type_t type) {
    size_t n = 0;
    for (size_t i = 0; i < g_comm_n; ++i) if (g_comms[i]->type == type) ++n;
    return n;
}
