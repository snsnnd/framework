"""
仿真场景配置系统

管理仿真场景的加载、保存和配置。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .core import MCUType


@dataclass
class ScenarioConfig:
    """场景配置"""
    name: str = "default"
    description: str = ""
    mcu_type: str = "STM32F407"
    
    # 外设配置
    gpios: list[dict] = field(default_factory=list)
    adcs: list[dict] = field(default_factory=list)
    pwms: list[dict] = field(default_factory=list)
    uarts: list[dict] = field(default_factory=list)
    i2cs: list[dict] = field(default_factory=list)
    spis: list[dict] = field(default_factory=list)
    
    # 传感器配置
    sensors: list[dict] = field(default_factory=list)
    
    # 执行器配置
    actuators: list[dict] = field(default_factory=list)
    
    # 环境配置
    environment: dict = field(default_factory=dict)


@dataclass
class Scenario:
    """仿真场景"""
    config: ScenarioConfig
    
    # 传感器初始值
    sensor_inputs: dict[str, Any] = field(default_factory=dict)
    
    # 环境参数
    track_pattern: str = ""  # 循迹轨道模式
    surface_friction: float = 1.0  # 地面摩擦系数
    battery_voltage: float = 7.4  # 电池电压
    
    @property
    def mcu_type(self) -> MCUType:
        return MCUType(self.config.mcu_type)


def create_line_tracker_scenario() -> Scenario:
    """创建循迹车仿真场景"""
    config = ScenarioConfig(
        name="line_tracker",
        description="5路循迹小车仿真场景",
        mcu_type="STM32F407",
        
        # GPIO 配置
        gpios=[
            {"port": "A", "pin": 0, "mode": "input"},   # 按键
            {"port": "B", "pin": 12, "mode": "output"},  # LED
        ],
        
        # ADC 配置（循迹传感器）
        adcs=[
            {"channel": 0, "resolution": 12},
            {"channel": 1, "resolution": 12},
            {"channel": 2, "resolution": 12},
            {"channel": 3, "resolution": 12},
            {"channel": 4, "resolution": 12},
        ],
        
        # PWM 配置（电机）
        pwms=[
            {"timer": "TIM1", "frequency_hz": 1000},
            {"timer": "TIM2", "frequency_hz": 1000},
        ],
        
        # UART 配置
        uarts=[
            {"port": 1, "baudrate": 115200},
        ],
        
        # 传感器配置
        sensors=[
            {"name": "line_sensor", "type": "line", "channels": 5},
            {"name": "left_encoder", "type": "encoder", "ppr": 360},
            {"name": "right_encoder", "type": "encoder", "ppr": 360},
        ],
        
        # 执行器配置
        actuators=[
            {"name": "left_motor", "type": "motor", "max_rpm": 300},
            {"name": "right_motor", "type": "motor", "max_rpm": 300},
            {"name": "status_led", "type": "led", "color": "green"},
        ],
    )
    
    return Scenario(
        config=config,
        track_pattern="10101",  # 中间检测到线
        battery_voltage=7.4,
    )


def create_smart_home_scenario() -> Scenario:
    """创建智能家居仿真场景"""
    config = ScenarioConfig(
        name="smart_home",
        description="智能家居控制器仿真场景",
        mcu_type="STM32F407",
        
        gpios=[
            {"port": "A", "pin": 0, "mode": "input"},
            {"port": "A", "pin": 1, "mode": "input"},
            {"port": "B", "pin": 0, "mode": "output"},
            {"port": "B", "pin": 1, "mode": "output"},
        ],
        
        adcs=[
            {"channel": 0, "resolution": 12},  # 温度传感器
            {"channel": 1, "resolution": 12},  # 光照传感器
            {"channel": 2, "resolution": 12},  # 湿度传感器
        ],
        
        i2cs=[
            {"bus_id": 1, "speed": 100000},
        ],
        
        sensors=[
            {"name": "temperature", "type": "custom"},
            {"name": "humidity", "type": "custom"},
            {"name": "light", "type": "custom"},
        ],
        
        actuators=[
            {"name": "relay_fan", "type": "led"},
            {"name": "relay_light", "type": "led"},
            {"name": "relay_heater", "type": "led"},
            {"name": "status_led", "type": "led", "color": "blue"},
        ],
    )
    
    return Scenario(
        config=config,
        environment={"temperature": 25.0, "humidity": 50.0, "light": 500.0},
    )


def load_scenario(path: str | Path) -> Scenario:
    """从文件加载场景"""
    path = Path(path)
    
    if not path.exists():
        raise FileNotFoundError(f"Scenario file not found: {path}")
    
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    config = ScenarioConfig(**data.get("config", {}))
    
    return Scenario(
        config=config,
        sensor_inputs=data.get("sensor_inputs", {}),
        track_pattern=data.get("track_pattern", ""),
        surface_friction=data.get("surface_friction", 1.0),
        battery_voltage=data.get("battery_voltage", 7.4),
    )


def save_scenario(scenario: Scenario, path: str | Path) -> None:
    """保存场景到文件"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    data = {
        "config": {
            "name": scenario.config.name,
            "description": scenario.config.description,
            "mcu_type": scenario.config.mcu_type,
            "gpios": scenario.config.gpios,
            "adcs": scenario.config.adcs,
            "pwms": scenario.config.pwms,
            "uarts": scenario.config.uarts,
            "i2cs": scenario.config.i2cs,
            "spis": scenario.config.spis,
            "sensors": scenario.config.sensors,
            "actuators": scenario.config.actuators,
            "environment": scenario.config.environment,
        },
        "sensor_inputs": scenario.sensor_inputs,
        "track_pattern": scenario.track_pattern,
        "surface_friction": scenario.surface_friction,
        "battery_voltage": scenario.battery_voltage,
    }
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# 内置场景列表
BUILTIN_SCENARIOS = {
    "line_tracker": create_line_tracker_scenario,
    "smart_home": create_smart_home_scenario,
}


def get_builtin_scenario(name: str) -> Scenario:
    """获取内置场景"""
    factory = BUILTIN_SCENARIOS.get(name)
    if factory:
        return factory()
    raise ValueError(f"Unknown built-in scenario: {name}")
