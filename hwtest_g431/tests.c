/* EFW on-hardware test suite for CT117E-M4 (STM32G431RBT6)
 *
 * Tests the EFW C framework core only (no Python toolchain):
 *   init/diag, data structures, HAL/COMM/SENSOR/ACTUATOR registries,
 *   motor layer, algorithms (PID/moving avg/low-pass/ramp),
 *   line tracking middleware + follower, module lifecycle,
 *   state machine, topic events, event queue, scheduler (+stats/jitter),
 *   performance counters, and a live LED/heartbeat demo.
 *
 * Output: UART broadcast on USART1/2/3 @115200.
 */
#include <stdint.h>
#include <string.h>
#include "efw/efw.h"
#include "bsp.h"
#include "lcd.h"
#include "stress.h"
#include "dashboard.h"
#include "game.h"
#include "boundary.h"

/* =================== test harness =================== */

int t_total = 0, t_pass = 0;   /* non-static: dashboard reads these */
static const char *t_cur = "";
static int t_fail_flag = 0;

static void t_start(const char *name) { t_cur = name; t_fail_flag = 0; }

static void t_end(void)
{
    t_total++;
    if (!t_fail_flag) {
        t_pass++;
        outs("[TEST] "); outs(t_cur); outs(" ......... PASS\r\n");
    } else {
        outs("[TEST] "); outs(t_cur); outs(" ......... FAIL\r\n");
    }
}

#define CHECK(cond) do { \
    if (!(cond) && !t_fail_flag) { \
        t_fail_flag = 1; \
        outs("    !! check failed: " #cond " @line "); outi(__LINE__); outs("\r\n"); \
    } } while (0)

static int feqf(float a, float b, float eps)
{
    float d = a - b;
    return (d < 0.0f ? -d : d) <= eps;
}

/* =================== stub HAL / device callbacks =================== */

/* GPIO stub: buf[0]=pin, buf[1]=value */
static uint8_t g_gpio_pin, g_gpio_val; static int g_gpio_writes;
static efw_status_t gpio_write_cb(void *ctx, const void *buf, uint16_t len, uint16_t *actual)
{
    (void)ctx;
    if (!buf || len < 2) return EFW_ERR_INVALID;
    g_gpio_pin = ((const uint8_t *)buf)[0];
    g_gpio_val = ((const uint8_t *)buf)[1];
    g_gpio_writes++;
    if (actual) *actual = len;
    return EFW_OK;
}

/* ADC stub: returns incrementing 16-bit value */
static uint16_t g_adc_val = 1000;
static efw_status_t adc_read_cb(void *ctx, void *buf, uint16_t len, uint16_t *actual)
{
    (void)ctx;
    if (!buf || len < 2) return EFW_ERR_INVALID;
    g_adc_val++;
    *(uint16_t *)buf = g_adc_val;
    if (actual) *actual = 2;
    return EFW_OK;
}

/* UART stub for comm: counts bytes */
static int g_uart_tx, g_uart_rx;
static efw_status_t uart_send_cb(void *ctx, const uint8_t *data, uint16_t len, uint16_t *actual)
{ (void)ctx; (void)data; g_uart_tx += len; if (actual) *actual = len; return EFW_OK; }
static efw_status_t uart_recv_cb(void *ctx, uint8_t *data, uint16_t len, uint16_t *actual)
{ (void)ctx; if (len) data[0] = 0xA5; if (actual) *actual = (len > 0) ? 1 : 0; g_uart_rx++; return EFW_OK; }

/* ioctl stub */
static uint32_t g_ioctl_cmd;
static efw_status_t ioctl_cb(void *ctx, uint32_t cmd, void *arg)
{ (void)ctx; (void)arg; g_ioctl_cmd = cmd; return EFW_OK; }

static efw_hal_ops_t h_gpio = { "gpio_led", EFW_HAL_GPIO, 1, 0, 0, 0, gpio_write_cb, 0 };
static efw_hal_ops_t h_adc  = { "adc_stub",  EFW_HAL_ADC,  1, 0, 0, adc_read_cb, 0, ioctl_cb };
static efw_hal_ops_t h_pwm  = { "pwm_stub",  EFW_HAL_PWM,  1, 0, 0, 0, 0, 0 };
static efw_hal_ops_t h_uart = { "uart1",     EFW_HAL_UART, 1, 0, 0, 0, 0, 0 };

static efw_comm_ops_t c_dbg = { "dbg_comm", EFW_COMM_UART, "uart1", 0, 0, 0, uart_send_cb, uart_recv_cb };

/* sensors */
static uint16_t g_sensor_val;
static efw_status_t sensor_read_cb(void *ctx, void *out, uint16_t out_size)
{
    (void)ctx;
    if (!out || out_size < 2) return EFW_ERR_RANGE;
    g_sensor_val += 3;
    *(uint16_t *)out = g_sensor_val;
    return EFW_OK;
}
static efw_sensor_ops_t s_adc = { "adc_sensor", EFW_SENSOR_CUSTOM, 1, "adc_stub", 0, 0, 0, sensor_read_cb };

/* line tracking sensor: pattern settable, 5 channels */
static efw_line_tracking_data_t g_line_pattern;
static efw_status_t line_read_cb(void *ctx, void *out, uint16_t out_size)
{
    (void)ctx;
    if (!out || out_size < (uint16_t)sizeof(efw_line_tracking_data_t)) return EFW_ERR_RANGE;
    *(efw_line_tracking_data_t *)out = g_line_pattern;
    return EFW_OK;
}
static efw_sensor_ops_t s_line = { "line5", EFW_SENSOR_LINE_TRACKING, 5, 0, 0, 0, 0, line_read_cb };

/* perf sensor */
static uint32_t g_perf_calls;
static efw_status_t perf_read_cb(void *ctx, void *out, uint16_t out_size)
{
    (void)ctx;
    if (!out || out_size < 2) return EFW_ERR_RANGE;
    g_perf_calls++;
    *(uint16_t *)out = 7;
    return EFW_OK;
}
static efw_sensor_ops_t s_perf = { "perf_sensor", EFW_SENSOR_CUSTOM, 1, 0, 0, 0, 0, perf_read_cb };

/* actuators: record command */
typedef struct { float speed; float dir; int writes; int enables; int disables; } motor_rec_t;
static motor_rec_t g_ma, g_mb;
static efw_status_t motor_write_cb(void *ctx, const void *cmd, uint16_t cmd_size)
{
    motor_rec_t *r = (motor_rec_t *)ctx;
    if (!cmd || cmd_size < (uint16_t)sizeof(efw_motor_cmd_t)) return EFW_ERR_RANGE;
    const efw_motor_cmd_t *m = (const efw_motor_cmd_t *)cmd;
    r->speed = m->speed; r->dir = m->direction; r->writes++;
    return EFW_OK;
}
static efw_status_t motor_enable_cb(void *ctx)  { ((motor_rec_t *)ctx)->enables++;  return EFW_OK; }
static efw_status_t motor_disable_cb(void *ctx) { ((motor_rec_t *)ctx)->disables++; return EFW_OK; }
static efw_actuator_ops_t a_left  = { "m_left",  EFW_ACTUATOR_MOTOR, "pwm_stub", 0, &g_ma, 0, motor_enable_cb, motor_disable_cb, motor_write_cb };
static efw_actuator_ops_t a_right = { "m_right", EFW_ACTUATOR_MOTOR, "pwm_stub", 0, &g_mb, 0, motor_enable_cb, motor_disable_cb, motor_write_cb };

