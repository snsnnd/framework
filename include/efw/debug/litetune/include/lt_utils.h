#ifndef LT_UTILS_H
#define LT_UTILS_H

#include "lt_config.h"
#include "lt_common.h"

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint8_t *data;
    uint16_t cap;
    uint16_t pos;
} lt_writer_t;

typedef struct {
    const uint8_t *data;
    uint16_t len;
    uint16_t pos;
} lt_reader_t;

typedef struct {
    const uint8_t *data;
    uint8_t len;
} lt_str8_view_t;

typedef struct {
    const uint8_t *data;
    uint8_t len;
} lt_bytes8_view_t;

LT_API void lt_writer_init(lt_writer_t *w, uint8_t *data, uint16_t cap);
LT_API void lt_reader_init(lt_reader_t *r, const uint8_t *data, uint16_t len);
LT_API uint16_t lt_writer_remaining(const lt_writer_t *w);
LT_API uint16_t lt_reader_remaining(const lt_reader_t *r);

LT_API lt_status_t lt_write_u8(lt_writer_t *w, uint8_t v);
LT_API lt_status_t lt_write_u16_le(lt_writer_t *w, uint16_t v);
LT_API lt_status_t lt_write_u32_le(lt_writer_t *w, uint32_t v);
LT_API lt_status_t lt_write_u64_le(lt_writer_t *w, uint64_t v);
LT_API lt_status_t lt_write_bytes(lt_writer_t *w, const uint8_t *src, uint16_t len);
LT_API lt_status_t lt_write_str8(lt_writer_t *w, const char *str);
LT_API lt_status_t lt_write_str8_view(lt_writer_t *w, lt_str8_view_t view);
LT_API lt_status_t lt_write_bytes8_view(lt_writer_t *w, lt_bytes8_view_t view);

LT_API lt_status_t lt_read_u8(lt_reader_t *r, uint8_t *out);
LT_API lt_status_t lt_read_u16_le(lt_reader_t *r, uint16_t *out);
LT_API lt_status_t lt_read_u32_le(lt_reader_t *r, uint32_t *out);
LT_API lt_status_t lt_read_u64_le(lt_reader_t *r, uint64_t *out);
LT_API lt_status_t lt_read_bytes(lt_reader_t *r, const uint8_t **out, uint16_t len);
LT_API lt_status_t lt_read_str8(lt_reader_t *r, lt_str8_view_t *out);
LT_API lt_status_t lt_read_bytes8(lt_reader_t *r, lt_bytes8_view_t *out);

LT_API uint16_t lt_cstr_len_u16(const char *str);
LT_API lt_status_t lt_str8_cstr_len(const char *str, uint8_t *len_out);
LT_API uint8_t lt_str8_is_valid_cstr(const char *str);
LT_API uint16_t lt_str8_wire_len_from_cstr(const char *str);
LT_API uint16_t lt_str8_wire_len_from_len(uint8_t len);

LT_API uint8_t lt_value_type_is_valid(uint8_t value_type);
LT_API uint16_t lt_value_type_fixed_size(uint8_t value_type);
LT_API uint8_t lt_value_type_is_variable(uint8_t value_type);

LT_API lt_status_t lt_write_value(lt_writer_t *w, uint8_t value_type, const void *value_ptr);
LT_API lt_status_t lt_read_value(lt_reader_t *r, uint8_t value_type, void *out_value_ptr, uint16_t out_cap);

LT_API uint16_t lt_crc16_mcrf4xx(const uint8_t *data, uint16_t len);

LT_API void lt_counters_clear(lt_counters_t *counters);
LT_API void lt_counter_inc_u16(uint16_t *counter);
LT_API uint16_t lt_min_u16(uint16_t a, uint16_t b);

#ifdef __cplusplus
}
#endif

#ifdef LITETUNE_IMPLEMENTATION

#include <string.h>

LT_API void lt_writer_init(lt_writer_t *w, uint8_t *data, uint16_t cap)
{
    if (w != (lt_writer_t *)0) {
        w->data = data;
        w->cap = cap;
        w->pos = 0u;
    }
}

LT_API void lt_reader_init(lt_reader_t *r, const uint8_t *data, uint16_t len)
{
    if (r != (lt_reader_t *)0) {
        r->data = data;
        r->len = len;
        r->pos = 0u;
    }
}

