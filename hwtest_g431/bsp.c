/* EFW hwtest BSP for CT117E-M4 (Lanqiao Cup, STM32G431RBT6)
 *
 * Board facts (蓝桥杯嵌入式竞赛板 CT117E-M4):
 *   LEDs    PC8..PC15, active LOW, latched by 74HC573 on PD2 (LE high pulse)
 *   Buttons B1=PB0, B2=PB1, B3=PB2, B4=PA0 (pressed = low, pull-ups)
 *   Buzzer  PA8 = TIM1_CH1 (AF6), passive buzzer -> 2kHz PWM
 *   USART1  PA9(TX)/PA10(RX) AF7 -> board USB-232 / DAPLink UART passthrough
 *
 * Clock: HSI16, no PLL -> SYSCLK=AHB=APB1=APB2=16MHz. USART BRR=139 (115200).
 * Timing: SysTick 1ms + DWT cycle counter (us).
 *
 * Console output is broadcast on USART1/2/3 so the test works regardless of
 * which UART the DAPLink dongle is wired to.
 */
#include <stdint.h>
#include "bsp.h"

/* ---------------- register shorthands ---------------- */
#define REG32(a) (*(volatile uint32_t *)(a))

/* G4 RCC layout (RM0440): AHB2ENR@0x4C, APB1ENR1@0x58, APB1ENR2@0x5C, APB2ENR@0x60 */
#define RCC_BASE     0x40021000u
#define RCC_AHB2ENR  REG32(RCC_BASE + 0x4Cu)
#define RCC_APB1ENR1 REG32(RCC_BASE + 0x58u)
#define RCC_APB2ENR  REG32(RCC_BASE + 0x60u)

#define GPIOA_BASE   0x48000000u
#define GPIOB_BASE   0x48000400u
#define GPIOC_BASE   0x48000800u
#define GPIOD_BASE   0x48000C00u
#define GPIO_MODER(g) REG32((g) + 0x00u)
#define GPIO_PUPDR(g) REG32((g) + 0x0Cu)
#define GPIO_IDR(g)   REG32((g) + 0x10u)
#define GPIO_ODR(g)   REG32((g) + 0x14u)
#define GPIO_BSRR(g)  REG32((g) + 0x18u)
#define GPIO_AFRL(g)  REG32((g) + 0x20u)
#define GPIO_AFRH(g)  REG32((g) + 0x24u)

/* STM32G4 USART is the new-generation layout (differs from F1/F4!):
 * CR1@0x00 CR2@0x04 CR3@0x08 BRR@0x0C ... ISR@0x1C ICR@0x20 RDR@0x24 TDR@0x28 */
#define USART1_BASE  0x40013800u
#define USART2_BASE  0x40004400u
#define USART3_BASE  0x40004800u
#define USART_CR1(u)  REG32((u) + 0x00u)
#define USART_BRR(u)  REG32((u) + 0x0Cu)
#define USART_ISR(u)  REG32((u) + 0x1Cu)
#define USART_TDR(u)  REG32((u) + 0x28u)
#define USART_ISR_TXE (1u << 7)

#define TIM1_BASE    0x40012C00u
#define TIM1_CR1     REG32(TIM1_BASE + 0x00u)
#define TIM1_PSC     REG32(TIM1_BASE + 0x28u)
#define TIM1_ARR     REG32(TIM1_BASE + 0x2Cu)
#define TIM1_CCR1    REG32(TIM1_BASE + 0x34u)
#define TIM1_CCER    REG32(TIM1_BASE + 0x20u)
#define TIM1_BDTR    REG32(TIM1_BASE + 0x44u)

#define SYST_CSR     REG32(0xE000E010u)
#define SYST_RVR     REG32(0xE000E014u)
#define SYST_CVR     REG32(0xE000E018u)
#define DEMCR        REG32(0xE000EDFCu)
#define DWT_CTRL     REG32(0xE0001000u)
#define DWT_CYCCNT   REG32(0xE0001004u)

/* ---------------- clock / time ---------------- */

static void uart_init(uint32_t base);   /* forward: clock boost re-inits UARTs */

static uint32_t g_sysclk_mhz = 16u;
uint32_t bsp_sysclk_mhz(void) { return g_sysclk_mhz; }