/* LED actuator */
typedef struct { float value; int writes; int enables; int disables; } led_rec_t;
static led_rec_t g_led_rec;
static efw_status_t led_write_cb(void *ctx, const void *cmd, uint16_t cmd_size)
{
    led_rec_t *r = (led_rec_t *)ctx;
    if (!cmd || cmd_size < (uint16_t)sizeof(efw_actuator_cmd_t)) return EFW_ERR_RANGE;
    r->value = ((const efw_actuator_cmd_t *)cmd)->value; r->writes++;
    return EFW_OK;
}
static efw_status_t led_enable_cb(void *ctx)  { ((led_rec_t *)ctx)->enables++;  return EFW_OK; }
static efw_status_t led_disable_cb(void *ctx) { ((led_rec_t *)ctx)->disables++; return EFW_OK; }
static efw_actuator_ops_t a_led = { "led_act", EFW_ACTUATOR_LED, "pwm_stub", 0, &g_led_rec, 0, led_enable_cb, led_disable_cb, led_write_cb };

/* follower motors (separate records) */
static motor_rec_t g_lf_l, g_lf_r;
static efw_actuator_ops_t a_lf_l   = { "lf_l", EFW_ACTUATOR_MOTOR, "pwm_stub", 0, &g_lf_l, 0, motor_enable_cb, motor_disable_cb, motor_write_cb };
static efw_actuator_ops_t a_lf_r   = { "lf_r", EFW_ACTUATOR_MOTOR, "pwm_stub", 0, &g_lf_r, 0, motor_enable_cb, motor_disable_cb, motor_write_cb };

/* algorithms */
static efw_pid_t g_pid, g_aw_pid, g_ic_pid, g_line_pid, g_perf_pid;
static efw_moving_avg_t g_avg;
static float g_avg_buf[4];
static efw_low_pass_t g_lp;
static efw_ramp_t g_ramp;

static const efw_algo_ops_t al_pid    = { "test_pid", EFW_ALGO_CONTROL, &g_pid,     efw_pid_run };
static const efw_algo_ops_t al_aw     = { "aw_pid",   EFW_ALGO_CONTROL, &g_aw_pid,  efw_pid_run };
static const efw_algo_ops_t al_ic     = { "ic_pid",   EFW_ALGO_CONTROL, &g_ic_pid,  efw_pid_run };
static const efw_algo_ops_t al_avg    = { "test_avg", EFW_ALGO_FILTER,  &g_avg,     efw_moving_avg_run };
static const efw_algo_ops_t al_lp     = { "test_lp",  EFW_ALGO_FILTER,  &g_lp,      efw_low_pass_run };
static const efw_algo_ops_t al_ramp   = { "test_ramp",EFW_ALGO_CONTROL, &g_ramp,    efw_ramp_run };
static const efw_algo_ops_t al_lpid   = { "line_pid", EFW_ALGO_CONTROL, &g_line_pid,efw_pid_run };
static const efw_algo_ops_t al_perfp  = { "perf_pid", EFW_ALGO_CONTROL, &g_perf_pid,efw_pid_run };

/* modules */
typedef struct { int init, start, poll, stop; } mod_cnt_t;
static mod_cnt_t g_mod_a, g_mod_b;
static int g_mod_order[4]; static int g_mod_order_n;
static efw_status_t mod_init_cb(void *ctx)
{ mod_cnt_t *m = (mod_cnt_t *)ctx; m->init++; if (g_mod_order_n < 4) g_mod_order[g_mod_order_n++] = (ctx == &g_mod_a) ? 1 : 2; return EFW_OK; }
static efw_status_t mod_start_cb(void *ctx){ ((mod_cnt_t *)ctx)->start++; return EFW_OK; }
static efw_status_t mod_stop_cb(void *ctx) { ((mod_cnt_t *)ctx)->stop++;  return EFW_OK; }
static efw_status_t mod_poll_cb(void *ctx) { ((mod_cnt_t *)ctx)->poll++;  return EFW_OK; }
static efw_module_ops_t m_b = { "mod_b", EFW_MODULE_SERVICE, 5, &g_mod_b, mod_init_cb, mod_start_cb, mod_stop_cb, mod_poll_cb };
static efw_module_ops_t m_a = { "mod_a", EFW_MODULE_APP,     1, &g_mod_a, mod_init_cb, mod_start_cb, mod_stop_cb, mod_poll_cb };

/* state machine */
static int g_state_enters[3];
static int g_sm_cond = 0;
static const char *g_trace_from[4]; static const char *g_trace_to[4]; static int g_trace_n;
static void sm_trace_cb(const efw_sm_context_t *ctx, const char *from, const char *to, uint32_t t, void *user)
{ (void)ctx; (void)t; (void)user; if (g_trace_n < 4) { g_trace_from[g_trace_n] = from; g_trace_to[g_trace_n] = to; g_trace_n++; } }
static efw_status_t st_idle_enter(void *c){ (void)c; g_state_enters[0]++; return EFW_OK; }
static efw_status_t st_run_enter(void *c) { (void)c; g_state_enters[1]++; return EFW_OK; }
static efw_status_t st_stop_enter(void *c){ (void)c; g_state_enters[2]++; return EFW_OK; }
static const efw_state_def_t st_idle = { "IDLE", 0, st_idle_enter, 0, 0 };
static const efw_state_def_t st_run  = { "RUN",  0, st_run_enter,  0, 0 };
static const efw_state_def_t st_stop = { "STOP", 0, st_stop_enter, 0, 0 };
static int sm_cond_fn(void) { return g_sm_cond; }
static const efw_sm_transition_t g_trans[] = {
    { &st_idle, &st_run,  sm_cond_fn, 0, 0,  1 },   /* condition-triggered */
    { &st_run,  &st_stop, 0,          0, 50, 1 },   /* 50ms timeout */
};
static efw_sm_context_t g_sm;

/* topic events */
static int g_cb_a_hits, g_cb_b_hits; static uint16_t g_cb_a_topic; static int32_t g_cb_a_data;static void topic_cb_a(uint16_t id, const void *data, uint16_t size, void *user)
{ (void)user; g_cb_a_hits++; g_cb_a_topic = id; if (data && size >= 4) g_cb_a_data = *(const int32_t *)data; }
static void topic_cb_b(uint16_t id, const void *data, uint16_t size, void *user)
{ (void)id; (void)data; (void)size; (void)user; g_cb_b_hits++; }

/* event queue dispatch */
#define EQ_MAX 16
static char g_eq_names[EQ_MAX][8]; static uint16_t g_eq_topics[EQ_MAX]; static int g_eq_n;
static void eq_dispatch(const char *name, uint16_t topic, const void *data, uint16_t size)
{
    (void)data; (void)size;
    if (g_eq_n < EQ_MAX) {
        g_eq_topics[g_eq_n] = topic;
        if (name) { strncpy(g_eq_names[g_eq_n], name, 7); g_eq_names[g_eq_n][7] = 0; }
        else g_eq_names[g_eq_n][0] = 0;
        g_eq_n++;
    }
}

