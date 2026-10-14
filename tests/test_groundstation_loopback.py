#!/usr/bin/env python3
"""Ground-station protocol loopback tests without real serial hardware."""

from __future__ import annotations

import struct
import sys
import tempfile
import unittest
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.groundstation import protocol as proto
from tools.groundstation.daemon_frames import dispatch_litetune_frame
from tools.groundstation.daemon_state import DaemonState, PendingRequest


class GroundStationLoopbackTest(unittest.TestCase):
    def test_frame_schema_param_cmd_and_log_loopback(self) -> None:
        frame = proto.RawFrame(proto.TYPE_IDS["STATUS"], 7, bytes([0x00]))
        wire = proto.encode_litetune_wire_frame(frame)
        self.assertEqual(proto.decode_litetune_wire_frame(wire[:-1]), frame)

        register_begin = (
            struct.pack("<BBBHIBHH", 0, 5, 0, 256, proto.DEFAULT_REQUESTED_FEATURES, 1, 1, 1)
            + proto.encode_str8("efw-loopback")
        )
        begin = proto.parse_register_begin(register_begin)
        self.assertEqual(begin["device"]["name"], "efw-loopback")

        layout_payload = (
            struct.pack("<BHB", 0x10, 10, 1)
            + struct.pack("<HB", 1, proto.VALUE_TYPE_IDS["u32"])
            + proto.encode_str8("ticks")
            + proto.encode_str8("ms")
        )
        layout = proto.parse_register_log_layout(layout_payload)
        self.assertEqual(layout["fields"][0]["name"], "ticks")

        param_payload = (
            struct.pack("<H", 1)
            + struct.pack("<HB", 0x1000, proto.VALUE_TYPE_IDS["u32"])
            + proto.encode_str8("sm.main.time_ms")
            + proto.encode_str8("ms")
        )
        params = proto.parse_register_param_desc(param_payload)
        self.assertEqual(params["sm.main.time_ms"]["type"], "u32")

        cmd_payload = struct.pack("<H", 1) + struct.pack("<HB", 0x0101, 0x01) + proto.encode_str8("debug.stats")
        commands = proto.parse_register_cmd_desc(cmd_payload)
        self.assertIn("HOST_TO_MCU", commands["debug.stats"]["flags"])

        schema = {"params": params, "layouts": {"16": layout}, "commands": commands}
        report_payload = struct.pack("<QBBH", 99, 0x01, 0x00, 1) + struct.pack("<HB", 0x1000, 0x00) + struct.pack("<I", 42)
        report = proto.parse_param_report(report_payload, schema)
        self.assertEqual(report["items"][0]["value"], 42)

        cmd_response = proto.parse_cmd_response(struct.pack("<QHB", 99, 0x0101, 0x00) + b"\x01\x02")
        self.assertEqual(cmd_response["payload_hex"], "0102")

        text = proto.parse_log_text(bytes([0x01]) + proto.encode_str8("sm.transition name=sm.main from=idle to=run"))
        self.assertIn("sm.transition", text["text"])

        log_report = proto.parse_log_report(struct.pack("<BH", 0x10, 3) + struct.pack("<I", 1234), schema)
        self.assertTrue(log_report["decoded"])
        self.assertEqual(log_report["fields"][0]["value"], 1234)


