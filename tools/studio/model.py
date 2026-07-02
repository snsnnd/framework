#!/usr/bin/env python3
"""Shared visual-editor metadata.

Keep graph schema/category metadata outside of the PyQt window implementation so
future work can split the editor into model, scene, panels, and generators
without changing the graph format.
"""

import json
from pathlib import Path

from codegen.graph import NODE_CONTRACTS, node_generation_label

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"

VISUAL_NODE_CATEGORIES = [
    ("框架库扫描", []),
    ("系统结构", ["project.module", "custom.card", "custom.interface_card"]),
    ("输入设备", ["hal.gpio_line_input", "hal.custom", "sensor.line_tracking", "sensor.custom"]),
    ("处理逻辑", ["processor.custom", "algorithm.pid", "algorithm.custom", "module.custom", "task.periodic"]),
    ("输出设备", ["actuator.motor", "actuator.custom"]),
    ("通信", ["event.topic", "event.publisher", "event.subscriber"]),
    ("状态机", ["state.machine", "state.state", "state.transition"]),
    ("数据类型与代码", ["data.enum", "data.struct", "custom.code"]),
]

GENERATED_APPLICATION_TREE = [
    "app_board_config.h        # Board Profile / Pin Planner",
    "app_manifest.h            # 功能开关、容量、topic 宏",
    "app_platform.c/.h         # HAL/SENSOR/ACTUATOR 注册",
    "app_components.c/.h       # Algorithm/Module 注册",
    "app_bootstrap.c/.h        # pool、bind、任务调度、topic subscribe",
    "main.c                    # 主入口",
    "CMakeLists.generated.txt",
]


NODE_GENERATION_STATUS = {
    node_type: (node_generation_label(node_type), str(contract.get("boundary", "")))
    for node_type, contract in NODE_CONTRACTS.items()
}


# ─── Default Board Profiles (fallback) ───────────────────────────────────────

DEFAULT_BOARD_PROFILES = {
    "generic-mock": {
        "label": "通用 Mock / Host 仿真",
        "ports": ["A", "B", "C", "D"],
        "pins_per_port": 16,
        "timers": [1, 2, 3, 4],
        "pwm_channels": [1, 2, 3, 4],
        "notes": "适合主机编译验证和无板卡演示。",
    },
}


# ─── Load Board Profiles from data/ ─────────────────────────────────────────

def load_board_profiles() -> dict:
    """Load board profiles from data/board_profiles/ and data/mcu/."""
    profiles = dict(DEFAULT_BOARD_PROFILES)
    
    # 从 data/board_profiles/ 加载开发板配置
    board_dir = DATA_DIR / "board_profiles"
    if board_dir.exists():
        for board_file in board_dir.glob("*.json"):
            try:
                with open(board_file, "r", encoding="utf-8") as f:
                    board_data = json.load(f)
                
                # 使用文件名（不含扩展名）作为 profile 名称
                profile_name = board_file.stem
                
                # 转换为 Studio 格式
                profile = _convert_board_profile(board_data)
                if profile:
                    profiles[profile_name] = profile
            except Exception:
                pass
    
    # 从 data/mcu/index.json 加载芯片数据作为可用的 board profiles
    mcu_index_path = DATA_DIR / "mcu" / "index.json"
    if mcu_index_path.exists():
        try:
            with open(mcu_index_path, "r", encoding="utf-8") as f:
                mcu_index = json.load(f)
            
            for chip_name, chip_info in mcu_index.items():
                chip_path = DATA_DIR / "mcu" / chip_info['path']
                if chip_path.exists():
                    with open(chip_path, "r", encoding="utf-8") as f:
                        chip_data = json.load(f)
                    
                    profile = _convert_mcu_to_profile(chip_data)
                    if profile:
                        # 使用芯片名称作为 profile 名称
                        profile_name = chip_name.lower().replace('-', '_').replace('(', '_').replace(')', '')
                        profiles[profile_name] = profile
        except Exception:
            pass
    
    return profiles


def _convert_board_profile(board_data: dict) -> dict | None:
    """Convert board profile data to Studio format."""
    if not board_data:
        return None
    
    return {
        "label": board_data.get("name", board_data.get("mcu", "Unknown")),
        "mcu": board_data.get("mcu", ""),
        "core": board_data.get("core", ""),
        "clock_mhz": board_data.get("frequency_mhz", board_data.get("clock", {}).get("sysclk_mhz", 0)),
        "flash_kb": board_data.get("flash_kb", 0),
        "ram_kb": board_data.get("ram_kb", 0),
        "package": board_data.get("package", ""),
        "ports": _extract_ports(board_data),
        "pins_per_port": 16,
        "timers": _extract_timers(board_data),
        "pwm_channels": _extract_pwm_channels(board_data),
        "gpio_pins": board_data.get("gpio_pins", []),
        "peripherals": board_data.get("peripherals", {}),
        "notes": board_data.get("description", ""),
    }


