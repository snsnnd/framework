/**
 * @file    efw_sim_test.c
 * @brief   EFW 框架完整仿真测试
 *
 * 测试分层:
 *   L1 — 单元测试: 每个 API 的输入输出正确性
 *   L2 — 边界测试: 溢出、空、满、NULL 等边界条件
 *   L3 — 集成测试: 多子系统协作的端到端场景
 *   L4 — 压力测试: 大量注册/注销/高频调用
 */

#include <stdio.h>
#include <string.h>
#include <math.h>
#include "efw/efw.h"
#include "efw/debug/efw_debug.h"

static int g_run = 0, g_pass = 0, g_fail = 0;

#define TEST(name) do { g_run++; printf("  %-60s ", name); } while(0)
#define PASS() do { g_pass++; printf("PASS\n"); } while(0)
#define FAIL(m) do { g_fail++; printf("FAIL: %s\n", m); } while(0)
#define CHECK(c, m) do { if (!(c)) { FAIL(m); return; } } while(0)
#define ASSERT_OK(s) do { efw_status_t _s=(s); if(_s!=EFW_OK){printf("FAIL: got %d at line %d\n",_s,__LINE__);g_fail++;g_run++;return;} } while(0)

/* ========================================================================
 *  模拟硬件
 * ======================================================================== */

static float g_adc_val = 0.0f;
static float g_motor_val = 0.0f;
static uint8_t g_gpio = 0;

static efw_status_t mock_adc_read(void *ctx, void *buf, uint16_t len, uint16_t *actual) {
    (void)ctx;
    if (!buf || len < sizeof(float)) return EFW_ERR_INVALID;
    *(float *)buf = g_adc_val;
    if (actual) *actual = sizeof(float);
    return EFW_OK;
}

static efw_status_t mock_gpio_write(void *ctx, const void *buf, uint16_t len, uint16_t *actual) {
    (void)ctx;
    if (!buf || len < sizeof(uint8_t)) return EFW_ERR_INVALID;
    g_gpio = *(const uint8_t *)buf;
    if (actual) *actual = sizeof(uint8_t);
    return EFW_OK;
}

static efw_status_t mock_sensor_read(void *ctx, void *out, uint16_t out_size) {
    (void)ctx;
    if (!out || out_size < sizeof(float)) return EFW_ERR_INVALID;
    *(float *)out = g_adc_val;
    return EFW_OK;
}

static efw_status_t mock_actuator_write(void *ctx, const void *cmd, uint16_t cmd_size) {
    (void)ctx; (void)cmd_size;
    if (!cmd) return EFW_ERR_INVALID;
    g_motor_val = ((const efw_actuator_cmd_t *)cmd)->value;
    return EFW_OK;
}

static efw_status_t mock_algo_double(void *ctx, const void *in, uint16_t in_size, void *out, uint16_t out_size) {
    (void)ctx;
    if (!in || !out) return EFW_ERR_INVALID;
    if (in_size < sizeof(float) || out_size < sizeof(float)) return EFW_ERR_RANGE;
    *(float *)out = *(const float *)in * 2.0f;
    return EFW_OK;
}

/* ========================================================================
 *  L1: 单元测试 — HAL 注册表
 * ======================================================================== */

static uint32_t g_enum_count;
static void count_enumerate(const efw_hal_ops_t *ops, void *user) { (void)ops; (void)user; g_enum_count++; }

static void test_hal_register_get(void) {
    TEST("L1/HAL: register → get → count");
    efw_hal_registry_init();
    efw_hal_ops_t h1 = { .name = "adc1", .type = EFW_HAL_ADC };
    efw_hal_ops_t h2 = { .name = "gpio1", .type = EFW_HAL_GPIO };
    ASSERT_OK(efw_hal_register(&h1));
    ASSERT_OK(efw_hal_register(&h2));
    CHECK(efw_hal_count() == 2, "count should be 2");
    const efw_hal_ops_t *found;
    ASSERT_OK(efw_hal_get("adc1", &found));
    CHECK(found == &h1, "pointer mismatch");
    CHECK(found->type == EFW_HAL_ADC, "type mismatch");
    PASS();
}

static void test_hal_read_write(void) {
    TEST("L1/HAL: read/write convenience");
    efw_hal_registry_init();
    efw_hal_ops_t adc = { .name = "adc", .type = EFW_HAL_ADC, .read = mock_adc_read };
    efw_hal_ops_t gpio = { .name = "gpio", .type = EFW_HAL_GPIO, .write = mock_gpio_write };
    ASSERT_OK(efw_hal_register(&adc));
    ASSERT_OK(efw_hal_register(&gpio));
    g_adc_val = 3.3f;
    float val;
    ASSERT_OK(efw_hal_read("adc", &val, sizeof(val), 0));
    CHECK(val == 3.3f, "read value mismatch");
    uint8_t led = 1;
    ASSERT_OK(efw_hal_write("gpio", &led, sizeof(led), 0));
    CHECK(g_gpio == 1, "write value mismatch");
    PASS();
}

static void test_hal_enumerate(void) {
    TEST("L1/HAL: enumerate callback");
    efw_hal_registry_init();
    efw_hal_ops_t h1 = { .name = "a", .type = EFW_HAL_ADC };
    efw_hal_ops_t h2 = { .name = "b", .type = EFW_HAL_GPIO };
    efw_hal_ops_t h3 = { .name = "c", .type = EFW_HAL_SPI };
    efw_hal_register(&h1); efw_hal_register(&h2); efw_hal_register(&h3);
    g_enum_count = 0;
    efw_hal_enumerate(count_enumerate, 0);
    CHECK(g_enum_count == 3, "should enumerate 3");
    PASS();
}

/* ========================================================================
 *  L1: 单元测试 — Sensor 注册表
 * ======================================================================== */

static void test_sensor_lifecycle(void) {
    TEST("L1/Sensor: register → read → unregister");
    efw_sensor_registry_init();
    efw_sensor_ops_t s = { .name = "temp", .type = EFW_SENSOR_CUSTOM, .read = mock_sensor_read };
    ASSERT_OK(efw_sensor_register(&s));
    g_adc_val = 25.5f;
    float val;
    ASSERT_OK(efw_sensor_read("temp", &val, sizeof(val)));
    CHECK(val == 25.5f, "read mismatch");
    ASSERT_OK(efw_sensor_unregister("temp"));
    CHECK(efw_sensor_count() == 0, "count should be 0");
    CHECK(efw_sensor_get("temp", 0) == EFW_ERR_INVALID, "should be gone");
    PASS();
}

/* ========================================================================
 *  L1: 单元测试 — Actuator 注册表
 * ======================================================================== */

