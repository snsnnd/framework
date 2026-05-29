/**
 * @file    runtime.h
 * @brief   Application runtime：按 manifest 执行初始化、注册、绑定和周期更新
 */

#ifndef EFW_APP_RUNTIME_H
#define EFW_APP_RUNTIME_H

#include "efw/core/common.h"

typedef efw_status_t (*efw_app_step_fn_t)(void);

typedef struct {
    efw_app_step_fn_t init_pools;
    efw_app_step_fn_t register_platform;
    efw_app_step_fn_t register_components;
    efw_app_step_fn_t bind_handles;
    efw_app_step_fn_t update_1ms;
} efw_app_manifest_t;

efw_status_t efw_app_init(const efw_app_manifest_t *manifest);
efw_status_t efw_app_update_1ms(const efw_app_manifest_t *manifest);

#endif
