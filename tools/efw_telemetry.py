#!/usr/bin/env python3
"""EFW PID scope telemetry protocol utilities.

Frame format:
    0xAA 0x55 | msg_type:u8 | payload_len:u16-le | payload | crc16:u16-le
CRC16 is Modbus/IBM (poly 0xA001) over msg_type + payload_len + payload.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import struct
import time
from typing import Deque, Iterable

SOF = b"\xAA\x55"
TYPE_TELEMETRY = 0x01
TYPE_PARAM_SET = 0x02
TELEMETRY_STRUCT = struct.Struct("<BBIfffffffff")
PARAM_SET_STRUCT = struct.Struct("<BBfff")


@dataclass(frozen=True)
class TelemetrySample:
    device_id: int
    channel_id: int
    time_ms: int
    target: float
    feedback: float
    error: float
    output: float
    kp: float
    ki: float
    kd: float
    extra1: float = 0.0
    extra2: float = 0.0

    @property
    def key(self) -> tuple[int, int]:
        return self.device_id, self.channel_id


@dataclass(frozen=True)
class ParamSet:
    device_id: int
    channel_id: int
    kp: float
    ki: float
    kd: float


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def encode_frame(msg_type: int, payload: bytes) -> bytes:
    head = bytes([msg_type]) + struct.pack("<H", len(payload)) + payload
    return SOF + head + struct.pack("<H", crc16(head))


def encode_telemetry(sample: TelemetrySample) -> bytes:
    payload = TELEMETRY_STRUCT.pack(
        sample.device_id,
        sample.channel_id,
        sample.time_ms,
        sample.target,
        sample.feedback,
        sample.error,
        sample.output,
        sample.kp,
        sample.ki,
        sample.kd,
        sample.extra1,
        sample.extra2,
    )
    return encode_frame(TYPE_TELEMETRY, payload)


def encode_param_set(param: ParamSet) -> bytes:
    return encode_frame(TYPE_PARAM_SET, PARAM_SET_STRUCT.pack(param.device_id, param.channel_id, param.kp, param.ki, param.kd))


def decode_payload(msg_type: int, payload: bytes):
    if msg_type == TYPE_TELEMETRY:
        if len(payload) != TELEMETRY_STRUCT.size:
            raise ValueError(f"bad telemetry payload length: {len(payload)}")
        return TelemetrySample(*TELEMETRY_STRUCT.unpack(payload))
    if msg_type == TYPE_PARAM_SET:
        if len(payload) != PARAM_SET_STRUCT.size:
            raise ValueError(f"bad param-set payload length: {len(payload)}")
        return ParamSet(*PARAM_SET_STRUCT.unpack(payload))
    return msg_type, payload


class FrameParser:
    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[object]:
        self._buf.extend(data)
        frames: list[object] = []
        while True:
            sof_index = self._buf.find(SOF)
            if sof_index < 0:
                self._buf.clear()
                break
            if sof_index > 0:
                del self._buf[:sof_index]
            if len(self._buf) < 7:
                break
            msg_type = self._buf[2]
            payload_len = struct.unpack_from("<H", self._buf, 3)[0]
            total_len = 2 + 1 + 2 + payload_len + 2
            if len(self._buf) < total_len:
                break
            frame = bytes(self._buf[:total_len])
            del self._buf[:total_len]
            expected = struct.unpack_from("<H", frame, total_len - 2)[0]
            checked = crc16(frame[2:-2])
            if expected != checked:
                continue
            frames.append(decode_payload(msg_type, frame[5:-2]))
        return frames


class TelemetryBuffer:
    def __init__(self, maxlen: int = 2000) -> None:
        self.maxlen = maxlen
        self._channels: dict[tuple[int, int], Deque[TelemetrySample]] = {}

    def append(self, sample: TelemetrySample) -> None:
        self._channels.setdefault(sample.key, deque(maxlen=self.maxlen)).append(sample)

    def keys(self) -> list[tuple[int, int]]:
        return sorted(self._channels)

    def samples(self, key: tuple[int, int]) -> list[TelemetrySample]:
        return list(self._channels.get(key, ()))

    def latest(self, key: tuple[int, int]) -> TelemetrySample | None:
        channel = self._channels.get(key)
        if not channel:
            return None
        return channel[-1]


def analyze_step(samples: Iterable[TelemetrySample]) -> dict[str, float]:
    data = list(samples)
    if not data:
        return {"overshoot": 0.0, "steady_error": 0.0, "iae": 0.0, "oscillations": 0.0}
    target = data[-1].target
    if abs(target) < 1e-6:
        overshoot = 0.0
    else:
        peak = max(s.feedback for s in data)
        overshoot = max(0.0, (peak - target) / abs(target) * 100.0)
    steady_window = data[-min(50, len(data)):]
    steady_error = sum(abs(s.error) for s in steady_window) / len(steady_window)
    iae = 0.0
    last_t = data[0].time_ms
    for sample in data[1:]:
        dt = max(0.0, (sample.time_ms - last_t) / 1000.0)
        iae += abs(sample.error) * dt
        last_t = sample.time_ms
    oscillations = 0
    last_sign = 0
    for sample in data:
        sign = 1 if sample.error > 0 else (-1 if sample.error < 0 else 0)
        if sign and last_sign and sign != last_sign:
            oscillations += 1
        if sign:
            last_sign = sign
    return {
        "overshoot": overshoot,
        "steady_error": steady_error,
        "iae": iae,
        "oscillations": float(oscillations),
    }


def simulated_frames(device_id: int = 1, channel_id: int = 1, count: int = 100000):
    start = time.monotonic()
    feedback = 0.0
    kp, ki, kd = 18.0, 0.0, 2.5
    for idx in range(count):
        now = time.monotonic() - start
        target = 1.0 if now > 0.5 else 0.0
        feedback += (target - feedback) * 0.08
        noise = math.sin(idx * 0.17) * 0.015
        measured = feedback + noise
        error = target - measured
        output = kp * error
        sample = TelemetrySample(
            device_id=device_id,
            channel_id=channel_id,
            time_ms=int(now * 1000),
            target=target,
            feedback=measured,
            error=error,
            output=output,
            kp=kp,
            ki=ki,
            kd=kd,
            extra1=7.4 + math.sin(idx * 0.01) * 0.2,
            extra2=0.0,
        )
        yield encode_telemetry(sample)
