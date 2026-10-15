/* Boundary hunt for the EFW framework + CT117E-M4 platform.
 * Engineering-mode only (B4 held at reset). Pushes until something breaks,
 * prints [BOUND] rows; UART line is printed BEFORE each risky switch so a
 * dead board still marks the boundary. Recover by power-cycle.
 */
#ifndef HOST_BUILD

#include <stdint.h>
#include <string.h>
#include "efw/efw.h"
#include "bsp.h"
#include "lcd.h"
#include "boundary.h"

extern volatile uint32_t g_ms_tick;
extern const unsigned char ASCII_Table[];   /* flash canary: big const table */

/* ---------- stack high-water ---------- */
#if defined(__ARMCC_VERSION)
extern char Image$$RW_IRAM1$$ZI$$Limit;             /* end of ZI (armlink) */
#define BSS_END   ((uint32_t)&Image$$RW_IRAM1$$ZI$$Limit)
#else
extern uint32_t _ebss, _estack;                     /* GNU ld symbols */
#define BSS_END   ((uint32_t)&_ebss)
#endif
#define STACK_TOP 0x20008000u                        /* top of 32K SRAM */

void bsp_stack_paint(void)
{
    volatile uint32_t *p = (uint32_t *)BSS_END;
    volatile uint32_t *end = (uint32_t *)(STACK_TOP - 2048u);  /* keep live stack clear */
    while (p < end) *p++ = 0xA5A5A5A5u;
}

static uint32_t stack_high_water(void)
{
    volatile uint32_t *p = (uint32_t *)(STACK_TOP - 2048u);
    while (p > (uint32_t *)BSS_END && *p == 0xA5A5A5A5u) p--;
    return (uint32_t)(STACK_TOP - (uint32_t)p);
}

/* ---------- flash canary: checksum of ASCII_Table ---------- */
static uint32_t canary_ref;

static uint32_t canary_calc(void)
{
    const unsigned char *p = ASCII_Table;
    uint32_t sum = 2166136261u;                     /* FNV-1a */
    for (int i = 0; i < 96 * 24 * 2; i++) {
        sum ^= p[i];
        sum *= 16777619u;
    }
    return sum;
}

/* ---------- frequency sweep ---------- */
static efw_status_t bnd_sched_cb(void *c) { (*(uint32_t *)c)++; return EFW_OK; }

static uint32_t measure_lookup32(void)
{
    extern char s_sensor_names[40][8];               /* from stress.c (non-static) */
    uint32_t t0, t1; uint16_t v;
    t0 = dwt_us();
    for (int i = 0; i < 10000; i++) efw_sensor_read(s_sensor_names[28], &v, 2);
    t1 = dwt_us();
    return ((t1 - t0) * 1000u) / 10000u;             /* ns/op */
}

static uint32_t measure_pid_ns(void)
{
    static efw_pid_t pid;
    static const efw_algo_ops_t ops = { "bnd_pid", EFW_ALGO_CONTROL, &pid, efw_pid_run };
    efw_pid_input_t in; efw_pid_output_t out;
    uint32_t t0, t1;
    memset(&pid, 0, sizeof(pid));
    pid.kp = 1.0f; pid.ki = 0.1f; pid.kd = 0.01f; pid.out_min = -100; pid.out_max = 100;
    efw_pid_reset(&pid);
    efw_algo_register(&ops);
    in.setpoint = 1.0f; in.feedback = 0.3f; in.dt = 0.001f; in.feedforward = 0.0f;
    t0 = dwt_us();
    for (int i = 0; i < 10000; i++) efw_algo_run("bnd_pid", &in, sizeof(in), &out, sizeof(out));
    t1 = dwt_us();
    efw_algo_unregister("bnd_pid");
    return ((t1 - t0) * 1000u) / 10000u;
}

static uint32_t measure_lcd_clear_ms(void)
{
    uint32_t t0 = dwt_us();
    LCD_Clear(Black);
    return (dwt_us() - t0) / 1000u;
}

