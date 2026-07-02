from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest import mock

CODE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src", "litetune-skill", "code"))
if CODE_DIR not in sys.path:
    sys.path.insert(0, CODE_DIR)

import daemon_frames
import daemon_ops
import litetune_protocol as proto
from daemon_frames import ensure_raw_fits, make_cmd_request_frame, make_param_get_frame, make_param_set_frame
from daemon_state import BadRequestError, BusinessDaemonError, DaemonState, FrameTooLargeError, NotFoundError, NotReadyError, TimeoutDaemonError


class LiteTuneDaemonOpsTests(unittest.IsolatedAsyncioTestCase):
    def make_state(self) -> DaemonState:
        runtime = tempfile.mkdtemp(prefix="litetune-test-")
        state = DaemonState(
            port="fake-port",
            baud=115200,
            socket_path=os.path.join(runtime, "litetune.sock"),
            log_path=os.path.join(runtime, "daemon.jsonl"),
            daemon_json_path=os.path.join(runtime, "daemon.json"),
            runtime_dir=runtime,
        )
        state.active_schema = {
            "ready": True,
            "features": {"enabled": ["PARAM_GET", "PARAM_SET", "CMD"]},
            "host": {"peer_max_decoded_frame": 2048},
            "layouts": {},
            "params": {
                "gain": {"id": 1, "type": "u16", "unit": "mV"},
                "enabled": {"id": 2, "type": "bool", "unit": ""},
            },
            "commands": {
                "reboot": {"id": 7, "flags": ["HOST_TO_MCU"], "flags_mask": "0x01"},
                "read_only": {"id": 8, "flags": [], "flags_mask": "0x00"},
            },
        }
        state.schema_ready.set()
        return state

    async def test_param_get_builds_request_and_returns_param_map(self) -> None:
        state = self.make_state()

        async def fake_send(send_state, frame, expected_type, timeout_s):
            self.assertIs(send_state, state)
            self.assertEqual(frame.type_name, "PARAM_GET")
            self.assertEqual(frame.payload, proto.build_param_get_payload([1]))
            self.assertEqual(expected_type, "PARAM_REPORT")
            self.assertEqual(timeout_s, 0.25)
            report = {
                "overall_status": "OK",
                "items": [
                    {"name": "gain", "id": 1, "type": "u16", "unit": "mV", "value": 42, "item_status": "OK"}
                ],
            }
            return frame, report

        with mock.patch.object(daemon_ops, "send_request_wait_response", side_effect=fake_send):
            result = await daemon_ops.op_param_get(state, {"names": ["gain"], "timeout_s": 0.25})

        self.assertEqual(result["requested"], ["gain"])
        self.assertEqual(result["params"], {"gain": {"id": 1, "type": "u16", "unit": "mV", "value": 42, "status": "OK"}})

    async def test_param_set_accepts_values_object_and_items_list(self) -> None:
        state = self.make_state()
        captured_payloads: list[bytes] = []

        async def fake_send(_state, frame, expected_type, timeout_s):
            captured_payloads.append(frame.payload)
            self.assertEqual(expected_type, "PARAM_REPORT")
            report = {
                "overall_status": "OK",
                "items": [
                    {"name": "gain", "id": 1, "type": "u16", "unit": "mV", "value": 55, "item_status": "OK"},
                    {"name": "enabled", "id": 2, "type": "bool", "unit": "", "value": True, "item_status": "OK"},
                ],
            }
            return frame, report

        with mock.patch.object(daemon_ops, "send_request_wait_response", side_effect=fake_send):
            result = await daemon_ops.op_param_set(state, {"values": {"gain": 55, "enabled": True}})
            result_from_items = await daemon_ops.op_param_set(
                state,
                {"items": [{"name": "gain", "value": 55}, {"name": "enabled", "value": True}]},
            )

        expected_payload = proto.build_param_set_payload(
            [
                {"id": 1, "type": "u16", "value": 55},
                {"id": 2, "type": "bool", "value": True},
            ]
        )
        self.assertEqual(captured_payloads, [expected_payload, expected_payload])
        self.assertEqual(result["params"]["gain"]["value"], 55)
        self.assertEqual(result_from_items["params"]["enabled"]["value"], True)

    async def test_param_set_rejects_missing_param_and_not_ready_schema(self) -> None:
        state = self.make_state()
        with self.assertRaises(NotFoundError):
            await daemon_ops.op_param_set(state, {"values": {"missing": 1}})

        state.schema_ready.clear()
        with self.assertRaises(NotReadyError):
            await daemon_ops.op_param_set(state, {"values": {"gain": 1}})

    async def test_param_report_non_ok_raises_business_error(self) -> None:
        state = self.make_state()

        async def fake_send(_state, frame, expected_type, timeout_s):
            return frame, {"overall_status": "DENIED", "items": []}

        with mock.patch.object(daemon_ops, "send_request_wait_response", side_effect=fake_send):
            with self.assertRaises(BusinessDaemonError) as ctx:
                await daemon_ops.op_param_get(state, {"names": ["gain"]})
        self.assertEqual(ctx.exception.details["status"], "DENIED")

    async def test_param_set_encoding_errors_are_bad_request(self) -> None:
        state = self.make_state()
        with self.assertRaises(BadRequestError) as ctx:
            await daemon_ops.op_param_set(state, {"values": {"gain": 70000}})
        self.assertIn("out of range", str(ctx.exception.details))

    async def test_cmd_run_builds_request_and_rejects_bad_inputs(self) -> None:
        state = self.make_state()

        async def fake_send(_state, frame, expected_type, timeout_s):
            self.assertEqual(frame.type_name, "CMD_REQUEST")
            self.assertEqual(frame.payload, proto.build_cmd_request_payload(7, b"\x01\x02"))
            self.assertEqual(expected_type, "CMD_RESPONSE")
            return frame, {"cmd_id": 7, "status": "OK", "payload_hex": "aabb"}

        with mock.patch.object(daemon_ops, "send_request_wait_response", side_effect=fake_send):
            result = await daemon_ops.op_cmd_run(state, {"name": "reboot", "payload_hex": "0102"})
        self.assertEqual(result, {"cmd": {"name": "reboot", "id": 7, "status": "OK", "payload_hex": "aabb"}})

        with self.assertRaises(BadRequestError):
            await daemon_ops.op_cmd_run(state, {"name": "reboot", "payload_hex": "xyz"})
        with self.assertRaises(BusinessDaemonError):
            await daemon_ops.op_cmd_run(state, {"name": "read_only"})
        with self.assertRaises(NotFoundError):
            await daemon_ops.op_cmd_run(state, {"name": "missing"})

    async def test_cmd_response_id_mismatch_is_rejected(self) -> None:
        state = self.make_state()

        async def fake_send(_state, frame, expected_type, timeout_s):
            return frame, {"cmd_id": 999, "status": "OK", "payload_hex": ""}

        with mock.patch.object(daemon_ops, "send_request_wait_response", side_effect=fake_send):
            with self.assertRaises(BadRequestError):
                await daemon_ops.op_cmd_run(state, {"name": "reboot"})

    async def test_cmd_response_non_ok_raises_business_error(self) -> None:
        state = self.make_state()

        async def fake_send(_state, frame, expected_type, timeout_s):
            return frame, {"cmd_id": 7, "status": "EXEC_ERROR", "payload_hex": ""}

        with mock.patch.object(daemon_ops, "send_request_wait_response", side_effect=fake_send):
            with self.assertRaises(BusinessDaemonError) as ctx:
                await daemon_ops.op_cmd_run(state, {"name": "reboot"})
        self.assertEqual(ctx.exception.details["status"], "EXEC_ERROR")

    async def test_cmd_encoding_errors_are_bad_request(self) -> None:
        state = self.make_state()
        state.active_schema["host"]["peer_max_decoded_frame"] = 13
        with self.assertRaises(BadRequestError) as ctx:
            await daemon_ops.op_cmd_run(state, {"name": "reboot", "payload_hex": "00"})
        self.assertIn("exceed peer", str(ctx.exception.details))

    def test_request_frame_helpers_allocate_ids_and_enforce_size(self) -> None:
        state = self.make_state()
        get_frame = make_param_get_frame(state, [1])
        set_frame = make_param_set_frame(state, [{"id": 1, "type": "u16", "value": 9}])
        cmd_frame = make_cmd_request_frame(state, 7, b"\xaa")
        self.assertEqual((get_frame.frame_id, set_frame.frame_id, cmd_frame.frame_id), (1, 2, 3))
        self.assertEqual(get_frame.payload, proto.build_param_get_payload([1]))
        self.assertEqual(set_frame.payload, proto.build_param_set_payload([{"id": 1, "type": "u16", "value": 9}]))
        self.assertEqual(cmd_frame.payload, b"\x07\x00\xaa")

        state.active_schema["host"]["peer_max_decoded_frame"] = 14
        ensure_raw_fits(state, b"x")
        with self.assertRaises(FrameTooLargeError):
            ensure_raw_fits(state, b"xx")

    async def test_dispatch_uds_request_aliases_and_unknown_op(self) -> None:
        state = self.make_state()
        status = await daemon_ops.dispatch_uds_request(state, {"op": "status"})
        self.assertEqual(status["daemon_id"], state.daemon_id)
        self.assertEqual((await daemon_ops.dispatch_uds_request(state, {"op": "param.list"}))["params"], state.active_schema["params"])
        with self.assertRaises(BadRequestError):
            await daemon_ops.dispatch_uds_request(state, {"op": "does.not.exist"})

    async def test_schema_discovery_surfaces_latest_status(self) -> None:
        state = self.make_state()
        state.schema_timeout_s = 0.01
        state.active_schema = {"ready": True}

        async def fake_put(frame):
            status_frame = proto.RawFrame(proto.TYPE_IDS["STATUS"], 2, b"\x1c")
            await daemon_frames.dispatch_litetune_frame(state, status_frame)

        with mock.patch.object(state.tx_queue, "put", side_effect=fake_put):
            with self.assertRaises(BusinessDaemonError) as ctx:
                await daemon_frames.schema_discovery(state)
        self.assertEqual(ctx.exception.details["status"], "TOO_LARGE")

    async def test_schema_discovery_without_status_times_out(self) -> None:
        state = self.make_state()
        state.schema_timeout_s = 0.01
        state.active_schema = {"ready": True}

        with self.assertRaises(TimeoutDaemonError):
            await daemon_frames.schema_discovery(state)


