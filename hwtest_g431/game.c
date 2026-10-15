/* EFW Arcade — CT117E-M4 招新演示（中文界面 / Flappy / 最高分掉电保持）
 *
 * 运行在 EFW 框架上：调度器出帧、事件总线传按键、执行器层控 LED。
 * 菜单只保留"按B1开始 / 最高分"，游戏结束显示 得分/最高分/新纪录。
 *
 * 按键：B1 拍翅膀；B2 退回菜单。
 * 最高分存 TAMP 备份寄存器（复位不丢）。
 *
 * LCD_FillArea(x, y, h, w)：x=行(0..239), y=列(0..319), h=行高, w=列宽。
 */
#include <stdint.h>
#include <string.h>
#include "efw/efw.h"
#include "bsp.h"
#include "lcd.h"
#include "game.h"
#include "font_cn.h"

#define REG32X(a) (*(volatile uint32_t *)(a))

extern volatile uint32_t g_ms_tick;

/* ---------------- 中文文本渲染（UTF-8 → 字模） ---------------- */

static char lb[64];
static int lb_n;
static void lb_reset(void) { lb_n = 0; lb[0] = 0; }
static void lb_add(const char *s)
{ while (*s && lb_n < 60) lb[lb_n++] = *s++; lb[lb_n] = 0; }
static void lb_addi(int32_t v)
{
    char t[12]; int i = 0; uint32_t u;
    if (v < 0) { lb[lb_n++] = '-'; u = (uint32_t)(-(int64_t)v); }
    else u = (uint32_t)v;
    do { t[i++] = (char)('0' + (u % 10u)); u /= 10u; } while (u);
    while (i) lb[lb_n++] = t[--i];
    lb[lb_n] = 0;
}

/* 在 row..row+23 条带上画一个 24x24 中文字模（水平游程填充） */
static void draw_cn_glyph(u8 line, u16 col, int gi, u16 fg)
{
    const uint8_t *g = CN_Glyphs[gi];
    for (int r = 0; r < 24; r++) {
        int c = 0;
        while (c < 24) {
            if ((g[r * 3 + c / 8] >> (7 - (c % 8))) & 1) {
                int run = 1;
                while (c + run < 24 &&
                       ((g[r * 3 + (c + run) / 8] >> (7 - ((c + run) % 8))) & 1))
                    run++;
                LCD_FillArea((u8)(line + r), (u16)(col + c), 1, (u16)run, fg);
                c += run;
            } else c++;
        }
    }
}

/* 整行清空后居中渲染 UTF-8 混排文本（中文 24x24，ASCII 16x24） */
static void text_cn_line(u8 line, const char *s)
{
    LCD_FillArea(line, 0, 24, 320, Black);
    u16 W = 0;
    for (const uint8_t *p = (const uint8_t *)s; *p; ) {
        if (*p < 0x80) { W += 16; p++; }
        else { W += 24; p += 3; }
    }
    if (W > 320) W = 320;
    u16 col_right = (u16)(319 - (320 - W) / 2);   /* 居中起始（最高列=视觉左端） */
    const uint8_t *p = (const uint8_t *)s;
    while (*p) {
        if (*p < 0x80) {                          /* ASCII */
            if (col_right < 15) break;
            LCD_DisplayChar(line, col_right, *p);
            col_right -= 16; p++;
        } else if ((*p & 0xE0) == 0xE0 && col_right >= 24) {   /* 3 字节 UTF-8 → 中文 */
            uint32_t cp = ((*p & 0x0F) << 12) | ((p[1] & 0x3F) << 6) | (p[2] & 0x3F);
            p += 3;
            int gi = -1;
            for (int i = 0; i < CN_GLYPH_N; i++)
                if (CN_CP[i] == cp) { gi = i; break; }
            if (gi >= 0) { draw_cn_glyph(line, col_right - 23, gi, White); col_right -= 24; }
        } else p++;
    }
}

static void text_cn_center(u8 line, const char *s)
{
    text_cn_line(line, s);
}

/* ---------------- 备份寄存器最高分 ---------------- */
#define TAMP_BKP0 (0x40002400u + 0x100u)
#define TAMP_BKP1 (0x40002400u + 0x104u)

