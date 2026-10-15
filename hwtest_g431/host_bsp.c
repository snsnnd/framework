/* Host-native build shim for the EFW hwtest suite.
 * Compiles the SAME tests.c/stress.c/dashboard.c on x86 with stubbed BSP/LCD
 * so the EFW logic runs natively for behavioral comparison against the MCU.
 * Windows/Linux: real monotonic clock drives g_ms_tick and dwt_us().
 */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#include "bsp.h"
#include "lcd.h"

volatile uint32_t g_ms_tick = 0;

__attribute__((constructor)) static void host_stdout_init(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);   /* survive timeout-kill with output intact */
}

static uint64_t t0_us;
static int t0_ok;

static uint64_t now_us(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000ull + (uint64_t)ts.tv_nsec / 1000ull;
}

static void host_time_update(void)
{
    if (!t0_ok) { t0_us = now_us(); t0_ok = 1; }
    uint64_t e = now_us() - t0_us;
    uint32_t ms = (uint32_t)(e / 1000ull);
    if (ms > g_ms_tick) g_ms_tick = ms;
}

/* ---- bsp.h API ---- */
void bsp_systick_init(void) { host_time_update(); }
void bsp_dwt_init(void)     { host_time_update(); }
void bsp_loop_hook(void)    { host_time_update(); }
uint32_t dwt_us(void)       { host_time_update(); return (uint32_t)((now_us() - t0_us) & 0xFFFFFFFFull); }
uint32_t dwt_cycles(void)   { return dwt_us() * 16u; }   /* virtual 16MHz */

void delay_ms(uint32_t ms)
{
    uint32_t start = g_ms_tick;
    while ((uint32_t)(g_ms_tick - start) < ms) {
        struct timespec ts = { 0, 200000 };  /* 0.2ms nap */
        nanosleep(&ts, 0);
        host_time_update();
    }
}

void bsp_gpio_init(void) {}
void bsp_uart_init(void) {}
uint32_t bsp_sysclk_mhz(void) { return 80u; }
void bsp_clock_boost(void)    { }
int bsp_clock_boost_to(uint32_t mhz, uint32_t ws) { (void)mhz; (void)ws; return 0; }
void bsp_stack_paint(void)    { }
void led_write(uint8_t m)  { (void)m; }
void led_off_all(void)     { }
uint8_t buttons_read(void) { return 0; }
void buzzer_on(void)       { }
void buzzer_off(void)      { }
uint32_t dbg_idcode(void)  { return 0x20026468u; }  /* same as real G431 */

/* ---- console (same formatting as MCU bsp.c) ---- */
void outc(char c) { fputc(c, stdout); }

void outs(const char *s) { if (s) while (*s) outc(*s++); }

void outi(int32_t v)
{
    char buf[12];
    int i = 0;
    uint32_t u;
    if (v < 0) { outc('-'); u = (uint32_t)(-(int64_t)v); }
    else u = (uint32_t)v;
    do { buf[i++] = (char)('0' + (u % 10u)); u /= 10u; } while (u);
    while (i) outc(buf[--i]);
}

void outx(uint32_t v)
{
    static const char hex[] = "0123456789ABCDEF";
    for (int i = 7; i >= 0; i--) outc(hex[(v >> (i * 4)) & 0xFu]);
}

void outf(float v, int frac)
{
    int32_t scale = 1;
    for (int i = 0; i < frac; i++) scale *= 10;
    int32_t s = (int32_t)(v * scale + (v < 0.0f ? -0.5f : 0.5f));
    int32_t ip = s / scale, fp = s % scale;
    if (fp < 0) fp = -fp;
    outi(ip);
    outc('.');
    int32_t p = scale / 10;
    while (p > 1 && fp < p) { outc('0'); p /= 10; }
    outi(fp);
}

/* ---- LCD stubs (headless; logic still exercised) ---- */
u16  LCD_ReadID(void) { return 0x9325u; }
void LCD_Init(void) {}
void LCD_SetTextColor(u16 c) { (void)c; }
void LCD_SetBackColor(u16 c) { (void)c; }
void LCD_ClearLine(u8 l) { (void)l; }
void LCD_Clear(u16 c) { (void)c; }
void LCD_SetCursor(u8 x, u16 y) { (void)x; (void)y; }
void LCD_DisplayChar(u8 l, u16 c, u8 a) { (void)l; (void)c; (void)a; }
void LCD_DisplayStringLine(u8 l, u8 *p) { (void)l; (void)p; }
void LCD_SetDisplayWindow(u8 x, u16 y, u8 h, u16 w) { (void)x; (void)y; (void)h; (void)w; }
void LCD_WindowModeDisable(void) {}
void LCD_DrawLine(u8 x, u16 y, u16 len, u8 dir) { (void)x; (void)y; (void)len; (void)dir; }
void LCD_DrawRect(u8 x, u16 y, u8 h, u16 w) { (void)x; (void)y; (void)h; (void)w; }
void LCD_DrawCircle(u8 x, u16 y, u16 r) { (void)x; (void)y; (void)r; }
void LCD_WriteReg(u8 r, u16 v) { (void)r; (void)v; }
u16  LCD_ReadReg(u8 r) { (void)r; return 0x9325u; }
void LCD_WriteRAM_Prepare(void) {}
void LCD_WriteRAM(u16 c) { (void)c; }
void LCD_CtrlLinesConfig(void) {}
void LCD_BusIn(void) {}
void LCD_BusOut(void) {}
void LCD_FillArea(u8 x, u16 y, u8 h, u16 w, u16 color)
{ (void)x; (void)y; (void)h; (void)w; (void)color; }
