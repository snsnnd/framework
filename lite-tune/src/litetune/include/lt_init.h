#ifndef LT_INIT_H
#define LT_INIT_H

#include "lt_config.h"
#include "lt_common.h"
#include "lt_utils.h"
#include "lt_state.h"
#include "lt_registry.h"
#include "lt_tx.h"
#include "lt_runtime.h"

#include <stdint.h>
#include <stddef.h>



#ifdef __cplusplus
extern "C" {
#endif

LT_API void lt_rx_reset(void);
LT_API void lt_params_reset(void);
LT_API void lt_cmd_reset(void);
LT_API void lt_telemetry_reset(void);

LT_API lt_status_t lt_init(const lt_config_t *config);
LT_API lt_status_t lt_register_log(const lt_log_registry_t *registry);
LT_API lt_status_t lt_register_param(const lt_param_registry_t *registry);
LT_API lt_status_t lt_register_cmd(const lt_cmd_registry_t *registry);
LT_API lt_status_t lt_register_complete(void);
LT_API lt_status_t lt_init_handle_discover(lt_frame_id_t request_frame_id, const uint8_t *payload, uint16_t payload_len);

#ifdef __cplusplus
}
#endif

#ifdef LITETUNE_IMPLEMENTATION

static uint16_t lt_init_count_log_layouts_(const lt_log_registry_t *registry)
{
    return (registry == (const lt_log_registry_t *)0) ? 0u : (uint16_t)registry->layout_count;
}

static uint16_t lt_init_count_params_(const lt_param_registry_t *registry)
{
    return (registry == (const lt_param_registry_t *)0) ? 0u : registry->param_count;
}

static uint16_t lt_init_count_cmds_(const lt_cmd_registry_t *registry)
{
    return (registry == (const lt_cmd_registry_t *)0) ? 0u : registry->cmd_count;
}

static lt_status_t lt_init_check_raw_payload_len_(uint16_t payload_len, uint16_t peer_max)
{
    uint16_t raw_len = (uint16_t)(LT_RAW_FRAME_MIN_SIZE + payload_len);
    if ((raw_len < payload_len) || (raw_len > (uint16_t)LT_RAW_FRAME_SIZE)) {
        return LT_STATUS_TOO_LARGE;
    }
    if ((peer_max != 0u) && (raw_len > peer_max)) {
        return LT_STATUS_TOO_LARGE;
    }
    return LT_STATUS_OK;
}

static lt_status_t lt_init_calc_log_layout_payload_len_(const lt_log_layout_desc_t *layout, uint16_t *len_out)
{
    uint16_t i;
    uint16_t len = 4u;

    if ((layout == (const lt_log_layout_desc_t *)0) || (len_out == (uint16_t *)0)) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    if ((layout->field_count > 0u) && (layout->fields == (const lt_log_field_desc_t *)0)) {
        return LT_STATUS_BAD_PAYLOAD;
    }

    for (i = 0u; i < (uint16_t)layout->field_count; ++i) {
        const lt_log_field_desc_t *field = &layout->fields[i];
        uint16_t name_len = lt_str8_wire_len_from_cstr(field->name);
        uint16_t unit_len = lt_str8_wire_len_from_cstr(field->unit);
        if ((name_len == 0u) || (unit_len == 0u)) {
            return LT_STATUS_TOO_LARGE;
        }
        if (!lt_field_id_is_valid(field->field_id) || !lt_value_type_is_valid(field->value_type) || (field->value_ptr == (const void *)0)) {
            return LT_STATUS_BAD_PAYLOAD;
        }
        if ((uint16_t)(0xFFFFu - len) < (uint16_t)(3u + name_len + unit_len)) {
            return LT_STATUS_TOO_LARGE;
        }
        len = (uint16_t)(len + 3u + name_len + unit_len);
    }

    *len_out = len;
    return LT_STATUS_OK;
}