static uint32_t measure_sched16(void)
{
    static uint32_t cnt[16];
    static char names[16][8];
    static efw_scheduler_task_def_t defs[16];
    /* re-register 16 tasks */
    for (int i = 0; i < 16; i++) {
        names[i][0] = 'b'; names[i][1] = '0' + (i / 10); names[i][2] = '0' + (i % 10); names[i][3] = 0;
        defs[i].name = names[i]; defs[i].period_ms = 1; defs[i].ctx = &cnt[i];
        defs[i].fn = bnd_sched_cb;
        if (efw_scheduler_register(&defs[i]) != EFW_OK) { /* slot may exist */ }
    }
    for (int i = 0; i < 16; i++) cnt[i] = 0;
    uint32_t start = g_ms_tick, last = start;
    while ((g_ms_tick - start) < 500) {
        uint32_t now = g_ms_tick;
        if (now != last) { efw_scheduler_tick(now - last); last = now; }
    }
    uint32_t total = 0;
    for (int i = 0; i < 16; i++) total += cnt[i];
    for (int i = 0; i < 16; i++) efw_scheduler_unregister(names[i]);
    return total;                                     /* expect 8000 in 500ms */
}

static void boundary_freq_sweep(void)
{
    static const struct { uint32_t mhz, ws; } sweep[] = {
        { 80, 2 }, { 120, 3 }, { 160, 4 }, { 170, 4 }, { 176, 4 }, { 184, 4 },
    };
    OUTLN("[BOUND] freq sweep (canary-verified):");
    for (unsigned k = 0; k < sizeof(sweep) / sizeof(sweep[0]); k++) {
        uint32_t f = sweep[k].mhz, ws = sweep[k].ws;
        outs("[BOUND] trying "); outi((int32_t)f);
        outs(" MHz ws="); outi((int32_t)ws); outs(" ...\r\n");
        if (!bsp_clock_boost_to(f, ws)) {
            outs("[BOUND]   cfg rejected -> stop sweep\r\n");
            break;
        }
        uint32_t can = canary_calc();
        if (can != canary_ref) {
            outs("[BOUND]   FLASH CANARY MISMATCH -> freq boundary found!\r\n");
            bsp_clock_boost_to(80, 2);
            break;
        }
        /* sanity: uart works (we printed), dwt alive: quick loop */
        uint32_t lut = measure_lookup32();
        uint32_t pid = measure_pid_ns();
        uint32_t clear_ms = measure_lcd_clear_ms();
        uint32_t runs = measure_sched16();
        outs("[BOUND]   f="); outi((int32_t)f);
        outs(" lookup32="); outi((int32_t)lut);
        outs("ns pid="); outi((int32_t)pid);
        outs("ns clear="); outi((int32_t)clear_ms);
        outs("ms sched16runs="); outi((int32_t)runs);
        outs("/8000\r\n");
    }
    bsp_clock_boost_to(80, 2);
    outs("[BOUND] sweep done, back to 80MHz\r\n");
}

/* ---------- scheduler starvation ---------- */
static uint32_t g_fast_cnt;
static efw_status_t fast_cb(void *c) { (*(uint32_t *)c)++; return EFW_OK; }
static efw_status_t blocker_cb(void *c) { (void)c; uint32_t t0 = dwt_cycles(); while ((dwt_cycles() - t0) < 3u * bsp_sysclk_mhz() * 1000u) { } return EFW_OK; }

