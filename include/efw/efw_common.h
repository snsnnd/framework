#ifndef EFW_COMMON_H
#define EFW_COMMON_H

#include <stdint.h>
#include <stddef.h>

typedef enum {
    EFW_OK = 0,
    EFW_ERR_INVALID = -1,
    EFW_ERR_FULL = -2,
    EFW_ERR_NOT_FOUND = -3,
    EFW_ERR_ALREADY_EXISTS = -4
} efw_status_t;

#endif
