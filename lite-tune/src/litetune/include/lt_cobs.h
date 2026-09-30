#ifndef LT_COBS_H
#define LT_COBS_H

#include "lt_common.h"

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

LT_API lt_status_t lt_cobs_encode(
    const uint8_t *input,
    uint16_t input_len,
    uint8_t *output,
    uint16_t output_cap,
    uint16_t *output_len
);

LT_API lt_status_t lt_cobs_decode(
    const uint8_t *input,
    uint16_t input_len,
    uint8_t *output,
    uint16_t output_cap,
    uint16_t *output_len
);

LT_API uint16_t lt_cobs_encoded_max_len(uint16_t raw_len);

#ifdef __cplusplus
}
#endif

#ifdef LITETUNE_IMPLEMENTATION

LT_API lt_status_t lt_cobs_encode(
    const uint8_t *input,
    uint16_t input_len,
    uint8_t *output,
    uint16_t output_cap,
    uint16_t *output_len
)
{
    uint16_t read_index = 0u;
    uint16_t write_index = 1u;
    uint16_t code_index = 0u;
    uint8_t code = 1u;

    if ((output_len == (uint16_t *)0) || (output == (uint8_t *)0) ||
        ((input == (const uint8_t *)0) && (input_len > 0u))) {
        return LT_STATUS_BAD_PAYLOAD;
    }

    *output_len = 0u;

    if (output_cap < 1u) {
        return LT_STATUS_TOO_LARGE;
    }

    while (read_index < input_len) {
        if (input[read_index] == 0u) {
            if (code_index >= output_cap) {
                return LT_STATUS_TOO_LARGE;
            }
            output[code_index] = code;
            code_index = write_index;
            write_index = (uint16_t)(write_index + 1u);
            if (write_index > output_cap) {
                return LT_STATUS_TOO_LARGE;
            }
            code = 1u;
            read_index = (uint16_t)(read_index + 1u);
        } else {
            if (write_index >= output_cap) {
                return LT_STATUS_TOO_LARGE;
            }
            output[write_index] = input[read_index];
            write_index = (uint16_t)(write_index + 1u);
            read_index = (uint16_t)(read_index + 1u);
            code = (uint8_t)(code + 1u);
            if (code == 0xFFu) {
                if (code_index >= output_cap) {
                    return LT_STATUS_TOO_LARGE;
                }
                output[code_index] = code;
                if (read_index >= input_len) {
                    *output_len = write_index;
                    return LT_STATUS_OK;
                }
                code_index = write_index;
                write_index = (uint16_t)(write_index + 1u);
                if (write_index > output_cap) {
                    return LT_STATUS_TOO_LARGE;
                }
                code = 1u;
            }
        }
    }

    if (code_index >= output_cap) {
        return LT_STATUS_TOO_LARGE;
    }
    output[code_index] = code;
    *output_len = write_index;
    return LT_STATUS_OK;
}

LT_API lt_status_t lt_cobs_decode(
    const uint8_t *input,
    uint16_t input_len,
    uint8_t *output,
    uint16_t output_cap,
    uint16_t *output_len
)
{
    uint16_t read_index = 0u;
    uint16_t write_index = 0u;
    uint16_t scan_index;

    if ((output_len == (uint16_t *)0) || (output == (uint8_t *)0) ||
        ((input == (const uint8_t *)0) && (input_len > 0u))) {
        return LT_STATUS_BAD_PAYLOAD;
    }

    *output_len = 0u;

    if (input_len == 0u) {
        return LT_STATUS_BAD_PAYLOAD;
    }

    for (scan_index = 0u; scan_index < input_len; ++scan_index) {
        if (input[scan_index] == 0u) {
            return LT_STATUS_BAD_PAYLOAD;
        }
    }

    while (read_index < input_len) {
        uint8_t code = input[read_index];
        uint8_t i;

        if (code == 0u) {
            return LT_STATUS_BAD_PAYLOAD;
        }
        read_index = (uint16_t)(read_index + 1u);

        if ((uint16_t)(read_index + (uint16_t)code - 1u) > input_len) {
            return LT_STATUS_BAD_PAYLOAD;
        }

        for (i = 1u; i < code; ++i) {
            if (input[read_index] == 0u) {
                return LT_STATUS_BAD_PAYLOAD;
            }
            if (write_index >= output_cap) {
                return LT_STATUS_TOO_LARGE;
            }
            output[write_index] = input[read_index];
            write_index = (uint16_t)(write_index + 1u);
            read_index = (uint16_t)(read_index + 1u);
        }

        if ((code != 0xFFu) && (read_index < input_len)) {
            if (write_index >= output_cap) {
                return LT_STATUS_TOO_LARGE;
            }
            output[write_index] = 0u;
            write_index = (uint16_t)(write_index + 1u);
        }
    }

    *output_len = write_index;
    return LT_STATUS_OK;
}

LT_API uint16_t lt_cobs_encoded_max_len(uint16_t raw_len)
{
    return (uint16_t)(raw_len + (uint16_t)(raw_len / 254u) + 1u);
}

#endif /* LITETUNE_IMPLEMENTATION */

#endif /* LT_COBS_H */
