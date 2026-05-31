/**
 * @file    app_components.c
 * @brief   Smart Environment Controller 组件层：滤波、事件、状态机和控制模块组合示例
 */

#include "app_components.h"

#include "app_manifest.h"

static float g_temperature_window[8];
static efw_moving_avg_t g_temperature_filter = {
    .buffer = g_temperature_window,
    .capacity = 8,
};
static efw_attitude_complementary_t g_attitude_filter = {
    .alpha = 0.50f,
};
static app_env_sample_t g_sample;

typedef struct {
    uint16_t tick;
} app_sampler_ctx_t;

typedef struct {
    uint8_t fault_latched;
} app_control_ctx_t;

static app_sampler_ctx_t g_sampler_ctx;
static app_control_ctx_t g_control_ctx;

static efw_status_t set_fan(uint8_t on) {
    efw_actuator_cmd_t cmd = { .value = on ? 1.0f : 0.0f };
    g_sample.fan_on = on ? 1u : 0u;
    return efw_actuator_write(APP_FAN_RELAY_NAME, &cmd);
}

static efw_status_t set_alarm(uint8_t on) {
    efw_actuator_cmd_t cmd = { .value = on ? 1.0f : 0.0f };
    g_sample.alarm_on = on ? 1u : 0u;
    return efw_actuator_write(APP_ALARM_LED_NAME, &cmd);
}

static void on_env_sample(uint16_t topic_id, const void *data, uint16_t size, void *user) {
    app_control_ctx_t *control = (app_control_ctx_t *)user;
    const app_env_sample_t *sample = (const app_env_sample_t *)data;

    EFW_UNUSED(topic_id);
    if (!control || !sample || size != sizeof(app_env_sample_t)) return;
    control->fault_latched =
        (sample->attitude.roll > APP_TILT_FAULT_DEG || sample->attitude.roll < -APP_TILT_FAULT_DEG) ? 1u : 0u;
}

static efw_status_t sampler_init(void *ctx) {
    app_sampler_ctx_t *sampler = (app_sampler_ctx_t *)ctx;
    if (!sampler) return EFW_ERR_INVALID;
    sampler->tick = 0;
    efw_moving_avg_reset(&g_temperature_filter);
    g_attitude_filter.roll = 0.0f;
    g_attitude_filter.pitch = 0.0f;
    g_attitude_filter.initialized = 0;
    return EFW_OK;
}

static efw_status_t sampler_poll(void *ctx) {
    app_sampler_ctx_t *sampler = (app_sampler_ctx_t *)ctx;
    float raw_temperature;
    efw_attitude_input_t attitude_in;
    efw_status_t s;

    if (!sampler) return EFW_ERR_INVALID;
    sampler->tick++;
    if ((sampler->tick % 10u) != 0u) return EFW_OK;

    s = efw_sensor_read(APP_TEMP_SENSOR_NAME, &raw_temperature);
    if (s != EFW_OK) return s;
    s = efw_algo_run(APP_TEMP_FILTER_NAME, &raw_temperature, &g_sample.temperature_c);
    if (s != EFW_OK) return s;
    s = efw_sensor_read(APP_HUMIDITY_SENSOR_NAME, &g_sample.humidity_pct);
    if (s != EFW_OK) return s;
    s = efw_imu_read(APP_IMU_SENSOR_NAME, &g_sample.imu);
    if (s != EFW_OK) return s;

    attitude_in.ax = g_sample.imu.ax;
    attitude_in.ay = g_sample.imu.ay;
    attitude_in.az = g_sample.imu.az;
    attitude_in.gx = g_sample.imu.gx;
    attitude_in.gy = g_sample.imu.gy;
    attitude_in.dt = 0.01f;
    s = efw_algo_run(APP_ATTITUDE_FILTER_NAME, &attitude_in, &g_sample.attitude);
    if (s != EFW_OK) return s;

    return efw_topic_publish(APP_TOPIC_ENV_SAMPLE, &g_sample, (uint16_t)sizeof(g_sample));
}

static efw_status_t control_init(void *ctx) {
    app_control_ctx_t *control = (app_control_ctx_t *)ctx;
    if (!control) return EFW_ERR_INVALID;
    control->fault_latched = 0;
    return efw_topic_subscribe(APP_TOPIC_ENV_SAMPLE, on_env_sample, control);
}