void bsp_systick_init(void)
{
    SYST_RVR = g_sysclk_mhz * 1000u - 1u;  /* sysclk/1000 = 1kHz */
    SYST_CVR = 0;
    SYST_CSR = 7u;                         /* ENABLE | TICKINT | CLKSOURCE */
}

void bsp_dwt_init(void)
{
    DEMCR |= (1u << 24);                 /* TRCENA */
    DWT_CYCCNT = 0;
    DWT_CTRL |= 1u;                      /* CYCCNTENA */
}

uint32_t dwt_cycles(void) { return DWT_CYCCNT; }
uint32_t dwt_us(void)     { return DWT_CYCCNT / g_sysclk_mhz; }

int bsp_clock_boost_to(uint32_t target_mhz, uint32_t flash_ws)
{
    /* PLL from HSI16: fin=16/M, vco=fin*N=target*R; auto-solve M/N/R within
     * spec (VCO 96-344MHz, N 8-127), switch, verify. 0 = failure (16MHz kept). */
    #define RCC_CR      REG32(RCC_BASE + 0x00u)
    #define RCC_CFGR    REG32(RCC_BASE + 0x08u)
    #define RCC_PLLCFGR REG32(RCC_BASE + 0x0Cu)
    #define FLASH_ACR   REG32(0x40022000u)

    /* fast path: already running at the target frequency on PLL */
    if (target_mhz == g_sysclk_mhz && ((RCC_CFGR & (3u << 2)) == (3u << 2))) {
        return 1;
    }

    uint32_t cfg_m = 0, cfg_n = 0, cfg_r = 0;
    int found = 0;
    for (uint32_t M = 2; M <= 6 && !found; M++) {
        uint32_t fin = 16u / M;
        if (fin == 0) continue;
        for (uint32_t R = 2; R <= 8; R += 2) {
            uint32_t vco = target_mhz * R;
            if (vco < 96u || vco > 344u) continue;
            if (vco % fin) continue;
            uint32_t N = vco / fin;
            if (N < 8u || N > 127u) continue;
            cfg_m = M; cfg_n = N; cfg_r = R;
            found = 1; break;
        }
    }
    if (!found) return 0;
    if (flash_ws > 4u) return 0;

    /* 0) 时钟净化：上游（如 Keil flash 算法）可能留下 HSE 时钟 + HSI 已关的
     *    状态且不复位 RCC。先把 HSI 拉起来，从已知状态开始。
     *    G4 位布局（RM0440）：HSION=bit8, HSIRDY=bit10（不是 F1 风格的 0/2！）*/
    RCC_CR |= (1u << 8);                             /* HSION */
    uint32_t hsi_guard = 2000000u;
    while (((RCC_CR & (1u << 10)) == 0u) && --hsi_guard) { }   /* wait HSIRDY */
    if ((RCC_CR & (1u << 10)) == 0u) {               /* HSI dead: dump state */
        outs("[CLK] HSI dead: CR="); outx(RCC_CR);
        outs(" CFGR="); outx(RCC_CFGR); outs("\r\n");
        return 0;
    }

    /* 1) 强制先切到 HSI（G4: SW=00, SWS=01 表示 HSI）；DSB + 最多 3 次重试 */
    int hsi_ok = 0;
    for (int attempt = 0; attempt < 3 && !hsi_ok; attempt++) {
        RCC_CFGR = (RCC_CFGR & ~3u) | 0u;
        __asm volatile ("dsb" ::: "memory");
        uint32_t sw_guard = 500000u;
        while (((RCC_CFGR & (3u << 2)) != (1u << 2)) && --sw_guard) { }
        if ((RCC_CFGR & (3u << 2)) == (1u << 2)) hsi_ok = 1;
    }
    if (!hsi_ok) {
        outs("[CLK] cannot switch to HSI: CFGR="); outx(RCC_CFGR); outs("\r\n");
        return 0;
    }

    RCC_CR &= ~(1u << 24);                           /* PLL off */
    uint32_t guard = 2000000u;
    while ((RCC_CR & (1u << 25)) && --guard) { }

    RCC_PLLCFGR = (2u << 0)                          /* PLLSRC = HSI16 */
                | ((cfg_m - 1u) << 4)                /* PLLM = /M */
                | (cfg_n << 8)                       /* PLLN xN */
                | (0u << 17)                         /* PLLP = /7 (unused) */
                | (1u << 21)                         /* PLLQ = /4 (unused) */
                | ((cfg_r / 2u - 1u) << 25)          /* PLLR = /R */
                | (1u << 24);                        /* PLLREN: R output enable */

    RCC_CR |= (1u << 24);                            /* PLL on */
    guard = 2000000u;
    while (((RCC_CR & (1u << 25)) == 0u) && --guard) { }
    if ((RCC_CR & (1u << 25)) == 0u) {
        outs("[CLK] PLL no lock: CR="); outx(RCC_CR);
        outs(" PLLCFGR="); outx(RCC_PLLCFGR); outs("\r\n");
        return 0;                                    /* no lock */
    }

    FLASH_ACR = (flash_ws & 7u) | (1u << 8);         /* latency + prefetch */

    RCC_CFGR = (RCC_CFGR & ~3u) | 3u;                /* SW = PLL (G4: 11=PLL!) */
    guard = 2000000u;
    while (((RCC_CFGR & (3u << 2)) != (3u << 2)) && --guard) { }   /* SWS=PLL */
    if ((RCC_CFGR & (3u << 2)) != (3u << 2)) {
        outs("[CLK] no switch: CR="); outx(RCC_CR);
        outs(" CFGR="); outx(RCC_CFGR);
        outs(" PLLCFGR="); outx(RCC_PLLCFGR); outs("\r\n");
        return 0;
    }

    g_sysclk_mhz = target_mhz;
    bsp_systick_init();                              /* 1ms @ new clock */
    uart_init(USART1_BASE);                          /* recompute BRR */
    uart_init(USART2_BASE);
    uart_init(USART3_BASE);
    outs("[CLK] boost ok: "); outi((int32_t)target_mhz); outs("MHz\r\n");
    return 1;
}

