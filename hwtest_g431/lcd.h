/* CT117E-M4 LCD driver port (register-level, no HAL/CMSIS dependency)
 * Ported from the official Lanqiao CT117E template lcd.c (ILI932x/UC8230 GRAM panel,
 * 240x320, 16-bit 8080 bus bit-banged on GPIO).
 *
 * Bus (from official driver + 4T HAL_06_LCD.ioc):
 *   data D0-D15 = GPIOC full port (PC14/15 double as LCD data on this board)
 *   LCD_nCS = PB9, LCD_RS(D/C) = PB8, LCD_nWR = PB5, LCD_nRD = PA8
 *   LEDs PC8-15 are isolated by the 74HC573 latch (PD2) so both can share pins.
 */
#ifndef HWTEST_LCD_H
#define HWTEST_LCD_H

#include <stdint.h>

typedef uint8_t  u8;  typedef uint16_t u16; typedef uint32_t u32;
typedef int8_t   s8;  typedef int16_t  s16; typedef int32_t  s32;
typedef volatile uint16_t vu16;
typedef volatile uint32_t vu32;
typedef const uint32_t uc32; typedef const uint16_t uc16; typedef const uint8_t uc8;

/* RGB565 colors */
#define White          0xFFFF
#define Black          0x0000
#define Grey           0xF7DE
#define Blue           0x001F
#define Blue2          0x051F
#define Red            0xF800
#define Magenta        0xF81F
#define Green          0x07E0
#define Cyan           0x7FFF
#define Yellow         0xFFE0

/* text rows (16x24 font, 10 rows on 240x320 portrait) */
#define Line0          0
#define Line1          24
#define Line2          48
#define Line3          72
#define Line4          96
#define Line5          120
#define Line6          144
#define Line7          168
#define Line8          192
#define Line9          216

#define Horizontal     0x00
#define Vertical       0x01

void LCD_Init(void);
void LCD_SetTextColor(u16 Color);
void LCD_SetBackColor(u16 Color);
void LCD_ClearLine(u8 Line);
void LCD_Clear(u16 Color);
void LCD_SetCursor(u8 Xpos, u16 Ypos);
void LCD_DisplayChar(u8 Line, u16 Column, u8 Ascii);
void LCD_DisplayStringLine(u8 Line, u8 *ptr);
void LCD_SetDisplayWindow(u8 Xpos, u16 Ypos, u8 Height, u16 Width);
void LCD_WindowModeDisable(void);
void LCD_DrawLine(u8 Xpos, u16 Ypos, u16 Length, u8 Direction);
void LCD_DrawRect(u8 Xpos, u16 Ypos, u8 Height, u16 Width);
void LCD_DrawCircle(u8 Xpos, u16 Ypos, u16 Radius);
void LCD_WriteReg(u8 LCD_Reg, u16 LCD_RegValue);
u16  LCD_ReadReg(u8 LCD_Reg);
void LCD_WriteRAM_Prepare(void);
void LCD_WriteRAM(u16 RGB_Code);
void LCD_CtrlLinesConfig(void);
void LCD_BusIn(void);
void LCD_BusOut(void);

/* extensions (this port) */
u16  LCD_ReadID(void);                                   /* raw R0 value */
void LCD_FillArea(u8 x, u16 y, u8 h, u16 w, u16 color);  /* fast window-mode rect fill */

#endif
