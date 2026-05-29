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
    "project.module": ("可视化组织", "用于分组和文档，不直接生成 C 模块文件"),
    "state.machine": ("可视化占位", "当前只校验图结构，尚未生成 state_machine 注册代码"),
    "state.state": ("可视化占位", "当前只校验图结构，尚未生成 state 节点代码"),
    "state.transition": ("可视化占位", "当前只校验图结构，尚未生成 transition 代码"),
    "logic.if": ("可视化占位", "当前只表达逻辑结构，尚未生成 C if 代码"),
    "logic.loop": ("可视化占位", "当前只表达逻辑结构，尚未生成 C loop 代码"),
    "custom.card": ("说明", "不生成代码"),
    "custom.code": ("说明", "代码正文来自 custom_files"),
}
