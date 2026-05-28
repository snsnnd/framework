#include "efw/efw.h"

typedef struct {
    uint16_t value;
} adc_ctx_t;

static adc_ctx_t g_adc_ctx;
static efw_pid_t g_pid = {
    .kp = 1.0f,
    .ki = 0.1f,
    .kd = 0.01f,
    .out_min = -100.0f,
    .out_max = 100.0f,
};

static efw_status_t adc_read(void *ctx, void *buf, uint16_t len, uint16_t *actual) {
    adc_ctx_t *adc = (adc_ctx_t *)ctx;
    uint16_t *out = (uint16_t *)buf;

    if (!adc || !out || len < sizeof(uint16_t)) return EFW_ERR_INVALID;
    *out = adc->value;
    if (actual) *actual = sizeof(uint16_t);
    return EFW_OK;
}

static efw_status_t line_sensor_read(void *ctx, void *out) {
    EFW_UNUSED(ctx);
    return efw_hal_read("adc1", out, sizeof(uint16_t), 0);
}

static efw_hal_ops_t g_adc_hal = {
    .name = "adc1",
    .type = EFW_HAL_ADC,
    .bus_id = 1,
    .ctx = &g_adc_ctx,
    .read = adc_read,
};

static efw_sensor_ops_t g_line_sensor = {
    .name = "line_adc",
    .type = EFW_SENSOR_LINE_TRACKING,
    .channel_count = 1,
    .hal_name = "adc1",
    .read = line_sensor_read,
};

static efw_algo_ops_t g_pid_algo = {
    .name = "motor_pid",
    .type = EFW_ALGO_CONTROL,
    .ctx = &g_pid,
    .run = efw_pid_run,
};

void app_init(void) {
    efw_init();
    efw_hal_register(&g_adc_hal);
    efw_sensor_register(&g_line_sensor);
    efw_algo_register(&g_pid_algo);
}

void app_loop(void) {
    uint16_t sensor_value = 0;
    efw_pid_input_t pid_in;
    efw_pid_output_t pid_out;

    g_adc_ctx.value = 1200;
    efw_sensor_read("line_adc", &sensor_value);

    pid_in.setpoint = 1500.0f;
    pid_in.feedback = (float)sensor_value;
    pid_in.dt = 0.001f;
    efw_algo_run("motor_pid", &pid_in, &pid_out);
}

int main(void) {
    app_init();
    app_loop();
    return 0;
}
