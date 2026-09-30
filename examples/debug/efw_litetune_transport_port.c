/**
 * @file    efw_litetune_transport_port.c
 * @brief   Single-file board transport port for EFW + LiteTune debug.
 *
 * Copy this file into your application or board_adapters directory and edit only
 * the TODO section. EFW/LiteTune owns the binary protocol, COBS framing, CRC,
 * schema discovery, param get/set and command handling. This file only moves
 * already-encoded bytes between LiteTune and your UART/USB CDC driver.
 */

#include "efw/efw.h"

#if EFW_ENABLE_DEBUG && EFW_ENABLE_LITETUNE

/* ========================================================================
 * TODO: board-specific includes and low-level byte I/O
 * ======================================================================== */

/* Examples:
 *   #include "stm32f4xx_hal.h"
 *   extern UART_HandleTypeDef huart2;
 *
 *   #include "usbd_cdc_if.h"
 */

static efw_status_t app_debug_transport_write_bytes(const uint8_t *data, uint16_t len)
{
    if (!data && len > 0u) {
        return EFW_ERR_INVALID;
    }

    /* TODO: replace this stub with your real transport write.
     * UART blocking example:
     *   return (HAL_UART_Transmit(&huart2, (uint8_t *)data, len, 10) == HAL_OK)
     *       ? EFW_OK : EFW_ERR_IO;
     *
     * USB CDC example:
     *   return (CDC_Transmit_FS((uint8_t *)data, len) == USBD_OK)
     *       ? EFW_OK : EFW_ERR_IO;
     */
    (void)data;
    (void)len;
    return EFW_ERR_UNSUPPORTED;
}

/* ========================================================================
 * Stable EFW/LiteTune transport API used by application code
 * ======================================================================== */

static efw_status_t app_debug_litetune_send(const void *data, uint16_t len)
{
    return app_debug_transport_write_bytes((const uint8_t *)data, len);
}

efw_status_t app_debug_transport_start(const char *device_name, uint16_t telemetry_period_ms)
{
    efw_debug_litetune_config_t config = {
        .send = app_debug_litetune_send,
        .next_frame_id = 0,
        .device_name = device_name ? device_name : "efw-board",
        .features = 0,
        .telemetry_period_ms = telemetry_period_ms,
    };

    return efw_debug_litetune_init(&config);
}

void app_debug_transport_on_rx(const uint8_t *data, uint16_t len)
{
    (void)efw_debug_litetune_rx(data, len);
}

void app_debug_transport_poll_1ms(uint16_t telemetry_period_ms)
{
    static uint16_t s_elapsed_ms;

    efw_debug_litetune_process();

    if (telemetry_period_ms == 0u) {
        return;
    }

    ++s_elapsed_ms;
    if (s_elapsed_ms >= telemetry_period_ms) {
        s_elapsed_ms = 0u;
        (void)efw_debug_update();
        (void)efw_debug_litetune_report();
    }
}

#endif /* EFW_ENABLE_DEBUG && EFW_ENABLE_LITETUNE */
