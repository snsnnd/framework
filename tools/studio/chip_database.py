#!/usr/bin/env python3
"""Chip database and wizard for EFW Studio.

Provides:
- Built-in chip database with common MCU configurations
- Chip selection wizard with vendor/series/model hierarchy
- Import from CubeMX .ioc, ESP-IDF sdkconfig, and other formats
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


# ─── Built-in Chip Database ──────────────────────────────────────────────────

CHIP_DATABASE: dict[str, dict[str, Any]] = {
    # ── STM32 Series ──────────────────────────────────────────────────────
    "stm32f103c8": {
        "vendor": "ST",
        "series": "STM32F1",
        "model": "STM32F103C8",
        "label": "STM32F103C8T6 (Blue Pill)",
        "package": "LQFP48",
        "flash_kb": 64,
        "ram_kb": 20,
        "clock_mhz": 72,
        "ports": ["A", "B", "C"],
        "pins_per_port": 16,
        "timers": [1, 2, 3, 4],
        "pwm_channels": [1, 2, 3, 4],
        "uart": [1, 2, 3],
        "i2c": [1, 2],
        "spi": [1, 2],
        "adc": [1],
        "notes": "经典入门MCU，适合学习和小型项目。",
    },
    "stm32f103rct6": {
        "vendor": "ST",
        "series": "STM32F1",
        "model": "STM32F103RCT6",
        "label": "STM32F103RCT6 (中容量)",
        "package": "LQFP64",
        "flash_kb": 256,
        "ram_kb": 48,
        "clock_mhz": 72,
        "ports": ["A", "B", "C", "D"],
        "pins_per_port": 16,
        "timers": [1, 2, 3, 4, 5, 6, 7, 8],
        "pwm_channels": [1, 2, 3, 4],
        "uart": [1, 2, 3, 4, 5],
        "i2c": [1, 2],
        "spi": [1, 2, 3],
        "adc": [1, 2, 3],
        "notes": "中容量MCU，引脚和资源更丰富。",
    },
    "stm32f407vgt6": {
        "vendor": "ST",
        "series": "STM32F4",
        "model": "STM32F407VGT6",
        "label": "STM32F407VGT6 (Discovery)",
        "package": "LQFP100",
        "flash_kb": 1024,
        "ram_kb": 192,
        "clock_mhz": 168,
        "ports": ["A", "B", "C", "D", "E"],
        "pins_per_port": 16,
        "timers": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14],
        "pwm_channels": [1, 2, 3, 4],
        "uart": [1, 2, 3, 4, 5, 6],
        "i2c": [1, 2, 3],
        "spi": [1, 2, 3],
        "adc": [1, 2, 3],
        "notes": "高性能MCU，带FPU和DSP指令，适合电机控制和信号处理。",
    },
    "stm32g431cb": {
        "vendor": "ST",
        "series": "STM32G4",
        "model": "STM32G431CB",
        "label": "STM32G431CB (Nucleo-64)",
        "package": "LQFP48",
        "flash_kb": 128,
        "ram_kb": 32,
        "clock_mhz": 170,
        "ports": ["A", "B", "C"],
        "pins_per_port": 16,
        "timers": [1, 2, 3, 4, 5, 6, 7, 8, 15, 16, 17, 20],
        "pwm_channels": [1, 2, 3, 4, 5],
        "uart": [1, 2, 3, 4, 5],
        "i2c": [1, 2, 3, 4],
        "spi": [1, 2, 3, 4],
        "adc": [1, 2, 3, 4, 5],
        "notes": "电机控制专用MCU，带高精度ADC和高级定时器。",
    },
    "stm32h743vit6": {
        "vendor": "ST",
        "series": "STM32H7",
        "model": "STM32H743VIT6",
        "label": "STM32H743VIT6 (高性能)",
        "package": "LQFP100",
        "flash_kb": 2048,
        "ram_kb": 1024,
        "clock_mhz": 480,
        "ports": ["A", "B", "C", "D", "E"],
        "pins_per_port": 16,
        "timers": [1, 2, 3, 4, 5, 6, 7, 8, 12, 13, 14, 15, 16, 17],
        "pwm_channels": [1, 2, 3, 4],
        "uart": [1, 2, 3, 4, 5, 6, 7, 8],
        "i2c": [1, 2, 3, 4],
        "spi": [1, 2, 3, 4, 5, 6],
        "adc": [1, 2, 3],
        "notes": "超高性能MCU，适合复杂算法和高速通信。",
    },

    # ── ESP32 Series ──────────────────────────────────────────────────────
    "esp32": {
        "vendor": "Espressif",
        "series": "ESP32",
        "model": "ESP32",
        "label": "ESP32 (经典双核)",
        "package": "QFN48",
        "flash_kb": 4096,
        "ram_kb": 520,
        "clock_mhz": 240,
        "ports": ["GPIO"],
        "pins_per_port": 34,
        "timers": [0, 1, 2, 3],
        "pwm_channels": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
        "uart": [0, 1, 2],
        "i2c": [0, 1],
        "spi": [1, 2, 3],
        "adc": [1, 2],
        "wifi": True,
        "bluetooth": True,
        "notes": "经典WiFi+蓝牙MCU，适合IoT项目。",
    },
    "esp32s3": {
        "vendor": "Espressif",
        "series": "ESP32-S",
        "model": "ESP32-S3",
        "label": "ESP32-S3 (AI增强)",
        "package": "QFN56",
        "flash_kb": 8192,
        "ram_kb": 512,
        "clock_mhz": 240,
        "ports": ["GPIO"],
        "pins_per_port": 45,
        "timers": [0, 1, 2, 3],
        "pwm_channels": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
        "uart": [0, 1, 2],
        "i2c": [0, 1],
        "spi": [0, 1, 2, 3],
        "adc": [1, 2],
        "wifi": True,
        "bluetooth": True,
        "usb": True,
        "notes": "带AI加速和USB OTG，适合AIoT项目。",
    },
    "esp32c3": {
        "vendor": "Espressif",
        "series": "ESP32-C",
        "model": "ESP32-C3",
        "label": "ESP32-C3 (低功耗)",
        "package": "QFN32",
        "flash_kb": 4096,
        "ram_kb": 400,
        "clock_mhz": 160,
        "ports": ["GPIO"],
        "pins_per_port": 22,
        "timers": [0, 1],
        "pwm_channels": [0, 1, 2, 3, 4, 5],
        "uart": [0, 1],
        "i2c": [0],
        "spi": [0, 1],
        "adc": [1],
        "wifi": True,
        "bluetooth": True,
        "notes": "RISC-V架构，低功耗低成本。",
    },

    # ── MSPM0 Series ──────────────────────────────────────────────────────
    "mspm0g3507": {
        "vendor": "TI",
        "series": "MSPM0",
        "model": "MSPM0G3507",
        "label": "MSPM0G3507 (LaunchPad)",
        "package": "LQFP48",
        "flash_kb": 128,
        "ram_kb": 32,
        "clock_mhz": 80,
        "ports": ["A", "B"],
        "pins_per_port": 16,
        "timers": [0, 1, 2, 3],
        "pwm_channels": [0, 1, 2, 3],
        "uart": [0, 1, 2],
        "i2c": [0, 1],
        "spi": [0, 1],
        "adc": [0, 1],
        "notes": "TI低功耗MCU，适合电池供电项目。",
    },
    "mspm0l1306": {
        "vendor": "TI",
        "series": "MSPM0",
        "model": "MSPM0L1306",
        "label": "MSPM0L1306 (超低功耗)",
        "package": "SOP16",
        "flash_kb": 32,
        "ram_kb": 4,
        "clock_mhz": 32,
        "ports": ["A", "B"],
        "pins_per_port": 8,
        "timers": [0, 1],
        "pwm_channels": [0, 1],
        "uart": [0],
        "i2c": [0],
        "spi": [0],
        "adc": [0],
        "notes": "超低功耗MCU，适合传感器节点。",
    },

    # ── Arduino Series ────────────────────────────────────────────────────
    "arduino_nano": {
        "vendor": "Arduino",
        "series": "AVR",
        "model": "ATmega328P",
        "label": "Arduino Nano (ATmega328P)",
        "package": "TQFP32",
        "flash_kb": 32,
        "ram_kb": 2,
        "clock_mhz": 16,
        "ports": ["D", "B", "C"],
        "pins_per_port": 8,
        "timers": [0, 1, 2],
        "pwm_channels": [3, 5, 6, 9, 10, 11],
        "uart": [0],
        "i2c": [0],
        "spi": [0],
        "adc": [0, 1, 2, 3, 4, 5, 6, 7],
        "notes": "经典入门开发板，适合学习和原型验证。",
    },
    "arduino_mega": {
        "vendor": "Arduino",
        "series": "AVR",
        "model": "ATmega2560",
        "label": "Arduino Mega (ATmega2560)",
        "package": "TQFP100",
        "flash_kb": 256,
        "ram_kb": 8,
        "clock_mhz": 16,
        "ports": ["A", "B", "C", "D", "E", "F", "G", "H", "J", "K", "L"],
        "pins_per_port": 8,
        "timers": [0, 1, 2, 3, 4, 5],
        "pwm_channels": [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 44, 45, 46],
        "uart": [0, 1, 2, 3],
        "i2c": [0],
        "spi": [0],
        "adc": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
        "notes": "资源丰富的开发板，适合大型项目。",
    },
}


# ─── Chip Query Functions ────────────────────────────────────────────────────

def get_vendors() -> list[str]:
    """Get list of unique vendors."""
    return sorted(set(chip["vendor"] for chip in CHIP_DATABASE.values()))


def get_series(vendor: str | None = None) -> list[str]:
    """Get list of series, optionally filtered by vendor."""
    if vendor:
        return sorted(set(chip["series"] for chip in CHIP_DATABASE.values() if chip["vendor"] == vendor))
    return sorted(set(chip["series"] for chip in CHIP_DATABASE.values()))


def get_models(vendor: str | None = None, series: str | None = None) -> list[str]:
    """Get list of models, optionally filtered by vendor/series."""
    result = []
    for chip_id, chip in CHIP_DATABASE.items():
        if vendor and chip["vendor"] != vendor:
            continue
        if series and chip["series"] != series:
            continue
        result.append(chip_id)
    return sorted(result)


def get_chip_info(chip_id: str) -> dict[str, Any] | None:
    """Get chip information by ID."""
    return CHIP_DATABASE.get(chip_id)


def chip_to_board_profile(chip_id: str) -> dict[str, Any] | None:
    """Convert chip info to EFW board profile format."""
    chip = get_chip_info(chip_id)
    if not chip:
        return None
    
    return {
        "label": chip["label"],
        "ports": chip["ports"],
        "pins_per_port": chip["pins_per_port"],
        "timers": chip["timers"],
        "pwm_channels": chip["pwm_channels"],
        "notes": chip.get("notes", ""),
        "_chip_info": {
            "vendor": chip["vendor"],
            "series": chip["series"],
            "model": chip["model"],
            "package": chip.get("package", ""),
            "flash_kb": chip.get("flash_kb", 0),
            "ram_kb": chip.get("ram_kb", 0),
            "clock_mhz": chip.get("clock_mhz", 0),
            "uart": chip.get("uart", []),
            "i2c": chip.get("i2c", []),
            "spi": chip.get("spi", []),
            "adc": chip.get("adc", []),
        }
    }


# ─── Import Functions ────────────────────────────────────────────────────────

def import_from_ioc(content: str) -> dict[str, Any] | None:
    """Import configuration from STM32CubeMX .ioc file."""
    config: dict[str, Any] = {
        "ports": [],
        "timers": [],
        "pwm_channels": [],
        "uart": [],
        "i2c": [],
        "spi": [],
        "adc": [],
    }
    
    # Parse MCU type
    mcu_match = re.search(r'Mcu\.Name=STM32\w+', content)
    if mcu_match:
        mcu_name = mcu_match.group().split('=')[1]
        config["mcu"] = mcu_name
    
    # Parse GPIO pins
    gpio_pins: dict[str, set] = {}
    for match in re.finditer(r'P(\w)\d+\.GPIOParameters', content):
        port = match.group(1)
        if port not in gpio_pins:
            gpio_pins[port] = set()
    
    for port in sorted(gpio_pins.keys()):
        config["ports"].append(port)
    
    # Parse timers
    for match in re.finditer(r'(TIM\d+)\.Channel=(\w+)', content):
        timer = match.group(1)
        channel = match.group(2)
        timer_num = int(timer.replace('TIM', ''))
        if timer_num not in config["timers"]:
            config["timers"].append(timer_num)
        config["pwm_channels"].append(f"{timer}_{channel}")
    
    # Parse UART
    for match in re.finditer(r'(USART\d+|UART\d+)\.Mode', content):
        uart = match.group(1)
        uart_num = int(re.search(r'\d+', uart).group())
        if uart_num not in config["uart"]:
            config["uart"].append(uart_num)
    
    # Parse I2C
    for match in re.finditer(r'I2C\d+\.Mode', content):
        i2c_num = int(re.search(r'\d+', match.group()).group())
        if i2c_num not in config["i2c"]:
            config["i2c"].append(i2c_num)
    
    # Parse SPI
    for match in re.finditer(r'SPI\d+\.Mode', content):
        spi_num = int(re.search(r'\d+', match.group()).group())
        if spi_num not in config["spi"]:
            config["spi"].append(spi_num)
    
    return config if config["ports"] else None


def import_from_sdkconfig(content: str) -> dict[str, Any] | None:
    """Import configuration from ESP-IDF sdkconfig file."""
    config: dict[str, Any] = {
        "mcu": "ESP32",
        "ports": ["GPIO"],
        "pins_per_port": 34,
        "timers": [0, 1, 2, 3],
        "pwm_channels": list(range(16)),
        "uart": [0, 1, 2],
        "i2c": [0, 1],
        "spi": [1, 2, 3],
        "adc": [1, 2],
    }
    
    # Detect chip type
    if "CONFIG_IDF_TARGET_ESP32S3=y" in content:
        config["mcu"] = "ESP32-S3"
        config["pins_per_port"] = 45
    elif "CONFIG_IDF_TARGET_ESP32C3=y" in content:
        config["mcu"] = "ESP32-C3"
        config["pins_per_port"] = 22
        config["timers"] = [0, 1]
        config["pwm_channels"] = list(range(6))
    
    # Parse custom settings
    for match in re.finditer(r'CONFIG_ESP_CONSOLE_UART_NUM=(\d+)', content):
        config["uart_primary"] = int(match.group(1))
    
    return config


def import_from_json(data: dict[str, Any]) -> dict[str, Any] | None:
    """Import configuration from generic JSON format."""
    if "board" in data:
        board = data["board"]
        return {
            "mcu": board.get("mcu", board.get("profile", "unknown")),
            "ports": board.get("ports", ["A", "B", "C"]),
            "pins_per_port": board.get("pins_per_port", 16),
            "timers": board.get("timers", [1, 2, 3, 4]),
            "pwm_channels": board.get("pwm_channels", [1, 2, 3, 4]),
        }
    
    if "ports" in data or "timers" in data:
        return data
    
    return None


def detect_and_import(file_path: Path) -> tuple[dict[str, Any] | None, str]:
    """Detect file format and import configuration."""
    content = file_path.read_text(encoding="utf-8", errors="ignore")
    suffix = file_path.suffix.lower()
    
    # STM32CubeMX .ioc file
    if suffix == ".ioc" or "Mcu.Name=STM32" in content:
        result = import_from_ioc(content)
        if result:
            return result, "STM32CubeMX .ioc"
    
    # ESP-IDF sdkconfig
    if file_path.name == "sdkconfig" or "CONFIG_IDF_TARGET" in content:
        result = import_from_sdkconfig(content)
        if result:
            return result, "ESP-IDF sdkconfig"
    
    # Generic JSON
    if suffix == ".json":
        try:
            data = json.loads(content)
            result = import_from_json(data)
            if result:
                return result, "JSON"
        except json.JSONDecodeError:
            pass
    
    return None, "未知格式"