def _convert_mcu_to_profile(chip_data: dict) -> dict | None:
    """Convert MCU chip data to Studio board profile format."""
    if not chip_data:
        return None
    
    # 提取端口列表
    ports = []
    for pin_name in chip_data.get('gpio_pins', []):
        import re
        port = re.match(r'P([A-Z])', pin_name)
        if port and port.group(1) not in ports:
            ports.append(port.group(1))
    
    # 提取定时器列表
    timers = set()
    for tim in chip_data.get('peripherals', {}).get('pwm', {}).get('outputs', {}).keys():
        import re
        match = re.match(r'TIM(\d+)', tim)
        if match:
            timers.add(int(match.group(1)))
    
    return {
        "label": f"{chip_data.get('name', chip_data.get('id', 'Unknown'))} ({chip_data.get('board', '')})".strip(),
        "mcu": chip_data.get('name', chip_data.get('id', '')),
        "family": chip_data.get('family', ''),
        "core": chip_data.get('core', ''),
        "clock_mhz": chip_data.get('frequency_mhz', 0),
        "flash_kb": chip_data.get('flash_kb', 0),
        "ram_kb": chip_data.get('ram_kb', 0),
        "package": chip_data.get('package', ''),
        "ports": sorted(ports),
        "pins_per_port": 16,
        "gpio_count": chip_data.get('gpio_count', 0),
        "gpio_pins": chip_data.get('gpio_pins', []),
        "timers": sorted(timers),
        "pwm_channels": list(chip_data.get('peripherals', {}).get('pwm', {}).get('outputs', {}).keys()),
        "uart": list(chip_data.get('peripherals', {}).get('uart', {}).get('ports', {}).keys()),
        "i2c": list(chip_data.get('peripherals', {}).get('i2c', {}).get('ports', {}).keys()),
        "spi": list(chip_data.get('peripherals', {}).get('spi', {}).get('ports', {}).keys()),
        "adc_channels": chip_data.get('peripherals', {}).get('adc', {}).get('channels', {}),
        "peripherals": chip_data.get('peripherals', {}),
        "pins": chip_data.get('pins', {}),
        "notes": f"{chip_data.get('board', '')} - {chip_data.get('core', '')}, {chip_data.get('frequency_mhz', 0)}MHz",
    }


def _extract_ports(board_data: dict) -> list[str]:
    """Extract port list from board data."""
    if 'ports' in board_data:
        return board_data['ports']
    
    # 从 GPIO 引脚推断端口
    ports = set()
    for pin in board_data.get('gpio_pins', []):
        import re
        match = re.match(r'P([A-Z])', pin)
        if match:
            ports.add(match.group(1))
    
    return sorted(ports) if ports else ["A", "B", "C"]


def _extract_timers(board_data: dict) -> list[int]:
    """Extract timer list from board data."""
    if 'timers' in board_data:
        return board_data['timers']
    
    # 从 PWM 输出推断定时器
    timers = set()
    for tim in board_data.get('peripherals', {}).get('pwm', {}).get('outputs', {}).keys():
        import re
        match = re.match(r'TIM(\d+)', tim)
        if match:
            timers.add(int(match.group(1)))
    
    return sorted(timers) if timers else [1, 2, 3, 4]


def _extract_pwm_channels(board_data: dict) -> list[str]:
    """Extract PWM channels from board data."""
    if 'pwm_channels' in board_data:
        return board_data['pwm_channels']
    
    return list(board_data.get('peripherals', {}).get('pwm', {}).get('outputs', {}).keys())


# ─── Load Chip Database from data/ ──────────────────────────────────────────

def load_chip_database() -> dict:
    """Load chip database from data/mcu/."""
    database = {}
    
    mcu_index_path = DATA_DIR / "mcu" / "index.json"
    if not mcu_index_path.exists():
        return database
    
    try:
        with open(mcu_index_path, "r", encoding="utf-8") as f:
            mcu_index = json.load(f)
        
        for chip_name, chip_info in mcu_index.items():
            chip_path = DATA_DIR / "mcu" / chip_info['path']
            if chip_path.exists():
                with open(chip_path, "r", encoding="utf-8") as f:
                    chip_data = json.load(f)
                
                chip_id = chip_name.lower().replace('-', '_').replace('(', '_').replace(')', '')
                database[chip_id] = chip_data
    except Exception:
        pass
    
    return database


# ─── Initialize ──────────────────────────────────────────────────────────────

BOARD_PROFILES = load_board_profiles()
CHIP_DATABASE = load_chip_database()


def reload_data():
    """Reload all data from disk."""
    global BOARD_PROFILES, CHIP_DATABASE
    BOARD_PROFILES = load_board_profiles()
    CHIP_DATABASE = load_chip_database()
