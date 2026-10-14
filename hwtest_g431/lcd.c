/* CT117E-M4 LCD driver, register-level port of the official template driver.
 * See lcd.h for the bus description. Delay/timing adapted to 16MHz HSI.
 */
#include <stdint.h>
#include "lcd.h"
#include "fonts.h"
#include "bsp.h"      /* delay_ms */

#define REG32(a)   (*(volatile uint32_t *)(a))
#define GPIOA_BASE 0x48000000u
#define GPIOB_BASE 0x48000400u
#define GPIOC_BASE 0x48000800u
#define G_MODER(g) REG32((g) + 0x00u)
#define G_ODR(g)   REG32((g) + 0x14u)
#define G_IDR(g)   REG32((g) + 0x10u)
#define G_BSRR(g)  REG32((g) + 0x18u)
#define RCC_BASE   0x40021000u
#define RCC_AHB2ENR REG32(RCC_BASE + 0x4Cu)

/* CS=PB9 RS=PB8 WR=PB5 RD=PA8 */
#define CS_LOW()   G_BSRR(GPIOB_BASE) = (1u << (9 + 16))
#define CS_HIGH()  G_BSRR(GPIOB_BASE) = (1u << 9)
#define RS_LOW()   G_BSRR(GPIOB_BASE) = (1u << (8 + 16))
#define RS_HIGH()  G_BSRR(GPIOB_BASE) = (1u << 8)
#define WR_LOW()   G_BSRR(GPIOB_BASE) = (1u << (5 + 16))
#define WR_HIGH()  G_BSRR(GPIOB_BASE) = (1u << 5)
#define RD_LOW()   G_BSRR(GPIOA_BASE) = (1u << (8 + 16))
#define RD_HIGH()  G_BSRR(GPIOA_BASE) = (1u << 8)
#define BUS_OUT(v) G_ODR(GPIOC_BASE) = (v)
#define BUS_IN()   G_IDR(GPIOC_BASE)

static vu16 TextColor = 0x0000, BackColor = 0xFFFF;
static u16 g_lcd_id = 0;

static inline void wr_pulse(void)
{
    /* >=75ns low time required; 8 nops = 100ns @80MHz, 500ns @16MHz */
    WR_LOW();
    __asm volatile ("nop" ::: "memory");
    __asm volatile ("nop" ::: "memory");
    __asm volatile ("nop" ::: "memory");
    __asm volatile ("nop" ::: "memory");
    __asm volatile ("nop" ::: "memory");
    __asm volatile ("nop" ::: "memory");
    __asm volatile ("nop" ::: "memory");
    __asm volatile ("nop" ::: "memory");
    WR_HIGH();
}

