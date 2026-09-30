/**
 * @file    mock_efw_stubs.c
 * @brief   EFW 框架桩函数 - 用于测试
 */

#include "efw/core/common.h"
#include "efw/hal/hal.h"
#include "efw/device/sensor.h"
#include "efw/algorithm/registry.h"
#include "efw/state/state_machine.h"
#include <stddef.h>
#include <string.h>

/* ==================================================================
 *  HAL 桩函数
 * ================================================================== */

static const efw_hal_ops_t *g_hals[16];
static size_t g_hal_count = 0;

efw_status_t efw_hal_registry_init(void) { g_hal_count = 0; return EFW_OK; }
efw_status_t efw_hal_register(const efw_hal_ops_t *ops) {
    if (!ops || g_hal_count >= 16) return EFW_ERR_FULL;
    g_hals[g_hal_count++] = ops;
    return EFW_OK;
}
efw_status_t efw_hal_get(const char *name, const efw_hal_ops_t **out_ops) {
    for (size_t i = 0; i < g_hal_count; i++) {
        if (strcmp(g_hals[i]->name, name) == 0) {
            if (out_ops) *out_ops = g_hals[i];
            return EFW_OK;
        }
    }
    return EFW_ERR_NOT_FOUND;
}
size_t efw_hal_count(void) { return g_hal_count; }
void efw_hal_enumerate(efw_hal_enumerate_fn fn, void *user) {
    for (size_t i = 0; i < g_hal_count; i++) {
        fn(g_hals[i], user);
    }
}
efw_status_t efw_hal_read(const char *name, void *buf, uint16_t len, uint16_t *actual) {
    const efw_hal_ops_t *ops;
    efw_status_t ret = efw_hal_get(name, &ops);
    if (ret != EFW_OK) return ret;
    if (!ops->read) return EFW_ERR_NOT_READY;
    return ops->read(ops->ctx, buf, len, actual);
}
efw_status_t efw_hal_write(const char *name, const void *buf, uint16_t len, uint16_t *actual) {
    const efw_hal_ops_t *ops;
    efw_status_t ret = efw_hal_get(name, &ops);
    if (ret != EFW_OK) return ret;
    if (!ops->write) return EFW_ERR_NOT_READY;
    return ops->write(ops->ctx, buf, len, actual);
}
efw_status_t efw_hal_ioctl(const char *name, uint32_t cmd, void *arg) {
    const efw_hal_ops_t *ops;
    efw_status_t ret = efw_hal_get(name, &ops);
    if (ret != EFW_OK) return ret;
    if (!ops->ioctl) return EFW_ERR_NOT_READY;
    return ops->ioctl(ops->ctx, cmd, arg);
}

/* ==================================================================
 *  传感器桩函数
 * ================================================================== */

static const efw_sensor_ops_t *g_sensors[32];
static size_t g_sensor_count = 0;

efw_status_t efw_sensor_registry_init(void) { g_sensor_count = 0; return EFW_OK; }
efw_status_t efw_sensor_register(const efw_sensor_ops_t *ops) {
    if (!ops || g_sensor_count >= 32) return EFW_ERR_FULL;
    g_sensors[g_sensor_count++] = ops;
    return EFW_OK;
}
efw_status_t efw_sensor_get(const char *name, const efw_sensor_ops_t **out_ops) {
    for (size_t i = 0; i < g_sensor_count; i++) {
        if (strcmp(g_sensors[i]->name, name) == 0) {
            if (out_ops) *out_ops = g_sensors[i];
            return EFW_OK;
        }
    }
    return EFW_ERR_NOT_FOUND;
}
size_t efw_sensor_count(void) { return g_sensor_count; }
void efw_sensor_enumerate(efw_sensor_enumerate_fn fn, void *user) {
    for (size_t i = 0; i < g_sensor_count; i++) {
        fn(g_sensors[i], user);
    }
}
efw_status_t efw_sensor_read(const char *name, void *out, uint16_t out_size) {
    const efw_sensor_ops_t *ops;
    efw_status_t ret = efw_sensor_get(name, &ops);
    if (ret != EFW_OK) return ret;
    if (!ops->read) return EFW_ERR_NOT_READY;
    return ops->read(ops->ctx, out, out_size);
}

/* ==================================================================
 *  算法桩函数
 * ================================================================== */

static const efw_algo_ops_t *g_algos[16];
static size_t g_algo_count = 0;

efw_status_t efw_algo_registry_init(void) { g_algo_count = 0; return EFW_OK; }
efw_status_t efw_algo_register(const efw_algo_ops_t *ops) {
    if (!ops || g_algo_count >= 16) return EFW_ERR_FULL;
    g_algos[g_algo_count++] = ops;
    return EFW_OK;
}
efw_status_t efw_algo_get(const char *name, const efw_algo_ops_t **out_ops) {
    for (size_t i = 0; i < g_algo_count; i++) {
        if (strcmp(g_algos[i]->name, name) == 0) {
            if (out_ops) *out_ops = g_algos[i];
            return EFW_OK;
        }
    }
    return EFW_ERR_NOT_FOUND;
}
size_t efw_algo_count(void) { return g_algo_count; }
efw_status_t efw_algo_run(const char *name, const void *in, uint16_t in_size, void *out, uint16_t out_size) {
    const efw_algo_ops_t *ops;
    efw_status_t ret = efw_algo_get(name, &ops);
    if (ret != EFW_OK) return ret;
    if (!ops->run) return EFW_ERR_NOT_READY;
    return ops->run(ops->ctx, in, in_size, out, out_size);
}

/* ==================================================================
 *  状态机桩函数
 * ================================================================== */

efw_status_t efw_sm_registry_init(void) { return EFW_OK; }
efw_status_t efw_sm_register(efw_sm_context_t *ctx) { (void)ctx; return EFW_OK; }
efw_status_t efw_sm_get(const char *name, efw_sm_context_t **out_ctx) { (void)name; (void)out_ctx; return EFW_ERR_NOT_FOUND; }
size_t efw_sm_count(void) { return 0; }
const char *efw_sm_current_state(const efw_sm_context_t *ctx) { (void)ctx; return "UNKNOWN"; }
