#ifndef LT_FRAME_H
#define LT_FRAME_H

#include "lt_common.h"
#include "lt_utils.h"
#include "lt_cobs.h"

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint8_t type;
    uint64_t frame_id;
    const uint8_t *payload;
    uint16_t payload_len;
} lt_raw_frame_view_t;

LT_API lt_status_t lt_build_raw_frame_prefix(
    uint8_t type,
    uint64_t frame_id,
    const uint8_t *payload,
    uint16_t payload_len,
    uint8_t *raw_without_crc,
    uint16_t raw_without_crc_cap,
    uint16_t *raw_without_crc_len
);

LT_API lt_status_t lt_finalize_wire_frame_from_raw_prefix(
    const uint8_t *raw_without_crc,
    uint16_t raw_without_crc_len,
    uint8_t *wire,
    uint16_t wire_cap,
    uint16_t *wire_len
);

LT_API lt_status_t lt_parse_raw_frame(
    const uint8_t *raw,
    uint16_t raw_len,
    lt_raw_frame_view_t *view
);

LT_API lt_status_t lt_decode_wire_frame(
    const uint8_t *encoded_without_delimiter,
    uint16_t encoded_len,
    uint8_t *raw,
    uint16_t raw_cap,
    uint16_t *raw_len,
    lt_raw_frame_view_t *view
);

LT_API uint16_t lt_raw_frame_len_from_payload_len(uint16_t payload_len);
LT_API uint16_t lt_raw_prefix_len_from_payload_len(uint16_t payload_len);

#ifdef __cplusplus
}
#endif

#ifdef LITETUNE_IMPLEMENTATION

#include <string.h>

LT_API lt_status_t lt_build_raw_frame_prefix(
    uint8_t type,
    uint64_t frame_id,
    const uint8_t *payload,
    uint16_t payload_len,
    uint8_t *raw_without_crc,
    uint16_t raw_without_crc_cap,
    uint16_t *raw_without_crc_len
)
{
    lt_writer_t w;
    lt_status_t st;

    if ((raw_without_crc == (uint8_t *)0) || (raw_without_crc_len == (uint16_t *)0) ||
        ((payload == (const uint8_t *)0) && (payload_len > 0u))) {
        return LT_STATUS_BAD_PAYLOAD;
    }

    *raw_without_crc_len = 0u;

    if (frame_id == 0u) {
        return LT_STATUS_BAD_PAYLOAD;
    }

    if (payload_len > (uint16_t)(65535u - LT_RAW_FRAME_MIN_SIZE)) {
        return LT_STATUS_TOO_LARGE;
    }

    lt_writer_init(&w, raw_without_crc, raw_without_crc_cap);

    st = lt_write_u16_le(&w, (uint16_t)LT_MAGIC);
    if (st != LT_STATUS_OK) {
        return st;
    }
    st = lt_write_u8(&w, type);
    if (st != LT_STATUS_OK) {
        return st;
    }
    st = lt_write_u64_le(&w, frame_id);
    if (st != LT_STATUS_OK) {
        return st;
    }
    st = lt_write_bytes(&w, payload, payload_len);
    if (st != LT_STATUS_OK) {
        return st;
    }

    *raw_without_crc_len = w.pos;
    return LT_STATUS_OK;
}

LT_API lt_status_t lt_finalize_wire_frame_from_raw_prefix(
    const uint8_t *raw_without_crc,
    uint16_t raw_without_crc_len,
    uint8_t *wire,
    uint16_t wire_cap,
    uint16_t *wire_len
)
{
    uint8_t raw[LT_RAW_FRAME_SIZE];
    uint16_t raw_len;
    uint16_t crc;
    uint16_t encoded_len = 0u;
    lt_status_t st;

    if ((raw_without_crc == (const uint8_t *)0) || (wire == (uint8_t *)0) || (wire_len == (uint16_t *)0)) {
        return LT_STATUS_BAD_PAYLOAD;
    }

    *wire_len = 0u;

    if (raw_without_crc_len < LT_RAW_FRAME_HEADER_SIZE) {
        return LT_STATUS_FRAME_DECODE_ERROR;
    }
    if (raw_without_crc_len > (uint16_t)(LT_RAW_FRAME_SIZE - LT_RAW_FRAME_CRC_SIZE)) {
        return LT_STATUS_TOO_LARGE;
    }
    if (wire_cap < 2u) {
        return LT_STATUS_TOO_LARGE;
    }

    (void)memcpy(raw, raw_without_crc, (size_t)raw_without_crc_len);
    raw_len = raw_without_crc_len;
    crc = lt_crc16_mcrf4xx(raw, raw_len);
    raw[raw_len] = (uint8_t)(crc & 0xFFu);
    raw[(uint16_t)(raw_len + 1u)] = (uint8_t)((crc >> 8) & 0xFFu);
    raw_len = (uint16_t)(raw_len + LT_RAW_FRAME_CRC_SIZE);

    st = lt_cobs_encode(raw, raw_len, wire, (uint16_t)(wire_cap - 1u), &encoded_len);
    if (st != LT_STATUS_OK) {
        return st;
    }

    if ((uint16_t)(encoded_len + 1u) > wire_cap) {
        return LT_STATUS_TOO_LARGE;
    }
    wire[encoded_len] = 0u;
    *wire_len = (uint16_t)(encoded_len + 1u);
    return LT_STATUS_OK;
}

