/* EFW stress tests: registry saturation, scheduler full load, event storm,
 * data-structure fuzzing, throughput, soak. Prints [STRESS] lines and fills
 * g_stress for the LCD dashboard. */
#include <stdint.h>
#include <string.h>
#include "efw/efw.h"
#include "bsp.h"
#include "lcd.h"
#include "stress.h"

stress_results_t g_stress;
extern volatile uint32_t g_ms_tick;

/* ================= registry saturation ================= */

static efw_status_t stub_read(void *ctx, void *out, uint16_t out_size)
{ (void)ctx; (void)out; (void)out_size; return EFW_OK; }

char s_sensor_names[40][8];                          /* non-static: boundary.c reads */
efw_sensor_ops_t s_sensor_ops[40];

static char s_hal_names[20][8];
static efw_hal_ops_t s_hal_ops[20];

static char s_act_names[20][8];
static efw_actuator_ops_t s_act_ops[20];

static char s_algo_names[20][8];
static efw_algo_ops_t s_algo_ops[20];

static efw_status_t stub_mod_init(void *c)  { (void)c; return EFW_OK; }
static efw_status_t stub_mod_poll(void *c)  { (void)c; return EFW_OK; }
static char s_mod_names[40][8];
static efw_module_ops_t s_mod_ops[40];

static efw_status_t stub_sm_enter(void *c)  { (void)c; return EFW_OK; }
static const efw_state_def_t s_sm_state = { "ST", 0, stub_sm_enter, 0, 0 };
static const efw_sm_transition_t s_sm_tr[1] = { { &s_sm_state, &s_sm_state, 0, 0, 0, 1 } };
static char s_sm_names[12][8];
static efw_sm_context_t s_sm_ctx[12];

/* small name builder: prefix + decimal index */
static void mkname(char *dst, const char *prefix, unsigned i)
{
    int p = 0;
    while (prefix[p]) { dst[p] = prefix[p]; p++; }
    if (i < 10u) {
        dst[p++] = (char)('0' + i);
    } else {
        dst[p++] = (char)('0' + (i / 10u));
        dst[p++] = (char)('0' + (i % 10u));
    }
    dst[p] = 0;
}

/* fill a registry with name-keyed stubs until FULL; returns number accepted */
static uint32_t fill_sensors(char *prefix)
{
    uint32_t added = 0;
    for (int i = 0; i < 40; i++) {
        mkname(s_sensor_names[i], prefix, (unsigned)i);
        s_sensor_ops[i].name = s_sensor_names[i];
        s_sensor_ops[i].type = EFW_SENSOR_CUSTOM;
        s_sensor_ops[i].channel_count = 1;
        s_sensor_ops[i].hal_name = 0; s_sensor_ops[i].comm_name = 0;
        s_sensor_ops[i].ctx = 0; s_sensor_ops[i].init = 0; s_sensor_ops[i].read = stub_read;
        if (efw_sensor_register(&s_sensor_ops[i]) != EFW_OK) return added;
        added++;
    }
    return added;
}

static uint32_t fill_hals(char *prefix)
{
    uint32_t added = 0;
    for (int i = 0; i < 20; i++) {
        mkname(s_hal_names[i], prefix, (unsigned)i);
        s_hal_ops[i].name = s_hal_names[i];
        s_hal_ops[i].type = EFW_HAL_CUSTOM;
        s_hal_ops[i].bus_id = 0; s_hal_ops[i].ctx = 0;
        s_hal_ops[i].init = 0; s_hal_ops[i].read = 0; s_hal_ops[i].write = 0; s_hal_ops[i].ioctl = 0;
        if (efw_hal_register(&s_hal_ops[i]) != EFW_OK) return added;
        added++;
    }
    return added;
}

static uint32_t fill_actuators(char *prefix)
{
    uint32_t added = 0;
    for (int i = 0; i < 20; i++) {
        mkname(s_act_names[i], prefix, (unsigned)i);
        s_act_ops[i].name = s_act_names[i];
        s_act_ops[i].type = EFW_ACTUATOR_CUSTOM;
        s_act_ops[i].hal_name = 0; s_act_ops[i].comm_name = 0;
        s_act_ops[i].ctx = 0;
        s_act_ops[i].init = 0; s_act_ops[i].enable = 0; s_act_ops[i].disable = 0;
        s_act_ops[i].write = (efw_status_t (*)(void *, const void *, uint16_t))stub_read;
        if (efw_actuator_register(&s_act_ops[i]) != EFW_OK) return added;
        added++;
    }
    return added;
}

