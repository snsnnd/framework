/**
 * @file    pid_scope.c
 * @brief   EFW PID telemetry frame encoder and PARAM_SET decoder.
 */

#include "efw/debug/pid_scope.h"

#if EFW_ENABLE_PID_SCOPE

#define EFW_PID_SCOPE_HEADER_LEN 5u
#define EFW_PID_SCOPE_CRC_LEN 2u
#define EFW_PID_SCOPE_TELEMETRY_PAYLOAD_LEN 42u
#define EFW_PID_SCOPE_PARAM_SET_PAYLOAD_LEN 14u

static void put_u16_le(uint8_t *buf, uint16_t value) {
    buf[0] = (uint8_t)(value & 0xFFu);
    buf[1] = (uint8_t)((value >> 8) & 0xFFu);
}

static uint16_t get_u16_le(const uint8_t *buf) {
    return (uint16_t)buf[0] | ((uint16_t)buf[1] << 8);
}

static void put_u32_le(uint8_t *buf, uint32_t value) {
    buf[0] = (uint8_t)(value & 0xFFu);
    buf[1] = (uint8_t)((value >> 8) & 0xFFu);
    buf[2] = (uint8_t)((value >> 16) & 0xFFu);
    buf[3] = (uint8_t)((value >> 24) & 0xFFu);
}

static uint32_t get_u32_le(const uint8_t *buf) {
    return (uint32_t)buf[0] |
           ((uint32_t)buf[1] << 8) |
           ((uint32_t)buf[2] << 16) |
           ((uint32_t)buf[3] << 24);
}

static void put_float_le(uint8_t *buf, float value) {
    union { float f; uint32_t u; } conv;
    conv.f = value;
    put_u32_le(buf, conv.u);
}

static float get_float_le(const uint8_t *buf) {
    union { float f; uint32_t u; } conv;
    conv.u = get_u32_le(buf);
    return conv.f;
}

uint16_t efw_pid_scope_crc16(const uint8_t *data, uint16_t len) {
    uint16_t crc = 0xFFFFu;
    uint16_t i;
    uint8_t bit;

    if (!data && len > 0u) return 0u;

    for (i = 0u; i < len; ++i) {
        crc ^= data[i];
        for (bit = 0u; bit < 8u; ++bit) {
            if (crc & 1u) {
                crc = (uint16_t)((crc >> 1) ^ 0xA001u);
            } else {
                crc >>= 1;
            }
        }
    }
    return crc;
}

efw_status_t efw_pid_scope_encode_telemetry(const efw_pid_scope_telemetry_t *telemetry,
                                            uint8_t *out_frame,
                                            uint16_t out_cap,
                                            uint16_t *out_len) {
    uint8_t *payload;
    uint16_t crc;
    uint16_t total_len = EFW_PID_SCOPE_HEADER_LEN + EFW_PID_SCOPE_TELEMETRY_PAYLOAD_LEN + EFW_PID_SCOPE_CRC_LEN;

    if (!telemetry || !out_frame || !out_len) return EFW_ERR_INVALID;
    if (out_cap < total_len) return EFW_ERR_RANGE;

    out_frame[0] = EFW_PID_SCOPE_SOF0;
    out_frame[1] = EFW_PID_SCOPE_SOF1;
    out_frame[2] = EFW_PID_SCOPE_TYPE_TELEMETRY;
    put_u16_le(&out_frame[3], EFW_PID_SCOPE_TELEMETRY_PAYLOAD_LEN);

    payload = &out_frame[EFW_PID_SCOPE_HEADER_LEN];
    payload[0] = telemetry->device_id;
    payload[1] = telemetry->channel_id;
    put_u32_le(&payload[2], telemetry->time_ms);
    put_float_le(&payload[6], telemetry->target);
    put_float_le(&payload[10], telemetry->feedback);
    put_float_le(&payload[14], telemetry->error);
    put_float_le(&payload[18], telemetry->output);
    put_float_le(&payload[22], telemetry->kp);
    put_float_le(&payload[26], telemetry->ki);
    put_float_le(&payload[30], telemetry->kd);
    put_float_le(&payload[34], telemetry->extra1);
    put_float_le(&payload[38], telemetry->extra2);

    crc = efw_pid_scope_crc16(&out_frame[2], (uint16_t)(1u + 2u + EFW_PID_SCOPE_TELEMETRY_PAYLOAD_LEN));
    put_u16_le(&out_frame[EFW_PID_SCOPE_HEADER_LEN + EFW_PID_SCOPE_TELEMETRY_PAYLOAD_LEN], crc);
    *out_len = total_len;
    return EFW_OK;
}

efw_status_t efw_pid_scope_parse_param_set_frame(const uint8_t *frame,
                                                 uint16_t frame_len,
                                                 efw_pid_scope_param_set_t *out_param) {
    const uint8_t *payload;
    uint16_t payload_len;
    uint16_t expected_len;
    uint16_t got_crc;
    uint16_t calc_crc;

    if (!frame || !out_param) return EFW_ERR_INVALID;
    if (frame_len < (EFW_PID_SCOPE_HEADER_LEN + EFW_PID_SCOPE_CRC_LEN)) return EFW_ERR_RANGE;
    if (frame[0] != EFW_PID_SCOPE_SOF0 || frame[1] != EFW_PID_SCOPE_SOF1) return EFW_ERR_INVALID;
    if (frame[2] != EFW_PID_SCOPE_TYPE_PARAM_SET) return EFW_ERR_UNSUPPORTED;

    payload_len = get_u16_le(&frame[3]);
    if (payload_len != EFW_PID_SCOPE_PARAM_SET_PAYLOAD_LEN) return EFW_ERR_RANGE;

    expected_len = EFW_PID_SCOPE_HEADER_LEN + payload_len + EFW_PID_SCOPE_CRC_LEN;
    if (frame_len != expected_len) return EFW_ERR_RANGE;

    got_crc = get_u16_le(&frame[EFW_PID_SCOPE_HEADER_LEN + payload_len]);
    calc_crc = efw_pid_scope_crc16(&frame[2], (uint16_t)(1u + 2u + payload_len));
    if (got_crc != calc_crc) return EFW_ERR_IO;

    payload = &frame[EFW_PID_SCOPE_HEADER_LEN];
    out_param->device_id = payload[0];
    out_param->channel_id = payload[1];
    out_param->kp = get_float_le(&payload[2]);
    out_param->ki = get_float_le(&payload[6]);
    out_param->kd = get_float_le(&payload[10]);
    return EFW_OK;
}

#else

uint16_t efw_pid_scope_crc16(const uint8_t *data, uint16_t len) {
    EFW_UNUSED(data); EFW_UNUSED(len);
    return 0u;
}

efw_status_t efw_pid_scope_encode_telemetry(const efw_pid_scope_telemetry_t *telemetry,
                                            uint8_t *out_frame,
                                            uint16_t out_cap,
                                            uint16_t *out_len) {
    EFW_UNUSED(telemetry); EFW_UNUSED(out_frame); EFW_UNUSED(out_cap); EFW_UNUSED(out_len);
    return EFW_ERR_UNSUPPORTED;
}

efw_status_t efw_pid_scope_parse_param_set_frame(const uint8_t *frame,
                                                 uint16_t frame_len,
                                                 efw_pid_scope_param_set_t *out_param) {
    EFW_UNUSED(frame); EFW_UNUSED(frame_len); EFW_UNUSED(out_param);
    return EFW_ERR_UNSUPPORTED;
}

#endif