static void bkp_unlock(void)
{
    REG32X(0x40021058u) |= (1u << 28) | (1u << 10);  /* PWREN + RTCAPBEN */
    REG32X(0x40007000u) |= (1u << 8);    /* PWR_CR1 DBP */
    __asm volatile ("dsb" ::: "memory");
    outs("[BKP] unlock: APB1ENR1="); outx(REG32X(0x40021058u));
    outs(" PWR="); outx(REG32X(0x40007000u)); outs("\r\n");
}

static uint32_t hiscore_get(int slot)
{
#ifdef HOST_BUILD
    (void)slot; return 0;
#else
    uint32_t v = REG32X(slot == 0 ? TAMP_BKP0 : TAMP_BKP1);
    if (v > 9999u) v = 0;
    return v;
#endif
}

static void hiscore_set(int slot, uint32_t v)
{
#ifndef HOST_BUILD
    bkp_unlock();
    REG32X(slot == 0 ? TAMP_BKP0 : TAMP_BKP1) = v;
#else
    (void)slot; (void)v;
#endif
}

/* ---------------- 按键：EFW 事件总线 ---------------- */
#define TOPIC_BTN 100
static volatile uint8_t g_btn_edge;

static void btn_topic_cb(uint16_t id, const void *data, uint16_t size, void *user)
{
    (void)id; (void)user;
    if (data && size >= 1) g_btn_edge |= *(const uint8_t *)data;
}

static efw_status_t input_task(void *ctx)
{
    static uint8_t last = 0;
    (void)ctx;
    uint8_t b = buttons_read();
    uint8_t edge = (uint8_t)(b & (uint8_t)~last);
    last = b;
    if (edge) efw_topic_publish(TOPIC_BTN, &edge, 1);
    return EFW_OK;
}

static int g_mode;                       /* 0=菜单 1=游戏 */
static int g_menu_dirty = 1;
static int g_attract = 0;                /* QA: 机器人自动试玩 */

static efw_status_t led_idle_task(void *ctx)
{
    static uint8_t pat = 0x01; static int dir = 1;
    (void)ctx;
    if (g_mode == 1) return EFW_OK;      /* 游戏中 LED 表示分数 */
    led_write(pat);
    if (dir) { pat = (uint8_t)(pat << 1); if (pat == 0x80) dir = 0; }
    else     { pat = (uint8_t)(pat >> 1); if (pat == 0x01) dir = 1; }
    return EFW_OK;
}

/* ---------------- 文本行辅助 ---------------- */

static void sched_spin_small(void)
{
    static uint32_t last = 0;
    uint32_t now = g_ms_tick;
    if (now != last) { efw_scheduler_tick(now - last); last = now; }
}

static uint8_t wait_edge(uint8_t mask)
{
    for (;;) {
        bsp_loop_hook();
        sched_spin_small();
        efw_event_queue_process();
        if (g_btn_edge & mask) {
            uint8_t e = g_btn_edge;
            g_btn_edge = 0;
            return e;
        }
    }
}

/* ================= flappy ================= */
#define F_GRAV      0.55f
#define F_FLAP     (-4.2f)
#define F_VMAX      6.0f
#define F_BIRD_X    54
#define F_PIPE_W    36
#define F_GAP       82
#define F_GROUND    210   /* 屏幕纵向只有 0..239 行！地面=底部 30px 区域 */

static int f_by, f_score, f_dead, f_speed, f_started;
static uint32_t f_frame;
static float f_vel;
static int f_pipe_x[2], f_gap_y[2];

