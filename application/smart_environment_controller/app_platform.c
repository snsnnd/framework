/**
 * @file    app_platform.c
 * @brief   Smart Environment Controller 平台层：模拟 ADC/I2C/GPIO 并注册传感器与执行器
 */

#include "app_platform.h"

#include "app_manifest.h"

typedef struct {
    float temperature_c;
    float humidity_pct;
    efw_imu_data_t imu;
    uint8_t fan_on;
    uint8_t alarm_on;
} app_platform_ctx_t;

static app_platform_ctx_t g_platform = {
    .temperature_c = 24.0f,
    .humidity_pct = 45.0f,
    .imu = { .az = 1.0f },
};

static efw_status_t env_adc_read(void *ctx, void *buf, uint16_t len, uint16_t *actual) {
    app_platform_ctx_t *platform = (app_platform_ctx_t *)ctx;
    float *values = (float *)buf;

    if (!platform || !values || len < (uint16_t)(2u * sizeof(float))) return EFW_ERR_INVALID;
    values[0] = platform->temperature_c;
    values[1] = platform->humidity_pct;
    if (actual) *actual = (uint16_t)(2u * sizeof(float));
    return EFW_OK;
}

static efw_status_t imu_i2c_read(void *ctx, void *buf, uint16_t len, uint16_t *actual) {
    app_platform_ctx_t *platform = (app_platform_ctx_t *)ctx;
    efw_imu_data_t *imu = (efw_imu_data_t *)buf;

    if (!platform || !imu || len < sizeof(efw_imu_data_t)) return EFW_ERR_INVALID;
    *imu = platform->imu;
    if (actual) *actual = (uint16_t)sizeof(efw_imu_data_t);
    return EFW_OK;
}

static efw_status_t relay_gpio_write(void *ctx, const void *buf, uint16_t len, uint16_t *actual) {
    EFW_UNUSED(ctx);
    if (!buf || len == 0u) return EFW_ERR_INVALID;
    if (actual) *actual = len;
    return EFW_OK;
}

static efw_status_t temperature_read(void *ctx, void *out, uint16_t out_size) {
    float raw[2];
    EFW_UNUSED(ctx);
    if (!out || out_size < sizeof(float)) return EFW_ERR_INVALID;
    if (efw_hal_read(APP_ENV_ADC_HAL_NAME, raw, (uint16_t)sizeof(raw), 0) != EFW_OK) return EFW_ERR_IO;
    *(float *)out = raw[0];
    return EFW_OK;
}

static efw_status_t humidity_read(void *ctx, void *out, uint16_t out_size) {
    float raw[2];
    EFW_UNUSED(ctx);
    if (!out || out_size < sizeof(float)) return EFW_ERR_INVALID;
    if (efw_hal_read(APP_ENV_ADC_HAL_NAME, raw, (uint16_t)sizeof(raw), 0) != EFW_OK) return EFW_ERR_IO;
    *(float *)out = raw[1];
    return EFW_OK;
}

static efw_status_t imu_read(void *ctx, void *out, uint16_t out_size) {
    EFW_UNUSED(ctx);
    if (!out || out_size < sizeof(efw_imu_data_t)) return EFW_ERR_INVALID;
    return efw_hal_read(APP_IMU_I2C_HAL_NAME, out, (uint16_t)sizeof(efw_imu_data_t), 0);
}

static efw_status_t fan_write(void *ctx, const void *cmd, uint16_t cmd_size) {
    app_platform_ctx_t *platform = (app_platform_ctx_t *)ctx;
    const efw_actuator_cmd_t *fan_cmd = (const efw_actuator_cmd_t *)cmd;
    uint8_t pin_value;
    (void)cmd_size;

    if (!platform || !fan_cmd) return EFW_ERR_INVALID;
    platform->fan_on = fan_cmd->value > 0.5f ? 1u : 0u;
    pin_value = platform->fan_on;
    return efw_hal_write(APP_RELAY_GPIO_HAL_NAME, &pin_value, (uint16_t)sizeof(pin_value), 0);
}

