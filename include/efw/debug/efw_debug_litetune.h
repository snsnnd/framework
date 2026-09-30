/**
 * @file    efw_debug_litetune.h
 * @brief   EFW debug integration with the LiteTune wire protocol.
 */

#ifndef EFW_DEBUG_LITETUNE_H
#define EFW_DEBUG_LITETUNE_H

#include "efw/core/common.h"
#include "efw/debug/efw_debug.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef efw_status_t (*efw_debug_litetune_send_fn)(const void *data, uint16_t len);
typedef uint64_t (*efw_debug_litetune_next_frame_id_fn)(void);

typedef struct {
    efw_debug_litetune_send_fn send;
    efw_debug_litetune_next_frame_id_fn next_frame_id;
    const char *device_name;
    uint32_t features;
    uint16_t telemetry_period_ms;
} efw_debug_litetune_config_t;

efw_status_t efw_debug_litetune_init(const efw_debug_litetune_config_t *config);
efw_status_t efw_debug_litetune_rx(const void *data, uint16_t len);
void efw_debug_litetune_process(void);
efw_status_t efw_debug_litetune_report(void);
uint8_t efw_debug_litetune_is_ready(void);

int efw_debug_litetune_register_all(void);
int efw_debug_litetune_sync_all(void);

efw_status_t efw_debug_handle_command(const char *cmd_name,
                                      const uint8_t *payload,
                                      uint16_t payload_len,
                                      uint8_t *response,
                                      uint16_t response_size);

efw_status_t efw_debug_export_snapshot(uint8_t *buffer,
                                       uint16_t buffer_size,
                                       uint16_t *out_len);

#ifdef __cplusplus
}
#endif

#endif /* EFW_DEBUG_LITETUNE_H */
