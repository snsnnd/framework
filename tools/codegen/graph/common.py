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
    "sensor.read": "void *ctx, void *out, uint16_t out_size",
    "actuator.init": "void *ctx",
    "actuator.enable": "void *ctx",
    "actuator.disable": "void *ctx",
    "actuator.write": "void *ctx, const void *cmd, uint16_t cmd_size",
    "algorithm.run": "void *ctx, const efw_app_multi_input_t *in, void *out",
    "module.lifecycle": "void *ctx",
    "module.poll": "void *ctx, const efw_app_multi_input_t *in",
    "task.call": "void",
    "state.lifecycle": "void *ctx",
    "transition.action": "void",
    "processor.process": "void *ctx, const efw_app_multi_input_t *in, void *out",
    "topic.callback": "uint16_t topic_id, const void *data, uint16_t size, void *user",
    "condition": "void",
}

CALLBACK_RETURNS = {
    "topic.callback": "void",
    "condition": "int",
}

MULTI_INPUT_NODE_PORTS = {
    "processor.custom": ("sensor", "algorithm", "event", "module_input"),
    "algorithm.custom": ("sensor", "processor", "event"),
    "module.custom": ("module_input", "event"),
}

MAPPING_ENABLED_NODE_TYPES = {"processor.custom", "algorithm.custom", "module.custom"}

TRIGGER_POLICY_CHOICES = ("primary_only", "any_input", "event_only", "manual")
OUTPUT_MODE_CHOICES = ("passthrough", "assemble_struct", "scalar_compute", "custom_code")
PROCESS_MODE_CHOICES = ("full_custom", "mapping_then_custom", "mapping_only")
FIELD_MAPPING_SOURCE_CHOICES = ("sensor", "processor", "algorithm", "event", "module_input", "const", "expr")
FIELD_MAPPING_TRANSFORM_CHOICES = ("identity", "to_float", "to_uint16", "scale", "offset")

BUILTIN_STRUCT_FIELD_TYPES = {
    "efw_pid_input_t": {"setpoint": "float", "feedback": "float", "dt": "float", "feedforward": "float"},
    "efw_pid_output_t": {"output": "float", "error": "float", "feedforward": "float"},
    "efw_motor_cmd_t": {"speed": "float", "direction": "float"},
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
    "app_bootstrap.h",
    "app_bootstrap.c",
    "app_publishers.c",
    "app_events.c",
    "app_state_machines.c",
    "main.c",
    "CMakeLists.generated.txt",
}