static void test_actuator_lifecycle(void) {
    TEST("L1/Actuator: register → write → unregister");
    efw_actuator_registry_init();
    efw_actuator_ops_t a = { .name = "motor", .type = EFW_ACTUATOR_MOTOR, .write = mock_actuator_write };
    ASSERT_OK(efw_actuator_register(&a));
    g_motor_val = 0.0f;
    efw_actuator_cmd_t cmd = { .value = 0.75f };
    ASSERT_OK(efw_actuator_write("motor", &cmd, sizeof(cmd)));
    CHECK(g_motor_val == 0.75f, "write mismatch");
    ASSERT_OK(efw_actuator_unregister("motor"));
    CHECK(efw_actuator_count() == 0, "count should be 0");
    PASS();
}

/* ========================================================================
 *  L1: 单元测试 — Algorithm 注册表
 * ======================================================================== */

static void test_algo_lifecycle(void) {
    TEST("L1/Algorithm: register → run → unregister");
    efw_algo_registry_init();
    float ctx = 0;
    efw_algo_ops_t algo = { .name = "dbl", .type = EFW_ALGO_CUSTOM, .ctx = &ctx, .run = mock_algo_double };
    ASSERT_OK(efw_algo_register(&algo));
    float in = 5.0f, out;
    ASSERT_OK(efw_algo_run("dbl", &in, sizeof(in), &out, sizeof(out)));
    CHECK(out == 10.0f, "algo output mismatch");
    ASSERT_OK(efw_algo_unregister("dbl"));
    CHECK(efw_algo_count() == 0, "count should be 0");
    PASS();
}

/* ========================================================================
 *  L1: 单元测试 — Module 注册表
 * ======================================================================== */

static uint32_t g_mod_call_order[8];
static uint32_t g_mod_call_idx;

static efw_status_t mod_record_0(void *ctx) { (void)ctx; g_mod_call_order[g_mod_call_idx++] = 0; return EFW_OK; }
static efw_status_t mod_record_1(void *ctx) { (void)ctx; g_mod_call_order[g_mod_call_idx++] = 1; return EFW_OK; }
static efw_status_t mod_record_2(void *ctx) { (void)ctx; g_mod_call_order[g_mod_call_idx++] = 2; return EFW_OK; }
static efw_status_t mod_record_3(void *ctx) { (void)ctx; g_mod_call_order[g_mod_call_idx++] = 3; return EFW_OK; }

static void test_module_priority_ordering(void) {
    TEST("L1/Module: priority ordering on poll_all");
    efw_module_registry_init();
    g_mod_call_idx = 0;
    efw_module_ops_t m3 = { .name = "m3", .type = EFW_MODULE_APP, .priority = 30, .poll = mod_record_3 };
    efw_module_ops_t m1 = { .name = "m1", .type = EFW_MODULE_APP, .priority = 10, .poll = mod_record_1 };
    efw_module_ops_t m0 = { .name = "m0", .type = EFW_MODULE_APP, .priority = 0,  .poll = mod_record_0 };
    efw_module_ops_t m2 = { .name = "m2", .type = EFW_MODULE_APP, .priority = 20, .poll = mod_record_2 };
    efw_module_register(&m3); efw_module_register(&m1); efw_module_register(&m0); efw_module_register(&m2);
    efw_module_poll_all();
    CHECK(g_mod_call_order[0] == 0, "first should be priority=0");
    CHECK(g_mod_call_order[1] == 1, "second should be priority=10");
    CHECK(g_mod_call_order[2] == 2, "third should be priority=20");
    CHECK(g_mod_call_order[3] == 3, "fourth should be priority=30");
    PASS();
}

static void test_module_priority_after_unregister(void) {
    TEST("L1/Module: priority maintained after unregister");
    efw_module_registry_init();
    g_mod_call_idx = 0;
    efw_module_ops_t m0 = { .name = "m0", .type = EFW_MODULE_APP, .priority = 0,  .poll = mod_record_0 };
    efw_module_ops_t m1 = { .name = "m1", .type = EFW_MODULE_APP, .priority = 10, .poll = mod_record_1 };
    efw_module_ops_t m2 = { .name = "m2", .type = EFW_MODULE_APP, .priority = 20, .poll = mod_record_2 };
    efw_module_register(&m0); efw_module_register(&m1); efw_module_register(&m2);
    efw_module_unregister("m1");  /* remove middle element */
    efw_module_poll_all();
    CHECK(g_mod_call_order[0] == 0, "first should be m0");
    CHECK(g_mod_call_order[1] == 2, "second should be m2");
    PASS();
}

static uint32_t g_mod_lifecycle_calls;
static efw_status_t lc_init(void *ctx) { (void)ctx; g_mod_lifecycle_calls |= 1; return EFW_OK; }
static efw_status_t lc_start(void *ctx) { (void)ctx; g_mod_lifecycle_calls |= 2; return EFW_OK; }
static efw_status_t lc_poll(void *ctx) { (void)ctx; g_mod_lifecycle_calls |= 4; return EFW_OK; }
static efw_status_t lc_stop(void *ctx) { (void)ctx; g_mod_lifecycle_calls |= 8; return EFW_OK; }

static void test_module_lifecycle(void) {
    TEST("L1/Module: init → start → poll → stop lifecycle");
    efw_module_registry_init();
    g_mod_lifecycle_calls = 0;
    efw_module_ops_t m = {
        .name = "lc", .type = EFW_MODULE_APP,
        .init = lc_init, .start = lc_start, .poll = lc_poll, .stop = lc_stop
    };
    efw_module_register(&m);
    efw_module_init_all(); CHECK(g_mod_lifecycle_calls & 1, "init not called");
    efw_module_start_all(); CHECK(g_mod_lifecycle_calls & 2, "start not called");
    efw_module_poll_all(); CHECK(g_mod_lifecycle_calls & 4, "poll not called");
    efw_module_stop("lc"); CHECK(g_mod_lifecycle_calls & 8, "stop not called");
    PASS();
}

static efw_status_t bad_poll(void *ctx) { (void)ctx; return EFW_ERR_IO; }

static void test_module_poll_all_tolerance(void) {
    TEST("L1/Module: poll_all continues on failure");
    efw_module_registry_init();
    g_mod_call_idx = 0;
    efw_module_ops_t good = { .name = "good", .type = EFW_MODULE_APP, .priority = 0, .poll = mod_record_0 };
    efw_module_ops_t bad = { .name = "bad", .type = EFW_MODULE_APP, .priority = 10, .poll = bad_poll };
    efw_module_ops_t good2 = { .name = "good2", .type = EFW_MODULE_APP, .priority = 20, .poll = mod_record_1 };
    efw_module_register(&good); efw_module_register(&bad); efw_module_register(&good2);
    efw_status_t s = efw_module_poll_all();
    CHECK(s == EFW_ERR_IO, "should return first error");
    CHECK(g_mod_call_idx == 2, "both good modules should be polled");
    PASS();
}

/* ========================================================================
 *  L1: 单元测试 — PID 控制器
 * ======================================================================== */

