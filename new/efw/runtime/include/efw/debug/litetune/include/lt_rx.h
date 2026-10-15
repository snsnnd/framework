#ifndef LT_RX_H
#define LT_RX_H

#include "lt_config.h"
#include "lt_common.h"
#include "lt_utils.h"
#include "lt_cobs.h"
#include "lt_frame.h"
#include "lt_state.h"
#include "lt_runtime.h"
#include "lt_init.h"
#include "lt_params.h"
#include "lt_cmd.h"

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

LT_API lt_status_t lt_rx_from_isr(const void *data, uint16_t len);
LT_API void lt_rx_ring_process(void);
LT_API void lt_rx_reset(void);

#ifdef __cplusplus
}
#endif

#ifdef LITETUNE_IMPLEMENTATION

#include <string.h>

static uint8_t lt_rx_ring_[LT_RX_RING_BUFFER_SIZE];
static uint16_t lt_rx_head_;
static uint16_t lt_rx_tail_;
static uint8_t lt_rx_drop_until_delim_;
static uint16_t lt_rx_current_encoded_len_;
static uint16_t lt_rx_pending_overflow_;
static uint16_t lt_rx_pending_decode_error_;
static uint8_t lt_rx_encoded_frame_[LT_WIRE_FRAME_SIZE];
static uint8_t lt_rx_raw_frame_[LT_RAW_FRAME_SIZE];
static uint16_t lt_rx_process_encoded_len_;
static uint8_t lt_rx_process_drop_until_delim_;

static uint16_t lt_rx_ring_next_(uint16_t index)
{
    ++index;
    if (index >= (uint16_t)LT_RX_RING_BUFFER_SIZE) {
        index = 0u;
    }
    return index;
}

static uint8_t lt_rx_ring_empty_(void)
{
    uint8_t empty;
    LT_CRITICAL_ENTER();
    empty = (uint8_t)(lt_rx_head_ == lt_rx_tail_);
    LT_CRITICAL_EXIT();
    return empty;
}

static uint8_t lt_rx_ring_push_(uint8_t byte)
{
    uint16_t next;
    uint8_t ok = 0u;

    LT_CRITICAL_ENTER();
    next = lt_rx_ring_next_(lt_rx_tail_);
    if (next != lt_rx_head_) {
        lt_rx_ring_[lt_rx_tail_] = byte;
        lt_rx_tail_ = next;
        ok = 1u;
    }
    LT_CRITICAL_EXIT();
    return ok;
}

static uint8_t lt_rx_ring_pop_(uint8_t *byte)
{
    uint8_t ok = 0u;

    if (byte == (uint8_t *)0) {
        return 0u;
    }
    LT_CRITICAL_ENTER();
    if (lt_rx_head_ != lt_rx_tail_) {
        *byte = lt_rx_ring_[lt_rx_head_];
        lt_rx_head_ = lt_rx_ring_next_(lt_rx_head_);
        ok = 1u;
    }
    LT_CRITICAL_EXIT();
    return ok;
}

static void lt_rx_pending_inc_(uint16_t *counter)
{
    LT_CRITICAL_ENTER();
    if (*counter != 0xFFFFu) {
        *counter = (uint16_t)(*counter + 1u);
    }
    LT_CRITICAL_EXIT();
}

static uint16_t lt_rx_pending_take_(uint16_t *counter)
{
    uint16_t value;
    LT_CRITICAL_ENTER();
    value = *counter;
    *counter = 0u;
    LT_CRITICAL_EXIT();
    return value;
}

static void lt_rx_count_status_(lt_status_t status)
{
    lt_counters_t *counters = lt_state_counters();

    if (counters != (lt_counters_t *)0) {
        if (status == LT_STATUS_CRC_ERROR) {
            lt_counter_inc_u16(&counters->rx_crc_error_count);
        } else if (status == LT_STATUS_RX_OVERFLOW) {
            lt_counter_inc_u16(&counters->rx_overflow_count);
        } else if (status == LT_STATUS_BAD_PAYLOAD) {
            lt_counter_inc_u16(&counters->rx_bad_payload_count);
        } else if (status == LT_STATUS_FRAME_DECODE_ERROR) {
            lt_counter_inc_u16(&counters->rx_decode_error_count);
        } else {
            /* no counter for this status */
        }
    }
}

