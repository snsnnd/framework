/**
 * @file    efw_debug_litetune.c
 * @brief   EFW debug integration with LiteTune.
 */

#include "efw/debug/efw_debug_litetune.h"

#if EFW_ENABLE_DEBUG && EFW_ENABLE_LITETUNE

/*
 * LiteTune 是 Debug 核心与主机协议之间的适配层：Debug 负责监控点和事件，
 * LiteTune 负责参数/日志注册、帧编解码以及传输回调。下面的 .inc 文件按
 * 主题拆分协议映射，但会在本编译单元中共享同一组静态状态。
 */
#define LITETUNE_IMPLEMENTATION
#include "efw/debug/litetune/litetune.h"

#include <stdio.h>
#include <string.h>

#define EFW_DEBUG_LITETUNE_CMD_LIST     0x100u
#define EFW_DEBUG_LITETUNE_CMD_STATS    0x101u
#define EFW_DEBUG_LITETUNE_CMD_SNAPSHOT 0x102u
#define EFW_DEBUG_LITETUNE_CMD_PERF     0x103u
#define EFW_DEBUG_LITETUNE_LAYOUT_DEBUG 0x10u
#define EFW_DEBUG_LITETUNE_LAYOUT_TRACE 0x11u
#define EFW_DEBUG_LITETUNE_TRACE_EVENT_FIELD_ID    0xF001u
#define EFW_DEBUG_LITETUNE_TRACE_NAME_FIELD_ID     0xF002u
#define EFW_DEBUG_LITETUNE_TRACE_STATUS_FIELD_ID   0xF003u
#define EFW_DEBUG_LITETUNE_TRACE_TIME_FIELD_ID     0xF004u
#define EFW_DEBUG_LITETUNE_TRACE_DURATION_FIELD_ID 0xF005u
#ifndef EFW_DEBUG_LITETUNE_TRACE_QUEUE_SIZE
#define EFW_DEBUG_LITETUNE_TRACE_QUEUE_SIZE 16u
#endif
#ifndef EFW_DEBUG_LITETUNE_TRACE_TEXT_SIZE
#define EFW_DEBUG_LITETUNE_TRACE_TEXT_SIZE 160u
#endif
#ifndef EFW_DEBUG_LITETUNE_DEFAULT_FLUSH_EVENTS
#define EFW_DEBUG_LITETUNE_DEFAULT_FLUSH_EVENTS 2u
#endif

static efw_debug_litetune_config_t g_litetune_config;
static lt_config_t g_litetune_lt_config;
static uint16_t g_litetune_param_count;
static uint64_t g_litetune_next_frame_id = 1u;
static uint8_t g_litetune_ready;

#include "efw_debug_litetune_trace.inc"

static lt_status_t map_efw_to_lt_status(efw_status_t status)
{
    switch (status) {
    case EFW_OK:
        return LT_STATUS_OK;
    case EFW_ERR_NOT_FOUND:
        return LT_STATUS_NOT_FOUND;
    case EFW_ERR_NOT_READY:
        return LT_STATUS_NOT_READY;
    case EFW_ERR_UNSUPPORTED:
        return LT_STATUS_UNSUPPORTED;
    case EFW_ERR_FULL:
    case EFW_ERR_RANGE:
        return LT_STATUS_RANGE_ERROR;
    case EFW_ERR_IO:
        return LT_STATUS_STORAGE_ERROR;
    case EFW_ERR_ALREADY_EXISTS:
        return LT_STATUS_CONFLICT;
    case EFW_ERR_INVALID:
    default:
        return LT_STATUS_BAD_PAYLOAD;
    }
}

static efw_status_t map_lt_to_efw_status(lt_status_t status)
{
    switch (status) {
    case LT_STATUS_OK:
    case LT_STATUS_ACCEPTED:
        return EFW_OK;
    case LT_STATUS_NOT_FOUND:
        return EFW_ERR_NOT_FOUND;
    case LT_STATUS_NOT_READY:
    case LT_STATUS_INVALID_STATE:
        return EFW_ERR_NOT_READY;
    case LT_STATUS_UNSUPPORTED:
        return EFW_ERR_UNSUPPORTED;
    case LT_STATUS_BUSY:
        return EFW_ERR_NOT_READY;
    case LT_STATUS_TOO_LARGE:
    case LT_STATUS_RANGE_ERROR:
        return EFW_ERR_RANGE;
    case LT_STATUS_CONFLICT:
        return EFW_ERR_ALREADY_EXISTS;
    case LT_STATUS_STORAGE_ERROR:
    case LT_STATUS_TX_DROP:
    case LT_STATUS_RX_OVERFLOW:
        return EFW_ERR_IO;
    case LT_STATUS_BAD_PAYLOAD:
    default:
        return EFW_ERR_INVALID;
    }
}

#include "efw_debug_litetune_params.inc"

static lt_frame_id_t efw_litetune_next_frame_id(void)
{
    uint64_t frame_id;
    if (g_litetune_config.next_frame_id) {
        frame_id = g_litetune_config.next_frame_id();
    } else {
        frame_id = g_litetune_next_frame_id++;
    }
    if (frame_id == 0u) {
        frame_id = 1u;
        g_litetune_next_frame_id = 2u;
    }
    return (lt_frame_id_t)frame_id;
}

