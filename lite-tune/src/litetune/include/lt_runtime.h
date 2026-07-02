#ifndef LT_RUNTIME_H
#define LT_RUNTIME_H

#include "lt_config.h"
#include "lt_common.h"
#include "lt_state.h"
#include "lt_utils.h"
#include "lt_tx.h"

#include <stdint.h>
#include <stddef.h>


#ifdef __cplusplus
extern "C" {
#endif

LT_API lt_status_t lt_runtime_send_status(lt_status_t status_code);
LT_API lt_status_t lt_log_text(uint8_t level, const char *text);

#ifdef __cplusplus
}
#endif

#ifdef LITETUNE_IMPLEMENTATION

LT_API lt_status_t lt_runtime_send_status(lt_status_t status_code)
{
    uint8_t payload[1];
    payload[0] = (uint8_t)status_code;
    return lt_tx_enqueue_frame((uint8_t)LT_TYPE_STATUS, payload, (uint16_t)sizeof(payload));
}

LT_API lt_status_t lt_log_text(uint8_t level, const char *text)
{
    uint8_t payload[1u + 1u + 255u];
    lt_writer_t w;
    lt_status_t st;

    if (lt_state_get() != LT_STATE_CONNECTED) {
        return LT_STATUS_INVALID_STATE;
    }
    if (lt_state_feature_enabled((uint32_t)LT_FEATURE_LOG_TEXT) == 0u) {
        return LT_STATUS_UNSUPPORTED;
    }
    if (text == (const char *)0) {
        return LT_STATUS_BAD_PAYLOAD;
    }

    lt_writer_init(&w, payload, (uint16_t)sizeof(payload));
    st = lt_write_u8(&w, level);
    if (st != LT_STATUS_OK) {
        return st;
    }
    st = lt_write_str8(&w, text);
    if (st != LT_STATUS_OK) {
        return st;
    }

    return lt_tx_enqueue_frame((uint8_t)LT_TYPE_LOG_TEXT, payload, w.pos);
}

#endif /* LITETUNE_IMPLEMENTATION */

#endif /* LT_RUNTIME_H */
