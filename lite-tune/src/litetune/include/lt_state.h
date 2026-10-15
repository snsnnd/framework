#ifndef LT_STATE_H
#define LT_STATE_H

#include "lt_config.h"
#include "lt_common.h"

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

struct lt_log_registry_t;
struct lt_param_registry_t;
struct lt_cmd_registry_t;

typedef struct {
    const lt_config_t *config;
    lt_state_t state;
    const struct lt_log_registry_t *log_registry;
    const struct lt_param_registry_t *param_registry;
    const struct lt_cmd_registry_t *cmd_registry;
    uint32_t enabled_features;
    uint16_t peer_max_decoded_frame;
    uint16_t response_timeout_ms;
    lt_counters_t counters;
} lt_state_storage_t;

LT_API lt_state_t lt_state_get(void);
LT_API void lt_state_set(lt_state_t state);

LT_API const lt_config_t *lt_state_config(void);
LT_API const struct lt_log_registry_t *lt_state_log_registry(void);
LT_API const struct lt_param_registry_t *lt_state_param_registry(void);
LT_API const struct lt_cmd_registry_t *lt_state_cmd_registry(void);

LT_API uint32_t lt_state_enabled_features(void);
LT_API uint8_t lt_state_feature_enabled(uint32_t feature_mask);
LT_API uint16_t lt_state_peer_max_decoded_frame(void);
LT_API uint16_t lt_state_response_timeout_ms(void);
LT_API lt_counters_t *lt_state_counters(void);

LT_API void lt_state_reset(void);
LT_API void lt_state_set_config(const lt_config_t *config);
LT_API void lt_state_set_registries(
    const struct lt_log_registry_t *log_registry,
    const struct lt_param_registry_t *param_registry,
    const struct lt_cmd_registry_t *cmd_registry
);
LT_API void lt_state_set_log_registry(const struct lt_log_registry_t *registry);
LT_API void lt_state_set_param_registry(const struct lt_param_registry_t *registry);
LT_API void lt_state_set_cmd_registry(const struct lt_cmd_registry_t *registry);
LT_API void lt_state_set_negotiated(uint32_t enabled_features, uint16_t peer_max_decoded_frame, uint16_t response_timeout_ms);

#ifdef __cplusplus
}
#endif

#ifdef LITETUNE_IMPLEMENTATION

static lt_state_storage_t lt_state_storage_ = {
    (const lt_config_t *)0,
    LT_STATE_UNINIT,
    (const struct lt_log_registry_t *)0,
    (const struct lt_param_registry_t *)0,
    (const struct lt_cmd_registry_t *)0,
    0u,
    0u,
    0u,
    { 0u, 0u, 0u, 0u, 0u }
};

LT_API lt_state_t lt_state_get(void)
{
    lt_state_t s;
    LT_CRITICAL_ENTER();
    s = lt_state_storage_.state;
    LT_CRITICAL_EXIT();
    return s;
}

LT_API void lt_state_set(lt_state_t state)
{
    LT_CRITICAL_ENTER();
    lt_state_storage_.state = state;
    LT_CRITICAL_EXIT();
}

LT_API const lt_config_t *lt_state_config(void)
{
    return lt_state_storage_.config;
}

LT_API const struct lt_log_registry_t *lt_state_log_registry(void)
{
    return lt_state_storage_.log_registry;
}

LT_API const struct lt_param_registry_t *lt_state_param_registry(void)
{
    return lt_state_storage_.param_registry;
}

LT_API const struct lt_cmd_registry_t *lt_state_cmd_registry(void)
{
    return lt_state_storage_.cmd_registry;
}

LT_API uint32_t lt_state_enabled_features(void)
{
    uint32_t features;
    LT_CRITICAL_ENTER();
    features = lt_state_storage_.enabled_features;
    LT_CRITICAL_EXIT();
    return features;
}

LT_API uint8_t lt_state_feature_enabled(uint32_t feature_mask)
{
    return (uint8_t)((lt_state_enabled_features() & feature_mask) == feature_mask);
}

LT_API uint16_t lt_state_peer_max_decoded_frame(void)
{
    uint16_t value;
    LT_CRITICAL_ENTER();
    value = lt_state_storage_.peer_max_decoded_frame;
    LT_CRITICAL_EXIT();
    return value;
}

LT_API uint16_t lt_state_response_timeout_ms(void)
{
    uint16_t value;
    LT_CRITICAL_ENTER();
    value = lt_state_storage_.response_timeout_ms;
    LT_CRITICAL_EXIT();
    return value;
}

LT_API lt_counters_t *lt_state_counters(void)
{
    return &lt_state_storage_.counters;
}

LT_API void lt_state_reset(void)
{
    LT_CRITICAL_ENTER();
    lt_state_storage_.config = (const lt_config_t *)0;
    lt_state_storage_.state = LT_STATE_UNINIT;
    lt_state_storage_.log_registry = (const struct lt_log_registry_t *)0;
    lt_state_storage_.param_registry = (const struct lt_param_registry_t *)0;
    lt_state_storage_.cmd_registry = (const struct lt_cmd_registry_t *)0;
    lt_state_storage_.enabled_features = 0u;
    lt_state_storage_.peer_max_decoded_frame = 0u;
    lt_state_storage_.response_timeout_ms = 0u;
    lt_state_storage_.counters.rx_decode_error_count = 0u;
    lt_state_storage_.counters.rx_crc_error_count = 0u;
    lt_state_storage_.counters.rx_bad_payload_count = 0u;
    lt_state_storage_.counters.rx_overflow_count = 0u;
    lt_state_storage_.counters.tx_drop_count = 0u;
    LT_CRITICAL_EXIT();
}

LT_API void lt_state_set_config(const lt_config_t *config)
{
    LT_CRITICAL_ENTER();
    lt_state_storage_.config = config;
    LT_CRITICAL_EXIT();
}

LT_API void lt_state_set_registries(
    const struct lt_log_registry_t *log_registry,
    const struct lt_param_registry_t *param_registry,
    const struct lt_cmd_registry_t *cmd_registry
)
{
    LT_CRITICAL_ENTER();
    lt_state_storage_.log_registry = log_registry;
    lt_state_storage_.param_registry = param_registry;
    lt_state_storage_.cmd_registry = cmd_registry;
    LT_CRITICAL_EXIT();
}

LT_API void lt_state_set_log_registry(const struct lt_log_registry_t *registry)
{
    LT_CRITICAL_ENTER();
    lt_state_storage_.log_registry = registry;
    LT_CRITICAL_EXIT();
}

LT_API void lt_state_set_param_registry(const struct lt_param_registry_t *registry)
{
    LT_CRITICAL_ENTER();
    lt_state_storage_.param_registry = registry;
    LT_CRITICAL_EXIT();
}

LT_API void lt_state_set_cmd_registry(const struct lt_cmd_registry_t *registry)
{
    LT_CRITICAL_ENTER();
    lt_state_storage_.cmd_registry = registry;
    LT_CRITICAL_EXIT();
}

LT_API void lt_state_set_negotiated(uint32_t enabled_features, uint16_t peer_max_decoded_frame, uint16_t response_timeout_ms)
{
    LT_CRITICAL_ENTER();
    lt_state_storage_.enabled_features = enabled_features;
    lt_state_storage_.peer_max_decoded_frame = peer_max_decoded_frame;
    lt_state_storage_.response_timeout_ms = response_timeout_ms;
    LT_CRITICAL_EXIT();
}

#endif /* LITETUNE_IMPLEMENTATION */

#endif /* LT_STATE_H */
