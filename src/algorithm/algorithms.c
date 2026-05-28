#include "efw/algorithm/algorithms.h"

static float clamp_float(float value, float min_value, float max_value) {
    if (min_value < max_value) {
        if (value < min_value) return min_value;
        if (value > max_value) return max_value;
    }
    return value;
}

void efw_pid_reset(efw_pid_t *pid) {
    if (!pid) return;
    pid->integral = 0.0f;
    pid->prev_error = 0.0f;
}

efw_status_t efw_pid_run(void *ctx, const void *in, void *out) {
    efw_pid_t *pid = (efw_pid_t *)ctx;
    const efw_pid_input_t *input = (const efw_pid_input_t *)in;
    efw_pid_output_t *output = (efw_pid_output_t *)out;
    float error;
    float derivative;
    float value;

    if (!pid || !input || !output || input->dt <= 0.0f) return EFW_ERR_INVALID;

    error = input->setpoint - input->feedback;
    pid->integral += error * input->dt;
    derivative = (error - pid->prev_error) / input->dt;
    value = pid->kp * error + pid->ki * pid->integral + pid->kd * derivative;
    value = clamp_float(value, pid->out_min, pid->out_max);

    pid->prev_error = error;
    output->output = value;
    output->error = error;
    return EFW_OK;
}

void efw_moving_avg_reset(efw_moving_avg_t *avg) {
    if (!avg) return;
    avg->count = 0;
    avg->index = 0;
    avg->sum = 0.0f;
}

efw_status_t efw_moving_avg_run(void *ctx, const void *in, void *out) {
    efw_moving_avg_t *avg = (efw_moving_avg_t *)ctx;
    const float *sample = (const float *)in;
    float *result = (float *)out;

    if (!avg || !avg->buffer || avg->capacity == 0 || !sample || !result) return EFW_ERR_INVALID;

    if (avg->count < avg->capacity) {
        avg->buffer[avg->index] = *sample;
        avg->sum += *sample;
        avg->count++;
    } else {
        avg->sum -= avg->buffer[avg->index];
        avg->buffer[avg->index] = *sample;
        avg->sum += *sample;
    }

    avg->index++;
    if (avg->index >= avg->capacity) avg->index = 0;

    *result = avg->sum / (float)avg->count;
    return EFW_OK;
}
