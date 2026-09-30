#!/usr/bin/env python3
"""UDS request handling and high-level operations for LiteTune daemon."""

from __future__ import annotations

import asyncio
import json
import os

from typing import Any

from daemon_frames import (
    ensure_feature,
    ensure_schema,
    make_cmd_request_frame,
    make_param_get_frame,
    make_param_set_frame,
    schema_discovery,
    send_request_wait_response,
)
from daemon_state import (
    BadRequestError,
    BusinessDaemonError,
    DaemonError,
    DaemonState,
    FrameTooLargeError,
    NotFoundError,
    json_dumps,
    json_response,
    log_event,
    response_error,
)
from litetune_protocol import ProtocolError


async def run_uds_server(state: DaemonState) -> None:
    try:
        os.unlink(state.socket_path)
    except FileNotFoundError:
        pass
    os.makedirs(os.path.dirname(state.socket_path), exist_ok=True)
    state.server = await asyncio.start_unix_server(lambda r, w: handle_uds_client(state, r, w), path=state.socket_path, limit=1024 * 1024)
    async with state.server:
        await state.server.serve_forever()


async def handle_uds_client(state: DaemonState, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    request: dict[str, Any] | None = None
    try:
        raw = await reader.readline()
        if not raw:
            raise BadRequestError("empty request")
        if len(raw) > 1024 * 1024:
            raise BadRequestError("request too large")
        if not raw.endswith(b"\n"):
            raise BadRequestError("request must be newline terminated")
        request = decode_request(raw)
        state.stats["uds_requests"] += 1
        await log_event(state, "local", "UDS_REQUEST", request)
        result = await dispatch_uds_request(state, request)
        response = json_response(request.get("id"), True, result)
    except DaemonError as exc:
        response = json_response(request.get("id") if request else None, False, error=response_error(exc)["error"])
    except Exception as exc:
        response = json_response(request.get("id") if request else None, False, error={"code": "INTERNAL_ERROR", "message": str(exc)})
    await log_event(state, "local", "UDS_RESPONSE", response)
    writer.write((json_dumps(response) + "\n").encode("utf-8"))
    try:
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


def decode_request(raw: bytes) -> dict[str, Any]:
    try:
        request = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BadRequestError("request is not valid UTF-8 JSON", str(exc)) from exc
    if not isinstance(request, dict):
        raise BadRequestError("request must be a JSON object")
    return request


async def dispatch_uds_request(state: DaemonState, request: dict[str, Any]) -> dict[str, Any]:
    op = request.get("op")
    params = request.get("params") if isinstance(request.get("params"), dict) else request
    match op:
        case "daemon.status" | "status":
            return daemon_status(state)
        case "daemon.stats" | "stats":
            return {"stats": state.stats}
        case "daemon.stop" | "stop":
            asyncio.create_task(shutdown_soon(state))
            return {"stopping": True, "daemon_id": state.daemon_id}
        case "schema.get" | "schema":
            schema = await schema_discovery(state) if params.get("refresh") else state.active_schema or {"ready": False}
            return {"schema": schema}
        case "schema.refresh":
            return {"schema": await schema_discovery(state)}
        case "param.list":
            return {"params": ensure_schema(state).get("params", {})}
        case "param.get":
            return await op_param_get(state, params)
        case "param.set":
            return await op_param_set(state, params)
        case "cmd.run":
            return await op_cmd_run(state, params)
        case "log.tail":
            return await op_log_tail(state, params)
        case "port_list" | "port-list":
            return await op_port_list(state)
        case _:
            raise BadRequestError("unknown op", {"op": op})


def daemon_status(state: DaemonState) -> dict[str, Any]:
    return {
        "daemon_id": state.daemon_id,
        "state": state.state,
        "pid": os.getpid(),
        "port": state.port,
        "baud": state.baud,
        "socket_path": state.socket_path,
        "log_path": state.log_path,
        "schema_ready": state.schema_ready.is_set(),
        "schema_digest": (state.active_schema or {}).get("schema_digest"),
        "stats": state.stats,
    }


async def shutdown_soon(state: DaemonState) -> None:
    await asyncio.sleep(0.05)
    state.shutdown_event.set()


async def op_param_get(state: DaemonState, params: dict[str, Any]) -> dict[str, Any]:
    async with state.request_lock:
        schema = ensure_schema(state)
        ensure_feature(schema, "PARAM_GET")
        all_params = bool(params.get("all"))
        names = names_from_params(params)
        if all_params:
            frame = make_param_get_frame(state, all_params=True)
            requested = list(schema.get("params", {}))
        else:
            if not names:
                raise BadRequestError("param.get requires names or all=true")
            missing = [name for name in names if name not in schema.get("params", {})]
            if missing:
                raise NotFoundError("parameter not registered", {"missing": missing})
            frame = make_param_get_frame(state, [int(schema["params"][name]["id"]) for name in names])
            requested = names
        _raw, report = await send_request_wait_response(state, frame, "PARAM_REPORT", timeout_value(params, state.request_timeout_s))
        ensure_param_report_ok(report)
        return {"params": report_items_as_param_map(report), "report": report, "requested": requested}


def names_from_params(params: dict[str, Any]) -> list[str]:
    names = params.get("names")
    if names is None and params.get("name"):
        names = [params["name"]]
    if not isinstance(names, list):
        return []
    return [str(name) for name in names]


async def op_param_set(state: DaemonState, params: dict[str, Any]) -> dict[str, Any]:
    async with state.request_lock:
        schema = ensure_schema(state)
        ensure_feature(schema, "PARAM_SET")
        items = normalize_param_set_items(params)
        missing = [item["name"] for item in items if item["name"] not in schema.get("params", {})]
        if missing:
            raise NotFoundError("parameter not registered", {"missing": missing})
        encoded_items = []
        for item in items:
            desc = schema["params"][item["name"]]
            encoded_items.append({"id": desc["id"], "type": desc["type"], "value": item["value"]})
        try:
            frame = make_param_set_frame(state, encoded_items)
        except (ProtocolError, ValueError, TypeError, OverflowError, FrameTooLargeError) as exc:
            raise BadRequestError("param.set value encoding failed", str(exc)) from exc
        _raw, report = await send_request_wait_response(state, frame, "PARAM_REPORT", timeout_value(params, state.request_timeout_s))
        ensure_param_report_ok(report)
        return {"params": report_items_as_param_map(report), "report": report}


def normalize_param_set_items(params: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(params.get("items"), list):
        return [{"name": str(item["name"]), "value": item["value"]} for item in params["items"]]
    if isinstance(params.get("values"), dict):
        return [{"name": str(name), "value": value} for name, value in params["values"].items()]
    if "name" in params and "value" in params:
        return [{"name": str(params["name"]), "value": params["value"]}]
    raise BadRequestError("param.set requires name/value, values object, or items list")


def report_items_as_param_map(report: dict[str, Any]) -> dict[str, Any]:
    return {
        item["name"]: {
            "id": item["id"],
            "type": item["type"],
            "unit": item.get("unit", ""),
            "value": item.get("value"),
            "status": item.get("item_status"),
        }
        for item in report.get("items", [])
    }


def ensure_param_report_ok(report: dict[str, Any]) -> None:
    status = report.get("overall_status")
    if status != "OK":
        raise BusinessDaemonError("PARAM_REPORT overall_status is not OK", {"status": status, "report": report})


def ensure_cmd_response_ok(response: dict[str, Any]) -> None:
    status = response.get("status")
    if status != "OK":
        raise BusinessDaemonError("CMD_RESPONSE status is not OK", {"status": status, "response": response})


async def op_cmd_run(state: DaemonState, params: dict[str, Any]) -> dict[str, Any]:
    async with state.request_lock:
        schema = ensure_schema(state)
        ensure_feature(schema, "CMD")
        name = params.get("name")
        if not name:
            raise BadRequestError("cmd.run requires name")
        commands = schema.get("commands", {})
        if name not in commands:
            raise NotFoundError("command not registered", {"name": name})
        desc = commands[name]
        if "HOST_TO_MCU" not in desc.get("flags", []):
            raise BusinessDaemonError("command does not allow HOST_TO_MCU", {"name": name, "flags": desc.get("flags", [])})
        try:
            user_payload = bytes.fromhex(params.get("payload_hex", ""))
        except ValueError as exc:
            raise BadRequestError("payload_hex is invalid", str(exc)) from exc
        try:
            frame = make_cmd_request_frame(state, int(desc["id"]), user_payload)
        except (ProtocolError, ValueError, TypeError, OverflowError, FrameTooLargeError) as exc:
            raise BadRequestError("cmd.run request encoding failed", str(exc)) from exc
        _raw, response = await send_request_wait_response(state, frame, "CMD_RESPONSE", timeout_value(params, state.request_timeout_s))
        ensure_cmd_response_ok(response)
        if int(response["cmd_id"]) != int(desc["id"]):
            raise BadRequestError("CMD_RESPONSE cmd_id mismatch", response)
        return {"cmd": {"name": name, "id": desc["id"], "status": response["status"], "payload_hex": response["payload_hex"]}}


async def op_log_tail(state: DaemonState, params: dict[str, Any]) -> dict[str, Any]:
    num = int(params.get("num") or params.get("lines") or 10)
    event_type = params.get("type") or params.get("filter")
    return {"log_path": state.log_path, "events": await asyncio.to_thread(read_log_tail, state.log_path, num, event_type)}


def read_log_tail(path: str, num: int, event_type: str | None) -> list[dict[str, Any]]:
    if num < 0:
        raise BadRequestError("num/lines must be non-negative")
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_lines = f.readlines()
    except FileNotFoundError:
        return []
    events = []
    for line in raw_lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event_type and event.get("type") != event_type and event_type not in line:
            continue
        events.append(event)
    return events[-num:] if num else []


async def op_port_list(state: DaemonState) -> dict[str, Any]:
    return {"ports": await asyncio.to_thread(list_serial_ports), "current": state.port}


def list_serial_ports() -> list[dict[str, Any]]:
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    return [{"device": p.device, "description": p.description, "hwid": p.hwid} for p in list_ports.comports()]


def timeout_value(params: dict[str, Any], default: float) -> float:
    try:
        return float(params.get("timeout_s") or params.get("timeout") or default)
    except (TypeError, ValueError):
        raise BadRequestError("timeout must be numeric")
