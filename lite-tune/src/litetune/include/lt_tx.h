#ifndef LT_TX_H
#define LT_TX_H

#include "lt_config.h"
#include "lt_common.h"
#include "lt_state.h"
#include "lt_utils.h"
#include "lt_cobs.h"

#include <stdint.h>
#include <stddef.h>


#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    LT_TX_SLOT_FREE = 0,
    LT_TX_SLOT_QUEUED,
    LT_TX_SLOT_SENDING
} lt_tx_slot_state_t;

typedef struct {
    uint8_t queue_head;
    uint8_t queue_tail;
    uint8_t queue_count;
    uint8_t slot_state[LT_TX_SLOT_POOL_SIZE];
    uint8_t status_pending[256];
} lt_tx_checkpoint_t;

LT_API void lt_tx_reset(void);
LT_API lt_status_t lt_tx_enqueue_frame(uint8_t type, const uint8_t *payload, uint16_t payload_len);
LT_API void lt_tx_try_send(void);
LT_API void lt_send_complete(void);
LT_API lt_status_t lt_tx_begin_atomic(uint8_t expected_frames, lt_tx_checkpoint_t *checkpoint);
LT_API void lt_tx_rollback_atomic(const lt_tx_checkpoint_t *checkpoint);
LT_API void lt_tx_commit_atomic(const lt_tx_checkpoint_t *checkpoint);

#ifdef __cplusplus
}
#endif

#ifdef LITETUNE_IMPLEMENTATION

#include <string.h>

typedef struct {
    lt_tx_slot_state_t state;
    uint8_t type;
    uint8_t status_code;
    uint8_t is_status;
    uint16_t raw_prefix_len;
    uint8_t raw_prefix[LT_RAW_FRAME_SIZE - LT_RAW_FRAME_CRC_SIZE];
} lt_tx_slot_t;

static lt_tx_slot_t lt_tx_slots_[LT_TX_SLOT_POOL_SIZE];
static uint8_t lt_tx_queue_[LT_TX_SEND_QUEUE_SIZE];
static uint8_t lt_tx_queue_head_;
static uint8_t lt_tx_queue_tail_;
static uint8_t lt_tx_queue_count_;
static uint8_t lt_tx_sending_indices_[LT_TX_SENDING_FRAME_COUNT];
static uint8_t lt_tx_sending_count_;
static uint8_t lt_tx_sending_busy_;
static uint16_t lt_tx_sending_len_;
static uint8_t lt_tx_sending_buffer_[LT_TX_SENDING_BUFFER_SIZE];
static uint8_t lt_tx_raw_work_[LT_RAW_FRAME_SIZE];
static uint8_t lt_tx_status_pending_[256];

static void lt_tx_inc_drop_(void)
{
    lt_counters_t *counters = lt_state_counters();
    if (counters != (lt_counters_t *)0) {
        lt_counter_inc_u16(&counters->tx_drop_count);
    }
}

static void lt_tx_release_slot_(uint8_t slot_index)
{
    lt_tx_slot_t *slot;
    if (slot_index >= (uint8_t)LT_TX_SLOT_POOL_SIZE) {
        return;
    }
    slot = &lt_tx_slots_[slot_index];
    if (slot->is_status != 0u) {
        lt_tx_status_pending_[slot->status_code] = 0u;
    }
    slot->state = LT_TX_SLOT_FREE;
    slot->type = (uint8_t)LT_TYPE_INVALID;
    slot->status_code = 0u;
    slot->is_status = 0u;
    slot->raw_prefix_len = 0u;
}

static uint8_t lt_tx_find_free_slot_(void)
{
    uint8_t i;
    for (i = 0u; i < (uint8_t)LT_TX_SLOT_POOL_SIZE; ++i) {
        if (lt_tx_slots_[i].state == LT_TX_SLOT_FREE) {
            return i;
        }
    }
    return 0xFFu;
}

static uint8_t lt_tx_free_slot_count_(void)
{
    uint8_t i;
    uint8_t count = 0u;
    for (i = 0u; i < (uint8_t)LT_TX_SLOT_POOL_SIZE; ++i) {
        if (lt_tx_slots_[i].state == LT_TX_SLOT_FREE) {
            count = (uint8_t)(count + 1u);
        }
    }
    return count;
}

