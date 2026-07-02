#ifndef LT_CMD_H
#define LT_CMD_H

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

LT_API lt_status_t lt_cmd_handle_request(
    lt_frame_id_t request_frame_id,
    const uint8_t *payload,
    uint16_t payload_len
);

LT_API void lt_cmd_reset(void);

#ifdef __cplusplus
}
#endif

#ifdef LITETUNE_IMPLEMENTATION

#include <string.h>

typedef struct {
    uint8_t valid;
    lt_frame_id_t request_frame_id;
    lt_cmd_id_t cmd_id;
    uint16_t request_payload_len;
    uint16_t response_payload_len;
    uint8_t request_payload[LT_RAW_FRAME_SIZE - LT_RAW_FRAME_MIN_SIZE];
    uint8_t response_payload[LT_RAW_FRAME_SIZE - LT_RAW_FRAME_MIN_SIZE];
} lt_cmd_response_cache_t;

static uint8_t lt_cmd_response_payload_[LT_RAW_FRAME_SIZE];
static uint8_t lt_cmd_user_response_[LT_CMD_RESPONSE_BUFFER_SIZE];
static lt_cmd_response_cache_t lt_cmd_response_cache_;

static uint16_t lt_cmd_max_payload_len_(void)
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

static const lt_cmd_desc_t *lt_cmd_find_cmd_(lt_cmd_id_t cmd_id)
{
    const lt_cmd_registry_t *registry = lt_state_cmd_registry();
    uint16_t i;

    if ((registry == (const lt_cmd_registry_t *)0) ||
        ((registry->cmd_count > 0u) && (registry->cmds == (const lt_cmd_desc_t *)0))) {
        return (const lt_cmd_desc_t *)0;
    }
    for (i = 0u; i < lt_registry_cmd_count(registry); ++i) {
        if (registry->cmds[i].cmd_id == cmd_id) {
            return &registry->cmds[i];
        }
    }
    return (const lt_cmd_desc_t *)0;
}

static void lt_cmd_cache_store_(
    lt_frame_id_t request_frame_id,
    lt_cmd_id_t cmd_id,
    const uint8_t *request_payload,
    uint16_t request_payload_len,
    const uint8_t *response_payload,
    uint16_t response_payload_len
)
{
    if (((request_payload == (const uint8_t *)0) && (request_payload_len > 0u)) ||
        ((response_payload == (const uint8_t *)0) && (response_payload_len > 0u)) ||
        (request_payload_len > (uint16_t)sizeof(lt_cmd_response_cache_.request_payload)) ||
        (response_payload_len > (uint16_t)sizeof(lt_cmd_response_cache_.response_payload))) {
        lt_cmd_response_cache_.valid = 0u;
        return;
    }

    if (request_payload_len > 0u) {
        (void)memcpy(lt_cmd_response_cache_.request_payload, request_payload, (size_t)request_payload_len);
    }
    if (response_payload_len > 0u) {
        (void)memcpy(lt_cmd_response_cache_.response_payload, response_payload, (size_t)response_payload_len);
    }
    lt_cmd_response_cache_.request_payload_len = request_payload_len;
    lt_cmd_response_cache_.response_payload_len = response_payload_len;
    lt_cmd_response_cache_.request_frame_id = request_frame_id;
    lt_cmd_response_cache_.cmd_id = cmd_id;
    lt_cmd_response_cache_.valid = 1u;
}

