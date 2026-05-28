#include <string.h>
#include "efw/core/config.h"
#include "efw/hal/hal.h"
#include "efw/comm/comm.h"

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
    if (ops->hal_name) {
        const efw_hal_ops_t *hal;
        efw_status_t s = efw_hal_get(ops->hal_name, &hal);
        if (s != EFW_OK) return s;
    }
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

efw_status_t efw_hal_init_device(const char *name) {
    const efw_hal_ops_t *ops;
    efw_status_t s = efw_hal_get(name, &ops);
    if (s != EFW_OK) return s;
    return ops->init ? ops->init(ops->ctx) : EFW_OK;
}

efw_status_t efw_hal_read(const char *name, void *buf, uint16_t len, uint16_t *actual) {
    const efw_hal_ops_t *ops;
    efw_status_t s = efw_hal_get(name, &ops);
    if (s != EFW_OK) return s;
    if (!ops->read) return EFW_ERR_INVALID;
    return ops->read(ops->ctx, buf, len, actual);
}

efw_status_t efw_hal_write(const char *name, const void *buf, uint16_t len, uint16_t *actual) {
    const efw_hal_ops_t *ops;
    efw_status_t s = efw_hal_get(name, &ops);
    if (s != EFW_OK) return s;
    if (!ops->write) return EFW_ERR_INVALID;
    return ops->write(ops->ctx, buf, len, actual);
}

efw_status_t efw_hal_ioctl(const char *name, uint32_t cmd, void *arg) {
    const efw_hal_ops_t *ops;
    efw_status_t s = efw_hal_get(name, &ops);
    if (s != EFW_OK) return s;
    if (!ops->ioctl) return EFW_ERR_INVALID;
    return ops->ioctl(ops->ctx, cmd, arg);
}

efw_status_t efw_comm_bind_hal(const char *comm_name, const efw_hal_ops_t **out_hal) {
    const efw_comm_ops_t *comm;
    efw_status_t s = efw_comm_get(comm_name, &comm);
    if (s != EFW_OK) return s;
    if (!comm->hal_name) return EFW_ERR_NOT_FOUND;
    return efw_hal_get(comm->hal_name, out_hal);
}

efw_status_t efw_comm_open(const char *name) {
    const efw_comm_ops_t *ops;
    efw_status_t s = efw_comm_get(name, &ops);
    if (s != EFW_OK) return s;
    return ops->open ? ops->open(ops->ctx) : EFW_OK;
}

efw_status_t efw_comm_close(const char *name) {
    const efw_comm_ops_t *ops;
    efw_status_t s = efw_comm_get(name, &ops);
    if (s != EFW_OK) return s;
    return ops->close ? ops->close(ops->ctx) : EFW_OK;
}

efw_status_t efw_comm_send(const char *name, const uint8_t *data, uint16_t len, uint16_t *actual) {
    const efw_comm_ops_t *ops;
    efw_status_t s = efw_comm_get(name, &ops);
    if (s != EFW_OK) return s;
    return ops->send(ops->ctx, data, len, actual);
}

efw_status_t efw_comm_recv(const char *name, uint8_t *data, uint16_t len, uint16_t *actual) {
    const efw_comm_ops_t *ops;
    efw_status_t s = efw_comm_get(name, &ops);
    if (s != EFW_OK) return s;
    return ops->recv(ops->ctx, data, len, actual);
}
