"""
固件集成模块

将固件库集成到 codegen 流程中，自动生成：
- HAL 适配代码
- CMake 配置
- 启动代码
- 链接脚本
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


class FirmwareIntegrator:
    """固件集成器
    
    将固件库集成到项目中。
    """
    
    def __init__(self, project_dir: Path, firmware_root: Optional[Path] = None):
        self.project_dir = project_dir
        self.firmware_root = firmware_root
        
        # 固件库配置
        self.firmware_config: dict[str, Any] = {}
    
    def load_chip_config(self, chip: str) -> dict[str, Any]:
        """加载芯片配置"""
        # 从 MCU 数据库加载
        from tools.simulator.chip_db import get_chip_database
        
        db = get_chip_database()
        chip_data = db.load_chip(chip)
        
        if not chip_data:
            raise ValueError(f"未找到芯片: {chip}")
        
        return chip_data
    
    def load_firmware_config(self, firmware_name: str) -> dict[str, Any]:
        """加载固件配置"""
        from tools.firmware.manager import FIRMWARES, FirmwareManager
        
        if firmware_name not in FIRMWARES:
            raise ValueError(f"未找到固件: {firmware_name}")
        
        fw = FIRMWARES[firmware_name]
        manager = FirmwareManager()
        
        # 检查固件是否已安装
        if firmware_name not in manager.config:
            raise ValueError(f"固件未安装: {firmware_name}")
        
        firmware_path = Path(manager.config[firmware_name]["path"])
        
        return {
            "name": firmware_name,
            "path": str(firmware_path),
            "include_dirs": [str(firmware_path / d) for d in fw.include_dirs],
            "source_dirs": [str(firmware_path / d) for d in fw.source_dirs],
            "cmsis_dir": str(firmware_path / fw.cmsis_dir) if fw.cmsis_dir else None,
            "startup_dir": str(firmware_path / fw.startup_dir) if fw.startup_dir else None,
            "linker_dir": str(firmware_path / fw.linker_dir) if fw.linker_dir else None,
        }
    
    def generate_all(
        self,
        chip: str,
        firmware_name: Optional[str] = None,
        app_name: str = "app",
    ) -> dict[str, Path]:
        """生成所有集成文件
        
        Args:
            chip: 芯片名称
            firmware_name: 固件名称（可选，自动检测）
            app_name: 应用名称
        
        Returns:
            生成的文件路径字典
        """
        # 加载芯片配置
        chip_config = self.load_chip_config(chip)
        
        # 确定固件名称
        if not firmware_name:
            firmware_name = self._detect_firmware(chip_config)
        
        # 加载固件配置
        firmware_config = self.load_firmware_config(firmware_name)
        
        # 生成文件
        generated = {}
        
        # 1. 生成 CMakeLists.txt
        cmake_path = self._generate_cmake(chip_config, firmware_config, app_name)
        generated["cmake"] = cmake_path
        
        # 2. 生成 HAL 适配代码
        hal_path = self._generate_hal_adapter(chip_config, firmware_config)
        generated["hal_adapter"] = hal_path
        
        # 3. 生成启动代码
        startup_path = self._generate_startup(chip_config, firmware_config)
        if startup_path:
            generated["startup"] = startup_path
        
        # 4. 生成链接脚本
        linker_path = self._generate_linker_script(chip_config, firmware_config)
        if linker_path:
            generated["linker"] = linker_path
        
        # 5. 生成系统配置
        system_path = self._generate_system_config(chip_config, firmware_config)
        generated["system"] = system_path
        
        return generated
    
    def _detect_firmware(self, chip_config: dict) -> str:
        """自动检测固件"""
        family = chip_config.get("family", "").upper()
        
        # 固件映射
        firmware_map = {
            "STM32F1": "stm32f1",
            "STM32F4": "stm32f4",
            "STM32G4": "stm32g4",
            "STM32H7": "stm32h7",
            "ESP32": "esp-idf",
            "GD32": "gd32-standard",
            "CH32V": "ch32v-sdk",
            "MSPM0": "mspm0-sdk",
        }
        
        for prefix, fw_name in firmware_map.items():
            if prefix in family:
                return fw_name
        
        raise ValueError(f"无法检测芯片 {chip_config.get('name')} 的固件")
    
    def _generate_cmake(
        self,
        chip_config: dict,
        firmware_config: dict,
        app_name: str,
    ) -> Path:
        """生成 CMakeLists.txt"""
        from tools.compiler.cmake_generator import CMakeGenerator
        
        generator = CMakeGenerator(
            self.project_dir,
            Path(firmware_config["path"])
        )
        
        # 不传 sources，让 CMakeGenerator 自动添加 main.c 和 hal_adapter.c
        content = generator.generate(
            chip=chip_config.get("name", ""),
            sources=[],
            includes=["include"],
        )
        
        cmake_path = self.project_dir / "CMakeLists.txt"
        cmake_path.parent.mkdir(parents=True, exist_ok=True)
        cmake_path.write_text(content)
        
        return cmake_path
    
    def _generate_hal_adapter(
        self,
        chip_config: dict,
        firmware_config: dict,
    ) -> Path:
        """生成 HAL 适配代码"""
        family = chip_config.get("family", "").upper()
        
        # 根据芯片系列选择适配器
        if "STM32" in family:
            content = self._generate_stm32_hal(chip_config, firmware_config)
        elif "ESP32" in family:
            content = self._generate_esp32_hal(chip_config, firmware_config)
        else:
            content = self._generate_generic_hal(chip_config, firmware_config)
        
        hal_path = self.project_dir / "hal_adapter.c"
        hal_path.parent.mkdir(parents=True, exist_ok=True)
        hal_path.write_text(content)
        
        return hal_path
    
    def _generate_stm32_hal(
        self,
        chip_config: dict,
        firmware_config: dict,
    ) -> str:
        """生成 STM32 HAL 适配代码"""
        device = chip_config.get("device", "STM32F407xx")
        
        return f'''/**
 * @file    hal_adapter.c
 * @brief   STM32 HAL 适配层 - 自动生成
 * @chip    {chip_config.get("name", "Unknown")}
 */

#include "efw/hal/hal_adapter.h"
#include "system_config.h"

/* ==================================================================
 *  系统初始化
 * ================================================================== */

void SystemClock_Config(void)
{{
    RCC_OscInitTypeDef RCC_OscInitStruct = {{0}};
    RCC_ClkInitTypeDef RCC_ClkInitStruct = {{0}};

    /* 配置电源 */
    __HAL_RCC_PWR_CLK_ENABLE();
    __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);

    /* 配置 HSE 和 PLL */
    RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
    RCC_OscInitStruct.HSEState = RCC_HSE_ON;
    RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
    RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
    RCC_OscInitStruct.PLL.PLLM = 8;
    RCC_OscInitStruct.PLL.PLLN = 336;
    RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
    RCC_OscInitStruct.PLL.PLLQ = 7;
    HAL_RCC_OscConfig(&RCC_OscInitStruct);

    /* 配置总线时钟 */
    RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK
                                | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
    RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV4;
    RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV2;
    HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_5);
}}

/* ==================================================================
 *  GPIO 适配
 * ================================================================== */

efw_status_t efw_hal_gpio_init(efw_hal_gpio_t *gpio, const char *name)
{{
    if (!gpio || !name) return EFW_ERR_INVALID;

    gpio->name = name;

    /* 解析端口和引脚 */
    if (name[0] == 'P' && strlen(name) >= 3)
    {{
        char port = name[1];
        int pin = atoi(&name[2]);

        /* 设置端口 */
        switch (port)
        {{
            case 'A': gpio->port = GPIOA; break;
            case 'B': gpio->port = GPIOB; break;
            case 'C': gpio->port = GPIOC; break;
            case 'D': gpio->port = GPIOD; break;
            case 'E': gpio->port = GPIOE; break;
            default: return EFW_ERR_INVALID;
        }}

        /* 设置引脚 */
        gpio->pin = (1 << pin);

        /* 使能时钟 */
        __HAL_RCC_GPIOA_CLK_ENABLE();
    }}
    else
    {{
        return EFW_ERR_INVALID;
    }}

    return EFW_OK;
}}

uint8_t efw_hal_gpio_read(const efw_hal_gpio_t *gpio)
{{
    if (!gpio || !gpio->port) return 0;
    return HAL_GPIO_ReadPin(gpio->port, gpio->pin) ? 1 : 0;
}}

void efw_hal_gpio_write(efw_hal_gpio_t *gpio, uint8_t value)
{{
    if (!gpio || !gpio->port) return;
    HAL_GPIO_WritePin(gpio->port, gpio->pin, value ? GPIO_PIN_SET : GPIO_PIN_RESET);
}}

void efw_hal_gpio_toggle(efw_hal_gpio_t *gpio)
{{
    if (!gpio || !gpio->port) return;
    HAL_GPIO_TogglePin(gpio->port, gpio->pin);
}}

/* ==================================================================
 *  ADC 适配
 * ================================================================== */

efw_status_t efw_hal_adc_init(efw_hal_adc_t *adc, const char *name)
{{
    if (!adc || !name) return EFW_ERR_INVALID;
    adc->name = name;
    return EFW_OK;
}}

uint16_t efw_hal_adc_read(const efw_hal_adc_t *adc)
{{
    if (!adc || !adc->hadc) return 0;

    HAL_ADC_Start(adc->hadc);
    HAL_ADC_PollForConversion(adc->hadc, 10);
    uint16_t value = HAL_ADC_GetValue(adc->hadc);
    HAL_ADC_Stop(adc->hadc);

    return value;
}}

uint32_t efw_hal_adc_read_voltage(const efw_hal_adc_t *adc)
{{
    uint16_t raw = efw_hal_adc_read(adc);
    return (uint32_t)(raw * 3300 / 4095);
}}

/* ==================================================================
 *  PWM 适配
 * ================================================================== */

efw_status_t efw_hal_pwm_init(efw_hal_pwm_t *pwm, const char *name, uint32_t freq)
{{
    if (!pwm || !name) return EFW_ERR_INVALID;
    pwm->name = name;
    pwm->frequency = freq;
    pwm->duty = 0;
    return EFW_OK;
}}

void efw_hal_pwm_set_duty(efw_hal_pwm_t *pwm, uint32_t duty)
{{
    if (!pwm || !pwm->htim) return;

    pwm->duty = duty;
    uint32_t period = __HAL_TIM_GET_AUTORELOAD(pwm->htim);
    uint32_t pulse = (period * duty) / 10000;

    __HAL_TIM_SET_COMPARE(pwm->htim, pwm->channel, pulse);
}}

void efw_hal_pwm_start(efw_hal_pwm_t *pwm)
{{
    if (!pwm || !pwm->htim) return;
    HAL_TIM_PWM_Start(pwm->htim, pwm->channel);
}}

void efw_hal_pwm_stop(efw_hal_pwm_t *pwm)
{{
    if (!pwm || !pwm->htim) return;
    HAL_TIM_PWM_Stop(pwm->htim, pwm->channel);
}}

/* ==================================================================
 *  UART 适配
 * ================================================================== */

efw_status_t efw_hal_uart_init(efw_hal_uart_t *uart, const char *name, uint32_t baud)
{{
    if (!uart || !name) return EFW_ERR_INVALID;
    uart->name = name;
    uart->baudrate = baud;
    return EFW_OK;
}}

efw_status_t efw_hal_uart_send(efw_hal_uart_t *uart, const uint8_t *data, uint16_t len)
{{
    if (!uart || !uart->huart || !data) return EFW_ERR_INVALID;

    HAL_StatusTypeDef status = HAL_UART_Transmit(uart->huart, (uint8_t *)data, len, 100);
    return (status == HAL_OK) ? EFW_OK : EFW_ERR_IO;
}}

efw_status_t efw_hal_uart_receive(efw_hal_uart_t *uart, uint8_t *data, uint16_t len, uint16_t *actual)
{{
    if (!uart || !uart->huart || !data || !actual) return EFW_ERR_INVALID;

    HAL_StatusTypeDef status = HAL_UART_Receive(uart->huart, data, len, 10);
    *actual = (status == HAL_OK) ? len : 0;

    return (status == HAL_OK) ? EFW_OK : EFW_ERR_IO;
}}

/* ==================================================================
 *  系统函数
 * ================================================================== */

uint32_t efw_hal_get_time_us(void)
{{
    return HAL_GetTick() * 1000;
}}

void efw_hal_delay_ms(uint32_t ms)
{{
    HAL_Delay(ms);
}}

void efw_hal_delay_us(uint32_t us)
{{
    uint32_t start = efw_hal_get_time_us();
    while ((efw_hal_get_time_us() - start) < us)
    {{
        // 忙等待
    }}
}}
'''
    
    def _generate_esp32_hal(
        self,
        chip_config: dict,
        firmware_config: dict,
    ) -> str:
        """生成 ESP32 HAL 适配代码"""
        return f'''/**
 * @file    hal_adapter.c
 * @brief   ESP32 HAL 适配层 - 自动生成
 * @chip    {chip_config.get("name", "ESP32")}
 */

#include "efw/hal/hal_adapter.h"
#include "driver/gpio.h"
#include "driver/adc.h"
#include "driver/uart.h"
#include "esp_timer.h"

/* ==================================================================
 *  GPIO 适配
 * ================================================================== */

efw_status_t efw_hal_gpio_init(efw_hal_gpio_t *gpio, const char *name)
{{
    if (!gpio || !name) return EFW_ERR_INVALID;

    gpio->name = name;
    gpio->gpio_num = atoi(name);

    gpio_config_t config = {{
        .pin_bit_mask = (1ULL << gpio->gpio_num),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    }};
    gpio_config(&config);

    return EFW_OK;
}}

uint8_t efw_hal_gpio_read(const efw_hal_gpio_t *gpio)
{{
    if (!gpio) return 0;
    return gpio_get_level(gpio->gpio_num);
}}

void efw_hal_gpio_write(efw_hal_gpio_t *gpio, uint8_t value)
{{
    if (!gpio) return;
    gpio_set_level(gpio->gpio_num, value);
}}

void efw_hal_gpio_toggle(efw_hal_gpio_t *gpio)
{{
    if (!gpio) return;
    uint8_t current = gpio_get_level(gpio->gpio_num);
    gpio_set_level(gpio->gpio_num, !current);
}}

/* ==================================================================
 *  ADC 适配
 * ================================================================== */

efw_status_t efw_hal_adc_init(efw_hal_adc_t *adc, const char *name)
{{
    if (!adc || !name) return EFW_ERR_INVALID;

    adc->name = name;
    adc->channel = atoi(name);

    adc1_config_width(ADC_WIDTH_BIT_12);
    adc1_config_channel_atten(adc->channel, ADC_ATTEN_DB_11);

    return EFW_OK;
}}

uint16_t efw_hal_adc_read(const efw_hal_adc_t *adc)
{{
    if (!adc) return 0;
    return adc1_get_raw(adc->channel);
}}

uint32_t efw_hal_adc_read_voltage(const efw_hal_adc_t *adc)
{{
    uint16_t raw = efw_hal_adc_read(adc);
    return (uint32_t)(raw * 3300 / 4095);
}}

/* ==================================================================
 *  UART 适配
 * ================================================================== */

efw_status_t efw_hal_uart_init(efw_hal_uart_t *uart, const char *name, uint32_t baud)
{{
    if (!uart || !name) return EFW_ERR_INVALID;

    uart->name = name;
    uart->baudrate = baud;
    uart->uart_num = atoi(name);

    uart_config_t config = {{
        .baud_rate = baud,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
    }};
    uart_param_config(uart->uart_num, &config);
    uart_driver_install(uart->uart_num, 1024, 1024, 0, NULL, 0);

    return EFW_OK;
}}

efw_status_t efw_hal_uart_send(efw_hal_uart_t *uart, const uint8_t *data, uint16_t len)
{{
    if (!uart || !data) return EFW_ERR_INVALID;

    int written = uart_write_bytes(uart->uart_num, data, len);
    return (written == len) ? EFW_OK : EFW_ERR_IO;
}}

efw_status_t efw_hal_uart_receive(efw_hal_uart_t *uart, uint8_t *data, uint16_t len, uint16_t *actual)
{{
    if (!uart || !data || !actual) return EFW_ERR_INVALID;

    int read = uart_read_bytes(uart->uart_num, data, len, 10 / portTICK_PERIOD_MS);
    *actual = (read > 0) ? read : 0;

    return (read >= 0) ? EFW_OK : EFW_ERR_IO;
}}

/* ==================================================================
 *  系统函数
 * ================================================================== */

uint32_t efw_hal_get_time_us(void)
{{
    return (uint32_t)esp_timer_get_time();
}}

void efw_hal_delay_ms(uint32_t ms)
{{
    vTaskDelay(ms / portTICK_PERIOD_MS);
}}

void efw_hal_delay_us(uint32_t us)
{{
    uint64_t start = esp_timer_get_time();
    while ((esp_timer_get_time() - start) < us)
    {{
        // 忙等待
    }}
}}
'''
    
    def _generate_generic_hal(
        self,
        chip_config: dict,
        firmware_config: dict,
    ) -> str:
        """生成通用 HAL 适配代码"""
        return f'''/**
 * @file    hal_adapter.c
 * @brief   通用 HAL 适配层 - 自动生成
 * @chip    {chip_config.get("name", "Unknown")}
 */

#include "efw/hal/hal_adapter.h"

/* 注意: 需要根据具体芯片实现以下函数 */

/* ==================================================================
 *  GPIO 适配
 * ================================================================== */

efw_status_t efw_hal_gpio_init(efw_hal_gpio_t *gpio, const char *name)
{{
    /* TODO: 实现 GPIO 初始化 */
    return EFW_OK;
}}

uint8_t efw_hal_gpio_read(const efw_hal_gpio_t *gpio)
{{
    /* TODO: 实现 GPIO 读取 */
    return 0;
}}

void efw_hal_gpio_write(efw_hal_gpio_t *gpio, uint8_t value)
{{
    /* TODO: 实现 GPIO 写入 */
}}

void efw_hal_gpio_toggle(efw_hal_gpio_t *gpio)
{{
    /* TODO: 实现 GPIO 切换 */
}}

/* ==================================================================
 *  ADC 适配
 * ================================================================== */

efw_status_t efw_hal_adc_init(efw_hal_adc_t *adc, const char *name)
{{
    /* TODO: 实现 ADC 初始化 */
    return EFW_OK;
}}

uint16_t efw_hal_adc_read(const efw_hal_adc_t *adc)
{{
    /* TODO: 实现 ADC 读取 */
    return 0;
}}

uint32_t efw_hal_adc_read_voltage(const efw_hal_adc_t *adc)
{{
    uint16_t raw = efw_hal_adc_read(adc);
    return (uint32_t)(raw * 3300 / 4095);
}}

/* ==================================================================
 *  PWM 适配
 * ================================================================== */

efw_status_t efw_hal_pwm_init(efw_hal_pwm_t *pwm, const char *name, uint32_t freq)
{{
    /* TODO: 实现 PWM 初始化 */
    return EFW_OK;
}}

void efw_hal_pwm_set_duty(efw_hal_pwm_t *pwm, uint32_t duty)
{{
    /* TODO: 实现 PWM 占空比设置 */
}}

void efw_hal_pwm_start(efw_hal_pwm_t *pwm)
{{
    /* TODO: 实现 PWM 启动 */
}}

void efw_hal_pwm_stop(efw_hal_pwm_t *pwm)
{{
    /* TODO: 实现 PWM 停止 */
}}

/* ==================================================================
 *  UART 适配
 * ================================================================== */

efw_status_t efw_hal_uart_init(efw_hal_uart_t *uart, const char *name, uint32_t baud)
{{
    /* TODO: 实现 UART 初始化 */
    return EFW_OK;
}}

efw_status_t efw_hal_uart_send(efw_hal_uart_t *uart, const uint8_t *data, uint16_t len)
{{
    /* TODO: 实现 UART 发送 */
    return EFW_OK;
}}

efw_status_t efw_hal_uart_receive(efw_hal_uart_t *uart, uint8_t *data, uint16_t len, uint16_t *actual)
{{
    /* TODO: 实现 UART 接收 */
    *actual = 0;
    return EFW_OK;
}}

/* ==================================================================
 *  系统函数
 * ================================================================== */

uint32_t efw_hal_get_time_us(void)
{{
    /* TODO: 实现获取系统时间 */
    return 0;
}}

void efw_hal_delay_ms(uint32_t ms)
{{
    /* TODO: 实现毫秒延时 */
}}

void efw_hal_delay_us(uint32_t us)
{{
    /* TODO: 实现微秒延时 */
}}
'''
    
    def _generate_startup(
        self,
        chip_config: dict,
        firmware_config: dict,
    ) -> Optional[Path]:
        """生成启动代码"""
        chip_name = chip_config.get("name", "")
        
        # Copy vendor startup code from the installed firmware package when available.
        startup_dir = firmware_config.get("startup_dir")
        if startup_dir:
            startup_path = Path(startup_dir)
            if startup_path.exists():
                chip_name_lower = chip_name.lower()
                
                for f in startup_path.glob("*.s"):
                    if chip_name_lower.replace("xx", "") in f.name.lower():
                        dest = self.project_dir / "startup.s"
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        
                        import shutil
                        shutil.copy2(f, dest)
                        
                        return dest
        
        return None
    
    def _generate_linker_script(
        self,
        chip_config: dict,
        firmware_config: dict,
    ) -> Optional[Path]:
        """生成链接脚本"""
        chip_name = chip_config.get("name", "")
        
        # Prefer vendor linker scripts when present; otherwise generate a local
        # linker script from the chip data bundled in data/mcu.
        linker_dir = firmware_config.get("linker_dir")
        if linker_dir:
            linker_path = Path(linker_dir)
            if linker_path.exists():
                chip_name_lower = chip_name.lower()
                
                for f in linker_path.glob("*.ld"):
                    if chip_name_lower.replace("xx", "") in f.name.lower():
                        dest = self.project_dir / "linker.ld"
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        
                        import shutil
                        shutil.copy2(f, dest)
                        
                        return dest
        
        # 3. 如果都没有，生成通用链接脚本
        return self._generate_generic_linker(chip_config)
    
    def _generate_generic_linker(self, chip_config: dict) -> Path:
        """生成通用链接脚本"""
        flash_size = chip_config.get("flash_kb", 1024)
        ram_size = chip_config.get("ram_kb", 256)
        
        content = f'''/*
 * 链接脚本 - {chip_config.get("name", "Unknown")}
 * 自动生成
 */

ENTRY(Reset_Handler)

MEMORY
{{
    FLASH (rx) : ORIGIN = 0x08000000, LENGTH = {flash_size}K
    RAM (xrw) : ORIGIN = 0x20000000, LENGTH = {ram_size}K
}}

SECTIONS
{{
    .text :
    {{
        . = ALIGN(4);
        KEEP(*(.isr_vector))
        *(.text)
        *(.text*)
        *(.rodata)
        *(.rodata*)
        . = ALIGN(4);
        _etext = .;
    }} >FLASH

    .data :
    {{
        . = ALIGN(4);
        _sdata = .;
        *(.data)
        *(.data*)
        . = ALIGN(4);
        _edata = .;
    }} >RAM AT> FLASH

    .bss :
    {{
        . = ALIGN(4);
        _sbss = .;
        *(.bss)
        *(.bss*)
        *(COMMON)
        . = ALIGN(4);
        _ebss = .;
    }} >RAM

    _sidata = LOADADDR(.data);

    .heap :
    {{
        . = ALIGN(8);
        __end__ = .;
        . = . + 0x2000;
        . = ALIGN(8);
        __heap_end__ = .;
    }} >RAM

    .stack :
    {{
        . = ALIGN(8);
        . = . + 0x4000;
        . = ALIGN(8);
        _estack = .;
    }} >RAM
}}
'''
        
        dest = self.project_dir / "linker.ld"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
        
        return dest
    
    def _generate_system_config(
        self,
        chip_config: dict,
        firmware_config: dict,
    ) -> Path:
        """生成系统配置"""
        content = f'''/**
 * @file    system_config.h
 * @brief   系统配置 - 自动生成
 * @chip    {chip_config.get("name", "Unknown")}
 */

#ifndef SYSTEM_CONFIG_H
#define SYSTEM_CONFIG_H

/* 芯片信息 */
#define CHIP_FAMILY         "{chip_config.get("family", "")}"
#define CHIP_NAME           "{chip_config.get("name", "")}"
#define CHIP_CORE           "{chip_config.get("core", "")}"
#define CHIP_FREQUENCY_MHZ  {chip_config.get("frequency_mhz", 168)}
#define CHIP_FLASH_KB       {chip_config.get("flash_kb", 1024)}
#define CHIP_RAM_KB         {chip_config.get("ram_kb", 256)}

/* 时钟配置 */
#define SYSCLK_MHZ          {chip_config.get("frequency_mhz", 168)}
#define HCLK_MHZ            {chip_config.get("frequency_mhz", 168)}
#define PCLK1_MHZ           {chip_config.get("frequency_mhz", 168) / 4}
#define PCLK2_MHZ           {chip_config.get("frequency_mhz", 168) / 2}

/* 外设配置 */
#define EFW_ENABLE_HAL       1
#define EFW_ENABLE_COMM      1
#define EFW_ENABLE_MODULE    1
#define EFW_ENABLE_SENSOR    1
#define EFW_ENABLE_ACTUATOR  1
#define EFW_ENABLE_ALGORITHM 1

/* 容量配置 */
#define EFW_MAX_HAL          16
#define EFW_MAX_COMMS        16
#define EFW_MAX_MODULES      32
#define EFW_MAX_SENSORS      32
#define EFW_MAX_ACTUATORS    16
#define EFW_MAX_ALGOS        16

#endif /* SYSTEM_CONFIG_H */
'''
        
        dest = self.project_dir / "include" / "system_config.h"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
        
        # 生成 HAL 配置文件
        self._generate_hal_conf(firmware_config)
        
        return dest
    
    def _generate_hal_conf(self, firmware_config: dict):
        """生成 HAL 配置文件并复制到固件库目录"""
        family = firmware_config.get("name", "stm32f4").upper()
        
        # 根据芯片系列生成不同的 HAL 配置
        if "STM32F4" in family:
            hal_conf_content = '''/**
 * @file    stm32f4xx_hal_conf.h
 * @brief   HAL 配置文件 - 自动生成
 */

#ifndef __STM32F4xx_HAL_CONF_H
#define __STM32F4xx_HAL_CONF_H

#ifdef __cplusplus
extern "C" {
#endif

/* 包含 HAL 定义文件 */
#include "stm32f4xx_hal_def.h"

/* 模块使能 */
#define HAL_MODULE_ENABLED
#define HAL_GPIO_MODULE_ENABLED
#define HAL_DMA_MODULE_ENABLED
#define HAL_RCC_MODULE_ENABLED
#define HAL_FLASH_MODULE_ENABLED
#define HAL_PWR_MODULE_ENABLED
#define HAL_CORTEX_MODULE_ENABLED
#define HAL_TIM_MODULE_ENABLED
#define HAL_UART_MODULE_ENABLED
#define HAL_ADC_MODULE_ENABLED
#define HAL_SPI_MODULE_ENABLED
#define HAL_I2C_MODULE_ENABLED

/* 振荡器参数 */
#define HSE_VALUE    8000000U
#define HSE_STARTUP_TIMEOUT  100U
#define HSI_VALUE    16000000U
#define LSE_VALUE    32768U
#define LSE_STARTUP_TIMEOUT  5000U
#define LSI_VALUE    32000U
#define EXTERNAL_CLOCK_VALUE  12288000U

/* System Configuration */
#define VDD_VALUE                    3300U
#define TICK_INT_PRIORITY            0x0FU
#define USE_RTOS                     0U
#define PREFETCH_ENABLE              1U
#define INSTRUCTION_CACHE_ENABLE     1U
#define DATA_CACHE_ENABLE            1U

/* 断言处理 */
#define assert_param(expr) ((void)0U)

#ifdef __cplusplus
}
#endif

#endif /* __STM32F4xx_HAL_CONF_H */
'''
        else:
            # 通用配置
            hal_conf_content = '''/**
 * @file    stm32_hal_conf.h
 * @brief   HAL 配置文件 - 自动生成
 */

#ifndef __STM32_HAL_CONF_H
#define __STM32_HAL_CONF_H

#define HAL_MODULE_ENABLED
#define HAL_GPIO_MODULE_ENABLED
#define HAL_RCC_MODULE_ENABLED

#define HSE_VALUE    8000000U
#define HSI_VALUE    16000000U
#define VDD_VALUE    3300U

#define assert_param(expr) ((void)0U)

#endif
'''
        
        # 保存到项目 include 目录
        hal_conf_path = self.project_dir / "include" / "stm32f4xx_hal_conf.h"
        hal_conf_path.write_text(hal_conf_content)
        
        # Do not modify the installed firmware package. Project-local include/
        # must be placed before vendor include directories by the generated build.


# ─── 便捷函数 ────────────────────────────────────────────────────────────────

def integrate_firmware(
    chip: str,
    project_dir: Path,
    firmware_name: Optional[str] = None,
    firmware_root: Optional[Path] = None,
) -> dict[str, Path]:
    """集成固件到项目
    
    Args:
        chip: 芯片名称
        project_dir: 项目目录
        firmware_name: 固件名称（可选）
        firmware_root: 固件库根目录（可选）
    
    Returns:
        生成的文件路径字典
    """
    integrator = FirmwareIntegrator(project_dir, firmware_root)
    return integrator.generate_all(chip, firmware_name)
