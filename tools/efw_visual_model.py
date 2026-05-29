#!/usr/bin/env python3
"""Shared visual-editor metadata.

Keep graph schema/category metadata outside of the PyQt window implementation so
future work can split the editor into model, scene, panels, and generators
without changing the graph format.
"""

VISUAL_NODE_CATEGORIES = [
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