void bsp_clock_boost(void)
{
    bsp_clock_boost_to(80u, 2u);
}

void delay_ms(uint32_t ms)
{
    uint32_t start = g_ms_tick;
    while ((g_ms_tick - start) < ms) { }
}

void bsp_loop_hook(void)
{
    /* MCU builds: nothing to do, SysTick ISR advances g_ms_tick */
}

/* ---------------- GPIO: LEDs / buttons / buzzer ---------------- */

/* PC13 probe helper (candidate backlight line on CT117E-M4) */
static void pc13_out(void)
{
    uint32_t g = 0x48000800u;                    /* GPIOC */
    uint32_t m = REG32(g);
    m &= ~(3u << 26);                            /* PC13 mode bits 26-27 */
    m |=  (1u << 26);                            /* output */
    REG32(g) = m;
}

static void pin_out(uint32_t g, int pin)
{
    GPIO_MODER(g) &= ~(3u << (pin * 2));
    GPIO_MODER(g) |=  (1u << (pin * 2));     /* output */
}
static void pin_af(uint32_t g, int pin, int af)
{
    GPIO_MODER(g) &= ~(3u << (pin * 2));
    GPIO_MODER(g) |=  (2u << (pin * 2));     /* alternate */
    if (pin < 8) {
        GPIO_AFRL(g) &= ~(0xFu << (pin * 4));
        GPIO_AFRL(g) |=  ((uint32_t)af << (pin * 4));
    } else {
        int p = pin - 8;
        GPIO_AFRH(g) &= ~(0xFu << (p * 4));
        GPIO_AFRH(g) |=  ((uint32_t)af << (p * 4));
    }
}
static void pin_in_pu(uint32_t g, int pin)
{
    GPIO_MODER(g) &= ~(3u << (pin * 2));     /* input */
    GPIO_PUPDR(g) &= ~(3u << (pin * 2));
    GPIO_PUPDR(g) |=  (1u << (pin * 2));     /* pull-up */
}

