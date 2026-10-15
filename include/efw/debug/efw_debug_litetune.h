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

typedef enum {
    /** send() returns only after all bytes have been transmitted. */
    EFW_DEBUG_LITETUNE_SEND_SYNC = 0,
    /** send() starts transmission; completion calls efw_debug_litetune_tx_complete(). */
    EFW_DEBUG_LITETUNE_SEND_ASYNC = 1,
} efw_debug_litetune_send_mode_t;

typedef struct {
    /**
     * EFW_OK means the buffer was accepted according to send_mode. The buffer
     * remains owned by LiteTune until synchronous return or asynchronous
     * completion. An asynchronous transport must call tx_complete exactly once
     * for each successful send, and must not call it after a failed send.
     */
    efw_debug_litetune_send_fn send;
    efw_debug_litetune_next_frame_id_fn next_frame_id;
    const char *device_name;
    uint32_t features;
    uint16_t telemetry_period_ms;
    efw_debug_litetune_send_mode_t send_mode;
} efw_debug_litetune_config_t;

typedef struct {
    uint32_t events_received;
    uint32_t events_queued;
    uint32_t events_flushed;
    uint32_t events_dropped;
    uint32_t process_calls;
    uint16_t current_queue_depth;
    uint16_t max_queue_depth;
} efw_debug_litetune_perf_t;

efw_status_t efw_debug_litetune_init(const efw_debug_litetune_config_t *config);
void efw_debug_litetune_tx_complete(void);
efw_status_t efw_debug_litetune_rx(const void *data, uint16_t len);
void efw_debug_litetune_process(void);
void efw_debug_litetune_process_budget(uint8_t max_trace_events);
void efw_debug_litetune_panic_flush(uint8_t max_trace_events);
efw_status_t efw_debug_litetune_report(void);
uint8_t efw_debug_litetune_is_ready(void);
efw_status_t efw_debug_litetune_get_perf(efw_debug_litetune_perf_t *perf);

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
