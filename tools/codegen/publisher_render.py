"""Publisher and dataflow C render helpers."""

from __future__ import annotations

try:
    from .utils import c_ident, c_str
    from .runtime_model import publisher_payload_size_expr, source_auto_publishers, source_cache_c_type
except ImportError:  # pragma: no cover
    from codegen.utils import c_ident, c_str
    from codegen.runtime_model import publisher_payload_size_expr, source_auto_publishers, source_cache_c_type


def render_publisher_runtime(ctx, publisher_model):
    parts = []
    for source_id in sorted({item["source_id"] for item in publisher_model if item["source_id"] and item["source_kind"] not in {"sensor.custom", "sensor.line_tracking"}}):
        ident = c_ident(source_id)
        parts.append(f"static app_dataflow_buffer_t g_{ident}_pub_cache;\n")
        parts.append(f"static uint16_t g_{ident}_pub_cache_size;\n")
        parts.append(f"static uint8_t g_{ident}_pub_cache_valid;\n")
        parts.append(f"static void app_cache_source_{ident}(const void *data, uint16_t size) {{\n")
        parts.append("    if (!data || size == 0u) return;\n")
        parts.append("    if (size > APP_DATAFLOW_BUFFER_SIZE) size = APP_DATAFLOW_BUFFER_SIZE;\n")
        parts.append(f"    memcpy(g_{ident}_pub_cache.raw, data, size);\n")
        parts.append(f"    g_{ident}_pub_cache_size = size;\n")
        parts.append(f"    g_{ident}_pub_cache_valid = 1u;\n")
        parts.append("}\n")
    for item in publisher_model:
        ident = item["ident"]
        parts.append(f"static app_dataflow_buffer_t g_{ident}_last_pub;\n")
        parts.append(f"static uint16_t g_{ident}_last_pub_size;\n")
        parts.append(f"static uint8_t g_{ident}_last_pub_valid;\n")
        parts.append(f"static uint32_t g_{ident}_last_pub_ms;\n")
        parts.append(f"static efw_status_t app_publish_{ident}_auto_commit(uint16_t topic_id, const void *data, uint16_t size, uint32_t min_interval_ms) {{\n")
        parts.append("    if (!data || size == 0u) return EFW_ERR_INVALID;\n")
        parts.append(f"    if (min_interval_ms > 0u && (app_elapsed_ms() - g_{ident}_last_pub_ms) < min_interval_ms) return EFW_OK;\n")
        parts.append(f"    if (g_{ident}_last_pub_valid && g_{ident}_last_pub_size == size && size <= APP_DATAFLOW_BUFFER_SIZE && memcmp(g_{ident}_last_pub.raw, data, size) == 0) return EFW_OK;\n")
        parts.append(f"    if (size <= APP_DATAFLOW_BUFFER_SIZE) memcpy(g_{ident}_last_pub.raw, data, size);\n")
        parts.append(f"    g_{ident}_last_pub_size = size;\n")
        parts.append(f"    g_{ident}_last_pub_valid = (uint8_t)(size <= APP_DATAFLOW_BUFFER_SIZE);\n")
        parts.append(f"    g_{ident}_last_pub_ms = app_elapsed_ms();\n")
        parts.append("    return efw_topic_publish(topic_id, data, size);\n}\n")
    parts.append("\n")
    for item in publisher_model:
        node = item["node"]
        ident = item["ident"]
        topic_id = item["topic_id"]
        interval_ms = item["interval_ms"]
        parts.append(f"efw_status_t app_publish_{ident}(const void *data, uint16_t size) {{\n    return efw_topic_publish({topic_id}u, data, size);\n}}\n")
        c_type = item["payload_c_type"]
        if c_type not in {"", "custom"}:
            parts.append(f"efw_status_t app_publish_{ident}_typed(const {c_type} *value) {{\n    return efw_topic_publish({topic_id}u, value, (uint16_t)sizeof({c_type}));\n}}\n")
            parts.append(f"efw_status_t app_publish_{ident}_value({c_type} value) {{\n    return app_publish_{ident}_typed(&value);\n}}\n")
        if node.get("data_expr") and node.get("size_expr"):
            parts.append(f"efw_status_t app_publish_{ident}_auto(void) {{\n    return app_publish_{ident}_auto_commit({topic_id}u, {node.get('data_expr')}, {node.get('size_expr')}, {interval_ms}u);\n}}\n")
        elif item["source_id"]:
            source = ctx["nodes_by_id"].get(item["source_id"])
            source_ident = c_ident(item["source_id"])
            size_expr = item["payload_size_expr"]
            if source and source.get("type") in {"sensor.custom", "sensor.line_tracking"}:
                parts.append(f"efw_status_t app_publish_{ident}_auto(void) {{\n    efw_status_t s;\n    app_dataflow_buffer_t data;\n    s = efw_sensor_read({c_str(source['id'])}, data.raw, {size_expr});\n    if (s != EFW_OK) return s;\n    return app_publish_{ident}_auto_commit({topic_id}u, data.raw, {size_expr}, {interval_ms}u);\n}}\n")
            elif source and source.get("type") in {"processor.custom", "module.custom"}:
                parts.append(f"efw_status_t app_publish_{ident}_auto(void) {{\n    if (!g_{source_ident}_pub_cache_valid) return EFW_ERR_NOT_READY;\n    return app_publish_{ident}_auto_commit({topic_id}u, g_{source_ident}_pub_cache.raw, g_{source_ident}_pub_cache_size, {interval_ms}u);\n}}\n")
    for source_id in sorted({item["source_id"] for item in publisher_model if item["source_id"] and ctx.get("nodes_by_id", {}).get(item["source_id"], {}).get("type") == "module.custom"}):
        ident = c_ident(source_id)
        c_type = source_cache_c_type(ctx, source_id)
        parts.append(f"efw_status_t app_source_{ident}_store(const void *data, uint16_t size) {{\n    if (!data || size == 0u) return EFW_ERR_INVALID;\n    app_cache_source_{ident}(data, size);\n    return EFW_OK;\n}}\n")
        if c_type not in {"", "custom"}:
            parts.append(f"efw_status_t app_source_{ident}_store_typed(const {c_type} *value) {{\n    if (!value) return EFW_ERR_INVALID;\n    return app_source_{ident}_store(value, (uint16_t)sizeof({c_type}));\n}}\n")
            parts.append(f"efw_status_t app_source_{ident}_store_value({c_type} value) {{\n    return app_source_{ident}_store_typed(&value);\n}}\n")
    return "".join(parts)
