/**
 * @file    runtime.c
 * @brief   Generic application runtime implementation
 */

#include "efw/app/runtime.h"

#include "efw/efw.h"

static efw_app_trace_fn_t g_app_trace_callback;
static void *g_app_trace_user;
static efw_app_time_ms_fn_t g_app_time_callback;
static void *g_app_time_user;

void efw_app_set_trace_callback(efw_app_trace_fn_t callback, void *user) {
    g_app_trace_callback = callback;
    g_app_trace_user = user;
}

void efw_app_set_time_provider(efw_app_time_ms_fn_t callback, void *user) {
    g_app_time_callback = callback;
    g_app_time_user = user;
}

uint32_t efw_app_current_time_ms(void) {
    return g_app_time_callback ? g_app_time_callback(g_app_time_user) : 0u;
}

void efw_app_trace_event(const char *event, const char *name, efw_status_t status) {
    efw_app_trace_event_ex(event, name, status, efw_app_current_time_ms(), EFW_APP_TRACE_DURATION_UNKNOWN);
}

void efw_app_trace_event_ex(const char *event, const char *name, efw_status_t status, uint32_t mcu_time_ms, uint32_t duration_ms) {
    if (g_app_trace_callback) {
        g_app_trace_callback(event, name, status, mcu_time_ms, duration_ms, g_app_trace_user);
    }
}

static efw_status_t run_optional_step(const char *name, efw_app_step_fn_t step) {
    efw_status_t status;
    uint32_t start_ms;
    uint32_t end_ms;
    if (!step) return EFW_OK;
    start_ms = efw_app_current_time_ms();
    efw_app_trace_event_ex("app.step.begin", name, EFW_OK, start_ms, EFW_APP_TRACE_DURATION_UNKNOWN);
    status = step();
    end_ms = efw_app_current_time_ms();
    efw_app_trace_event_ex("app.step.end", name, status, end_ms, end_ms - start_ms);
    return status;
}

efw_status_t efw_app_init(const efw_app_manifest_t *manifest) {
    efw_status_t s;
    uint32_t start_ms;
    uint32_t end_ms;

    if (!manifest) return EFW_ERR_INVALID;

    s = efw_init();
    if (s != EFW_OK) return s;

    start_ms = efw_app_current_time_ms();
    efw_app_trace_event_ex("app.init.begin", "app", EFW_OK, start_ms, EFW_APP_TRACE_DURATION_UNKNOWN);

    s = run_optional_step("init_pools", manifest->init_pools);
    if (s != EFW_OK) return s;

    s = run_optional_step("register_platform", manifest->register_platform);
    if (s != EFW_OK) return s;

    s = run_optional_step("register_components", manifest->register_components);
    if (s != EFW_OK) return s;

    s = run_optional_step("bind_handles", manifest->bind_handles);
    end_ms = efw_app_current_time_ms();
    efw_app_trace_event_ex("app.init.end", "app", s, end_ms, end_ms - start_ms);
    return s;
}

efw_status_t efw_app_update_1ms(const efw_app_manifest_t *manifest) {
    efw_status_t status;
    uint32_t start_ms;
    uint32_t end_ms;
    if (!manifest || !manifest->update_1ms) return EFW_ERR_INVALID;
    start_ms = efw_app_current_time_ms();
    efw_app_trace_event_ex("app.update.begin", "update_1ms", EFW_OK, start_ms, EFW_APP_TRACE_DURATION_UNKNOWN);
    status = manifest->update_1ms();
    end_ms = efw_app_current_time_ms();
    efw_app_trace_event_ex("app.update.end", "update_1ms", status, end_ms, end_ms - start_ms);
    return status;
}
