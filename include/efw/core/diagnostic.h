#ifndef EFW_DIAGNOSTIC_H
#define EFW_DIAGNOSTIC_H

#include "efw/core/common.h"

typedef struct {
    efw_status_t code;
    const char *module;
    const char *name;
    const char *message;
} efw_error_t;

void efw_diag_clear(void);
void efw_diag_set(efw_status_t code, const char *module, const char *name, const char *message);
const efw_error_t *efw_diag_last_error(void);

#endif
