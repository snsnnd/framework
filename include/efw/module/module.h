#ifndef EFW_MODULE_REGISTRY_H
#define EFW_MODULE_REGISTRY_H

#include "efw/core/common.h"

typedef enum {
    EFW_MODULE_DRIVER = 0,
    EFW_MODULE_SERVICE,
    EFW_MODULE_APP,
    EFW_MODULE_CUSTOM
} efw_module_type_t;

typedef struct {
    const char *name;
    efw_module_type_t type;
    void *ctx;
    efw_status_t (*init)(void *ctx);
    efw_status_t (*start)(void *ctx);
    efw_status_t (*stop)(void *ctx);
    efw_status_t (*poll)(void *ctx);
} efw_module_ops_t;

efw_status_t efw_module_registry_init(void);
efw_status_t efw_module_register(const efw_module_ops_t *ops);
efw_status_t efw_module_get(const char *name, const efw_module_ops_t **out_ops);
efw_status_t efw_module_init(const char *name);
efw_status_t efw_module_start(const char *name);
efw_status_t efw_module_stop(const char *name);
efw_status_t efw_module_poll(const char *name);
efw_status_t efw_module_init_all(void);
efw_status_t efw_module_start_all(void);
efw_status_t efw_module_poll_all(void);
size_t efw_module_count_by_type(efw_module_type_t type);

#endif
