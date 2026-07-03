/**
 * @file    efw_debug_litetune.c
 * @brief   EFW debug integration with LiteTune.
 */

#include "efw/debug/efw_debug_litetune.h"

#if EFW_ENABLE_DEBUG && EFW_ENABLE_LITETUNE

#define LITETUNE_IMPLEMENTATION
#include "litetune.h"

#include <string.h>

#define EFW_DEBUG_LITETUNE_CMD_LIST     0x100u
#define EFW_DEBUG_LITETUNE_CMD_STATS    0x101u
#define EFW_DEBUG_LITETUNE_CMD_SNAPSHOT 0x102u
#define EFW_DEBUG_LITETUNE_LAYOUT_DEBUG 0x10u

static lt_param_desc_t g_litetune_params[EFW_MAX_DEBUG_POINTS];
static lt_log_field_desc_t g_litetune_fields[EFW_MAX_DEBUG_POINTS];
static lt_param_registry_t g_litetune_param_registry;
static lt_log_layout_desc_t g_litetune_layout;
static lt_log_registry_t g_litetune_log_registry;
static efw_debug_litetune_config_t g_litetune_config;
static uint16_t g_litetune_param_count;
static uint64_t g_litetune_next_frame_id = 1u;
static uint8_t g_litetune_ready;

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

static uint8_t map_debug_type_to_litetune(efw_debug_type_t debug_type)
{
    switch (debug_type) {
    case EFW_DEBUG_TYPE_BOOL:
        return (uint8_t)LT_VALUE_BOOL;
    case EFW_DEBUG_TYPE_U8:
        return (uint8_t)LT_VALUE_U8;
    case EFW_DEBUG_TYPE_I8:
        return (uint8_t)LT_VALUE_I8;
    case EFW_DEBUG_TYPE_U16:
        return (uint8_t)LT_VALUE_U16;
    case EFW_DEBUG_TYPE_I16:
        return (uint8_t)LT_VALUE_I16;
    case EFW_DEBUG_TYPE_U32:
        return (uint8_t)LT_VALUE_U32;
    case EFW_DEBUG_TYPE_I32:
        return (uint8_t)LT_VALUE_I32;
    case EFW_DEBUG_TYPE_F32:
        return (uint8_t)LT_VALUE_F32;
    case EFW_DEBUG_TYPE_F64:
        return (uint8_t)LT_VALUE_F64;
    default:
        return (uint8_t)LT_VALUE_INVALID;
    }
}

static uint8_t get_debug_type_size(efw_debug_type_t type)
{
    switch (type) {
    case EFW_DEBUG_TYPE_BOOL:
    case EFW_DEBUG_TYPE_U8:
    case EFW_DEBUG_TYPE_I8:
        return 1u;
    case EFW_DEBUG_TYPE_U16:
    case EFW_DEBUG_TYPE_I16:
        return 2u;
    case EFW_DEBUG_TYPE_U32:
    case EFW_DEBUG_TYPE_I32:
    case EFW_DEBUG_TYPE_F32:
        return 4u;
    case EFW_DEBUG_TYPE_F64:
        return 8u;
    default:
        return 0u;
    }
}

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
    if (!g_litetune_config.send) {
        return LT_STATUS_NOT_READY;
    }
    return map_efw_to_lt_status(g_litetune_config.send(data, len));
}

static lt_status_t debug_command_callback(const uint8_t *req_payload,
                                          uint16_t req_len,
                                          uint8_t *resp_payload,
                                          uint16_t resp_cap,
                                          uint16_t *resp_len,
                                          void *user_ctx)
{
    const char *cmd_name = (const char *)user_ctx;
    efw_status_t status;

    if (!resp_len || !cmd_name) {
        return LT_STATUS_BAD_PAYLOAD;
    }

    *resp_len = 0u;
    status = efw_debug_handle_command(cmd_name, req_payload, req_len, resp_payload, resp_cap);
    if (status != EFW_OK) {
        return map_efw_to_lt_status(status);
    }

    if (strcmp(cmd_name, "debug.stats") == 0) {
        *resp_len = 14u;
    } else if (strcmp(cmd_name, "debug.snapshot") == 0) {
        status = efw_debug_export_snapshot(resp_payload, resp_cap, resp_len);
        return map_efw_to_lt_status(status);
    } else {
        uint16_t offset = 2u;
        while (offset < resp_cap) {
            uint8_t name_len = resp_payload[offset];
            if (name_len == 0u || (uint16_t)(offset + 1u + name_len + 3u) > resp_cap) {
                break;
            }
            offset = (uint16_t)(offset + 1u + name_len + 3u);
        }
        *resp_len = offset;
    }

    return LT_STATUS_OK;
}