/* ---------------- registers (template R-numbers) ---------------- */
#define R0   0x00
#define R1   0x01
#define R2   0x02
#define R3   0x03
#define R4   0x04
#define R7   0x07
#define R8   0x08
#define R9   0x09
#define R10  0x0A
#define R12  0x0C
#define R13  0x0D
#define R15  0x0F
#define R16  0x10
#define R17  0x11
#define R18  0x12
#define R19  0x13
#define R21  0x15
#define R22  0x16
#define R23  0x17
#define R24  0x18
#define R25  0x19
#define R26  0x1A
#define R27  0x1B
#define R28  0x1C
#define R29  0x1D
#define R30  0x1E
#define R31  0x1F
#define R32  0x20
#define R33  0x21
#define R34  0x22
#define R36  0x24
#define R37  0x25
#define R40  0x28
#define R41  0x29
#define R43  0x2B
#define R45  0x2D
#define R48  0x30
#define R49  0x31
#define R50  0x32
#define R51  0x33
#define R52  0x34
#define R53  0x35
#define R54  0x36
#define R55  0x37
#define R56  0x38
#define R57  0x39
#define R59  0x3B
#define R60  0x3C
#define R61  0x3D
#define R62  0x3E
#define R63  0x3F
#define R64  0x40
#define R65  0x41
#define R66  0x42
#define R67  0x43
#define R68  0x44
#define R69  0x45
#define R70  0x46
#define R71  0x47
#define R72  0x48
#define R73  0x49
#define R74  0x4A
#define R75  0x4B
#define R76  0x4C
#define R77  0x4D
#define R78  0x4E
#define R79  0x4F
#define R80  0x50
#define R81  0x51
#define R82  0x52
#define R83  0x53
#define R96  0x60
#define R97  0x61
#define R106 0x6A
#define R118 0x76
#define R128 0x80
#define R129 0x81
#define R130 0x82
#define R131 0x83
#define R132 0x84
#define R133 0x85
#define R134 0x86
#define R135 0x87
#define R136 0x88
#define R137 0x89
#define R139 0x8B
#define R140 0x8C
#define R141 0x8D
#define R143 0x8F
#define R144 0x90
#define R145 0x91
#define R146 0x92
#define R147 0x93
#define R148 0x94
#define R149 0x95
#define R150 0x96
#define R151 0x97
#define R152 0x98
#define R153 0x99
#define R154 0x9A
#define R157 0x9D
#define R192 0xC0
#define R193 0xC1
#define R227 0xE3
#define R229 0xE5
#define R231 0xE7
#define R239 0xEF

void Delay_LCD(u16 n)
{
    u16 i, j;
    for (i = 0; i < n; ++i)
        for (j = 0; j < 3000; ++j)
            __asm volatile ("nop");
}

/* ---------------- low level ---------------- */

void LCD_CtrlLinesConfig(void)
{
    RCC_AHB2ENR |= (1u << 0) | (1u << 1) | (1u << 2);   /* GPIOA/B/C */

    /* PB5/PB8/PB9 outputs */
    G_MODER(GPIOB_BASE) &= ~((3u << 10) | (3u << 16) | (3u << 18));
    G_MODER(GPIOB_BASE) |=  ((1u << 10) | (1u << 16) | (1u << 18));
    /* PA8 output */
    G_MODER(GPIOA_BASE) &= ~(3u << 16);
    G_MODER(GPIOA_BASE) |=  (1u << 16);

    LCD_BusOut();

    RD_HIGH();   /* PA8 high */
    WR_HIGH();   /* PB5 high */
    CS_HIGH();   /* PB9 high (RS/PB8 idle low) */
}

void LCD_BusIn(void)
{
    G_MODER(GPIOC_BASE) = 0x00000000u;                  /* all PC pins input */
}

void LCD_BusOut(void)
{
    G_MODER(GPIOC_BASE) = 0x55555555u;                  /* all PC pins output */
}

void LCD_WriteReg(u8 LCD_Reg, u16 LCD_RegValue)
{
    CS_LOW();
    RS_LOW();
    WR_HIGH();

    BUS_OUT(LCD_Reg);
    wr_pulse();
    RS_HIGH();

    BUS_OUT(LCD_RegValue);
    wr_pulse();
    RS_HIGH();

    CS_HIGH();
}

u16 LCD_ReadReg(u8 LCD_Reg)
{
    u16 temp;

    CS_LOW();
    RS_LOW();
    WR_HIGH();

    BUS_OUT(LCD_Reg);
    wr_pulse();
    RS_HIGH();

    LCD_BusIn();
    RD_LOW();
    __asm volatile ("nop" ::: "memory");
    __asm volatile ("nop" ::: "memory");
    __asm volatile ("nop" ::: "memory");
    temp = (u16)BUS_IN();
    RD_HIGH();

    LCD_BusOut();
    CS_HIGH();

    return temp;
}

void LCD_WriteRAM_Prepare(void)
{
    CS_LOW();
    RS_LOW();
    WR_HIGH();

    BUS_OUT(R34);          /* 0x22: GRAM write */
    wr_pulse();
    RS_HIGH();
    CS_HIGH();
}