/* scheduler */
static uint32_t g_cnt1, g_cnt2, g_cnt3, g_cnt_slow, g_cnt_jit;
static uint32_t time_ms_fn(void *u) { (void)u; return g_ms_tick; }
static uint32_t time_us_fn(void *u) { (void)u; return dwt_us(); }
static uint32_t g_jit_last, g_jit_min, g_jit_max, g_jit_sum, g_jit_n;
static efw_status_t task_count1(void *c)   { (void)c; g_cnt1++; return EFW_OK; }
static efw_status_t task_count2(void *c)   { (void)c; g_cnt2++; return EFW_OK; }
static efw_status_t task_count3(void *c)   { (void)c; g_cnt3++; return EFW_OK; }
static efw_status_t task_slow(void *c)     { uint32_t t0 = dwt_cycles(); (void)c; g_cnt_slow++; while ((dwt_cycles() - t0) < 3u * 16000u) { } return EFW_OK; }
static efw_status_t task_jit(void *c)
{
    uint32_t now = dwt_us();
    (void)c; g_cnt_jit++;
    if (g_jit_last) {
        uint32_t p = now - g_jit_last;
        if (!g_jit_min || p < g_jit_min) g_jit_min = p;
        if (p > g_jit_max) g_jit_max = p;
        g_jit_sum += p; g_jit_n++;
    }
    g_jit_last = now;
    return EFW_OK;
}
static void sched_spin(uint32_t duration_ms)
{
    uint32_t start = g_ms_tick, last = start;
    while ((g_ms_tick - start) < duration_ms) {
        bsp_loop_hook();
        uint32_t now = g_ms_tick;
        if (now != last) { efw_scheduler_tick(now - last); last = now; }
    }
}

/* =================== tests =================== */

static uint32_t g_init_us;

static void test_core_init(void)
{
    uint32_t t0 = dwt_us();
    efw_status_t s = efw_init();
    g_init_us = dwt_us() - t0;
    t_start("core_init");
    CHECK(s == EFW_OK);
    CHECK(efw_diag_last_error()->code == EFW_OK);
    CHECK(efw_diag_error_count() == 0);
    t_end();
    outs("[PERF] efw_init = "); outi((int32_t)g_init_us); outs(" us\r\n");
}

static void test_ds_ringbuf(void)
{
    static efw_ringbuf_t rb; static uint8_t buf[4];
    uint8_t v; size_t n;
    t_start("ds_ringbuf");
    CHECK(efw_ringbuf_init(&rb, buf, 4) == EFW_OK);
    CHECK(efw_ringbuf_init(&rb, 0, 4) == EFW_ERR_INVALID);
    for (int i = 1; i <= 4; i++) CHECK(efw_ringbuf_push(&rb, (uint8_t)i) == EFW_OK);
    CHECK(efw_ringbuf_full(&rb));
    CHECK(efw_ringbuf_push(&rb, 5) == EFW_ERR_FULL);
    CHECK(efw_ringbuf_pop(&rb, &v) == EFW_OK && v == 1);
    CHECK(efw_ringbuf_pop(&rb, &v) == EFW_OK && v == 2);
    CHECK(efw_ringbuf_push(&rb, 5) == EFW_OK);          /* wraparound */
    CHECK(efw_ringbuf_push(&rb, 6) == EFW_OK);
    CHECK(efw_ringbuf_size(&rb) == 4);
    CHECK(efw_ringbuf_pop(&rb, &v) == EFW_OK && v == 3);
    CHECK(efw_ringbuf_pop(&rb, &v) == EFW_OK && v == 4);
    CHECK(efw_ringbuf_pop(&rb, &v) == EFW_OK && v == 5);
    CHECK(efw_ringbuf_pop(&rb, &v) == EFW_OK && v == 6);
    CHECK(efw_ringbuf_empty(&rb));
    CHECK(efw_ringbuf_pop(&rb, &v) == EFW_ERR_NOT_FOUND);
    n = efw_ringbuf_write(&rb, "abcdef", 6);            /* bulk write > capacity */
    CHECK(n == 4);
    static uint8_t rd[8]; memset(rd, 0, sizeof(rd));
    n = efw_ringbuf_read(&rb, rd, 8);
    CHECK(n == 4 && rd[0] == 'a' && rd[1] == 'b' && rd[2] == 'c' && rd[3] == 'd');
    t_end();
}

static void test_ds_queue(void)
{
    static efw_queue_t q; static int32_t qb[3]; int32_t v;
    t_start("ds_queue");
    CHECK(efw_queue_init(&q, qb, sizeof(int32_t), 3) == EFW_OK);
    CHECK(efw_queue_push(&q, &(int32_t){10}) == EFW_OK);
    CHECK(efw_queue_push(&q, &(int32_t){20}) == EFW_OK);
    CHECK(efw_queue_push(&q, &(int32_t){30}) == EFW_OK);
    CHECK(efw_queue_full(&q));
    CHECK(efw_queue_push(&q, &(int32_t){40}) == EFW_ERR_FULL);
    CHECK(efw_queue_peek(&q, &v) == EFW_OK && v == 10);
    CHECK(efw_queue_pop(&q, &v) == EFW_OK && v == 10);
    CHECK(efw_queue_pop(&q, &v) == EFW_OK && v == 20);
    CHECK(efw_queue_pop(&q, &v) == EFW_OK && v == 30);
    CHECK(efw_queue_empty(&q));
    CHECK(efw_queue_pop(&q, &v) == EFW_ERR_NOT_FOUND);
    t_end();
}

static void test_ds_stack(void)
{
    static efw_stack_t st; static int32_t sb[3]; int32_t v;
    t_start("ds_stack");
    CHECK(efw_stack_init(&st, sb, sizeof(int32_t), 3) == EFW_OK);
    CHECK(efw_stack_push(&st, &(int32_t){1}) == EFW_OK);
    CHECK(efw_stack_push(&st, &(int32_t){2}) == EFW_OK);
    CHECK(efw_stack_push(&st, &(int32_t){3}) == EFW_OK);
    CHECK(efw_stack_full(&st));
    CHECK(efw_stack_peek(&st, &v) == EFW_OK && v == 3);
    CHECK(efw_stack_pop(&st, &v) == EFW_OK && v == 3);
    CHECK(efw_stack_pop(&st, &v) == EFW_OK && v == 2);
    CHECK(efw_stack_pop(&st, &v) == EFW_OK && v == 1);
    CHECK(efw_stack_pop(&st, &v) == EFW_ERR_NOT_FOUND);
    t_end();
}

static void test_hal_registry(void)
{
    const efw_hal_ops_t *got;
    t_start("hal_registry");
    CHECK(efw_hal_register(&h_gpio) == EFW_OK);
    CHECK(efw_hal_register(&h_gpio) == EFW_ERR_ALREADY_EXISTS);
    CHECK(efw_hal_register(&h_adc) == EFW_OK);
    CHECK(efw_hal_register(&h_pwm) == EFW_OK);
    CHECK(efw_hal_register(&h_uart) == EFW_OK);
    CHECK(efw_hal_count() == 4);
    CHECK(efw_hal_get("gpio_led", &got) == EFW_OK && got == &h_gpio);
    CHECK(efw_hal_get("nope", &got) == EFW_ERR_NOT_FOUND);
    CHECK(efw_hal_unregister("gpio_led") == EFW_OK);
    CHECK(efw_hal_get("gpio_led", &got) == EFW_ERR_NOT_FOUND);
    CHECK(efw_hal_register(&h_gpio) == EFW_OK);          /* re-register for io tests */
    t_end();
}

static void test_hal_io_route(void)
{
    uint8_t cmd[2] = { 5, 1 }; uint16_t act = 0; uint16_t v;
    t_start("hal_io_route");
    CHECK(efw_hal_write("gpio_led", cmd, 2, &act) == EFW_OK && act == 2);
    CHECK(g_gpio_writes == 1 && g_gpio_pin == 5 && g_gpio_val == 1);
    CHECK(efw_hal_read("adc_stub", &v, 2, &act) == EFW_OK && act == 2 && v == 1001);
    CHECK(efw_hal_ioctl("adc_stub", 0xABCD, 0) == EFW_OK && g_ioctl_cmd == 0xABCD);
    CHECK(efw_hal_read("gpio_led", &v, 2, &act) == EFW_ERR_INVALID);  /* no read cb */
    CHECK(efw_hal_write("nope", cmd, 2, &act) == EFW_ERR_NOT_FOUND);
    t_end();
}

