/**
 * @file    pid_scope.h
 * @brief   Lightweight PID telemetry protocol helpers for EFW ground station.
 *
 * The frame format mirrors tools/efw_telemetry.py:
 *   SOF(0xAA,0x55) + type + payload_len_le16 + payload + crc16_le
 * CRC16 is calculated over type + payload_len + payload.
 */

#ifndef EFW_DEBUG_PID_SCOPE_H
#define EFW_DEBUG_PID_SCOPE_H

#include "efw/core/common.h"
#include "efw/core/config.h"

#ifdef __cplusplus
extern "C" {
#endif

#define EFW_PID_SCOPE_SOF0          0xAAu
#define EFW_PID_SCOPE_SOF1          0x55u
#define EFW_PID_SCOPE_TYPE_TELEMETRY 0x01u
#define EFW_PID_SCOPE_TYPE_PARAM_SET 0x02u
#define EFW_PID_SCOPE_MAX_FRAME     64u

typedef struct {
    uint8_t device_id;
    uint8_t channel_id;
    uint32_t time_ms;
    float target;
    float feedback;
    float error;
    float output;
    float kp;
    float ki;
    float kd;
    float extra1;
    float extra2;
} efw_pid_scope_telemetry_t;

typedef struct {
    uint8_t device_id;
    uint8_t channel_id;
    float kp;
    float ki;
    float kd;
} efw_pid_scope_param_set_t;

uint16_t efw_pid_scope_crc16(const uint8_t *data, uint16_t len);
efw_status_t efw_pid_scope_encode_telemetry(const efw_pid_scope_telemetry_t *telemetry,
                                            uint8_t *out_frame,
                                            uint16_t out_cap,
                                            uint16_t *out_len);
efw_status_t efw_pid_scope_parse_param_set_frame(const uint8_t *frame,
                                                 uint16_t frame_len,
                                                 efw_pid_scope_param_set_t *out_param);

#ifdef __cplusplus
}
#endif

#endif