static lt_status_t efw_litetune_send(const void *data, uint16_t len)
{
    efw_status_t status;
    if (!g_litetune_config.send) {
        return LT_STATUS_NOT_READY;
    }
    status = g_litetune_config.send(data, len);
    if (status == EFW_OK && g_litetune_config.send_mode == EFW_DEBUG_LITETUNE_SEND_SYNC) {
        lt_send_complete();
    }
    return map_efw_to_lt_status(status);
}

#include "efw_debug_litetune_commands.inc"

efw_status_t efw_debug_litetune_init(const efw_debug_litetune_config_t *config)
{
    lt_status_t status;

    if (!config || !config->send ||
        (config->send_mode != EFW_DEBUG_LITETUNE_SEND_SYNC &&
         config->send_mode != EFW_DEBUG_LITETUNE_SEND_ASYNC)) {
        return EFW_ERR_INVALID;
    }

    g_litetune_config = *config;
    trace_queue_reset();
    if (!g_litetune_config.device_name) {
        g_litetune_config.device_name = "efw-device";
    }
    if (g_litetune_config.features == 0u) {
        g_litetune_config.features = LT_FEATURE_PARAM_GET | LT_FEATURE_CMD | LT_FEATURE_LOG_PACKED | LT_FEATURE_LOG_TEXT;
    }

    (void)build_litetune_registries(g_litetune_config.telemetry_period_ms);

    g_litetune_lt_config.send = efw_litetune_send;
    g_litetune_lt_config.next_frame_id = efw_litetune_next_frame_id;
    g_litetune_lt_config.device_name = g_litetune_config.device_name;
    g_litetune_lt_config.mcu_supported_features = g_litetune_config.features;

    status = lt_init(&g_litetune_lt_config);
    if (status != LT_STATUS_OK) {
        g_litetune_ready = 0u;
        return map_lt_to_efw_status(status);
    }

    if (g_litetune_param_count > 0u) {
        status = lt_register_param(&g_litetune_param_registry);
        if (status != LT_STATUS_OK) {
            g_litetune_ready = 0u;
            return map_lt_to_efw_status(status);
        }
    }

    status = lt_register_log(&g_litetune_log_registry);
    if (status != LT_STATUS_OK) {
        g_litetune_ready = 0u;
        return map_lt_to_efw_status(status);
    }

    status = lt_register_cmd(&g_litetune_cmd_registry);
    if (status != LT_STATUS_OK) {
        g_litetune_ready = 0u;
        return map_lt_to_efw_status(status);
    }

    status = lt_register_complete();
    g_litetune_ready = (uint8_t)(status == LT_STATUS_OK);
    if (g_litetune_ready) {
        efw_debug_set_event_sink(litetune_debug_event_sink, NULL);
        efw_debug_attach_runtime_trace();
    }
    return map_lt_to_efw_status(status);
}

void efw_debug_litetune_tx_complete(void)
{
    if (g_litetune_ready && g_litetune_config.send_mode == EFW_DEBUG_LITETUNE_SEND_ASYNC) {
        lt_send_complete();
    }
}

efw_status_t efw_debug_litetune_rx(const void *data, uint16_t len)
{
    return map_lt_to_efw_status(lt_rx_from_isr(data, len));
}

void efw_debug_litetune_process(void)
{
    efw_debug_litetune_process_budget((uint8_t)EFW_DEBUG_LITETUNE_DEFAULT_FLUSH_EVENTS);
}

void efw_debug_litetune_process_budget(uint8_t max_trace_events)
{
    efw_debug_litetune_trace_record_t record;
    uint8_t flushed = 0u;
    g_litetune_perf.process_calls++;
    refresh_string_views();
    if (lt_state_get() != LT_STATE_CONNECTED) {
        lt_process();
        return;
    }
    while (flushed < max_trace_events && trace_queue_pop(&record) != 0u) {
        lt_status_t trace_status;
        g_trace_event_id = record.event_id;
        g_trace_name_id = record.name_id;
        g_trace_status = record.status;
        g_trace_mcu_time_ms = record.mcu_time_ms;
        g_trace_duration_ms = record.duration_ms;
        trace_status = lt_log_report(EFW_DEBUG_LITETUNE_LAYOUT_TRACE);
        if (trace_status == LT_STATUS_OK) {
            g_litetune_perf.events_flushed++;
        } else {
            if (lt_log_text(0x01u, record.text) == LT_STATUS_OK) {
                g_litetune_perf.events_flushed++;
            } else {
                g_litetune_perf.events_dropped++;
            }
        }
        flushed++;
    }
    lt_process();
}

void efw_debug_litetune_panic_flush(uint8_t max_trace_events)
{
    uint8_t remaining = max_trace_events;
    if (remaining == 0u) {
        remaining = (uint8_t)EFW_DEBUG_LITETUNE_TRACE_QUEUE_SIZE;
    }
    while (remaining > 0u && g_trace_count > 0u) {
        efw_debug_litetune_process_budget(1u);
        remaining--;
    }
}