static lt_status_t lt_tx_build_prefix_(lt_tx_slot_t *slot, uint8_t type, lt_frame_id_t frame_id, const uint8_t *payload, uint16_t payload_len)
{
    lt_writer_t w;
    lt_status_t st;

    lt_writer_init(&w, slot->raw_prefix, (uint16_t)sizeof(slot->raw_prefix));
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
    slot->raw_prefix_len = w.pos;
    return LT_STATUS_OK;
}

LT_API void lt_tx_reset(void)
{
    uint16_t i;
    LT_CRITICAL_ENTER();
    for (i = 0u; i < (uint16_t)LT_TX_SLOT_POOL_SIZE; ++i) {
        lt_tx_slots_[i].state = LT_TX_SLOT_FREE;
        lt_tx_slots_[i].type = (uint8_t)LT_TYPE_INVALID;
        lt_tx_slots_[i].status_code = 0u;
        lt_tx_slots_[i].is_status = 0u;
        lt_tx_slots_[i].raw_prefix_len = 0u;
    }
    for (i = 0u; i < 256u; ++i) {
        lt_tx_status_pending_[i] = 0u;
    }
    lt_tx_queue_head_ = 0u;
    lt_tx_queue_tail_ = 0u;
    lt_tx_queue_count_ = 0u;
    lt_tx_sending_count_ = 0u;
    lt_tx_sending_busy_ = 0u;
    lt_tx_sending_len_ = 0u;
    LT_CRITICAL_EXIT();
}

LT_API lt_status_t lt_tx_enqueue_frame(uint8_t type, const uint8_t *payload, uint16_t payload_len)
{
    const lt_config_t *config;
    lt_frame_id_t frame_id;
    uint16_t raw_prefix_len;
    uint16_t raw_frame_len;
    uint16_t peer_max;
    uint8_t slot_index;
    uint8_t is_status = 0u;
    uint8_t status_code = 0u;
    lt_status_t st;

    if ((payload == (const uint8_t *)0) && (payload_len > 0u)) {
        return LT_STATUS_BAD_PAYLOAD;
    }

    raw_prefix_len = (uint16_t)(LT_RAW_FRAME_HEADER_SIZE + payload_len);
    raw_frame_len = (uint16_t)(raw_prefix_len + LT_RAW_FRAME_CRC_SIZE);
    if ((raw_prefix_len < LT_RAW_FRAME_HEADER_SIZE) || (raw_frame_len < raw_prefix_len) || (raw_frame_len > (uint16_t)LT_RAW_FRAME_SIZE)) {
        return LT_STATUS_TOO_LARGE;
    }

    peer_max = lt_state_peer_max_decoded_frame();
    if ((peer_max != 0u) && (raw_frame_len > peer_max)) {
        return LT_STATUS_TOO_LARGE;
    }

    if ((type == (uint8_t)LT_TYPE_STATUS) && (payload_len == 1u) && (payload != (const uint8_t *)0)) {
        is_status = 1u;
        status_code = payload[0];
        LT_CRITICAL_ENTER();
        if (lt_tx_status_pending_[status_code] != 0u) {
            LT_CRITICAL_EXIT();
            return LT_STATUS_OK;
        }
        LT_CRITICAL_EXIT();
    }

    config = lt_state_config();
    if ((config == (const lt_config_t *)0) || (config->next_frame_id == (lt_next_frame_id_fn_t)0)) {
        return LT_STATUS_NOT_READY;
    }

    frame_id = config->next_frame_id();
    if (frame_id == (lt_frame_id_t)0) {
        return LT_STATUS_BAD_PAYLOAD;
    }

    LT_CRITICAL_ENTER();
    if (lt_tx_queue_count_ >= (uint8_t)LT_TX_SEND_QUEUE_SIZE) {
        LT_CRITICAL_EXIT();
        lt_tx_inc_drop_();
        return LT_STATUS_BUSY;
    }
    slot_index = lt_tx_find_free_slot_();
    if (slot_index == 0xFFu) {
        LT_CRITICAL_EXIT();
        lt_tx_inc_drop_();
        return LT_STATUS_BUSY;
    }
    if ((is_status != 0u) && (lt_tx_status_pending_[status_code] != 0u)) {
        LT_CRITICAL_EXIT();
        return LT_STATUS_OK;
    }

    lt_tx_slots_[slot_index].state = LT_TX_SLOT_QUEUED;
    lt_tx_slots_[slot_index].type = type;
    lt_tx_slots_[slot_index].status_code = status_code;
    lt_tx_slots_[slot_index].is_status = is_status;
    st = lt_tx_build_prefix_(&lt_tx_slots_[slot_index], type, frame_id, payload, payload_len);
    if (st != LT_STATUS_OK) {
        lt_tx_release_slot_(slot_index);
        LT_CRITICAL_EXIT();
        return st;
    }

    lt_tx_queue_[lt_tx_queue_tail_] = slot_index;
    lt_tx_queue_tail_ = (uint8_t)((lt_tx_queue_tail_ + 1u) % (uint8_t)LT_TX_SEND_QUEUE_SIZE);
    lt_tx_queue_count_ = (uint8_t)(lt_tx_queue_count_ + 1u);
    if (is_status != 0u) {
        lt_tx_status_pending_[status_code] = 1u;
    }
    LT_CRITICAL_EXIT();

    return LT_STATUS_OK;
}