static void pipe_draw_at(int x, int gap_y, u16 color)
{
    if (x > 239) return;
    int cx = x, w = F_PIPE_W;
    if (cx < 0) { w += cx; cx = 0; }              /* clip left */
    if (w <= 0) return;

    if (color == Black) {                         /* 擦除：覆盖含管口加宽部分 */
        int ex = x, ew = F_PIPE_W;
        if (ex < 0) { ew += ex; ex = 0; }
        ex -= 2; ew += 4;
        if (ex < 0) { ew += ex; ex = 0; }
        if (ew > 0) {
            LCD_FillArea(0, (u16)ex, (u8)gap_y, (u16)ew, Black);
            LCD_FillArea((u8)(gap_y + F_GAP), (u16)ex,
                         (u8)(F_GROUND - gap_y - F_GAP), (u16)ew, Black);
        }
        return;
    }

    /* 管身：底色 + 左暗 + 右高光（立体感） */
    LCD_FillArea(0, (u16)cx, (u8)gap_y, (u16)w, 0x0660);
    LCD_FillArea(0, (u16)cx, (u8)gap_y, 3, 0x0280);
    LCD_FillArea(0, (u16)(cx + w - 6), (u8)gap_y, 3, 0x0BE0);
    LCD_FillArea((u8)(gap_y + F_GAP), (u16)cx,
                 (u8)(F_GROUND - gap_y - F_GAP), (u16)w, 0x0660);
    LCD_FillArea((u8)(gap_y + F_GAP), (u16)cx,
                 (u8)(F_GROUND - gap_y - F_GAP), 3, 0x0280);
    LCD_FillArea((u8)(gap_y + F_GAP), (u16)(cx + w - 6),
                 (u8)(F_GROUND - gap_y - F_GAP), 3, 0x0BE0);

    /* 管口：比管身宽 4px（两侧各挑出 2px），白边收口 */
    int capx = cx - 2, capw = w + 4;
    if (capx < 0) { capw += capx; capx = 0; }
    if (capw > 0) {
        int ty0 = gap_y - 6; if (ty0 < 0) ty0 = 0;
        LCD_FillArea((u8)ty0, (u16)capx, (u8)(gap_y - ty0), (u16)capw, 0x0660);
        LCD_FillArea((u8)(gap_y - 2), (u16)capx, 2, (u16)capw, White);
        int by0 = gap_y + F_GAP;
        LCD_FillArea((u8)by0, (u16)capx, 6, (u16)capw, 0x0660);
        LCD_FillArea((u8)by0, (u16)capx, 2, (u16)capw, White);
    }
}

static void pipe_draw(int i, u16 color) { pipe_draw_at(f_pipe_x[i], f_gap_y[i], color); }

static void flappy_reset(void)
{
    f_by = 140; f_vel = 0; f_score = 0; f_dead = 0; f_frame = 0; f_speed = 2;
    f_started = 0;
    f_pipe_x[0] = 240;       f_gap_y[0] = 40 + (int)((dwt_cycles() >> 3) % 88u);
    f_pipe_x[1] = 240 + 130; f_gap_y[1] = 40 + (int)((dwt_cycles() >> 5) % 88u);
    LCD_Clear(Black);
    LCD_FillArea((u8)F_GROUND, 0, 3, 320, White);
}

static void flappy_gameover(void)
{
    LCD_FillArea(0, 0, 240, 320, White);
    led_write(0xFF);
    delay_ms(120);
    LCD_Clear(Black);
    led_write(0);
    int best = (int)hiscore_get(0);
    int nb = f_score > best;
    if (nb) hiscore_set(0, (uint32_t)f_score);

    text_cn_line(Line1, "游戏结束");
    lb_reset(); lb_add("得分:"); lb_addi(f_score); text_cn_line(Line3, lb);
    lb_reset(); lb_add("最高分:"); lb_addi(nb ? f_score : best); text_cn_line(Line4, lb);
    if (nb) text_cn_line(Line5, "新纪录!");
    text_cn_line(Line7, "按B1再来");
    text_cn_line(Line8, "按B2回菜单");
    outs("[ARCADE] flappy over score="); outi(f_score);
    outs(" best="); outi(nb ? f_score : best); outs("\r\n");

    for (;;) {
        uint8_t e = wait_edge(0x3);
        if (e & 0x1) { flappy_reset(); f_dead = 0; return; }
        if (e & 0x2) { f_dead = 0; g_mode = 0; g_menu_dirty = 1; return; }
    }
}