static lt_status_t lt_init_calc_param_desc_payload_len_(const lt_param_registry_t *registry, uint16_t *len_out)
{
    uint16_t i;
    uint16_t len = 2u;

    if (len_out == (uint16_t *)0) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    if (registry == (const lt_param_registry_t *)0) {
        *len_out = len;
        return LT_STATUS_OK;
    }
    if ((registry->param_count > 0u) && (registry->params == (const lt_param_desc_t *)0)) {
        return LT_STATUS_BAD_PAYLOAD;
    }

    for (i = 0u; i < registry->param_count; ++i) {
        const lt_param_desc_t *param = &registry->params[i];
        uint16_t name_len = lt_str8_wire_len_from_cstr(param->name);
        uint16_t unit_len = lt_str8_wire_len_from_cstr(param->unit);
        if ((name_len == 0u) || (unit_len == 0u)) {
            return LT_STATUS_TOO_LARGE;
        }
        if (!lt_param_id_is_valid(param->param_id) || !lt_value_type_is_valid(param->value_type)) {
            return LT_STATUS_BAD_PAYLOAD;
        }
        if ((uint16_t)(0xFFFFu - len) < (uint16_t)(3u + name_len + unit_len)) {
            return LT_STATUS_TOO_LARGE;
        }
        len = (uint16_t)(len + 3u + name_len + unit_len);
    }

    *len_out = len;
    return LT_STATUS_OK;
}

static lt_status_t lt_init_calc_cmd_desc_payload_len_(const lt_cmd_registry_t *registry, uint16_t *len_out)
{
    uint16_t i;
    uint16_t len = 2u;

    if (len_out == (uint16_t *)0) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    if (registry == (const lt_cmd_registry_t *)0) {
        *len_out = len;
        return LT_STATUS_OK;
    }
    if ((registry->cmd_count > 0u) && (registry->cmds == (const lt_cmd_desc_t *)0)) {
        return LT_STATUS_BAD_PAYLOAD;
    }

    for (i = 0u; i < registry->cmd_count; ++i) {
        const lt_cmd_desc_t *cmd = &registry->cmds[i];
        uint16_t name_len = lt_str8_wire_len_from_cstr(cmd->name);
        if (name_len == 0u) {
            return LT_STATUS_TOO_LARGE;
        }
        if (!lt_cmd_id_is_valid(cmd->cmd_id) || ((cmd->cmd_flags & (uint8_t)~LT_CMD_FLAG_HOST_TO_MCU) != 0u) || (cmd->callback == (lt_cmd_callback_t)0)) {
            return LT_STATUS_BAD_PAYLOAD;
        }
        if ((uint16_t)(0xFFFFu - len) < (uint16_t)(3u + name_len)) {
            return LT_STATUS_TOO_LARGE;
        }
        len = (uint16_t)(len + 3u + name_len);
    }

    *len_out = len;
    return LT_STATUS_OK;
}

static lt_status_t lt_init_calc_register_begin_payload_len_(uint16_t *len_out)
{
    const lt_config_t *config = lt_state_config();
    uint16_t name_len;
    if ((len_out == (uint16_t *)0) || (config == (const lt_config_t *)0)) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    name_len = lt_str8_wire_len_from_cstr(config->device_name);
    if (name_len == 0u) {
        return LT_STATUS_TOO_LARGE;
    }
    *len_out = (uint16_t)(14u + name_len);
    return LT_STATUS_OK;
}

