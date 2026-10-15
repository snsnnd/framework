#ifndef LT_PARAMS_H
#define LT_PARAMS_H

#include "lt_config.h"
#include "lt_common.h"
#include "lt_utils.h"
#include "lt_state.h"
#include "lt_registry.h"
#include "lt_tx.h"

#include <stdint.h>


#ifdef __cplusplus
extern "C" {
#endif

#define LT_PARAM_QUERY_BY_ID 0x00u
#define LT_PARAM_QUERY_ALL   0x01u

#define LT_PARAM_REPORT_RESPONSE_TO_SET    0x00u
#define LT_PARAM_REPORT_RESPONSE_TO_GET    0x01u
#define LT_PARAM_REPORT_CHANGED_EVENT      0x02u
#define LT_PARAM_REPORT_ERROR_ONLY         0x03u

LT_API lt_status_t lt_params_handle_param_set(
    lt_frame_id_t request_frame_id,
    const uint8_t *payload,
    uint16_t payload_len
);

LT_API lt_status_t lt_params_handle_param_get(
    lt_frame_id_t request_frame_id,
    const uint8_t *payload,
    uint16_t payload_len
);

LT_API void lt_params_reset(void);

#ifdef __cplusplus
}
#endif

#ifdef LITETUNE_IMPLEMENTATION

#include <string.h>

typedef struct {
    lt_param_id_t param_id;
    const lt_param_desc_t *desc;
    uint8_t value[LT_PARAM_MAX_VALUE_SIZE];
    lt_status_t item_status;
} lt_params_set_item_t;

static lt_params_set_item_t lt_params_set_items_[LT_PARAM_SET_MAX_ITEMS];
static uint8_t lt_params_report_payload_[LT_RAW_FRAME_SIZE];

static uint16_t lt_params_max_payload_len_(void)
{
    uint16_t raw_max = (uint16_t)LT_RAW_FRAME_SIZE;
    uint16_t peer_max = lt_state_peer_max_decoded_frame();

    if ((peer_max != 0u) && (peer_max < raw_max)) {
        raw_max = peer_max;
    }
    if (raw_max <= (uint16_t)LT_RAW_FRAME_MIN_SIZE) {
        return 0u;
    }
    return (uint16_t)(raw_max - (uint16_t)LT_RAW_FRAME_MIN_SIZE);
}

static const lt_param_desc_t *lt_params_find_param_(lt_param_id_t param_id)
{
    const lt_param_registry_t *registry = lt_state_param_registry();
    uint16_t i;

    if ((registry == (const lt_param_registry_t *)0) ||
        ((registry->param_count > 0u) && (registry->params == (const lt_param_desc_t *)0))) {
        return (const lt_param_desc_t *)0;
    }
    for (i = 0u; i < lt_registry_param_count(registry); ++i) {
        if (registry->params[i].param_id == param_id) {
            return &registry->params[i];
        }
    }
    return (const lt_param_desc_t *)0;
}

static uint8_t lt_params_readable_(const lt_param_desc_t *param)
{
    uint8_t access_flags;
    if (param == (const lt_param_desc_t *)0) {
        return 0u;
    }
    access_flags = (uint8_t)(param->flags & (uint8_t)(LT_PARAM_FLAG_READABLE | LT_PARAM_FLAG_WRITABLE));
    if (access_flags == 0u) {
        return 1u;
    }
    return (uint8_t)((param->flags & (uint8_t)LT_PARAM_FLAG_READABLE) != 0u);
}

static uint8_t lt_params_writable_(const lt_param_desc_t *param)
{
    uint8_t access_flags;
    if (param == (const lt_param_desc_t *)0) {
        return 0u;
    }
    access_flags = (uint8_t)(param->flags & (uint8_t)(LT_PARAM_FLAG_READABLE | LT_PARAM_FLAG_WRITABLE));
    if (access_flags == 0u) {
        return 1u;
    }
    return (uint8_t)((param->flags & (uint8_t)LT_PARAM_FLAG_WRITABLE) != 0u);
}