LT_API uint16_t lt_writer_remaining(const lt_writer_t *w)
{
    if ((w == (const lt_writer_t *)0) || (w->pos > w->cap)) {
        return 0u;
    }
    return (uint16_t)(w->cap - w->pos);
}

LT_API uint16_t lt_reader_remaining(const lt_reader_t *r)
{
    if ((r == (const lt_reader_t *)0) || (r->pos > r->len)) {
        return 0u;
    }
    return (uint16_t)(r->len - r->pos);
}

LT_API lt_status_t lt_write_u8(lt_writer_t *w, uint8_t v)
{
    if ((w == (lt_writer_t *)0) || (w->data == (uint8_t *)0)) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    if (lt_writer_remaining(w) < 1u) {
        return LT_STATUS_TOO_LARGE;
    }
    w->data[w->pos] = v;
    w->pos = (uint16_t)(w->pos + 1u);
    return LT_STATUS_OK;
}

LT_API lt_status_t lt_write_u16_le(lt_writer_t *w, uint16_t v)
{
    if ((w == (lt_writer_t *)0) || (w->data == (uint8_t *)0)) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    if (lt_writer_remaining(w) < 2u) {
        return LT_STATUS_TOO_LARGE;
    }
    w->data[w->pos] = (uint8_t)(v & 0xFFu);
    w->data[(uint16_t)(w->pos + 1u)] = (uint8_t)((v >> 8) & 0xFFu);
    w->pos = (uint16_t)(w->pos + 2u);
    return LT_STATUS_OK;
}

LT_API lt_status_t lt_write_u32_le(lt_writer_t *w, uint32_t v)
{
    if ((w == (lt_writer_t *)0) || (w->data == (uint8_t *)0)) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    if (lt_writer_remaining(w) < 4u) {
        return LT_STATUS_TOO_LARGE;
    }
    w->data[w->pos] = (uint8_t)(v & 0xFFu);
    w->data[(uint16_t)(w->pos + 1u)] = (uint8_t)((v >> 8) & 0xFFu);
    w->data[(uint16_t)(w->pos + 2u)] = (uint8_t)((v >> 16) & 0xFFu);
    w->data[(uint16_t)(w->pos + 3u)] = (uint8_t)((v >> 24) & 0xFFu);
    w->pos = (uint16_t)(w->pos + 4u);
    return LT_STATUS_OK;
}

LT_API lt_status_t lt_write_u64_le(lt_writer_t *w, uint64_t v)
{
    uint8_t i;
    if ((w == (lt_writer_t *)0) || (w->data == (uint8_t *)0)) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    if (lt_writer_remaining(w) < 8u) {
        return LT_STATUS_TOO_LARGE;
    }
    for (i = 0u; i < 8u; ++i) {
        w->data[(uint16_t)(w->pos + (uint16_t)i)] = (uint8_t)((v >> (8u * i)) & 0xFFu);
    }
    w->pos = (uint16_t)(w->pos + 8u);
    return LT_STATUS_OK;
}

LT_API lt_status_t lt_write_bytes(lt_writer_t *w, const uint8_t *src, uint16_t len)
{
    if ((w == (lt_writer_t *)0) || (w->data == (uint8_t *)0) || ((src == (const uint8_t *)0) && (len > 0u))) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    if (lt_writer_remaining(w) < len) {
        return LT_STATUS_TOO_LARGE;
    }
    if (len > 0u) {
        (void)memcpy(&w->data[w->pos], src, (size_t)len);
    }
    w->pos = (uint16_t)(w->pos + len);
    return LT_STATUS_OK;
}

LT_API uint16_t lt_cstr_len_u16(const char *str)
{
    uint16_t len = 0u;
    if (str == (const char *)0) {
        return 0u;
    }
    while ((len < 65535u) && (str[len] != '\0')) {
        len = (uint16_t)(len + 1u);
    }
    return len;
}

LT_API lt_status_t lt_str8_cstr_len(const char *str, uint8_t *len_out)
{
    uint16_t len;
    if (len_out == (uint8_t *)0) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    len = lt_cstr_len_u16(str);
    if (len > 255u) {
        return LT_STATUS_TOO_LARGE;
    }
    *len_out = (uint8_t)len;
    return LT_STATUS_OK;
}

LT_API uint8_t lt_str8_is_valid_cstr(const char *str)
{
    uint8_t len = 0u;
    return (uint8_t)(lt_str8_cstr_len(str, &len) == LT_STATUS_OK);
}