class LiteTuneDaemonOpsSyncTests(unittest.TestCase):
    def test_normalize_param_set_items_variants_and_errors(self) -> None:
        self.assertEqual(daemon_ops.normalize_param_set_items({"values": {"a": 1}}), [{"name": "a", "value": 1}])
        self.assertEqual(daemon_ops.normalize_param_set_items({"items": [{"name": "a", "value": 2}]}), [{"name": "a", "value": 2}])
        self.assertEqual(daemon_ops.normalize_param_set_items({"name": "a", "value": 3}), [{"name": "a", "value": 3}])
        with self.assertRaises(BadRequestError):
            daemon_ops.normalize_param_set_items({})

    def test_timeout_value_and_report_map(self) -> None:
        self.assertEqual(daemon_ops.timeout_value({"timeout": "1.25"}, 2.0), 1.25)
        self.assertEqual(daemon_ops.timeout_value({}, 2.0), 2.0)
        with self.assertRaises(BadRequestError):
            daemon_ops.timeout_value({"timeout": "nanosecond"}, 2.0)
        self.assertEqual(
            daemon_ops.report_items_as_param_map(
                {"items": [{"name": "gain", "id": 1, "type": "u16", "unit": "mV", "value": 4, "item_status": "OK"}]}
            ),
            {"gain": {"id": 1, "type": "u16", "unit": "mV", "value": 4, "status": "OK"}},
        )


if __name__ == "__main__":
    unittest.main()
