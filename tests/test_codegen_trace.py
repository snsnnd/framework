#!/usr/bin/env python3
"""Codegen trace instrumentation tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from codegen.generator import render_dataflow_pipelines  # noqa: E402


class CodegenTraceTest(unittest.TestCase):
    def test_dataflow_pipeline_emits_node_and_edge_trace(self) -> None:
        nodes = [
            {"id": "sensor_a", "type": "sensor.custom"},
            {"id": "proc_a", "type": "processor.custom", "process": "process_a"},
            {"id": "motor_a", "type": "actuator.custom"},
        ]
        ctx = {
            "project": {"tick_ms": 1},
            "nodes": nodes,
            "nodes_by_id": {node["id"]: node for node in nodes},
            "runtime_dataflows": [["sensor_a", "proc_a", "motor_a"]],
            "contracts": {},
        }
        code = render_dataflow_pipelines(ctx)
        self.assertIn('efw_app_trace_event_ex("dataflow.begin"', code)
        self.assertIn('efw_app_trace_event_ex("node.begin", "sensor_a"', code)
        self.assertIn('efw_app_trace_event_ex("node.end", "proc_a"', code)
        self.assertIn('efw_app_trace_event_ex("dataflow.edge", "sensor_a->proc_a"', code)
        self.assertIn('efw_app_trace_event_ex("dataflow.end"', code)
        self.assertIn("app_elapsed_ms()", code)
        self.assertIn("EFW_APP_TRACE_DURATION_UNKNOWN", code)


if __name__ == "__main__":
    unittest.main()