static efw_status_t stub_run(void *ctx, const void *in, uint16_t is, void *out, uint16_t os)
{ (void)ctx; (void)in; (void)is; (void)out; (void)os; return EFW_OK; }

static uint32_t fill_algos(char *prefix)
{
    uint32_t added = 0;
    for (int i = 0; i < 20; i++) {
        mkname(s_algo_names[i], prefix, (unsigned)i);
        s_algo_ops[i].name = s_algo_names[i];
        s_algo_ops[i].type = EFW_ALGO_CUSTOM;
        s_algo_ops[i].ctx = 0;
        s_algo_ops[i].run = stub_run;
        if (efw_algo_register(&s_algo_ops[i]) != EFW_OK) return added;
        added++;
    }
    return added;
}

static uint32_t fill_modules(char *prefix)
{
    uint32_t added = 0;
    for (int i = 0; i < 40; i++) {
        mkname(s_mod_names[i], prefix, (unsigned)i);
        s_mod_ops[i].name = s_mod_names[i];
        s_mod_ops[i].type = EFW_MODULE_CUSTOM;
        s_mod_ops[i].priority = 200;
        s_mod_ops[i].ctx = 0;
        s_mod_ops[i].init = stub_mod_init; s_mod_ops[i].start = 0;
        s_mod_ops[i].stop = 0; s_mod_ops[i].poll = stub_mod_poll;
        if (efw_module_register(&s_mod_ops[i]) != EFW_OK) return added;
        added++;
    }
    return added;
}

static uint32_t fill_sms(char *prefix)
{
    uint32_t added = 0;
    for (int i = 0; i < 12; i++) {
        mkname(s_sm_names[i], prefix, (unsigned)i);
        if (efw_sm_init(&s_sm_ctx[i], s_sm_names[i], &s_sm_state, s_sm_tr, 1) != EFW_OK) return added;
        if (efw_sm_register(&s_sm_ctx[i]) != EFW_OK) return added;
        added++;
    }
    return added;
}

static void stress_registry_capacity(void)
{
    uint32_t t0, t1;
    OUTLN("[STRESS] registry saturation:");
    g_stress.cap_sensor   = fill_sensors("ss");
    g_stress.cap_hal      = fill_hals("hh");
    g_stress.cap_actuator = fill_actuators("aa");
    g_stress.cap_algo     = fill_algos("gg");
    g_stress.cap_module   = fill_modules("mm");
    g_stress.cap_sm       = fill_sms("sm");
    outs("    caps: sen="); outi((int32_t)g_stress.cap_sensor);
    outs(" hal="); outi((int32_t)g_stress.cap_hal);
    outs(" act="); outi((int32_t)g_stress.cap_actuator);
    outs(" alg="); outi((int32_t)g_stress.cap_algo);
    outs(" mod="); outi((int32_t)g_stress.cap_module);
    outs(" sm="); outi((int32_t)g_stress.cap_sm);
    outs("\r\n");
    /* worst-case lookup: last registered of 32 sensors */
    t0 = dwt_us();
    for (int i = 0; i < 10000; i++) { uint16_t v; efw_sensor_read(s_sensor_names[g_stress.cap_sensor - 1], &v, 2); }
    t1 = dwt_us();
    g_stress.lookup32_ns = ((t1 - t0) * 1000u) / 10000u;
    outs("[STRESS] lookup@32 = "); outi((int32_t)g_stress.lookup32_ns); outs(" ns/op (was 15654 @3)\r\n");
}

/* ================= scheduler full load ================= */

static uint32_t s_sched_cnt[16];
static char s_sched_names[16][8];
static efw_scheduler_task_def_t s_sched_defs[16];
static efw_status_t sched_cnt_cb(void *c) { (*(uint32_t *)c)++; return EFW_OK; }