static void test_comm_registry(void)
{
    const efw_hal_ops_t *hal;
    const efw_comm_ops_t *got;
    uint8_t tx[3] = { 1, 2, 3 }; uint8_t rx[4] = { 0 }; uint16_t act = 0;
    static efw_comm_ops_t c_bad = { "bad_comm", EFW_COMM_UART, "ghost_hal", 0, 0, 0, uart_send_cb, uart_recv_cb };
    t_start("comm_registry");
    CHECK(efw_comm_register(&c_dbg) == EFW_OK);
    CHECK(efw_comm_register(&c_dbg) == EFW_ERR_ALREADY_EXISTS);
    CHECK(efw_comm_get("dbg_comm", &got) == EFW_OK && got == &c_dbg);
    CHECK(efw_comm_bind_hal("dbg_comm", &hal) == EFW_OK && hal == &h_uart);
    CHECK(efw_comm_register(&c_bad) == EFW_ERR_NOT_FOUND);   /* hal binding validated */
    CHECK(efw_comm_send("dbg_comm", tx, 3, &act) == EFW_OK && act == 3 && g_uart_tx == 3);
    CHECK(efw_comm_recv("dbg_comm", rx, 4, &act) == EFW_OK && rx[0] == 0xA5);
    t_end();
}

static void test_sensor_registry(void)
{
    const efw_sensor_ops_t *got;
    uint16_t v = 0;
    static efw_sensor_ops_t s_bad = { "bad_sensor", EFW_SENSOR_CUSTOM, 1, "ghost_hal", 0, 0, 0, sensor_read_cb };
    t_start("sensor_registry");
    CHECK(efw_sensor_register(&s_adc) == EFW_OK);
    CHECK(efw_sensor_register(&s_adc) == EFW_ERR_ALREADY_EXISTS);
    CHECK(efw_sensor_get("adc_sensor", &got) == EFW_OK && got == &s_adc);
    CHECK(efw_sensor_count_by_type(EFW_SENSOR_CUSTOM) == 1);
    CHECK(efw_sensor_read("adc_sensor", &v, 2) == EFW_OK && v == 3);
    CHECK(efw_sensor_read("adc_sensor", &v, 2) == EFW_OK && v == 6);
    CHECK(efw_sensor_register(&s_bad) == EFW_ERR_NOT_FOUND); /* bad hal_name rejected */
    t_end();
}

static void test_actuator_led(void)
{
    efw_actuator_cmd_t cmd = { 0.7f };
    t_start("actuator_led");
    CHECK(efw_actuator_register(&a_led) == EFW_OK);
    CHECK(efw_actuator_enable("led_act") == EFW_OK && g_led_rec.enables == 1);
    CHECK(efw_actuator_write("led_act", &cmd, sizeof(cmd)) == EFW_OK);
    CHECK(g_led_rec.writes == 1 && feqf(g_led_rec.value, 0.7f, 1e-6f));
    CHECK(efw_actuator_disable("led_act") == EFW_OK && g_led_rec.disables == 1);
    t_end();
}

static void test_motor_layer(void)
{
    t_start("motor_layer");
    CHECK(efw_actuator_register(&a_left) == EFW_OK);
    CHECK(efw_actuator_register(&a_right) == EFW_OK);
    CHECK(efw_motor_set_speed("m_left", 0.5f) == EFW_OK);
    CHECK(feqf(g_ma.speed * (g_ma.dir < 0 ? -1.0f : 1.0f), 0.5f, 1e-6f));
    CHECK(efw_motor_set_speed("m_left", -0.5f) == EFW_OK);
    CHECK(feqf(g_ma.speed * (g_ma.dir < 0 ? -1.0f : 1.0f), -0.5f, 1e-6f));
    CHECK(efw_motor_stop("m_left") == EFW_OK && feqf(g_ma.speed, 0.0f, 1e-6f));
    CHECK(efw_motor_set_diff("m_left", "m_right", 60.0f, 10.0f) == EFW_OK);
    CHECK(feqf(g_ma.speed * (g_ma.dir < 0 ? -1.0f : 1.0f), 50.0f, 1e-4f));  /* left = 60-10 */
    CHECK(feqf(g_mb.speed * (g_mb.dir < 0 ? -1.0f : 1.0f), 70.0f, 1e-4f));  /* right = 60+10 */
    CHECK(efw_motor_set_diff_limited("m_left", "m_right", 60.0f, 1000.0f, 0.0f, 100.0f) == EFW_OK);
    CHECK(feqf(g_ma.speed, 0.0f, 1e-4f));                    /* clamped to min */
    CHECK(feqf(g_mb.speed, 100.0f, 1e-4f));                  /* clamped to max */
    t_end();
}

static void test_algo_pid(void)
{
    efw_pid_input_t in; efw_pid_output_t out;
    t_start("algo_pid");
    CHECK(efw_algo_register(&al_pid) == EFW_OK);
    CHECK(efw_algo_register(&al_pid) == EFW_ERR_ALREADY_EXISTS);
    CHECK(efw_algo_register(&al_aw) == EFW_OK);
    CHECK(efw_algo_register(&al_ic) == EFW_OK);
    CHECK(efw_algo_register(&al_avg) == EFW_OK);
    CHECK(efw_algo_register(&al_lp) == EFW_OK);
    CHECK(efw_algo_register(&al_ramp) == EFW_OK);
    CHECK(efw_algo_register(&al_perfp) == EFW_OK);
    CHECK(efw_algo_count() >= 7);
    memset(&g_pid, 0, sizeof(g_pid));
    g_pid.kp = 2.0f; g_pid.ki = 1.0f; g_pid.kd = 0.1f;
    g_pid.out_min = -1000.0f; g_pid.out_max = 1000.0f;
    efw_pid_reset(&g_pid);
    in.setpoint = 1.0f; in.feedback = 0.0f; in.dt = 0.1f; in.feedforward = 0.0f;
    CHECK(efw_algo_run("test_pid", &in, sizeof(in), &out, sizeof(out)) == EFW_OK);
    CHECK(feqf(out.output, 3.1f, 1e-3f));                /* P=2 I=0.1 D=1 */
    in.feedback = 0.5f;
    CHECK(efw_algo_run("test_pid", &in, sizeof(in), &out, sizeof(out)) == EFW_OK);
    CHECK(feqf(out.output, 0.65f, 1e-3f));               /* P=1 I=0.15 D=-0.5 */
    CHECK(efw_algo_get("test_pid", 0) == EFW_ERR_INVALID);
    t_end();
}

