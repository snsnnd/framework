#define EFW_ENABLE_DEBUG 1
#define EFW_ENABLE_LITETUNE 1

#include "efw/debug/efw_debug_litetune.h"
#include "efw/debug/litetune/litetune.h"

#include <stdint.h>
#include <stdio.h>

static efw_debug_event_sink_fn g_sink;
static efw_status_t g_send_result = EFW_OK;
static unsigned g_send_calls;
static uint64_t g_frame_id = 1u;

void efw_debug_foreach_point(efw_debug_point_iter_fn callback, void *user)
{
    (void)callback;
    (void)user;
}

void efw_debug_set_event_sink(efw_debug_event_sink_fn sink, void *user)
{
    (void)user;
    g_sink = sink;
}

void efw_debug_attach_runtime_trace(void)
{
}

uint16_t efw_debug_point_count(void)
{
    return 0u;
}

efw_status_t efw_debug_get_stats(efw_debug_stats_t *stats)
{
    if (!stats) return EFW_ERR_INVALID;
    *stats = (efw_debug_stats_t){0};
    return EFW_OK;
}

static efw_status_t test_send(const void *data, uint16_t len)
{
    (void)data;
    (void)len;
    g_send_calls++;
    return g_send_result;
}

static uint64_t next_frame_id(void)
{
    return g_frame_id++;
}

static int run_mode(efw_debug_litetune_send_mode_t mode)
{
    efw_debug_litetune_config_t config = {
        .send = test_send,
        .next_frame_id = next_frame_id,
        .device_name = "tx-test",
        .features = 0u,
        .telemetry_period_ms = 10u,
        .send_mode = mode,
    };

    if (efw_debug_litetune_init(&config) != EFW_OK || !g_sink) return 1;
    if (lt_tx_enqueue_frame((uint8_t)LT_TYPE_STATUS, NULL, 0u) != LT_STATUS_OK) return 1;
    lt_tx_try_send();
    if (g_send_calls != 1u) return 1;

    lt_tx_try_send();
    if (g_send_calls != 1u) return 1;

    if (lt_tx_enqueue_frame((uint8_t)LT_TYPE_STATUS, NULL, 0u) != LT_STATUS_OK) return 1;
    lt_tx_try_send();
    if (mode == EFW_DEBUG_LITETUNE_SEND_SYNC) {
        return (g_send_calls == 2u) ? 0 : 1;
    }
    if (g_send_calls != 1u) return 1;
    efw_debug_litetune_tx_complete();
    lt_tx_try_send();
    return (g_send_calls == 2u) ? 0 : 1;
}

int main(void)
{
    if (run_mode(EFW_DEBUG_LITETUNE_SEND_SYNC) != 0) {
        fputs("synchronous completion contract failed\n", stderr);
        return 1;
    }

    g_send_calls = 0u;
    if (run_mode(EFW_DEBUG_LITETUNE_SEND_ASYNC) != 0) {
        fputs("asynchronous completion contract failed\n", stderr);
        return 1;
    }

    puts("LiteTune TX completion checks passed");
    return 0;
}
