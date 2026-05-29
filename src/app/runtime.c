/**
 * @file    runtime.c
 * @brief   Generic application runtime implementation
 */

#include "efw/app/runtime.h"

#include "efw/efw.h"

static efw_status_t run_optional_step(efw_app_step_fn_t step) {
    if (!step) return EFW_OK;
    return step();
}

efw_status_t efw_app_init(const efw_app_manifest_t *manifest) {
    efw_status_t s;

    if (!manifest) return EFW_ERR_INVALID;

    s = efw_init();
    if (s != EFW_OK) return s;

    s = run_optional_step(manifest->init_pools);
    if (s != EFW_OK) return s;

    s = run_optional_step(manifest->register_platform);
    if (s != EFW_OK) return s;

    s = run_optional_step(manifest->register_components);
    if (s != EFW_OK) return s;

    return run_optional_step(manifest->bind_handles);
}

efw_status_t efw_app_update_1ms(const efw_app_manifest_t *manifest) {
    if (!manifest || !manifest->update_1ms) return EFW_ERR_INVALID;
    return manifest->update_1ms();
}
