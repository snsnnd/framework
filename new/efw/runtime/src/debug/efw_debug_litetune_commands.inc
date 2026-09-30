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
    } else if (strcmp(cmd_name, "debug.perf") == 0) {
        *resp_len = (uint16_t)sizeof(efw_debug_litetune_perf_t);
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
    { EFW_DEBUG_LITETUNE_CMD_PERF, LT_CMD_FLAG_HOST_TO_MCU, "debug.perf", debug_command_callback, (void *)"debug.perf" },
};

static lt_cmd_registry_t g_litetune_cmd_registry = {
    (uint16_t)(sizeof(g_litetune_cmds) / sizeof(g_litetune_cmds[0])),
    g_litetune_cmds,
};

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

    if (point->type == EFW_DEBUG_TYPE_STRING) {
        const char *text = (const char *)point->value_ptr;
        value_size = bounded_cstr_len_u8(text);
        if ((uint16_t)(writer->offset + 3u + value_size) > writer->buffer_size) {
            return;
        }
        writer->buffer[writer->offset++] = (uint8_t)(point->param_id & 0xFFu);
        writer->buffer[writer->offset++] = (uint8_t)((point->param_id >> 8) & 0xFFu);
        writer->buffer[writer->offset++] = value_size;
        if (value_size > 0u) {
            (void)memcpy(&writer->buffer[writer->offset], text, value_size);
            writer->offset = (uint16_t)(writer->offset + value_size);
        }
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
