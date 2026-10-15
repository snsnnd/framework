#ifndef LT_REGISTRY_H
#define LT_REGISTRY_H

#include "lt_config.h"
#include "lt_common.h"
#include "lt_utils.h"

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define LT_PARAM_FLAG_READABLE        (1u << 0)
#define LT_PARAM_FLAG_WRITABLE        (1u << 1)
#define LT_PARAM_FLAG_HAS_MIN         (1u << 2)
#define LT_PARAM_FLAG_HAS_MAX         (1u << 3)
#define LT_PARAM_FLAG_HAS_DEFAULT     (1u << 4)
#define LT_PARAM_FLAG_REBOOT_REQUIRED (1u << 5)
#define LT_PARAM_FLAG_USER0           (1u << 6)
#define LT_PARAM_FLAG_USER1           (1u << 7)

#define LT_CMD_FLAG_HOST_TO_MCU (1u << 0)
#define LT_CMD_FLAG_WIRE_MASK   LT_CMD_FLAG_HOST_TO_MCU

typedef lt_status_t (*lt_cmd_callback_t)(
    const uint8_t *req_payload,
    uint16_t req_len,
    uint8_t *resp_payload,
    uint16_t resp_cap,
    uint16_t *resp_len,
    void *user_ctx
);

typedef struct lt_log_field_desc_t {
    lt_field_id_t field_id;
    uint8_t value_type;
    const char *name;
    const char *unit;
    const void *value_ptr;
} lt_log_field_desc_t;

typedef struct lt_log_layout_desc_t {
    lt_layout_id_t layout_id;
    uint16_t default_period_ms;
    uint8_t field_count;
    const lt_log_field_desc_t *fields;
} lt_log_layout_desc_t;

typedef struct lt_log_registry_t {
    uint8_t layout_count;
    const lt_log_layout_desc_t *layouts;
} lt_log_registry_t;

typedef struct lt_param_desc_t {
    lt_param_id_t param_id;
    uint8_t value_type;
    const char *name;
    const char *unit;
    void *value_ptr;
    uint8_t flags;
    const void *min_value_ptr;
    const void *max_value_ptr;
    const void *default_value_ptr;
} lt_param_desc_t;

typedef struct lt_param_registry_t {
    uint16_t param_count;
    const lt_param_desc_t *params;
} lt_param_registry_t;

typedef struct lt_cmd_desc_t {
    lt_cmd_id_t cmd_id;
    uint8_t cmd_flags;
    const char *name;
    lt_cmd_callback_t callback;
    void *user_ctx;
} lt_cmd_desc_t;

typedef struct lt_cmd_registry_t {
    uint16_t cmd_count;
    const lt_cmd_desc_t *cmds;
} lt_cmd_registry_t;

LT_API lt_status_t lt_registry_validate_log(const lt_log_registry_t *registry);
LT_API lt_status_t lt_registry_validate_param(const lt_param_registry_t *registry);
LT_API lt_status_t lt_registry_validate_cmd(const lt_cmd_registry_t *registry);

LT_API lt_status_t lt_registry_calc_register_begin_payload_len(const lt_config_t *config, uint16_t *len_out);
LT_API lt_status_t lt_registry_calc_log_layout_payload_len(const lt_log_layout_desc_t *layout, uint16_t *len_out);
LT_API lt_status_t lt_registry_calc_param_desc_payload_len(const lt_param_registry_t *registry, uint16_t *len_out);
LT_API lt_status_t lt_registry_calc_cmd_desc_payload_len(const lt_cmd_registry_t *registry, uint16_t *len_out);


LT_API uint16_t lt_registry_log_layout_count(const lt_log_registry_t *registry);
LT_API uint16_t lt_registry_param_count(const lt_param_registry_t *registry);
LT_API uint16_t lt_registry_cmd_count(const lt_cmd_registry_t *registry);

#ifdef __cplusplus
}
#endif

#ifdef LITETUNE_IMPLEMENTATION

static lt_status_t lt_registry_add_u16_(uint16_t *acc, uint16_t add)
{
    if (acc == (uint16_t *)0) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    if (*acc > (uint16_t)(65535u - add)) {
        return LT_STATUS_TOO_LARGE;
    }
    *acc = (uint16_t)(*acc + add);
    return LT_STATUS_OK;
}

static lt_status_t lt_registry_add_str8_cstr_len_(uint16_t *acc, const char *str)
{
    uint8_t len = 0u;
    lt_status_t st = lt_str8_cstr_len(str, &len);
    if (st != LT_STATUS_OK) {
        return st;
    }
    return lt_registry_add_u16_(acc, (uint16_t)(1u + (uint16_t)len));
}

LT_API uint16_t lt_registry_log_layout_count(const lt_log_registry_t *registry)
{
    return (registry == (const lt_log_registry_t *)0) ? 0u : (uint16_t)registry->layout_count;
}

LT_API uint16_t lt_registry_param_count(const lt_param_registry_t *registry)
{
    return (registry == (const lt_param_registry_t *)0) ? 0u : registry->param_count;
}