static efw_status_t state_idle_tick(void *ctx) {
    app_control_ctx_t *control = (app_control_ctx_t *)ctx;
    if (!control) return EFW_ERR_INVALID;
    if (control->fault_latched) {
        g_sample.state = APP_ENV_STATE_FAULT;
        return EFW_OK;
    }
    if (g_sample.temperature_c >= APP_TEMP_HIGH_C) g_sample.state = APP_ENV_STATE_COOLING;
    return EFW_OK;
}

static efw_status_t state_cooling_tick(void *ctx) {
    app_control_ctx_t *control = (app_control_ctx_t *)ctx;
    if (!control) return EFW_ERR_INVALID;
    if (control->fault_latched) {
        g_sample.state = APP_ENV_STATE_FAULT;
        return EFW_OK;
    }
    if (g_sample.temperature_c <= APP_TEMP_LOW_C) g_sample.state = APP_ENV_STATE_IDLE;
    return EFW_OK;
}

static efw_status_t state_fault_tick(void *ctx) {
    app_control_ctx_t *control = (app_control_ctx_t *)ctx;
    if (!control) return EFW_ERR_INVALID;
    if (!control->fault_latched && g_sample.temperature_c < APP_TEMP_HIGH_C) g_sample.state = APP_ENV_STATE_IDLE;
    return EFW_OK;
}

static efw_status_t control_poll(void *ctx) {
    app_control_ctx_t *control = (app_control_ctx_t *)ctx;
    efw_status_t s;

    if (!control) return EFW_ERR_INVALID;
    switch (g_sample.state) {
    case APP_ENV_STATE_IDLE:
        s = state_idle_tick(control);
        break;
    case APP_ENV_STATE_COOLING:
        s = state_cooling_tick(control);
        break;
    case APP_ENV_STATE_FAULT:
        s = state_fault_tick(control);
        break;
    default:
        g_sample.state = APP_ENV_STATE_FAULT;
        s = EFW_OK;
        break;
    }
    if (s != EFW_OK) return s;

    if (g_sample.state == APP_ENV_STATE_FAULT) {
        s = set_fan(0);
        if (s != EFW_OK) return s;
        return set_alarm(1);
    }

    s = set_alarm(0);
    if (s != EFW_OK) return s;
    return set_fan(g_sample.state == APP_ENV_STATE_COOLING ? 1u : 0u);
}

static efw_algo_ops_t g_temperature_filter_ops = {
    .name = APP_TEMP_FILTER_NAME,
    .type = EFW_ALGO_FILTER,
    .ctx = &g_temperature_filter,
    .run = efw_moving_avg_run,
};

static efw_algo_ops_t g_attitude_filter_ops = {
    .name = APP_ATTITUDE_FILTER_NAME,
    .type = EFW_ALGO_FILTER,
    .ctx = &g_attitude_filter,
    .run = efw_attitude_complementary_run,
};

static efw_module_ops_t g_sampler_module = {
    .name = APP_SAMPLER_MODULE_NAME,
    .type = EFW_MODULE_SERVICE,
    .ctx = &g_sampler_ctx,
    .init = sampler_init,
    .poll = sampler_poll,
};

static efw_module_ops_t g_control_module = {
    .name = APP_CONTROL_MODULE_NAME,
    .type = EFW_MODULE_APP,
    .ctx = &g_control_ctx,
    .init = control_init,
    .poll = control_poll,
};

static efw_state_machine_ops_t g_state_idle = {
    .name = APP_STATE_IDLE_NAME,
    .ctx = &g_control_ctx,
    .on_tick = state_idle_tick,
};

static efw_state_machine_ops_t g_state_cooling = {
    .name = APP_STATE_COOLING_NAME,
    .ctx = &g_control_ctx,
    .on_tick = state_cooling_tick,
};

static efw_state_machine_ops_t g_state_fault = {
    .name = APP_STATE_FAULT_NAME,
    .ctx = &g_control_ctx,
    .on_tick = state_fault_tick,
};

efw_status_t app_components_register(void) {
    efw_status_t s = efw_algo_register(&g_temperature_filter_ops);
    if (s != EFW_OK) return s;
    s = efw_algo_register(&g_attitude_filter_ops);
    if (s != EFW_OK) return s;
    s = efw_sm_register(&g_state_idle);
    if (s != EFW_OK) return s;
    s = efw_sm_register(&g_state_cooling);
    if (s != EFW_OK) return s;
    s = efw_sm_register(&g_state_fault);
    if (s != EFW_OK) return s;
    s = efw_module_register(&g_sampler_module);
    if (s != EFW_OK) return s;
    return efw_module_register(&g_control_module);
}

const app_env_sample_t *app_components_current_sample(void) {
    return &g_sample;
}