static lt_cmd_desc_t g_litetune_cmds[] = {
    { EFW_DEBUG_LITETUNE_CMD_LIST, LT_CMD_FLAG_HOST_TO_MCU, "debug.list", debug_command_callback, (void *)"debug.list" },
    { EFW_DEBUG_LITETUNE_CMD_STATS, LT_CMD_FLAG_HOST_TO_MCU, "debug.stats", debug_command_callback, (void *)"debug.stats" },
    { EFW_DEBUG_LITETUNE_CMD_SNAPSHOT, LT_CMD_FLAG_HOST_TO_MCU, "debug.snapshot", debug_command_callback, (void *)"debug.snapshot" },
};

static lt_cmd_registry_t g_litetune_cmd_registry = {
    (uint16_t)(sizeof(g_litetune_cmds) / sizeof(g_litetune_cmds[0])),
    g_litetune_cmds,
};

static void build_litetune_point_iter(const efw_debug_point_t *point, void *user)
{
    uint16_t *count = (uint16_t *)user;
    uint8_t value_type;

    if (!point || !point->registered || !point->value_ptr || !count || *count >= (uint16_t)EFW_MAX_DEBUG_POINTS) {
        return;
    }

    value_type = map_debug_type_to_litetune(point->type);
    if (value_type == (uint8_t)LT_VALUE_INVALID) {
        return;
    }

    g_litetune_params[*count].param_id = (lt_param_id_t)point->param_id;
    g_litetune_params[*count].value_type = value_type;
    g_litetune_params[*count].name = point->name;
    g_litetune_params[*count].unit = "";
    g_litetune_params[*count].value_ptr = (void *)point->value_ptr;
    g_litetune_params[*count].flags = LT_PARAM_FLAG_READABLE;
    g_litetune_params[*count].min_value_ptr = 0;
    g_litetune_params[*count].max_value_ptr = 0;
    g_litetune_params[*count].default_value_ptr = 0;

    g_litetune_fields[*count].field_id = (lt_field_id_t)point->param_id;
    g_litetune_fields[*count].value_type = value_type;
    g_litetune_fields[*count].name = point->name;
    g_litetune_fields[*count].unit = "";
    g_litetune_fields[*count].value_ptr = point->value_ptr;

    *count = (uint16_t)(*count + 1u);
}

static efw_status_t build_litetune_registries(uint16_t telemetry_period_ms)
{
    g_litetune_param_count = 0u;
    (void)memset(g_litetune_params, 0, sizeof(g_litetune_params));
    (void)memset(g_litetune_fields, 0, sizeof(g_litetune_fields));
    efw_debug_foreach_point(build_litetune_point_iter, &g_litetune_param_count);

    g_litetune_param_registry.param_count = g_litetune_param_count;
    g_litetune_param_registry.params = g_litetune_params;

    g_litetune_layout.layout_id = EFW_DEBUG_LITETUNE_LAYOUT_DEBUG;
    g_litetune_layout.default_period_ms = telemetry_period_ms ? telemetry_period_ms : 100u;
    g_litetune_layout.field_count = (uint8_t)((g_litetune_param_count > 255u) ? 255u : g_litetune_param_count);
    g_litetune_layout.fields = g_litetune_fields;

    g_litetune_log_registry.layout_count = (g_litetune_param_count > 0u) ? 1u : 0u;
    g_litetune_log_registry.layouts = (g_litetune_param_count > 0u) ? &g_litetune_layout : 0;

    return EFW_OK;
}