static void stress_scheduler_full(void)
{
    uint32_t t0, t1, accepted = 0;
    for (int i = 0; i < 16; i++) {
        mkname(s_sched_names[i], "sc", (unsigned)i);
        s_sched_defs[i].name = s_sched_names[i];
        s_sched_defs[i].period_ms = 1;
        s_sched_defs[i].fn = sched_cnt_cb;
        s_sched_defs[i].ctx = &s_sched_cnt[i];
        if (efw_scheduler_register(&s_sched_defs[i]) == EFW_OK) accepted++;
    }
    g_stress.cap_sched = accepted;
    t0 = g_ms_tick;
    {
        uint32_t start = g_ms_tick, last = start;
        while ((g_ms_tick - start) < 200) {
            uint32_t now = g_ms_tick;
            if (now != last) { efw_scheduler_tick(now - last); last = now; }
        }
    }
    t1 = g_ms_tick;
    g_stress.sched16_ms = t1 - t0;
    uint32_t total = 0;
    for (int i = 0; i < (int)accepted; i++) total += s_sched_cnt[i];
    outs("[STRESS] 16x1ms tasks: accepted="); outi((int32_t)accepted);
    outs(" 200ms window runs="); outi((int32_t)total);
    outs(" wall="); outi((int32_t)g_stress.sched16_ms); outs("ms\r\n");
    for (int i = 0; i < (int)accepted; i++) efw_scheduler_unregister(s_sched_names[i]);
}

/* ================= event storm ================= */

static uint32_t s_cb_hits;
static void storm_cb(uint16_t id, const void *d, uint16_t sz, void *u)
{ (void)id; (void)d; (void)sz; (void)u; s_cb_hits++; }

static void stress_events(void)
{
    uint32_t t0, t1, payload = 1;
    for (int i = 0; i < 4; i++) efw_topic_subscribe(90, storm_cb, 0);
    s_cb_hits = 0;
    t0 = dwt_us();
    for (int i = 0; i < 20000; i++) efw_topic_publish(90, &payload, 4);
    t1 = dwt_us();
    g_stress.pub_ns = ((t1 - t0) * 1000u) / 20000u;
    outs("[STRESS] topic publish x4subs = "); outi((int32_t)g_stress.pub_ns);
    outs(" ns/pub (hits="); outi((int32_t)s_cb_hits); outs(")\r\n");
    for (int i = 0; i < 4; i++) efw_topic_unsubscribe(90, storm_cb);

    /* queue roundtrip */
    uint8_t data[4] = { 1, 2, 3, 4 };
    t0 = dwt_us();
    for (int i = 0; i < 2000; i++) {
        efw_event_queue_post(91, data, 4);
        efw_event_queue_process();
    }
    t1 = dwt_us();
    g_stress.queue_rt_ns = ((t1 - t0) * 1000u) / 2000u;
    outs("[STRESS] queue post+process = "); outi((int32_t)g_stress.queue_rt_ns); outs(" ns/roundtrip\r\n");
}

/* ================= ds fuzz vs shadow model ================= */

static uint32_t s_lcg = 0x12345678u;
static uint32_t rnd(void) { s_lcg = s_lcg * 1103515245u + 12345u; return (s_lcg >> 16) & 0x7FFF; }

static void stress_ds_fuzz(void)
{
    static efw_ringbuf_t rb; static uint8_t rb_buf[16];
    static efw_queue_t q; static int32_t q_buf[8];
    static efw_stack_t st; static int32_t st_buf[8];
    int rb_cnt = 0, q_cnt = 0, st_cnt = 0;
    uint32_t rb_sum = 0, q_sum = 0, st_sum = 0, bad = 0;
    uint32_t t0, t1;
    const uint32_t N = 200000;

    efw_ringbuf_init(&rb, rb_buf, 16);
    efw_queue_init(&q, q_buf, 4, 8);
    efw_stack_init(&st, st_buf, 4, 8);

    t0 = dwt_us();
    for (uint32_t i = 0; i < N; i++) {
        uint32_t op = rnd() % 6;
        int32_t v = (int32_t)(rnd() & 0xFFFF);
        switch (op) {
        case 0: case 1:
            if (efw_ringbuf_push(&rb, (uint8_t)v) == EFW_OK) { rb_cnt++; rb_sum += (uint8_t)v; }
            else if (rb_cnt >= 16) { /* expected full */ } else bad++;
            break;
        case 2: {
            uint8_t o;
            if (efw_ringbuf_pop(&rb, &o) == EFW_OK) { if (rb_cnt == 0) bad++; rb_cnt--; rb_sum -= o; }
            else if (rb_cnt != 0) bad++;
            break; }
        case 3:
            if (efw_queue_push(&q, &v) == EFW_OK) { q_cnt++; q_sum += (uint32_t)v; }
            else if (q_cnt < 8) bad++;
            break;
        case 4: {
            int32_t o;
            if (efw_queue_pop(&q, &o) == EFW_OK) { if (q_cnt == 0) bad++; q_cnt--; q_sum -= (uint32_t)o; }
            else if (q_cnt != 0) bad++;
            break; }
        default:
            if (rnd() & 1) {
                if (efw_stack_push(&st, &v) == EFW_OK) { st_cnt++; st_sum += (uint32_t)v; }
                else if (st_cnt < 8) bad++;
            } else {
                int32_t o;
                if (efw_stack_pop(&st, &o) == EFW_OK) { if (st_cnt == 0) bad++; st_cnt--; st_sum -= (uint32_t)o; }
                else if (st_cnt != 0) bad++;
            }
            break;
        }
        if ((int)efw_ringbuf_size(&rb) != rb_cnt) bad++;
        if ((int)efw_queue_count(&q) != q_cnt) bad++;
        if ((int)efw_stack_count(&st) != st_cnt) bad++;
    }
    t1 = dwt_us();
    g_stress.fuzz_ops = N;
    g_stress.fuzz_bad = bad;
    outs("[STRESS] ds fuzz 200k ops in "); outi((int32_t)((t1 - t0) / 1000));
    outs(" ms, violations="); outi((int32_t)bad); outs("\r\n");
}