static uint16_t lt_params_value_storage_size_(uint8_t value_type)
{
    if (value_type == (uint8_t)LT_VALUE_STRING) {
        return (uint16_t)sizeof(lt_str8_view_t);
    }
    if (value_type == (uint8_t)LT_VALUE_BYTES) {
        return (uint16_t)sizeof(lt_bytes8_view_t);
    }
    return lt_value_type_fixed_size(value_type);
}

static lt_status_t lt_params_write_report_header_(
    lt_writer_t *w,
    lt_frame_id_t request_frame_id,
    uint8_t report_kind,
    lt_status_t overall_status,
    uint16_t item_count
)
{
    lt_status_t st;

    st = lt_write_u64_le(w, request_frame_id);
    if (st != LT_STATUS_OK) {
        return st;
    }
    st = lt_write_u8(w, report_kind);
    if (st != LT_STATUS_OK) {
        return st;
    }
    st = lt_write_u8(w, (uint8_t)overall_status);
    if (st != LT_STATUS_OK) {
        return st;
    }
    return lt_write_u16_le(w, item_count);
}

static lt_status_t lt_params_enqueue_error_report_(lt_frame_id_t request_frame_id, lt_status_t status)
{
    lt_writer_t w;
    lt_status_t st;
    uint16_t cap = lt_params_max_payload_len_();

    lt_writer_init(&w, lt_params_report_payload_, cap);
    st = lt_params_write_report_header_(&w, request_frame_id, (uint8_t)LT_PARAM_REPORT_ERROR_ONLY, status, 0u);
    if (st != LT_STATUS_OK) {
        return st;
    }
    return lt_tx_enqueue_frame((uint8_t)LT_TYPE_PARAM_REPORT, lt_params_report_payload_, w.pos);
}

static lt_status_t lt_params_write_report_item_current_(
    lt_writer_t *w,
    const lt_param_desc_t *param,
    lt_status_t item_status
)
{
    lt_status_t st;

    if (param == (const lt_param_desc_t *)0) {
        return LT_STATUS_NOT_FOUND;
    }
    st = lt_write_u16_le(w, param->param_id);
    if (st != LT_STATUS_OK) {
        return st;
    }
    st = lt_write_u8(w, (uint8_t)item_status);
    if (st != LT_STATUS_OK) {
        return st;
    }
    return lt_write_value(w, param->value_type, param->value_ptr);
}

static lt_status_t lt_params_write_report_item_value_(
    lt_writer_t *w,
    const lt_param_desc_t *param,
    lt_status_t item_status,
    const void *value_ptr
)
{
    lt_status_t st;

    if ((param == (const lt_param_desc_t *)0) || (value_ptr == (const void *)0)) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    st = lt_write_u16_le(w, param->param_id);
    if (st != LT_STATUS_OK) {
        return st;
    }
    st = lt_write_u8(w, (uint8_t)item_status);
    if (st != LT_STATUS_OK) {
        return st;
    }
    return lt_write_value(w, param->value_type, value_ptr);
}

static lt_status_t lt_params_enqueue_set_items_report_(
    lt_frame_id_t request_frame_id,
    lt_status_t overall_status,
    const lt_params_set_item_t *items,
    uint8_t count,
    uint8_t use_requested_values
)
{
    lt_writer_t w;
    lt_status_t st;
    uint8_t i;
    uint16_t cap = lt_params_max_payload_len_();

    lt_writer_init(&w, lt_params_report_payload_, cap);
    st = lt_params_write_report_header_(&w, request_frame_id, (uint8_t)LT_PARAM_REPORT_RESPONSE_TO_SET, overall_status, (uint16_t)count);
    if (st != LT_STATUS_OK) {
        return st;
    }

    for (i = 0u; i < count; ++i) {
        if ((items[i].desc == (const lt_param_desc_t *)0) || (items[i].desc->value_ptr == (void *)0)) {
            return LT_STATUS_BAD_PAYLOAD;
        }
        if (use_requested_values != 0u) {
            st = lt_params_write_report_item_value_(&w, items[i].desc, items[i].item_status, items[i].value);
        } else {
            st = lt_params_write_report_item_current_(&w, items[i].desc, items[i].item_status);
        }
        if (st != LT_STATUS_OK) {
            return st;
        }
    }

    return lt_tx_enqueue_frame((uint8_t)LT_TYPE_PARAM_REPORT, lt_params_report_payload_, w.pos);
}