void LCD_WriteRAM(u16 RGB_Code)
{
    CS_LOW();
    RS_HIGH();

    BUS_OUT(RGB_Code);
    wr_pulse();

    CS_HIGH();
}

/* ---------------- controller init sequences (template) ---------------- */

static void REG_8230_Init(void)
{
    LCD_WriteReg(0x0000, 0x0001);
    Delay_LCD(1000);
    LCD_WriteReg(0x0001, 0x0000);
    LCD_WriteReg(0x0010, 0x1790);
    LCD_WriteReg(0x0060, 0x2700);
    LCD_WriteReg(0x0061, 0x0001);
    LCD_WriteReg(0x0046, 0x0002);
    LCD_WriteReg(0x0013, 0x8010);
    LCD_WriteReg(0x0012, 0x80fe);
    LCD_WriteReg(0x0002, 0x0500);
    LCD_WriteReg(0x0003, 0x1030);

    LCD_WriteReg(0x0030, 0x0303);
    LCD_WriteReg(0x0031, 0x0303);
    LCD_WriteReg(0x0032, 0x0303);
    LCD_WriteReg(0x0033, 0x0300);
    LCD_WriteReg(0x0034, 0x0003);
    LCD_WriteReg(0x0035, 0x0303);
    LCD_WriteReg(0x0036, 0x0014);
    LCD_WriteReg(0x0037, 0x0303);
    LCD_WriteReg(0x0038, 0x0303);
    LCD_WriteReg(0x0039, 0x0303);
    LCD_WriteReg(0x003a, 0x0300);
    LCD_WriteReg(0x003b, 0x0003);
    LCD_WriteReg(0x003c, 0x0303);
    LCD_WriteReg(0x003d, 0x1400);

    LCD_WriteReg(0x0092, 0x0200);
    LCD_WriteReg(0x0093, 0x0303);
    LCD_WriteReg(0x0090, 0x080d);
    LCD_WriteReg(0x0003, 0x1018);
    LCD_WriteReg(0x0007, 0x0173);
}

static void REG_932X_Init(void)
{
    LCD_WriteReg(R227, 0x3008);
    LCD_WriteReg(R231, 0x0012);
    LCD_WriteReg(R239, 0x1231);
    LCD_WriteReg(R1, 0x0000);
    LCD_WriteReg(R2, 0x0700);
    LCD_WriteReg(R3, 0x1030);
    LCD_WriteReg(R4, 0x0000);
    LCD_WriteReg(R8, 0x0207);
    LCD_WriteReg(R9, 0x0000);
    LCD_WriteReg(R10, 0x0000);
    LCD_WriteReg(R12, 0x0000);
    LCD_WriteReg(R13, 0x0000);
    LCD_WriteReg(R15, 0x0000);
    /* power on */
    LCD_WriteReg(R16, 0x0000);
    LCD_WriteReg(R17, 0x0007);
    LCD_WriteReg(R18, 0x0000);
    LCD_WriteReg(R19, 0x0000);
    delay_ms(200);
    LCD_WriteReg(R16, 0x1690);
    LCD_WriteReg(R17, 0x0227);
    delay_ms(50);
    LCD_WriteReg(R18, 0x001D);
    delay_ms(50);
    LCD_WriteReg(R19, 0x0800);
    LCD_WriteReg(R41, 0x0014);
    LCD_WriteReg(R43, 0x000B);
    delay_ms(50);
    LCD_WriteReg(R32, 0x0000);
    LCD_WriteReg(R33, 0x0000);
    /* gamma */
    LCD_WriteReg(R48, 0x0007);
    LCD_WriteReg(R49, 0x0707);
    LCD_WriteReg(R50, 0x0006);
    LCD_WriteReg(R53, 0x0704);
    LCD_WriteReg(R54, 0x1F04);
    LCD_WriteReg(R55, 0x0004);
    LCD_WriteReg(R56, 0x0000);
    LCD_WriteReg(R57, 0x0706);
    LCD_WriteReg(R60, 0x0701);
    LCD_WriteReg(R61, 0x000F);
    /* GRAM area */
    LCD_WriteReg(R80, 0x0000);
    LCD_WriteReg(R81, 0x00EF);
    LCD_WriteReg(R82, 0x0000);
    LCD_WriteReg(R83, 0x013F);
    LCD_WriteReg(R96, 0x2700);
    LCD_WriteReg(R97, 0x0001);
    LCD_WriteReg(R106, 0x0000);
    LCD_WriteReg(R128, 0x0000);
    LCD_WriteReg(R129, 0x0000);
    LCD_WriteReg(R130, 0x0000);
    LCD_WriteReg(R131, 0x0000);
    LCD_WriteReg(R132, 0x0000);
    LCD_WriteReg(R133, 0x0000);
    LCD_WriteReg(R144, 0x0010);
    LCD_WriteReg(R146, 0x0000);
    LCD_WriteReg(R147, 0x0003);
    LCD_WriteReg(R149, 0x0110);
    LCD_WriteReg(R151, 0x0000);
    LCD_WriteReg(R152, 0x0000);
    LCD_WriteReg(R3, 0x01018);
    LCD_WriteReg(R7, 0x0173);      /* display ON */
}

