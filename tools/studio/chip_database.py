#!/usr/bin/env python3
"""Chip database and wizard for EFW Studio.

Provides:
- Chip database loaded from data/mcu/ directory
- Chip selection wizard with vendor/series/model hierarchy
- Import from CubeMX .ioc, ESP-IDF sdkconfig, and other formats
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


# ─── Data Directory ──────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent.parent.parent / "data"
MCU_DIR = DATA_DIR / "mcu"


# ─── Chip Database Loader ───────────────────────────────────────────────────

def _load_chip_database() -> dict[str, dict[str, Any]]:
    """Load chip database from data/mcu/ directory."""
    database = {}
    
    index_path = MCU_DIR / "index.json"
    if not index_path.exists():
        return database
    
    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)
    
    for chip_name, chip_index in index.items():
        chip_path = MCU_DIR / chip_index['path']
        if not chip_path.exists():
            continue
        
        with open(chip_path, "r", encoding="utf-8") as f:
            chip_data = json.load(f)
        
        # 转换为 Studio 格式
        chip_id = chip_name.lower().replace('-', '_').replace('(', '_').replace(')', '')
        
        # 提取端口列表
        ports = []
        for pin_name in chip_data.get('gpio_pins', []):
            port = re.match(r'P([A-Z])', pin_name)
            if port and port.group(1) not in ports:
                ports.append(port.group(1))
        
        # 提取定时器列表
        timers = set()
        for tim in chip_data.get('peripherals', {}).get('pwm', {}).get('outputs', {}).keys():
            match = re.match(r'TIM(\d+)', tim)
            if match:
                timers.add(int(match.group(1)))
        
        # 提取 UART 列表
        uart_ports = []
        for uart in chip_data.get('peripherals', {}).get('uart', {}).get('ports', {}).keys():
            match = re.match(r'UART(\d+)', uart)
            if match:
                uart_ports.append(int(match.group(1)))
        
        # 提取 I2C 列表
        i2c_ports = []
        for i2c in chip_data.get('peripherals', {}).get('i2c', {}).get('ports', {}).keys():
            match = re.match(r'I2C(\d+)', i2c)
            if match:
                i2c_ports.append(int(match.group(1)))
        
        # 提取 SPI 列表
        spi_ports = []
        for spi in chip_data.get('peripherals', {}).get('spi', {}).get('ports', {}).keys():
            match = re.match(r'SPI(\d+)', spi)
            if match:
                spi_ports.append(int(match.group(1)))
        
        database[chip_id] = {
            "vendor": "ST",
            "series": chip_data.get('family', ''),
            "model": chip_name,
            "label": f"{chip_name} ({chip_data.get('board', '')})",
            "package": chip_data.get('package', ''),
            "flash_kb": chip_data.get('flash_kb', 0),
            "ram_kb": chip_data.get('ram_kb', 0),
            "clock_mhz": chip_data.get('frequency_mhz', 0),
            "core": chip_data.get('core', ''),
            "ports": ports,
            "pins_per_port": 16,
            "gpio_count": chip_data.get('gpio_count', 0),
            "gpio_pins": chip_data.get('gpio_pins', []),
            "timers": sorted(timers),
            "pwm_channels": list(chip_data.get('peripherals', {}).get('pwm', {}).get('outputs', {}).keys()),
            "uart": sorted(uart_ports),
            "i2c": sorted(i2c_ports),
            "spi": sorted(spi_ports),
            "adc_channels": chip_data.get('peripherals', {}).get('adc', {}).get('channels', {}),
            "peripherals": chip_data.get('peripherals', {}),
            "pins": chip_data.get('pins', {}),
            "board": chip_data.get('board', ''),
            "path": chip_index['path'],
        }
    
    return database


# 加载数据库
CHIP_DATABASE = _load_chip_database()


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


def get_all_chips() -> dict[str, dict[str, Any]]:
    """Get all chips in database."""
    return CHIP_DATABASE.copy()


def reload_database() -> None:
    """Reload chip database from disk."""
    global CHIP_DATABASE
    CHIP_DATABASE = _load_chip_database()


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
        "gpio_pins": chip.get("gpio_pins", []),
        "peripherals": chip.get("peripherals", {}),
        "notes": chip.get("notes", ""),
        "_chip_info": {
            "vendor": chip["vendor"],
            "series": chip["series"],
            "model": chip["model"],
            "package": chip.get("package", ""),
            "flash_kb": chip.get("flash_kb", 0),
            "ram_kb": chip.get("ram_kb", 0),
            "clock_mhz": chip.get("clock_mhz", 0),
            "core": chip.get("core", ""),
            "uart": chip.get("uart", []),
            "i2c": chip.get("i2c", []),
            "spi": chip.get("spi", []),
            "adc_channels": chip.get("adc_channels", {}),
        }
    }


def get_pin_functions(chip_id: str, pin_name: str) -> dict[str, Any] | None:
    """Get available functions for a specific pin."""
    chip = get_chip_info(chip_id)
    if not chip:
        return None
    
    pins = chip.get("pins", {})
    return pins.get(pin_name)


def get_adc_pins(chip_id: str) -> dict[str, str]:
    """Get ADC channel to pin mapping."""
    chip = get_chip_info(chip_id)
    if not chip:
        return {}
    return chip.get("adc_channels", {})


def get_pwm_pins(chip_id: str) -> dict[str, str]:
    """Get PWM output to pin mapping."""
    chip = get_chip_info(chip_id)
    if not chip:
        return {}
    return chip.get("peripherals", {}).get("pwm", {}).get("outputs", {})


def get_uart_pins(chip_id: str, port: int) -> dict[str, list[str]]:
    """Get UART TX/RX pins."""
    chip = get_chip_info(chip_id)
    if not chip:
        return {}
    uart_ports = chip.get("peripherals", {}).get("uart", {}).get("ports", {})
    return uart_ports.get(f"UART{port}", {"tx": [], "rx": []})


def get_i2c_pins(chip_id: str, port: int) -> dict[str, list[str]]:
    """Get I2C SDA/SCL pins."""
    chip = get_chip_info(chip_id)
    if not chip:
        return {}
    i2c_ports = chip.get("peripherals", {}).get("i2c", {}).get("ports", {})
    return i2c_ports.get(f"I2C{port}", {"sda": [], "scl": []})


def get_spi_pins(chip_id: str, port: int) -> dict[str, list[str]]:
    """Get SPI MOSI/MISO/SCK/NSS pins."""
    chip = get_chip_info(chip_id)
    if not chip:
        return {}
    spi_ports = chip.get("peripherals", {}).get("spi", {}).get("ports", {})
    return spi_ports.get(f"SPI{port}", {"mosi": [], "miso": [], "sck": [], "nss": []})


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