static lt_status_t lt_params_compare_min_(uint8_t value_type, const uint8_t *value, const void *min_value_ptr, uint8_t *ok)
{
    *ok = 1u;
    switch (value_type) {
    case LT_VALUE_BOOL:
    case LT_VALUE_U8:
    case LT_VALUE_ENUM_U8: {
        uint8_t v;
        uint8_t m;
        (void)memcpy(&v, value, sizeof(v));
        (void)memcpy(&m, min_value_ptr, sizeof(m));
        *ok = (uint8_t)(v >= m);
        return LT_STATUS_OK;
    }
    case LT_VALUE_I8: {
        int8_t v;
        int8_t m;
        (void)memcpy(&v, value, sizeof(v));
        (void)memcpy(&m, min_value_ptr, sizeof(m));
        *ok = (uint8_t)(v >= m);
        return LT_STATUS_OK;
    }
    case LT_VALUE_U16: {
        uint16_t v;
        uint16_t m;
        (void)memcpy(&v, value, sizeof(v));
        (void)memcpy(&m, min_value_ptr, sizeof(m));
        *ok = (uint8_t)(v >= m);
        return LT_STATUS_OK;
    }
    case LT_VALUE_I16: {
        int16_t v;
        int16_t m;
        (void)memcpy(&v, value, sizeof(v));
        (void)memcpy(&m, min_value_ptr, sizeof(m));
        *ok = (uint8_t)(v >= m);
        return LT_STATUS_OK;
    }
    case LT_VALUE_U32: {
        uint32_t v;
        uint32_t m;
        (void)memcpy(&v, value, sizeof(v));
        (void)memcpy(&m, min_value_ptr, sizeof(m));
        *ok = (uint8_t)(v >= m);
        return LT_STATUS_OK;
    }
    case LT_VALUE_I32: {
        int32_t v;
        int32_t m;
        (void)memcpy(&v, value, sizeof(v));
        (void)memcpy(&m, min_value_ptr, sizeof(m));
        *ok = (uint8_t)(v >= m);
        return LT_STATUS_OK;
    }
    case LT_VALUE_U64: {
        uint64_t v;
        uint64_t m;
        (void)memcpy(&v, value, sizeof(v));
        (void)memcpy(&m, min_value_ptr, sizeof(m));
        *ok = (uint8_t)(v >= m);
        return LT_STATUS_OK;
    }
    case LT_VALUE_I64: {
        int64_t v;
        int64_t m;
        (void)memcpy(&v, value, sizeof(v));
        (void)memcpy(&m, min_value_ptr, sizeof(m));
        *ok = (uint8_t)(v >= m);
        return LT_STATUS_OK;
    }
    case LT_VALUE_F32: {
        float v;
        float m;
        (void)memcpy(&v, value, sizeof(v));
        (void)memcpy(&m, min_value_ptr, sizeof(m));
        *ok = (uint8_t)(v >= m);
        return LT_STATUS_OK;
    }
    case LT_VALUE_F64: {
        double v;
        double m;
        (void)memcpy(&v, value, sizeof(v));
        (void)memcpy(&m, min_value_ptr, sizeof(m));
        *ok = (uint8_t)(v >= m);
        return LT_STATUS_OK;
    }
    default:
        return LT_STATUS_UNSUPPORTED;
    }
}