void bsp_gpio_init(void)
{
    RCC_AHB2ENR |= (1u << 0) | (1u << 1) | (1u << 2) | (1u << 3); /* A/B/C/D */

    for (int p = 8; p <= 15; p++) pin_out(GPIOC_BASE, p);   /* LEDs */
    pin_out(GPIOD_BASE, 2);                                 /* latch LE */
    pc13_out();                                             /* PC13: backlight probe */

    pin_in_pu(GPIOB_BASE, 0);
    pin_in_pu(GPIOB_BASE, 1);
    pin_in_pu(GPIOB_BASE, 2);
    pin_in_pu(GPIOA_BASE, 0);

    led_off_all();                                          /* latch LEDs off */

    /* NOTE: PA8 is LCD_nRD on CT117E-M4 (confirmed by 4T HAL_06_LCD.ioc) —
     * it must stay a plain GPIO for the LCD driver. No TIM1 PWM here. */
}

void led_write(uint8_t m)
{
    uint32_t odr = GPIO_ODR(GPIOC_BASE) & ~(0xFFu << 8);
    odr |= ((uint32_t)(~m & 0xFFu)) << 8;                   /* active low */
    GPIO_ODR(GPIOC_BASE) = odr;
    GPIO_BSRR(GPIOD_BASE) = (1u << 2);                      /* latch: LE high */
    for (volatile int i = 0; i < 40; i++) { }
    GPIO_BSRR(GPIOD_BASE) = (1u << (2 + 16));               /* LE low */
}

void led_off_all(void) { led_write(0x00); }

uint8_t buttons_read(void)
{
    uint8_t b = 0;
    if ((GPIO_IDR(GPIOB_BASE) & (1u << 0)) == 0u) b |= 1u;  /* B1 PB0 */
    if ((GPIO_IDR(GPIOB_BASE) & (1u << 1)) == 0u) b |= 2u;  /* B2 PB1 */
    if ((GPIO_IDR(GPIOB_BASE) & (1u << 2)) == 0u) b |= 4u;  /* B3 PB2 */
    if ((GPIO_IDR(GPIOA_BASE) & (1u << 0)) == 0u) b |= 8u;  /* B4 PA0 */
    return b;
}

/* PA8 = LCD_nRD: no PWM buzzer on this pin. Beep helper disabled until the
 * real buzzer pin is confirmed; PC13 is a candidate backlight/control line. */
void buzzer_on(void)  { REG32(0x48000818u) = (1u << 13); }  /* PC13 high (probe) */
void buzzer_off(void) { REG32(0x48000818u) = (1u << (13 + 16)); }

/* ---------------- UART console ---------------- */

static void uart_init(uint32_t base)
{
    USART_CR1(base) = 0;                 /* disable */
    USART_BRR(base) = (g_sysclk_mhz * 1000000u + 57600u) / 115200u;
    USART_CR1(base) = (1u << 0)          /* UE */
                    | (1u << 3);         /* TE (no RX, console is TX-only) */
}

void bsp_uart_init(void)
{
    RCC_APB2ENR  |= (1u << 14);          /* USART1 */
    RCC_APB1ENR1 |= (1u << 17) | (1u << 18); /* USART2/3 */

    pin_af(GPIOA_BASE, 9, 7);            /* USART1 TX */
    pin_af(GPIOA_BASE, 10, 7);           /* USART1 RX (unused) */
    pin_af(GPIOA_BASE, 2, 7);            /* USART2 TX */
    pin_af(GPIOA_BASE, 3, 7);            /* USART2 RX (unused) */
    pin_af(GPIOB_BASE, 10, 7);           /* USART3 TX */
    pin_af(GPIOB_BASE, 11, 7);           /* USART3 RX (unused) */

    uart_init(USART1_BASE);
    uart_init(USART2_BASE);
    uart_init(USART3_BASE);
}

static void uart_putc(uint32_t base, char c)
{
    uint32_t guard = 200000u;
    while (((USART_ISR(base) & USART_ISR_TXE) == 0u) && --guard) { }
    USART_TDR(base) = (uint8_t)c;
}

void outc(char c)
{
    uart_putc(USART1_BASE, c);
    uart_putc(USART2_BASE, c);
    uart_putc(USART3_BASE, c);
}

void outs(const char *s)
{
    if (!s) return;
    while (*s) outc(*s++);
}

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
    /* zero-pad fraction */
    int32_t p = scale / 10;
    while (p > 1 && fp < p) { outc('0'); p /= 10; }
    outi(fp);
}

uint32_t dbg_idcode(void) { return REG32(0xE0042000u); }