LT_API uint16_t lt_registry_cmd_count(const lt_cmd_registry_t *registry)
{
    return (registry == (const lt_cmd_registry_t *)0) ? 0u : registry->cmd_count;
}

LT_API lt_status_t lt_registry_validate_log(const lt_log_registry_t *registry)
{
    uint16_t i;
    uint16_t j;
    uint16_t f;
    uint16_t g;

    if (registry == (const lt_log_registry_t *)0) {
        return LT_STATUS_OK;
    }
    if ((registry->layout_count > 0u) && (registry->layouts == (const lt_log_layout_desc_t *)0)) {
        return LT_STATUS_BAD_PAYLOAD;
    }

    for (i = 0u; i < (uint16_t)registry->layout_count; ++i) {
        const lt_log_layout_desc_t *layout = &registry->layouts[i];
        if (!lt_layout_id_is_valid(layout->layout_id)) {
            return LT_STATUS_BAD_PAYLOAD;
        }
        if ((layout->field_count > 0u) && (layout->fields == (const lt_log_field_desc_t *)0)) {
            return LT_STATUS_BAD_PAYLOAD;
        }
        for (j = (uint16_t)(i + 1u); j < (uint16_t)registry->layout_count; ++j) {
            if (layout->layout_id == registry->layouts[j].layout_id) {
                return LT_STATUS_CONFLICT;
            }
        }
        for (f = 0u; f < (uint16_t)layout->field_count; ++f) {
            const lt_log_field_desc_t *field = &layout->fields[f];
            if (!lt_field_id_is_valid(field->field_id)) {
                return LT_STATUS_BAD_PAYLOAD;
            }
            if (!lt_value_type_is_valid(field->value_type)) {
                return LT_STATUS_BAD_PAYLOAD;
            }
            if (field->name == (const char *)0) {
                return LT_STATUS_BAD_PAYLOAD;
            }
            if (!lt_str8_is_valid_cstr(field->name)) {
                return LT_STATUS_TOO_LARGE;
            }
            if (!lt_str8_is_valid_cstr(field->unit)) {
                return LT_STATUS_TOO_LARGE;
            }
            if (field->value_ptr == (const void *)0) {
                return LT_STATUS_BAD_PAYLOAD;
            }
            for (g = (uint16_t)(f + 1u); g < (uint16_t)layout->field_count; ++g) {
                if (field->field_id == layout->fields[g].field_id) {
                    return LT_STATUS_CONFLICT;
                }
            }
        }
    }

    return LT_STATUS_OK;
}

LT_API lt_status_t lt_registry_validate_param(const lt_param_registry_t *registry)
{
    uint16_t i;
    uint16_t j;

    if (registry == (const lt_param_registry_t *)0) {
        return LT_STATUS_OK;
    }
    if ((registry->param_count > 0u) && (registry->params == (const lt_param_desc_t *)0)) {
        return LT_STATUS_BAD_PAYLOAD;
    }

    for (i = 0u; i < registry->param_count; ++i) {
        const lt_param_desc_t *param = &registry->params[i];
        if (!lt_param_id_is_valid(param->param_id)) {
            return LT_STATUS_BAD_PAYLOAD;
        }
        if (!lt_value_type_is_valid(param->value_type)) {
            return LT_STATUS_BAD_PAYLOAD;
        }
        if (param->name == (const char *)0) {
            return LT_STATUS_BAD_PAYLOAD;
        }
        if (!lt_str8_is_valid_cstr(param->name)) {
            return LT_STATUS_TOO_LARGE;
        }
        if (!lt_str8_is_valid_cstr(param->unit)) {
            return LT_STATUS_TOO_LARGE;
        }
        if (param->value_ptr == (void *)0) {
            return LT_STATUS_BAD_PAYLOAD;
        }
        if ((lt_value_type_is_variable(param->value_type) != 0u) &&
            ((param->flags & (uint8_t)(LT_PARAM_FLAG_HAS_MIN | LT_PARAM_FLAG_HAS_MAX | LT_PARAM_FLAG_HAS_DEFAULT)) != 0u)) {
            return LT_STATUS_UNSUPPORTED;
        }
        for (j = (uint16_t)(i + 1u); j < registry->param_count; ++j) {
            if (param->param_id == registry->params[j].param_id) {
                return LT_STATUS_CONFLICT;
            }
        }
    }

    return LT_STATUS_OK;
}

