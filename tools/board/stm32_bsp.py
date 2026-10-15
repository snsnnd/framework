"""Generate a minimal STM32 BSP from a resolved Board Profile."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.target import REPO_ROOT, TargetDescriptor


class BSPGenerationError(ValueError):
    """Raised when Board Profile data is insufficient for safe BSP generation."""


@dataclass(frozen=True)
class GeneratedBSP:
    source: Path
    hal_config: Path


def load_board_profile(name: str) -> dict[str, Any]:
    path = REPO_ROOT / "data" / "board_profiles" / f"{name}.json"
    if not path.is_file():
        raise BSPGenerationError(f"Board Profile 不存在: {name}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise BSPGenerationError(f"Board Profile 必须是 JSON object: {name}")
    return data


def _pin_parts(pin: str) -> tuple[str, int]:
    match = re.fullmatch(r"P([A-Z])(\d{1,2})", pin)
    if match is None or int(match.group(2)) > 15:
        raise BSPGenerationError(f"无效 GPIO 引脚: {pin}")
    return match.group(1), int(match.group(2))


def _clock_divider(hclk: int, pclk: int) -> int:
    if hclk <= 0 or pclk <= 0 or hclk % pclk != 0:
        raise BSPGenerationError(f"无效总线时钟: HCLK={hclk}MHz, PCLK={pclk}MHz")
    divider = hclk // pclk
    if divider not in {1, 2, 4, 8, 16}:
        raise BSPGenerationError(f"不支持的 APB 分频: {divider}")
    return divider


def _hal_config(family_lower: str) -> str:
    guard = f"__{family_lower.upper()}XX_HAL_CONF_H"
    return f"""#ifndef {guard}
#define {guard}

#define HAL_MODULE_ENABLED
#define HAL_CORTEX_MODULE_ENABLED
#define HAL_FLASH_MODULE_ENABLED
#define HAL_GPIO_MODULE_ENABLED
#define HAL_PWR_MODULE_ENABLED
#define HAL_RCC_MODULE_ENABLED

#ifndef HSE_VALUE
#define HSE_VALUE 8000000U
#endif
#define HSE_STARTUP_TIMEOUT 100U
#ifndef HSI_VALUE
#define HSI_VALUE 16000000U
#endif
#ifndef HSI48_VALUE
#define HSI48_VALUE 48000000U
#endif
#define LSI_VALUE 32000U
#define LSE_VALUE 32768U
#define LSE_STARTUP_TIMEOUT 5000U
#define EXTERNAL_CLOCK_VALUE 12288000U
#define VDD_VALUE 3300U
#define TICK_INT_PRIORITY 0x0FU
#define USE_RTOS 0U
#define PREFETCH_ENABLE 1U
#define INSTRUCTION_CACHE_ENABLE 1U
#define DATA_CACHE_ENABLE 1U
#define assert_param(expr) ((void)0U)

#include "{family_lower}xx_hal_rcc.h"
#include "{family_lower}xx_hal_gpio.h"
#include "{family_lower}xx_hal_cortex.h"
#include "{family_lower}xx_hal_flash.h"
#include "{family_lower}xx_hal_pwr.h"

#endif
"""


def _f1_clock(clock: dict[str, Any]) -> str:
    bypass = bool(clock.get("bypass"))
    pll = clock["pll"]
    return f"""    osc.OscillatorType = RCC_OSCILLATORTYPE_HSE;
    osc.HSEState = {'RCC_HSE_BYPASS' if bypass else 'RCC_HSE_ON'};
    osc.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
    osc.PLL.PLLState = RCC_PLL_ON;
    osc.PLL.PLLSource = RCC_PLLSOURCE_HSE;
    osc.PLL.PLLMUL = RCC_PLL_MUL{int(pll['n'])};
"""


def _f4_clock(clock: dict[str, Any]) -> tuple[str, str]:
    bypass = bool(clock.get("bypass"))
    pll = clock["pll"]
    setup = f"""    __HAL_RCC_PWR_CLK_ENABLE();
    __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);
    osc.OscillatorType = RCC_OSCILLATORTYPE_HSE;
    osc.HSEState = {'RCC_HSE_BYPASS' if bypass else 'RCC_HSE_ON'};
    osc.PLL.PLLState = RCC_PLL_ON;
    osc.PLL.PLLSource = RCC_PLLSOURCE_HSE;
    osc.PLL.PLLM = {int(pll['m'])};
    osc.PLL.PLLN = {int(pll['n'])};
    osc.PLL.PLLP = RCC_PLLP_DIV{int(pll['p'])};
    osc.PLL.PLLQ = {int(pll['q'])};
