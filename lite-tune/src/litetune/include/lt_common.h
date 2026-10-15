#ifndef LT_COMMON_H
#define LT_COMMON_H

#include "lt_config.h"

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define LT_PROTO_MAJOR 0u
#define LT_PROTO_MINOR 5u
#define LT_PROTO_PATCH 0u

#define LT_MAGIC 0xA55Au

#define LT_RAW_FRAME_HEADER_SIZE 11u
#define LT_RAW_FRAME_CRC_SIZE 2u
#define LT_RAW_FRAME_MIN_SIZE (LT_RAW_FRAME_HEADER_SIZE + LT_RAW_FRAME_CRC_SIZE)

#define LT_ID_U8_RESERVED_LOW 0x00u
#define LT_ID_U8_RESERVED_HIGH 0xFFu
#define LT_ID_U16_RESERVED_LOW 0x0000u
#define LT_ID_U16_RESERVED_HIGH 0xFFFFu

typedef uint8_t  lt_u8_t;
typedef uint16_t lt_u16_t;
typedef uint32_t lt_u32_t;
typedef uint64_t lt_u64_t;

typedef uint8_t  lt_layout_id_t;
typedef uint16_t lt_field_id_t;
typedef uint16_t lt_param_id_t;
typedef uint16_t lt_cmd_id_t;
typedef uint64_t lt_frame_id_t;

typedef enum {
    LT_TYPE_INVALID = 0x00,
    LT_TYPE_DISCOVER = 0x01,
    LT_TYPE_REGISTER_BEGIN = 0x02,
    LT_TYPE_REGISTER_LOG_LAYOUT = 0x03,
    LT_TYPE_REGISTER_PARAM_DESC = 0x04,
    LT_TYPE_REGISTER_CMD_DESC = 0x05,
    LT_TYPE_REGISTER_END = 0x06,
    LT_TYPE_STATUS = 0x07,
    LT_TYPE_LOG_REPORT = 0x11,
    LT_TYPE_LOG_TEXT = 0x12,
    LT_TYPE_PARAM_SET = 0x21,
    LT_TYPE_PARAM_GET = 0x22,
    LT_TYPE_PARAM_REPORT = 0x23,
    LT_TYPE_CMD_REQUEST = 0x31,
    LT_TYPE_CMD_RESPONSE = 0x32
} lt_type_t;

#define LT_FEATURE_LOG_PACKED (1u << 0)
#define LT_FEATURE_PARAM_GET  (1u << 1)
#define LT_FEATURE_PARAM_SET  (1u << 2)
#define LT_FEATURE_CMD        (1u << 3)
#define LT_FEATURE_LOG_TEXT   (1u << 4)
#define LT_FEATURE_ALL_STANDARD (LT_FEATURE_LOG_PACKED | LT_FEATURE_PARAM_GET | LT_FEATURE_PARAM_SET | LT_FEATURE_CMD | LT_FEATURE_LOG_TEXT)

typedef enum {
    LT_VALUE_INVALID = 0x00,
    LT_VALUE_BOOL = 0x01,
    LT_VALUE_U8 = 0x02,
    LT_VALUE_I8 = 0x03,
    LT_VALUE_U16 = 0x04,
    LT_VALUE_I16 = 0x05,
    LT_VALUE_U32 = 0x06,
    LT_VALUE_I32 = 0x07,
    LT_VALUE_U64 = 0x08,
    LT_VALUE_I64 = 0x09,
    LT_VALUE_F32 = 0x0A,
    LT_VALUE_F64 = 0x0B,
    LT_VALUE_STRING = 0x0C,
    LT_VALUE_BYTES = 0x0D,
    LT_VALUE_ENUM_U8 = 0x0E
} lt_value_type_t;

typedef enum {
    LT_LOG_LEVEL_DEBUG = 0x00,
    LT_LOG_LEVEL_INFO = 0x01,
    LT_LOG_LEVEL_WARN = 0x02,
    LT_LOG_LEVEL_ERROR = 0x03,
    LT_LOG_LEVEL_FATAL = 0x04
} lt_log_level_t;

