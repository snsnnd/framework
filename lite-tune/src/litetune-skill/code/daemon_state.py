#!/usr/bin/env python3
"""Shared LiteTune daemon state, errors and JSONL helpers."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from litetune_protocol import DEFAULT_REQUESTED_FEATURES, hex64

MAX_UDS_LINE_BYTES = 1024 * 1024


class DaemonError(Exception):
    code = "INTERNAL_ERROR"

    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class BadRequestError(DaemonError):
    code = "BAD_REQUEST"


class NotReadyError(DaemonError):
    code = "NOT_READY"


class NotFoundError(DaemonError):
    code = "NOT_FOUND"


class BusinessDaemonError(DaemonError):
    code = "BUSINESS_ERROR"


class TimeoutDaemonError(DaemonError):
    code = "TIMEOUT"


class FrameTooLargeError(DaemonError):
    code = "TOO_LARGE"


@dataclass
class PendingRequest:
    frame_id: int
    expected_type: str
    future: asyncio.Future
    created_at: float
    timeout_s: float
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class SchemaBuilder:
    begin: dict[str, Any] | None = None
    layouts: dict[str, dict[str, Any]] = field(default_factory=dict)
    params: dict[str, dict[str, Any]] = field(default_factory=dict)
    commands: dict[str, dict[str, Any]] = field(default_factory=dict)
    done: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass
class DaemonState:
    port: str
    baud: int
    socket_path: str
    log_path: str
    daemon_json_path: str
    runtime_dir: str
    host_max_decoded_frame: int = 2048
    requested_features: int = DEFAULT_REQUESTED_FEATURES
    response_timeout_ms: int = 1000
    host_name: str = "litetune-agent"
    schema_timeout_s: float = 5.0
    request_timeout_s: float = 2.0
    telemetry_log: str = "all"
    log_max_bytes: int = 0

    state: str = "starting"
    daemon_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    serial_transport: Any | None = None
    server: Any | None = None
    active_schema: dict[str, Any] | None = None
    schema_ready: asyncio.Event = field(default_factory=asyncio.Event)
    rx_queue: asyncio.Queue[Any] = field(default_factory=asyncio.Queue)
    tx_queue: asyncio.Queue[Any] = field(default_factory=asyncio.Queue)
    log_queue: asyncio.Queue[dict[str, Any] | None] = field(default_factory=asyncio.Queue)
    pending: dict[int, PendingRequest] = field(default_factory=dict)
    request_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    stopping: bool = False
    next_frame_id: int = 1
    log_seq: int = 0
    stats: dict[str, Any] = field(default_factory=lambda: {
        "frames_rx": 0,
        "frames_tx": 0,
        "decode_errors": 0,
        "uds_requests": 0,
        "schema_refreshes": 0,
        "telemetry_logged": 0,
        "telemetry_dropped": 0,
    })
    started_at: str = ""
    schema_builder: SchemaBuilder | None = None
    shutdown_event: asyncio.Event = field(default_factory=asyncio.Event)
    latest_discover_status: dict[str, Any] | None = None

    def allocate_frame_id(self) -> int:
        frame_id = self.next_frame_id & 0xFFFFFFFFFFFFFFFF
        if frame_id == 0:
            frame_id = 1
        self.next_frame_id = (frame_id + 1) & 0xFFFFFFFFFFFFFFFF
        if self.next_frame_id == 0:
            self.next_frame_id = 1
        return frame_id


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def json_response(request_id: Any, ok: bool, result: Any | None = None, error: dict[str, Any] | None = None) -> dict[str, Any]:
    response: dict[str, Any] = {"id": str(uuid.uuid4()), "op": "response", "request_id": request_id, "ok": ok}
    if ok:
        response["result"] = result or {}
    else:
        response["error"] = error or {"code": "INTERNAL_ERROR", "message": "unknown error"}
    return response


def response_error(exc: DaemonError) -> dict[str, Any]:
    err = {"code": exc.code, "message": exc.message}
    if exc.details is not None:
        err["details"] = exc.details
    return {"ok": False, "error": err}


def atomic_write_json(path: str, data: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


async def write_daemon_json(state: DaemonState) -> None:
    schema = state.active_schema or {}
    data = {
        "version": 1,
        "daemon_id": state.daemon_id,
        "state": state.state,
        "pid": os.getpid(),
        "port": state.port,
        "baud": state.baud,
        "socket_path": state.socket_path,
        "log_path": state.log_path,
        "started_at": state.started_at,
        "updated_at": utc_now(),
        "protocol": {"name": "LiteTune", "version": "0.5.0"},
        "device": schema.get("device", {}),
        "host": {
            "host_max_decoded_frame": state.host_max_decoded_frame,
            "peer_max_decoded_frame": schema.get("host", {}).get("peer_max_decoded_frame"),
        },
        "schema_digest": schema.get("schema_digest"),
    }
    await asyncio.to_thread(atomic_write_json, state.daemon_json_path, data)


async def log_event(
    state: DaemonState,
    direction: str,
    event_type: str,
    payload: Any | None = None,
    *,
    frame_id: int | None = None,
    request_frame_id: int | None = None,
    ok: bool | None = None,
    status: str | None = None,
    raw: dict[str, Any] | None = None,
) -> None:
    state.log_seq += 1
    event: dict[str, Any] = {
        "time": utc_now(),
        "seq": state.log_seq,
        "direction": direction,
        "type": event_type,
        "payload": payload if payload is not None else {},
    }
    if frame_id is not None:
        event["frame_id"] = hex64(frame_id)
    if request_frame_id is not None:
        event["request_frame_id"] = hex64(request_frame_id)
    if ok is not None:
        event["ok"] = ok
    if status is not None:
        event["status"] = status
    if raw is not None:
        event["raw"] = raw
    await state.log_queue.put(event)


async def log_writer_loop(state: DaemonState) -> None:
    os.makedirs(os.path.dirname(state.log_path), exist_ok=True)
    f = open(state.log_path, "a", buffering=1, encoding="utf-8")
    try:
        while True:
            event = await state.log_queue.get()
            if event is None:
                break
            f.write(json_dumps(event) + "\n")
            if state.log_max_bytes > 0 and f.tell() >= state.log_max_bytes:
                f.close()
                rotate_log(state.log_path)
                f = open(state.log_path, "a", buffering=1, encoding="utf-8")
    finally:
        f.close()


def rotate_log(path: str) -> None:
    rotated = f"{path}.{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    try:
        os.replace(path, rotated)
    except FileNotFoundError:
        pass


async def set_state(state: DaemonState, value: str) -> None:
    state.state = value
    await write_daemon_json(state)