static void test_algo_pid_antawindup(void)
{
    efw_pid_input_t in; efw_pid_output_t out;
    t_start("algo_pid_antiwindup");
    memset(&g_aw_pid, 0, sizeof(g_aw_pid));
    g_aw_pid.ki = 1.0f; g_aw_pid.out_min = -0.5f; g_aw_pid.out_max = 0.5f;
    g_aw_pid.anti_windup = 1;
    efw_pid_reset(&g_aw_pid);
    in.setpoint = 100.0f; in.feedback = 0.0f; in.dt = 1.0f; in.feedforward = 0.0f;
    CHECK(efw_algo_run("aw_pid", &in, sizeof(in), &out, sizeof(out)) == EFW_OK);
    CHECK(feqf(out.output, 0.5f, 1e-6f));                /* clamped */
    in.setpoint = 0.0f;
    CHECK(efw_algo_run("aw_pid", &in, sizeof(in), &out, sizeof(out)) == EFW_OK);
    CHECK(feqf(out.output, 0.5f, 1e-3f));                /* integral back-calculated, no windup */
    /* integral clamping */
    memset(&g_ic_pid, 0, sizeof(g_ic_pid));
    g_ic_pid.ki = 1.0f; g_ic_pid.integral_min = -0.05f; g_ic_pid.integral_max = 0.05f;
    g_ic_pid.out_min = -1000.0f; g_ic_pid.out_max = 1000.0f;
    efw_pid_reset(&g_ic_pid);
    in.setpoint = 1.0f; in.feedback = 0.0f; in.dt = 1.0f;
    CHECK(efw_algo_run("ic_pid", &in, sizeof(in), &out, sizeof(out)) == EFW_OK);
    CHECK(feqf(out.output, 0.05f, 1e-6f));               /* integral clamped to 0.05 */
    t_end();
}

static void test_algo_filters(void)
{
    float in, out;
    t_start("algo_filters");
    memset(&g_avg, 0, sizeof(g_avg));
    g_avg.buffer = g_avg_buf; g_avg.capacity = 4;
    efw_moving_avg_reset(&g_avg);
    in = 1.0f; efw_algo_run("test_avg", &in, 4, &out, 4); CHECK(feqf(out, 1.0f, 1e-5f));
    in = 2.0f; efw_algo_run("test_avg", &in, 4, &out, 4); CHECK(feqf(out, 1.5f, 1e-5f));
    in = 3.0f; efw_algo_run("test_avg", &in, 4, &out, 4); CHECK(feqf(out, 2.0f, 1e-5f));
    in = 4.0f; efw_algo_run("test_avg", &in, 4, &out, 4); CHECK(feqf(out, 2.5f, 1e-5f));
    in = 5.0f; efw_algo_run("test_avg", &in, 4, &out, 4); CHECK(feqf(out, 3.5f, 1e-5f)); /* window slides */
    /* low-pass: y += 0.5*(x-y) */
    g_lp.alpha = 0.5f;
    efw_low_pass_reset(&g_lp, 0.0f);
    in = 1.0f; efw_algo_run("test_lp", &in, 4, &out, 4); CHECK(feqf(out, 0.5f, 1e-5f));
    in = 1.0f; efw_algo_run("test_lp", &in, 4, &out, 4); CHECK(feqf(out, 0.75f, 1e-5f));
    /* ramp: rise 2/s, dt=0.1 */
    g_ramp.rise_rate = 2.0f; g_ramp.fall_rate = 5.0f;
    efw_ramp_reset(&g_ramp, 0.0f);
    { efw_ramp_input_t ri = { 10.0f, 0.1f };
      efw_algo_run("test_ramp", &ri, sizeof(ri), &out, 4); CHECK(feqf(out, 0.2f, 1e-5f));
      efw_algo_run("test_ramp", &ri, sizeof(ri), &out, 4); CHECK(feqf(out, 0.4f, 1e-5f));
      ri.target = 0.0f;
      efw_algo_run("test_ramp", &ri, sizeof(ri), &out, 4); CHECK(feqf(out, 0.0f, 1e-5f)); /* fall clamps to 0 */ }
    t_end();
}

static void test_line_tracking(void)
{
    static const float weights[5] = { -2.0f, -1.0f, 0.0f, 1.0f, 2.0f };
    efw_line_tracking_data_t d;
    float err, turn;
    efw_line_follower_t fol;
    efw_line_follower_config_t cfg;
    t_start("line_tracking");
    CHECK(efw_sensor_register(&s_line) == EFW_OK);
    g_line_pattern.count = 5;
    g_line_pattern.value[0] = 0; g_line_pattern.value[1] = 0; g_line_pattern.value[2] = 9;
    g_line_pattern.value[3] = 0; g_line_pattern.value[4] = 0;
    CHECK(efw_line_tracking_read("line5", &d) == EFW_OK && d.count == 5 && d.value[2] == 9);
    CHECK(feqf(efw_line_tracking_error_weighted(&d, weights), 0.0f, 1e-6f));
    g_line_pattern.value[0] = 9; g_line_pattern.value[2] = 0;
    CHECK(efw_line_tracking_read("line5", &d) == EFW_OK);
    CHECK(feqf(efw_line_tracking_error_weighted(&d, weights), -2.0f, 1e-6f));
    g_line_pattern.value[0] = 0; g_line_pattern.value[1] = 9;
    CHECK(efw_line_tracking_read("line5", &d) == EFW_OK);
    CHECK(feqf(efw_line_tracking_error_weighted(&d, weights), -1.0f, 1e-6f));
    { uint16_t mask;
      g_line_pattern.value[1] = 0; g_line_pattern.value[2] = 1;         /* {1,0,1,0,0} */
      g_line_pattern.value[0] = 1;
      CHECK(efw_line_tracking_read("line5", &d) == EFW_OK);
      mask = efw_line_tracking_active_mask(&d, 1);
      CHECK(mask == 0x0005);
      CHECK(feqf(efw_line_tracking_error_binary(&d, weights, 1), -1.0f, 1e-6f)); /* (-2+0)/2 */ }
    /* follower integration: sensor -> error -> pid(kp=1) -> diff_limited */
    memset(&g_line_pid, 0, sizeof(g_line_pid));
    g_line_pid.kp = 1.0f; g_line_pid.out_min = -100.0f; g_line_pid.out_max = 100.0f;
    efw_pid_reset(&g_line_pid);
    CHECK(efw_algo_register(&al_lpid) == EFW_OK);
    CHECK(efw_actuator_register(&a_lf_l) == EFW_OK);
    CHECK(efw_actuator_register(&a_lf_r) == EFW_OK);
    memset(&cfg, 0, sizeof(cfg));
    cfg.sensor_name = "line5"; cfg.pid_name = "line_pid";
    cfg.left_motor = "lf_l"; cfg.right_motor = "lf_r";
    cfg.weights = weights; cfg.base_speed = 60.0f;
    cfg.min_speed = 0.0f; cfg.max_speed = 100.0f; cfg.dt = 0.001f;
    cfg.active_value = 1; cfg.binary_mode = 0;
    CHECK(efw_line_follower_bind_config(&fol, &cfg) == EFW_OK);
    /* line centered -> turn 0 -> both 60 */
    memset(&g_line_pattern, 0, sizeof(g_line_pattern));
    g_line_pattern.count = 5; g_line_pattern.value[2] = 9;
    CHECK(efw_line_follower_update(&fol, &err, &turn) == EFW_OK);
    CHECK(feqf(err, 0.0f, 1e-6f) && feqf(turn, 0.0f, 1e-6f));
    CHECK(feqf(g_lf_l.speed * (g_lf_l.dir < 0 ? -1.0f : 1.0f), 60.0f, 1e-4f));
    CHECK(feqf(g_lf_r.speed * (g_lf_r.dir < 0 ? -1.0f : 1.0f), 60.0f, 1e-4f));
    /* line at ch0 (doc: far left, err=-2) -> turn=+2 -> left=58, right=62 */
    g_line_pattern.value[2] = 0; g_line_pattern.value[0] = 9;
    CHECK(efw_line_follower_update(&fol, &err, &turn) == EFW_OK);
    CHECK(feqf(err, -2.0f, 1e-5f) && feqf(turn, 2.0f, 1e-5f));
    CHECK(feqf(g_lf_l.speed * (g_lf_l.dir < 0 ? -1.0f : 1.0f), 58.0f, 1e-4f));
    CHECK(feqf(g_lf_r.speed * (g_lf_r.dir < 0 ? -1.0f : 1.0f), 62.0f, 1e-4f));
    /* one-shot string API */
    CHECK(efw_line_tracking_follow_diff("line5", "line_pid", "lf_l", "lf_r", weights,
                                        60.0f, 0.001f, &err, &turn) == EFW_OK);
    CHECK(feqf(err, -2.0f, 1e-5f) && feqf(turn, 2.0f, 1e-5f));
    t_end();
}

