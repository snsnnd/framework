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
                           'efw_status_t app_process(void *ctx, const efw_app_multi_input_t *in, void *out){const efw_app_input_view_t *sensor = efw_app_multi_input_get(in, "sensor"); EFW_UNUSED(ctx); if(sensor && sensor->data && out) *(float*)out = *(const float*)sensor->data; return EFW_OK;}\n'
            }],
            "ui": {"positions": {}},
        }
        files = self.render_graph(graph)
        bootstrap_c = files["app_bootstrap.c"]
        self.assertIn("g_root_processor_custom_proc_pub_cache", bootstrap_c)
        self.assertIn("app_cache_source_root_processor_custom_proc", bootstrap_c)
        self.assertIn("app_publish_root_event_publisher_pub_auto", bootstrap_c)
        self.assertIn("EFW_ERR_NOT_READY", bootstrap_c)

    def test_processor_uses_port_specific_input_contracts(self) -> None:
        graph = {
            "project": {"name": "proc_ports", "tick_ms": 1},
            "board": {"profile": "generic-mock", "pin_plan": []},
            "nodes": [
                {"id": "src", "type": "sensor.custom", "read": "app_read_sensor", "output_type": "float"},
                {"id": "topic_evt", "type": "event.topic", "topic_id": 3, "payload_type": "uint16_t"},
                {"id": "sub", "type": "event.subscriber", "topic": "topic_evt", "target": "proc", "callback": "app_on_evt"},
                {"id": "proc", "type": "processor.custom", "process": "app_process", "output_type": "efw_pid_input_t", "output_contract": "efw_pid_input_t"},
            ],
            "edges": [
                {"id": "e1", "from": "src", "to": "proc", "from_port": "sensor", "to_port": "sensor", "kind": "data_flow"},
                {"id": "e2", "from": "topic_evt", "to": "sub", "from_port": "topic", "to_port": "topic", "kind": "event"},
                {"id": "e3", "from": "sub", "to": "proc", "from_port": "event", "to_port": "event", "kind": "event"},
            ],
            "flows": [],
            "tasks": [],
            "custom_files": [{
                "path": "app_custom.c",
                "content": '#include "efw/efw.h"\n'
                           'efw_status_t app_read_sensor(void *ctx, void *out){EFW_UNUSED(ctx); if(out) *(float*)out = 1.0f; return EFW_OK;}\n'
                           'efw_status_t app_process(void *ctx, const efw_app_multi_input_t *in, void *out){EFW_UNUSED(ctx); EFW_UNUSED(in); EFW_UNUSED(out); return EFW_OK;}\n'
                           'void app_on_evt(uint16_t topic_id, const void *data, uint16_t size, void *user){EFW_UNUSED(topic_id); EFW_UNUSED(data); EFW_UNUSED(size); EFW_UNUSED(user);}\n'
            }],
            "ui": {"positions": {}},
        }
        ctx = validate_graph(graph)
        proc = ctx["nodes_by_id"]["proc"]
        self.assertEqual(proc["input_ports"]["sensor"]["contract"], "float")
        self.assertEqual(proc["input_ports"]["sensor"]["size"], 4)
        self.assertEqual(proc["input_ports"]["event"]["contract"], "uint16_t")

    def test_processor_rejects_builtin_contract_mismatch(self) -> None:
        graph = {
            "project": {"name": "proc_mismatch", "tick_ms": 1},
            "board": {"profile": "generic-mock", "pin_plan": []},
            "nodes": [
                {"id": "proc", "type": "processor.custom", "process": "app_process", "input_contract": "float", "input_type": "uint8_t", "input_size": 8, "output_type": "float"},
            ],
            "edges": [],
            "flows": [],
            "tasks": [],
            "custom_files": [{
                "path": "app_custom.c",
                "content": '#include "efw/efw.h"\n'
                           'efw_status_t app_process(void *ctx, const efw_app_multi_input_t *in, void *out){EFW_UNUSED(ctx); EFW_UNUSED(in); EFW_UNUSED(out); return EFW_OK;}\n'
            }],
            "ui": {"positions": {}},
        }
        with self.assertRaisesRegex(ValueError, "内建契约 float 不一致"):
            validate_graph(graph)

    def test_processor_and_algorithm_use_multi_input_runtime_abi(self) -> None:
        graph = {
            "project": {"name": "multi_input_runtime", "tick_ms": 1},
            "board": {"profile": "generic-mock", "pin_plan": []},
            "nodes": [
                {"id": "src", "type": "sensor.custom", "read": "app_read_sensor", "output_type": "float"},
                {"id": "proc", "type": "processor.custom", "process": "app_process", "output_contract": "float", "output_type": "float"},
                {"id": "algo", "type": "algorithm.custom", "run": "app_run_algo", "output_type": "float"},
            ],
            "edges": [
                {"id": "e1", "from": "src", "to": "proc", "from_port": "sensor", "to_port": "sensor", "kind": "data_flow"},
                {"id": "e2", "from": "proc", "to": "algo", "from_port": "processor", "to_port": "processor", "kind": "data_flow"},
            ],
            "flows": [],
            "tasks": [],
            "custom_files": [{
                "path": "app_custom.c",
                "content": '#include "efw/efw.h"\n'
                           'efw_status_t app_read_sensor(void *ctx, void *out){EFW_UNUSED(ctx); if(out) *(float*)out = 1.0f; return EFW_OK;}\n'
                           'efw_status_t app_process(void *ctx, const efw_app_multi_input_t *in, void *out){const efw_app_input_view_t *sensor = efw_app_multi_input_get(in, "sensor"); EFW_UNUSED(ctx); if(sensor && sensor->data && out) *(float*)out = *(const float*)sensor->data; return EFW_OK;}\n'
                           'efw_status_t app_run_algo(void *ctx, const efw_app_multi_input_t *in, void *out){const efw_app_input_view_t *processor = efw_app_multi_input_get(in, "processor"); EFW_UNUSED(ctx); if(processor && processor->data && out) *(float*)out = *(const float*)processor->data; return EFW_OK;}\n'
            }],
            "ui": {"positions": {}},
        }
        files = self.render_graph(graph)
        self.assertIn("const efw_app_multi_input_t *in", files["app_bootstrap.c"])
        self.assertIn("app_processor_proc_run_port", files["app_bootstrap.c"])
        self.assertIn("app_algorithm_algo_dispatch", files["app_bootstrap.c"])
        self.assertIn(".run = app_algorithm_algo_dispatch", files["app_components.c"])

    def test_subscriber_targeting_processor_updates_event_cache_via_proxy(self) -> None:
        graph = {
            "project": {"name": "processor_event_proxy", "tick_ms": 1},
            "board": {"profile": "generic-mock", "pin_plan": []},
            "nodes": [
                {"id": "topic_evt", "type": "event.topic", "topic_id": 5, "payload_type": "uint16_t"},
                {"id": "sub", "type": "event.subscriber", "topic": "topic_evt", "target": "proc", "callback": "app_on_evt"},
                {"id": "proc", "type": "processor.custom", "process": "app_process", "output_contract": "float", "output_type": "float"},
            ],
            "edges": [
                {"id": "e1", "from": "topic_evt", "to": "sub", "from_port": "topic", "to_port": "topic", "kind": "event"},
                {"id": "e2", "from": "sub", "to": "proc", "from_port": "event", "to_port": "event", "kind": "event"},
            ],
            "flows": [],
            "tasks": [],
            "custom_files": [{
                "path": "app_custom.c",
                "content": '#include "efw/efw.h"\n'
                           'efw_status_t app_process(void *ctx, const efw_app_multi_input_t *in, void *out){EFW_UNUSED(ctx); EFW_UNUSED(in); EFW_UNUSED(out); return EFW_OK;}\n'
                           'void app_on_evt(uint16_t topic_id, const void *data, uint16_t size, void *user){EFW_UNUSED(topic_id); EFW_UNUSED(data); EFW_UNUSED(size); EFW_UNUSED(user);}\n'
            }],
            "ui": {"positions": {}},
        }
        files = self.render_graph(graph)
        self.assertIn("app_subscriber_sub_proxy", files["app_bootstrap.c"])
        self.assertIn("app_cache_processor_proc_event(data, size);", files["app_bootstrap.c"])

    def test_module_custom_poll_uses_multi_input_bridge(self) -> None:
        graph = {
            "project": {"name": "module_multi_input", "tick_ms": 1},
            "board": {"profile": "generic-mock", "pin_plan": []},
            "nodes": [
                {"id": "src", "type": "sensor.custom", "read": "app_read_sensor", "output_type": "float"},
                {"id": "proc", "type": "processor.custom", "process": "app_process", "output_contract": "float", "output_type": "float"},
                {"id": "mod", "type": "module.custom", "poll": "app_poll_module"},
            ],
            "edges": [
                {"id": "e1", "from": "src", "to": "proc", "from_port": "sensor", "to_port": "sensor", "kind": "data_flow"},
                {"id": "e2", "from": "proc", "to": "mod", "from_port": "module_output", "to_port": "module_input", "kind": "data_flow"},
            ],
            "flows": [],
            "tasks": [],
            "custom_files": [{
                "path": "app_custom.c",
                "content": '#include "efw/efw.h"\n'
                           'efw_status_t app_read_sensor(void *ctx, void *out){EFW_UNUSED(ctx); if(out) *(float*)out = 1.0f; return EFW_OK;}\n'
                           'efw_status_t app_process(void *ctx, const efw_app_multi_input_t *in, void *out){const efw_app_input_view_t *sensor = efw_app_multi_input_get(in, "sensor"); EFW_UNUSED(ctx); if(sensor && sensor->data && out) *(float*)out = *(const float*)sensor->data; return EFW_OK;}\n'
                           'efw_status_t app_poll_module(void *ctx, const efw_app_multi_input_t *in){const efw_app_input_view_t *module_input = efw_app_multi_input_get(in, "module_input"); EFW_UNUSED(ctx); EFW_UNUSED(module_input); return EFW_OK;}\n'
            }],
            "ui": {"positions": {}},
        }
        files = self.render_graph(graph)
        self.assertIn("app_module_mod_poll_bridge", files["app_bootstrap.c"])
        self.assertIn("app_cache_module_mod_module_input", files["app_bootstrap.c"])
        self.assertIn(".poll = app_module_mod_poll_bridge", files["app_components.c"])

    def test_subscriber_targeting_algorithm_triggers_event_runtime(self) -> None:
        graph = {
            "project": {"name": "algorithm_event_proxy", "tick_ms": 1},
            "board": {"profile": "generic-mock", "pin_plan": []},
            "nodes": [
                {"id": "topic_evt", "type": "event.topic", "topic_id": 6, "payload_type": "uint16_t"},
                {"id": "sub", "type": "event.subscriber", "topic": "topic_evt", "target": "algo", "callback": "app_on_evt"},
                {"id": "algo", "type": "algorithm.custom", "run": "app_run_algo", "output_type": "float"},
                {"id": "motor", "type": "actuator.custom", "write": "app_write_motor", "input_type": "float"},
            ],
            "edges": [
                {"id": "e1", "from": "topic_evt", "to": "sub", "from_port": "topic", "to_port": "topic", "kind": "event"},
                {"id": "e2", "from": "sub", "to": "algo", "from_port": "event", "to_port": "event", "kind": "event"},
                {"id": "e3", "from": "algo", "to": "motor", "from_port": "algorithm", "to_port": "control", "kind": "control_flow"},
            ],
            "flows": [],
            "tasks": [],
            "custom_files": [{
                "path": "app_custom.c",
                "content": '#include "efw/efw.h"\n'
                           'efw_status_t app_run_algo(void *ctx, const efw_app_multi_input_t *in, void *out){EFW_UNUSED(ctx); EFW_UNUSED(in); if(out) *(float*)out = 1.0f; return EFW_OK;}\n'
                           'efw_status_t app_write_motor(void *ctx, const void *cmd){EFW_UNUSED(ctx); EFW_UNUSED(cmd); return EFW_OK;}\n'
                           'void app_on_evt(uint16_t topic_id, const void *data, uint16_t size, void *user){EFW_UNUSED(topic_id); EFW_UNUSED(data); EFW_UNUSED(size); EFW_UNUSED(user);}\n'
            }],
            "ui": {"positions": {}},
        }
        files = self.render_graph(graph)
        self.assertIn("app_subscriber_sub_proxy", files["app_bootstrap.c"])
        self.assertIn("app_cache_algorithm_algo_event(data, size);", files["app_bootstrap.c"])
        self.assertIn("app_algorithm_algo_trigger_event", files["app_bootstrap.c"])

    def test_module_custom_event_can_optionally_trigger_poll_immediately(self) -> None:
        graph = {
            "project": {"name": "module_event_poll", "tick_ms": 1},
            "board": {"profile": "generic-mock", "pin_plan": []},
            "nodes": [
                {"id": "topic_evt", "type": "event.topic", "topic_id": 8, "payload_type": "uint16_t"},
                {"id": "sub", "type": "event.subscriber", "topic": "topic_evt", "target": "mod", "callback": "app_on_evt"},
                {"id": "mod", "type": "module.custom", "poll": "app_poll_module", "poll_on_event": True, "input_ports": {"event": {"contract": "uint16_t", "type": "uint16_t", "size": 2, "align": 2}}},
            ],
            "edges": [
                {"id": "e1", "from": "topic_evt", "to": "sub", "from_port": "topic", "to_port": "topic", "kind": "event"},
                {"id": "e2", "from": "sub", "to": "mod", "from_port": "event", "to_port": "event", "kind": "event"},
            ],
            "flows": [],
            "tasks": [],
            "custom_files": [{
                "path": "app_custom.c",
                "content": '#include "efw/efw.h"\n'
                           'efw_status_t app_poll_module(void *ctx, const efw_app_multi_input_t *in){EFW_UNUSED(ctx); EFW_UNUSED(in); return EFW_OK;}\n'
                           'void app_on_evt(uint16_t topic_id, const void *data, uint16_t size, void *user){EFW_UNUSED(topic_id); EFW_UNUSED(data); EFW_UNUSED(size); EFW_UNUSED(user);}\n'
            }],
            "ui": {"positions": {}},
        }
        files = self.render_graph(graph)
        self.assertIn("app_cache_module_mod_event(data, size);", files["app_bootstrap.c"])
        self.assertIn("app_record_immediate_status(\"module:mod\", \"event\", s);", files["app_bootstrap.c"])

    def test_event_contract_mismatch_is_rejected(self) -> None:
        graph = {
            "project": {"name": "event_mismatch", "tick_ms": 1},
            "board": {"profile": "generic-mock", "pin_plan": []},
            "nodes": [
                {"id": "topic_evt", "type": "event.topic", "topic_id": 1, "payload_type": "uint16_t"},
                {"id": "sub", "type": "event.subscriber", "topic": "topic_evt", "target": "proc", "callback": "app_on_evt"},
                {"id": "proc", "type": "processor.custom", "process": "app_process", "input_ports": {"event": {"contract": "float", "type": "float", "size": 4, "align": 4}}, "output_type": "float"},
            ],
            "edges": [
                {"id": "e1", "from": "topic_evt", "to": "sub", "from_port": "topic", "to_port": "topic", "kind": "event"},
                {"id": "e2", "from": "sub", "to": "proc", "from_port": "event", "to_port": "event", "kind": "event"},
            ],
            "flows": [],
            "tasks": [],
            "custom_files": [{
                "path": "app_custom.c",
                "content": '#include "efw/efw.h"\n'
                           'void app_on_evt(uint16_t topic_id, const void *data, uint16_t size, void *user){EFW_UNUSED(topic_id);EFW_UNUSED(data);EFW_UNUSED(size);EFW_UNUSED(user);}\n'
                           'efw_status_t app_process(void *ctx, const efw_app_multi_input_t *in, void *out){EFW_UNUSED(ctx);EFW_UNUSED(in);EFW_UNUSED(out); return EFW_OK;}\n'
            }],
            "ui": {"positions": {}},
        }
        with self.assertRaisesRegex(ValueError, "event contract mismatch"):
            validate_graph(graph)

    def test_immediate_event_diagnostics_are_generated(self) -> None:
        graph = {
            "project": {"name": "event_diag", "tick_ms": 1},
            "board": {"profile": "generic-mock", "pin_plan": []},
            "nodes": [
                {"id": "topic_evt", "type": "event.topic", "topic_id": 9, "payload_type": "uint16_t"},
                {"id": "sub", "type": "event.subscriber", "topic": "topic_evt", "target": "algo", "callback": "app_on_evt"},
                {"id": "algo", "type": "algorithm.custom", "run": "app_run_algo", "output_type": "float"},
            ],
            "edges": [
                {"id": "e1", "from": "topic_evt", "to": "sub", "from_port": "topic", "to_port": "topic", "kind": "event"},
                {"id": "e2", "from": "sub", "to": "algo", "from_port": "event", "to_port": "event", "kind": "event"},
            ],
            "flows": [],
            "tasks": [],
            "custom_files": [{
                "path": "app_custom.c",
                "content": '#include "efw/efw.h"\n'
                           'efw_status_t app_run_algo(void *ctx, const efw_app_multi_input_t *in, void *out){EFW_UNUSED(ctx);EFW_UNUSED(in); if(out) *(float*)out = 0.0f; return EFW_OK;}\n'
                           'void app_on_evt(uint16_t topic_id, const void *data, uint16_t size, void *user){EFW_UNUSED(topic_id);EFW_UNUSED(data);EFW_UNUSED(size);EFW_UNUSED(user);}\n'
            }],
            "ui": {"positions": {}},
        }
        files = self.render_graph(graph)
        self.assertIn("app_last_immediate_status", files["app_bootstrap.h"])
        self.assertIn("app_record_immediate_status", files["app_bootstrap.c"])

    def test_processor_mapping_only_generates_struct_mapping(self) -> None:
        graph = {
            "project": {"name": "processor_mapping_only", "tick_ms": 1},
            "board": {"profile": "generic-mock", "pin_plan": []},
            "nodes": [
                {
                    "id": "src",
                    "type": "sensor.custom",
                    "read": "app_read_sensor",
                    "output_type": "float",
                },
                {
                    "id": "proc",
                    "type": "processor.custom",
                    "output_contract": "efw_pid_input_t",
                    "output_type": "efw_pid_input_t",
                    "output_size": 16,
                    "output_align": 4,
                    "primary_input_port": "sensor",
                    "trigger_policy": "primary_only",
                    "output_mode": "assemble_struct",
                    "process_mode": "mapping_only",
                    "field_mappings": [
                        {"field": "setpoint", "source": "const", "value": 0.0, "transform": "identity", "required": True},
                        {"field": "feedback", "source": "sensor", "path": "", "transform": "identity", "required": True},
                        {"field": "dt", "source": "const", "value": 0.01, "transform": "identity", "required": True},
                        {"field": "feedforward", "source": "const", "value": 0.0, "transform": "identity", "required": True},
                    ],
                },
            ],
            "edges": [
                {"id": "e1", "from": "src", "to": "proc", "from_port": "sensor", "to_port": "sensor", "kind": "data_flow"},
            ],
            "flows": [],
            "tasks": [],
            "custom_files": [{
                "path": "app_custom.c",
                "content": '#include "efw/efw.h"\n'
                           'efw_status_t app_read_sensor(void *ctx, void *out){EFW_UNUSED(ctx); if(out) *(float*)out = 2.0f; return EFW_OK;}\n'
            }],
            "ui": {"positions": {}},
        }
        files = self.render_graph(graph)
        bootstrap_c = files["app_bootstrap.c"]
        self.assertIn("static efw_status_t app_processor_proc_apply_mapping", bootstrap_c)
        self.assertIn("mapped->feedback = (*(const float *)src_view->data);", bootstrap_c)
        self.assertIn("mapped->dt = 0.01f;", bootstrap_c)
        self.assertIn("return EFW_OK;", bootstrap_c)

    def test_processor_mapping_then_custom_calls_callback_after_mapping(self) -> None:
        graph = {
            "project": {"name": "processor_mapping_then_custom", "tick_ms": 1},
            "board": {"profile": "generic-mock", "pin_plan": []},
            "nodes": [
                {"id": "src", "type": "sensor.custom", "read": "app_read_sensor", "output_type": "float"},
                {
                    "id": "proc",
                    "type": "processor.custom",
                    "process": "app_process",
                    "output_contract": "efw_pid_input_t",
                    "output_type": "efw_pid_input_t",
                    "output_size": 16,
                    "output_align": 4,
                    "primary_input_port": "sensor",
                    "trigger_policy": "primary_only",
                    "output_mode": "assemble_struct",
                    "process_mode": "mapping_then_custom",
                    "field_mappings": [
                        {"field": "feedback", "source": "sensor", "path": "", "transform": "identity", "required": True},
                    ],
                },
            ],
            "edges": [
                {"id": "e1", "from": "src", "to": "proc", "from_port": "sensor", "to_port": "sensor", "kind": "data_flow"},
            ],
            "flows": [],
            "tasks": [],
            "custom_files": [{
                "path": "app_custom.c",
                "content": '#include "efw/efw.h"\n'
                           'efw_status_t app_read_sensor(void *ctx, void *out){EFW_UNUSED(ctx); if(out) *(float*)out = 2.0f; return EFW_OK;}\n'
                           'efw_status_t app_process(void *ctx, const efw_app_multi_input_t *in, void *out){EFW_UNUSED(ctx); EFW_UNUSED(in); EFW_UNUSED(out); return EFW_OK;}\n'
            }],
            "ui": {"positions": {}},
        }
        files = self.render_graph(graph)
        bootstrap_c = files["app_bootstrap.c"]
        self.assertIn("app_processor_proc_apply_mapping(&multi, out)", bootstrap_c)
        self.assertIn("return app_process(ctx ? ctx : 0, &multi, out);", bootstrap_c)

    def test_algorithm_mapping_only_generates_output_mapping(self) -> None:
        graph = {
            "project": {"name": "algorithm_mapping_only", "tick_ms": 1},
            "board": {"profile": "generic-mock", "pin_plan": []},
            "nodes": [
                {"id": "src", "type": "sensor.custom", "read": "app_read_sensor", "output_type": "float"},
                {
                    "id": "algo",
                    "type": "algorithm.custom",
                    "output_contract": "efw_pid_output_t",
                    "output_type": "efw_pid_output_t",
                    "output_size": 12,
                    "output_align": 4,
                    "primary_input_port": "sensor",
                    "trigger_policy": "primary_only",
                    "output_mode": "assemble_struct",
                    "process_mode": "mapping_only",
                    "field_mappings": [
                        {"field": "output", "source": "sensor", "path": "", "transform": "identity", "required": True},
                        {"field": "error", "source": "const", "value": 0.0, "transform": "identity", "required": True},
                        {"field": "feedforward", "source": "const", "value": 0.0, "transform": "identity", "required": True},
                    ],
                },
            ],
            "edges": [
                {"id": "e1", "from": "src", "to": "algo", "from_port": "sensor", "to_port": "sensor", "kind": "data_flow"},
            ],
            "flows": [],
            "tasks": [],
            "custom_files": [{
                "path": "app_custom.c",
                "content": '#include "efw/efw.h"\n'
                           'efw_status_t app_read_sensor(void *ctx, void *out){EFW_UNUSED(ctx); if(out) *(float*)out = 3.0f; return EFW_OK;}\n'
            }],
            "ui": {"positions": {}},
        }
        files = self.render_graph(graph)
        bootstrap_c = files["app_bootstrap.c"]
        self.assertIn("static efw_status_t app_algorithm_algo_apply_mapping", bootstrap_c)
        self.assertIn("mapped->output = (*(const float *)src_view->data);", bootstrap_c)
        self.assertIn("mapped->error = 0.0f;", bootstrap_c)

    def test_algorithm_mapping_then_custom_calls_run_after_mapping(self) -> None:
        graph = {
            "project": {"name": "algorithm_mapping_then_custom", "tick_ms": 1},
            "board": {"profile": "generic-mock", "pin_plan": []},
            "nodes": [
                {"id": "src", "type": "sensor.custom", "read": "app_read_sensor", "output_type": "float"},
                {
                    "id": "algo",
                    "type": "algorithm.custom",
                    "run": "app_run_algo",
                    "output_contract": "efw_pid_output_t",
                    "output_type": "efw_pid_output_t",
                    "output_size": 12,
                    "output_align": 4,
                    "primary_input_port": "sensor",
                    "trigger_policy": "primary_only",
                    "output_mode": "assemble_struct",
                    "process_mode": "mapping_then_custom",
                    "field_mappings": [
                        {"field": "output", "source": "sensor", "path": "", "transform": "identity", "required": True},
                    ],
                },
            ],
            "edges": [
                {"id": "e1", "from": "src", "to": "algo", "from_port": "sensor", "to_port": "sensor", "kind": "data_flow"},
            ],
            "flows": [],
            "tasks": [],
            "custom_files": [{
                "path": "app_custom.c",
                "content": '#include "efw/efw.h"\n'
                           'efw_status_t app_read_sensor(void *ctx, void *out){EFW_UNUSED(ctx); if(out) *(float*)out = 3.0f; return EFW_OK;}\n'
                           'efw_status_t app_run_algo(void *ctx, const efw_app_multi_input_t *in, void *out){EFW_UNUSED(ctx); EFW_UNUSED(in); EFW_UNUSED(out); return EFW_OK;}\n'
            }],
            "ui": {"positions": {}},
        }
        files = self.render_graph(graph)
        bootstrap_c = files["app_bootstrap.c"]
        self.assertIn("app_algorithm_algo_apply_mapping(&multi, out)", bootstrap_c)
        self.assertIn("return app_run_algo(ctx ? ctx : 0, &multi, out);", bootstrap_c)

    def test_module_mapping_only_caches_output_for_auto_publish(self) -> None:
        graph = {
            "project": {"name": "module_mapping_only", "tick_ms": 1},
            "board": {"profile": "generic-mock", "pin_plan": []},
            "nodes": [
                {"id": "src", "type": "sensor.custom", "read": "app_read_sensor", "output_type": "float"},
                {
                    "id": "mod",
                    "type": "module.custom",
                    "poll": "app_poll_module",
                    "input_ports": {"module_input": {"contract": "float", "type": "float", "size": 4, "align": 4}},
                    "output_contract": "float",
                    "output_type": "float",
                    "output_size": 4,
                    "output_mode": "scalar_compute",
                    "process_mode": "mapping_only",
                    "field_mappings": [
                        {"field": "", "source": "module_input", "path": "", "transform": "identity", "required": True},
                    ],
                },
                {"id": "topic_evt", "type": "event.topic", "topic_id": 12, "payload_type": "float"},
                {"id": "pub", "type": "event.publisher", "topic": "topic_evt", "source": "mod"},
            ],
            "edges": [
                {"id": "e1", "from": "src", "to": "mod", "from_port": "sensor", "to_port": "module_input", "kind": "data_flow"},
                {"id": "e2", "from": "mod", "to": "pub", "from_port": "event_source", "to_port": "event_source", "kind": "event"},
                {"id": "e3", "from": "topic_evt", "to": "pub", "from_port": "topic", "to_port": "topic", "kind": "event"},
            ],
            "flows": [],
            "tasks": [],
            "custom_files": [{
                "path": "app_custom.c",
                "content": '#include "efw/efw.h"\n'
                           'efw_status_t app_read_sensor(void *ctx, void *out){EFW_UNUSED(ctx); if(out) *(float*)out = 4.0f; return EFW_OK;}\n'
                           'efw_status_t app_poll_module(void *ctx, const efw_app_multi_input_t *in){EFW_UNUSED(ctx); EFW_UNUSED(in); return EFW_OK;}\n'
            }],
            "ui": {"positions": {}},
        }
        files = self.render_graph(graph)
        bootstrap_c = files["app_bootstrap.c"]
        self.assertIn("app_cache_source_mod(&mapped_out", bootstrap_c)

    def test_nested_path_mapping_validates_and_generates(self) -> None:
        graph = {
            "project": {"name": "nested_path", "tick_ms": 1},
            "board": {"profile": "generic-mock", "pin_plan": []},
            "nodes": [
                {"id": "inner_type", "type": "data.struct", "name": "inner_t", "fields": [{"type": "float", "name": "value"}]},
                {"id": "outer_type", "type": "data.struct", "name": "outer_t", "fields": [{"type": "inner_t", "name": "nested"}]},
                {"id": "src", "type": "sensor.custom", "read": "app_read_sensor", "output_contract": "outer_t", "output_type": "outer_t", "output_size": 4},
                {"id": "proc", "type": "processor.custom", "output_contract": "float", "output_type": "float", "output_mode": "scalar_compute", "process_mode": "mapping_only", "primary_input_port": "sensor", "field_mappings": [{"field": "", "source": "sensor", "path": "nested.value", "transform": "identity", "required": True}]},
            ],
            "edges": [
                {"id": "e1", "from": "src", "to": "proc", "from_port": "sensor", "to_port": "sensor", "kind": "data_flow"},
            ],
            "flows": [],
            "tasks": [],
            "custom_files": [{"path": "app_custom.c", "content": '#include "efw/efw.h"\nefw_status_t app_read_sensor(void *ctx, void *out){EFW_UNUSED(ctx); EFW_UNUSED(out); return EFW_OK;}\n'}],
            "ui": {"positions": {}},
        }
        files = self.render_graph(graph)
        self.assertIn("->nested.value", files["app_bootstrap.c"])

    def test_invalid_expr_and_transform_type_are_rejected(self) -> None:
        graph = {
            "project": {"name": "invalid_mapping_rules", "tick_ms": 1},
            "board": {"profile": "generic-mock", "pin_plan": []},
            "nodes": [
                {"id": "proc", "type": "processor.custom", "output_contract": "efw_pid_input_t", "output_type": "efw_pid_input_t", "output_mode": "assemble_struct", "process_mode": "mapping_only", "field_mappings": [{"field": "feedback", "source": "expr", "expr": "a();", "transform": "identity", "required": True}, {"field": "dt", "source": "const", "value": 1, "transform": "to_uint16", "required": True}]},
            ],
            "edges": [],
            "flows": [],
            "tasks": [],
            "custom_files": [],
            "ui": {"positions": {}},
        }
        with self.assertRaisesRegex(ValueError, "expr|to_uint16"):
            validate_graph(graph)


if __name__ == "__main__":
    unittest.main()