static efw_status_t alarm_write(void *ctx, const void *cmd, uint16_t cmd_size) {
    app_platform_ctx_t *platform = (app_platform_ctx_t *)ctx;
    const efw_actuator_cmd_t *alarm_cmd = (const efw_actuator_cmd_t *)cmd;
    uint8_t pin_value;
    (void)cmd_size;

    if (!platform || !alarm_cmd) return EFW_ERR_INVALID;
    platform->alarm_on = alarm_cmd->value > 0.5f ? 1u : 0u;
    pin_value = platform->alarm_on;
    return efw_hal_write(APP_RELAY_GPIO_HAL_NAME, &pin_value, (uint16_t)sizeof(pin_value), 0);
}

static efw_hal_ops_t g_env_adc = {
    .name = APP_ENV_ADC_HAL_NAME,
    .type = EFW_HAL_ADC,
    .bus_id = 1,
    .ctx = &g_platform,
    .read = env_adc_read,
};

static efw_hal_ops_t g_imu_i2c = {
    .name = APP_IMU_I2C_HAL_NAME,
    .type = EFW_HAL_I2C,
    .bus_id = 1,
    .ctx = &g_platform,
    .read = imu_i2c_read,
};

static efw_hal_ops_t g_relay_gpio = {
    .name = APP_RELAY_GPIO_HAL_NAME,
    .type = EFW_HAL_GPIO,
    .bus_id = 2,
    .ctx = &g_platform,
    .write = relay_gpio_write,
};

static efw_sensor_ops_t g_temperature_sensor = {
    .name = APP_TEMP_SENSOR_NAME,
    .type = EFW_SENSOR_CUSTOM,
    .channel_count = 1,
    .hal_name = APP_ENV_ADC_HAL_NAME,
    .read = temperature_read,
};

static efw_sensor_ops_t g_humidity_sensor = {
    .name = APP_HUMIDITY_SENSOR_NAME,
    .type = EFW_SENSOR_CUSTOM,
    .channel_count = 1,
    .hal_name = APP_ENV_ADC_HAL_NAME,
    .read = humidity_read,
};

static efw_sensor_ops_t g_imu_sensor = {
    .name = APP_IMU_SENSOR_NAME,
    .type = EFW_SENSOR_IMU,
    .channel_count = 6,
    .hal_name = APP_IMU_I2C_HAL_NAME,
    .read = imu_read,
};

static efw_actuator_ops_t g_fan_relay = {
    .name = APP_FAN_RELAY_NAME,
    .type = EFW_ACTUATOR_RELAY,
    .hal_name = APP_RELAY_GPIO_HAL_NAME,
    .ctx = &g_platform,
    .write = fan_write,
};

static efw_actuator_ops_t g_alarm_led = {
    .name = APP_ALARM_LED_NAME,
    .type = EFW_ACTUATOR_LED,
    .hal_name = APP_RELAY_GPIO_HAL_NAME,
    .ctx = &g_platform,
    .write = alarm_write,
};

efw_status_t app_platform_register(void) {
    efw_status_t s = efw_hal_register(&g_env_adc);
    if (s != EFW_OK) return s;
    s = efw_hal_register(&g_imu_i2c);
    if (s != EFW_OK) return s;
    s = efw_hal_register(&g_relay_gpio);
    if (s != EFW_OK) return s;
    s = efw_sensor_register(&g_temperature_sensor);
    if (s != EFW_OK) return s;
    s = efw_sensor_register(&g_humidity_sensor);
    if (s != EFW_OK) return s;
    s = efw_sensor_register(&g_imu_sensor);
    if (s != EFW_OK) return s;
    s = efw_actuator_register(&g_fan_relay);
    if (s != EFW_OK) return s;
    return efw_actuator_register(&g_alarm_led);
}

void app_platform_set_temperature(float temperature_c) {
    g_platform.temperature_c = temperature_c;
}

void app_platform_set_humidity(float humidity_pct) {
    g_platform.humidity_pct = humidity_pct;
}

void app_platform_set_imu(const efw_imu_data_t *imu) {
    if (imu) g_platform.imu = *imu;
}

uint8_t app_platform_fan_is_on(void) {
    return g_platform.fan_on;
}

uint8_t app_platform_alarm_is_on(void) {
    return g_platform.alarm_on;
}
