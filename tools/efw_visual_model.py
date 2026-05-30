#!/usr/bin/env python3
"""Shared visual-editor metadata.

Keep graph schema/category metadata outside of the PyQt window implementation so
future work can split the editor into model, scene, panels, and generators
without changing the graph format.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

VISUAL_NODE_CATEGORIES = [
    ("框架库扫描", []),
    ("项目结构", ["project.module"]),
    ("HAL / 硬件", ["hal.gpio_line_input", "hal.custom"]),
    ("传感器", ["sensor.line_tracking", "sensor.custom"]),
    ("执行器", ["actuator.motor", "actuator.custom"]),
    ("算法", ["algorithm.pid", "algorithm.custom"]),
    ("模块 / 任务", ["module.custom", "task.periodic"]),
    ("通信发布订阅", ["event.topic", "event.publisher", "event.subscriber"]),
    ("状态机", ["state.machine", "state.state", "state.transition"]),
    ("逻辑控制", ["logic.if", "logic.loop"]),
    ("自定义", ["custom.card", "custom.code"]),
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
    "hal.gpio_line_input": ("完整生成", "生成 HAL mock 与 board pin 常量"),
    "hal.custom": ("完整生成", "生成 HAL 注册，回调由 custom_files/board_adapters 提供"),
    "sensor.line_tracking": ("完整生成", "生成循迹 sensor 注册"),
    "sensor.custom": ("完整生成", "生成 custom sensor 注册，read 回调由用户代码提供"),
    "actuator.motor": ("完整生成", "生成 motor actuator mock 与 PWM/DIR 常量"),
    "actuator.custom": ("完整生成", "生成 custom actuator 注册，write 回调由用户代码提供"),
    "algorithm.pid": ("完整生成", "生成 PID 实例与算法注册"),
    "algorithm.custom": ("完整生成", "生成算法注册，run 回调由用户代码提供"),
    "module.custom": ("完整生成", "生成 module 注册与生命周期调用"),
    "task.periodic": ("完整生成", "生成 tick scheduler 调用"),
    "event.topic": ("部分生成", "生成 APP_TOPIC_* 宏"),
    "event.publisher": ("说明/半自动", "表达发布关系，publish 调用仍在用户代码中"),
    "event.subscriber": ("部分生成", "生成 efw_topic_subscribe 绑定，回调由用户代码提供"),
    "project.module": ("生成分组", "用于 graph.module 分组，可双击进入子模块页面"),
    "state.machine": ("完整生成", "生成轻量状态机调度与状态注册 glue"),
    "state.state": ("完整生成", "生成 efw_state_machine_ops_t 状态注册"),
    "state.transition": ("完整生成", "生成条件判断和状态切换代码"),
    "logic.if": ("完整生成", "生成条件分支 wrapper，可由周期任务/模块调用"),
    "logic.loop": ("完整生成", "生成带 max_iterations 防护的循环 wrapper"),
    "custom.card": ("说明", "不生成代码"),
    "custom.code": ("说明", "代码正文来自 custom_files"),
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