static lt_status_t lt_params_compare_max_(uint8_t value_type, const uint8_t *value, const void *max_value_ptr, uint8_t *ok)
{
    *ok = 1u;
    switch (value_type) {
    case LT_VALUE_BOOL:
    case LT_VALUE_U8:
    case LT_VALUE_ENUM_U8: {
        uint8_t v;
        uint8_t m;
        (void)memcpy(&v, value, sizeof(v));
        (void)memcpy(&m, max_value_ptr, sizeof(m));
        *ok = (uint8_t)(v <= m);
        return LT_STATUS_OK;
    }
    case LT_VALUE_I8: {
        int8_t v;
        int8_t m;
        (void)memcpy(&v, value, sizeof(v));
        (void)memcpy(&m, max_value_ptr, sizeof(m));
        *ok = (uint8_t)(v <= m);
        return LT_STATUS_OK;
    }
    case LT_VALUE_U16: {
        uint16_t v;
        uint16_t m;
        (void)memcpy(&v, value, sizeof(v));
        (void)memcpy(&m, max_value_ptr, sizeof(m));
        *ok = (uint8_t)(v <= m);
        return LT_STATUS_OK;
    }
    case LT_VALUE_I16: {
        int16_t v;
        int16_t m;
        (void)memcpy(&v, value, sizeof(v));
        (void)memcpy(&m, max_value_ptr, sizeof(m));
        *ok = (uint8_t)(v <= m);
        return LT_STATUS_OK;
    }
    case LT_VALUE_U32: {
        uint32_t v;
        uint32_t m;
        (void)memcpy(&v, value, sizeof(v));
        (void)memcpy(&m, max_value_ptr, sizeof(m));
        *ok = (uint8_t)(v <= m);
        return LT_STATUS_OK;
    }
    case LT_VALUE_I32: {
        int32_t v;
        int32_t m;
        (void)memcpy(&v, value, sizeof(v));
        (void)memcpy(&m, max_value_ptr, sizeof(m));
        *ok = (uint8_t)(v <= m);
        return LT_STATUS_OK;
    }
    case LT_VALUE_U64: {
        uint64_t v;
        uint64_t m;
        (void)memcpy(&v, value, sizeof(v));
        (void)memcpy(&m, max_value_ptr, sizeof(m));
        *ok = (uint8_t)(v <= m);
        return LT_STATUS_OK;
    }
    case LT_VALUE_I64: {
        int64_t v;
        int64_t m;
        (void)memcpy(&v, value, sizeof(v));
        (void)memcpy(&m, max_value_ptr, sizeof(m));
        *ok = (uint8_t)(v <= m);
        return LT_STATUS_OK;
    }
    case LT_VALUE_F32: {
        float v;
        float m;
        (void)memcpy(&v, value, sizeof(v));
        (void)memcpy(&m, max_value_ptr, sizeof(m));
        *ok = (uint8_t)(v <= m);
        return LT_STATUS_OK;
    }
    case LT_VALUE_F64: {
        double v;
        double m;
        (void)memcpy(&v, value, sizeof(v));
        (void)memcpy(&m, max_value_ptr, sizeof(m));
        *ok = (uint8_t)(v <= m);
        return LT_STATUS_OK;
    }
    default:
        return LT_STATUS_UNSUPPORTED;
    }
}

static lt_status_t lt_params_validate_set_item_(const lt_params_set_item_t *item)
{
    const lt_param_desc_t *param;
    uint8_t ok;
    lt_status_t st;

    if ((item == (const lt_params_set_item_t *)0) || (item->desc == (const lt_param_desc_t *)0)) {
        return LT_STATUS_NOT_FOUND;
    }
    param = item->desc;

    if (!lt_params_writable_(param)) {
        return LT_STATUS_DENIED;
    }
    if (lt_value_type_is_variable(param->value_type) != 0u) {
        return LT_STATUS_UNSUPPORTED;
    }
    if (param->value_ptr == (void *)0) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    if ((param->value_type == (uint8_t)LT_VALUE_BOOL) && (item->value[0] > 1u)) {
        return LT_STATUS_RANGE_ERROR;
    }
    if ((param->flags & (uint8_t)LT_PARAM_FLAG_HAS_MIN) != 0u) {
        if (param->min_value_ptr == (const void *)0) {
            return LT_STATUS_BAD_PAYLOAD;
        }
        st = lt_params_compare_min_(param->value_type, item->value, param->min_value_ptr, &ok);
        if (st != LT_STATUS_OK) {
            return st;
        }
        if (ok == 0u) {
            return LT_STATUS_RANGE_ERROR;
        }
    }
    if ((param->flags & (uint8_t)LT_PARAM_FLAG_HAS_MAX) != 0u) {
        if (param->max_value_ptr == (const void *)0) {
            return LT_STATUS_BAD_PAYLOAD;
        }
        st = lt_params_compare_max_(param->value_type, item->value, param->max_value_ptr, &ok);
        if (st != LT_STATUS_OK) {
            return st;
        }
        if (ok == 0u) {
            return LT_STATUS_RANGE_ERROR;
        }
    }

    return LT_STATUS_OK;
}

