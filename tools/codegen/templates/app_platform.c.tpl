/**
 * @file    app_platform.c
 * @brief   Generated platform layer. Replace mock read/write internals with BSP calls.
 */

#include "app_platform.h"
#include "app_manifest.h"

#ifndef EFW_NULL_NAME
#define EFW_NULL_NAME 0
#endif

$TYPE_HELPERS$EXTERNS$HAL_DEFS$SENSOR_DEFS$ACTUATOR_DEFS$REGISTRATIONS
void app_platform_set_line_state(const char *input_name, const uint16_t *values, uint8_t count) {
    if (!input_name || !values) return;
$LINE_STATE_BODY}
