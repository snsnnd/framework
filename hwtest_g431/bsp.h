#ifndef HWTEST_BSP_H
#define HWTEST_BSP_H

#include <stdint.h>

/* 1ms system tick, incremented in SysTick_Handler (startup.c) */
extern volatile uint32_t g_ms_tick;

/* cooperative-loop hook: called from busy poll loops (sched_spin);
 * no-op on MCU, updates the emulated tick on host builds */
void bsp_loop_hook(void);

/* --- core bring-up --- */
void bsp_systick_init(void);   /* SysTick @ 1ms */
void bsp_dwt_init(void);       /* DWT cycle counter for us timing */
uint32_t dwt_us(void);         /* microseconds since DWT start */
uint32_t dwt_cycles(void);
void delay_ms(uint32_t ms);    /* busy wait on g_ms_tick */

/* --- CT117E-M4 board hardware --- */
void bsp_gpio_init(void);      /* LEDs(PC8-15+PD2 latch), buttons, buzzer PWM */
void led_write(uint8_t m);     /* bit0..7 = LED1..LED8, 1=on (latched to PC8..15) */
void led_off_all(void);
uint8_t buttons_read(void);    /* bit0..3 = B1(PB0) B2(PB1) B3(PB2) B4(PA0), 1=pressed */
void buzzer_on(void);          /* TIM1_CH1 PA8 PWM 2kHz, 50% */
void buzzer_off(void);

/* --- UART console (broadcast on USART1 PA9/PA10, USART2 PA2/PA3, USART3 PB10/PB11) --- */
void bsp_uart_init(void);      /* all 3 UARTs 115200 8N1 @ 16MHz */
void outc(char c);
void outs(const char *s);
void outi(int32_t v);
void outx(uint32_t v);         /* 8 hex digits, no 0x prefix */
void outf(float v, int frac);  /* fixed point, frac digits after '.' */
#define OUTLN(s) do { outs(s); outs("\r\n"); } while (0)

/* --- chip identity --- */
uint32_t dbg_idcode(void);     /* DBGMCU_IDCODE: [11:0] DEV_ID, [15:12] REV_ID */

/* --- clock boost (arcade mode) --- */
uint32_t bsp_sysclk_mhz(void); /* current SYSCLK in MHz (16 or 80) */
void bsp_clock_boost(void);    /* HSI16/2 x20 /2 -> 80MHz PLL, fallback safe */
int bsp_clock_boost_to(uint32_t target_mhz, uint32_t flash_ws); /* sweep; 1=ok */
void bsp_stack_paint(void);    /* paint free RAM for high-water scan */

#endif
