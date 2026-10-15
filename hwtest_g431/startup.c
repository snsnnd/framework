/* EFW hwtest startup for STM32G431 (Cortex-M4F)
 * Dual toolchain: GNU (ld script, manual data/bss init) and Arm Compiler 6
 * (scatter file, __main path). Vector table entry 0 = SP top = 0x20008000
 * (top of the 32K SRAM — identical in both toolchains).
 */
#include <stdint.h>
#include "bsp.h"

#if !defined(__ARMCC_VERSION)
extern uint32_t _estack, _sidata, _sdata, _edata, _sbss, _ebss;
#endif

int main(void);
void SysTick_Handler(void);
void Reset_Handler(void);
static void Default_Handler(void) { for (;;) { } }

volatile uint32_t g_ms_tick = 0;

void SysTick_Handler(void) { g_ms_tick++; }

#define D Default_Handler

__attribute__((used, section(".isr_vector")))
static void (* const g_vectors[])(void) = {
    (void (*)(void))0x20008000u,  /* 0  initial SP (top of SRAM) */
    Reset_Handler,                /* 1  reset                 */
    D,                            /* 2  NMI                   */
    D,                            /* 3  HardFault             */
    D,                            /* 4  MemManage             */
    D,                            /* 5  BusFault              */
    D,                            /* 6  UsageFault            */
    0, 0, 0, 0,                   /* 7..10 reserved           */
    D,                            /* 11 SVCall                */
    D,                            /* 12 DebugMon              */
    0,                            /* 13 reserved              */
    D,                            /* 14 PendSV                */
    SysTick_Handler,              /* 15 SysTick               */
    [16 ... 117] = D              /* device IRQs (G431 uses up to ~101) */
};

#if defined(__ARMCC_VERSION)
/* Arm Compiler 6: __main performs scatter-loading (data/bss init) then calls main. */
extern void __main(void);

void Reset_Handler(void)
{
    *(volatile uint32_t *)0xE000ED88 |= (0xFu << 20);   /* enable FPU before any FP code */
    __asm volatile ("dsb" ::: "memory");
    __asm volatile ("isb" ::: "memory");
    __main();
    for (;;) { }
}

#else /* GNU toolchain */

void Reset_Handler(void)
{
    uint32_t *src, *dst;

    src = &_sidata;
    for (dst = &_sdata; dst < &_edata; ) { *dst++ = *src++; }
    for (dst = &_sbss; dst < &_ebss; ) { *dst++ = 0; }

    /* enable FPU CP10/CP11 full access before any float code runs */
    *(volatile uint32_t *)0xE000ED88 |= (0xFu << 20);
    __asm volatile ("dsb" ::: "memory");
    __asm volatile ("isb" ::: "memory");

    main();
    for (;;) { }
}

#endif

