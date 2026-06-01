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

VISUAL_NODE_CATEGORIES = [
    ("框架库扫描", []),
    ("System View · 系统层", ["project.module", "event.topic", "event.publisher", "event.subscriber", "custom.card"]),
    ("Module Internal · HAL / 通信", ["hal.gpio_line_input", "hal.custom"]),
    ("Module Internal · Sensor", ["sensor.line_tracking", "sensor.custom"]),
    ("Module Internal · Processor", ["processor.custom"]),
    ("Module Internal · Algorithm", ["algorithm.pid", "algorithm.custom"]),
    ("Module Internal · Actuator", ["actuator.motor", "actuator.custom"]),
    ("Module Internal · Task / Module", ["module.custom", "task.periodic"]),
    ("Module Internal · StateMachine", ["state.machine", "state.state", "state.transition"]),
    ("Module Internal · 数据契约 / 自定义代码", ["data.enum", "data.struct", "custom.code"]),
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


DEFAULT_BOARD_PROFILES = {
    "generic-mock": {
        "label": "通用 Mock / Host 仿真",
        "ports": ["A", "B", "C", "D"],
        "pins_per_port": 16,
        "timers": [1, 2, 3, 4],
        "pwm_channels": [1, 2, 3, 4],
        "notes": "适合主机编译验证和无板卡演示。",
    },
    "stm32-basic": {
        "label": "STM32 基础板卡",
        "ports": ["A", "B", "C"],
        "pins_per_port": 16,
        "timers": [1, 2, 3, 4],
        "pwm_channels": [1, 2, 3, 4],
        "notes": "用于生成 STM32 GPIO/PWM 规划草稿，实际复用功能仍需按 CubeMX/手册核对。",
    },
    "esp32-basic": {
        "label": "ESP32 基础板卡",
        "ports": ["GPIO"],
        "pins_per_port": 40,
        "timers": [0, 1, 2, 3],
        "pwm_channels": [0, 1, 2, 3, 4, 5, 6, 7],
        "notes": "用于 ESP-IDF GPIO/LEDC 规划草稿。",
    },
}


def load_board_profiles() -> dict:
    path = REPO_ROOT / "examples" / "board_profiles" / "board_profiles.json"
    if not path.exists():
        return DEFAULT_BOARD_PROFILES
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) and data else DEFAULT_BOARD_PROFILES


BOARD_PROFILES = load_board_profiles()
