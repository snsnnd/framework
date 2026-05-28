#include <string.h>
#include "efw/core/config.h"
#include "efw/efw.h"
#include "efw/module/module.h"
#include "efw/device/sensor.h"
#include "efw/algorithm/registry.h"
#include "efw/state/state_machine.h"

static const efw_sensor_ops_t *g_sensors[EFW_MAX_SENSORS];
static size_t g_sensor_n;

static const efw_module_ops_t *g_modules[EFW_MAX_MODULES];
static size_t g_module_n;

static const efw_algo_ops_t *g_algos[EFW_MAX_ALGOS];
static size_t g_algo_n;

static const efw_state_machine_ops_t *g_sms[EFW_MAX_STATE_MACHINES];
static size_t g_sm_n;

static int same_name(const char *a, const char *b) {
    return a && b && strcmp(a, b) == 0;
}

efw_status_t efw_sensor_registry_init(void) { g_sensor_n = 0; return EFW_OK; }
efw_status_t efw_module_registry_init(void) { g_module_n = 0; return EFW_OK; }
efw_status_t efw_algo_registry_init(void) { g_algo_n = 0; return EFW_OK; }
efw_status_t efw_sm_registry_init(void) { g_sm_n = 0; return EFW_OK; }

efw_status_t efw_init(void) {
    efw_status_t s;
    s = efw_hal_registry_init(); if (s != EFW_OK) return s;
    s = efw_comm_registry_init(); if (s != EFW_OK) return s;
    s = efw_module_registry_init(); if (s != EFW_OK) return s;
    s = efw_sensor_registry_init(); if (s != EFW_OK) return s;
    s = efw_algo_registry_init(); if (s != EFW_OK) return s;
    return efw_sm_registry_init();
}

efw_status_t efw_module_register(const efw_module_ops_t *ops) {
    if (!ops || !ops->name) return EFW_ERR_INVALID;
    for (size_t i = 0; i < g_module_n; ++i) if (same_name(g_modules[i]->name, ops->name)) return EFW_ERR_ALREADY_EXISTS;
    if (g_module_n >= EFW_MAX_MODULES) return EFW_ERR_FULL;
    g_modules[g_module_n++] = ops;
    return EFW_OK;
}

efw_status_t efw_sensor_register(const efw_sensor_ops_t *ops) {
    if (!ops || !ops->name || !ops->read) return EFW_ERR_INVALID;
    if (ops->hal_name) {
        const efw_hal_ops_t *hal;
        efw_status_t s = efw_hal_get(ops->hal_name, &hal);
        if (s != EFW_OK) return s;
    }
    if (ops->comm_name) {
        const efw_comm_ops_t *comm;
        efw_status_t s = efw_comm_get(ops->comm_name, &comm);
        if (s != EFW_OK) return s;
    }
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
    if (g_sm_n >= EFW_MAX_STATE_MACHINES) return EFW_ERR_FULL;
    g_sms[g_sm_n++] = ops;
    return EFW_OK;
}

efw_status_t efw_module_get(const char *name, const efw_module_ops_t **out_ops) {
    if (!name || !out_ops) return EFW_ERR_INVALID;
    for (size_t i = 0; i < g_module_n; ++i) if (same_name(g_modules[i]->name, name)) { *out_ops = g_modules[i]; return EFW_OK; }
    return EFW_ERR_NOT_FOUND;
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

efw_status_t efw_algo_run(const char *name, const void *in, void *out) {
    const efw_algo_ops_t *ops;
    efw_status_t s = efw_algo_get(name, &ops);
    if (s != EFW_OK) return s;
    return ops->run(ops->ctx, in, out);
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

efw_status_t efw_sensor_bind_hal(const char *sensor_name, const efw_hal_ops_t **out_hal) {
    const efw_sensor_ops_t *sensor;
    efw_status_t s = efw_sensor_get(sensor_name, &sensor);
    if (s != EFW_OK) return s;
    if (!sensor->hal_name) return EFW_ERR_NOT_FOUND;
    return efw_hal_get(sensor->hal_name, out_hal);
}

efw_status_t efw_sensor_bind_comm(const char *sensor_name, const efw_comm_ops_t **out_comm) {
    const efw_sensor_ops_t *sensor;
    efw_status_t s = efw_sensor_get(sensor_name, &sensor);
    if (s != EFW_OK) return s;
    if (!sensor->comm_name) return EFW_ERR_NOT_FOUND;
    return efw_comm_get(sensor->comm_name, out_comm);
}

efw_status_t efw_sensor_init_device(const char *name) {
    const efw_sensor_ops_t *ops;
    efw_status_t s = efw_sensor_get(name, &ops);
    if (s != EFW_OK) return s;
    return ops->init ? ops->init(ops->ctx) : EFW_OK;
}

efw_status_t efw_sensor_read(const char *name, void *out) {
    const efw_sensor_ops_t *ops;
    efw_status_t s = efw_sensor_get(name, &ops);
    if (s != EFW_OK) return s;
    return ops->read(ops->ctx, out);
}

static efw_status_t module_call(const efw_module_ops_t *ops, efw_status_t (*fn)(void *ctx)) {
    if (!fn) return EFW_OK;
    return fn(ops->ctx);
}

efw_status_t efw_module_init(const char *name) {
    const efw_module_ops_t *ops;
    efw_status_t s = efw_module_get(name, &ops);
    if (s != EFW_OK) return s;
    return module_call(ops, ops->init);
}

efw_status_t efw_module_start(const char *name) {
    const efw_module_ops_t *ops;
    efw_status_t s = efw_module_get(name, &ops);
    if (s != EFW_OK) return s;
    return module_call(ops, ops->start);
}

efw_status_t efw_module_stop(const char *name) {
    const efw_module_ops_t *ops;
    efw_status_t s = efw_module_get(name, &ops);
    if (s != EFW_OK) return s;
    return module_call(ops, ops->stop);
}

efw_status_t efw_module_poll(const char *name) {
    const efw_module_ops_t *ops;
    efw_status_t s = efw_module_get(name, &ops);
    if (s != EFW_OK) return s;
    return module_call(ops, ops->poll);
}

efw_status_t efw_module_init_all(void) {
    for (size_t i = 0; i < g_module_n; ++i) {
        efw_status_t s = module_call(g_modules[i], g_modules[i]->init);
        if (s != EFW_OK) return s;
    }
    return EFW_OK;
}

efw_status_t efw_module_start_all(void) {
    for (size_t i = 0; i < g_module_n; ++i) {
        efw_status_t s = module_call(g_modules[i], g_modules[i]->start);
        if (s != EFW_OK) return s;
    }
    return EFW_OK;
}

efw_status_t efw_module_poll_all(void) {
    for (size_t i = 0; i < g_module_n; ++i) {
        efw_status_t s = module_call(g_modules[i], g_modules[i]->poll);
        if (s != EFW_OK) return s;
    }
    return EFW_OK;
}

size_t efw_module_count_by_type(efw_module_type_t type) {
    size_t n = 0;
    for (size_t i = 0; i < g_module_n; ++i) if (g_modules[i]->type == type) ++n;
    return n;
}