static void lt_params_apply_set_items_(const lt_params_set_item_t *items, uint8_t count)
{
    uint8_t i;

    for (i = 0u; i < count; ++i) {
        uint16_t size = lt_value_type_fixed_size(items[i].desc->value_type);
        if ((size > 0u) && (items[i].desc->value_ptr != (void *)0)) {
            (void)memcpy(items[i].desc->value_ptr, items[i].value, (size_t)size);
        }
    }
}

LT_API void lt_params_reset(void)
{
    (void)memset(lt_params_set_items_, 0, sizeof(lt_params_set_items_));
    (void)memset(lt_params_report_payload_, 0, sizeof(lt_params_report_payload_));
}

LT_API lt_status_t lt_params_handle_param_set(
    lt_frame_id_t request_frame_id,
    const uint8_t *payload,
    uint16_t payload_len
)
{
    lt_reader_t r;
    uint8_t count = 0u;
    uint8_t i;
    uint8_t j;
    lt_status_t st;
    lt_status_t overall_status = LT_STATUS_OK;

    if ((payload == (const uint8_t *)0) && (payload_len > 0u)) {
        return lt_params_enqueue_error_report_(request_frame_id, LT_STATUS_BAD_PAYLOAD);
    }
    if (lt_state_get() != LT_STATE_CONNECTED) {
        return lt_params_enqueue_error_report_(request_frame_id, LT_STATUS_NOT_READY);
    }
    if (!lt_state_feature_enabled((uint32_t)LT_FEATURE_PARAM_SET)) {
        return lt_params_enqueue_error_report_(request_frame_id, LT_STATUS_UNSUPPORTED);
    }

    lt_reader_init(&r, payload, payload_len);
    st = lt_read_u8(&r, &count);
    if (st != LT_STATUS_OK) {
        return lt_params_enqueue_error_report_(request_frame_id, LT_STATUS_BAD_PAYLOAD);
    }
    if (count == 0u) {
        return lt_params_enqueue_error_report_(request_frame_id, LT_STATUS_BAD_PAYLOAD);
    }
    if (count > (uint8_t)LT_PARAM_SET_MAX_ITEMS) {
        return lt_params_enqueue_error_report_(request_frame_id, LT_STATUS_TOO_LARGE);
    }

    for (i = 0u; i < count; ++i) {
        uint16_t storage_size;
        lt_params_set_items_[i].param_id = 0u;
        lt_params_set_items_[i].desc = (const lt_param_desc_t *)0;
        lt_params_set_items_[i].item_status = LT_STATUS_OK;
        (void)memset(lt_params_set_items_[i].value, 0, sizeof(lt_params_set_items_[i].value));

        st = lt_read_u16_le(&r, &lt_params_set_items_[i].param_id);
        if (st != LT_STATUS_OK) {
            return lt_params_enqueue_error_report_(request_frame_id, LT_STATUS_BAD_PAYLOAD);
        }
        lt_params_set_items_[i].desc = lt_params_find_param_(lt_params_set_items_[i].param_id);
        if (lt_params_set_items_[i].desc == (const lt_param_desc_t *)0) {
            return lt_params_enqueue_error_report_(request_frame_id, LT_STATUS_NOT_FOUND);
        }

        storage_size = lt_params_value_storage_size_(lt_params_set_items_[i].desc->value_type);
        if ((storage_size == 0u) || (storage_size > (uint16_t)LT_PARAM_MAX_VALUE_SIZE)) {
            return lt_params_enqueue_error_report_(request_frame_id, LT_STATUS_TOO_LARGE);
        }
        st = lt_read_value(&r, lt_params_set_items_[i].desc->value_type, lt_params_set_items_[i].value, storage_size);
        if (st != LT_STATUS_OK) {
            return lt_params_enqueue_error_report_(request_frame_id, (st == LT_STATUS_TOO_LARGE) ? LT_STATUS_TOO_LARGE : LT_STATUS_BAD_PAYLOAD);
        }
    }

    if (lt_reader_remaining(&r) != 0u) {
        return lt_params_enqueue_error_report_(request_frame_id, LT_STATUS_BAD_PAYLOAD);
    }

    for (i = 0u; i < count; ++i) {
        for (j = (uint8_t)(i + 1u); j < count; ++j) {
            if (lt_params_set_items_[i].param_id == lt_params_set_items_[j].param_id) {
                lt_params_set_items_[j].item_status = LT_STATUS_CONFLICT;
            }
        }
    }

    for (i = 0u; i < count; ++i) {
        if (lt_params_set_items_[i].item_status == LT_STATUS_OK) {
            lt_params_set_items_[i].item_status = lt_params_validate_set_item_(&lt_params_set_items_[i]);
        }
        if ((overall_status == LT_STATUS_OK) && (lt_params_set_items_[i].item_status != LT_STATUS_OK)) {
            overall_status = lt_params_set_items_[i].item_status;
        }
    }

    st = lt_params_enqueue_set_items_report_(request_frame_id, overall_status, lt_params_set_items_, count, (uint8_t)(overall_status == LT_STATUS_OK));
    if (st != LT_STATUS_OK) {
        lt_status_t report_status = (st == LT_STATUS_TOO_LARGE) ? LT_STATUS_TOO_LARGE : st;
        (void)lt_params_enqueue_error_report_(request_frame_id, report_status);
        return report_status;
    }

    if (overall_status == LT_STATUS_OK) {
        lt_params_apply_set_items_(lt_params_set_items_, count);
    }
    return LT_STATUS_OK;
}