static void test_pid_positive_error(void) {
    TEST("L1/PID: positive error → positive output");
    efw_pid_t pid; memset(&pid, 0, sizeof(pid));
    pid.kp = 1.0f; pid.out_min = -10.0f; pid.out_max = 10.0f;
    efw_pid_input_t in = { .setpoint = 1.0f, .feedback = 0.0f, .dt = 0.01f };
    efw_pid_output_t out;
    ASSERT_OK(efw_pid_run(&pid, &in, sizeof(in), &out, sizeof(out)));
    CHECK(out.output > 0.0f, "output should be positive");
    CHECK(fabsf(out.error - 1.0f) < 0.001f, "error should be 1.0");
    PASS();
}

static void test_pid_negative_error(void) {
    TEST("L1/PID: negative error → negative output");
    efw_pid_t pid; memset(&pid, 0, sizeof(pid));
    pid.kp = 1.0f; pid.out_min = -10.0f; pid.out_max = 10.0f;
    efw_pid_input_t in = { .setpoint = 0.0f, .feedback = 1.0f, .dt = 0.01f };
    efw_pid_output_t out;
    ASSERT_OK(efw_pid_run(&pid, &in, sizeof(in), &out, sizeof(out)));
    CHECK(out.output < 0.0f, "output should be negative");
    PASS();
}

static void test_pid_output_clamp(void) {
    TEST("L1/PID: output clamping");
    efw_pid_t pid; memset(&pid, 0, sizeof(pid));
    pid.kp = 100.0f; pid.out_min = 0.0f; pid.out_max = 0.5f;
    efw_pid_input_t in = { .setpoint = 10.0f, .feedback = 0.0f, .dt = 0.01f };
    efw_pid_output_t out;
    ASSERT_OK(efw_pid_run(&pid, &in, sizeof(in), &out, sizeof(out)));
    CHECK(out.output <= 0.5f, "should be clamped to max");
    CHECK(out.output >= 0.0f, "should be clamped to min");
    PASS();
}

static void test_pid_integral(void) {
    TEST("L1/PID: integral accumulation");
    efw_pid_t pid; memset(&pid, 0, sizeof(pid));
    pid.ki = 1.0f; pid.out_min = -100.0f; pid.out_max = 100.0f;
    for (int i = 0; i < 100; ++i) {
        efw_pid_input_t in = { .setpoint = 1.0f, .feedback = 0.0f, .dt = 0.01f };
        efw_pid_output_t out;
        efw_pid_run(&pid, &in, sizeof(in), &out, sizeof(out));
    }
    CHECK(pid.integral > 0.0f, "integral should accumulate");
    CHECK(pid.integral < 2.0f, "integral should be reasonable");
    PASS();
}

static void test_pid_reset(void) {
    TEST("L1/PID: reset clears state");
    efw_pid_t pid; memset(&pid, 0, sizeof(pid));
    pid.ki = 1.0f;
    efw_pid_input_t in = { .setpoint = 1.0f, .feedback = 0.0f, .dt = 0.01f };
    efw_pid_output_t out;
    efw_pid_run(&pid, &in, sizeof(in), &out, sizeof(out));
    CHECK(pid.integral > 0.0f, "integral should be non-zero");
    efw_pid_reset(&pid);
    CHECK(pid.integral == 0.0f, "integral should be zero after reset");
    CHECK(pid.prev_error == 0.0f, "prev_error should be zero after reset");
    PASS();
}

/* ========================================================================
 *  L1: 单元测试 — 状态机引擎
 * ======================================================================== */

static uint32_t g_sm_enter_count, g_sm_tick_count, g_sm_exit_count;

static efw_status_t sm_on_enter(void *ctx) { (void)ctx; g_sm_enter_count++; return EFW_OK; }
static efw_status_t sm_on_tick(void *ctx) { (void)ctx; g_sm_tick_count++; return EFW_OK; }
static efw_status_t sm_on_exit(void *ctx) { (void)ctx; g_sm_exit_count++; return EFW_OK; }

static int g_sm_cond = 0;
static int sm_cond(void) { return g_sm_cond; }
static int g_veh_cond;
static int veh_cond(void) { return g_veh_cond; }

static void test_sm_basic_tick(void) {
    TEST("L1/SM: init → tick → current_state");
    efw_state_def_t s = { .name = "idle", .on_enter = sm_on_enter, .on_tick = sm_on_tick };
    efw_sm_context_t sm;
    g_sm_enter_count = g_sm_tick_count = 0;
    ASSERT_OK(efw_sm_init(&sm, "test", &s, 0, 0));
    CHECK(g_sm_enter_count == 1, "on_enter should fire once");
    CHECK(strcmp(efw_sm_current_state(&sm), "idle") == 0, "should be idle");
    efw_sm_set_elapsed(&sm, 100);
    efw_sm_tick(&sm);
    CHECK(g_sm_tick_count == 1, "on_tick should fire once");
    PASS();
}

static void test_sm_null_tick_is_valid(void) {
    TEST("L1/SM: null on_tick is valid");
    efw_state_def_t s = { .name = "idle" };
    efw_sm_context_t sm;
    ASSERT_OK(efw_sm_init(&sm, "test", &s, 0, 0));
    efw_sm_set_elapsed(&sm, 1);
    ASSERT_OK(efw_sm_tick(&sm));
    CHECK(strcmp(efw_sm_current_state(&sm), "idle") == 0, "should remain in idle");
    PASS();
}

static void test_sm_condition_transition(void) {
    TEST("L1/SM: condition-based transition");
    efw_state_def_t s1 = { .name = "a", .on_tick = sm_on_tick };
    efw_state_def_t s2 = { .name = "b", .on_tick = sm_on_tick, .on_exit = sm_on_exit };
    efw_sm_transition_t trans[] = {
        { .from = &s1, .to = &s2, .condition = sm_cond, .priority = 10 },
    };
    efw_sm_context_t sm;
    g_sm_cond = 0;
    ASSERT_OK(efw_sm_init(&sm, "test", &s1, trans, 1));
    efw_sm_set_elapsed(&sm, 100);
    efw_sm_tick(&sm);
    CHECK(strcmp(efw_sm_current_state(&sm), "a") == 0, "should stay in a");
    g_sm_cond = 1;
    efw_sm_tick(&sm);
    CHECK(strcmp(efw_sm_current_state(&sm), "b") == 0, "should transition to b");
    PASS();
}

static void test_sm_timeout_transition(void) {
    TEST("L1/SM: timeout-based transition");
    efw_state_def_t s1 = { .name = "wait", .on_tick = sm_on_tick };
    efw_state_def_t s2 = { .name = "done", .on_tick = sm_on_tick };
    efw_sm_transition_t trans[] = {
        { .from = &s1, .to = &s2, .timeout_ms = 500, .priority = 5 },
    };
    efw_sm_context_t sm;
    ASSERT_OK(efw_sm_init(&sm, "test", &s1, trans, 1));
    efw_sm_set_elapsed(&sm, 400);
    efw_sm_tick(&sm);
    CHECK(strcmp(efw_sm_current_state(&sm), "wait") == 0, "should not timeout yet");
    efw_sm_set_elapsed(&sm, 500);
    efw_sm_tick(&sm);
    CHECK(strcmp(efw_sm_current_state(&sm), "done") == 0, "should timeout");
    PASS();
}

