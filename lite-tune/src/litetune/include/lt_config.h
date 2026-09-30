#ifndef LT_CONFIG_H
#define LT_CONFIG_H

/*
 * LiteTune MCU configuration layer.
 *
 * This project uses a header-only/stb-style layout: declarations are visible
 * from every translation unit; storage and function bodies are emitted only by
 * the one translation unit defining LITETUNE_IMPLEMENTATION before including
 * src/litetune/litetune.h.
 */

#include <stdint.h>
#include <stddef.h>

#ifndef LT_API
#  ifdef LITETUNE_STATIC
#    define LT_API static
#  else
#    define LT_API extern
#  endif
#endif

#ifdef LITETUNE_IMPLEMENTATION
#  ifndef LT_IMPL
#    define LT_IMPL
#  endif
#endif

#ifndef LT_RAW_FRAME_SIZE
#define LT_RAW_FRAME_SIZE 256u
#endif

#ifndef LT_WIRE_FRAME_SIZE
#define LT_WIRE_FRAME_SIZE (LT_RAW_FRAME_SIZE + LT_RAW_FRAME_SIZE / 254u + 2u)
#endif

#ifndef LT_RX_RING_BUFFER_SIZE
#define LT_RX_RING_BUFFER_SIZE (4u * LT_WIRE_FRAME_SIZE)
#endif

#ifndef LT_RX_MAX_FRAMES_PER_PROCESS
#define LT_RX_MAX_FRAMES_PER_PROCESS 4u
#endif

#ifndef LT_TX_SLOT_POOL_SIZE
#define LT_TX_SLOT_POOL_SIZE 16u
#endif

#ifndef LT_TX_SEND_QUEUE_SIZE
#define LT_TX_SEND_QUEUE_SIZE 8u
#endif

#ifndef LT_TX_SENDING_FRAME_COUNT
#define LT_TX_SENDING_FRAME_COUNT 4u
#endif

#ifndef LT_TX_SENDING_BUFFER_SIZE
#define LT_TX_SENDING_BUFFER_SIZE (LT_TX_SENDING_FRAME_COUNT * LT_WIRE_FRAME_SIZE)
#endif

#ifndef LT_PARAM_SET_MAX_ITEMS
#define LT_PARAM_SET_MAX_ITEMS 8u
#endif

#ifndef LT_PARAM_MAX_VALUE_SIZE
#define LT_PARAM_MAX_VALUE_SIZE 16u
#endif

#ifndef LT_CMD_RESPONSE_BUFFER_SIZE
#define LT_CMD_RESPONSE_BUFFER_SIZE 64u
#endif

#ifndef LT_CMD_RESPONSE_CACHE_SIZE
#define LT_CMD_RESPONSE_CACHE_SIZE LT_CMD_RESPONSE_BUFFER_SIZE
#endif

#ifndef LT_STATUS_MIN_INTERVAL_MS
#define LT_STATUS_MIN_INTERVAL_MS 100u
#endif

#ifndef LT_CRITICAL_ENTER
#define LT_CRITICAL_ENTER() do { } while (0)
#endif

#ifndef LT_CRITICAL_EXIT
#define LT_CRITICAL_EXIT() do { } while (0)
#endif

#if defined(__STDC_VERSION__) && (__STDC_VERSION__ >= 201112L)
#define LT_STATIC_ASSERT(cond, name) _Static_assert((cond), #name)
#else
#define LT_STATIC_ASSERT_JOIN_(a, b) a##b
#define LT_STATIC_ASSERT_JOIN(a, b) LT_STATIC_ASSERT_JOIN_(a, b)
#define LT_STATIC_ASSERT(cond, name) typedef char LT_STATIC_ASSERT_JOIN(lt_static_assert_, name)[(cond) ? 1 : -1]
#endif

LT_STATIC_ASSERT(LT_RAW_FRAME_SIZE >= 24u, raw_frame_size_too_small);
LT_STATIC_ASSERT(LT_WIRE_FRAME_SIZE >= (LT_RAW_FRAME_SIZE + LT_RAW_FRAME_SIZE / 254u + 2u), wire_frame_size_too_small);
LT_STATIC_ASSERT(LT_RX_RING_BUFFER_SIZE >= (LT_WIRE_FRAME_SIZE + 1u), rx_ring_buffer_size_too_small);
LT_STATIC_ASSERT(LT_RAW_FRAME_SIZE <= 65535u, raw_frame_size_too_large);
LT_STATIC_ASSERT(LT_WIRE_FRAME_SIZE <= 65535u, wire_frame_size_too_large);
LT_STATIC_ASSERT(LT_RX_RING_BUFFER_SIZE <= 65535u, rx_ring_buffer_size_too_large);
LT_STATIC_ASSERT(LT_RX_MAX_FRAMES_PER_PROCESS > 0u, rx_max_frames_per_process_zero);
LT_STATIC_ASSERT(LT_TX_SLOT_POOL_SIZE > 0u, tx_slot_pool_size_zero);
LT_STATIC_ASSERT(LT_TX_SLOT_POOL_SIZE <= 255u, tx_slot_pool_size_too_large);
LT_STATIC_ASSERT(LT_TX_SEND_QUEUE_SIZE > 0u, tx_send_queue_size_zero);
LT_STATIC_ASSERT(LT_TX_SEND_QUEUE_SIZE <= 255u, tx_send_queue_size_too_large);
LT_STATIC_ASSERT(LT_TX_SENDING_FRAME_COUNT > 0u, tx_sending_frame_count_zero);
LT_STATIC_ASSERT(LT_TX_SENDING_FRAME_COUNT <= 255u, tx_sending_frame_count_too_large);
LT_STATIC_ASSERT(LT_TX_SENDING_BUFFER_SIZE >= LT_WIRE_FRAME_SIZE, tx_sending_buffer_size_too_small);
LT_STATIC_ASSERT(LT_TX_SENDING_BUFFER_SIZE <= 65535u, tx_sending_buffer_size_too_large);
LT_STATIC_ASSERT(LT_PARAM_SET_MAX_ITEMS > 0u, param_set_max_items_zero);
LT_STATIC_ASSERT(LT_PARAM_SET_MAX_ITEMS <= 255u, param_set_max_items_too_large);
LT_STATIC_ASSERT(LT_PARAM_MAX_VALUE_SIZE > 0u, param_max_value_size_zero);
LT_STATIC_ASSERT(LT_CMD_RESPONSE_BUFFER_SIZE > 0u, cmd_response_buffer_size_zero);
LT_STATIC_ASSERT(LT_CMD_RESPONSE_CACHE_SIZE >= LT_CMD_RESPONSE_BUFFER_SIZE, cmd_response_cache_size_too_small);

#endif /* LT_CONFIG_H */
