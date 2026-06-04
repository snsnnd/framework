#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from codegen.generator import build_runtime_summary, render_application_files
from codegen.validate import validate_graph


class CodegenSnapshotTest(unittest.TestCase):
    def load_graph(self, rel_path: str) -> dict:
        return json.loads((REPO_ROOT / rel_path).read_text(encoding="utf-8"))

    def render_graph(self, graph: dict) -> dict[str, str]:
        return render_application_files(validate_graph(graph))

    def test_generic_embedded_app_runtime_surfaces(self) -> None:
        ctx = validate_graph(self.load_graph("examples/graphs/generic_embedded_app.json"))
        files = render_application_files(ctx)

        bootstrap_h = files["app_bootstrap.h"]
        bootstrap_c = files["app_bootstrap.c"]
        components_c = files["app_components.c"]
        platform_c = files["app_platform.c"]
        manifest_h = files["app_manifest.h"]
        main_c = files["main.c"]

        self.assertIn("efw_status_t app_main(void);", bootstrap_h)
        self.assertIn("efw_status_t app_dispatch_event(const char *event_name, uint16_t topic_id, const void *data, uint16_t size);", bootstrap_h)
        self.assertIn("efw_status_t app_publish_publish_battery_value(float value);", bootstrap_h)
        self.assertIn("app_process_event_queue", bootstrap_c)
        self.assertIn("app_update_1ms", bootstrap_c)
        self.assertIn("app_publish_publish_battery_auto", bootstrap_c)
        self.assertIn("app_components_register", components_c)
        self.assertIn("app_platform_register", platform_c)
        self.assertIn("APP_TOPIC_TOPIC_BATTERY", manifest_h)
        self.assertIn("app_poll_forever", main_c)

    def test_runtime_summary_values_for_generic_embedded_app(self) -> None:
        ctx = validate_graph(self.load_graph("examples/graphs/generic_embedded_app.json"))
        summary = build_runtime_summary(ctx)
        self.assertEqual(sorted(summary.keys()), ["actuators", "hal", "project_modules", "publishers", "sensors", "state_machines"])
        self.assertEqual(len(summary["publishers"]), 1)
        publisher = summary["publishers"][0]
        self.assertEqual(publisher["id"], "publish_battery")
        self.assertEqual(publisher["mode"], "expr/size")
        self.assertEqual(publisher["stage"], "module.poll")
        self.assertEqual(publisher["source_kind"], "sensor.custom")
        self.assertEqual(publisher["payload_c_type"], "float")
        self.assertEqual(len(summary["project_modules"]), 1)
        project_module = summary["project_modules"][0]
        self.assertEqual(project_module["module_id"], "system_core")
        self.assertEqual(len(project_module["publishers"]), 1)
        self.assertEqual(len(project_module["state_machines"]), 0)

    def test_state_machine_runtime_surfaces(self) -> None:
        graph = {
            "project": {"name": "sm_app", "tick_ms": 1},
            "board": {"profile": "generic-mock", "pin_plan": []},
            "nodes": [
                {"id": "root__topic__start_evt", "type": "event.topic", "topic_id": 7, "payload_type": "float"},
                {"id": "root__state_machine__main", "type": "state.machine", "display_name": "主状态机", "initial": "root__state_state__idle"},
                {"id": "root__state_state__idle", "type": "state.state", "machine": "root__state_machine__main", "on_update": "app_idle_tick"},
                {"id": "root__state_state__run", "type": "state.state", "machine": "root__state_machine__main", "on_update": "app_run_tick"},
                {"id": "root__state_transition__idle_to_run", "type": "state.transition", "machine": "root__state_machine__main", "from": "root__state_state__idle", "to": "root__state_state__run", "condition": "app_should_run", "event_trigger": "topic:root__topic__start_evt"},
                {"id": "root__state_transition__run_to_idle", "type": "state.transition", "machine": "root__state_machine__main", "from": "root__state_state__run", "to": "root__state_state__idle", "condition": "app_should_idle"},
            ],
            "edges": [],
            "flows": [],
            "tasks": [],
            "custom_files": [{
                "path": "app_custom.c",
                "content": '#include "efw/efw.h"\n'
                           'efw_status_t app_idle_tick(void *ctx){EFW_UNUSED(ctx);return EFW_OK;}\n'
                           'efw_status_t app_run_tick(void *ctx){EFW_UNUSED(ctx);return EFW_OK;}\n'
                           'int app_should_run(void){return app_current_event_topic_id() == 7u;}\n'
                           'int app_should_idle(void){return 0;}\n'
            }],
            "ui": {"positions": {}},
        }
        files = self.render_graph(graph)
        bootstrap_h = files["app_bootstrap.h"]
        bootstrap_c = files["app_bootstrap.c"]
        self.assertIn("efw_status_t app_sm_root_state_machine_main_tick(void);", bootstrap_h)
        self.assertIn("efw_status_t app_sm_root_state_machine_main_dispatch_event(const char *event_name, uint16_t topic_id, const void *data, uint16_t size);", bootstrap_h)
        self.assertIn("app_sm_root_state_machine_main_transition_to", bootstrap_c)
        self.assertIn("app_bootstrap_event_matches", bootstrap_c)
        self.assertIn("topic:root__topic__start_evt", bootstrap_c)

    def test_module_source_auto_publish_surfaces(self) -> None:
        graph = {
            "project": {"name": "mod_pub", "tick_ms": 1},
            "board": {"profile": "generic-mock", "pin_plan": []},
            "nodes": [
                {"id": "root__project_module__main", "type": "project.module", "display_name": "主模块"},
                {"id": "root__module_custom__svc", "type": "module.custom", "module": "root__project_module__main", "poll": "app_service_poll", "output_type": "float"},
                {"id": "root__topic__evt", "type": "event.topic", "topic_id": 11, "payload_type": "float", "module": "root__project_module__main"},
                {"id": "root__event_publisher__pub", "type": "event.publisher", "topic": "root__topic__evt", "source": "root__module_custom__svc", "module": "root__project_module__main"},
            ],
            "edges": [],
            "flows": [],
            "tasks": [],
            "custom_files": [{
                "path": "app_custom.c",
                "content": '#include "efw/efw.h"\n'
                           'efw_status_t app_service_poll(void *ctx){EFW_UNUSED(ctx); return app_source_root_module_custom_svc_store_value(1.0f); }\n'
            }],
            "ui": {"positions": {}},
        }
        files = self.render_graph(graph)
        bootstrap_h = files["app_bootstrap.h"]
        bootstrap_c = files["app_bootstrap.c"]
        components_c = files["app_components.c"]
        self.assertIn("app_source_root_module_custom_svc_store_value(float value);", bootstrap_h)
        self.assertIn("app_source_root_module_custom_svc_store_value", bootstrap_c)
        self.assertIn("g_root_module_custom_svc_pub_cache_valid", bootstrap_c)
        self.assertIn("app_publish_root_event_publisher_pub_auto", bootstrap_c)
        self.assertIn("app_project_module_root_project_module_main_poll", components_c)

    def test_processor_source_auto_publish_surfaces(self) -> None:
        graph = {
            "project": {"name": "proc_pub", "tick_ms": 1},
            "board": {"profile": "generic-mock", "pin_plan": []},
            "nodes": [
                {"id": "root__sensor_custom__src", "type": "sensor.custom", "read": "app_read_sensor", "output_type": "float"},
                {"id": "root__processor_custom__proc", "type": "processor.custom", "process": "app_process", "input_type": "float", "output_type": "float"},
                {"id": "root__topic__evt", "type": "event.topic", "topic_id": 9, "payload_type": "float"},
                {"id": "root__event_publisher__pub", "type": "event.publisher", "topic": "root__topic__evt", "source": "root__processor_custom__proc"},
            ],
            "edges": [
                {"id": "e1", "from": "root__sensor_custom__src", "to": "root__processor_custom__proc", "from_port": "sensor", "to_port": "sensor", "kind": "data_flow"}
            ],
            "flows": [],
            "tasks": [],
            "custom_files": [{
                "path": "app_custom.c",
                "content": '#include "efw/efw.h"\n'
                           'efw_status_t app_read_sensor(void *ctx, void *out){EFW_UNUSED(ctx); if(out) *(float*)out = 1.0f; return EFW_OK;}\n'
                           'efw_status_t app_process(void *ctx, const void *in, void *out){EFW_UNUSED(ctx); if(in && out) *(float*)out = *(const float*)in; return EFW_OK;}\n'
            }],
            "ui": {"positions": {}},
        }
        files = self.render_graph(graph)
        bootstrap_c = files["app_bootstrap.c"]
        self.assertIn("g_root_processor_custom_proc_pub_cache", bootstrap_c)
        self.assertIn("app_cache_source_root_processor_custom_proc", bootstrap_c)
        self.assertIn("app_publish_root_event_publisher_pub_auto", bootstrap_c)
        self.assertIn("EFW_ERR_NOT_READY", bootstrap_c)


if __name__ == "__main__":
    unittest.main()