static void test_sm_priority_ordering(void) {
    TEST("L1/SM: priority ordering of transitions");
    efw_state_def_t s1 = { .name = "s1", .on_tick = sm_on_tick };
    efw_state_def_t s2 = { .name = "s2", .on_tick = sm_on_tick };
    efw_state_def_t s3 = { .name = "s3", .on_tick = sm_on_tick };
    efw_sm_transition_t trans[] = {
        { .from = &s1, .to = &s2, .condition = sm_cond, .priority = 1 },
        { .from = &s1, .to = &s3, .condition = sm_cond, .priority = 10 },
    };
    efw_sm_context_t sm;
    g_sm_cond = 1;
    ASSERT_OK(efw_sm_init(&sm, "test", &s1, trans, 2));
    efw_sm_set_elapsed(&sm, 100);
    efw_sm_tick(&sm);
    CHECK(strcmp(efw_sm_current_state(&sm), "s3") == 0, "should go to higher priority");
    PASS();
}

static efw_sm_context_t *g_sm_snapshot_ptr;
static efw_status_t tick_and_transition(void *ctx) {
    (void)ctx;
    efw_state_def_t target = { .name = "b", .on_tick = sm_on_tick };
    efw_sm_transition_to(g_sm_snapshot_ptr, &target);
    return EFW_OK;
}

static void test_sm_snapshot_protection(void) {
    TEST("L1/SM: snapshot prevents double transition");
    efw_state_def_t s1 = { .name = "a", .on_tick = tick_and_transition };
    efw_state_def_t s2 = { .name = "b", .on_tick = sm_on_tick };
    efw_state_def_t s3 = { .name = "c", .on_tick = sm_on_tick };
    efw_sm_transition_t trans[] = {
        { .from = &s1, .to = &s3, .condition = sm_cond, .priority = 10 },
    };
    efw_sm_context_t sm;
    g_sm_snapshot_ptr = &sm;
    g_sm_cond = 1;
    ASSERT_OK(efw_sm_init(&sm, "test", &s1, trans, 1));
    efw_sm_set_elapsed(&sm, 100);
    efw_sm_tick(&sm);
    CHECK(strcmp(efw_sm_current_state(&sm), "b") == 0, "on_tick transition should win");
    PASS();
}

static void test_sm_dynamic_transitions(void) {
    TEST("L1/SM: set_transitions at runtime");
    efw_state_def_t s1 = { .name = "s1", .on_tick = sm_on_tick };
    efw_state_def_t s2 = { .name = "s2", .on_tick = sm_on_tick };
    efw_sm_context_t sm;
    ASSERT_OK(efw_sm_init(&sm, "test", &s1, 0, 0));
    efw_sm_set_elapsed(&sm, 100);
    efw_sm_tick(&sm);
    CHECK(strcmp(efw_sm_current_state(&sm), "s1") == 0, "no transitions, stay");
    efw_sm_transition_t trans[] = {
        { .from = &s1, .to = &s2, .condition = sm_cond, .priority = 10 },
    };
    efw_sm_set_transitions(&sm, trans, 1);
    g_sm_cond = 1;
    efw_sm_tick(&sm);
    CHECK(strcmp(efw_sm_current_state(&sm), "s2") == 0, "should use new transitions");
    PASS();
}

static void test_sm_registry(void) {
    TEST("L1/SM: context register/get/unregister");
    efw_sm_registry_init();
    efw_state_def_t s = { .name = "s", .on_tick = sm_on_tick };
    efw_sm_context_t sm;
    ASSERT_OK(efw_sm_init(&sm, "sm1", &s, 0, 0));
    ASSERT_OK(efw_sm_register(&sm));
    CHECK(efw_sm_count() == 1, "count should be 1");
    efw_sm_context_t *found;
    ASSERT_OK(efw_sm_get("sm1", &found));
    CHECK(found == &sm, "pointer mismatch");
    ASSERT_OK(efw_sm_unregister("sm1"));
    CHECK(efw_sm_count() == 0, "count should be 0");
    PASS();
}

/* ========================================================================
 *  L1: 单元测试 — 调度器
 * ======================================================================== */

static uint32_t g_task_1ms_n, g_task_5ms_n, g_task_10ms_n;
static efw_status_t t_1ms(void *ctx) { (void)ctx; g_task_1ms_n++; return EFW_OK; }
static efw_status_t t_5ms(void *ctx) { (void)ctx; g_task_5ms_n++; return EFW_OK; }
static efw_status_t t_10ms(void *ctx) { (void)ctx; g_task_10ms_n++; return EFW_OK; }

static void test_scheduler_multi_period(void) {
    TEST("L1/Scheduler: 1ms + 5ms + 10ms over 100ms");
    efw_scheduler_init();
    g_task_1ms_n = g_task_5ms_n = g_task_10ms_n = 0;
    efw_scheduler_task_def_t d1 = { .name = "1ms", .period_ms = 1, .fn = t_1ms };
    efw_scheduler_task_def_t d5 = { .name = "5ms", .period_ms = 5, .fn = t_5ms };
    efw_scheduler_task_def_t d10 = { .name = "10ms", .period_ms = 10, .fn = t_10ms };
    efw_scheduler_register(&d1); efw_scheduler_register(&d5); efw_scheduler_register(&d10);
    for (uint32_t ms = 1; ms <= 100; ++ms) efw_scheduler_tick(ms);
    CHECK(g_task_1ms_n == 100, "1ms: expected 100");
    CHECK(g_task_5ms_n == 20, "5ms: expected 20");
    CHECK(g_task_10ms_n == 10, "10ms: expected 10");
    PASS();
}

static void test_scheduler_pause_resume(void) {
    TEST("L1/Scheduler: pause → tick → resume → tick");
    efw_scheduler_init();
    g_task_1ms_n = 0;
    efw_scheduler_task_def_t d = { .name = "t", .period_ms = 1, .fn = t_1ms };
    efw_scheduler_register(&d);
    for (uint32_t ms = 1; ms <= 10; ++ms) efw_scheduler_tick(ms);
    CHECK(g_task_1ms_n == 10, "should be 10");
    efw_scheduler_pause("t");
    for (uint32_t ms = 11; ms <= 20; ++ms) efw_scheduler_tick(ms);
    CHECK(g_task_1ms_n == 10, "should still be 10");
    efw_scheduler_resume("t");
    for (uint32_t ms = 21; ms <= 30; ++ms) efw_scheduler_tick(ms);
    CHECK(g_task_1ms_n == 20, "should be 20");
    PASS();
}

