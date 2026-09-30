#ifndef LITETUNE_H
#define LITETUNE_H

/*
 * LiteTune MCU facade.
 *
 * Usage:
 *   // exactly one translation unit
 *   #define LITETUNE_IMPLEMENTATION
 *   #include "src/litetune/litetune.h"
 *
 *   // all other translation units
 *   #include "src/litetune/litetune.h"
 */

#include "include/lt_config.h"
#include "include/lt_common.h"
#include "include/lt_utils.h"
#include "include/lt_cobs.h"
#include "include/lt_frame.h"
#include "include/lt_state.h"
#include "include/lt_registry.h"
#include "include/lt_tx.h"
#include "include/lt_runtime.h"
#include "include/lt_init.h"
#include "include/lt_telemetry.h"
#include "include/lt_params.h"
#include "include/lt_cmd.h"
#include "include/lt_rx.h"
#include "include/lt_processor.h"

#endif /* LITETUNE_H */