static void boundary_starvation(void)
{
    static efw_scheduler_task_def_t fast = { "bnd_fast", 1, fast_cb, &g_fast_cnt };
    static efw_scheduler_task_def_t blk1 = { "bnd_blk1", 2, blocker_cb, 0 };
    static efw_scheduler_task_def_t blk2 = { "bnd_blk2", 2, blocker_cb, 0 };
    OUTLN("[BOUND] starvation: 1ms task vs N blocking tasks (3ms exec / 2ms period):");
    efw_scheduler_register(&fast);
    for (int stage = 0; stage <= 2; stage++) {
        if (stage == 1) efw_scheduler_register(&blk1);
        if (stage == 2) efw_scheduler_register(&blk2);
        g_fast_cnt = 0;
        uint32_t start = g_ms_tick, last = start;
        while ((g_ms_tick - start) < 1000) {
            uint32_t now = g_ms_tick;
            if (now != last) { efw_scheduler_tick(now - last); last = now; }
        }
        outs("[BOUND]   blockers="); outi(stage);
        outs(" 1ms-task runs in 1s = "); outi((int32_t)g_fast_cnt);
        outs(" (ideal 1000)\r\n");
    }
    efw_scheduler_unregister("bnd_fast");
    efw_scheduler_unregister("bnd_blk1");
    efw_scheduler_unregister("bnd_blk2");
}

/* ---------- event saturation ---------- */
static uint32_t g_hit;
static void sat_cb(uint16_t id, const void *d, uint16_t s, void *u) { (void)id; (void)d; (void)s; (void)u; g_hit++; }

static void boundary_event_sat(void)
{
    uint32_t payload = 7;
    for (int i = 0; i < 4; i++) efw_topic_subscribe(95, sat_cb, 0);
    g_hit = 0;
    uint32_t t0 = dwt_us();
    uint32_t n = 0;
    while ((dwt_us() - t0) < 100000u) { efw_topic_publish(95, &payload, 4); n++; }
    uint32_t dt = dwt_us() - t0;
    uint32_t ops_s = (uint32_t)((uint64_t)n * 1000000u / dt);
    outs("[BOUND] publish saturation: "); outi((int32_t)n);
    outs(" pubs in 100ms x4subs = "); outi((int32_t)ops_s); outs(" pubs/s\r\n");
    for (int i = 0; i < 4; i++) efw_topic_unsubscribe(95, sat_cb);
}

/* ---------- uart throughput ---------- */
static void boundary_uart(void)
{
    uint32_t t0 = dwt_us();
    for (int i = 0; i < 200; i++) outc('.');
    uint32_t dt = dwt_us() - t0;
    uint32_t ns_per_char = dt * 1000u / 200u;
    outs("\r\n[BOUND] uart blocking rate = "); outi((int32_t)ns_per_char);
    outs(" ns/char @115200 -> max "); outi((int32_t)(115200 / 10));
    outs(" B/s; 1ms budget fits "); outi((int32_t)(1000000u / ns_per_char));
    outs(" chars\r\n");
}

/* ---------- queue burst roundtrip ---------- */
static void boundary_queue(void)
{
    uint8_t d[4] = { 1, 2, 3, 4 };
    uint32_t t0 = dwt_us();
    uint32_t n = 0;
    while ((dwt_us() - t0) < 100000u) {
        efw_event_queue_post(96, d, 4);
        efw_event_queue_process();
        n++;
    }
    uint32_t dt = dwt_us() - t0;
    outs("[BOUND] queue sustained: "); outi((int32_t)((uint64_t)n * 1000000u / dt));
    outs(" roundtrips/s\r\n");
}

void boundary_run_all(void)
{
    OUTLN("==================================================");
    OUTLN("==== BOUNDARY HUNT ====");
    bsp_clock_boost_to(80, 2);
    canary_ref = canary_calc();                       /* reference @ known-good */
    boundary_uart();
    boundary_freq_sweep();
    boundary_starvation();
    boundary_event_sat();
    boundary_queue();
    outs("[BOUND] stack high-water = "); outi((int32_t)stack_high_water());
    outs(" bytes (of 32KB)\r\n");
    OUTLN("==== BOUNDARY DONE ====");
}

#endif /* !HOST_BUILD */

#ifdef HOST_BUILD
void boundary_run_all(void) { }
#endif