static void test_module_lifecycle(void)
{
    t_start("module_lifecycle");
    CHECK(efw_module_register(&m_b) == EFW_OK);          /* priority 5 */
    CHECK(efw_module_register(&m_a) == EFW_OK);          /* priority 1 */
    CHECK(efw_module_count() == 2);
    g_mod_order_n = 0;
    CHECK(efw_module_init_all() == EFW_OK);
    CHECK(g_mod_order[0] == 1 && g_mod_order[1] == 2);   /* prio 1 before prio 5 */
    CHECK(g_mod_a.init == 1 && g_mod_b.init == 1);
    CHECK(efw_module_start_all() == EFW_OK);
    CHECK(efw_module_poll_all() == EFW_OK);
    CHECK(efw_module_poll_all() == EFW_OK);
    CHECK(efw_module_poll_all() == EFW_OK);
    CHECK(g_mod_a.poll == 3 && g_mod_b.poll == 3);
    CHECK(efw_module_stop("mod_a") == EFW_OK && g_mod_a.stop == 1);
    t_end();
}

static void test_state_machine(void)
{
    efw_sm_context_t *got;
    t_start("state_machine");
    memset(g_state_enters, 0, sizeof(g_state_enters));
    g_trace_n = 0; g_sm_cond = 0;
    CHECK(efw_sm_init(&g_sm, "test_sm", &st_idle, g_trans, 2) == EFW_OK);
    efw_sm_set_trace_callback(sm_trace_cb, 0);
    CHECK(g_state_enters[0] == 1);                        /* initial on_enter */
    CHECK(efw_sm_register(&g_sm) == EFW_OK);
    CHECK(efw_sm_get("test_sm", &got) == EFW_OK && got == &g_sm);
    efw_sm_set_elapsed(&g_sm, 0);
    CHECK(efw_sm_tick(&g_sm) == EFW_OK);
    CHECK(strcmp(efw_sm_current_state(&g_sm), "IDLE") == 0);
    g_sm_cond = 1;
    efw_sm_set_elapsed(&g_sm, 10);
    CHECK(efw_sm_tick(&g_sm) == EFW_OK);
    CHECK(strcmp(efw_sm_current_state(&g_sm), "RUN") == 0);
    CHECK(g_state_enters[1] == 1);
    /* timeout transition: entered at 10, timeout 50ms */
    efw_sm_set_elapsed(&g_sm, 100);
    CHECK(efw_sm_tick(&g_sm) == EFW_OK);
    CHECK(strcmp(efw_sm_current_state(&g_sm), "STOP") == 0);
    CHECK(g_state_enters[2] == 1);
    CHECK(g_trace_n == 2);
    CHECK(efw_sm_time_in_state(&g_sm) == 0);
    t_end();
    outs("    sm transitions: ");
    for (int i = 0; i < g_trace_n && i < 2; i++) {
        outs(g_trace_from[i]); outs("->"); outs(g_trace_to[i]); outs(" ");
    }
    outs("\r\n");
}

static void test_event_topic(void)
{
    int32_t payload = 4242;
    t_start("event_topic");
    CHECK(efw_topic_subscribe(7, topic_cb_a, 0) == EFW_OK);
    CHECK(efw_topic_subscribe(7, topic_cb_b, 0) == EFW_OK);
    CHECK(efw_topic_publish(7, &payload, sizeof(payload)) == EFW_OK);
    CHECK(g_cb_a_hits == 1 && g_cb_b_hits == 1 && g_cb_a_data == 4242 && g_cb_a_topic == 7);
    CHECK(efw_topic_unsubscribe(7, topic_cb_a) == EFW_OK);
    CHECK(efw_topic_publish(7, &payload, sizeof(payload)) == EFW_OK);
    CHECK(g_cb_a_hits == 1 && g_cb_b_hits == 2);          /* only cb_b remains */
    CHECK(efw_topic_publish(9, 0, 0) == EFW_OK);
    CHECK(g_cb_a_hits == 1 && g_cb_b_hits == 2);          /* other topic: no hits */
    t_end();
}

static void test_event_queue(void)
{
    uint8_t small[4] = { 1, 2, 3, 4 };
    t_start("event_queue");
    g_eq_n = 0;
    CHECK(efw_event_queue_init() == EFW_OK);
    CHECK(efw_event_queue_post_named(3, "evA", small, 4) == EFW_OK);
    CHECK(efw_event_queue_post_named(4, "evB", small, 4) == EFW_OK);
    CHECK(efw_event_queue_post_named(5, "evC", small, 4) == EFW_OK);
    CHECK(efw_event_queue_count() == 3);
    /* overflow: capacity is EFW_EVENT_QUEUE_CAPACITY (8) */
    for (int i = 0; i < 10; i++) efw_event_queue_post(6, small, 4);
    CHECK(efw_event_queue_count() == 8);                  /* 3 named + 5 fit, 5 rejected */
    CHECK(efw_event_queue_process_ex(eq_dispatch) == EFW_OK);
    CHECK(g_eq_n == 8);                                   /* dispatch sees exactly the 8 queued */
    CHECK(strcmp(g_eq_names[0], "evA") == 0 && strcmp(g_eq_names[1], "evB") == 0 && strcmp(g_eq_names[2], "evC") == 0);
    CHECK(efw_event_queue_count() == 0);
    CHECK(strcmp(g_eq_names[7], "") == 0);                /* unnamed events */
    t_end();
}

static void test_scheduler_basic(void)
{
    const efw_scheduler_slot_t *slot;
    static efw_scheduler_task_def_t t1 = { "sched_t1", 1,  task_count1, 0 };  /* defs must outlive
        registration: the scheduler stores the def pointer (documented contract) */
    static efw_scheduler_task_def_t t2 = { "sched_t2", 5,  task_count2, 0 };
    static efw_scheduler_task_def_t t3 = { "sched_t3", 10, task_count3, 0 };
    t_start("scheduler_basic");
    efw_scheduler_set_time_providers(time_ms_fn, time_us_fn, 0);
    CHECK(efw_scheduler_register(&t1) == EFW_OK);
    CHECK(efw_scheduler_register(&t2) == EFW_OK);
    CHECK(efw_scheduler_register(&t3) == EFW_OK);
    sched_spin(110);
    CHECK(g_cnt1 >= 100 && g_cnt1 <= 115);
    CHECK(g_cnt2 >= 17  && g_cnt2 <= 24);
    CHECK(g_cnt3 >= 8   && g_cnt3 <= 13);
    CHECK(efw_scheduler_get("sched_t1", &slot) == EFW_OK && slot->run_count == g_cnt1);
    /* pause/resume */
    { uint32_t c2 = g_cnt2; uint32_t c1 = g_cnt1;
      CHECK(efw_scheduler_pause("sched_t2") == EFW_OK);
      sched_spin(10);
      CHECK(g_cnt2 == c2);                                /* paused: frozen */
      CHECK(g_cnt1 > c1);                                 /* others keep running */
      CHECK(efw_scheduler_resume("sched_t2") == EFW_OK);
      sched_spin(10);
      CHECK(g_cnt2 > c2); }
    /* unregister */
    { uint32_t c3 = g_cnt3;
      CHECK(efw_scheduler_unregister("sched_t3") == EFW_OK);
      sched_spin(10);
      CHECK(g_cnt3 == c3); }
    t_end();
    outs("    counts after spin: t1ms="); outi((int32_t)g_cnt1);
    outs(" t5ms="); outi((int32_t)g_cnt2);
    outs(" t10ms="); outi((int32_t)g_cnt3); outs("\r\n");
}