class GroundStationFakeDaemonTest(unittest.IsolatedAsyncioTestCase):
    async def test_fake_daemon_state_schema_requests_and_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = DaemonState(
                port="fake",
                baud=115200,
                socket_path=str(root / "daemon.sock"),
                log_path=str(root / "daemon.jsonl"),
                daemon_json_path=str(root / "daemon.json"),
                runtime_dir=str(root),
            )

            begin_payload = (
                struct.pack("<BBBHIBHH", 0, 5, 0, 256, proto.DEFAULT_REQUESTED_FEATURES, 1, 1, 1)
                + proto.encode_str8("efw-fake")
            )
            await dispatch_litetune_frame(state, proto.RawFrame(proto.TYPE_IDS["REGISTER_BEGIN"], 1, begin_payload))
            await dispatch_litetune_frame(state, proto.RawFrame(proto.TYPE_IDS["REGISTER_LOG_LAYOUT"], 2,
                struct.pack("<BHB", 0x11, 0, 2)
                + struct.pack("<HB", 0xF001, proto.VALUE_TYPE_IDS["u16"])
                + proto.encode_str8("trace.event_id")
                + proto.encode_str8("")
                + struct.pack("<HB", 0xF004, proto.VALUE_TYPE_IDS["u32"])
                + proto.encode_str8("trace.mcu_time_ms")
                + proto.encode_str8("ms")
            ))
            await dispatch_litetune_frame(state, proto.RawFrame(proto.TYPE_IDS["REGISTER_PARAM_DESC"], 3,
                struct.pack("<H", 1)
                + struct.pack("<HB", 0x1000, proto.VALUE_TYPE_IDS["string"])
                + proto.encode_str8("app.mode")
                + proto.encode_str8("")
            ))
            await dispatch_litetune_frame(state, proto.RawFrame(proto.TYPE_IDS["REGISTER_CMD_DESC"], 4,
                struct.pack("<H", 1)
                + struct.pack("<HB", 0x0103, 0x01)
                + proto.encode_str8("debug.perf")
            ))
            await dispatch_litetune_frame(state, proto.RawFrame(proto.TYPE_IDS["REGISTER_END"], 5, b""))

            self.assertTrue(state.schema_ready.is_set())
            self.assertEqual(state.state, "ready")
            self.assertEqual(state.active_schema["device"]["name"], "efw-fake")
            self.assertEqual(state.active_schema["params"]["app.mode"]["type"], "string")

            loop = asyncio.get_running_loop()
            param_future = loop.create_future()
            state.pending[55] = PendingRequest(55, "PARAM_REPORT", param_future, loop.time(), 1.0)
            await dispatch_litetune_frame(state, proto.RawFrame(proto.TYPE_IDS["PARAM_REPORT"], 6,
                struct.pack("<QBBH", 55, 0x00, 0x00, 1)
                + struct.pack("<HB", 0x1000, 0x00)
                + proto.encode_str8("AUTO")
            ))
            _frame, param_payload = param_future.result()
            self.assertEqual(param_payload["items"][0]["value"], "AUTO")

            cmd_future = loop.create_future()
            state.pending[56] = PendingRequest(56, "CMD_RESPONSE", cmd_future, loop.time(), 1.0)
            await dispatch_litetune_frame(state, proto.RawFrame(proto.TYPE_IDS["CMD_RESPONSE"], 7,
                struct.pack("<QHB", 56, 0x0103, 0x00) + b"\x01\x02"
            ))
            _frame, cmd_payload = cmd_future.result()
            self.assertEqual(cmd_payload["cmd_id"], 0x0103)
            self.assertEqual(cmd_payload["payload_hex"], "0102")

            await dispatch_litetune_frame(state, proto.RawFrame(proto.TYPE_IDS["LOG_REPORT"], 8,
                struct.pack("<BH", 0x11, 1) + struct.pack("<HI", 0x1234, 99)
            ))
            await dispatch_litetune_frame(state, proto.RawFrame(proto.TYPE_IDS["LOG_TEXT"], 9,
                bytes([0x01]) + proto.encode_str8("fallback trace")
            ))

            self.assertEqual(state.stats["telemetry_logged"], 1)
            events = []
            while not state.log_queue.empty():
                events.append(await state.log_queue.get())
            event_types = [event["type"] for event in events]
            self.assertIn("LOG_REPORT", event_types)
            self.assertIn("LOG_TEXT", event_types)


if __name__ == "__main__":
    unittest.main()