static void lt_rx_flush_pending_status_(void)
{
    uint16_t overflow_count = lt_rx_pending_take_(&lt_rx_pending_overflow_);
    uint16_t decode_count = lt_rx_pending_take_(&lt_rx_pending_decode_error_);

    if (overflow_count > 0u) {
        lt_rx_count_status_(LT_STATUS_RX_OVERFLOW);
        (void)lt_runtime_send_status(LT_STATUS_RX_OVERFLOW);
    }
    if (decode_count > 0u) {
        lt_rx_count_status_(LT_STATUS_FRAME_DECODE_ERROR);
        (void)lt_runtime_send_status(LT_STATUS_FRAME_DECODE_ERROR);
    }
}

static lt_status_t lt_rx_dispatch_(const lt_raw_frame_view_t *view)
{
    lt_status_t st;

    if (view == (const lt_raw_frame_view_t *)0) {
        return LT_STATUS_BAD_PAYLOAD;
    }

    switch (view->type) {
    case LT_TYPE_DISCOVER:
        st = lt_init_handle_discover(view->frame_id, view->payload, view->payload_len);
        break;
    case LT_TYPE_PARAM_SET:
        st = lt_params_handle_param_set(view->frame_id, view->payload, view->payload_len);
        break;
    case LT_TYPE_PARAM_GET:
        st = lt_params_handle_param_get(view->frame_id, view->payload, view->payload_len);
        break;
    case LT_TYPE_CMD_REQUEST:
        st = lt_cmd_handle_request(view->frame_id, view->payload, view->payload_len);
        break;
    case LT_TYPE_CMD_RESPONSE:
        st = lt_runtime_send_status(LT_STATUS_INVALID_STATE);
        break;
    case LT_TYPE_REGISTER_BEGIN:
    case LT_TYPE_REGISTER_LOG_LAYOUT:
    case LT_TYPE_REGISTER_PARAM_DESC:
    case LT_TYPE_REGISTER_CMD_DESC:
    case LT_TYPE_REGISTER_END:
    case LT_TYPE_STATUS:
    case LT_TYPE_LOG_REPORT:
    case LT_TYPE_LOG_TEXT:
    case LT_TYPE_PARAM_REPORT:
        st = lt_runtime_send_status(LT_STATUS_UNSUPPORTED);
        break;
    default:
        if (lt_type_is_standard(view->type) || lt_type_is_project_extension(view->type)) {
            st = lt_runtime_send_status(LT_STATUS_UNSUPPORTED);
        } else {
            st = lt_runtime_send_status(LT_STATUS_UNKNOWN_TYPE);
        }
        break;
    }
    return st;
}

LT_API void lt_rx_reset(void)
{
    LT_CRITICAL_ENTER();
    lt_rx_head_ = 0u;
    lt_rx_tail_ = 0u;
    lt_rx_drop_until_delim_ = 0u;
    lt_rx_current_encoded_len_ = 0u;
    lt_rx_pending_overflow_ = 0u;
    lt_rx_pending_decode_error_ = 0u;
    lt_rx_process_encoded_len_ = 0u;
    lt_rx_process_drop_until_delim_ = 0u;
    LT_CRITICAL_EXIT();
    (void)memset(lt_rx_ring_, 0, sizeof(lt_rx_ring_));
    (void)memset(lt_rx_encoded_frame_, 0, sizeof(lt_rx_encoded_frame_));
    (void)memset(lt_rx_raw_frame_, 0, sizeof(lt_rx_raw_frame_));
}