static void test_scheduler_unregister(void) {
    TEST("L1/Scheduler: unregister task");
    efw_scheduler_init();
    g_task_1ms_n = 0;
    efw_scheduler_task_def_t d = { .name = "t", .period_ms = 1, .fn = t_1ms };
    efw_scheduler_register(&d);
    efw_scheduler_unregister("t");
    for (uint32_t ms = 1; ms <= 10; ++ms) efw_scheduler_tick(ms);
    CHECK(g_task_1ms_n == 0, "should not fire after unregister");
    CHECK(efw_scheduler_task_count() == 0, "count should be 0");
    PASS();
}

/* ========================================================================
 *  L1: 单元测试 — 事件系统
 * ======================================================================== */

static uint32_t g_evt_count;
static uint16_t g_last_topic;
static uint16_t g_last_size;
static uint32_t g_repost_count;

static void evt_cb(uint16_t id, const void *data, uint16_t size, void *user) {
    (void)data; (void)user;
    g_evt_count++; g_last_topic = id; g_last_size = size;
}

static void repost_cb(uint16_t id, const void *data, uint16_t size, void *user) {
    (void)data; (void)size; (void)user;
    g_evt_count++;
    if (g_repost_count < 3) {
        float v = 0;
        efw_event_queue_post(id, &v, sizeof(v));
        g_repost_count++;
    }
}

static void test_event_subscribe_publish(void) {
    TEST("L1/Event: subscribe → publish → unsubscribe");
    efw_topic_clear();
    g_evt_count = 0;
    ASSERT_OK(efw_topic_subscribe(42, evt_cb, 0));
    float val = 1.0f;
    ASSERT_OK(efw_topic_publish(42, &val, sizeof(val)));
    CHECK(g_evt_count == 1, "callback should fire");
    CHECK(g_last_topic == 42, "topic mismatch");
    ASSERT_OK(efw_topic_unsubscribe(42, evt_cb));
    ASSERT_OK(efw_topic_publish(42, &val, sizeof(val)));
    CHECK(g_evt_count == 1, "should not fire after unsubscribe");
    PASS();
}

static void test_event_queue_basic(void) {
    TEST("L1/Event: queue post → process");
    efw_topic_clear();
    efw_event_queue_init();
    g_evt_count = 0;
    ASSERT_OK(efw_topic_subscribe(1, evt_cb, 0));
    float v1 = 1.0f, v2 = 2.0f;
    ASSERT_OK(efw_event_queue_post(1, &v1, sizeof(v1)));
    ASSERT_OK(efw_event_queue_post(1, &v2, sizeof(v2)));
    CHECK(efw_event_queue_count() == 2, "count should be 2");
    ASSERT_OK(efw_event_queue_process());
    CHECK(g_evt_count == 2, "should fire twice");
    CHECK(efw_event_queue_count() == 0, "queue should be empty");
    PASS();
}

static void test_event_queue_null_data_size_zero(void) {
    TEST("L1/Event: post NULL data with size=0 is valid");
    efw_event_queue_init();
    ASSERT_OK(efw_event_queue_post(1, 0, 0));
    CHECK(efw_event_queue_count() == 1, "should accept signal event");
    PASS();
}

static void test_event_queue_null_data_size_nonzero(void) {
    TEST("L1/Event: post NULL data with size>0 is rejected");
    efw_event_queue_init();
    CHECK(efw_event_queue_post(1, 0, 5) == EFW_ERR_INVALID, "should reject");
    CHECK(efw_event_queue_count() == 0, "queue should be empty");
    PASS();
}

static void test_event_queue_overflow(void) {
    TEST("L1/Event: queue overflow protection");
    efw_event_queue_init();
    float v = 1.0f;
    for (int i = 0; i < EFW_EVENT_QUEUE_CAPACITY; ++i) {
        ASSERT_OK(efw_event_queue_post((uint16_t)i, &v, sizeof(v)));
    }
    CHECK(efw_event_queue_post(99, &v, sizeof(v)) == EFW_ERR_FULL, "should overflow");
    PASS();
}

static void test_event_queue_large_data(void) {
    TEST("L1/Event: reject data > EFW_EVENT_ITEM_MAX_SIZE");
    efw_event_queue_init();
    uint8_t big[64]; memset(big, 0xAA, sizeof(big));
    CHECK(efw_event_queue_post(1, big, sizeof(big)) == EFW_ERR_RANGE, "should reject");
    PASS();
}

static void test_event_queue_process_limited(void) {
    TEST("L1/Event: process only snapshot count");
    efw_topic_clear();
    efw_event_queue_init();
    g_evt_count = 0;
    g_repost_count = 0;
    ASSERT_OK(efw_topic_subscribe(1, repost_cb, 0));
    float v = 1.0f;
    ASSERT_OK(efw_event_queue_post(1, &v, sizeof(v)));
    efw_event_queue_process();
    CHECK(g_evt_count == 1, "should only process 1 event");
    CHECK(efw_event_queue_count() == 1, "reposted event should remain");
    PASS();
}

/* ========================================================================
 *  L1: 单元测试 — 诊断系统
 * ======================================================================== */

static void test_diag_basic(void) {
    TEST("L1/Diag: set → last_error → count");
    efw_diag_clear();
    efw_diag_set(EFW_ERR_IO, "sensor", "temp", "read failed");
    const efw_error_t *err = efw_diag_last_error();
    CHECK(err->code == EFW_ERR_IO, "code mismatch");
    CHECK(strcmp(err->module, "sensor") == 0, "module mismatch");
    CHECK(efw_diag_error_count() == 1, "count mismatch");
    PASS();
}

static void test_diag_history(void) {
    TEST("L1/Diag: history ring buffer");
    efw_diag_clear();
    for (int i = 0; i < EFW_ERROR_HISTORY_SIZE + 2; ++i) {
        efw_diag_set((efw_status_t)(-1 - i), "m", "n", "msg");
    }
    CHECK(efw_diag_error_count() == (uint32_t)(EFW_ERROR_HISTORY_SIZE + 2), "total count");
    const efw_error_t *last = efw_diag_last_error();
    CHECK(last->code == (efw_status_t)(-1 - EFW_ERROR_HISTORY_SIZE - 1), "last error code");
    PASS();
}

static uint32_t g_debug_iter_count;
static void debug_iter_count_cb(const efw_debug_point_t *point, void *user) {
    (void)point;
    uint32_t *count = (uint32_t *)user;
    (*count)++;
}

static void test_debug_foreach_point(void) {
    TEST("L1/Debug: foreach registered points");
    uint32_t value = 42;
    ASSERT_OK(efw_debug_init());
    ASSERT_OK(efw_debug_register_custom("test.value", EFW_DEBUG_TYPE_U32, &value));
    g_debug_iter_count = 0;
    efw_debug_foreach_point(debug_iter_count_cb, &g_debug_iter_count);
    CHECK(g_debug_iter_count == 1, "should enumerate one point");
    ASSERT_OK(efw_debug_unregister("test.value"));
    PASS();
}

/* ========================================================================
 *  L1: 单元测试 — 数据结构
 * ======================================================================== */

