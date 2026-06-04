/**
 * @file    app_components.c
 * @brief   Generated algorithm and module registration.
 */

#include "app_components.h"
#include "app_manifest.h"
#include "app_bootstrap.h"

$ALGORITHM_RUNTIME_DEFS$CUSTOM_MODULE_RUNTIME_DEFS$PROJECT_MODULE_RUNTIME_DEFS
efw_status_t app_components_register(void) {
    efw_status_t s;
$ALGORITHM_REGISTRATIONS$CUSTOM_MODULE_REGISTRATIONS$PROJECT_MODULE_REGISTRATIONS    return EFW_OK;
}
