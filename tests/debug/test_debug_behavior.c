#include "efw/debug/efw_debug_async.h"
#include "efw/debug/efw_debug_fast.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

extern efw_debug_fast_t g_debug_fast;

static efw_status_t g_dma_result;
static uint8_t g_dma_data[EFW_DEBUG_BATCH_SIZE];
static uint16_t g_dma_length;
static void (*g_tx_callback)(void);
static unsigned g_failures;

#define CHECK(condition) do { \
    if (!(condition)) { \
        fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
        g_failures++; \
    } \
} while (0)

uint32_t efw_debug_get_us(void)
{
    static uint32_t now;
    return now++;
}

efw_status_t efw_debug_start_dma(const uint8_t *data, uint16_t length)
{
    if (g_dma_result == EFW_OK) {
        memcpy(g_dma_data, data, length);
        g_dma_length = length;
    }
    return g_dma_result;
}

void efw_debug_register_tx_callback(void (*callback)(void))
{
    g_tx_callback = callback;
}

static void test_dma_failure_retains_data(void)
{
    static const uint8_t payload[] = { 1u, 2u, 3u, 4u };
    uint32_t bytes_written = 0u;
    uint32_t bytes_sent = 0u;
    uint32_t tx_count = 0u;

    CHECK(efw_debug_async_init() == EFW_OK);
    CHECK(g_tx_callback == efw_debug_async_tx_complete);
    CHECK(efw_debug_async_write(payload, sizeof(payload)) == EFW_OK);

    g_dma_result = EFW_ERR_IO;
    CHECK(efw_debug_async_flush() == EFW_ERR_IO);
    CHECK(efw_debug_async_has_data() != 0);
    CHECK(efw_debug_async_get_stats(&bytes_written, &bytes_sent, &tx_count, NULL) == EFW_OK);
    CHECK(bytes_written == sizeof(payload));
    CHECK(bytes_sent == 0u);
    CHECK(tx_count == 0u);

    g_dma_result = EFW_OK;
    CHECK(efw_debug_async_flush() == EFW_OK);
    CHECK(g_dma_length == sizeof(payload));
    CHECK(memcmp(g_dma_data, payload, sizeof(payload)) == 0);
    CHECK(efw_debug_async_has_data() != 0);
    CHECK(efw_debug_async_get_stats(NULL, &bytes_sent, &tx_count, NULL) == EFW_OK);
    CHECK(bytes_sent == 0u);
    CHECK(tx_count == 0u);

    g_tx_callback();
    CHECK(efw_debug_async_has_data() == 0);
    CHECK(efw_debug_async_get_stats(NULL, &bytes_sent, &tx_count, NULL) == EFW_OK);
    CHECK(bytes_sent == sizeof(payload));
    CHECK(tx_count == 1u);
}

static void test_fast_full_buffer_retains_dirty(void)
{
    double values[EFW_DEBUG_MAX_POINTS];
    char names[EFW_DEBUG_MAX_POINTS][12];
    uint16_t first_dirty = 0xFFFFu;

    memset(values, 0, sizeof(values));
    CHECK(efw_debug_fast_init() == EFW_OK);
    for (uint16_t i = 0u; i < EFW_DEBUG_MAX_POINTS; ++i) {
        snprintf(names[i], sizeof(names[i]), "point%u", (unsigned)i);
        CHECK(efw_debug_fast_register(names[i], 0x0Bu, &values[i], (uint16_t)(0x1000u + i)) == EFW_OK);
    }
    for (uint16_t i = 0u; i < EFW_DEBUG_MAX_POINTS; ++i) {
        values[i] = (double)(i + 1u);
    }
    CHECK(efw_debug_fast_update() == EFW_OK);
    CHECK(efw_debug_fast_sync() == EFW_OK);

    for (uint16_t i = 0u; i < EFW_DEBUG_MAX_POINTS; ++i) {
        if ((g_debug_fast.incr.dirty_bitmap[i / 8u] & (uint8_t)(1u << (i % 8u))) != 0u) {
            first_dirty = i;
            break;
        }
    }
    CHECK(first_dirty != 0xFFFFu);
    CHECK(g_debug_fast.incr.last_sync_seq != g_debug_fast.incr.update_seq);
}

static void test_fast_batch_requires_release(void)
{
    uint32_t value = 0u;
    const uint8_t *data = NULL;
    uint16_t size = 0u;

    CHECK(efw_debug_fast_init() == EFW_OK);
    CHECK(efw_debug_fast_register("batch", 0x06u, &value, 0x2000u) == EFW_OK);
    value = 1u;
    CHECK(efw_debug_fast_update() == EFW_OK);
    CHECK(efw_debug_fast_sync() == EFW_OK);
    CHECK(efw_debug_fast_acquire(&data, &size) == EFW_OK);
    CHECK(data != NULL);
    CHECK(size > 0u);
    value = 2u;
    CHECK(efw_debug_fast_update() == EFW_OK);
    CHECK(efw_debug_fast_sync() == EFW_ERR_NOT_READY);
    efw_debug_fast_release();
    CHECK(efw_debug_fast_sync() == EFW_OK);
}

int main(void)
{
    test_dma_failure_retains_data();
    test_fast_full_buffer_retains_dirty();
    test_fast_batch_requires_release();
    if (g_failures != 0u) {
        fprintf(stderr, "%u debug behavior checks failed\n", g_failures);
        return 1;
    }
    puts("debug behavior checks passed");
    return 0;
}
