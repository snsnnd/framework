#ifndef EFW_DIAGNOSTIC_H
#define EFW_DIAGNOSTIC_H

#include "efw/core/common.h"

#ifndef EFW_ERROR_HISTORY_SIZE
#define EFW_ERROR_HISTORY_SIZE 4
#endif

typedef struct {
    efw_status_t code;
    const char *module;
    const char *name;
    const char *message;
} efw_error_t;

void efw_diag_clear(void);
void efw_diag_set(efw_status_t code, const char *module, const char *name, const char *message);
const efw_error_t *efw_diag_last_error(void);
uint32_t efw_diag_error_count(void);
uint8_t efw_diag_history_size(void);
const efw_error_t *efw_diag_history_entry(uint8_t index);

#endif