LT_API lt_status_t lt_parse_raw_frame(
    const uint8_t *raw,
    uint16_t raw_len,
    lt_raw_frame_view_t *view
)
{
    uint16_t magic;
    uint16_t rx_crc;
    uint16_t calc_crc;
    lt_reader_t r;
    lt_status_t st;

    if ((raw == (const uint8_t *)0) || (view == (lt_raw_frame_view_t *)0)) {
        return LT_STATUS_BAD_PAYLOAD;
    }

    view->type = 0u;
    view->frame_id = 0u;
    view->payload = (const uint8_t *)0;
    view->payload_len = 0u;

    if (raw_len < LT_RAW_FRAME_MIN_SIZE) {
        return LT_STATUS_FRAME_DECODE_ERROR;
    }

    lt_reader_init(&r, raw, raw_len);
    st = lt_read_u16_le(&r, &magic);
    if (st != LT_STATUS_OK) {
        return LT_STATUS_FRAME_DECODE_ERROR;
    }
    if (magic != (uint16_t)LT_MAGIC) {
        return LT_STATUS_FRAME_DECODE_ERROR;
    }

    rx_crc = (uint16_t)(((uint16_t)raw[(uint16_t)(raw_len - 2u)]) |
                        ((uint16_t)raw[(uint16_t)(raw_len - 1u)] << 8));
    calc_crc = lt_crc16_mcrf4xx(raw, (uint16_t)(raw_len - LT_RAW_FRAME_CRC_SIZE));
    if (rx_crc != calc_crc) {
        return LT_STATUS_CRC_ERROR;
    }

    st = lt_read_u8(&r, &view->type);
    if (st != LT_STATUS_OK) {
        return LT_STATUS_FRAME_DECODE_ERROR;
    }
    st = lt_read_u64_le(&r, &view->frame_id);
    if (st != LT_STATUS_OK) {
        return LT_STATUS_FRAME_DECODE_ERROR;
    }
    if (view->frame_id == 0u) {
        view->type = 0u;
        return LT_STATUS_BAD_PAYLOAD;
    }

    view->payload = &raw[LT_RAW_FRAME_HEADER_SIZE];
    view->payload_len = (uint16_t)(raw_len - LT_RAW_FRAME_MIN_SIZE);
    return LT_STATUS_OK;
}

LT_API lt_status_t lt_decode_wire_frame(
    const uint8_t *encoded_without_delimiter,
    uint16_t encoded_len,
    uint8_t *raw,
    uint16_t raw_cap,
    uint16_t *raw_len,
    lt_raw_frame_view_t *view
)
{
    lt_status_t st;

    if ((raw_len == (uint16_t *)0) || (view == (lt_raw_frame_view_t *)0)) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    *raw_len = 0u;

    st = lt_cobs_decode(encoded_without_delimiter, encoded_len, raw, raw_cap, raw_len);
    if (st != LT_STATUS_OK) {
        return st;
    }
    return lt_parse_raw_frame(raw, *raw_len, view);
}

LT_API uint16_t lt_raw_frame_len_from_payload_len(uint16_t payload_len)
{
    return (uint16_t)(LT_RAW_FRAME_MIN_SIZE + payload_len);
}

LT_API uint16_t lt_raw_prefix_len_from_payload_len(uint16_t payload_len)
{
    return (uint16_t)(LT_RAW_FRAME_HEADER_SIZE + payload_len);
}

#endif /* LITETUNE_IMPLEMENTATION */

#endif /* LT_FRAME_H */
