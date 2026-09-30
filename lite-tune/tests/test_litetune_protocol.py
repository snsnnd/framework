from __future__ import annotations

import os
import struct
import sys
import unittest

CODE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src", "litetune-skill", "code"))
if CODE_DIR not in sys.path:
    sys.path.insert(0, CODE_DIR)

import litetune_protocol as proto


class LiteTuneProtocolTests(unittest.TestCase):
    def test_crc_cobs_and_frame_roundtrip(self) -> None:
        self.assertEqual(proto.crc16_mcrf4xx(b"123456789"), 0x6F91)

        samples = [
            b"",
            b"\x00",
            b"abc\x00def\x00",
            bytes(range(1, 255)),
            b"\x00" + bytes(range(1, 255)) + b"\x00tail",
        ]
        for sample in samples:
            with self.subTest(sample=sample[:8], length=len(sample)):
                encoded = proto.cobs_encode(sample)
                self.assertNotIn(0, encoded)
                self.assertEqual(proto.cobs_decode(encoded), sample)

        frame = proto.RawFrame(
            type_id=proto.TYPE_IDS["PARAM_SET"],
            frame_id=0x0102030405060708,
            payload=b"\x02\x00value\x00",
        )
        raw = proto.encode_raw_frame(frame)
        self.assertEqual(proto.parse_raw_frame(raw), frame)
        wire = proto.encode_litetune_wire_frame(frame)
        self.assertTrue(wire.endswith(b"\x00"))
        self.assertNotIn(0, wire[:-1])
        # Serial framing strips the trailing delimiter before COBS decoding.
        self.assertEqual(proto.decode_litetune_wire_frame(wire[:-1]), frame)

        corrupted = bytearray(raw)
        corrupted[-1] ^= 0x01
        with self.assertRaises(proto.ProtocolError):
            proto.parse_raw_frame(bytes(corrupted))
        with self.assertRaises(proto.ProtocolError):
            proto.cobs_decode(b"\x00")

    def test_register_payload_parsers(self) -> None:
        begin_payload = (
            struct.pack("<BBBH I BHH", 0, 5, 0, 1024, (1 << 1) | (1 << 2) | (1 << 3), 1, 2, 1)
            + proto.encode_str8("demo-device")
        )
        begin = proto.parse_register_begin(begin_payload)
        self.assertEqual(begin["protocol"]["version"], "0.5.0")
        self.assertEqual(begin["device"]["name"], "demo-device")
        self.assertEqual(begin["device"]["mcu_max_decoded_frame"], 1024)
        self.assertEqual(begin["layout_count"], 1)
        self.assertEqual(begin["param_count"], 2)
        self.assertEqual(begin["cmd_count"], 1)
        self.assertEqual(begin["features"]["enabled"], ["PARAM_GET", "PARAM_SET", "CMD"])

        layout_payload = (
            struct.pack("<BHB", 7, 100, 2)
            + struct.pack("<HB", 10, proto.VALUE_TYPE_IDS["u16"])
            + proto.encode_str8("rpm")
            + proto.encode_str8("rpm")
            + struct.pack("<HB", 11, proto.VALUE_TYPE_IDS["f32"])
            + proto.encode_str8("temp")
            + proto.encode_str8("C")
        )
        layout = proto.parse_register_log_layout(layout_payload)
        self.assertEqual(layout["id"], 7)
        self.assertEqual(layout["default_period_ms"], 100)
        self.assertEqual(layout["fields"][0], {"id": 10, "type": "u16", "unit": "rpm", "name": "rpm"})
        self.assertEqual(layout["fields"][1]["type"], "f32")

        params_payload = (
            struct.pack("<H", 2)
            + struct.pack("<HB", 1, proto.VALUE_TYPE_IDS["u16"])
            + proto.encode_str8("gain")
            + proto.encode_str8("mV")
            + struct.pack("<HB", 2, proto.VALUE_TYPE_IDS["bool"])
            + proto.encode_str8("enabled")
            + proto.encode_str8("")
        )
        params = proto.parse_register_param_desc(params_payload)
        self.assertEqual(params, {"gain": {"id": 1, "type": "u16", "unit": "mV"}, "enabled": {"id": 2, "type": "bool", "unit": ""}})

        cmd_payload = struct.pack("<H", 1) + struct.pack("<HB", 3, 0x01) + proto.encode_str8("reboot")
        commands = proto.parse_register_cmd_desc(cmd_payload)
        self.assertEqual(commands, {"reboot": {"id": 3, "flags": ["HOST_TO_MCU"], "flags_mask": "0x01"}})

    def test_param_and_cmd_payload_building_and_parsing(self) -> None:
        self.assertEqual(proto.build_param_get_payload([1, 0x0203]), b"\x00\x02\x01\x00\x03\x02")
        self.assertEqual(proto.build_param_get_payload(all_params=True), b"\x01\x00")

        set_payload = proto.build_param_set_payload(
            [
                {"id": 1, "type": "u16", "value": "0x1234"},
                {"id": 2, "type": "bool", "value": "on"},
                {"id": 3, "type": "string", "value": "abc"},
                {"id": 4, "type": "bytes", "value": "hex:00ff"},
            ]
        )
        self.assertEqual(set_payload, b"\x04\x01\x004\x12\x02\x00\x01\x03\x00\x03abc\x04\x00\x02\x00\xff")

        schema = {
            "params": {
                "gain": {"id": 1, "type": "u16", "unit": "mV"},
                "enabled": {"id": 2, "type": "bool", "unit": ""},
            }
        }
        report_payload = (
            struct.pack("<QBBH", 0xABC, 0x00, 0x00, 2)
            + struct.pack("<HB", 1, 0x00)
            + proto.encode_value("u16", 99)
            + struct.pack("<HB", 2, 0x00)
            + proto.encode_value("bool", False)
        )
        report = proto.parse_param_report(report_payload, schema)
        self.assertEqual(report["request_frame_id_int"], 0xABC)
        self.assertEqual(report["report_kind"], "RESPONSE_TO_SET")
        self.assertEqual(report["overall_status"], "OK")
        self.assertEqual(report["items"][0]["value"], 99)
        self.assertEqual(report["items"][1]["value"], False)

        self.assertEqual(proto.build_cmd_request_payload(5, b"\xaa\xbb"), b"\x05\x00\xaa\xbb")
        cmd_response = proto.parse_cmd_response(struct.pack("<QHB", 0xABC, 5, 0x00) + b"\x01\x02")
        self.assertEqual(cmd_response["request_frame_id_int"], 0xABC)
        self.assertEqual(cmd_response["cmd_id"], 5)
        self.assertEqual(cmd_response["status"], "OK")
        self.assertEqual(cmd_response["payload_hex"], "0102")

        with self.assertRaises(proto.ProtocolError):
            proto.build_param_set_payload([])
        with self.assertRaises(proto.ProtocolError):
            proto.parse_param_report(report_payload, {"params": {}})


if __name__ == "__main__":
    unittest.main()