void LCD_Init(void)
{
    u16 dummy;
    LCD_CtrlLinesConfig();
    delay_ms(50);
    dummy = LCD_ReadReg(0);
    g_lcd_id = dummy;
    if (dummy == 0x8230) {
        REG_8230_Init();
    } else {
        REG_932X_Init();
    }
}

u16 LCD_ReadID(void) { return g_lcd_id; }

/* ---------------- graphics ---------------- */

void LCD_SetTextColor(u16 Color) { TextColor = Color; }
void LCD_SetBackColor(u16 Color) { BackColor = Color; }

void LCD_SetCursor(u8 Xpos, u16 Ypos)
{
    LCD_WriteReg(R32, Xpos);
    LCD_WriteReg(R33, Ypos);
}

void LCD_Clear(u16 Color)
{
    u32 index;
    LCD_SetCursor(0x00, 0x0000);
    LCD_WriteRAM_Prepare();
    for (index = 0; index < 76800; index++)
        LCD_WriteRAM(Color);
}

void LCD_ClearLine(u8 Line)
{
    LCD_DisplayStringLine(Line, (u8 *)"                    ");
}

void LCD_DrawChar(u8 Xpos, u16 Ypos, uc16 *c)
{
    u32 index, i;
    u8 Xaddress = Xpos;
    LCD_SetCursor(Xaddress, Ypos);

    for (index = 0; index < 24; index++) {
        LCD_WriteRAM_Prepare();
        for (i = 0; i < 16; i++) {
            if ((c[index] & (1u << i)) == 0x00)
                LCD_WriteRAM(BackColor);
            else
                LCD_WriteRAM(TextColor);
        }
        Xaddress++;
        LCD_SetCursor(Xaddress, Ypos);
    }
}

void LCD_DisplayChar(u8 Line, u16 Column, u8 Ascii)
{
    if (Ascii < 32 || Ascii > 126) Ascii = '?';
    Ascii -= 32;
    LCD_DrawChar(Line, Column, &ASCII_Table[Ascii * 24]);
}

void LCD_DisplayStringLine(u8 Line, u8 *ptr)
{
    u32 i = 0;
    u16 refcolumn = 319;

    while ((*ptr != 0) && (i < 20)) {
        LCD_DisplayChar(Line, refcolumn, *ptr);
        refcolumn -= 16;
        ptr++;
        i++;
    }
}