static void test_scheduler_overrun(void)
{
    const efw_scheduler_slot_t *slot;
    static efw_scheduler_task_def_t slow = { "sched_slow", 2, task_slow, 0 };
    t_start("scheduler_overrun");
    CHECK(efw_scheduler_register(&slow) == EFW_OK);
    sched_spin(45);
    CHECK(efw_scheduler_get("sched_slow", &slot) == EFW_OK);
    CHECK(slot->run_count > 0);
    CHECK(slot->missed_releases > 0);                     /* late releases skipped, no storm */
    CHECK(slot->run_count < 22);                          /* no catch-up: (45/2) would be 22 */
    t_end();
    outs("    slow task: run_count="); outi((int32_t)slot->run_count);
    outs(" missed="); outi((int32_t)slot->missed_releases);
    outs(" overrun="); outi((int32_t)slot->overrun_count); outs("\r\n");
    CHECK(efw_scheduler_unregister("sched_slow") == EFW_OK);   /* clean up before jitter test */
}

static void test_scheduler_jitter(void)
{
    const efw_scheduler_slot_t *slot;
    static efw_scheduler_task_def_t jit = { "jit_task", 1, task_jit, 0 };
    uint32_t avg;
    t_start("scheduler_jitter");
    g_jit_last = g_jit_min = g_jit_max = g_jit_sum = g_jit_n = 0; g_cnt_jit = 0;
    CHECK(efw_scheduler_register(&jit) == EFW_OK);
    sched_spin(1100);
    CHECK(g_jit_n >= 1000);
    avg = g_jit_sum / g_jit_n;
    CHECK(avg >= 990 && avg <= 1010);
    CHECK((g_jit_max - g_jit_min) < 200);                 /* span under 200us */
    CHECK(efw_scheduler_unregister("jit_task") == EFW_OK);
    t_end();
    outs("[PERF] scheduler 1ms release period: avg="); outi((int32_t)avg);
    outs("us min="); outi((int32_t)g_jit_min);
    outs("us max="); outi((int32_t)g_jit_max);
    outs("us span="); outi((int32_t)(g_jit_max - g_jit_min));
    outs("us n="); outi((int32_t)g_jit_n); outs("\r\n");
}

static void test_perf(void)
{
    uint16_t v; efw_pid_input_t in; efw_pid_output_t out;
    uint32_t t0, t1;
    t_start("perf");
    CHECK(efw_sensor_register(&s_perf) == EFW_OK);
    memset(&g_perf_pid, 0, sizeof(g_perf_pid));
    g_perf_pid.kp = 1.0f; g_perf_pid.ki = 0.1f; g_perf_pid.kd = 0.01f;
    g_perf_pid.out_min = -100.0f; g_perf_pid.out_max = 100.0f;
    efw_pid_reset(&g_perf_pid);
    in.setpoint = 1.0f; in.feedback = 0.3f; in.dt = 0.001f; in.feedforward = 0.0f;
    /* sensor lookup + read, 10000 iters */
    t0 = dwt_us();
    for (int i = 0; i < 10000; i++) efw_sensor_read("perf_sensor", &v, 2);
    t1 = dwt_us();
    { uint32_t ns = ((t1 - t0) * 1000u) / 10000u;         /* total us -> ns/op */
      outs("[PERF] sensor_read lookup = "); outi((int32_t)ns); outs(" ns/op (10000 iters)\r\n");
      CHECK(ns < 50000u); }                               /* sanity guard @16MHz */
    CHECK(g_perf_calls == 10000);
    /* pid via registry, 10000 iters */
    t0 = dwt_us();
    for (int i = 0; i < 10000; i++) efw_algo_run("perf_pid", &in, sizeof(in), &out, sizeof(out));
    t1 = dwt_us();
    { uint32_t ns = ((t1 - t0) * 1000u) / 10000u;
      outs("[PERF] algo_run pid = "); outi((int32_t)ns); outs(" ns/op (10000 iters)\r\n");
      CHECK(ns < 50000u); }                               /* sanity guard @16MHz */
    /* diag: record an error, check last_error */
    efw_diag_set(EFW_ERR_NOT_FOUND, "hwtest", "perf", "intentional error for diag test");
    CHECK(efw_diag_last_error()->code == EFW_ERR_NOT_FOUND);
    CHECK(strcmp(efw_diag_last_error()->module, "hwtest") == 0);
    CHECK(efw_diag_error_count() >= 1);
    efw_diag_clear();
    CHECK(efw_diag_last_error()->code == EFW_OK);
    t_end();
}

/* =================== pool test (#2 内存池) =================== */

static void test_pool(void)
{
    static efw_pool_t pool;
    static uint8_t pbuf[4 * 16];
    void *blocks[4];
    t_start("pool");
    /* init + 校验 */
    CHECK(efw_pool_init(&pool, pbuf, 16, 4) == EFW_OK);
    CHECK(efw_pool_init(&pool, 0, 16, 4) == EFW_ERR_INVALID);
    CHECK(efw_pool_init(&pool, pbuf, 1, 4) == EFW_ERR_INVALID);   /* block<2 */
    /* 耗尽 */
    for (int i = 0; i < 4; i++) {
        blocks[i] = efw_pool_alloc(&pool);
        CHECK(blocks[i] != 0);
        memset(blocks[i], (int)(0x10 + i), 16);                   /* 写标记 */
    }
    CHECK(efw_pool_alloc(&pool) == 0);                            /* 空 */
    CHECK(efw_pool_free_count(&pool) == 0);
    /* 释放+复用：LIFO */
    CHECK(efw_pool_free(&pool, blocks[2]) == EFW_OK);
    CHECK(efw_pool_alloc(&pool) == blocks[2]);
    /* 非法释放 */
    CHECK(efw_pool_free(&pool, pbuf + 1) == EFW_ERR_RANGE);       /* 未对齐 */
    CHECK(efw_pool_free(&pool, pbuf + 64) == EFW_ERR_RANGE);      /* 越界 */
    CHECK(efw_pool_free(&pool, 0) == EFW_ERR_INVALID);
    /* 全部归还 */
    for (int i = 0; i < 4; i++) CHECK(efw_pool_free(&pool, blocks[i]) == EFW_OK);
    CHECK(efw_pool_free_count(&pool) == 4);
    /* 随机 alloc/free 影子对账 */
    { uint32_t lcg = 0xC0FFEEu; int live = 0; void *live_p[4]; int bad = 0;
      for (int i = 0; i < 4; i++) live_p[i] = 0;
      for (int iter = 0; iter < 50000; iter++) {
          lcg = lcg * 1103515245u + 12345u;
          uint32_t op = (lcg >> 16) % 3;
          if (op != 0 && live < 4) {            /* alloc */
              void *p = efw_pool_alloc(&pool);
              if (!p) bad++;
              else live_p[live++] = p;
          } else if (live > 0) {                /* free 随机一个 */
              int idx = (int)((lcg >> 8) % (uint32_t)live);
              if (efw_pool_free(&pool, live_p[idx]) != EFW_OK) bad++;
              live_p[idx] = live_p[--live];
          }
          if ((int)efw_pool_free_count(&pool) != 4 - live) { bad++; break; }
      }
      CHECK(bad == 0);
      for (int i = 0; i < live; i++) CHECK(efw_pool_free(&pool, live_p[i]) == EFW_OK); }
    t_end();
}