LT_API uint16_t lt_str8_wire_len_from_cstr(const char *str)
{
    uint8_t len = 0u;
    if (lt_str8_cstr_len(str, &len) != LT_STATUS_OK) {
        return 0u;
    }
    return (uint16_t)(1u + (uint16_t)len);
}

LT_API uint16_t lt_str8_wire_len_from_len(uint8_t len)
{
    return (uint16_t)(1u + (uint16_t)len);
}

LT_API lt_status_t lt_write_str8_view(lt_writer_t *w, lt_str8_view_t view)
{
    lt_status_t st;
    if ((view.data == (const uint8_t *)0) && (view.len > 0u)) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    st = lt_write_u8(w, view.len);
    if (st != LT_STATUS_OK) {
        return st;
    }
    return lt_write_bytes(w, view.data, (uint16_t)view.len);
}

LT_API lt_status_t lt_write_bytes8_view(lt_writer_t *w, lt_bytes8_view_t view)
{
    lt_status_t st;
    if ((view.data == (const uint8_t *)0) && (view.len > 0u)) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    st = lt_write_u8(w, view.len);
    if (st != LT_STATUS_OK) {
        return st;
    }
    return lt_write_bytes(w, view.data, (uint16_t)view.len);
}

LT_API lt_status_t lt_write_str8(lt_writer_t *w, const char *str)
{
    uint8_t len = 0u;
    lt_status_t st = lt_str8_cstr_len(str, &len);
    lt_str8_view_t view;
    if (st != LT_STATUS_OK) {
        return st;
    }
    view.data = (const uint8_t *)str;
    view.len = len;
    return lt_write_str8_view(w, view);
}

LT_API lt_status_t lt_read_u8(lt_reader_t *r, uint8_t *out)
{
    if ((r == (lt_reader_t *)0) || (out == (uint8_t *)0) || ((r->data == (const uint8_t *)0) && (r->len > 0u))) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    if (lt_reader_remaining(r) < 1u) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    *out = r->data[r->pos];
    r->pos = (uint16_t)(r->pos + 1u);
    return LT_STATUS_OK;
}

LT_API lt_status_t lt_read_u16_le(lt_reader_t *r, uint16_t *out)
{
    if ((r == (lt_reader_t *)0) || (out == (uint16_t *)0) || ((r->data == (const uint8_t *)0) && (r->len > 0u))) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    if (lt_reader_remaining(r) < 2u) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    *out = (uint16_t)(((uint16_t)r->data[r->pos]) |
                      ((uint16_t)r->data[(uint16_t)(r->pos + 1u)] << 8));
    r->pos = (uint16_t)(r->pos + 2u);
    return LT_STATUS_OK;
}

LT_API lt_status_t lt_read_u32_le(lt_reader_t *r, uint32_t *out)
{
    if ((r == (lt_reader_t *)0) || (out == (uint32_t *)0) || ((r->data == (const uint8_t *)0) && (r->len > 0u))) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    if (lt_reader_remaining(r) < 4u) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    *out = ((uint32_t)r->data[r->pos]) |
           ((uint32_t)r->data[(uint16_t)(r->pos + 1u)] << 8) |
           ((uint32_t)r->data[(uint16_t)(r->pos + 2u)] << 16) |
           ((uint32_t)r->data[(uint16_t)(r->pos + 3u)] << 24);
    r->pos = (uint16_t)(r->pos + 4u);
    return LT_STATUS_OK;
}

LT_API lt_status_t lt_read_u64_le(lt_reader_t *r, uint64_t *out)
{
    uint8_t i;
    uint64_t v = 0u;
    if ((r == (lt_reader_t *)0) || (out == (uint64_t *)0) || ((r->data == (const uint8_t *)0) && (r->len > 0u))) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    if (lt_reader_remaining(r) < 8u) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    for (i = 0u; i < 8u; ++i) {
        v |= ((uint64_t)r->data[(uint16_t)(r->pos + (uint16_t)i)] << (8u * i));
    }
    *out = v;
    r->pos = (uint16_t)(r->pos + 8u);
    return LT_STATUS_OK;
}

LT_API lt_status_t lt_read_bytes(lt_reader_t *r, const uint8_t **out, uint16_t len)
{
    if ((r == (lt_reader_t *)0) || (out == (const uint8_t **)0) || ((r->data == (const uint8_t *)0) && (r->len > 0u))) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    if (lt_reader_remaining(r) < len) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    *out = (len > 0u) ? &r->data[r->pos] : (const uint8_t *)0;
    r->pos = (uint16_t)(r->pos + len);
    return LT_STATUS_OK;
}