efw_status_t efw_debug_litetune_report(void)
{
    if (g_litetune_param_count == 0u) {
        return EFW_ERR_NOT_FOUND;
    }
    refresh_string_views();
    return map_lt_to_efw_status(lt_log_report(EFW_DEBUG_LITETUNE_LAYOUT_DEBUG));
}

uint8_t efw_debug_litetune_is_ready(void)
{
    return g_litetune_ready;
}

efw_status_t efw_debug_litetune_get_perf(efw_debug_litetune_perf_t *perf)
{
    if (!perf) {
        return EFW_ERR_INVALID;
    }
    *perf = g_litetune_perf;
    perf->current_queue_depth = g_trace_count;
    return EFW_OK;
}

int efw_debug_litetune_register_all(void)
{
    int registered = 0;
    efw_debug_foreach_point(register_litetune_point_iter, &registered);
    return registered;
}

int efw_debug_litetune_sync_all(void)
{
    int synced = 0;
    efw_debug_foreach_point(sync_litetune_point_iter, &synced);
    return synced;
}

efw_status_t efw_debug_handle_command(const char *cmd_name,
                                      const uint8_t *payload,
                                      uint16_t payload_len,
                                      uint8_t *response,
                                      uint16_t response_size)
{
    (void)payload;
    (void)payload_len;

    if (!cmd_name || !response) {
        return EFW_ERR_INVALID;
    }

    if (strcmp(cmd_name, "debug.list") == 0) {
        efw_debug_list_writer_t writer;
        uint16_t point_count;
        if (response_size < 2u) {
            return EFW_ERR_RANGE;
        }
        point_count = efw_debug_point_count();
        response[0] = (uint8_t)(point_count & 0xFFu);
        response[1] = (uint8_t)((point_count >> 8) & 0xFFu);
        writer.response = response;
        writer.response_size = response_size;
        writer.offset = 2u;
        efw_debug_foreach_point(write_debug_list_item, &writer);
        return EFW_OK;
    }

    if (strcmp(cmd_name, "debug.stats") == 0) {
        efw_debug_stats_t stats;
        uint16_t offset = 0u;
        efw_status_t ret = efw_debug_get_stats(&stats);
        if (ret != EFW_OK) {
            return ret;
        }
        if (response_size < 14u) {
            return EFW_ERR_RANGE;
        }
        response[offset++] = (uint8_t)(stats.total_points & 0xFFu);
        response[offset++] = (uint8_t)((stats.total_points >> 8) & 0xFFu);
        response[offset++] = (uint8_t)(stats.efw_points & 0xFFu);
        response[offset++] = (uint8_t)((stats.efw_points >> 8) & 0xFFu);
        response[offset++] = (uint8_t)(stats.custom_points & 0xFFu);
        response[offset++] = (uint8_t)((stats.custom_points >> 8) & 0xFFu);
        (void)memcpy(&response[offset], &stats.update_count, 4u);
        offset = (uint16_t)(offset + 4u);
        (void)memcpy(&response[offset], &stats.error_count, 4u);
        return EFW_OK;
    }

    if (strcmp(cmd_name, "debug.perf") == 0) {
        efw_debug_litetune_perf_t perf;
        efw_status_t ret = efw_debug_litetune_get_perf(&perf);
        if (ret != EFW_OK) {
            return ret;
        }
        if (response_size < (uint16_t)sizeof(perf)) {
            return EFW_ERR_RANGE;
        }
        (void)memcpy(response, &perf, sizeof(perf));
        return EFW_OK;
    }

    if (strcmp(cmd_name, "debug.snapshot") == 0) {
        uint16_t out_len = 0u;
        return efw_debug_export_snapshot(response, response_size, &out_len);
    }

    return EFW_ERR_UNSUPPORTED;
}

efw_status_t efw_debug_export_snapshot(uint8_t *buffer, uint16_t buffer_size, uint16_t *out_len)
{
    efw_debug_snapshot_writer_t writer;
    efw_debug_stats_t stats;
    efw_status_t status;
    uint16_t offset = 0u;

    if (!buffer || !out_len) {
        return EFW_ERR_INVALID;
    }
    if (buffer_size < 6u) {
        return EFW_ERR_RANGE;
    }

    status = efw_debug_get_stats(&stats);
    if (status != EFW_OK) {
        return status;
    }

    (void)memcpy(&buffer[offset], &stats.update_count, 4u);
    offset = (uint16_t)(offset + 4u);
    buffer[offset++] = (uint8_t)(stats.total_points & 0xFFu);
    buffer[offset++] = (uint8_t)((stats.total_points >> 8) & 0xFFu);

    writer.buffer = buffer;
    writer.buffer_size = buffer_size;
    writer.offset = offset;
    efw_debug_foreach_point(write_debug_snapshot_item, &writer);
    *out_len = writer.offset;
    return EFW_OK;
}

#endif /* EFW_ENABLE_DEBUG && EFW_ENABLE_LITETUNE */