static lt_status_t lt_cmd_send_response_payload_(
    lt_frame_id_t request_frame_id,
    lt_cmd_id_t cmd_id,
    lt_status_t status,
    const uint8_t *user_payload,
    uint16_t user_payload_len,
    uint8_t update_cache,
    const uint8_t *request_payload,
    uint16_t request_payload_len
)
{
    lt_writer_t w;
    lt_status_t st;
    uint16_t cap = lt_cmd_max_payload_len_();

    if ((user_payload == (const uint8_t *)0) && (user_payload_len > 0u)) {
        user_payload_len = 0u;
        status = LT_STATUS_BAD_PAYLOAD;
    }

    lt_writer_init(&w, lt_cmd_response_payload_, cap);
    st = lt_write_u64_le(&w, request_frame_id);
    if (st != LT_STATUS_OK) {
        return st;
    }
    st = lt_write_u16_le(&w, cmd_id);
    if (st != LT_STATUS_OK) {
        return st;
    }
    st = lt_write_u8(&w, (uint8_t)status);
    if (st != LT_STATUS_OK) {
        return st;
    }
    st = lt_write_bytes(&w, user_payload, user_payload_len);
    if (st != LT_STATUS_OK) {
        return st;
    }

    st = lt_tx_enqueue_frame((uint8_t)LT_TYPE_CMD_RESPONSE, lt_cmd_response_payload_, w.pos);
    if ((st == LT_STATUS_OK) && (update_cache != 0u)) {
        lt_cmd_cache_store_(request_frame_id,
                            cmd_id,
                            request_payload,
                            request_payload_len,
                            lt_cmd_response_payload_,
                            w.pos);
    }
    return st;
}

static lt_status_t lt_cmd_send_response_(
    lt_frame_id_t request_frame_id,
    lt_cmd_id_t cmd_id,
    lt_status_t status,
    const uint8_t *user_payload,
    uint16_t user_payload_len,
    const uint8_t *request_payload,
    uint16_t request_payload_len
)
{
    lt_status_t st;

    st = lt_cmd_send_response_payload_(request_frame_id,
                                       cmd_id,
                                       status,
                                       user_payload,
                                       user_payload_len,
                                       1u,
                                       request_payload,
                                       request_payload_len);
    if (st == LT_STATUS_TOO_LARGE) {
        st = lt_cmd_send_response_payload_(request_frame_id,
                                           cmd_id,
                                           LT_STATUS_TOO_LARGE,
                                           (const uint8_t *)0,
                                           0u,
                                           1u,
                                           request_payload,
                                           request_payload_len);
    }
    return st;
}

static lt_status_t lt_cmd_cache_handle_duplicate_(
    lt_frame_id_t request_frame_id,
    lt_cmd_id_t cmd_id,
    const uint8_t *request_payload,
    uint16_t request_payload_len,
    uint8_t *handled
)
{
    if (handled == (uint8_t *)0) {
        return LT_STATUS_BAD_PAYLOAD;
    }
    *handled = 0u;

    if ((lt_cmd_response_cache_.valid == 0u) ||
        (lt_cmd_response_cache_.request_frame_id != request_frame_id)) {
        return LT_STATUS_OK;
    }

    *handled = 1u;
    if ((request_payload_len == lt_cmd_response_cache_.request_payload_len) &&
        ((request_payload_len == 0u) ||
         ((request_payload != (const uint8_t *)0) &&
          (memcmp(request_payload, lt_cmd_response_cache_.request_payload, (size_t)request_payload_len) == 0)))) {
        return lt_tx_enqueue_frame((uint8_t)LT_TYPE_CMD_RESPONSE,
                                   lt_cmd_response_cache_.response_payload,
                                   lt_cmd_response_cache_.response_payload_len);
    }

    return lt_cmd_send_response_payload_(request_frame_id,
                                         cmd_id,
                                         LT_STATUS_CONFLICT,
                                         (const uint8_t *)0,
                                         0u,
                                         0u,
                                         request_payload,
                                         request_payload_len);
}

LT_API void lt_cmd_reset(void)
{
    (void)memset(lt_cmd_response_payload_, 0, sizeof(lt_cmd_response_payload_));
    (void)memset(lt_cmd_user_response_, 0, sizeof(lt_cmd_user_response_));
    (void)memset(&lt_cmd_response_cache_, 0, sizeof(lt_cmd_response_cache_));
}