static lt_status_t lt_init_validate_registries_(uint16_t peer_max)
{
    const lt_log_registry_t *log_registry = (const lt_log_registry_t *)lt_state_log_registry();
    const lt_param_registry_t *param_registry = (const lt_param_registry_t *)lt_state_param_registry();
    const lt_cmd_registry_t *cmd_registry = (const lt_cmd_registry_t *)lt_state_cmd_registry();
    uint16_t i;
    uint16_t j;
    uint16_t len;
    lt_status_t st;

    st = lt_init_calc_register_begin_payload_len_(&len);
    if ((st != LT_STATUS_OK) || (lt_init_check_raw_payload_len_(len, peer_max) != LT_STATUS_OK)) {
        return (st != LT_STATUS_OK) ? st : LT_STATUS_TOO_LARGE;
    }

    if (log_registry != (const lt_log_registry_t *)0) {
        if ((log_registry->layout_count > 0u) && (log_registry->layouts == (const lt_log_layout_desc_t *)0)) {
            return LT_STATUS_BAD_PAYLOAD;
        }
        for (i = 0u; i < (uint16_t)log_registry->layout_count; ++i) {
            const lt_log_layout_desc_t *layout = &log_registry->layouts[i];
            if (!lt_layout_id_is_valid(layout->layout_id)) {
                return LT_STATUS_BAD_PAYLOAD;
            }
            for (j = (uint16_t)(i + 1u); j < (uint16_t)log_registry->layout_count; ++j) {
                if (layout->layout_id == log_registry->layouts[j].layout_id) {
                    return LT_STATUS_CONFLICT;
                }
            }
            if ((layout->field_count > 0u) && (layout->fields == (const lt_log_field_desc_t *)0)) {
                return LT_STATUS_BAD_PAYLOAD;
            }
            for (j = 0u; j < (uint16_t)layout->field_count; ++j) {
                uint16_t k;
                if (!lt_field_id_is_valid(layout->fields[j].field_id)) {
                    return LT_STATUS_BAD_PAYLOAD;
                }
                for (k = (uint16_t)(j + 1u); k < (uint16_t)layout->field_count; ++k) {
                    if (layout->fields[j].field_id == layout->fields[k].field_id) {
                        return LT_STATUS_CONFLICT;
                    }
                }
            }
            st = lt_init_calc_log_layout_payload_len_(layout, &len);
            if ((st != LT_STATUS_OK) || (lt_init_check_raw_payload_len_(len, peer_max) != LT_STATUS_OK)) {
                return (st != LT_STATUS_OK) ? st : LT_STATUS_TOO_LARGE;
            }
        }
    }

    if (param_registry != (const lt_param_registry_t *)0) {
        if ((param_registry->param_count > 0u) && (param_registry->params == (const lt_param_desc_t *)0)) {
            return LT_STATUS_BAD_PAYLOAD;
        }
        for (i = 0u; i < param_registry->param_count; ++i) {
            if (!lt_param_id_is_valid(param_registry->params[i].param_id)) {
                return LT_STATUS_BAD_PAYLOAD;
            }
            for (j = (uint16_t)(i + 1u); j < param_registry->param_count; ++j) {
                if (param_registry->params[i].param_id == param_registry->params[j].param_id) {
                    return LT_STATUS_CONFLICT;
                }
            }
        }
        st = lt_init_calc_param_desc_payload_len_(param_registry, &len);
        if ((st != LT_STATUS_OK) || ((param_registry->param_count > 0u) && (lt_init_check_raw_payload_len_(len, peer_max) != LT_STATUS_OK))) {
            return (st != LT_STATUS_OK) ? st : LT_STATUS_TOO_LARGE;
        }
    }

    if (cmd_registry != (const lt_cmd_registry_t *)0) {
        if ((cmd_registry->cmd_count > 0u) && (cmd_registry->cmds == (const lt_cmd_desc_t *)0)) {
            return LT_STATUS_BAD_PAYLOAD;
        }
        for (i = 0u; i < cmd_registry->cmd_count; ++i) {
            if (!lt_cmd_id_is_valid(cmd_registry->cmds[i].cmd_id)) {
                return LT_STATUS_BAD_PAYLOAD;
            }
            for (j = (uint16_t)(i + 1u); j < cmd_registry->cmd_count; ++j) {
                if (cmd_registry->cmds[i].cmd_id == cmd_registry->cmds[j].cmd_id) {
                    return LT_STATUS_CONFLICT;
                }
            }
        }
        st = lt_init_calc_cmd_desc_payload_len_(cmd_registry, &len);
        if ((st != LT_STATUS_OK) || ((cmd_registry->cmd_count > 0u) && (lt_init_check_raw_payload_len_(len, peer_max) != LT_STATUS_OK))) {
            return (st != LT_STATUS_OK) ? st : LT_STATUS_TOO_LARGE;
        }
    }

    return LT_STATUS_OK;
}

static lt_status_t lt_init_enqueue_register_begin_(uint32_t enabled_features)
{
    const lt_config_t *config = lt_state_config();
    const lt_log_registry_t *log_registry = (const lt_log_registry_t *)lt_state_log_registry();
    const lt_param_registry_t *param_registry = (const lt_param_registry_t *)lt_state_param_registry();
    const lt_cmd_registry_t *cmd_registry = (const lt_cmd_registry_t *)lt_state_cmd_registry();
    uint8_t payload[32u + 255u];
    lt_writer_t w;
    lt_status_t st;

    lt_writer_init(&w, payload, (uint16_t)sizeof(payload));
    st = lt_write_u8(&w, (uint8_t)LT_PROTO_MAJOR);
    if (st != LT_STATUS_OK) { return st; }
    st = lt_write_u8(&w, (uint8_t)LT_PROTO_MINOR);
    if (st != LT_STATUS_OK) { return st; }
    st = lt_write_u8(&w, (uint8_t)LT_PROTO_PATCH);
    if (st != LT_STATUS_OK) { return st; }
    st = lt_write_u16_le(&w, (uint16_t)LT_RAW_FRAME_SIZE);
    if (st != LT_STATUS_OK) { return st; }
    st = lt_write_u32_le(&w, enabled_features);
    if (st != LT_STATUS_OK) { return st; }
    st = lt_write_u8(&w, (uint8_t)lt_init_count_log_layouts_(log_registry));
    if (st != LT_STATUS_OK) { return st; }
    st = lt_write_u16_le(&w, lt_init_count_params_(param_registry));
    if (st != LT_STATUS_OK) { return st; }
    st = lt_write_u16_le(&w, lt_init_count_cmds_(cmd_registry));
    if (st != LT_STATUS_OK) { return st; }
    st = lt_write_str8(&w, config->device_name);
    if (st != LT_STATUS_OK) { return st; }

    return lt_tx_enqueue_frame((uint8_t)LT_TYPE_REGISTER_BEGIN, payload, w.pos);
}

