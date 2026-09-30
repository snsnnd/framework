#!/usr/bin/env python3
"""LiteTune v0.5.0 binary protocol helpers.
This module intentionally contains no serial or daemon code. It only knows how
LiteTune frames and payloads are represented on the wire.
"""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass
from typing import Any

MAGIC = 0xA55A
RAW_FRAME_OVERHEAD = 13
U64_MAX = 0xFFFFFFFFFFFFFFFF
TYPE_NAMES = {
    0x01: "DISCOVER",
    0x02: "REGISTER_BEGIN",
    0x03: "REGISTER_LOG_LAYOUT",
    0x04: "REGISTER_PARAM_DESC",
    0x05: "REGISTER_CMD_DESC",
    0x06: "REGISTER_END",
    0x07: "STATUS",
    0x11: "LOG_REPORT",
    0x12: "LOG_TEXT",
    0x21: "PARAM_SET",
    0x22: "PARAM_GET",
    0x23: "PARAM_REPORT",
    0x31: "CMD_REQUEST",
    0x32: "CMD_RESPONSE",
}
TYPE_IDS = {name: type_id for type_id, name in TYPE_NAMES.items()}
FEATURES = {
    0: "LOG_PACKED",
    1: "PARAM_GET",
    2: "PARAM_SET",
    3: "CMD",
    4: "LOG_TEXT",
}
DEFAULT_REQUESTED_FEATURES = sum(1 << bit for bit in FEATURES)
VALUE_TYPE_NAMES = {
    0x01: "bool",
    0x02: "u8",
    0x03: "i8",
    0x04: "u16",
    0x05: "i16",
    0x06: "u32",
    0x07: "i32",
    0x08: "u64",
    0x09: "i64",
    0x0A: "f32",
    0x0B: "f64",
    0x0C: "string",
    0x0D: "bytes",
    0x0E: "enum_u8",
}
VALUE_TYPE_IDS = {name: type_id for type_id, name in VALUE_TYPE_NAMES.items()}
VALUE_STRUCTS = {
    "u8": ("<B", 0, 0xFF),
    "i8": ("<b", -0x80, 0x7F),
    "u16": ("<H", 0, 0xFFFF),
    "i16": ("<h", -0x8000, 0x7FFF),
    "u32": ("<I", 0, 0xFFFFFFFF),
    "i32": ("<i", -0x80000000, 0x7FFFFFFF),
    "u64": ("<Q", 0, U64_MAX),
    "i64": ("<q", -0x8000000000000000, 0x7FFFFFFFFFFFFFFF),
    "f32": ("<f", None, None),
    "f64": ("<d", None, None),
    "enum_u8": ("<B", 0, 0xFF),
}
STATUS_NAMES = {
    0x00: "OK",
    0x01: "ACCEPTED",
    0x02: "PARTIAL_OK",
    0x10: "VERSION_UNSUPPORTED",
    0x11: "UNKNOWN_TYPE",
    0x13: "BAD_PAYLOAD",
    0x14: "NOT_FOUND",
    0x15: "TYPE_MISMATCH",
    0x16: "RANGE_ERROR",
    0x18: "BUSY",
    0x19: "STORAGE_ERROR",
    0x1A: "DENIED",
    0x1B: "EXEC_ERROR",
    0x1C: "TOO_LARGE",
    0x1D: "UNSUPPORTED",
    0x1E: "TIMEOUT",
    0x1F: "CONFLICT",
    0x20: "NOT_READY",
    0x21: "INVALID_STATE",
    0x22: "FRAME_DECODE_ERROR",
    0x23: "CRC_ERROR",
    0x24: "RX_OVERFLOW",
    0x25: "TX_DROP",
    0x7F: "UNKNOWN_ERROR",
}
REPORT_KIND_NAMES = {
    0x00: "RESPONSE_TO_SET",
    0x01: "RESPONSE_TO_GET",
    0x02: "PARAM_CHANGED_EVENT",
    0x03: "ERROR_ONLY",
}
LOG_LEVEL_NAMES = {
    0x00: "DEBUG",
    0x01: "INFO",
    0x02: "WARN",
    0x03: "ERROR",
    0x04: "FATAL",
}


