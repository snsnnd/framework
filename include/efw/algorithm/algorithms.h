#ifndef EFW_ALGORITHMS_H
#define EFW_ALGORITHMS_H

#include "efw/core/common.h"

typedef struct {
    float kp;
    float ki;
    float kd;
    float integral;
    float prev_error;
    float out_min;
    float out_max;
} efw_pid_t;

typedef struct {
    float setpoint;
    float feedback;
    float dt;
} efw_pid_input_t;

typedef struct {
    float output;
    float error;
} efw_pid_output_t;

typedef struct {
    float *buffer;
    uint16_t capacity;
    uint16_t count;
    uint16_t index;
    float sum;
} efw_moving_avg_t;

void efw_pid_reset(efw_pid_t *pid);
efw_status_t efw_pid_run(void *ctx, const void *in, void *out);

void efw_moving_avg_reset(efw_moving_avg_t *avg);
efw_status_t efw_moving_avg_run(void *ctx, const void *in, void *out);

#endif