static lt_status_t lt_init_enqueue_log_layout_(const lt_log_layout_desc_t *layout)
{
    uint8_t payload[LT_RAW_FRAME_SIZE - LT_RAW_FRAME_MIN_SIZE];
    lt_writer_t w;
    lt_status_t st;
    uint16_t i;

    lt_writer_init(&w, payload, (uint16_t)sizeof(payload));
    st = lt_write_u8(&w, layout->layout_id);
    if (st != LT_STATUS_OK) { return st; }
    st = lt_write_u16_le(&w, layout->default_period_ms);
    if (st != LT_STATUS_OK) { return st; }
    st = lt_write_u8(&w, layout->field_count);
    if (st != LT_STATUS_OK) { return st; }

    for (i = 0u; i < (uint16_t)layout->field_count; ++i) {
        const lt_log_field_desc_t *field = &layout->fields[i];
        st = lt_write_u16_le(&w, field->field_id);
        if (st != LT_STATUS_OK) { return st; }
        st = lt_write_u8(&w, field->value_type);
        if (st != LT_STATUS_OK) { return st; }
        st = lt_write_str8(&w, field->name);
        if (st != LT_STATUS_OK) { return st; }
        st = lt_write_str8(&w, field->unit);
        if (st != LT_STATUS_OK) { return st; }
    }

    return lt_tx_enqueue_frame((uint8_t)LT_TYPE_REGISTER_LOG_LAYOUT, payload, w.pos);
}

static lt_status_t lt_init_enqueue_param_desc_(const lt_param_registry_t *registry)
{
    uint8_t payload[LT_RAW_FRAME_SIZE - LT_RAW_FRAME_MIN_SIZE];
    lt_writer_t w;
    lt_status_t st;
    uint16_t i;

    lt_writer_init(&w, payload, (uint16_t)sizeof(payload));
    st = lt_write_u16_le(&w, lt_init_count_params_(registry));
    if (st != LT_STATUS_OK) { return st; }
    if (registry != (const lt_param_registry_t *)0) {
        for (i = 0u; i < registry->param_count; ++i) {
            const lt_param_desc_t *param = &registry->params[i];
            st = lt_write_u16_le(&w, param->param_id);
            if (st != LT_STATUS_OK) { return st; }
            st = lt_write_u8(&w, param->value_type);
            if (st != LT_STATUS_OK) { return st; }
            st = lt_write_str8(&w, param->name);
            if (st != LT_STATUS_OK) { return st; }
            st = lt_write_str8(&w, param->unit);
            if (st != LT_STATUS_OK) { return st; }
        }
    }
    return lt_tx_enqueue_frame((uint8_t)LT_TYPE_REGISTER_PARAM_DESC, payload, w.pos);
}

static lt_status_t lt_init_enqueue_cmd_desc_(const lt_cmd_registry_t *registry)
{
    uint8_t payload[LT_RAW_FRAME_SIZE - LT_RAW_FRAME_MIN_SIZE];
    lt_writer_t w;
    lt_status_t st;
    uint16_t i;

    lt_writer_init(&w, payload, (uint16_t)sizeof(payload));
    st = lt_write_u16_le(&w, lt_init_count_cmds_(registry));
    if (st != LT_STATUS_OK) { return st; }
    if (registry != (const lt_cmd_registry_t *)0) {
        for (i = 0u; i < registry->cmd_count; ++i) {
            const lt_cmd_desc_t *cmd = &registry->cmds[i];
            st = lt_write_u16_le(&w, cmd->cmd_id);
            if (st != LT_STATUS_OK) { return st; }
            st = lt_write_u8(&w, (uint8_t)(cmd->cmd_flags & (uint8_t)LT_CMD_FLAG_HOST_TO_MCU));
            if (st != LT_STATUS_OK) { return st; }
            st = lt_write_str8(&w, cmd->name);
            if (st != LT_STATUS_OK) { return st; }
        }
    }
    return lt_tx_enqueue_frame((uint8_t)LT_TYPE_REGISTER_CMD_DESC, payload, w.pos);
}

