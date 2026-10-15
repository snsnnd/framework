/* LCD dashboard UI for the EFW hwtest.
 * Page 0: framework status (registries, tests, buttons, uptime, FPS)
 * Page 1: stress results
 * Page 2: sine wave + PID trace + bouncing ball (animation)
 */
#include <stdint.h>
#include <string.h>
#include "efw/efw.h"
#include "bsp.h"
#include "lcd.h"
#include "dashboard.h"
#include "stress.h"

extern volatile uint32_t g_ms_tick;
extern int t_total, t_pass;

#define PC_ODR (*(volatile uint32_t *)0x48000814u)

static int g_page = 0;
static int g_pause = 0;
static uint8_t g_last_btn = 0;
static uint32_t g_deb_ms = 0;
static uint32_t g_last_render = 0;
static uint32_t g_frames = 0, g_fps = 0, g_fps_window = 0;
static uint32_t g_page_switches = 0;

/* bouncing ball */
static int g_bx = 100, g_by = 150, g_vx = 3, g_vy = 2;
static uint32_t g_last_anim = 0;
static uint16_t g_border = Blue;

/* wave */
static int g_wave_col = 0;
static float g_wave_t = 0.0f;

/* ---- tiny string builders (line buffer max 20 chars) ---- */
static char lb[24];
static int lb_n;

static void lb_reset(void) { lb_n = 0; lb[0] = 0; }
static void lb_add(const char *s)
{
    while (*s && lb_n < 20) lb[lb_n++] = *s++;
    lb[lb_n] = 0;
}
static void lb_addi(int32_t v)
{
    char tmp[12];
    int i = 0, neg = v < 0;
    uint32_t u = neg ? (uint32_t)(-(int64_t)v) : (uint32_t)v;
    if (neg && lb_n < 20) lb[lb_n++] = '-';
    do { tmp[i++] = (char)('0' + (u % 10u)); u /= 10u; } while (u);
    while (i && lb_n < 20) lb[lb_n++] = tmp[--i];
    lb[lb_n] = 0;
}
static void lb_addf(float v, int frac)
{
    int32_t scale = 1;
    for (int i = 0; i < frac; i++) scale *= 10;
    int32_t s2 = (int32_t)(v * scale + (v < 0.0f ? -0.5f : 0.5f));
    int32_t ip = s2 / scale, fp = s2 % scale;
    if (fp < 0) fp = -fp;
    lb_addi(ip);
    if (lb_n < 20) lb[lb_n++] = '.';
    { int32_t p = scale / 10;
      while (p > 1 && fp < p) { if (lb_n < 20) lb[lb_n++] = '0'; p /= 10; } }
    lb_addi(fp < 0 ? -fp : fp);
}
static void lb_flush(u8 line)
{
    while (lb_n < 20) lb[lb_n++] = ' ';
    lb[20] = 0;
    LCD_DisplayStringLine(line, (u8 *)lb);
}

/* ---- page renderers ---- */

static void render_page0(void)
{
    lb_reset(); lb_add("UP="); lb_addi((int32_t)(g_ms_tick / 1000u));
    lb_add("s FPS="); lb_addi((int32_t)g_fps);
    lb_flush(Line0);
    lb_reset(); lb_add("TESTS "); lb_addi(t_pass); lb_add("/"); lb_addi(t_total);
    lb_add(t_pass == t_total ? " PASS" : " FAIL");
    lb_flush(Line1);
    lb_reset(); lb_add("HAL="); lb_addi((int32_t)efw_hal_count());
    lb_add(" COM="); lb_addi((int32_t)efw_comm_count_by_type(EFW_COMM_UART));
    lb_add(" SEN="); lb_addi((int32_t)efw_sensor_count());
    lb_flush(Line2);
    lb_reset(); lb_add("ACT="); lb_addi((int32_t)efw_actuator_count());
    lb_add(" ALG="); lb_addi((int32_t)efw_algo_count());
    lb_flush(Line3);
    lb_reset(); lb_add("MOD="); lb_addi((int32_t)efw_module_count());
    lb_add(" SM="); lb_addi((int32_t)efw_sm_count());
    lb_flush(Line4);
    lb_reset(); lb_add("BTN=");
    { uint8_t b = buttons_read();
      for (int i = 3; i >= 0; i--) lb_add((b >> i) & 1 ? "1" : "0"); }
    lb_flush(Line5);
    lb_reset(); lb_add("ERR="); lb_addi((int32_t)efw_diag_error_count());
    lb_add(" PGS="); lb_addi((int32_t)g_page_switches);
    lb_flush(Line6);
    lb_reset(); lb_add(g_pause ? "STATE=PAUSED " : "STATE=RUN    ");
    lb_add("B1 PG");
    lb_flush(Line7);
    lb_reset(); lb_add("B2 PAUSE B3 PC13");
    lb_flush(Line8);
    lb_reset(); lb_add("PAGE 0/2 EFW V.HW");
    lb_flush(Line9);
}