/* ================= pid throughput ================= */

static void stress_pid_throughput(void)
{
    /* register a fresh pid */
    static efw_pid_t pid;
    static const efw_algo_ops_t ops = { "stress_pid", EFW_ALGO_CONTROL, &pid, efw_pid_run };
    efw_pid_input_t in; efw_pid_output_t out;
    uint32_t t0, t1, n = 0;
    memset(&pid, 0, sizeof(pid));
    pid.kp = 1.0f; pid.ki = 0.1f; pid.kd = 0.01f; pid.out_min = -100; pid.out_max = 100;
    efw_algo_register(&ops);
    in.setpoint = 1.0f; in.feedback = 0.2f; in.dt = 0.001f; in.feedforward = 0.0f;
    t0 = dwt_us();
    while ((dwt_us() - t0) < 50000) {
        for (int i = 0; i < 100; i++) { efw_algo_run("stress_pid", &in, sizeof(in), &out, sizeof(out)); n++; }
    }
    t1 = dwt_us();
    g_stress.pid_ops_s = (uint32_t)((uint64_t)n * 1000000u / (t1 - t0));
    outs("[STRESS] pid throughput = "); outi((int32_t)(g_stress.pid_ops_s / 1000));
    outs(" kops/s\r\n");
    efw_algo_unregister("stress_pid");
}

/* ================= soak ================= */

static uint32_t s_soak1, s_soak2, s_soak3;
static efw_status_t soak_cb1(void *c) { (*(uint32_t *)c)++; return EFW_OK; }
static efw_status_t soak_cb2(void *c) { (*(uint32_t *)c)++; return EFW_OK; }
static efw_status_t soak_cb3(void *c) { (*(uint32_t *)c)++; return EFW_OK; }

static void stress_soak(void)
{
    static efw_scheduler_task_def_t d1 = { "soak1", 1, soak_cb1, &s_soak1 };
    static efw_scheduler_task_def_t d2 = { "soak2", 10, soak_cb2, &s_soak2 };
    static efw_scheduler_task_def_t d3 = { "soak3", 50, soak_cb3, &s_soak3 };
    efw_diag_clear();
    efw_scheduler_register(&d1);
    efw_scheduler_register(&d2);
    efw_scheduler_register(&d3);
    for (int s = 1; s <= 20; s++) {
        uint32_t start = g_ms_tick, last = start;
        while ((g_ms_tick - start) < 1000) {
            uint32_t now = g_ms_tick;
            if (now != last) { efw_scheduler_tick(now - last); last = now; }
        }
        uint32_t errs = efw_diag_error_count();
        if (s % 5 == 0 || errs) {
            outs("[STRESS] soak "); outi(s); outs("s: t1="); outi((int32_t)s_soak1);
            outs(" t10="); outi((int32_t)s_soak2);
            outs(" t50="); outi((int32_t)s_soak3);
            outs(" diag_errs="); outi((int32_t)errs); outs("\r\n");
        }
    }
    g_stress.soak_errors = efw_diag_error_count();
    efw_scheduler_unregister("soak1");
    efw_scheduler_unregister("soak2");
    efw_scheduler_unregister("soak3");
    OUTLN("[STRESS] soak 20s done");
}

void stress_run_all(void)
{
    OUTLN("==================================================");
    OUTLN("==== STRESS PHASE ====");
    stress_registry_capacity();
    stress_scheduler_full();
    stress_events();
    stress_ds_fuzz();
    stress_pid_throughput();
    stress_soak();
    OUTLN("==== STRESS DONE ====");
}