"""
    after_osc = ""
    if int(clock["sysclk_mhz"]) > 168:
        after_osc = "    if (HAL_PWREx_EnableOverDrive() != HAL_OK) return EFW_ERR_IO;\n"
    return setup, after_osc


def _g4_clock(clock: dict[str, Any]) -> str:
    pll = clock["pll"]
    return f"""    __HAL_RCC_PWR_CLK_ENABLE();
    if (HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1_BOOST) != HAL_OK) return EFW_ERR_IO;
    osc.OscillatorType = RCC_OSCILLATORTYPE_HSI;
    osc.HSIState = RCC_HSI_ON;
    osc.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
    osc.PLL.PLLState = RCC_PLL_ON;
    osc.PLL.PLLSource = RCC_PLLSOURCE_HSI;
    osc.PLL.PLLM = RCC_PLLM_DIV{int(pll['m'])};
    osc.PLL.PLLN = {int(pll['n'])};
    osc.PLL.PLLP = RCC_PLLP_DIV{int(pll['p'])};
    osc.PLL.PLLQ = RCC_PLLQ_DIV{int(pll['q'])};
    osc.PLL.PLLR = RCC_PLLR_DIV{int(pll['r'])};
"""


def _gpio_init(route: dict[str, Any], mode: str) -> str:
    if not route:
        return ""
    port, pin = _pin_parts(str(route["pin"]))
    active = str(route.get("active", "high"))
    initial = "GPIO_PIN_SET" if active == "low" else "GPIO_PIN_RESET"
    write = f"    HAL_GPIO_WritePin(GPIO{port}, GPIO_PIN_{pin}, {initial});\n" if mode == "GPIO_MODE_OUTPUT_PP" else ""
    pull = "GPIO_PULLUP" if mode == "GPIO_MODE_INPUT" and active == "low" else "GPIO_PULLDOWN" if mode == "GPIO_MODE_INPUT" else "GPIO_NOPULL"
    return f"""    __HAL_RCC_GPIO{port}_CLK_ENABLE();
{write}    gpio.Pin = GPIO_PIN_{pin};
    gpio.Mode = {mode};
    gpio.Pull = {pull};
    gpio.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIO{port}, &gpio);
"""


def render_stm32_bsp(target: TargetDescriptor, profile: dict[str, Any]) -> tuple[str, str]:
    clock = profile.get("clock")
    if not isinstance(clock, dict) or not isinstance(clock.get("pll"), dict):
        raise BSPGenerationError(f"目标 {target.chip} 的 Board Profile 缺少 clock.pll")
    family_lower = target.family.lower()
    if target.family == "STM32F1":
        clock_setup = _f1_clock(clock)
        after_osc = ""
    elif target.family == "STM32F4":
        clock_setup, after_osc = _f4_clock(clock)
    elif target.family == "STM32G4":
        clock_setup = _g4_clock(clock)
        after_osc = ""
    else:
        raise BSPGenerationError(f"自动 BSP 暂不支持系列: {target.family}")
    hclk = int(clock["hclk_mhz"])
    if int(clock["sysclk_mhz"]) != hclk:
        raise BSPGenerationError("自动 BSP 仅支持 SYSCLK 与 HCLK 相同的配置")
    apb1 = _clock_divider(hclk, int(clock["pclk1_mhz"]))
    apb2 = _clock_divider(hclk, int(clock["pclk2_mhz"]))
    pins = profile.get("pins", {})
    source = f"""/* Generated from EFW target {target.chip} and Board Profile. */
#include "efw/efw.h"
#include "{family_lower}xx_hal.h"

efw_status_t app_board_init(void) {{
    RCC_ClkInitTypeDef clk = {{0}};
    RCC_OscInitTypeDef osc = {{0}};
    GPIO_InitTypeDef gpio = {{0}};

    HAL_Init();
{clock_setup}    if (HAL_RCC_OscConfig(&osc) != HAL_OK) return EFW_ERR_IO;
{after_osc}    clk.ClockType = RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    clk.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    clk.AHBCLKDivider = RCC_SYSCLK_DIV1;
    clk.APB1CLKDivider = RCC_HCLK_DIV{apb1};
    clk.APB2CLKDivider = RCC_HCLK_DIV{apb2};
    if (HAL_RCC_ClockConfig(&clk, FLASH_LATENCY_{int(clock['flash_latency'])}) != HAL_OK) return EFW_ERR_IO;
{_gpio_init(pins.get('led', {}), 'GPIO_MODE_OUTPUT_PP')}{_gpio_init(pins.get('button', {}), 'GPIO_MODE_INPUT')}    return EFW_OK;
}}
"""
    return source, _hal_config(family_lower)


def generate_stm32_bsp(project_dir: Path, target: TargetDescriptor, board_profile: str) -> GeneratedBSP:
    from tools.target import resolve_target

    resolve_target(chip=target.chip, board_profile=board_profile)
    if not (REPO_ROOT / "data" / "board_profiles" / f"{board_profile}.json").is_file():
        raise BSPGenerationError(
            f"Board Profile {board_profile} 不是可自动生成 BSP 的具体板卡；请选择具体板卡或提供 app_board_init() 和 HAL 配置"
        )
    profile = load_board_profile(board_profile)
    source_text, config_text = render_stm32_bsp(target, profile)
    generated_dir = project_dir / ".efw_target"
    include_dir = generated_dir / "include"
    include_dir.mkdir(parents=True, exist_ok=True)
    source = generated_dir / "board_adapter.c"
    hal_config = include_dir / f"{target.family.lower()}xx_hal_conf.h"
    source.write_text(source_text, encoding="utf-8")
    hal_config.write_text(config_text, encoding="utf-8")
    return GeneratedBSP(source=source, hal_config=hal_config)