LT_API lt_status_t lt_read_str8(lt_reader_t *r, lt_str8_view_t *out)
{
    uint8_t len = 0u;
    const uint8_t *data = (const uint8_t *)0;
    lt_status_t st;
    if (out == (lt_str8_view_t *)0) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    st = lt_read_u8(r, &len);
    if (st != LT_STATUS_OK) {
        return st;
    }
    st = lt_read_bytes(r, &data, (uint16_t)len);
    if (st != LT_STATUS_OK) {
        return st;
    }
    out->data = data;
    out->len = len;
    return LT_STATUS_OK;
}

LT_API lt_status_t lt_read_bytes8(lt_reader_t *r, lt_bytes8_view_t *out)
{
    uint8_t len = 0u;
    const uint8_t *data = (const uint8_t *)0;
    lt_status_t st;
    if (out == (lt_bytes8_view_t *)0) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    st = lt_read_u8(r, &len);
    if (st != LT_STATUS_OK) {
        return st;
    }
    st = lt_read_bytes(r, &data, (uint16_t)len);
    if (st != LT_STATUS_OK) {
        return st;
    }
    out->data = data;
    out->len = len;
    return LT_STATUS_OK;
}

LT_API uint8_t lt_value_type_is_valid(uint8_t value_type)
{
    return (uint8_t)((value_type >= (uint8_t)LT_VALUE_BOOL) &&
                     (value_type <= (uint8_t)LT_VALUE_ENUM_U8));
}

LT_API uint16_t lt_value_type_fixed_size(uint8_t value_type)
{
    switch (value_type) {
    case LT_VALUE_BOOL:
    case LT_VALUE_U8:
    case LT_VALUE_I8:
    case LT_VALUE_ENUM_U8:
        return 1u;
    case LT_VALUE_U16:
    case LT_VALUE_I16:
        return 2u;
    case LT_VALUE_U32:
    case LT_VALUE_I32:
    case LT_VALUE_F32:
        return 4u;
    case LT_VALUE_U64:
    case LT_VALUE_I64:
    case LT_VALUE_F64:
        return 8u;
    default:
        return 0u;
    }
}

LT_API uint8_t lt_value_type_is_variable(uint8_t value_type)
{
    return (uint8_t)((value_type == (uint8_t)LT_VALUE_STRING) ||
                     (value_type == (uint8_t)LT_VALUE_BYTES));
}

LT_API lt_status_t lt_write_value(lt_writer_t *w, uint8_t value_type, const void *value_ptr)
{
    uint16_t u16v;
    uint32_t u32v;
    uint64_t u64v;
    lt_str8_view_t str_view;
    lt_bytes8_view_t bytes_view;

    if (value_ptr == (const void *)0) {
        return LT_STATUS_BAD_PAYLOAD;
    }

    switch (value_type) {
    case LT_VALUE_BOOL:
    case LT_VALUE_U8:
    case LT_VALUE_I8:
    case LT_VALUE_ENUM_U8:
        return lt_write_u8(w, *((const uint8_t *)value_ptr));
    case LT_VALUE_U16:
    case LT_VALUE_I16:
        (void)memcpy(&u16v, value_ptr, sizeof(u16v));
        return lt_write_u16_le(w, u16v);
    case LT_VALUE_U32:
    case LT_VALUE_I32:
    case LT_VALUE_F32:
        (void)memcpy(&u32v, value_ptr, sizeof(u32v));
        return lt_write_u32_le(w, u32v);
    case LT_VALUE_U64:
    case LT_VALUE_I64:
    case LT_VALUE_F64:
        (void)memcpy(&u64v, value_ptr, sizeof(u64v));
        return lt_write_u64_le(w, u64v);
    case LT_VALUE_STRING:
        (void)memcpy(&str_view, value_ptr, sizeof(str_view));
        return lt_write_str8_view(w, str_view);
    case LT_VALUE_BYTES:
        (void)memcpy(&bytes_view, value_ptr, sizeof(bytes_view));
        return lt_write_bytes8_view(w, bytes_view);
    default:
        return LT_STATUS_BAD_PAYLOAD;
    }
}