/* =================== LCD panel test + bench =================== */

static void test_lcd(void)
{
    uint32_t t0, t1;
    u16 id;
    t_start("lcd_panel");
    LCD_Init();
    id = LCD_ReadID();
    outs("    LCD controller ID=0x"); outx(id); outs("\r\n");
    CHECK(id != 0x0000);
    LCD_SetTextColor(White);
    LCD_SetBackColor(Black);
    t0 = dwt_us();
    LCD_Clear(Black);
    t1 = dwt_us();
    outs("[PERF] LCD_Clear = "); outi((int32_t)((t1 - t0) / 1000));
    outs(" ms (76800 px)\r\n");
    t0 = dwt_us();
    LCD_FillArea(50, 50, 100, 200, Red);
    t1 = dwt_us();
    outs("[PERF] LCD_FillArea 100x200 = "); outi((int32_t)(t1 - t0)); outs(" us\r\n");
    t0 = dwt_us();
    LCD_DisplayStringLine(Line0, (u8 *)"EFW LCD OK");
    t1 = dwt_us();
    outs("[PERF] LCD text line = "); outi((int32_t)(t1 - t0)); outs(" us\r\n");
    CHECK(LCD_ReadReg(0) == id);        /* bus alive after graphics */
    t_end();
}

/* =================== demo phase (real hardware) =================== */

static uint8_t g_chase = 0x01; static uint32_t g_hb_count;
static efw_status_t demo_led_task(void *c)
{ (void)c; led_write(g_chase); g_chase = (uint8_t)((g_chase << 1) | (g_chase >> 7)); return EFW_OK; }
static efw_status_t demo_hb_task(void *c)
{ (void)c; g_hb_count++; outs("HB t="); outi((int32_t)g_ms_tick); outs("ms btn=0b"); outi(buttons_read());
  outs(" led=0x"); outx(g_chase); outs("\r\n"); return EFW_OK; }

static void demo_phase(void)
{
    static efw_scheduler_task_def_t led = { "demo_led", 100,  demo_led_task, 0 };
    static efw_scheduler_task_def_t hb  = { "demo_hb",  500,  demo_hb_task,  0 };
    OUTLN("==== DEMO: LED chase + UART heartbeat + LCD dashboard ====");
    efw_scheduler_register(&led);
    efw_scheduler_register(&hb);
    ui_init();
    for (;;) {
        sched_spin(1);
        ui_task_1ms();
        efw_event_queue_process();                        /* keep queue drained */
    }
}

/* =================== quick boot self-test (arcade path) =================== */

static void quick_selftest(void)
{
    OUTLN("==== QUICK SELFTEST ====");
    test_core_init();
    test_hal_registry();
    test_comm_registry();
    test_sensor_registry();
    test_algo_pid();
    test_state_machine();
    test_event_topic();
    test_lcd();
    outs("==== QUICK SELFTEST: "); outi(t_pass); outs("/"); outi(t_total);
    outs(t_pass == t_total ? " PASS ====\r\n" : " FAIL ====\r\n");
}

/* =================== main =================== */

int main(void)
{
    bsp_systick_init();
    bsp_dwt_init();
    bsp_gpio_init();
    bsp_uart_init();
    buzzer_on();                                          /* PC13 probe (candidate backlight) */
    bsp_stack_paint();                                    /* for high-water scan */

#define HW_REG32(a) (*(volatile uint32_t *)(a))
#define HW_MAILBOX  0x20007800u      /* SRAM 邮箱（bss 之外，复位不清除） */
#define HW_ENG_MAGIC 0xB0A10D01u
#define HW_QA_MAGIC  0xB0A10D02u

#if defined(HOST_BUILD)
    int engineering = 1;                                  /* host: full regression path */
    int qa_attract = 0;                                   /* host: no QA attract */
#else
    /* 远程模式邮箱：openocd 在复位后 halt 时写入（SRAM 不被复位清除） */
    uint32_t boot_req = HW_REG32(HW_MAILBOX);
    HW_REG32(HW_MAILBOX) = 0;                             /* consume */
    int engineering = ((buttons_read() & 0x8) != 0) ||
                      (boot_req == HW_ENG_MAGIC);
    int qa_attract = (boot_req == HW_QA_MAGIC);
#endif

    if (engineering) {
        /* ---------------- engineering mode (B4 held at reset) @16MHz ---------------- */
        OUTLN("");
        OUTLN("==================================================");
        OUTLN("  EFW framework on-hardware test (ENGINEERING)");
        OUTLN("  board=CT117E-M4  mcu=STM32G431RBT6  sysclk=16MHz");
        outs("  IDCODE=0x"); outx(dbg_idcode());
        outs("  build=" __DATE__ " " __TIME__ "\r\n");
        OUTLN("==================================================");

        test_core_init();
        test_ds_ringbuf();
        test_ds_queue();
        test_ds_stack();
        test_pool();
        test_hal_registry();
        test_hal_io_route();
        test_comm_registry();
        test_sensor_registry();
        test_actuator_led();
        test_motor_layer();
        test_algo_pid();
        test_algo_pid_antawindup();
        test_algo_filters();
        test_line_tracking();
        test_module_lifecycle();
        test_state_machine();
        test_event_topic();
        test_event_queue();
        test_scheduler_basic();
        test_scheduler_overrun();
        test_scheduler_jitter();
        test_perf();
        test_lcd();
        stress_run_all();
        boundary_run_all();

        outs("==================================================\r\n");
        outs("==== SUMMARY: total="); outi(t_total);
        outs(" pass="); outi(t_pass);
        outs(" fail="); outi(t_total - t_pass);
        outs(" ====\r\n");
        outs("==== RESULT: "); outs(t_pass == t_total ? "ALL PASS" : "HAS FAILURES");
        outs(" ====\r\n");
        outs("[REG] hal="); outi((int32_t)efw_hal_count());
        outs(" comm="); outi((int32_t)efw_comm_count_by_type(EFW_COMM_UART));
        outs(" sensor="); outi((int32_t)efw_sensor_count());
        outs(" actuator="); outi((int32_t)efw_actuator_count());
        outs(" algo="); outi((int32_t)efw_algo_count());
        outs(" module="); outi((int32_t)efw_module_count());
        outs(" sm="); outi((int32_t)efw_sm_count());
        outs("\r\n");

        demo_phase();
        return 0;
    }

    /* ---------------- arcade mode (default boot) @80MHz ---------------- */
    bsp_clock_boost();
    OUTLN("");
    OUTLN("==================================================");
    OUTLN("  EFW ARCADE boot  (STM32G431RBT6 @80MHz)");
    outs("  IDCODE=0x"); outx(dbg_idcode());
    outs("  sysclk="); outi((int32_t)bsp_sysclk_mhz());
    outs("MHz  build=" __DATE__ " " __TIME__ "\r\n");
    OUTLN("==================================================");
    quick_selftest();
    arcade_run(qa_attract);
    return 0;
}