static lt_status_t lt_init_enqueue_register_sequence_(uint32_t enabled_features)
{
    const lt_log_registry_t *log_registry = (const lt_log_registry_t *)lt_state_log_registry();
    const lt_param_registry_t *param_registry = (const lt_param_registry_t *)lt_state_param_registry();
    const lt_cmd_registry_t *cmd_registry = (const lt_cmd_registry_t *)lt_state_cmd_registry();
    uint8_t expected = 2u;
    uint16_t i;
    lt_tx_checkpoint_t checkpoint;
    lt_status_t st;

    expected = (uint8_t)(expected + (uint8_t)lt_init_count_log_layouts_(log_registry));
    if (lt_init_count_params_(param_registry) > 0u) {
        expected = (uint8_t)(expected + 1u);
    }
    if (lt_init_count_cmds_(cmd_registry) > 0u) {
        expected = (uint8_t)(expected + 1u);
    }

    st = lt_tx_begin_atomic(expected, &checkpoint);
    if (st != LT_STATUS_OK) {
        return st;
    }

    st = lt_init_enqueue_register_begin_(enabled_features);
    if (st == LT_STATUS_OK) {
        for (i = 0u; (log_registry != (const lt_log_registry_t *)0) && (i < (uint16_t)log_registry->layout_count); ++i) {
            st = lt_init_enqueue_log_layout_(&log_registry->layouts[i]);
            if (st != LT_STATUS_OK) {
                break;
            }
        }
    }
    if ((st == LT_STATUS_OK) && (lt_init_count_params_(param_registry) > 0u)) {
        st = lt_init_enqueue_param_desc_(param_registry);
    }
    if ((st == LT_STATUS_OK) && (lt_init_count_cmds_(cmd_registry) > 0u)) {
        st = lt_init_enqueue_cmd_desc_(cmd_registry);
    }
    if (st == LT_STATUS_OK) {
        st = lt_tx_enqueue_frame((uint8_t)LT_TYPE_REGISTER_END, (const uint8_t *)0, 0u);
    }

    if (st != LT_STATUS_OK) {
        lt_tx_rollback_atomic(&checkpoint);
        return st;
    }
    lt_tx_commit_atomic(&checkpoint);
    return LT_STATUS_OK;
}

LT_API lt_status_t lt_init(const lt_config_t *config)
{
    if ((config == (const lt_config_t *)0) || (config->send == (lt_send_fn_t)0) || (config->next_frame_id == (lt_next_frame_id_fn_t)0)) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    if (!lt_str8_is_valid_cstr(config->device_name)) {
        return LT_STATUS_TOO_LARGE;
    }

    lt_state_reset();
    lt_tx_reset();
    lt_rx_reset();
    lt_params_reset();
    lt_cmd_reset();
    lt_telemetry_reset();
    lt_state_set_config(config);
    lt_state_set(LT_STATE_REGISTERING);
    return LT_STATUS_OK;
}

LT_API lt_status_t lt_register_log(const lt_log_registry_t *registry)
{
    if (lt_state_get() != LT_STATE_REGISTERING) {
        return LT_STATUS_INVALID_STATE;
    }
    if (lt_state_log_registry() != (const struct lt_log_registry_t *)0) {
        return LT_STATUS_CONFLICT;
    }
    lt_state_set_log_registry((const struct lt_log_registry_t *)registry);
    return LT_STATUS_OK;
}

LT_API lt_status_t lt_register_param(const lt_param_registry_t *registry)
{
    if (lt_state_get() != LT_STATE_REGISTERING) {
        return LT_STATUS_INVALID_STATE;
    }
    if (lt_state_param_registry() != (const struct lt_param_registry_t *)0) {
        return LT_STATUS_CONFLICT;
    }
    lt_state_set_param_registry((const struct lt_param_registry_t *)registry);
    return LT_STATUS_OK;
}

LT_API lt_status_t lt_register_cmd(const lt_cmd_registry_t *registry)
{
    if (lt_state_get() != LT_STATE_REGISTERING) {
        return LT_STATUS_INVALID_STATE;
    }
    if (lt_state_cmd_registry() != (const struct lt_cmd_registry_t *)0) {
        return LT_STATUS_CONFLICT;
    }
    lt_state_set_cmd_registry((const struct lt_cmd_registry_t *)registry);
    return LT_STATUS_OK;
}