LT_API lt_status_t lt_registry_validate_cmd(const lt_cmd_registry_t *registry)
{
    uint16_t i;
    uint16_t j;

    if (registry == (const lt_cmd_registry_t *)0) {
        return LT_STATUS_OK;
    }
    if ((registry->cmd_count > 0u) && (registry->cmds == (const lt_cmd_desc_t *)0)) {
        return LT_STATUS_BAD_PAYLOAD;
    }

    for (i = 0u; i < registry->cmd_count; ++i) {
        const lt_cmd_desc_t *cmd = &registry->cmds[i];
        if (!lt_cmd_id_is_valid(cmd->cmd_id)) {
            return LT_STATUS_BAD_PAYLOAD;
        }
        if (cmd->name == (const char *)0) {
            return LT_STATUS_BAD_PAYLOAD;
        }
        if (!lt_str8_is_valid_cstr(cmd->name)) {
            return LT_STATUS_TOO_LARGE;
        }
        if (cmd->callback == (lt_cmd_callback_t)0) {
            return LT_STATUS_BAD_PAYLOAD;
        }
        if ((cmd->cmd_flags & (uint8_t)~LT_CMD_FLAG_WIRE_MASK) != 0u) {
            return LT_STATUS_BAD_PAYLOAD;
        }
        for (j = (uint16_t)(i + 1u); j < registry->cmd_count; ++j) {
            if (cmd->cmd_id == registry->cmds[j].cmd_id) {
                return LT_STATUS_CONFLICT;
            }
        }
    }

    return LT_STATUS_OK;
}

LT_API lt_status_t lt_registry_calc_register_begin_payload_len(const lt_config_t *config, uint16_t *len_out)
{
    uint16_t len = 14u;
    lt_status_t st;

    if (len_out == (uint16_t *)0) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    *len_out = 0u;

    st = lt_registry_add_str8_cstr_len_(&len, (config != (const lt_config_t *)0) ? config->device_name : (const char *)0);
    if (st != LT_STATUS_OK) {
        return st;
    }
    *len_out = len;
    return LT_STATUS_OK;
}

LT_API lt_status_t lt_registry_calc_log_layout_payload_len(const lt_log_layout_desc_t *layout, uint16_t *len_out)
{
    uint16_t len = 4u;
    uint16_t i;
    lt_status_t st;

    if ((layout == (const lt_log_layout_desc_t *)0) || (len_out == (uint16_t *)0)) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    *len_out = 0u;

    if ((layout->field_count > 0u) && (layout->fields == (const lt_log_field_desc_t *)0)) {
        return LT_STATUS_BAD_PAYLOAD;
    }

    for (i = 0u; i < (uint16_t)layout->field_count; ++i) {
        const lt_log_field_desc_t *field = &layout->fields[i];
        st = lt_registry_add_u16_(&len, 3u);
        if (st != LT_STATUS_OK) {
            return st;
        }
        st = lt_registry_add_str8_cstr_len_(&len, field->name);
        if (st != LT_STATUS_OK) {
            return st;
        }
        st = lt_registry_add_str8_cstr_len_(&len, field->unit);
        if (st != LT_STATUS_OK) {
            return st;
        }
    }

    *len_out = len;
    return LT_STATUS_OK;
}

LT_API lt_status_t lt_registry_calc_param_desc_payload_len(const lt_param_registry_t *registry, uint16_t *len_out)
{
    uint16_t len = 2u;
    uint16_t i;
    lt_status_t st;

    if (len_out == (uint16_t *)0) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    *len_out = 0u;
    if (registry == (const lt_param_registry_t *)0) {
        *len_out = len;
        return LT_STATUS_OK;
    }
    if ((registry->param_count > 0u) && (registry->params == (const lt_param_desc_t *)0)) {
        return LT_STATUS_BAD_PAYLOAD;
    }

    for (i = 0u; i < registry->param_count; ++i) {
        const lt_param_desc_t *param = &registry->params[i];
        st = lt_registry_add_u16_(&len, 3u);
        if (st != LT_STATUS_OK) {
            return st;
        }
        st = lt_registry_add_str8_cstr_len_(&len, param->name);
        if (st != LT_STATUS_OK) {
            return st;
        }
        st = lt_registry_add_str8_cstr_len_(&len, param->unit);
        if (st != LT_STATUS_OK) {
            return st;
        }
    }

    *len_out = len;
    return LT_STATUS_OK;
}

LT_API lt_status_t lt_registry_calc_cmd_desc_payload_len(const lt_cmd_registry_t *registry, uint16_t *len_out)
{
    uint16_t len = 2u;
    uint16_t i;
    lt_status_t st;

    if (len_out == (uint16_t *)0) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    *len_out = 0u;
    if (registry == (const lt_cmd_registry_t *)0) {
        *len_out = len;
        return LT_STATUS_OK;
    }
    if ((registry->cmd_count > 0u) && (registry->cmds == (const lt_cmd_desc_t *)0)) {
        return LT_STATUS_BAD_PAYLOAD;
    }

    for (i = 0u; i < registry->cmd_count; ++i) {
        const lt_cmd_desc_t *cmd = &registry->cmds[i];
        st = lt_registry_add_u16_(&len, 3u);
        if (st != LT_STATUS_OK) {
            return st;
        }
        st = lt_registry_add_str8_cstr_len_(&len, cmd->name);
        if (st != LT_STATUS_OK) {
            return st;
        }
    }

    *len_out = len;
    return LT_STATUS_OK;
}

#endif /* LITETUNE_IMPLEMENTATION */

#endif /* LT_REGISTRY_H */