static void flappy_frame(void)
{
    f_frame++;

    if (!f_started) {                     /* 准备起跳：悬停 */
        if (g_btn_edge & 0x1) {
            g_btn_edge &= (uint8_t)~0x1;
            f_started = 1;
            f_vel = F_FLAP;
            LCD_FillArea((u8)Line4, 0, 24, 320, Black);   /* 清除"按B1起飞" */
            return;                                       /* 本帧结束，防止重绘 */
        }
        if ((f_frame & 16u)) text_cn_line(Line4, "按B1起飞");
        else                 text_cn_line(Line4, "        ");
        for (int i = 0; i < 2; i++) pipe_draw(i, Green);
        LCD_FillArea((u8)f_by, F_BIRD_X, 9, 12, Yellow);
        LCD_FillArea((u8)(f_by + 1), F_BIRD_X + 8, 2, 3, White);
        return;
    }

    f_vel += F_GRAV;
    if (f_vel > F_VMAX) f_vel = F_VMAX;
    int old_by = f_by;
    f_by = (int)(f_by + f_vel);

    if (g_btn_edge & 0x1) {
        g_btn_edge &= (uint8_t)~0x1;
        f_vel = F_FLAP;
    }

    if (f_by < 0) { f_by = 0; f_vel = 0; }
    if (f_by > F_GROUND - 10) f_dead = 1;
    if (g_btn_edge & 0x2) {                          /* B2 退出到菜单 */
        g_btn_edge &= (uint8_t)~0x2;
        f_dead = 2;
    }

    int old_x0 = f_pipe_x[0], old_g0 = f_gap_y[0];
    int old_x1 = f_pipe_x[1], old_g1 = f_gap_y[1];
    for (int i = 0; i < 2; i++) {
        int old = f_pipe_x[i];
        f_pipe_x[i] -= f_speed;
        if (f_pipe_x[i] < -F_PIPE_W) {
            f_pipe_x[i] = 280;
            f_gap_y[i] = 40 + (int)((dwt_cycles() >> (4 + i)) % 88u);
        }
        if (!f_dead && old + F_PIPE_W >= F_BIRD_X + 12 &&
            f_pipe_x[i] + F_PIPE_W < F_BIRD_X + 12) {
            f_score++;
            if (g_attract) {
                outs("[BOT] pass score="); outi(f_score); outs("\r\n");
            }
        }
        if (!f_dead && f_pipe_x[i] < F_BIRD_X + 12 && f_pipe_x[i] + F_PIPE_W > F_BIRD_X) {
            if (f_by < f_gap_y[i] || f_by + 9 > f_gap_y[i] + F_GAP) f_dead = 1;
        }
    }
    if (f_score && f_score % 5 == 0) {
        f_speed = 2 + f_score / 10;
        if (f_speed > 5) f_speed = 5;
    }

    /* 渲染：擦旧位置 → 画新位置 */
    pipe_draw_at(old_x0, old_g0, Black);
    pipe_draw_at(old_x1, old_g1, Black);
    LCD_FillArea((u8)old_by, F_BIRD_X, 10, 14, Black);
    for (int i = 0; i < 2; i++) pipe_draw(i, Green);
    {
        int y = f_by;
        LCD_FillArea((u8)y, F_BIRD_X, 9, 12, Yellow);
        LCD_FillArea((u8)(y + 7), F_BIRD_X + 1, 2, 10, 0xFD20);  /* 腹部 */
        LCD_FillArea((u8)(y + 1), F_BIRD_X + 8, 2, 3, White);    /* 眼白 */
        LCD_FillArea((u8)(y + 2), F_BIRD_X + 9, 1, 1, Black);    /* 瞳孔 */
        LCD_FillArea((u8)(y + 3), F_BIRD_X + 11, 2, 2, Red);     /* 喙 */
        if (f_frame & 2) LCD_FillArea((u8)(y + 1), F_BIRD_X + 2, 3, 5, 0xD200);
        else             LCD_FillArea((u8)(y + 5), F_BIRD_X + 2, 3, 5, 0xD200);
    }
    {
        static int off = 0;
        off = (off + f_speed) % 16;
        LCD_FillArea((u8)F_GROUND, 0, 4, 320, 0x0660);          /* 草皮 4px */
        LCD_FillArea((u8)(F_GROUND + 4), 0, 26, 320, 0x5268);   /* 土层 26px（到 239 行） */
        for (int x = -off; x < 240; x += 16) {
            int cx = x < 0 ? 0 : x;
            LCD_FillArea((u8)(F_GROUND + 10), (u16)cx, 3, (u16)(16 + x - cx), White);
        }
    }
    led_write((uint8_t)(0xFFu >> (8 - (f_score % 9))));

    if (f_dead == 1) { flappy_gameover(); return; }
    if (f_dead == 2) { f_dead = 0; g_mode = 0; g_menu_dirty = 1; }
}

