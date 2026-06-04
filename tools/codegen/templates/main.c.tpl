/**
 * @file    main.c
 * @brief   Generated host-checkable entry point.
 */

#include "app_bootstrap.h"
#include "app_platform.h"

int main(void) {
    if (app_init() != EFW_OK) return 1;
$SETUP    return (app_poll_forever() == EFW_OK) ? 0 : 1;
}