LT_API lt_status_t lt_cmd_handle_request(
    lt_frame_id_t request_frame_id,
    const uint8_t *payload,
    uint16_t payload_len
)
{
    lt_reader_t r;
    lt_cmd_id_t cmd_id = 0u;
    const uint8_t *user_payload = (const uint8_t *)0;
    uint16_t user_payload_len = 0u;
    const lt_cmd_desc_t *cmd;
    lt_status_t st;
    uint16_t resp_len = 0u;
    uint8_t cache_handled = 0u;

    if ((payload == (const uint8_t *)0) && (payload_len > 0u)) {
        return lt_cmd_send_response_(request_frame_id,
                                     0u,
                                     LT_STATUS_BAD_PAYLOAD,
                                     (const uint8_t *)0,
                                     0u,
                                     payload,
                                     payload_len);
    }

    if (payload_len >= 2u) {
        lt_reader_init(&r, payload, payload_len);
        st = lt_read_u16_le(&r, &cmd_id);
        if (st != LT_STATUS_OK) {
            return lt_cmd_send_response_(request_frame_id,
                                         0u,
                                         LT_STATUS_BAD_PAYLOAD,
                                         (const uint8_t *)0,
                                         0u,
                                         payload,
                                         payload_len);
        }
        user_payload = (lt_reader_remaining(&r) > 0u) ? &payload[r.pos] : (const uint8_t *)0;
        user_payload_len = lt_reader_remaining(&r);
    }

    st = lt_cmd_cache_handle_duplicate_(request_frame_id, cmd_id, payload, payload_len, &cache_handled);
    if (cache_handled != 0u) {
        return st;
    }

    if (payload_len < 2u) {
        return lt_cmd_send_response_(request_frame_id,
                                     0u,
                                     LT_STATUS_BAD_PAYLOAD,
                                     (const uint8_t *)0,
                                     0u,
                                     payload,
                                     payload_len);
    }

    if (lt_state_get() != LT_STATE_CONNECTED) {
        return lt_cmd_send_response_(request_frame_id,
                                     cmd_id,
                                     LT_STATUS_NOT_READY,
                                     (const uint8_t *)0,
                                     0u,
                                     payload,
                                     payload_len);
    }
    if (!lt_state_feature_enabled((uint32_t)LT_FEATURE_CMD)) {
        return lt_cmd_send_response_(request_frame_id,
                                     cmd_id,
                                     LT_STATUS_UNSUPPORTED,
                                     (const uint8_t *)0,
                                     0u,
                                     payload,
                                     payload_len);
    }

    cmd = lt_cmd_find_cmd_(cmd_id);
    if (cmd == (const lt_cmd_desc_t *)0) {
        return lt_cmd_send_response_(request_frame_id,
                                     cmd_id,
                                     LT_STATUS_NOT_FOUND,
                                     (const uint8_t *)0,
                                     0u,
                                     payload,
                                     payload_len);
    }
    if ((cmd->cmd_flags & (uint8_t)LT_CMD_FLAG_HOST_TO_MCU) == 0u) {
        return lt_cmd_send_response_(request_frame_id,
                                     cmd_id,
                                     LT_STATUS_DENIED,
                                     (const uint8_t *)0,
                                     0u,
                                     payload,
                                     payload_len);
    }
    if (cmd->callback == (lt_cmd_callback_t)0) {
        return lt_cmd_send_response_(request_frame_id,
                                     cmd_id,
                                     LT_STATUS_EXEC_ERROR,
                                     (const uint8_t *)0,
                                     0u,
                                     payload,
                                     payload_len);
    }

    resp_len = 0u;
    st = cmd->callback(user_payload,
                       user_payload_len,
                       lt_cmd_user_response_,
                       (uint16_t)LT_CMD_RESPONSE_BUFFER_SIZE,
                       &resp_len,
                       cmd->user_ctx);
    if (resp_len > (uint16_t)LT_CMD_RESPONSE_BUFFER_SIZE) {
        return lt_cmd_send_response_(request_frame_id,
                                     cmd_id,
                                     LT_STATUS_TOO_LARGE,
                                     (const uint8_t *)0,
                                     0u,
                                     payload,
                                     payload_len);
    }
    if (st == LT_STATUS_TOO_LARGE) {
        return lt_cmd_send_response_(request_frame_id,
                                     cmd_id,
                                     LT_STATUS_TOO_LARGE,
                                     (const uint8_t *)0,
                                     0u,
                                     payload,
                                     payload_len);
    }
    return lt_cmd_send_response_(request_frame_id,
                                 cmd_id,
                                 st,
                                 (resp_len > 0u) ? lt_cmd_user_response_ : (const uint8_t *)0,
                                 resp_len,
                                 payload,
                                 payload_len);
}

#endif /* LITETUNE_IMPLEMENTATION */

#endif /* LT_CMD_H */
