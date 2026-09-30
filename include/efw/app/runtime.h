/**
 * @file    runtime.h
 * @brief   Application runtime：按 manifest 执行初始化、注册、绑定和周期更新
 */

#ifndef EFW_APP_RUNTIME_H
#define EFW_APP_RUNTIME_H

#include "efw/core/common.h"

typedef struct {
    const char *port;
    const char *contract;
    const char *c_type;
    const void *data;
    uint16_t size;
    uint16_t expected_size;
    uint8_t valid;
} efw_app_input_view_t;

typedef struct {
    const efw_app_input_view_t *ports;
    uint8_t count;
    const char *active_port;
} efw_app_multi_input_t;

static inline const efw_app_input_view_t *efw_app_multi_input_get(const efw_app_multi_input_t *input, const char *port) {
    uint8_t i;
    if (!input || !port) return 0;
    for (i = 0; i < input->count; ++i) {
        const efw_app_input_view_t *item = &input->ports[i];
        const char *a = item->port;
        const char *b = port;
        if (!a) continue;
        while (*a && *b && (*a == *b)) {
            ++a;
            ++b;
        }
        if (*a == '\0' && *b == '\0') return item;
    }
    return 0;
}

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
