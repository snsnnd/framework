#include "efw/core/diagnostic.h"
#include "efw/core/config.h"

static efw_error_t g_last_error;
static efw_error_t g_error_history[EFW_ERROR_HISTORY_SIZE];
static uint8_t g_history_idx;
static uint32_t g_error_count;

void efw_diag_clear(void) {
    g_last_error.code = EFW_OK;
    g_last_error.module = 0;
    g_last_error.name = 0;
    g_last_error.message = 0;
    g_history_idx = 0;
    g_error_count = 0;
    for (uint8_t i = 0; i < EFW_ERROR_HISTORY_SIZE; ++i) {
        g_error_history[i].code = EFW_OK;
        g_error_history[i].module = 0;
        g_error_history[i].name = 0;
        g_error_history[i].message = 0;
    }
}

void efw_diag_set(efw_status_t code, const char *module, const char *name, const char *message) {
    g_last_error.code = code;
    g_last_error.module = module;
    g_last_error.name = name;
    g_last_error.message = message;
    g_error_history[g_history_idx] = g_last_error;
    g_history_idx = (uint8_t)((g_history_idx + 1u) % EFW_ERROR_HISTORY_SIZE);
    g_error_count++;
}

const efw_error_t *efw_diag_last_error(void) {
    return &g_last_error;
}

uint32_t efw_diag_error_count(void) {
    return g_error_count;
}

uint8_t efw_diag_history_size(void) {
    return EFW_ERROR_HISTORY_SIZE;
}

const efw_error_t *efw_diag_history_entry(uint8_t index) {
    if (index >= EFW_ERROR_HISTORY_SIZE) return 0;
    return &g_error_history[index];
}