LT_API lt_status_t lt_rx_from_isr(const void *data, uint16_t len)
{
    const uint8_t *bytes = (const uint8_t *)data;
    uint16_t i;

    if (len == 0u) {
        return LT_STATUS_OK;
    }
    if (data == (const void *)0) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    if ((lt_state_get() == LT_STATE_UNINIT) || (lt_state_get() == LT_STATE_REGISTERING)) {
        return LT_STATUS_NOT_READY;
    }

    for (i = 0u; i < len; ++i) {
        uint8_t b = bytes[i];

        if (lt_rx_drop_until_delim_ != 0u) {
            if (b == 0u) {
                lt_rx_drop_until_delim_ = 0u;
                lt_rx_current_encoded_len_ = 0u;
                (void)lt_rx_ring_push_(0u);
            }
            continue;
        }

        if (b != 0u) {
            if (lt_rx_current_encoded_len_ >= (uint16_t)(LT_WIRE_FRAME_SIZE - 1u)) {
                lt_rx_drop_until_delim_ = 1u;
                lt_rx_current_encoded_len_ = 0u;
                lt_rx_process_encoded_len_ = 0u;
                lt_rx_process_drop_until_delim_ = 1u;
                lt_rx_pending_inc_(&lt_rx_pending_decode_error_);
                continue;
            }
            if (!lt_rx_ring_push_(b)) {
                lt_rx_drop_until_delim_ = 1u;
                lt_rx_current_encoded_len_ = 0u;
                lt_rx_process_encoded_len_ = 0u;
                lt_rx_process_drop_until_delim_ = 1u;
                lt_rx_pending_inc_(&lt_rx_pending_overflow_);
                continue;
            }
            ++lt_rx_current_encoded_len_;
        } else {
            if (!lt_rx_ring_push_(0u)) {
                lt_rx_pending_inc_(&lt_rx_pending_overflow_);
            }
            lt_rx_current_encoded_len_ = 0u;
        }
    }

    return LT_STATUS_OK;
}

LT_API void lt_rx_ring_process(void)
{
    uint8_t processed = 0u;

    lt_rx_flush_pending_status_();

    while (processed < (uint8_t)LT_RX_MAX_FRAMES_PER_PROCESS) {
        uint8_t found_delim = 0u;
        uint8_t b = 0u;

        while (lt_rx_ring_pop_(&b)) {
            if (b == 0u) {
                found_delim = 1u;
                break;
            }
            if (lt_rx_process_drop_until_delim_ != 0u) {
                continue;
            }
            if (lt_rx_process_encoded_len_ < (uint16_t)sizeof(lt_rx_encoded_frame_)) {
                lt_rx_encoded_frame_[lt_rx_process_encoded_len_] = b;
                ++lt_rx_process_encoded_len_;
            } else {
                lt_rx_process_encoded_len_ = 0u;
                lt_rx_process_drop_until_delim_ = 1u;
                lt_rx_count_status_(LT_STATUS_FRAME_DECODE_ERROR);
                (void)lt_runtime_send_status(LT_STATUS_FRAME_DECODE_ERROR);
            }
        }

        if (found_delim == 0u) {
            break;
        }
        if (lt_rx_process_drop_until_delim_ != 0u) {
            lt_rx_process_drop_until_delim_ = 0u;
            lt_rx_process_encoded_len_ = 0u;
            continue;
        }
        if (lt_rx_process_encoded_len_ == 0u) {
            continue;
        }

        {
            uint16_t encoded_len = lt_rx_process_encoded_len_;
            uint16_t raw_len = 0u;
            lt_raw_frame_view_t view;
            lt_status_t st;

            lt_rx_process_encoded_len_ = 0u;
            st = lt_decode_wire_frame(lt_rx_encoded_frame_,
                                      encoded_len,
                                      lt_rx_raw_frame_,
                                      (uint16_t)LT_RAW_FRAME_SIZE,
                                      &raw_len,
                                      &view);
            (void)raw_len;
            if (st == LT_STATUS_OK) {
                (void)lt_rx_dispatch_(&view);
            } else {
                lt_status_t report = (st == LT_STATUS_CRC_ERROR) ? LT_STATUS_CRC_ERROR : st;
                if ((report != LT_STATUS_CRC_ERROR) && (report != LT_STATUS_BAD_PAYLOAD)) {
                    report = LT_STATUS_FRAME_DECODE_ERROR;
                }
                lt_rx_count_status_(report);
                (void)lt_runtime_send_status(report);
            }
        }

        ++processed;

        if (lt_rx_ring_empty_()) {
            break;
        }
    }
}

#endif /* LITETUNE_IMPLEMENTATION */

#endif /* LT_RX_H */