LT_API void lt_tx_try_send(void)
{
    const lt_config_t *config;
    uint8_t encoded_count = 0u;
    uint8_t queue_pos;
    uint16_t out_len = 0u;
    lt_status_t st;

    LT_CRITICAL_ENTER();
    if ((lt_tx_sending_busy_ != 0u) || (lt_tx_queue_count_ == 0u)) {
        LT_CRITICAL_EXIT();
        return;
    }
    LT_CRITICAL_EXIT();

    config = lt_state_config();
    if ((config == (const lt_config_t *)0) || (config->send == (lt_send_fn_t)0)) {
        return;
    }

    lt_tx_sending_len_ = 0u;
    queue_pos = lt_tx_queue_head_;

    while ((encoded_count < (uint8_t)LT_TX_SENDING_FRAME_COUNT) && (encoded_count < lt_tx_queue_count_)) {
        uint8_t slot_index = lt_tx_queue_[queue_pos];
        lt_tx_slot_t *slot = &lt_tx_slots_[slot_index];
        uint16_t raw_len;
        uint16_t crc;
        uint16_t encoded_len = 0u;
        uint16_t remaining;
        uint16_t needed;

        if (slot->state != LT_TX_SLOT_QUEUED) {
            break;
        }

        raw_len = (uint16_t)(slot->raw_prefix_len + LT_RAW_FRAME_CRC_SIZE);
        needed = (uint16_t)(lt_cobs_encoded_max_len(raw_len) + 1u);
        remaining = (uint16_t)((uint16_t)LT_TX_SENDING_BUFFER_SIZE - lt_tx_sending_len_);
        if ((needed > remaining) || (raw_len > (uint16_t)LT_RAW_FRAME_SIZE)) {
            break;
        }

        (void)memcpy(lt_tx_raw_work_, slot->raw_prefix, (size_t)slot->raw_prefix_len);
        crc = lt_crc16_mcrf4xx(slot->raw_prefix, slot->raw_prefix_len);
        lt_tx_raw_work_[slot->raw_prefix_len] = (uint8_t)(crc & 0xFFu);
        lt_tx_raw_work_[(uint16_t)(slot->raw_prefix_len + 1u)] = (uint8_t)((crc >> 8) & 0xFFu);

        st = lt_cobs_encode(
            lt_tx_raw_work_,
            raw_len,
            &lt_tx_sending_buffer_[lt_tx_sending_len_],
            (uint16_t)(remaining - 1u),
            &encoded_len
        );
        if (st != LT_STATUS_OK) {
            break;
        }
        lt_tx_sending_len_ = (uint16_t)(lt_tx_sending_len_ + encoded_len);
        lt_tx_sending_buffer_[lt_tx_sending_len_] = 0u;
        lt_tx_sending_len_ = (uint16_t)(lt_tx_sending_len_ + 1u);
        lt_tx_sending_indices_[encoded_count] = slot_index;
        encoded_count = (uint8_t)(encoded_count + 1u);
        queue_pos = (uint8_t)((queue_pos + 1u) % (uint8_t)LT_TX_SEND_QUEUE_SIZE);
    }

    if (encoded_count == 0u) {
        return;
    }

    LT_CRITICAL_ENTER();
    for (out_len = 0u; out_len < (uint16_t)encoded_count; ++out_len) {
        uint8_t slot_index = lt_tx_sending_indices_[out_len];
        lt_tx_slots_[slot_index].state = LT_TX_SLOT_SENDING;
    }
    lt_tx_queue_head_ = (uint8_t)((lt_tx_queue_head_ + encoded_count) % (uint8_t)LT_TX_SEND_QUEUE_SIZE);
    lt_tx_queue_count_ = (uint8_t)(lt_tx_queue_count_ - encoded_count);
    lt_tx_sending_count_ = encoded_count;
    lt_tx_sending_busy_ = 1u;
    LT_CRITICAL_EXIT();

    st = config->send(lt_tx_sending_buffer_, lt_tx_sending_len_);
    if (st != LT_STATUS_OK) {
        LT_CRITICAL_ENTER();
        for (out_len = 0u; out_len < (uint16_t)lt_tx_sending_count_; ++out_len) {
            lt_tx_release_slot_(lt_tx_sending_indices_[out_len]);
            lt_tx_inc_drop_();
        }
        lt_tx_sending_count_ = 0u;
        lt_tx_sending_busy_ = 0u;
        lt_tx_sending_len_ = 0u;
        LT_CRITICAL_EXIT();
    }
}