static void render_page1(void)
{
    lb_reset(); lb_add("STRESS RESULTS");
    lb_flush(Line0);
    lb_reset(); lb_add("PUB="); lb_addi((int32_t)g_stress.pub_ns); lb_add("ns x4");
    lb_flush(Line1);
    lb_reset(); lb_add("QUEUE="); lb_addi((int32_t)g_stress.queue_rt_ns); lb_add("ns/rt");
    lb_flush(Line2);
    lb_reset(); lb_add("PID="); lb_addi((int32_t)(g_stress.pid_ops_s / 1000)); lb_add(" kops/s");
    lb_flush(Line3);
    lb_reset(); lb_add("FUZZ="); lb_addi((int32_t)(g_stress.fuzz_ops / 1000)); lb_add("k bad=");
    lb_addi((int32_t)g_stress.fuzz_bad);
    lb_flush(Line4);
    lb_reset(); lb_add("LKP 3="); lb_addi((int32_t)(g_stress.lookup3_ns / 1000));
    lb_add("us 32="); lb_addi((int32_t)(g_stress.lookup32_ns / 1000)); lb_add("us");
    lb_flush(Line5);
    lb_reset(); lb_add("CAP S="); lb_addi((int32_t)g_stress.cap_sensor);
    lb_add(" H="); lb_addi((int32_t)g_stress.cap_hal);
    lb_flush(Line6);
    lb_reset(); lb_add("CAP A="); lb_addi((int32_t)g_stress.cap_actuator);
    lb_add(" G="); lb_addi((int32_t)g_stress.cap_algo);
    lb_flush(Line7);
    lb_reset(); lb_add("CAP M="); lb_addi((int32_t)g_stress.cap_module);
    lb_add(" SM="); lb_addi((int32_t)g_stress.cap_sm);
    lb_add(" K="); lb_addi((int32_t)g_stress.cap_sched);
    lb_flush(Line8);
    lb_reset(); lb_add("SOAK ERR="); lb_addi((int32_t)g_stress.soak_errors);
    lb_flush(Line9);
}

static void draw_wave_frame(void)
{
    /* plot region: rows 60..199 (x), columns 20..300 (y); axis row 130 */
    int col;
    for (col = 0; col < 140; col++) {
        float t = g_wave_t - (139 - col) * 0.05f;
        float s = 60.0f * __builtin_sinf(t);
        float p = 60.0f * __builtin_sinf(t) * 0.6f + 24.0f * __builtin_sinf(t * 0.37f);
        int r1 = 130 - (int)s;
        int len1 = (int)(s < 0 ? -s : s);
        if (len1 < 2) len1 = 2;
        LCD_FillArea((u8)(r1), (u16)(20 + col * 2), (u8)len1, 2, Green);
        int r2 = 130 - (int)p;
        LCD_FillArea((u8)(r2), (u16)(20 + col * 2), 2, 2, Yellow);
        int gap = r1 < r2 ? (r2 - r1 - len1) : (r1 - r2 - 2);
        (void)gap;
    }
    LCD_FillArea(130, 20, 1, 280, Grey);   /* axis */
}