class ProtocolError(ValueError):
    """Raised when bytes cannot be parsed as a valid LiteTune object."""


@dataclass(frozen=True)
class RawFrame:
    type_id: int
    frame_id: int
    payload: bytes = b""

    @property
    def type_name(self) -> str:
        return type_name(self.type_id)


@dataclass
class ByteReader:
    data: bytes
    offset: int = 0

    def remaining(self) -> int:
        return len(self.data) - self.offset

    def require_done(self) -> None:
        if self.remaining() != 0:
            raise ProtocolError(f"trailing payload bytes: {self.remaining()}")

    def read(self, size: int) -> bytes:
        if size < 0 or self.offset + size > len(self.data):
            raise ProtocolError("payload too short")
        chunk = self.data[self.offset : self.offset + size]
        self.offset += size
        return chunk

    def rest(self) -> bytes:
        return self.read(self.remaining())

    def u8(self) -> int:
        return self.read(1)[0]

    def u16(self) -> int:
        return struct.unpack("<H", self.read(2))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.read(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self.read(8))[0]

    def str8(self) -> str:
        raw = self.bytes8()
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProtocolError("invalid UTF-8 str8") from exc

    def bytes8(self) -> bytes:
        size = self.u8()
        return self.read(size)


# ---------------------------------------------------------------------------
# Small formatting helpers


def type_name(type_id: int) -> str:
    if type_id in TYPE_NAMES:
        return TYPE_NAMES[type_id]
    if 0x40 <= type_id <= 0x7F:
        return f"PROJECT_SPECIFIC_0x{type_id:02X}"
    return f"UNKNOWN_0x{type_id:02X}"


def status_name(code: int) -> str:
    return STATUS_NAMES.get(code, f"USER_0x{code:02X}" if code >= 0x80 else f"UNKNOWN_0x{code:02X}")


def hex64(value: int) -> str:
    return f"0x{value & U64_MAX:016X}"


def features_to_names(mask: int) -> list[str]:
    return [name for bit, name in FEATURES.items() if mask & (1 << bit)]


def cmd_flags_to_names(flags: int) -> list[str]:
    names = []
    if flags & 0x01:
        names.append("HOST_TO_MCU")
    if flags & 0xFE:
        names.append(f"RESERVED_0x{flags & 0xFE:02X}")
    return names


def stable_digest(data: Any) -> str:
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# COBS and RawFrame layer