void LCD_SetDisplayWindow(u8 Xpos, u16 Ypos, u8 Height, u16 Width)
{
    if (Xpos >= Height)
        LCD_WriteReg(R80, (u16)(Xpos - Height + 1));
    else
        LCD_WriteReg(R80, 0);
    LCD_WriteReg(R81, Xpos);
    if (Ypos >= Width)
        LCD_WriteReg(R82, (u16)(Ypos - Width + 1));
    else
        LCD_WriteReg(R82, 0);
    LCD_WriteReg(R83, Ypos);
    LCD_SetCursor(Xpos, Ypos);
}

void LCD_WindowModeDisable(void)
{
    LCD_SetDisplayWindow(239, 0x13F, 240, 320);
    LCD_WriteReg(R3, 0x1018);
}

void LCD_FillArea(u8 x, u16 y, u8 h, u16 w, u16 color)
{
    u32 n = (u32)h * w, i;
    LCD_SetDisplayWindow((u8)(x + h - 1), (u16)(y + w - 1), h, w);
    LCD_WriteRAM_Prepare();
    for (i = 0; i < n; i++)
        LCD_WriteRAM(color);
    LCD_WindowModeDisable();
}

void LCD_DrawLine(u8 Xpos, u16 Ypos, u16 Length, u8 Direction)
{
    u32 i;

    LCD_SetCursor(Xpos, Ypos);
    if (Direction == Horizontal) {
        LCD_WriteRAM_Prepare();
        for (i = 0; i < Length; i++)
            LCD_WriteRAM(TextColor);
    } else {
        for (i = 0; i < Length; i++) {
            LCD_WriteRAM_Prepare();
            LCD_WriteRAM(TextColor);
            Xpos++;
            LCD_SetCursor(Xpos, Ypos);
        }
    }
}

void LCD_DrawRect(u8 Xpos, u16 Ypos, u8 Height, u16 Width)
{
    LCD_DrawLine(Xpos, Ypos, Width, Horizontal);
    LCD_DrawLine((u8)(Xpos + Height), Ypos, Width, Horizontal);
    LCD_DrawLine(Xpos, Ypos, Height, Vertical);
    LCD_DrawLine(Xpos, (u16)(Ypos - Width + 1), Height, Vertical);
}

void LCD_DrawCircle(u8 Xpos, u16 Ypos, u16 Radius)
{
    s32 D;
    u32 CurX, CurY;

    D = 2 - 2 * (s32)Radius;
    CurX = 0;
    CurY = Radius;
    while (CurX <= CurY) {
        LCD_SetCursor((u8)(Xpos + CurX), (u16)(Ypos + CurY));
        LCD_WriteRAM_Prepare();
        LCD_WriteRAM(TextColor);
        LCD_SetCursor((u8)(Xpos + CurX), (u16)(Ypos - CurY));
        LCD_WriteRAM(TextColor);
        LCD_SetCursor((u8)(Xpos - CurX), (u16)(Ypos + CurY));
        LCD_WriteRAM(TextColor);
        LCD_SetCursor((u8)(Xpos - CurX), (u16)(Ypos - CurY));
        LCD_WriteRAM(TextColor);
        LCD_SetCursor((u8)(Xpos + CurY), (u16)(Ypos + CurX));
        LCD_WriteRAM(TextColor);
        LCD_SetCursor((u8)(Xpos + CurY), (u16)(Ypos - CurX));
        LCD_WriteRAM(TextColor);
        LCD_SetCursor((u8)(Xpos - CurY), (u16)(Ypos + CurX));
        LCD_WriteRAM(TextColor);
        LCD_SetCursor((u8)(Xpos - CurY), (u16)(Ypos - CurX));
        LCD_WriteRAM(TextColor);
        if (D < 0) {
            D += 2 * (s32)CurX + 3;
        } else {
            D += 2 * ((s32)CurX - (s32)CurY) + 5;
            CurY--;
        }
        CurX++;
    }
}