/* ================= 菜单 ================= */

static void menu_frame(uint32_t frame)
{
    /* 静态内容只在画面脏时画一次（反复清空重画会造成可见闪烁） */
    if (g_menu_dirty) {
        LCD_Clear(Black);
        text_cn_line(Line2, "按B1开始");
        lb_reset(); lb_add("最高分:"); lb_addi((int32_t)hiscore_get(0));
        text_cn_line(Line4, lb);
        g_menu_dirty = 0;
    }
    /* 闪烁行独立刷新 */
    if (frame & 16u) text_cn_line(Line6, "按B1");
    else             text_cn_line(Line6, "     ");
}

/* ================= 主循环 ================= */

void arcade_run(int qa_attract)
{
    bkp_unlock();
    efw_topic_subscribe(TOPIC_BTN, btn_topic_cb, 0);
    static efw_scheduler_task_def_t t_in  = { "arc_in",  10, input_task,    0 };
    static efw_scheduler_task_def_t t_led = { "arc_led", 60,  led_idle_task, 0 };
    efw_scheduler_register(&t_in);
    efw_scheduler_register(&t_led);
    OUTLN("[ARCADE] booted, menu up");
    /* BKP 持久化自检：BKP1 作启动计数器，跨复位递增 = 读写链路完好 */
    bkp_unlock();
    uint32_t boots = hiscore_get(1);
    hiscore_set(1, boots + 1u);
    uint32_t rd = hiscore_get(1);
    outs("[BKP] boot# "); outi((int32_t)rd);
    outs(rd == boots + 1u ? " (persist OK)\r\n" : " (FAIL!)\r\n");
    outs("[BKP] APB1ENR1="); outx(REG32X(0x40021058u));
    outs(" PWR_CR1="); outx(REG32X(0x40007000u));
    outs(" TAMP_CR="); outx(REG32X(0x40002400u));
    outs(" BKP0="); outx(REG32X(0x40002500u));
    outs(" BKP1="); outx(REG32X(0x40002504u)); outs("\r\n");
    /* 二次验证：重新解锁+写 BKP1=0x5A5A，立即回读 */
    bkp_unlock();
    REG32X(0x40002504u) = 0x5A5Au;
    outs("[BKP] rewrite BKP1="); outx(REG32X(0x40002504u));
    outs(" APB1ENR1="); outx(REG32X(0x40021058u)); outs("\r\n");
    outs("[ARCADE] hiscore readback = "); outi((int32_t)hiscore_get(0));
    outs(" / "); outi((int32_t)hiscore_get(1)); outs("\r\n");
    if (qa_attract) {                                 /* QA: 机器人自动试玩 */
        outs("[BOT] QA attract engage\r\n");
        g_attract = 1; g_mode = 1;
        flappy_reset();
    }

    uint32_t frame = 0, last_ms = 0;
    if (!g_attract) g_mode = 0;
    for (;;) {
        bsp_loop_hook();
        sched_spin_small();
        efw_event_queue_process();
        if (g_ms_tick == last_ms) continue;
        last_ms = g_ms_tick;
        frame++;
        if (g_mode == 0) {
            if ((frame % 33) == 0) menu_frame(frame);
            if (g_btn_edge & 0x1) {
                g_btn_edge = 0; g_mode = 1;
                outs("[ARCADE] start flappy\r\n");
                flappy_reset();
            }
        } else {
            if ((frame % 33) == 0) flappy_frame();
        }
    }
}
