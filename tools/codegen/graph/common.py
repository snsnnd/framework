"""Reusable Graph schema primitives shared by codegen and Studio."""

from __future__ import annotations

GEN_FULL = "full"
GEN_PARTIAL = "partial"
GEN_GLUE = "glue"
GEN_DOC = "doc"

GENERATION_LEVEL_LABELS = {
    GEN_FULL: "完整生成",
    GEN_PARTIAL: "部分生成",
    GEN_GLUE: "轻量 glue",
    GEN_DOC: "说明/文档",
}

VALID_EDGE_KINDS = {
    "contains",
    "data_flow",
    "hardware_dependency",
    "schedule",
    "control_flow",
    "event",
    "state_transition",
    "state_transition_from",
    "state_transition_to",
    "code",
    "generic",
    # Legacy aliases accepted for old graphs. New Studio writes normalized kinds.
    "containment",
    "data",
    "control",
    "state",
    "module_contains",
    "module_data_flow",
    "event_subscribe",
}

CALLBACK_SIGNATURES = {
    "hal.init": "void *ctx",
    "hal.read": "void *ctx, void *buf, uint16_t len, uint16_t *actual",
    "hal.write": "void *ctx, const void *buf, uint16_t len, uint16_t *actual",
    "hal.ioctl": "void *ctx, uint32_t cmd, void *arg",
    "sensor.init": "void *ctx",
    "sensor.read": "void *ctx, void *out",
    "actuator.init": "void *ctx",
    "actuator.enable": "void *ctx",
    "actuator.disable": "void *ctx",
    "actuator.write": "void *ctx, const void *cmd",
    "algorithm.run": "void *ctx, const void *in, void *out",
    "module.lifecycle": "void *ctx",
    "task.call": "void",
    "state.lifecycle": "void *ctx",
    "transition.action": "void",
    "processor.process": "void *ctx, const void *in, void *out",
    "topic.callback": "uint16_t topic_id, const void *data, uint16_t size, void *user",
    "condition": "void",
}

CALLBACK_RETURNS = {
    "topic.callback": "void",
    "condition": "int",
}


def callback_signature(signature_key: str) -> str:
    params = CALLBACK_SIGNATURES.get(signature_key, "void")
    return_type = CALLBACK_RETURNS.get(signature_key, "efw_status_t")
    return f"{return_type} ({params})"

SUPPORTED_FLOW_TYPES = {"control.line_follower"}

GENERATED_FILES = {
    "app_board_config.h",
    "app_manifest.h",
    "app_components.h",
    "app_components.c",
    "app_platform.h",
    "app_platform.c",
    "app_board_adapter.h",
    "app_bootstrap.h",
    "app_bootstrap.c",
    "main.c",
    "CMakeLists.generated.txt",
}
