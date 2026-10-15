#ifndef LT_TELEMETRY_H
#define LT_TELEMETRY_H

#include "lt_config.h"
#include "lt_common.h"
#include "lt_state.h"
#include "lt_utils.h"
#include "lt_tx.h"
#include "lt_registry.h"

#include <stdint.h>
#include <stddef.h>


#ifdef __cplusplus
extern "C" {
#endif

LT_API lt_status_t lt_log_report(uint8_t layout_id);
LT_API void lt_telemetry_reset(void);

#ifdef __cplusplus
}
#endif

#ifdef LITETUNE_IMPLEMENTATION

#include <string.h>

static uint16_t lt_telemetry_sample_seq_[256];

static const lt_log_layout_desc_t *lt_telemetry_find_layout_(lt_layout_id_t layout_id)
{
    const lt_log_registry_t *registry = (const lt_log_registry_t *)lt_state_log_registry();
    uint16_t i;
    if (registry == (const lt_log_registry_t *)0) {
        return (const lt_log_layout_desc_t *)0;
    }
    for (i = 0u; i < (uint16_t)registry->layout_count; ++i) {
        if (registry->layouts[i].layout_id == layout_id) {
            return &registry->layouts[i];
        }
    }
    return (const lt_log_layout_desc_t *)0;
}

LT_API void lt_telemetry_reset(void)
{
    (void)memset(lt_telemetry_sample_seq_, 0, sizeof(lt_telemetry_sample_seq_));
}

LT_API lt_status_t lt_log_report(uint8_t layout_id)
{
    const lt_log_layout_desc_t *layout;
    uint8_t payload[LT_RAW_FRAME_SIZE - LT_RAW_FRAME_MIN_SIZE];
    lt_writer_t w;
    lt_status_t st;
    uint16_t i;
    uint16_t seq;

    if (lt_state_get() != LT_STATE_CONNECTED) {
        return LT_STATUS_INVALID_STATE;
    }
    if (lt_state_feature_enabled((uint32_t)LT_FEATURE_LOG_PACKED) == 0u) {
        return LT_STATUS_UNSUPPORTED;
    }

    layout = lt_telemetry_find_layout_((lt_layout_id_t)layout_id);
    if (layout == (const lt_log_layout_desc_t *)0) {
        return LT_STATUS_NOT_FOUND;
    }
    if ((layout->field_count > 0u) && (layout->fields == (const lt_log_field_desc_t *)0)) {
        return LT_STATUS_BAD_PAYLOAD;
    }

    seq = lt_telemetry_sample_seq_[layout_id];
    lt_writer_init(&w, payload, (uint16_t)sizeof(payload));
    st = lt_write_u8(&w, layout_id);
    if (st != LT_STATUS_OK) {
        return st;
    }
    st = lt_write_u16_le(&w, seq);
    if (st != LT_STATUS_OK) {
        return st;
    }

    for (i = 0u; i < (uint16_t)layout->field_count; ++i) {
        const lt_log_field_desc_t *field = &layout->fields[i];
        if ((field->value_ptr == (const void *)0) || !lt_value_type_is_valid(field->value_type)) {
            return LT_STATUS_BAD_PAYLOAD;
        }
        st = lt_write_value(&w, field->value_type, field->value_ptr);
        if (st != LT_STATUS_OK) {
            return st;
        }
    }

    st = lt_tx_enqueue_frame((uint8_t)LT_TYPE_LOG_REPORT, payload, w.pos);
    if (st == LT_STATUS_OK) {
        lt_telemetry_sample_seq_[layout_id] = (uint16_t)(seq + 1u);
    }
    return st;
}

#endif /* LITETUNE_IMPLEMENTATION */

#endif /* LT_TELEMETRY_H */