LT_API lt_status_t lt_register_complete(void)
{
    lt_status_t st;
    if (lt_state_get() != LT_STATE_REGISTERING) {
        return LT_STATUS_INVALID_STATE;
    }
    st = lt_init_validate_registries_((uint16_t)LT_RAW_FRAME_SIZE);
    if (st != LT_STATUS_OK) {
        lt_state_set(LT_STATE_ERROR);
        return st;
    }
    lt_state_set(LT_STATE_WAIT_DISCOVER);
    return LT_STATUS_OK;
}

LT_API lt_status_t lt_init_handle_discover(lt_frame_id_t request_frame_id, const uint8_t *payload, uint16_t payload_len)
{
    lt_reader_t r;
    uint8_t host_major;
    uint8_t host_minor;
    uint8_t host_patch;
    uint16_t host_max_decoded_frame;
    uint32_t requested_features;
    uint16_t response_timeout_ms;
    lt_str8_view_t host_name;
    uint16_t peer_max;
    uint32_t enabled_features;
    const lt_config_t *config;
    lt_status_t st;

    (void)request_frame_id;

    if ((payload == (const uint8_t *)0) && (payload_len > 0u)) {
        (void)lt_runtime_send_status(LT_STATUS_BAD_PAYLOAD);
        return LT_STATUS_BAD_PAYLOAD;
    }
    if ((lt_state_get() != LT_STATE_WAIT_DISCOVER) && (lt_state_get() != LT_STATE_CONNECTED)) {
        (void)lt_runtime_send_status(LT_STATUS_NOT_READY);
        return LT_STATUS_NOT_READY;
    }

    lt_reader_init(&r, payload, payload_len);
    st = lt_read_u8(&r, &host_major);
    if (st == LT_STATUS_OK) { st = lt_read_u8(&r, &host_minor); }
    if (st == LT_STATUS_OK) { st = lt_read_u8(&r, &host_patch); }
    if (st == LT_STATUS_OK) { st = lt_read_u16_le(&r, &host_max_decoded_frame); }
    if (st == LT_STATUS_OK) { st = lt_read_u32_le(&r, &requested_features); }
    if (st == LT_STATUS_OK) { st = lt_read_u16_le(&r, &response_timeout_ms); }
    if (st == LT_STATUS_OK) { st = lt_read_str8(&r, &host_name); }
    if ((st != LT_STATUS_OK) || (lt_reader_remaining(&r) != 0u)) {
        (void)lt_runtime_send_status(LT_STATUS_BAD_PAYLOAD);
        return LT_STATUS_BAD_PAYLOAD;
    }

    if ((host_major != (uint8_t)LT_PROTO_MAJOR) || (host_minor != (uint8_t)LT_PROTO_MINOR) || (host_patch != (uint8_t)LT_PROTO_PATCH)) {
        (void)lt_runtime_send_status(LT_STATUS_VERSION_UNSUPPORTED);
        return LT_STATUS_VERSION_UNSUPPORTED;
    }
    if (host_max_decoded_frame < (uint16_t)LT_RAW_FRAME_MIN_SIZE) {
        (void)lt_runtime_send_status(LT_STATUS_BAD_PAYLOAD);
        return LT_STATUS_BAD_PAYLOAD;
    }

    peer_max = lt_min_u16(host_max_decoded_frame, (uint16_t)LT_RAW_FRAME_SIZE);
    config = lt_state_config();
    if (config == (const lt_config_t *)0) {
        (void)lt_runtime_send_status(LT_STATUS_NOT_READY);
        return LT_STATUS_NOT_READY;
    }
    enabled_features = requested_features & config->mcu_supported_features;

    st = lt_init_validate_registries_(peer_max);
    if (st != LT_STATUS_OK) {
        (void)lt_runtime_send_status(st);
        return st;
    }

    lt_state_set_negotiated(enabled_features, peer_max, response_timeout_ms);
    st = lt_init_enqueue_register_sequence_(enabled_features);
    if (st != LT_STATUS_OK) {
        (void)lt_runtime_send_status((st == LT_STATUS_BUSY) ? LT_STATUS_BUSY : st);
        return st;
    }

    lt_state_set(LT_STATE_CONNECTED);
    return LT_STATUS_OK;
}

#endif /* LITETUNE_IMPLEMENTATION */

#endif /* LT_INIT_H */