static void test_ringbuf_push_pop(void) {
    TEST("L1/RingBuf: push/pop single bytes");
    uint8_t buf[8];
    efw_ringbuf_t rb;
    ASSERT_OK(efw_ringbuf_init(&rb, buf, 8));
    CHECK(efw_ringbuf_empty(&rb), "should be empty");
    ASSERT_OK(efw_ringbuf_push(&rb, 0xAA));
    ASSERT_OK(efw_ringbuf_push(&rb, 0xBB));
    CHECK(efw_ringbuf_size(&rb) == 2, "size should be 2");
    uint8_t v;
    ASSERT_OK(efw_ringbuf_pop(&rb, &v));
    CHECK(v == 0xAA, "first pop mismatch");
    ASSERT_OK(efw_ringbuf_pop(&rb, &v));
    CHECK(v == 0xBB, "second pop mismatch");
    CHECK(efw_ringbuf_empty(&rb), "should be empty");
    PASS();
}

static void test_ringbuf_bulk_write_read(void) {
    TEST("L1/RingBuf: bulk write/read with wraparound");
    uint8_t buf[8];
    efw_ringbuf_t rb;
    ASSERT_OK(efw_ringbuf_init(&rb, buf, 8));
    for (int cycle = 0; cycle < 5; ++cycle) {
        uint8_t data[8];
        for (int i = 0; i < 8; ++i) data[i] = (uint8_t)(cycle * 10 + i);
        CHECK(efw_ringbuf_write(&rb, data, 8) == 8, "write should return 8");
        CHECK(efw_ringbuf_full(&rb), "should be full");
        uint8_t out[8];
        CHECK(efw_ringbuf_read(&rb, out, 8) == 8, "read should return 8");
        CHECK(memcmp(data, out, 8) == 0, "data mismatch");
        CHECK(efw_ringbuf_empty(&rb), "should be empty");
    }
    PASS();
}

static void test_ringbuf_partial_write(void) {
    TEST("L1/RingBuf: partial write when nearly full");
    uint8_t buf[4];
    efw_ringbuf_t rb;
    ASSERT_OK(efw_ringbuf_init(&rb, buf, 4));
    uint8_t data[] = {1, 2, 3};
    CHECK(efw_ringbuf_write(&rb, data, 3) == 3, "write 3");
    uint8_t more[] = {4, 5, 6};
    CHECK(efw_ringbuf_write(&rb, more, 3) == 1, "should only write 1");
    CHECK(efw_ringbuf_full(&rb), "should be full");
    PASS();
}

static void test_queue_fifo(void) {
    TEST("L1/Queue: FIFO order");
    uint8_t buf[4 * sizeof(int)];
    efw_queue_t q;
    ASSERT_OK(efw_queue_init(&q, buf, sizeof(int), 4));
    int vals[] = {10, 20, 30};
    for (int i = 0; i < 3; ++i) efw_queue_push(&q, &vals[i]);
    int v;
    efw_queue_pop(&q, &v); CHECK(v == 10, "first should be 10");
    efw_queue_pop(&q, &v); CHECK(v == 20, "second should be 20");
    efw_queue_pop(&q, &v); CHECK(v == 30, "third should be 30");
    PASS();
}

static void test_stack_lifo(void) {
    TEST("L1/Stack: LIFO order");
    uint8_t buf[4 * sizeof(int)];
    efw_stack_t s;
    ASSERT_OK(efw_stack_init(&s, buf, sizeof(int), 4));
    int vals[] = {10, 20, 30};
    for (int i = 0; i < 3; ++i) efw_stack_push(&s, &vals[i]);
    int v;
    efw_stack_pop(&s, &v); CHECK(v == 30, "first should be 30");
    efw_stack_pop(&s, &v); CHECK(v == 20, "second should be 20");
    efw_stack_pop(&s, &v); CHECK(v == 10, "third should be 10");
    PASS();
}

/* ========================================================================
 *  L2: 边界测试
 * ======================================================================== */

static void test_boundary_duplicate_register(void) {
    TEST("L2: duplicate name rejected across registries");
    efw_hal_registry_init();
    efw_hal_ops_t h1 = { .name = "x", .type = EFW_HAL_GPIO };
    efw_hal_ops_t h2 = { .name = "x", .type = EFW_HAL_ADC };
    ASSERT_OK(efw_hal_register(&h1));
    CHECK(efw_hal_register(&h2) == EFW_ERR_ALREADY_EXISTS, "should reject");
    PASS();
}

static void test_boundary_not_found(void) {
    TEST("L2: get non-existent returns NOT_FOUND");
    efw_hal_registry_init();
    const efw_hal_ops_t *out;
    CHECK(efw_hal_get("nonexistent", &out) == EFW_ERR_NOT_FOUND, "should be NOT_FOUND");
    PASS();
}

static void test_boundary_null_params(void) {
    TEST("L2: NULL parameter checks");
    CHECK(efw_hal_get(0, 0) == EFW_ERR_INVALID, "null name");
    CHECK(efw_hal_register(0) == EFW_ERR_INVALID, "null ops");
    CHECK(efw_sensor_read(0, 0, 0) == EFW_ERR_INVALID, "null name");
    CHECK(efw_module_get(0, 0) == EFW_ERR_INVALID, "null name");
    CHECK(efw_sm_init(0, 0, 0, 0, 0) == EFW_ERR_INVALID, "null ctx");
    CHECK(efw_scheduler_init() == EFW_OK, "init should always work");
    PASS();
}

static void test_boundary_register_limit(void) {
    TEST("L2: register to capacity limit");
    efw_algo_registry_init();
    char names[20][8];
    efw_algo_ops_t algos[20];
    int registered = 0;
    for (int i = 0; i < 20; ++i) {
        snprintf(names[i], 8, "a%d", i);
        algos[i] = (efw_algo_ops_t){ .name = names[i], .type = EFW_ALGO_CUSTOM, .run = mock_algo_double };
        efw_status_t s = efw_algo_register(&algos[i]);
        if (s == EFW_OK) registered++;
        else { CHECK(s == EFW_ERR_FULL, "should be FULL"); break; }
    }
    CHECK(registered == EFW_MAX_ALGOS, "should fill to max");
    PASS();
}

/* ========================================================================
 *  L3: 集成测试 — 传感器融合管线
 * ======================================================================== */