LT_API void lt_send_complete(void)
{
    uint8_t i;
    LT_CRITICAL_ENTER();
    for (i = 0u; i < lt_tx_sending_count_; ++i) {
        lt_tx_release_slot_(lt_tx_sending_indices_[i]);
    }
    lt_tx_sending_count_ = 0u;
    lt_tx_sending_busy_ = 0u;
    lt_tx_sending_len_ = 0u;
    LT_CRITICAL_EXIT();
}

LT_API lt_status_t lt_tx_begin_atomic(uint8_t expected_frames, lt_tx_checkpoint_t *checkpoint)
{
    uint16_t i;
    if (checkpoint == (lt_tx_checkpoint_t *)0) {
        return LT_STATUS_BAD_PAYLOAD;
    }

    LT_CRITICAL_ENTER();
    if (((uint16_t)expected_frames > (uint16_t)lt_tx_free_slot_count_()) ||
        ((uint16_t)expected_frames > ((uint16_t)LT_TX_SEND_QUEUE_SIZE - (uint16_t)lt_tx_queue_count_))) {
        LT_CRITICAL_EXIT();
        return LT_STATUS_BUSY;
    }

    checkpoint->queue_head = lt_tx_queue_head_;
    checkpoint->queue_tail = lt_tx_queue_tail_;
    checkpoint->queue_count = lt_tx_queue_count_;
    for (i = 0u; i < (uint16_t)LT_TX_SLOT_POOL_SIZE; ++i) {
        checkpoint->slot_state[i] = (uint8_t)lt_tx_slots_[i].state;
    }
    for (i = 0u; i < 256u; ++i) {
        checkpoint->status_pending[i] = lt_tx_status_pending_[i];
    }
    LT_CRITICAL_EXIT();
    return LT_STATUS_OK;
}

LT_API void lt_tx_rollback_atomic(const lt_tx_checkpoint_t *checkpoint)
{
    uint16_t i;
    if (checkpoint == (const lt_tx_checkpoint_t *)0) {
        return;
    }

    LT_CRITICAL_ENTER();
    lt_tx_queue_head_ = checkpoint->queue_head;
    lt_tx_queue_tail_ = checkpoint->queue_tail;
    lt_tx_queue_count_ = checkpoint->queue_count;
    for (i = 0u; i < (uint16_t)LT_TX_SLOT_POOL_SIZE; ++i) {
        if ((lt_tx_slots_[i].state != LT_TX_SLOT_FREE) && (checkpoint->slot_state[i] == (uint8_t)LT_TX_SLOT_FREE)) {
            lt_tx_release_slot_((uint8_t)i);
        }
        lt_tx_slots_[i].state = (lt_tx_slot_state_t)checkpoint->slot_state[i];
    }
    for (i = 0u; i < 256u; ++i) {
        lt_tx_status_pending_[i] = checkpoint->status_pending[i];
    }
    LT_CRITICAL_EXIT();
}

LT_API void lt_tx_commit_atomic(const lt_tx_checkpoint_t *checkpoint)
{
    (void)checkpoint;
}

#endif /* LITETUNE_IMPLEMENTATION */

#endif /* LT_TX_H */