static void render_page2(void)
{
    lb_reset(); lb_add("SINE + FILTER TRACE");
    lb_flush(Line0);
    lb_reset(); lb_add("t="); lb_addf(g_wave_t, 2);
    lb_add(" FPS="); lb_addi((int32_t)g_fps);
    lb_flush(Line1);
    lb_reset(); lb_add("B2="); lb_add(g_pause ? "HOLD" : "RUN ");
    lb_add(" B1 PG");
    lb_flush(Line9);
    if (!g_pause) {
        draw_wave_frame();
        g_wave_t += 0.05f;
        g_wave_col = (g_wave_col + 1) % 280;
    }
}

static void render_border(void)
{
    /* thin frame using FillArea on edges (240x320) */
    LCD_FillArea(0, 0, 3, 320, g_border);
    LCD_FillArea(237, 0, 3, 320, g_border);
    LCD_FillArea(0, 0, 240, 3, g_border);
    LCD_FillArea(0, 317, 240, 3, g_border);
}

static void anim_ball(void)
{
    /* erase + draw 16x16 ball in rows 40..230, cols 40..280 */
    LCD_FillArea((u8)g_by, (u16)g_bx, 14, 14, Black);
    if (!g_pause) {
        g_bx += g_vx; g_by += g_vy;
        if (g_bx < 40) { g_bx = 40; g_vx = -g_vx; }
        if (g_bx > 262) { g_bx = 262; g_vx = -g_vx; }
        if (g_by < 40) { g_by = 40; g_vy = -g_vy; }
        if (g_by > 214) { g_by = 214; g_vy = -g_vy; }
    }
    LCD_FillArea((u8)g_by, (u16)g_bx, 14, 14, Cyan);
}

/* ---- public ---- */

void ui_init(void)
{
    g_page = 0; g_pause = 0; g_frames = 0; g_fps = 0;
    LCD_Clear(Black);
    LCD_SetTextColor(White);
    LCD_SetBackColor(Black);
    render_border();
    render_page0();
    g_last_render = g_ms_tick;
}

void ui_task_1ms(void)
{
    uint8_t btn = buttons_read();
    uint8_t pressed = btn & ~g_last_btn;

    /* debounce: sample every 20ms */
    if ((g_ms_tick - g_deb_ms) >= 20) {
        g_deb_ms = g_ms_tick;
        if (pressed & 0x1) {                        /* B1: page */
            g_page = (g_page + 1) % 3;
            g_page_switches++;
            g_last_render = 0;                      /* force redraw */
            LCD_Clear(Black);
            render_border();
        }
        if (pressed & 0x2) g_pause = !g_pause;      /* B2 */
        if (pressed & 0x4) {                        /* B3: PC13 toggle */
#ifndef HOST_BUILD
            if (PC_ODR & (1u << 13)) buzzer_off(); else buzzer_on();
#endif
        }
        if (pressed & 0x8) {                        /* B4: border color */
            static const uint16_t cols[4] = { Blue, Red, Green, Yellow };
            static int ci = 0;
            ci = (ci + 1) % 4;
            g_border = cols[ci];
            render_border();
        }
        g_last_btn = btn;
    }

    /* animation at ~30ms */
    if ((g_ms_tick - g_last_anim) >= 30) {
        g_last_anim = g_ms_tick;
        if (g_page == 2) anim_ball();
    }

    /* frame render pacing */
    uint32_t period = (g_page == 2) ? 60u : 150u;
    if ((g_ms_tick - g_last_render) >= period) {
        g_last_render = g_ms_tick;
        g_frames++;
        if (g_page == 0) render_page0();
        else if (g_page == 1) render_page1();
        else render_page2();
    }

    /* fps accounting */
    static uint32_t fps_t0 = 0;
    if (fps_t0 == 0) fps_t0 = g_ms_tick;
    if ((g_ms_tick - fps_t0) >= 1000) {
        g_fps = g_frames;
        g_frames = 0;
        fps_t0 = g_ms_tick;
    }
}
