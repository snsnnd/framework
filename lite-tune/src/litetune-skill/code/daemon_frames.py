#!/usr/bin/env python3
"""Serial, frame dispatch and schema discovery for LiteTune daemon."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from daemon_state import (
    BusinessDaemonError,
    DaemonError,
    DaemonState,
    FrameTooLargeError,
    NotReadyError,
    PendingRequest,
    SchemaBuilder,
    TimeoutDaemonError,
    log_event,
    set_state,
)
from litetune_protocol import (
    TYPE_IDS,
    ProtocolError,
    RawFrame,
    build_cmd_request_payload,
    build_discover_payload,
    build_param_get_payload,
    build_param_set_payload,
    decode_litetune_wire_frame,
    encode_litetune_wire_frame,
    hex64,
    parse_cmd_response,
    parse_log_report,
    parse_log_text,
    parse_param_report,
    parse_register_begin,
    parse_register_cmd_desc,
    parse_register_log_layout,
    parse_register_param_desc,
    parse_status,
    raw_frame_len,
    stable_digest,
)


class LiteTuneSerialProtocol(asyncio.Protocol):
    def __init__(self, state: DaemonState) -> None:
        self.state = state
        self.buf = bytearray()

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.state.serial_transport = transport
        asyncio.create_task(log_event(self.state, "local", "SERIAL_OPEN", {"port": self.state.port, "baud": self.state.baud}))

    def data_received(self, data: bytes) -> None:
        self.buf.extend(data)
        while True:
            try:
                idx = self.buf.index(0)
            except ValueError:
                break
            wire = bytes(self.buf[:idx])
            del self.buf[: idx + 1]
            if wire:
                self.state.rx_queue.put_nowait(wire)

    def connection_lost(self, exc: Exception | None) -> None:
        self.state.serial_transport = None
        asyncio.create_task(handle_serial_disconnect(self.state, exc))


async def handle_serial_disconnect(state: DaemonState, exc: Exception | None) -> None:
    await log_event(state, "local", "SERIAL_CLOSED", {"error": str(exc) if exc else None})
    if not state.stopping:
        await fail_all_pending(state, "SERIAL_CLOSED", "serial connection lost")
        await set_state(state, "error")
        state.shutdown_event.set()


async def serial_tx_loop(state: DaemonState) -> None:
    while True:
        frame = await state.tx_queue.get()
        if frame is None:
            break
        try:
            if state.serial_transport is None:
                raise DaemonError("serial transport is not open")
            state.serial_transport.write(encode_litetune_wire_frame(frame))
            state.stats["frames_tx"] += 1
            await log_event(state, "send", frame.type_name, frame_log_payload(frame), frame_id=frame.frame_id)
        except Exception as exc:
            await log_event(state, "local", "SERIAL_WRITE_ERROR", {"error": str(exc), "frame_id": hex64(frame.frame_id)})
            pending = state.pending.get(frame.frame_id)
            if pending is not None and not pending.future.done():
                pending.future.set_exception(DaemonError(str(exc)))


async def frame_dispatch_loop(state: DaemonState) -> None:
    while True:
        wire = await state.rx_queue.get()
        if wire is None:
            break
        try:
            frame = decode_litetune_wire_frame(wire)
        except Exception as exc:
            state.stats["decode_errors"] += 1
            await log_event(state, "local", "FRAME_DECODE_ERROR", {"error": str(exc), "wire_hex": wire.hex()[:512]}, ok=False)
            continue
        state.stats["frames_rx"] += 1
        try:
            await dispatch_litetune_frame(state, frame)
        except Exception as exc:
            await log_event(state, "local", "FRAME_DISPATCH_ERROR", {"error": str(exc), "type": frame.type_name}, frame_id=frame.frame_id, ok=False)


def frame_log_payload(frame: RawFrame) -> dict[str, Any]:
    if frame.type_id == TYPE_IDS["DISCOVER"]:
        return {"host": "litetune-agent"}
    return {"payload_hex": frame.payload.hex()}


async def dispatch_litetune_frame(state: DaemonState, frame: RawFrame) -> None:
    match frame.type_name:
        case "REGISTER_BEGIN":
            await handle_register_begin(state, frame)
        case "REGISTER_LOG_LAYOUT":
            await handle_register_log_layout(state, frame)
        case "REGISTER_PARAM_DESC":
            await handle_register_param_desc(state, frame)
        case "REGISTER_CMD_DESC":
            await handle_register_cmd_desc(state, frame)
        case "REGISTER_END":
            await handle_register_end(state, frame)
        case "PARAM_REPORT":
            await handle_param_report(state, frame)
        case "CMD_RESPONSE":
            await handle_cmd_response(state, frame)
        case "STATUS":
            payload = parse_status(frame.payload)
            if state.state == "discovering":
                state.latest_discover_status = {**payload, "frame_id": hex64(frame.frame_id)}
            await log_event(state, "receive", "STATUS", payload, frame_id=frame.frame_id, status=payload["status"])
        case "LOG_TEXT":
            await log_event(state, "receive", "LOG_TEXT", parse_log_text(frame.payload), frame_id=frame.frame_id)
        case "LOG_REPORT":
            await handle_log_report(state, frame)
        case _:
            await log_event(state, "receive", frame.type_name, {"payload_hex": frame.payload.hex()}, frame_id=frame.frame_id)


async def handle_register_begin(state: DaemonState, frame: RawFrame) -> None:
    await fail_all_pending(state, "REGISTER_RESTARTED", "register cycle restarted")
    state.schema_ready.clear()
    state.schema_builder = SchemaBuilder(begin=parse_register_begin(frame.payload))
    await set_state(state, "discovering")
    await log_event(state, "receive", "REGISTER_BEGIN", state.schema_builder.begin, frame_id=frame.frame_id)


async def handle_register_log_layout(state: DaemonState, frame: RawFrame) -> None:
    builder = require_schema_builder(state)
    layout = parse_register_log_layout(frame.payload)
    builder.layouts[str(layout["id"])] = layout
    await log_event(state, "receive", "REGISTER_LOG_LAYOUT", layout, frame_id=frame.frame_id)


async def handle_register_param_desc(state: DaemonState, frame: RawFrame) -> None:
    builder = require_schema_builder(state)
    builder.params = parse_register_param_desc(frame.payload)
    await log_event(state, "receive", "REGISTER_PARAM_DESC", {"param_count": len(builder.params)}, frame_id=frame.frame_id)


async def handle_register_cmd_desc(state: DaemonState, frame: RawFrame) -> None:
    builder = require_schema_builder(state)
    builder.commands = parse_register_cmd_desc(frame.payload)
    await log_event(state, "receive", "REGISTER_CMD_DESC", {"cmd_count": len(builder.commands)}, frame_id=frame.frame_id)


async def handle_register_end(state: DaemonState, frame: RawFrame) -> None:
    builder = require_schema_builder(state)
    if frame.payload:
        raise ProtocolError("REGISTER_END payload must be empty")
    schema = build_schema_from_builder(state, builder)
    state.active_schema = schema
    state.schema_ready.set()
    builder.done.set()
    await set_state(state, "ready")
    await log_event(state, "receive", "REGISTER_END", {}, frame_id=frame.frame_id)
    await log_event(state, "local", "SCHEMA", schema_summary(schema), frame_id=frame.frame_id)


def require_schema_builder(state: DaemonState) -> SchemaBuilder:
    if state.schema_builder is None:
        raise ProtocolError("REGISTER record before REGISTER_BEGIN")
    return state.schema_builder


def build_schema_from_builder(state: DaemonState, builder: SchemaBuilder) -> dict[str, Any]:
    if builder.begin is None:
        raise ProtocolError("missing REGISTER_BEGIN")
    begin = builder.begin
    expected_layouts = int(begin.get("layout_count", 0))
    expected_params = int(begin.get("param_count", 0))
    expected_cmds = int(begin.get("cmd_count", 0))
    if len(builder.layouts) != expected_layouts:
        raise ProtocolError(f"layout count mismatch: expected {expected_layouts}, got {len(builder.layouts)}")
    if len(builder.params) != expected_params:
        raise ProtocolError(f"param count mismatch: expected {expected_params}, got {len(builder.params)}")
    if len(builder.commands) != expected_cmds:
        raise ProtocolError(f"command count mismatch: expected {expected_cmds}, got {len(builder.commands)}")
    mcu_max = int(begin["device"].get("mcu_max_decoded_frame", state.host_max_decoded_frame))
    schema = {
        "protocol": begin["protocol"],
        "ready": True,
        "device": begin["device"],
        "host": {"host_max_decoded_frame": state.host_max_decoded_frame, "peer_max_decoded_frame": min(state.host_max_decoded_frame, mcu_max)},
        "features": begin["features"],
        "layouts": builder.layouts,
        "params": builder.params,
        "commands": builder.commands,
    }
    schema["schema_digest"] = stable_digest(schema)
    return schema


def schema_summary(schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_digest": schema["schema_digest"],
        "device": schema["device"],
        "param_count": len(schema["params"]),
        "cmd_count": len(schema["commands"]),
        "layout_count": len(schema["layouts"]),
    }


async def handle_param_report(state: DaemonState, frame: RawFrame) -> None:
    payload = parse_param_report(frame.payload, state.active_schema)
    request_id = payload.pop("request_frame_id_int")
    await log_event(state, "receive", "PARAM_REPORT", payload, frame_id=frame.frame_id, request_frame_id=request_id, ok=payload["overall_status"] == "OK", status=payload["overall_status"])
    pending = state.pending.get(request_id)
    if pending is not None and pending.expected_type == "PARAM_REPORT" and not pending.future.done():
        pending.future.set_result((frame, {**payload, "request_frame_id_int": request_id}))


async def handle_cmd_response(state: DaemonState, frame: RawFrame) -> None:
    payload = parse_cmd_response(frame.payload)
    request_id = payload.pop("request_frame_id_int")
    await log_event(state, "receive", "CMD_RESPONSE", payload, frame_id=frame.frame_id, request_frame_id=request_id, ok=payload["status"] == "OK", status=payload["status"])
    pending = state.pending.get(request_id)
    if pending is not None and pending.expected_type == "CMD_RESPONSE" and not pending.future.done():
        pending.future.set_result((frame, {**payload, "request_frame_id_int": request_id}))


async def handle_log_report(state: DaemonState, frame: RawFrame) -> None:
    if should_drop_telemetry(state):
        state.stats["telemetry_dropped"] += 1
        return
    payload = parse_log_report(frame.payload, state.active_schema)
    state.stats["telemetry_logged"] += 1
    await log_event(state, "receive", "LOG_REPORT", payload, frame_id=frame.frame_id, ok=payload.get("decoded"))


def should_drop_telemetry(state: DaemonState) -> bool:
    mode = state.telemetry_log
    if mode == "off":
        return True
    if not mode.startswith("decimate:"):
        return False
    try:
        n = int(mode.split(":", 1)[1])
    except ValueError:
        return False
    total = state.stats["telemetry_logged"] + state.stats["telemetry_dropped"]
    return n > 1 and total % n != 0


async def send_request_wait_response(state: DaemonState, frame: RawFrame, expected_type: str, timeout_s: float) -> tuple[RawFrame, dict[str, Any]]:
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    state.pending[frame.frame_id] = PendingRequest(frame.frame_id, expected_type, fut, loop.time(), timeout_s)
    await state.tx_queue.put(frame)
    try:
        return await asyncio.wait_for(fut, timeout_s)
    except asyncio.TimeoutError as exc:
        raise TimeoutDaemonError(f"{frame.type_name} timed out", {"frame_id": hex64(frame.frame_id), "timeout_s": timeout_s}) from exc
    finally:
        state.pending.pop(frame.frame_id, None)


async def schema_discovery(state: DaemonState) -> dict[str, Any]:
    async with state.request_lock:
        state.stats["schema_refreshes"] += 1
        state.schema_ready.clear()
        state.schema_builder = None
        state.active_schema = None
        state.latest_discover_status = None
        await set_state(state, "discovering")
        frame = RawFrame(TYPE_IDS["DISCOVER"], state.allocate_frame_id(), build_discover_payload(state.host_max_decoded_frame, state.requested_features, state.response_timeout_ms, state.host_name))
        await log_event(state, "local", "DISCOVER", {"frame_id": hex64(frame.frame_id)})
        await state.tx_queue.put(frame)
        deadline = time.monotonic() + state.schema_timeout_s
        while time.monotonic() < deadline:
            builder = state.schema_builder
            if builder is not None and builder.done.is_set() and state.active_schema is not None:
                return state.active_schema
            await asyncio.sleep(0.02)
        await set_state(state, "error")
        state.schema_ready.clear()
        if state.latest_discover_status is not None:
            status = state.latest_discover_status.get("status", "UNKNOWN_ERROR")
            details = {"status": status, "timeout_s": state.schema_timeout_s, "latest_status": state.latest_discover_status}
            await log_event(state, "local", "SCHEMA_ERROR", details, ok=False, status=status)
            raise BusinessDaemonError(f"schema discovery failed with status {status}", details)
        await log_event(state, "local", "SCHEMA_ERROR", {"error": "schema discovery timed out"}, ok=False)
        raise TimeoutDaemonError("schema discovery timed out", {"timeout_s": state.schema_timeout_s})


async def fail_all_pending(state: DaemonState, code: str, message: str) -> None:
    for pending in state.pending.values():
        if not pending.future.done():
            pending.future.set_exception(DaemonError(message, {"code": code}))
    state.pending.clear()


def ensure_schema(state: DaemonState) -> dict[str, Any]:
    if state.active_schema is None or not state.schema_ready.is_set():
        raise NotReadyError("schema is not ready")
    return state.active_schema


def ensure_feature(schema: dict[str, Any], feature: str) -> None:
    enabled = schema.get("features", {}).get("enabled", [])
    if feature not in enabled:
        raise BusinessDaemonError(f"feature not enabled: {feature}", {"enabled": enabled})


def ensure_raw_fits(state: DaemonState, payload: bytes) -> None:
    schema = state.active_schema or {}
    peer_max = int(schema.get("host", {}).get("peer_max_decoded_frame") or state.host_max_decoded_frame)
    size = raw_frame_len(payload)
    if size > peer_max:
        raise FrameTooLargeError("LiteTune frame would exceed peer max decoded frame", {"raw_len": size, "peer_max_decoded_frame": peer_max})


def make_param_get_frame(state: DaemonState, ids: list[int] | None = None, all_params: bool = False) -> RawFrame:
    payload = build_param_get_payload(ids, all_params=all_params)
    ensure_raw_fits(state, payload)
    return RawFrame(TYPE_IDS["PARAM_GET"], state.allocate_frame_id(), payload)


def make_param_set_frame(state: DaemonState, items: list[dict[str, Any]]) -> RawFrame:
    payload = build_param_set_payload(items)
    ensure_raw_fits(state, payload)
    return RawFrame(TYPE_IDS["PARAM_SET"], state.allocate_frame_id(), payload)


def make_cmd_request_frame(state: DaemonState, cmd_id: int, user_payload: bytes) -> RawFrame:
    payload = build_cmd_request_payload(cmd_id, user_payload)
    ensure_raw_fits(state, payload)
    return RawFrame(TYPE_IDS["CMD_REQUEST"], state.allocate_frame_id(), payload)
