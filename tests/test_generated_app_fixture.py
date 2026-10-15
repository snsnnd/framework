#!/usr/bin/env python3
"""Generated application compile, link, and runtime tests."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from codegen.generator import render_application_files  # noqa: E402


class GeneratedAppFixtureTest(unittest.TestCase):
    def test_generated_multi_input_event_and_module_runtime(self) -> None:
        nodes = [
            {"id": "sensor_a", "type": "sensor.custom", "sensor_type": "custom", "read": "app_sensor_a_read", "output_type": "float"},
            {
                "id": "proc_a",
                "type": "processor.custom",
                "process": "app_proc_a_process",
                "primary_input_port": "sensor",
                "trigger_policy": "primary_only",
                "input_ports": {
                    "sensor": {"contract": "float", "type": "float", "size": 4, "align": 4},
                    "event": {"contract": "uint16_t", "type": "uint16_t", "size": 2, "align": 2},
                },
                "output_type": "float",
                "output_contract": "float",
            },
            {"id": "topic_evt", "type": "event.topic", "topic_id": 5, "payload_type": "uint16_t"},
            {"id": "sub_proc", "type": "event.subscriber", "topic": "topic_evt", "target": "proc_a", "callback": "app_on_proc_event"},
            {"id": "sub_algo", "type": "event.subscriber", "topic": "topic_evt", "target": "algo_a", "callback": "app_on_algo_event"},
            {"id": "sub_mod", "type": "event.subscriber", "topic": "topic_evt", "target": "mod_a", "callback": "app_on_mod_event"},
            {
                "id": "algo_a",
                "type": "algorithm.custom",
                "run": "app_algo_a_run",
                "primary_input_port": "sensor",
                "trigger_policy": "primary_only",
                "input_ports": {
                    "sensor": {"contract": "float", "type": "float", "size": 4, "align": 4},
                    "event": {"contract": "uint16_t", "type": "uint16_t", "size": 2, "align": 2},
                },
                "output_type": "float",
                "output_contract": "float",
            },
            {
                "id": "mod_a",
                "type": "module.custom",
                "poll": "app_mod_a_poll",
                "poll_on_event": True,
                "trigger_policy": "event_only",
                "primary_input_port": "event",
                "input_ports": {"event": {"contract": "uint16_t", "type": "uint16_t", "size": 2, "align": 2}},
            },
        ]
        custom_c = '''#include "efw/efw.h"

unsigned app_aggregate_count;
unsigned app_algorithm_count;
unsigned app_module_count;
unsigned app_proc_callback_count;
unsigned app_algo_callback_count;
unsigned app_mod_callback_count;

efw_status_t app_sensor_a_read(void *ctx, void *out, uint16_t out_size) {
    EFW_UNUSED(ctx);
    if (!out || out_size != sizeof(float)) return EFW_ERR_INVALID;
    *(float *)out = 3.5f;
    return EFW_OK;
}

efw_status_t app_proc_a_process(void *ctx, const efw_app_multi_input_t *in, void *out) {
    const efw_app_input_view_t *sensor = efw_app_multi_input_get(in, "sensor");
    const efw_app_input_view_t *event = efw_app_multi_input_get(in, "event");
    EFW_UNUSED(ctx);
    if (in->count != 2u || !sensor || !event || !sensor->valid || !event->valid) return EFW_OK;
    if (*(const float *)sensor->data != 3.5f || *(const uint16_t *)event->data != 42u) return EFW_ERR_INVALID;
    if (out) *(float *)out = 42.0f;
    app_aggregate_count++;
    return EFW_OK;
}

efw_status_t app_algo_a_run(void *ctx, const efw_app_multi_input_t *in, void *out) {
    const efw_app_input_view_t *sensor = efw_app_multi_input_get(in, "sensor");
    const efw_app_input_view_t *event = efw_app_multi_input_get(in, "event");
    EFW_UNUSED(ctx);
    if (in->count != 2u || !sensor || !event || !sensor->valid || !event->valid) return EFW_OK;
    if (*(const float *)sensor->data != 3.5f || *(const uint16_t *)event->data != 42u) return EFW_ERR_INVALID;
    if (out) *(float *)out = 42.0f;
    app_algorithm_count++;
    return EFW_OK;
}

efw_status_t app_mod_a_poll(void *ctx, const efw_app_multi_input_t *in) {
    const efw_app_input_view_t *event = efw_app_multi_input_get(in, "event");
    EFW_UNUSED(ctx);
    if (!event || !event->valid || *(const uint16_t *)event->data != 42u) return EFW_ERR_INVALID;
    app_module_count++;
    return EFW_OK;
}

void app_on_proc_event(uint16_t topic_id, const void *data, uint16_t size, void *user) {
    EFW_UNUSED(topic_id); EFW_UNUSED(data); EFW_UNUSED(size); EFW_UNUSED(user);
    app_proc_callback_count++;
}

void app_on_algo_event(uint16_t topic_id, const void *data, uint16_t size, void *user) {
    EFW_UNUSED(topic_id); EFW_UNUSED(data); EFW_UNUSED(size); EFW_UNUSED(user);
    app_algo_callback_count++;
}

void app_on_mod_event(uint16_t topic_id, const void *data, uint16_t size, void *user) {
    EFW_UNUSED(topic_id); EFW_UNUSED(data); EFW_UNUSED(size); EFW_UNUSED(user);
    app_mod_callback_count++;
}
'''
        ctx = {
            "project": {"name": "fixture", "tick_ms": 1, "board_profile": "stm32-basic"},
            "nodes": nodes,
            "nodes_by_id": {node["id"]: node for node in nodes},
            "edges": [
                {"id": "sensor_proc", "from": "sensor_a", "to": "proc_a", "from_port": "sensor", "to_port": "sensor", "kind": "data_flow"},
                {"id": "topic_proc", "from": "topic_evt", "to": "sub_proc", "from_port": "topic", "to_port": "topic", "kind": "event"},
                {"id": "sub_proc_target", "from": "sub_proc", "to": "proc_a", "from_port": "event", "to_port": "event", "kind": "event"},
                {"id": "sensor_algo", "from": "sensor_a", "to": "algo_a", "from_port": "sensor", "to_port": "sensor", "kind": "data_flow"},
                {"id": "topic_algo", "from": "topic_evt", "to": "sub_algo", "from_port": "topic", "to_port": "topic", "kind": "event"},
                {"id": "sub_algo_target", "from": "sub_algo", "to": "algo_a", "from_port": "event", "to_port": "event", "kind": "event"},
                {"id": "topic_mod", "from": "topic_evt", "to": "sub_mod", "from_port": "topic", "to_port": "topic", "kind": "event"},
                {"id": "sub_mod_target", "from": "sub_mod", "to": "mod_a", "from_port": "event", "to_port": "event", "kind": "event"},
            ],
            "flows": [],
            "tasks": [],
            "custom_files": [{"path": "app_custom.c", "content": custom_c}],
            "board_adapters": [],
            "contracts": {
                "float": {"name": "float", "type": "float", "c_type": "float", "size": 4, "align": 4},
                "uint16_t": {"name": "uint16_t", "type": "uint16_t", "c_type": "uint16_t", "size": 2, "align": 2},
            },
            "runtime_dataflows": [["sensor_a", "proc_a"], ["sensor_a", "algo_a"]],
        }
        files = render_application_files(ctx)
        bootstrap_c = files["app_bootstrap.c"]
        self.assertIn("efw_app_input_view_t views[2]", bootstrap_c)
        self.assertIn("app_subscriber_sub_proc_proxy", bootstrap_c)
        self.assertIn("app_subscriber_sub_algo_proxy", bootstrap_c)
        self.assertIn("app_subscriber_sub_mod_proxy", bootstrap_c)
        self.assertNotIn("s = app_module_mod_a_poll_bridge(0);", bootstrap_c)

        harness_c = '''#include "app_bootstrap.h"

extern unsigned app_aggregate_count;
extern unsigned app_algorithm_count;
extern unsigned app_module_count;
extern unsigned app_proc_callback_count;
extern unsigned app_algo_callback_count;
extern unsigned app_mod_callback_count;

int main(void) {
    const uint16_t event_value = 42u;
    if (app_init() != EFW_OK) return 10;
    if (app_post_event("fixture", 5u, &event_value, sizeof(event_value)) != EFW_OK) return 11;
    if (app_loop_tick() != EFW_OK) return 12;
    if (app_loop_tick() != EFW_OK) return 13;
    if (app_aggregate_count != 1u) return 20;
    if (app_algorithm_count != 1u) return 21;
    if (app_module_count != 1u) return 22;
    if (app_proc_callback_count != 1u) return 23;
    if (app_algo_callback_count != 1u) return 24;
    if (app_mod_callback_count != 1u) return 25;
    return 0;
}
'''
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as tmp:
            out_dir = Path(tmp)
            for rel_path, content in files.items():
                path = out_dir / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            (out_dir / "fixture_main.c").write_text(harness_c, encoding="utf-8")

            sources = [str(path) for path in out_dir.glob("*.c") if path.name != "main.c"]
            executable = out_dir / "fixture_app"
            result = subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Iinclude", f"-I{out_dir}", *sources, "src/efw_all.c", "-lm", "-o", str(executable)],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, f"link failed:\n{result.stderr}")
            run = subprocess.run([str(executable)], cwd=ROOT, text=True, capture_output=True, timeout=10)
            self.assertEqual(run.returncode, 0, f"fixture runtime failed with {run.returncode}:\n{run.stderr}")


if __name__ == "__main__":
    unittest.main()