static void test_integration_sensor_algo_actuator(void) {
    TEST("L3: Sensor → Algorithm → Actuator pipeline");
    efw_hal_registry_init();
    efw_sensor_registry_init();
    efw_actuator_registry_init();
    efw_algo_registry_init();

    efw_hal_ops_t adc = { .name = "adc", .type = EFW_HAL_ADC, .read = mock_adc_read };
    efw_sensor_ops_t sens = { .name = "temp", .type = EFW_SENSOR_CUSTOM, .read = mock_sensor_read };
    efw_actuator_ops_t mot = { .name = "motor", .type = EFW_ACTUATOR_MOTOR, .write = mock_actuator_write };
    float algo_ctx = 0;
    efw_algo_ops_t dbl = { .name = "dbl", .type = EFW_ALGO_CUSTOM, .ctx = &algo_ctx, .run = mock_algo_double };

    efw_hal_register(&adc);
    efw_sensor_register(&sens);
    efw_actuator_register(&mot);
    efw_algo_register(&dbl);

    g_adc_val = 0.5f;
    float raw, processed;
    ASSERT_OK(efw_sensor_read("temp", &raw, sizeof(raw)));
    ASSERT_OK(efw_algo_run("dbl", &raw, sizeof(raw), &processed, sizeof(processed)));
    efw_actuator_cmd_t cmd = { .value = processed };
    ASSERT_OK(efw_actuator_write("motor", &cmd, sizeof(cmd)));

    CHECK(raw == 0.5f, "raw mismatch");
    CHECK(processed == 1.0f, "processed mismatch");
    CHECK(g_motor_val == 1.0f, "motor mismatch");
    PASS();
}

/* ========================================================================
 *  L3: 集成测试 — 状态机驱动执行器
 * ======================================================================== */

static efw_status_t sm_run_enter(void *ctx) {
    (void)ctx;
    efw_actuator_cmd_t cmd = { .value = 1.0f };
    efw_actuator_write("motor", &cmd, sizeof(cmd));
    return EFW_OK;
}

static efw_status_t sm_stop_enter(void *ctx) {
    (void)ctx;
    efw_actuator_cmd_t cmd = { .value = 0.0f };
    efw_actuator_write("motor", &cmd, sizeof(cmd));
    return EFW_OK;
}

static void test_integration_sm_actuator(void) {
    TEST("L3: StateMachine transitions drive Actuator");
    efw_actuator_registry_init();
    efw_actuator_ops_t mot = { .name = "motor", .type = EFW_ACTUATOR_MOTOR, .write = mock_actuator_write };
    efw_actuator_register(&mot);

    efw_state_def_t idle = { .name = "idle", .on_tick = sm_on_tick };
    efw_state_def_t run = { .name = "run", .on_enter = sm_run_enter, .on_tick = sm_on_tick };
    efw_state_def_t stop = { .name = "stop", .on_enter = sm_stop_enter, .on_tick = sm_on_tick };
    efw_sm_transition_t trans[] = {
        { .from = &idle, .to = &run, .condition = sm_cond, .priority = 10 },
        { .from = &run, .to = &stop, .condition = sm_cond, .priority = 10 },
    };
    efw_sm_context_t sm;
    g_sm_cond = 0;
    g_motor_val = 0.0f;
    efw_sm_init(&sm, "ctrl", &idle, trans, 2);
    efw_sm_set_elapsed(&sm, 100);

    g_sm_cond = 1;
    efw_sm_tick(&sm);
    CHECK(strcmp(efw_sm_current_state(&sm), "run") == 0, "should be run");
    CHECK(g_motor_val == 1.0f, "motor should be on");

    efw_sm_tick(&sm);
    CHECK(strcmp(efw_sm_current_state(&sm), "stop") == 0, "should be stop");
    CHECK(g_motor_val == 0.0f, "motor should be off");
    PASS();
}

/* ========================================================================
 *  L3: 集成测试 — 事件驱动模块通信
 * ======================================================================== */

static float g_last_sensor_val;
static uint32_t g_sensor_events;

static void on_sensor_data(uint16_t id, const void *data, uint16_t size, void *user) {
    (void)id; (void)size; (void)user;
    if (data) { g_last_sensor_val = *(const float *)data; g_sensor_events++; }
}

static void test_integration_event_driven(void) {
    TEST("L3: Event-driven sensor → subscriber → actuator");
    efw_topic_clear();
    efw_event_queue_init();
    efw_actuator_registry_init();
    efw_actuator_ops_t mot = { .name = "motor", .type = EFW_ACTUATOR_MOTOR, .write = mock_actuator_write };
    efw_actuator_register(&mot);

    g_sensor_events = 0;
    efw_topic_subscribe(10, on_sensor_data, 0);

    for (int i = 0; i < 5; ++i) {
        float val = (float)(i + 1) * 0.1f;
        efw_event_queue_post(10, &val, sizeof(val));
    }
    efw_event_queue_process();

    CHECK(g_sensor_events == 5, "should receive 5 events");
    CHECK(g_last_sensor_val > 0.4f && g_last_sensor_val < 0.6f, "last val ~0.5");

    efw_actuator_cmd_t cmd = { .value = g_last_sensor_val };
    efw_actuator_write("motor", &cmd, sizeof(cmd));
    CHECK(g_motor_val > 0.4f && g_motor_val < 0.6f, "motor ~0.5");
    PASS();
}

/* ========================================================================
 *  L4: 压力测试 — 大量注册/注销
 * ======================================================================== */

static void test_stress_hal_register_unregister(void) {
    TEST("L4: stress — 100 register/unregister cycles");
    efw_hal_registry_init();
    efw_hal_ops_t h = { .name = "test", .type = EFW_HAL_GPIO };
    for (int i = 0; i < 100; ++i) {
        ASSERT_OK(efw_hal_register(&h));
        CHECK(efw_hal_count() == 1, "count should be 1");
        ASSERT_OK(efw_hal_unregister("test"));
        CHECK(efw_hal_count() == 0, "count should be 0");
    }
    PASS();
}

static void test_stress_scheduler_many_tasks(void) {
    TEST("L4: stress — register EFW_MAX_SCHEDULER_TASKS tasks");
    efw_scheduler_init();
    efw_scheduler_task_def_t tasks[EFW_MAX_SCHEDULER_TASKS];
    char names[EFW_MAX_SCHEDULER_TASKS][8];
    for (int i = 0; i < EFW_MAX_SCHEDULER_TASKS; ++i) {
        snprintf(names[i], 8, "t%d", i);
        tasks[i] = (efw_scheduler_task_def_t){ .name = names[i], .period_ms = (uint32_t)(i + 1), .fn = t_1ms };
        ASSERT_OK(efw_scheduler_register(&tasks[i]));
    }
    CHECK(efw_scheduler_task_count() == EFW_MAX_SCHEDULER_TASKS, "should fill to max");
    for (uint32_t ms = 1; ms <= 1000; ++ms) efw_scheduler_tick(ms);
    PASS();
}

static void test_stress_event_flood(void) {
    TEST("L4: stress — event queue fill/drain 100 cycles");
    efw_topic_clear();
    efw_event_queue_init();
    g_evt_count = 0;
    efw_topic_subscribe(1, evt_cb, 0);
    for (int cycle = 0; cycle < 100; ++cycle) {
        float v = (float)cycle;
        for (int i = 0; i < EFW_EVENT_QUEUE_CAPACITY; ++i) {
            efw_event_queue_post(1, &v, sizeof(v));
        }
        efw_event_queue_process();
    }
    CHECK(g_evt_count == (uint32_t)(100 * EFW_EVENT_QUEUE_CAPACITY), "should process all");
    PASS();
}

