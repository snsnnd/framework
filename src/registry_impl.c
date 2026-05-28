#include <string.h>
#include "efw/sensor_registry.h"
#include "efw/algorithm_registry.h"
#include "efw/state_machine_registry.h"

#define EFW_MAX_SENSORS 32
#define EFW_MAX_ALGOS 32
#define EFW_MAX_SMS 16

static const efw_sensor_ops_t *g_sensors[EFW_MAX_SENSORS];
static size_t g_sensor_n;

static const efw_algo_ops_t *g_algos[EFW_MAX_ALGOS];
static size_t g_algo_n;

static const efw_state_machine_ops_t *g_sms[EFW_MAX_SMS];
static size_t g_sm_n;

static int same_name(const char *a, const char *b) {
    return a && b && strcmp(a, b) == 0;
}

efw_status_t efw_sensor_registry_init(void) { g_sensor_n = 0; return EFW_OK; }
efw_status_t efw_algo_registry_init(void) { g_algo_n = 0; return EFW_OK; }
efw_status_t efw_sm_registry_init(void) { g_sm_n = 0; return EFW_OK; }

efw_status_t efw_sensor_register(const efw_sensor_ops_t *ops) {
    if (!ops || !ops->name || !ops->read) return EFW_ERR_INVALID;
    for (size_t i = 0; i < g_sensor_n; ++i) if (same_name(g_sensors[i]->name, ops->name)) return EFW_ERR_ALREADY_EXISTS;
    if (g_sensor_n >= EFW_MAX_SENSORS) return EFW_ERR_FULL;
    g_sensors[g_sensor_n++] = ops;
    return EFW_OK;
}

efw_status_t efw_algo_register(const efw_algo_ops_t *ops) {
    if (!ops || !ops->name || !ops->run) return EFW_ERR_INVALID;
    for (size_t i = 0; i < g_algo_n; ++i) if (same_name(g_algos[i]->name, ops->name)) return EFW_ERR_ALREADY_EXISTS;
    if (g_algo_n >= EFW_MAX_ALGOS) return EFW_ERR_FULL;
    g_algos[g_algo_n++] = ops;
    return EFW_OK;
}

efw_status_t efw_sm_register(const efw_state_machine_ops_t *ops) {
    if (!ops || !ops->name || !ops->on_tick) return EFW_ERR_INVALID;
    for (size_t i = 0; i < g_sm_n; ++i) if (same_name(g_sms[i]->name, ops->name)) return EFW_ERR_ALREADY_EXISTS;
    if (g_sm_n >= EFW_MAX_SMS) return EFW_ERR_FULL;
    g_sms[g_sm_n++] = ops;
    return EFW_OK;
}

efw_status_t efw_sensor_get(const char *name, const efw_sensor_ops_t **out_ops) {
    if (!name || !out_ops) return EFW_ERR_INVALID;
    for (size_t i = 0; i < g_sensor_n; ++i) if (same_name(g_sensors[i]->name, name)) { *out_ops = g_sensors[i]; return EFW_OK; }
    return EFW_ERR_NOT_FOUND;
}

efw_status_t efw_algo_get(const char *name, const efw_algo_ops_t **out_ops) {
    if (!name || !out_ops) return EFW_ERR_INVALID;
    for (size_t i = 0; i < g_algo_n; ++i) if (same_name(g_algos[i]->name, name)) { *out_ops = g_algos[i]; return EFW_OK; }
    return EFW_ERR_NOT_FOUND;
}

efw_status_t efw_sm_get(const char *name, const efw_state_machine_ops_t **out_ops) {
    if (!name || !out_ops) return EFW_ERR_INVALID;
    for (size_t i = 0; i < g_sm_n; ++i) if (same_name(g_sms[i]->name, name)) { *out_ops = g_sms[i]; return EFW_OK; }
    return EFW_ERR_NOT_FOUND;
}

size_t efw_sensor_count_by_type(efw_sensor_type_t type) {
    size_t n = 0;
    for (size_t i = 0; i < g_sensor_n; ++i) {
        if (g_sensors[i]->type == type) ++n;
    }
    return n;
}