typedef enum {
    LT_STATUS_OK = 0x00,
    LT_STATUS_ACCEPTED = 0x01,
    LT_STATUS_PARTIAL_OK = 0x02,

    LT_STATUS_VERSION_UNSUPPORTED = 0x10,
    LT_STATUS_UNKNOWN_TYPE = 0x11,
    LT_STATUS_BAD_PAYLOAD = 0x13,
    LT_STATUS_NOT_FOUND = 0x14,
    LT_STATUS_TYPE_MISMATCH = 0x15,
    LT_STATUS_RANGE_ERROR = 0x16,
    LT_STATUS_BUSY = 0x18,
    LT_STATUS_STORAGE_ERROR = 0x19,
    LT_STATUS_DENIED = 0x1A,
    LT_STATUS_EXEC_ERROR = 0x1B,
    LT_STATUS_TOO_LARGE = 0x1C,
    LT_STATUS_UNSUPPORTED = 0x1D,
    LT_STATUS_TIMEOUT = 0x1E,
    LT_STATUS_CONFLICT = 0x1F,
    LT_STATUS_NOT_READY = 0x20,
    LT_STATUS_INVALID_STATE = 0x21,
    LT_STATUS_FRAME_DECODE_ERROR = 0x22,
    LT_STATUS_CRC_ERROR = 0x23,
    LT_STATUS_RX_OVERFLOW = 0x24,
    LT_STATUS_TX_DROP = 0x25,

    LT_STATUS_UNKNOWN_ERROR = 0x7F
} lt_status_t;

typedef enum {
    LT_STATE_UNINIT = 0,
    LT_STATE_REGISTERING,
    LT_STATE_WAIT_DISCOVER,
    LT_STATE_CONNECTED,
    LT_STATE_ERROR
} lt_state_t;

typedef lt_status_t (*lt_send_fn_t)(const void *data, uint16_t len);
typedef lt_frame_id_t (*lt_next_frame_id_fn_t)(void);

typedef struct {
    uint16_t rx_decode_error_count;
    uint16_t rx_crc_error_count;
    uint16_t rx_bad_payload_count;
    uint16_t rx_overflow_count;
    uint16_t tx_drop_count;
} lt_counters_t;

typedef struct {
    lt_send_fn_t send;
    lt_next_frame_id_fn_t next_frame_id;
    const char *device_name;
    uint32_t mcu_supported_features;
} lt_config_t;

LT_API uint8_t lt_type_is_standard(uint8_t type);
LT_API uint8_t lt_type_is_project_extension(uint8_t type);
LT_API uint8_t lt_layout_id_is_valid(lt_layout_id_t id);
LT_API uint8_t lt_field_id_is_valid(lt_field_id_t id);
LT_API uint8_t lt_param_id_is_valid(lt_param_id_t id);
LT_API uint8_t lt_cmd_id_is_valid(lt_cmd_id_t id);

#ifdef __cplusplus
}
#endif

#ifdef LITETUNE_IMPLEMENTATION

LT_API uint8_t lt_type_is_standard(uint8_t type)
{
    switch (type) {
    case LT_TYPE_DISCOVER:
    case LT_TYPE_REGISTER_BEGIN:
    case LT_TYPE_REGISTER_LOG_LAYOUT:
    case LT_TYPE_REGISTER_PARAM_DESC:
    case LT_TYPE_REGISTER_CMD_DESC:
    case LT_TYPE_REGISTER_END:
    case LT_TYPE_STATUS:
    case LT_TYPE_LOG_REPORT:
    case LT_TYPE_LOG_TEXT:
    case LT_TYPE_PARAM_SET:
    case LT_TYPE_PARAM_GET:
    case LT_TYPE_PARAM_REPORT:
    case LT_TYPE_CMD_REQUEST:
    case LT_TYPE_CMD_RESPONSE:
        return 1u;
    default:
        return 0u;
    }
}

LT_API uint8_t lt_type_is_project_extension(uint8_t type)
{
    return (uint8_t)((type >= 0x40u) && (type <= 0x7Fu));
}

LT_API uint8_t lt_layout_id_is_valid(lt_layout_id_t id)
{
    return (uint8_t)((id != (lt_layout_id_t)LT_ID_U8_RESERVED_LOW) &&
                     (id != (lt_layout_id_t)LT_ID_U8_RESERVED_HIGH));
}

LT_API uint8_t lt_field_id_is_valid(lt_field_id_t id)
{
    return (uint8_t)((id != (lt_field_id_t)LT_ID_U16_RESERVED_LOW) &&
                     (id != (lt_field_id_t)LT_ID_U16_RESERVED_HIGH));
}

LT_API uint8_t lt_param_id_is_valid(lt_param_id_t id)
{
    return (uint8_t)((id != (lt_param_id_t)LT_ID_U16_RESERVED_LOW) &&
                     (id != (lt_param_id_t)LT_ID_U16_RESERVED_HIGH));
}

LT_API uint8_t lt_cmd_id_is_valid(lt_cmd_id_t id)
{
    return (uint8_t)((id != (lt_cmd_id_t)LT_ID_U16_RESERVED_LOW) &&
                     (id != (lt_cmd_id_t)LT_ID_U16_RESERVED_HIGH));
}

#endif /* LITETUNE_IMPLEMENTATION */

#endif /* LT_COMMON_H */
