#!/usr/bin/env python3
"""EFW ground-station serial daemon entry point."""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys

try:
    import serial_asyncio
except ImportError:  # pragma: no cover - optional runtime dependency
    serial_asyncio = None

from .daemon_frames import LiteTuneSerialProtocol, fail_all_pending, frame_dispatch_loop, schema_discovery, serial_tx_loop
from .daemon_ops import run_uds_server
from .daemon_state import DaemonError, DaemonState, log_event, log_writer_loop, utc_now, write_daemon_json
from .profile import load_protocol_profile, requested_features_mask
from .protocol import apply_protocol_profile

EXIT_IO = 6


async def open_serial(state: DaemonState) -> None:
    if serial_asyncio is None:
        raise DaemonError("pyserial-asyncio is not installed", "install pyserial-asyncio")
    loop = asyncio.get_running_loop()
    await serial_asyncio.create_serial_connection(
        loop,
        lambda: LiteTuneSerialProtocol(state),
        state.port,
        baudrate=state.baud,
    )


async def run_daemon(args: argparse.Namespace) -> int:
    runtime = os.path.abspath(args.runtime)
    os.makedirs(runtime, exist_ok=True)
    profile = load_protocol_profile(args.profile)
    apply_protocol_profile(profile)
    state = DaemonState(
        port=args.port,
        baud=args.baud,
        socket_path=os.path.abspath(args.socket_path or os.path.join(runtime, "litetune.sock")),
        log_path=os.path.abspath(args.log_path or os.path.join(runtime, "litetune.log")),
        daemon_json_path=os.path.abspath(args.daemon_json or os.path.join(runtime, "daemon.json")),
        runtime_dir=runtime,
        host_max_decoded_frame=args.host_max_decoded_frame,
        requested_features=requested_features_mask(profile),
        response_timeout_ms=args.response_timeout_ms,
        host_name=args.host_name,
        schema_timeout_s=args.schema_timeout,
        request_timeout_s=args.request_timeout,
        telemetry_log=args.telemetry_log,
        log_max_bytes=args.log_max_bytes,
        rx_queue_size=args.rx_queue_size,
        tx_queue_size=args.tx_queue_size,
        log_queue_size=args.log_queue_size,
        protocol_profile=profile,
    )
    state.started_at = utc_now()
    log_task = asyncio.create_task(log_writer_loop(state))
    tx_task: asyncio.Task | None = None
    rx_task: asyncio.Task | None = None
    uds_task: asyncio.Task | None = None
    try:
        await write_daemon_json(state)
        await log_event(state, "local", "DAEMON_START", {"port": state.port, "baud": state.baud})
        await open_serial(state)
        tx_task = asyncio.create_task(serial_tx_loop(state))
        rx_task = asyncio.create_task(frame_dispatch_loop(state))
        uds_task = asyncio.create_task(run_uds_server(state))
        try:
            await schema_discovery(state)
        except Exception as exc:
            await log_event(state, "local", "SCHEMA_ERROR", {"error": str(exc)}, ok=False)
            state.state = "error"
            await write_daemon_json(state)
        install_signal_handlers(state)
        await state.shutdown_event.wait()
        return 0
    except Exception as exc:
        await log_event(state, "local", "DAEMON_ERROR", {"error": str(exc)}, ok=False)
        state.state = "error"
        await write_daemon_json(state)
        return EXIT_IO
    finally:
        await graceful_shutdown(state, log_task, tx_task, rx_task, uds_task)


def install_signal_handlers(state: DaemonState) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, state.shutdown_event.set)
        except (NotImplementedError, RuntimeError):
            pass


async def graceful_shutdown(
    state: DaemonState,
    log_task: asyncio.Task,
    tx_task: asyncio.Task | None,
    rx_task: asyncio.Task | None,
    uds_task: asyncio.Task | None,
) -> None:
    state.stopping = True
    state.state = "stopping"
    await fail_all_pending(state, "STOPPING", "daemon is stopping")
    if state.server is not None:
        state.server.close()
        await state.server.wait_closed()
    if uds_task is not None:
        uds_task.cancel()
        await asyncio.gather(uds_task, return_exceptions=True)
    await state.tx_queue.put(None)
    await state.rx_queue.put(None)
    for task in (tx_task, rx_task):
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
    if state.serial_transport is not None:
        state.serial_transport.close()
    await log_event(state, "local", "DAEMON_STOP", {})
    state.state = "stopped"
    await write_daemon_json(state)
    try:
        os.unlink(state.socket_path)
    except FileNotFoundError:
        pass
    await state.log_queue.put(None)
    await log_task


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="EFW ground-station serial daemon")
    default_runtime = os.path.abspath(os.path.join(os.getcwd(), ".efw_runtime", "groundstation"))
    parser.add_argument("--runtime", default=default_runtime)
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--socket-path")
    parser.add_argument("--log-path")
    parser.add_argument("--daemon-json")
    parser.add_argument("--host-max-decoded-frame", type=int, default=2048)
    parser.add_argument("--response-timeout-ms", type=int, default=1000)
    parser.add_argument("--schema-timeout", type=float, default=5.0)
    parser.add_argument("--request-timeout", type=float, default=2.0)
    parser.add_argument("--host-name", default="efw-groundstation")
    parser.add_argument("--profile", help="Protocol profile JSON path or EFW project descriptor")
    parser.add_argument("--log-max-bytes", type=int, default=0)
    parser.add_argument("--telemetry-log", default="all")
    parser.add_argument("--rx-queue-size", type=int, default=256)
    parser.add_argument("--tx-queue-size", type=int, default=64)
    parser.add_argument("--log-queue-size", type=int, default=1024)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(run_daemon(args))


if __name__ == "__main__":
    sys.exit(main())