def crc16_mcrf4xx(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0x8408
            else:
                crc >>= 1
            crc &= 0xFFFF
    return crc & 0xFFFF


def cobs_encode(data: bytes) -> bytes:
    out = bytearray([0])
    code_index = 0
    code = 1
    for byte in data:
        if byte == 0:
            out[code_index] = code
            code_index = len(out)
            out.append(0)
            code = 1
            continue
        out.append(byte)
        code += 1
        if code == 0xFF:
            out[code_index] = code
            code_index = len(out)
            out.append(0)
            code = 1
    out[code_index] = code
    return bytes(out)


def cobs_decode(data: bytes) -> bytes:
    out = bytearray()
    index = 0
    while index < len(data):
        code = data[index]
        if code == 0:
            raise ProtocolError("COBS code byte is zero")
        index += 1
        end = index + code - 1
        if end > len(data):
            raise ProtocolError("COBS code exceeds frame length")
        out.extend(data[index:end])
        index = end
        if code < 0xFF and index < len(data):
            out.append(0)
    return bytes(out)


def encode_raw_frame(frame: RawFrame) -> bytes:
    if frame.frame_id == 0:
        raise ProtocolError("FrameID must not be zero")
    if not 0 <= frame.type_id <= 0xFF:
        raise ProtocolError("frame type out of range")
    header = struct.pack("<HBQ", MAGIC, frame.type_id, frame.frame_id & U64_MAX)
    body = header + frame.payload
    crc = crc16_mcrf4xx(body)
    return body + struct.pack("<H", crc)


def parse_raw_frame(raw: bytes) -> RawFrame:
    if len(raw) < RAW_FRAME_OVERHEAD:
        raise ProtocolError("RawFrame too short")
    got_crc = struct.unpack("<H", raw[-2:])[0]
    body = raw[:-2]
    calc_crc = crc16_mcrf4xx(body)
    if calc_crc != got_crc:
        raise ProtocolError(f"CRC mismatch: got 0x{got_crc:04X}, expected 0x{calc_crc:04X}")
    magic, type_id, frame_id = struct.unpack("<HBQ", body[:11])
    if magic != MAGIC:
        raise ProtocolError(f"bad magic: 0x{magic:04X}")
    if frame_id == 0:
        raise ProtocolError("FrameID must not be zero")
    return RawFrame(type_id=type_id, frame_id=frame_id, payload=body[11:])


def encode_litetune_wire_frame(frame: RawFrame) -> bytes:
    return cobs_encode(encode_raw_frame(frame)) + b"\x00"


def decode_litetune_wire_frame(wire: bytes) -> RawFrame:
    return parse_raw_frame(cobs_decode(wire))


def raw_frame_len(payload: bytes) -> int:
    return RAW_FRAME_OVERHEAD + len(payload)


# ---------------------------------------------------------------------------
# Primitive value encoding / decoding


def encode_str8(value: str) -> bytes:
    raw = value.encode("utf-8")
    if len(raw) > 255:
        raise ProtocolError("str8 too long")
    return bytes([len(raw)]) + raw


def encode_bytes8(raw: bytes) -> bytes:
    if len(raw) > 255:
        raise ProtocolError("bytes8 too long")
    return bytes([len(raw)]) + raw


def parse_int_text(value: Any) -> int:
    if isinstance(value, bool):
        raise ProtocolError("boolean is not an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 0)
    raise ProtocolError(f"cannot parse integer from {value!r}")


def parse_bool_text(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    raise ProtocolError(f"cannot parse boolean from {value!r}")


def encode_value(type_name_value: str, value: Any) -> bytes:
    if type_name_value == "bool":
        return struct.pack("<B", 1 if parse_bool_text(value) else 0)
    if type_name_value == "string":
        return encode_str8(str(value))
    if type_name_value == "bytes":
        if isinstance(value, bytes):
            raw = value
        elif isinstance(value, str):
            text = value[4:] if value.startswith("hex:") else value
            raw = bytes.fromhex(text)
        else:
            raise ProtocolError("bytes value must be bytes or hex text")
        return encode_bytes8(raw)
    if type_name_value in {"f32", "f64"}:
        fmt, _low, _high = VALUE_STRUCTS[type_name_value]
        return struct.pack(fmt, float(value))
    if type_name_value in VALUE_STRUCTS:
        fmt, low, high = VALUE_STRUCTS[type_name_value]
        parsed = parse_int_text(value)
        if parsed < low or parsed > high:
            raise ProtocolError(f"{type_name_value} out of range")
        return struct.pack(fmt, parsed)
    raise ProtocolError(f"unsupported value type: {type_name_value}")


def decode_value(reader: ByteReader, type_name_value: str) -> Any:
    if type_name_value == "bool":
        return bool(reader.u8())
    if type_name_value == "string":
        return reader.str8()
    if type_name_value == "bytes":
        return reader.bytes8().hex()
    if type_name_value in VALUE_STRUCTS:
        fmt, _low, _high = VALUE_STRUCTS[type_name_value]
        value = struct.unpack(fmt, reader.read(struct.calcsize(fmt)))[0]
        if type_name_value in {"u64", "i64"}:
            return str(value)
        return value
    raise ProtocolError(f"unsupported value type: {type_name_value}")


# ---------------------------------------------------------------------------
# Payload builders


def build_discover_payload(
    host_max_decoded_frame: int = 2048,
    requested_features: int = DEFAULT_REQUESTED_FEATURES,
    response_timeout_ms: int = 1000,
    host_name: str = "litetune-agent",
) -> bytes:
    return (
        struct.pack("<BBBH I H", 0, 5, 0, host_max_decoded_frame, requested_features, response_timeout_ms)
        + encode_str8(host_name)
    )


def build_param_get_payload(param_ids: list[int] | None = None, all_params: bool = False) -> bytes:
    if all_params:
        return bytes([0x01, 0])
    ids = param_ids or []
    if not ids or len(ids) > 255:
        raise ProtocolError("PARAM_GET BY_ID requires 1..255 param ids")
    payload = bytearray([0x00, len(ids)])
    for param_id in ids:
        payload.extend(struct.pack("<H", param_id))
    return bytes(payload)


def build_param_set_payload(items: list[dict[str, Any]]) -> bytes:
    if not items or len(items) > 255:
        raise ProtocolError("PARAM_SET requires 1..255 items")
    payload = bytearray([len(items)])
    for item in items:
        payload.extend(struct.pack("<H", int(item["id"])))
        payload.extend(encode_value(item["type"], item["value"]))
    return bytes(payload)


def build_cmd_request_payload(cmd_id: int, payload: bytes = b"") -> bytes:
    return struct.pack("<H", cmd_id) + payload


# ---------------------------------------------------------------------------
# Payload parsers


def _read_descriptor_name_unit(reader: ByteReader) -> tuple[str, str]:
    return reader.str8(), reader.str8()


def parse_register_begin(payload: bytes) -> dict[str, Any]:
    reader = ByteReader(payload)
    if reader.remaining() < 15:
        raise ProtocolError("REGISTER_BEGIN payload too short")
    major = reader.u8()
    minor = reader.u8()
    patch = reader.u8()
    max_frame = reader.u16()
    features = reader.u32()
    layout_count = reader.u8()
    param_count = reader.u16()
    cmd_count = reader.u16()
    device_name = reader.str8()
    reader.require_done()
    return {
        "protocol": {"name": "LiteTune", "version": f"{major}.{minor}.{patch}"},
        "device": {"name": device_name, "mcu_max_decoded_frame": max_frame},
        "features": {"mask": f"0x{features:08X}", "enabled": features_to_names(features)},
        "layout_count": layout_count,
        "param_count": param_count,
        "cmd_count": cmd_count,
    }


def parse_register_log_layout(payload: bytes) -> dict[str, Any]:
    reader = ByteReader(payload)
    layout_id = reader.u8()
    default_period_ms = reader.u16()
    field_count = reader.u8()
    fields = []
    seen_ids = set()
    for _ in range(field_count):
        field_id = reader.u16()
        value_type_id = reader.u8()
        name, unit = _read_descriptor_name_unit(reader)
        if field_id in seen_ids:
            raise ProtocolError(f"duplicate field id {field_id}")
        seen_ids.add(field_id)
        fields.append(
            {
                "id": field_id,
                "type": VALUE_TYPE_NAMES.get(value_type_id, f"unknown_0x{value_type_id:02X}"),
                "unit": unit,
                "name": name,
            }
        )
    reader.require_done()
    return {"id": layout_id, "default_period_ms": default_period_ms, "fields": fields}


def parse_register_param_desc(payload: bytes) -> dict[str, dict[str, Any]]:
    reader = ByteReader(payload)
    param_count = reader.u16()
    params: dict[str, dict[str, Any]] = {}
    seen_ids = set()
    for _ in range(param_count):
        param_id = reader.u16()
        value_type_id = reader.u8()
        name, unit = _read_descriptor_name_unit(reader)
        if param_id in seen_ids:
            raise ProtocolError(f"duplicate param id {param_id}")
        if name in params:
            raise ProtocolError(f"duplicate param name {name}")
        seen_ids.add(param_id)
        params[name] = {
            "id": param_id,
            "type": VALUE_TYPE_NAMES.get(value_type_id, f"unknown_0x{value_type_id:02X}"),
            "unit": unit,
        }
    reader.require_done()
    return params


def parse_register_cmd_desc(payload: bytes) -> dict[str, dict[str, Any]]:
    reader = ByteReader(payload)
    cmd_count = reader.u16()
    commands: dict[str, dict[str, Any]] = {}
    seen_ids = set()
    for _ in range(cmd_count):
        cmd_id = reader.u16()
        flags = reader.u8()
        name = reader.str8()
        if cmd_id in seen_ids:
            raise ProtocolError(f"duplicate command id {cmd_id}")
        if name in commands:
            raise ProtocolError(f"duplicate command name {name}")
        seen_ids.add(cmd_id)
        commands[name] = {"id": cmd_id, "flags": cmd_flags_to_names(flags), "flags_mask": f"0x{flags:02X}"}
    reader.require_done()
    return commands


def param_schema_by_id(schema: dict[str, Any]) -> dict[int, tuple[str, dict[str, Any]]]:
    return {int(item["id"]): (name, item) for name, item in schema.get("params", {}).items()}


def parse_param_report(payload: bytes, schema: dict[str, Any] | None) -> dict[str, Any]:
    reader = ByteReader(payload)
    request_frame_id = reader.u64()
    report_kind_id = reader.u8()
    overall_status_id = reader.u8()
    item_count = reader.u16()
    by_id = param_schema_by_id(schema or {})
    items = []
    for _ in range(item_count):
        param_id = reader.u16()
        item_status_id = reader.u8()
        if param_id not in by_id:
            raise ProtocolError(f"PARAM_REPORT references unknown param id {param_id}")
        name, desc = by_id[param_id]
        value = decode_value(reader, desc["type"])
        items.append(
            {
                "name": name,
                "id": param_id,
                "type": desc["type"],
                "unit": desc.get("unit", ""),
                "value": value,
                "item_status": status_name(item_status_id),
            }
        )
    reader.require_done()
    return {
        "request_frame_id": hex64(request_frame_id),
        "request_frame_id_int": request_frame_id,
        "report_kind": REPORT_KIND_NAMES.get(report_kind_id, f"UNKNOWN_0x{report_kind_id:02X}"),
        "overall_status": status_name(overall_status_id),
        "items": items,
    }


def parse_cmd_response(payload: bytes) -> dict[str, Any]:
    reader = ByteReader(payload)
    request_frame_id = reader.u64()
    cmd_id = reader.u16()
    status_id = reader.u8()
    user_payload = reader.rest()
    return {
        "request_frame_id": hex64(request_frame_id),
        "request_frame_id_int": request_frame_id,
        "cmd_id": cmd_id,
        "status": status_name(status_id),
        "payload_hex": user_payload.hex(),
    }


def parse_status(payload: bytes) -> dict[str, Any]:
    reader = ByteReader(payload)
    code = reader.u8()
    reader.require_done()
    return {"status": status_name(code), "code": code}


def parse_log_text(payload: bytes) -> dict[str, Any]:
    reader = ByteReader(payload)
    level = reader.u8()
    text = reader.str8()
    reader.require_done()
    return {"level": LOG_LEVEL_NAMES.get(level, f"USER_0x{level:02X}"), "text": text}


def parse_log_report(payload: bytes, schema: dict[str, Any] | None) -> dict[str, Any]:
    reader = ByteReader(payload)
    layout_id = reader.u8()
    sample_seq = reader.u16()
    layout = (schema or {}).get("layouts", {}).get(str(layout_id))
    if layout is None:
        return {"layout_id": layout_id, "sample_seq": sample_seq, "raw_hex": reader.rest().hex(), "decoded": False}
    fields = []
    for field in layout.get("fields", []):
        fields.append({**field, "value": decode_value(reader, field["type"])})
    reader.require_done()
    return {"layout_id": layout_id, "sample_seq": sample_seq, "fields": fields, "decoded": True}