static lt_status_t lt_params_validate_get_param_(const lt_param_desc_t *param)
{
    if (param == (const lt_param_desc_t *)0) {
        return LT_STATUS_NOT_FOUND;
    }
    if (!lt_params_readable_(param)) {
        return LT_STATUS_DENIED;
    }
    if (param->value_ptr == (void *)0) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    return LT_STATUS_OK;
}

static lt_status_t lt_params_enqueue_get_registry_report_(lt_frame_id_t request_frame_id, const lt_param_registry_t *registry)
{
    lt_writer_t w;
    lt_status_t st;
    uint16_t i;
    uint16_t count = lt_registry_param_count(registry);
    uint16_t cap = lt_params_max_payload_len_();

    lt_writer_init(&w, lt_params_report_payload_, cap);
    st = lt_params_write_report_header_(&w, request_frame_id, (uint8_t)LT_PARAM_REPORT_RESPONSE_TO_GET, LT_STATUS_OK, count);
    if (st != LT_STATUS_OK) {
        return st;
    }

    for (i = 0u; i < count; ++i) {
        st = lt_params_write_report_item_current_(&w, &registry->params[i], LT_STATUS_OK);
        if (st != LT_STATUS_OK) {
            return lt_params_enqueue_error_report_(request_frame_id, (st == LT_STATUS_TOO_LARGE) ? LT_STATUS_TOO_LARGE : st);
        }
    }
    return lt_tx_enqueue_frame((uint8_t)LT_TYPE_PARAM_REPORT, lt_params_report_payload_, w.pos);
}

static lt_status_t lt_params_enqueue_get_by_id_report_(
    lt_frame_id_t request_frame_id,
    const uint8_t *ids_payload,
    uint8_t count
)
{
    lt_writer_t w;
    lt_reader_t r;
    lt_status_t st;
    uint8_t i;
    uint16_t cap = lt_params_max_payload_len_();

    lt_writer_init(&w, lt_params_report_payload_, cap);
    st = lt_params_write_report_header_(&w, request_frame_id, (uint8_t)LT_PARAM_REPORT_RESPONSE_TO_GET, LT_STATUS_OK, (uint16_t)count);
    if (st != LT_STATUS_OK) {
        return st;
    }

    lt_reader_init(&r, ids_payload, (uint16_t)((uint16_t)count * 2u));
    for (i = 0u; i < count; ++i) {
        lt_param_id_t param_id;
        const lt_param_desc_t *param;
        st = lt_read_u16_le(&r, &param_id);
        if (st != LT_STATUS_OK) {
            return lt_params_enqueue_error_report_(request_frame_id, LT_STATUS_BAD_PAYLOAD);
        }
        param = lt_params_find_param_(param_id);
        st = lt_params_write_report_item_current_(&w, param, LT_STATUS_OK);
        if (st != LT_STATUS_OK) {
            return lt_params_enqueue_error_report_(request_frame_id, (st == LT_STATUS_TOO_LARGE) ? LT_STATUS_TOO_LARGE : st);
        }
    }
    return lt_tx_enqueue_frame((uint8_t)LT_TYPE_PARAM_REPORT, lt_params_report_payload_, w.pos);
}

