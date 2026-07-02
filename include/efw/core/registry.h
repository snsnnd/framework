#ifndef EFW_REGISTRY_H
#define EFW_REGISTRY_H

#include "efw/core/common.h"
#include <string.h>

static inline int efw_name_eq(const char *a, const char *b) {
    return a && b && strcmp(a, b) == 0;
}

static inline efw_status_t efw_registry_find_by_name(const void *const *pool, size_t count,
                                                      const char *name, size_t name_offset,
                                                      void *out_ptr) {
    if (!name || !out_ptr) return EFW_ERR_INVALID;
    const char **out = (const char **)out_ptr;
    for (size_t i = 0; i < count; ++i) {
        const char *entry_name = *(const char *const *)((const char *)pool[i] + name_offset);
        if (efw_name_eq(entry_name, name)) {
            *out = (const char *)pool[i];
            return EFW_OK;
        }
    }
    return EFW_ERR_NOT_FOUND;
}

static inline efw_status_t efw_registry_check_duplicate(const void *const *pool, size_t count,
                                                         const char *name, size_t name_offset) {
    for (size_t i = 0; i < count; ++i) {
        const char *entry_name = *(const char *const *)((const char *)pool[i] + name_offset);
        if (efw_name_eq(entry_name, name)) return EFW_ERR_ALREADY_EXISTS;
    }
    return EFW_OK;
}

#endif