/* ========================================================================
 *  L3: 集成测试 — 完整仿真 (10000 步)
 * ======================================================================== */

typedef struct {
    float velocity;
    float target;
    float motor_output;
    uint32_t tick;
} vehicle_t;

static vehicle_t g_veh;

static void veh_step(float dt) {
    float accel = (g_veh.motor_output - g_veh.velocity) * 10.0f;
    g_veh.velocity += accel * dt;
    if (g_veh.velocity < 0) g_veh.velocity = 0;
    if (g_veh.velocity > 3) g_veh.velocity = 3;
    g_veh.tick++;
}

static efw_status_t veh_sensor_read(void *ctx, void *out, uint16_t out_size) {
    (void)ctx;
    if (!out || out_size < sizeof(float)) return EFW_ERR_INVALID;
    *(float *)out = g_veh.velocity;
    return EFW_OK;
}

static void test_integration_full_simulation(void) {
    TEST("L3: full simulation — 10000 steps with all subsystems");
    efw_diag_clear();
    efw_init();

    /* Register components */
    efw_hal_ops_t adc = { .name = "adc", .type = EFW_HAL_ADC, .read = mock_adc_read };
    efw_sensor_ops_t vel = { .name = "vel", .type = EFW_SENSOR_CUSTOM, .read = veh_sensor_read };
    efw_actuator_ops_t mot = { .name = "motor", .type = EFW_ACTUATOR_MOTOR, .write = mock_actuator_write };
    efw_hal_register(&adc); efw_sensor_register(&vel); efw_actuator_register(&mot);

    /* PID */
    efw_pid_t pid; memset(&pid, 0, sizeof(pid));
    pid.kp = 1.5f; pid.ki = 0.3f; pid.kd = 0.05f;
    pid.out_min = 0; pid.out_max = 1; pid.anti_windup = 1;
    pid.integral_min = 0; pid.integral_max = 1;
    efw_algo_ops_t pid_algo = { .name = "pid", .type = EFW_ALGO_CONTROL, .ctx = &pid, .run = efw_pid_run };
    efw_algo_register(&pid_algo);

    /* State machine */
    efw_state_def_t s_idle = { .name = "idle", .on_tick = sm_on_tick };
    efw_state_def_t s_run = { .name = "run", .on_tick = sm_on_tick };
    g_veh_cond = 1;
    efw_sm_transition_t trans[] = {
        { .from = &s_idle, .to = &s_run, .condition = veh_cond, .priority = 10 },
    };
    efw_sm_context_t sm;
    efw_sm_init(&sm, "main", &s_idle, trans, 1);
    efw_sm_register(&sm);

    /* Scheduler */
    efw_scheduler_task_def_t t_pub = { .name = "pub", .period_ms = 100, .fn = t_1ms };
    efw_scheduler_register(&t_pub);

    /* Events */
    efw_topic_clear();
    efw_event_queue_init();
    g_sensor_events = 0;
    efw_topic_subscribe(1, on_sensor_data, 0);

    /* Init vehicle */
    memset(&g_veh, 0, sizeof(g_veh));
    g_veh.target = 1.0f;
    efw_pid_reset(&pid);

    float dt = 0.001f;

    /* Main loop */
    for (uint32_t ms = 1; ms <= 10000; ++ms) {
        efw_sm_set_elapsed(&sm, ms);
        efw_sm_tick(&sm);
        efw_scheduler_tick(ms);

        float raw;
        efw_sensor_read("vel", &raw, sizeof(raw));

        efw_pid_input_t pin = { .setpoint = g_veh.target, .feedback = raw, .dt = dt };
        efw_pid_output_t pout;
        efw_algo_run("pid", &pin, sizeof(pin), &pout, sizeof(pout));

        g_veh.motor_output = pout.output;
        veh_step(dt);

        if (ms % 100 == 0) {
            float speed = g_veh.velocity;
            efw_event_queue_post(1, &speed, sizeof(speed));
        }
    }

    efw_event_queue_process();

    printf("(vel=%.3f, events=%lu, errors=%lu) ",
           g_veh.velocity, (unsigned long)g_sensor_events, (unsigned long)efw_diag_error_count());
    CHECK(g_veh.velocity > 0.5f, "vehicle should have moved");
    CHECK(g_veh.velocity < 2.0f, "no extreme overshoot");
    CHECK(efw_diag_error_count() == 0, "no errors");
    CHECK(g_sensor_events > 0, "events should fire");
    PASS();
}

/* ========================================================================
 *  主函数
 * ======================================================================== */

int main(void) {
    printf("=== EFW 框架完整仿真测试 ===\n\n");

    printf("[L1 — 单元测试]\n");
    test_hal_register_get();
    test_hal_read_write();
    test_hal_enumerate();
    test_sensor_lifecycle();
    test_actuator_lifecycle();
    test_algo_lifecycle();
    test_module_priority_ordering();
    test_module_priority_after_unregister();
    test_module_lifecycle();
    test_module_poll_all_tolerance();
    test_pid_positive_error();
    test_pid_negative_error();
    test_pid_output_clamp();
    test_pid_integral();
    test_pid_reset();
    test_sm_basic_tick();
    test_sm_null_tick_is_valid();
    test_sm_condition_transition();
    test_sm_timeout_transition();
    test_sm_priority_ordering();
    test_sm_snapshot_protection();
    test_sm_dynamic_transitions();
    test_sm_registry();
    test_scheduler_multi_period();
    test_scheduler_pause_resume();
    test_scheduler_unregister();
    test_event_subscribe_publish();
    test_event_queue_basic();
    test_event_queue_null_data_size_zero();
    test_event_queue_null_data_size_nonzero();
    test_event_queue_overflow();
    test_event_queue_large_data();
    test_event_queue_process_limited();
    test_diag_basic();
    test_diag_history();
    test_debug_foreach_point();
    test_ringbuf_push_pop();
    test_ringbuf_bulk_write_read();
    test_ringbuf_partial_write();
    test_queue_fifo();
    test_stack_lifo();

    printf("\n[L2 — 边界测试]\n");
    test_boundary_duplicate_register();
    test_boundary_not_found();
    test_boundary_null_params();
    test_boundary_register_limit();

    printf("\n[L3 — 集成测试]\n");
    test_integration_sensor_algo_actuator();
    test_integration_sm_actuator();
    test_integration_event_driven();
    test_integration_full_simulation();

    printf("\n[L4 — 压力测试]\n");
    test_stress_hal_register_unregister();
    test_stress_scheduler_many_tasks();
    test_stress_event_flood();

    printf("\n=== 结果: %d/%d 通过", g_pass, g_run);
    if (g_fail > 0) printf(", %d 失败", g_fail);
    printf(" ===\n");
    return g_fail > 0 ? 1 : 0;
}