LT_API lt_status_t lt_read_value(lt_reader_t *r, uint8_t value_type, void *out_value_ptr, uint16_t out_cap)
{
    uint8_t u8v;
    uint16_t u16v;
    uint32_t u32v;
    uint64_t u64v;
    lt_str8_view_t str_view;
    lt_bytes8_view_t bytes_view;
    lt_status_t st;

    if (out_value_ptr == (void *)0) {
        return LT_STATUS_BAD_PAYLOAD;
    }

    switch (value_type) {
    case LT_VALUE_BOOL:
    case LT_VALUE_U8:
    case LT_VALUE_I8:
    case LT_VALUE_ENUM_U8:
        if (out_cap < 1u) {
            return LT_STATUS_TOO_LARGE;
        }
        st = lt_read_u8(r, &u8v);
        if (st == LT_STATUS_OK) {
            (void)memcpy(out_value_ptr, &u8v, sizeof(u8v));
        }
        return st;
    case LT_VALUE_U16:
    case LT_VALUE_I16:
        if (out_cap < 2u) {
            return LT_STATUS_TOO_LARGE;
        }
        st = lt_read_u16_le(r, &u16v);
        if (st == LT_STATUS_OK) {
            (void)memcpy(out_value_ptr, &u16v, sizeof(u16v));
        }
        return st;
    case LT_VALUE_U32:
    case LT_VALUE_I32:
    case LT_VALUE_F32:
        if (out_cap < 4u) {
            return LT_STATUS_TOO_LARGE;
        }
        st = lt_read_u32_le(r, &u32v);
        if (st == LT_STATUS_OK) {
            (void)memcpy(out_value_ptr, &u32v, sizeof(u32v));
        }
        return st;
    case LT_VALUE_U64:
    case LT_VALUE_I64:
    case LT_VALUE_F64:
        if (out_cap < 8u) {
            return LT_STATUS_TOO_LARGE;
        }
        st = lt_read_u64_le(r, &u64v);
        if (st == LT_STATUS_OK) {
            (void)memcpy(out_value_ptr, &u64v, sizeof(u64v));
        }
        return st;
    case LT_VALUE_STRING:
        if (out_cap < (uint16_t)sizeof(str_view)) {
            return LT_STATUS_TOO_LARGE;
        }
        st = lt_read_str8(r, &str_view);
        if (st == LT_STATUS_OK) {
            (void)memcpy(out_value_ptr, &str_view, sizeof(str_view));
        }
        return st;
    case LT_VALUE_BYTES:
        if (out_cap < (uint16_t)sizeof(bytes_view)) {
            return LT_STATUS_TOO_LARGE;
        }
        st = lt_read_bytes8(r, &bytes_view);
        if (st == LT_STATUS_OK) {
            (void)memcpy(out_value_ptr, &bytes_view, sizeof(bytes_view));
        }
        return st;
    default:
        return LT_STATUS_BAD_PAYLOAD;
    }
}

LT_API uint16_t lt_crc16_mcrf4xx(const uint8_t *data, uint16_t len)
{
    uint16_t crc = 0xFFFFu;
    uint16_t i;
    uint8_t bit;

    if ((data == (const uint8_t *)0) && (len > 0u)) {
        return 0u;
    }

    for (i = 0u; i < len; ++i) {
        crc ^= (uint16_t)data[i];
        for (bit = 0u; bit < 8u; ++bit) {
            if ((crc & 0x0001u) != 0u) {
                crc = (uint16_t)((crc >> 1) ^ 0x8408u);
            } else {
                crc = (uint16_t)(crc >> 1);
            }
        }
    }
    return crc;
}

LT_API void lt_counters_clear(lt_counters_t *counters)
{
    if (counters != (lt_counters_t *)0) {
        LT_CRITICAL_ENTER();
        counters->rx_decode_error_count = 0u;
        counters->rx_crc_error_count = 0u;
        counters->rx_bad_payload_count = 0u;
        counters->rx_overflow_count = 0u;
        counters->tx_drop_count = 0u;
        LT_CRITICAL_EXIT();
    }
}

LT_API void lt_counter_inc_u16(uint16_t *counter)
{
    if (counter != (uint16_t *)0) {
        LT_CRITICAL_ENTER();
        if (*counter != 0xFFFFu) {
            *counter = (uint16_t)(*counter + 1u);
        }
        LT_CRITICAL_EXIT();
    }
}

LT_API uint16_t lt_min_u16(uint16_t a, uint16_t b)
{
    return (a < b) ? a : b;
}

#endif /* LITETUNE_IMPLEMENTATION */

#endif /* LT_UTILS_H */