LT_API lt_status_t lt_params_handle_param_get(
    lt_frame_id_t request_frame_id,
    const uint8_t *payload,
    uint16_t payload_len
)
{
    lt_reader_t r;
    uint8_t query_mode = 0u;
    uint8_t count = 0u;
    lt_status_t st;

    if ((payload == (const uint8_t *)0) && (payload_len > 0u)) {
        return lt_params_enqueue_error_report_(request_frame_id, LT_STATUS_BAD_PAYLOAD);
    }
    if (lt_state_get() != LT_STATE_CONNECTED) {
        return lt_params_enqueue_error_report_(request_frame_id, LT_STATUS_NOT_READY);
    }
    if (!lt_state_feature_enabled((uint32_t)LT_FEATURE_PARAM_GET)) {
        return lt_params_enqueue_error_report_(request_frame_id, LT_STATUS_UNSUPPORTED);
    }

    lt_reader_init(&r, payload, payload_len);
    st = lt_read_u8(&r, &query_mode);
    if (st != LT_STATUS_OK) {
        return lt_params_enqueue_error_report_(request_frame_id, LT_STATUS_BAD_PAYLOAD);
    }
    st = lt_read_u8(&r, &count);
    if (st != LT_STATUS_OK) {
        return lt_params_enqueue_error_report_(request_frame_id, LT_STATUS_BAD_PAYLOAD);
    }

    if (query_mode == (uint8_t)LT_PARAM_QUERY_BY_ID) {
        uint8_t i;
        const uint8_t *ids_payload = (payload_len >= 2u) ? &payload[2] : (const uint8_t *)0;
        if ((count == 0u) || (lt_reader_remaining(&r) != (uint16_t)((uint16_t)count * 2u))) {
            return lt_params_enqueue_error_report_(request_frame_id, LT_STATUS_BAD_PAYLOAD);
        }
        for (i = 0u; i < count; ++i) {
            lt_param_id_t param_id;
            const lt_param_desc_t *param;
            st = lt_read_u16_le(&r, &param_id);
            if (st != LT_STATUS_OK) {
                return lt_params_enqueue_error_report_(request_frame_id, LT_STATUS_BAD_PAYLOAD);
            }
            param = lt_params_find_param_(param_id);
            st = lt_params_validate_get_param_(param);
            if (st != LT_STATUS_OK) {
                return lt_params_enqueue_error_report_(request_frame_id, st);
            }
        }
        return lt_params_enqueue_get_by_id_report_(request_frame_id, ids_payload, count);
    }

    if (query_mode == (uint8_t)LT_PARAM_QUERY_ALL) {
        const lt_param_registry_t *registry = lt_state_param_registry();
        uint16_t i;
        if ((count != 0u) || (lt_reader_remaining(&r) != 0u)) {
            return lt_params_enqueue_error_report_(request_frame_id, LT_STATUS_BAD_PAYLOAD);
        }
        if ((registry != (const lt_param_registry_t *)0) && (registry->param_count > 0u) && (registry->params == (const lt_param_desc_t *)0)) {
            return lt_params_enqueue_error_report_(request_frame_id, LT_STATUS_BAD_PAYLOAD);
        }
        for (i = 0u; i < lt_registry_param_count(registry); ++i) {
            st = lt_params_validate_get_param_(&registry->params[i]);
            if (st != LT_STATUS_OK) {
                return lt_params_enqueue_error_report_(request_frame_id, st);
            }
        }
        return lt_params_enqueue_get_registry_report_(request_frame_id, registry);
    }

    return lt_params_enqueue_error_report_(request_frame_id, LT_STATUS_UNSUPPORTED);
}

#endif /* LITETUNE_IMPLEMENTATION */

#endif /* LT_PARAMS_H */