efw_status_t efw_debug_litetune_init(const efw_debug_litetune_config_t *config)
{
    lt_config_t lt_config;
    lt_status_t status;

    if (!config || !config->send) {
        return EFW_ERR_INVALID;
    }

    g_litetune_config = *config;
    if (!g_litetune_config.device_name) {
        g_litetune_config.device_name = "efw-device";
    }
    if (g_litetune_config.features == 0u) {
        g_litetune_config.features = LT_FEATURE_PARAM_GET | LT_FEATURE_CMD | LT_FEATURE_LOG_PACKED;
    }

    (void)build_litetune_registries(g_litetune_config.telemetry_period_ms);

    lt_config.send = efw_litetune_send;
    lt_config.next_frame_id = efw_litetune_next_frame_id;
    lt_config.device_name = g_litetune_config.device_name;
    lt_config.mcu_supported_features = g_litetune_config.features;

    status = lt_init(&lt_config);
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
        status = lt_register_log(&g_litetune_log_registry);
        if (status != LT_STATUS_OK) {
            g_litetune_ready = 0u;
            return map_lt_to_efw_status(status);
        }
    }

    status = lt_register_cmd(&g_litetune_cmd_registry);
    if (status != LT_STATUS_OK) {
        g_litetune_ready = 0u;
        return map_lt_to_efw_status(status);
    }

    status = lt_register_complete();
    g_litetune_ready = (uint8_t)(status == LT_STATUS_OK);
    return map_lt_to_efw_status(status);
}

efw_status_t efw_debug_litetune_rx(const void *data, uint16_t len)
{
    return map_lt_to_efw_status(lt_rx_from_isr(data, len));
}

void efw_debug_litetune_process(void)
{
    lt_process();
}

efw_status_t efw_debug_litetune_report(void)
{
    if (g_litetune_param_count == 0u) {
        return EFW_ERR_NOT_FOUND;
    }
    return map_lt_to_efw_status(lt_log_report(EFW_DEBUG_LITETUNE_LAYOUT_DEBUG));
}

uint8_t efw_debug_litetune_is_ready(void)
{
    return g_litetune_ready;
}

static efw_status_t register_point_to_litetune(const efw_debug_point_t *point)
{
    if (!point || !point->registered) {
        return EFW_ERR_INVALID;
    }
    return EFW_OK;
}

static efw_status_t update_litetune_param(const efw_debug_point_t *point)
{
    if (!point || !point->registered || !point->value_ptr) {
        return EFW_ERR_INVALID;
    }
    return EFW_OK;
}

static void register_litetune_point_iter(const efw_debug_point_t *point, void *user)
{
    int *count = (int *)user;
    if (count && register_point_to_litetune(point) == EFW_OK) {
        (*count)++;
    }
}

static void sync_litetune_point_iter(const efw_debug_point_t *point, void *user)
{
    int *count = (int *)user;
    if (count && update_litetune_param(point) == EFW_OK) {
        (*count)++;
    }
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

typedef struct {
    uint8_t *response;
    uint16_t response_size;
    uint16_t offset;
} efw_debug_list_writer_t;

typedef struct {
    uint8_t *buffer;
    uint16_t buffer_size;
    uint16_t offset;
} efw_debug_snapshot_writer_t;

static void write_debug_list_item(const efw_debug_point_t *point, void *user)
{
    efw_debug_list_writer_t *writer = (efw_debug_list_writer_t *)user;
    uint8_t name_len;

    if (!point || !writer || writer->offset >= writer->response_size) {
        return;
    }

    name_len = (uint8_t)strlen(point->name);
    if ((uint16_t)(writer->offset + 1u + name_len + 3u) > writer->response_size) {
        return;
    }

    writer->response[writer->offset++] = name_len;
    (void)memcpy(&writer->response[writer->offset], point->name, name_len);
    writer->offset = (uint16_t)(writer->offset + name_len);
    writer->response[writer->offset++] = (uint8_t)point->type;
    writer->response[writer->offset++] = (uint8_t)(point->param_id & 0xFFu);
    writer->response[writer->offset++] = (uint8_t)((point->param_id >> 8) & 0xFFu);
}

static void write_debug_snapshot_item(const efw_debug_point_t *point, void *user)
{
    efw_debug_snapshot_writer_t *writer = (efw_debug_snapshot_writer_t *)user;
    uint8_t value_size;

    if (!point || !writer || !point->value_ptr) {
        return;
    }

    value_size = get_debug_type_size(point->type);
    if (value_size == 0u || (uint16_t)(writer->offset + 3u + value_size) > writer->buffer_size) {
        return;
    }

    writer->buffer[writer->offset++] = (uint8_t)(point->param_id & 0xFFu);
    writer->buffer[writer->offset++] = (uint8_t)((point->param_id >> 8) & 0xFFu);
    writer->buffer[writer->offset++] = value_size;
    (void)memcpy(&writer->buffer[writer->offset], point->value_ptr, value_size);
    writer->offset = (uint16_t)(writer->offset + value_size);
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
