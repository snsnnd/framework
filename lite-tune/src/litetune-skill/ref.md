# LiteTune CLI Reference

Complete reference for every `lt.py` command, argument, response shape, and error code.
Read this file when you need exact argument names, response field layouts, or edge-case
behavior that the main SKILL.md doesn't cover.

---

## Table of Contents

1. [Global options](#1-global-options)
2. [port-list](#2-port-list)
3. [daemon start](#3-daemon-start)
4. [daemon status](#4-daemon-status)
5. [daemon stop](#5-daemon-stop)
6. [daemon restart](#6-daemon-restart)
7. [schema](#7-schema)
8. [param list](#8-param-list)
9. [param get](#9-param-get)
10. [param set](#10-param-set)
11. [cmd](#11-cmd)
12. [log](#12-log)
13. [Exit codes](#13-exit-codes)
14. [Error codes](#14-error-codes)
15. [Value types](#15-value-types)
16. [Environment variables](#16-environment-variables)
17. [Port resolution order](#17-port-resolution-order)

---

## 1. Global options

These flags are accepted by **every** subcommand.

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--runtime` | string | `src/litetune-skill/runtime/` (relative to `code/`) | Path to the runtime directory. Daemon stores `litetune.sock`, `litetune.log`, `daemon.json`, and `daemon.stdout.log` here. |
| `--timeout` | float | `5.0` | UDS (Unix Domain Socket) request timeout in seconds. Must be positive. Applies to the CLI↔daemon round trip, not the MCU response time. |
| `--pretty` | flag | off | Indent JSON output. For human debugging only; agents should omit it. |

---

## 2. port-list

List serial ports detected on the host system. Does **not** require a running daemon.

```
lt.py port-list
```

**Arguments:** global options only.

**Response:**

```json
{
  "ok": true,
  "ports": [
    {
      "device": "/dev/ttyUSB0",
      "description": "USB Serial Device",
      "hwid": "USB VID:PID=1A86:7523"
    }
  ]
}
```

If `pyserial` is not installed:

```json
{
  "ok": true,
  "ports": [],
  "warning": "pyserial is not installed"
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `ports` | array | One entry per detected serial port. May be empty. |
| `ports[].device` | string | OS device path (e.g. `/dev/ttyUSB0`, `COM3`). Use this as `--port` for daemon start. |
| `ports[].description` | string | Human-readable port description from the driver. |
| `ports[].hwid` | string | Hardware ID string (vendor/product IDs, serial number). |
| `warning` | string? | Present only when pyserial is missing. |

---

## 3. daemon start

Launch the background daemon process. Idempotent: if the daemon is already running and
connectable, returns success without launching a second instance.

```
lt.py daemon start --port <PORT> [options]
```

**Arguments:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--port` | string | *(see [Port resolution order](#17-port-resolution-order))* | Serial port device path. Required unless resolvable from `daemon.json` or `LITETUNE_PORT`. |
| `--baud` | int | `115200` | Serial baud rate. Must match the MCU firmware configuration. |
| `--wait` | float | `5.0` | Max seconds to wait for the daemon to become connectable after launch. Must be positive. |
| `--daemon-stdout` | string | `<runtime>/daemon.stdout.log` | File path for daemon process stdout/stderr. |
| `--daemon-log` | string | *(alias for `--daemon-stdout`)* | Same as `--daemon-stdout`. |
| `--daemon-arg` | string | *(repeatable)* | Extra arguments passed verbatim to `daemon.py`. Can be specified multiple times. |
| `--log-max-bytes` | int | `0` | Rotate the NDJSON log file when it exceeds this byte size. `0` = never rotate. |
| `--telemetry-log` | string | `all` | Telemetry logging policy: `all` (log every report), `off` (drop all), or `decimate:N` (keep every Nth). |
| `--host-max-decoded-frame` | int | `2048` | Maximum decoded frame size (bytes) the host is willing to accept. Negotiated with MCU during discovery. |

**Response (fresh start):**

```json
{
  "ok": true,
  "started": true,
  "pid": 12345,
  "stdout": "/abs/path/to/daemon.stdout.log",
  "status": { "...daemon status payload..." }
}
```

**Response (already running):**

```json
{
  "ok": true,
  "started": false,
  "reason": "already_running",
  "status": { "...daemon status payload..." }
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `started` | bool | `true` = new daemon launched; `false` = one was already running. |
| `reason` | string? | `"already_running"` when `started` is `false`. |
| `pid` | int? | PID of the newly launched daemon process. Only present when `started` is `true`. |
| `stdout` | string? | Absolute path to the daemon stdout log. Only present when `started` is `true`. |
| `status` | object | Full daemon status payload (same shape as `daemon status` output). |

**Possible errors:**

| Code | When |
|------|------|
| `INVALID_ARGS` | `--port` not provided and can't be resolved |
| `LOCAL_IO_ERROR` | `daemon.py` not found, can't open stdout file, can't launch process, daemon exited during startup |
| `TIMEOUT` | Daemon didn't become connectable within `--wait` seconds |
| `DAEMON_CONFIG_MISMATCH` | Existing daemon is running with different `--port`/`--baud` |

---

## 4. daemon status

Query daemon health. Does **not** fail if the daemon is unreachable; reports the state
it can determine from metadata and connectivity probing.

```
lt.py daemon status [--port PORT] [--baud BAUD]
```

**Arguments:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--port` | string | *(none)* | If specified, asserts the running daemon's port matches. Raises `DAEMON_CONFIG_MISMATCH` on mismatch. |
| `--baud` | int | *(none)* | If specified, asserts the running daemon's baud matches. |

**Response:**

```json
{
  "ok": true,
  "runtime": "/abs/path/to/runtime",
  "daemon_json_path": "/abs/path/to/runtime/daemon.json",
  "daemon_json_exists": true,
  "socket_path": "/abs/path/to/runtime/litetune.sock",
  "socket_exists": true,
  "pid": 12345,
  "pid_alive": true,
  "connectable": true,
  "daemon_id_matches": true,
  "metadata": { "...daemon.json contents..." },
  "daemon": {
    "daemon_id": "uuid",
    "state": "ready",
    "pid": 12345,
    "port": "/dev/ttyUSB0",
    "baud": 115200,
    "socket_path": "/abs/path",
    "log_path": "/abs/path",
    "schema_ready": true,
    "schema_digest": "sha256:...",
    "stats": {
      "frames_rx": 42,
      "frames_tx": 10,
      "decode_errors": 0,
      "uds_requests": 5,
      "schema_refreshes": 1,
      "telemetry_logged": 30,
      "telemetry_dropped": 0
    }
  }
}
```

**Key fields:**

| Field | Type | Description |
|-------|------|-------------|
| `connectable` | bool | Whether the CLI can talk to the daemon over UDS right now. This is the primary health check. |
| `pid_alive` | bool \| null | OS-level check whether the PID is still running. `null` if PID unknown. |
| `daemon_json_exists` | bool | Whether `daemon.json` exists in the runtime dir. |
| `daemon_id_matches` | bool | Whether the daemon's self-reported id matches daemon.json. `false` ⇒ stale metadata. |
| `daemon.state` | string | Daemon state machine: `"starting"`, `"discovering"`, `"ready"`, `"error"`, `"stopping"`, `"stopped"`. |
| `daemon.schema_ready` | bool | Whether schema discovery completed successfully. |
| `daemon.stats` | object | Cumulative counters since daemon start. |
| `metadata` | object | Raw contents of `daemon.json` on disk. |

If the daemon is unreachable, `ok` is `false`, `connectable` is `false`, and `error` contains the reason.

---

## 5. daemon stop

Gracefully stop the daemon.

```
lt.py daemon stop [--force] [--wait SECS]
```

**Arguments:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--port` | string | *(none)* | Assert port match before stopping. |
| `--baud` | int | *(none)* | Assert baud match before stopping. |
| `--force` | flag | off | If the daemon is not connectable via UDS, fall back to sending SIGTERM to the PID from `daemon.json`. |
| `--wait` | float | `5.0` | Max seconds to wait for PID to exit after SIGTERM (only applies in `--force` mode). Must be positive. |

**Response (normal stop via UDS):**

```json
{
  "ok": true,
  "stopped": true,
  "via": "uds",
  "daemon": { "stopping": true, "daemon_id": "uuid" }
}
```

**Response (force stop via SIGTERM):**

```json
{
  "ok": true,
  "stopped": true,
  "via": "signal",
  "pid": 12345
}
```

**Response (force mode, daemon already dead):**

```json
{
  "ok": true,
  "stopped": false,
  "via": "metadata",
  "reason": "not_running",
  "connect_error": { "...error details..." }
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `stopped` | bool | `true` = daemon was stopped; `false` = was already dead. |
| `via` | string | `"uds"` (clean shutdown), `"signal"` (SIGTERM), `"metadata"` (already dead). |

**Possible errors:**

| Code | When |
|------|------|
| `DAEMON_NOT_RUNNING` | Daemon unreachable and `--force` not set |
| `TIMEOUT` | `--force` was set, SIGTERM sent, but PID didn't exit within `--wait` |
| `LOCAL_IO_ERROR` | SIGTERM failed (permission denied, etc.) |

---

## 6. daemon restart

Stop then start the daemon. Equivalent to `daemon stop` + 200 ms pause + `daemon start`.

```
lt.py daemon restart --port <PORT> [--force] [other start options]
```

**Arguments:** combines all arguments from [daemon stop](#5-daemon-stop) and [daemon start](#3-daemon-start). The `--force` flag applies to the stop phase.

**Response:**

```json
{
  "ok": true,
  "stop": { "...daemon stop response..." },
  "start": { "...daemon start response..." }
}
```

---

## 7. schema

Retrieve the MCU schema discovered at daemon startup. The schema describes every parameter,
command, and telemetry log layout the MCU exposes.

```
lt.py schema [--refresh]
```

**Arguments:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--refresh` | flag | off | Force a new DISCOVER exchange with the MCU and rebuild the schema from scratch. Use after a firmware update. |

**Response:**

```json
{
  "ok": true,
  "schema": {
    "ready": true,
    "protocol": { "name": "LiteTune", "version": "0.5.0" },
    "device": { "name": "my-mcu-board", "mcu_max_decoded_frame": 1024 },
    "host": { "host_max_decoded_frame": 2048, "peer_max_decoded_frame": 1024 },
    "features": { "mask": "0x0000001F", "enabled": ["LOG_PACKED", "PARAM_GET", "PARAM_SET", "CMD", "LOG_TEXT"] },
    "schema_digest": "sha256:abcdef...",
    "params": {
      "motor_speed": { "id": 0, "type": "u16", "unit": "rpm" },
      "pid_kp":      { "id": 1, "type": "f32", "unit": "" }
    },
    "commands": {
      "save_config":    { "id": 0, "flags": ["HOST_TO_MCU"], "flags_mask": "0x01" },
      "factory_reset":  { "id": 1, "flags": ["HOST_TO_MCU"], "flags_mask": "0x01" }
    },
    "layouts": {
      "0": {
        "id": 0,
        "default_period_ms": 100,
        "fields": [
          { "id": 0, "type": "f32", "unit": "rpm", "name": "speed" },
          { "id": 1, "type": "f32", "unit": "A",   "name": "current" }
        ]
      }
    }
  }
}
```

**Key schema fields:**

| Path | Type | Description |
|------|------|-------------|
| `schema.ready` | bool | `true` once discovery is complete. |
| `schema.device.name` | string | MCU firmware's self-reported device name. |
| `schema.device.mcu_max_decoded_frame` | int | Max decoded frame the MCU can handle (bytes). |
| `schema.host.peer_max_decoded_frame` | int | Negotiated max = min(host, MCU). Frames exceeding this are rejected before sending. |
| `schema.features.enabled` | string[] | Features the MCU supports: `LOG_PACKED`, `PARAM_GET`, `PARAM_SET`, `CMD`, `LOG_TEXT`. |
| `schema.params` | object | Map of parameter name → `{id, type, unit}`. `type` is a [value type](#15-value-types). |
| `schema.commands` | object | Map of command name → `{id, flags, flags_mask}`. Only commands with `HOST_TO_MCU` in `flags` can be invoked from `cmd`. |
| `schema.layouts` | object | Map of layout id (string) → telemetry layout definition. Each layout has `fields[]` with `{id, type, unit, name}`. |
| `schema.schema_digest` | string | `sha256:...` digest of the full schema. Changes when schema changes. |

If schema is not yet ready (discovery in progress): `{"ok": true, "schema": {"ready": false}}`.

---

## 8. param list

List parameter names and their types from the schema. This is a schema-only operation — it
does **not** read values from the MCU.

```
lt.py param list
```

**Arguments:** global options only.

**Response:**

```json
{
  "ok": true,
  "params": {
    "motor_speed": { "id": 0, "type": "u16", "unit": "rpm" },
    "pid_kp":      { "id": 1, "type": "f32", "unit": "" },
    "enabled":     { "id": 2, "type": "bool", "unit": "" }
  }
}
```

Same shape as `schema.params`. The names returned here are exactly the names you pass
to `param get` and `param set`.

**Possible errors:**

| Code | When |
|------|------|
| `NOT_READY` | Schema discovery not complete |
| `DAEMON_NOT_RUNNING` | Daemon not connectable |

---

## 9. param get

Read parameter values from the MCU. This sends a PARAM_GET frame over serial and waits
for a PARAM_REPORT response.

```
lt.py param get <name> [<name> ...]
lt.py param get --all
```

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `names` | positional, 0+ | One or more parameter names to read. |
| `--all` | flag | Read every parameter the MCU exposes. |

At least one name **or** `--all` is required.

**Response:**

```json
{
  "ok": true,
  "params": {
    "motor_speed": { "id": 0, "type": "u16", "unit": "rpm", "value": 1200, "status": "OK" },
    "pid_kp":      { "id": 1, "type": "f32", "unit": "",    "value": 1.5,  "status": "OK" }
  },
  "report": {
    "request_frame_id": "0x0000000000000003",
    "report_kind": "RESPONSE_TO_GET",
    "overall_status": "OK",
    "items": [ "...raw items..." ]
  },
  "requested": ["motor_speed", "pid_kp"]
}
```

**Key fields:**

| Field | Type | Description |
|-------|------|-------------|
| `params` | object | Map of name → `{id, type, unit, value, status}`. The `value` field is the decoded value from the MCU. |
| `params[].value` | varies | Decoded according to type. See [Value types](#15-value-types). |
| `params[].status` | string | Per-item status: `"OK"`, `"NOT_FOUND"`, `"TYPE_MISMATCH"`, etc. |
| `report.overall_status` | string | `"OK"` if all items succeeded. |
| `report.report_kind` | string | `"RESPONSE_TO_GET"` for get operations. |
| `requested` | string[] | The parameter names that were requested. |

**Possible errors:**

| Code | When |
|------|------|
| `INVALID_ARGS` | No names and `--all` not set |
| `NOT_FOUND` | One or more names not in schema |
| `NOT_READY` | Schema not ready |
| `TIMEOUT` | MCU didn't respond within deadline |
| `MCU_ERROR` | `overall_status` is not `"OK"` |

---

## 10. param set

Write parameter values to the MCU. Sends a PARAM_SET frame and waits for confirmation.

```
lt.py param set "NAME=VALUE[,NAME=VALUE,...]" [--command-timeout SECS]
```

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `assignments` | positional, required | Comma-separated `NAME=VALUE` pairs. Quoted as a single shell argument. |
| `--command-timeout` | float | MCU-side timeout for the set operation (sent to daemon, forwarded as `timeout_s`). |

**Value parsing rules:**

Values are parsed with `json.loads()` first. If that fails, the raw string is used.

| Input | Parsed as | Notes |
|-------|-----------|-------|
| `1200` | int `1200` | |
| `1.5` | float `1.5` | |
| `true` | bool `true` | Also: `false` |
| `"hello"` | string `"hello"` | With the JSON quotes |
| `hello` | string `"hello"` | JSON parse fails → raw string |
| `0xFF` | string `"0xFF"` | JSON parse fails → raw string. For hex ints, MCU type must be int. |

The parameter's declared type in the schema determines how the value is encoded on the wire.
Type mismatch (e.g. sending a string to a `u16` parameter) causes an error.

**Response:**

```json
{
  "ok": true,
  "params": {
    "pid_kp": { "id": 1, "type": "f32", "unit": "", "value": 1.5, "status": "OK" }
  },
  "report": {
    "request_frame_id": "0x0000000000000005",
    "report_kind": "RESPONSE_TO_SET",
    "overall_status": "OK",
    "items": [ "...raw items..." ]
  }
}
```

The `params[].value` is the **readback** from the MCU — the actual stored value. If the
MCU clamped the value to a valid range, the readback will differ from what you sent.

**Possible errors:**

| Code | When |
|------|------|
| `INVALID_ARGS` | Malformed assignment string (missing `=`, empty name, empty item) |
| `NOT_FOUND` | Parameter name not in schema |
| `NOT_READY` | Schema not ready |
| `BAD_REQUEST` | Value encoding failed (type mismatch, out of range) |
| `TIMEOUT` | MCU didn't respond |
| `MCU_ERROR` | `overall_status` is not `"OK"` |
| `TOO_LARGE` | Encoded frame exceeds `peer_max_decoded_frame` |

---

## 11. cmd

Execute a named command on the MCU.

```
lt.py cmd <name> [--command-timeout SECS]
```

**Arguments:**

| Argument | Type | Description |
|----------|------|-------------|
| `name` | positional, required | Command name as registered in the schema. |
| `--command-timeout` | float | MCU-side timeout (sent to daemon as `timeout_s`). |

Only commands with the `HOST_TO_MCU` flag in their schema entry can be invoked.

**Response:**

```json
{
  "ok": true,
  "cmd": {
    "name": "save_config",
    "id": 0,
    "status": "OK",
    "payload_hex": ""
  }
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `cmd.name` | string | Command name (echoed). |
| `cmd.id` | int | Command ID from the schema. |
| `cmd.status` | string | MCU response status: `"OK"`, `"EXEC_ERROR"`, `"BUSY"`, `"DENIED"`, etc. |
| `cmd.payload_hex` | string | Any response payload from the MCU, hex-encoded. Empty string if none. |

**Possible errors:**

| Code | When |
|------|------|
| `NOT_FOUND` | Command name not in schema |
| `NOT_READY` | Schema not ready |
| `MCU_ERROR` | Command status is not `"OK"` (daemon raises `BusinessError`) |
| `MCU_ERROR` | Command doesn't have `HOST_TO_MCU` flag |
| `TIMEOUT` | MCU didn't respond |
| `BAD_REQUEST` | `payload_hex` (if sent via UDS directly) is invalid hex |
| `TOO_LARGE` | Frame exceeds peer max |

---

## 12. log

View daemon event log. The log is an NDJSON file (one JSON object per line) recording
serial frames, UDS requests, errors, and telemetry.

### 12.1 Tail (default)

```
lt.py log [--num N] [--type TYPE]
```

**Arguments:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--num`, `--lines`, `--tail`, `-n` | int | `10` | Number of recent events to return. Must be non-negative. `0` returns empty. |
| `--type`, `--filter` | string | *(none)* | Filter events by type. Matches the `type` field in log entries (e.g. `PARAM_REPORT`, `SERIAL_OPEN`, `UDS_REQUEST`). Also matches as substring in the raw line. |

**Response:**

```json
{
  "ok": true,
  "log_path": "/abs/path/to/litetune.log",
  "events": [
    {
      "time": "2024-06-20T12:00:00.123Z",
      "seq": 42,
      "direction": "receive",
      "type": "PARAM_REPORT",
      "payload": { "..." },
      "frame_id": "0x0000000000000003",
      "ok": true,
      "status": "OK"
    }
  ]
}
```

**Log event fields:**

| Field | Type | Description |
|-------|------|-------------|
| `time` | string | ISO 8601 UTC timestamp with milliseconds. |
| `seq` | int | Monotonic sequence number within the daemon session. |
| `direction` | string | `"send"` (host→MCU), `"receive"` (MCU→host), `"local"` (internal daemon event). |
| `type` | string | Event type. See [Log event types](#log-event-types) below. |
| `payload` | object | Event-specific data. |
| `frame_id` | string? | Hex frame ID (e.g. `"0x0000000000000003"`). Present for serial frame events. |
| `request_frame_id` | string? | Frame ID of the request this is responding to. Present on response frames. |
| `ok` | bool? | Whether the event represents a success. |
| `status` | string? | Status code string when applicable. |

#### Log event types

| Type | Direction | Description |
|------|-----------|-------------|
| `DAEMON_START` | local | Daemon started |
| `DAEMON_STOP` | local | Daemon shutting down |
| `DAEMON_ERROR` | local | Fatal daemon error |
| `SERIAL_OPEN` | local | Serial port opened |
| `SERIAL_CLOSED` | local | Serial connection lost |
| `SERIAL_WRITE_ERROR` | local | Failed to write to serial |
| `DISCOVER` | local | Sent DISCOVER frame |
| `SCHEMA` | local | Schema discovery completed (summary) |
| `SCHEMA_ERROR` | local | Schema discovery failed |
| `REGISTER_BEGIN` | receive | MCU began schema registration |
| `REGISTER_LOG_LAYOUT` | receive | MCU sent a log layout descriptor |
| `REGISTER_PARAM_DESC` | receive | MCU sent parameter descriptors |
| `REGISTER_CMD_DESC` | receive | MCU sent command descriptors |
| `REGISTER_END` | receive | MCU finished schema registration |
| `PARAM_REPORT` | receive | MCU responded to param get/set |
| `CMD_RESPONSE` | receive | MCU responded to a command |
| `STATUS` | receive | MCU sent a status frame |
| `LOG_TEXT` | receive | MCU sent a text log message |
| `LOG_REPORT` | receive | MCU sent a telemetry report |
| `UDS_REQUEST` | local | Incoming request from CLI |
| `UDS_RESPONSE` | local | Outgoing response to CLI |
| `FRAME_DECODE_ERROR` | local | Failed to decode a received serial frame |
| `FRAME_DISPATCH_ERROR` | local | Error while handling a decoded frame |

### 12.2 Follow

```
lt.py log --follow [--num N] [--type TYPE]
lt.py log -f
```

Prints the last `--num` events as JSON first, then streams new log lines to stdout in
real time (raw NDJSON, one line per event). Blocks until Ctrl+C.

**Final response** (after Ctrl+C):

```json
{ "ok": true, "follow_interrupted": true, "log_path": "/abs/path" }
```

---

## 13. Exit codes

| Code | Constant | Meaning |
|------|----------|---------|
| `0` | `EXIT_OK` | Success |
| `1` | `EXIT_ARGS` | Invalid CLI arguments |
| `2` | `EXIT_DAEMON` | Daemon not running or config mismatch |
| `3` | `EXIT_BUSINESS` | MCU-level or operation-level error |
| `4` | `EXIT_TIMEOUT` | Operation timed out |
| `5` | `EXIT_PROTOCOL` | Protocol error (corrupt frame, invalid response) |
| `6` | `EXIT_IO` | Local I/O error (file, socket, process) |

On any non-zero exit, stdout contains:

```json
{ "ok": false, "error": { "code": "...", "message": "...", "exit_code": N, "details": {...} } }
```

---

## 14. Error codes

Error codes appear in the JSON `error.code` field.

### CLI-level errors

| Code | Exit | Description |
|------|------|-------------|
| `INVALID_ARGS` | 1 | Bad CLI arguments or daemon rejected request arguments |
| `DAEMON_NOT_RUNNING` | 2 | Can't connect to daemon UDS socket |
| `DAEMON_CONFIG_MISMATCH` | 2 | Running daemon's `--port`/`--baud` doesn't match requested values |
| `DAEMON_ID_MISMATCH` | 2 | daemon.json and live daemon report different `daemon_id` (stale metadata) |
| `MCU_ERROR` | 3 | Daemon-reported business error (MCU rejected operation, param report not OK, etc.) |
| `TIMEOUT` | 4 | UDS connect/response timeout, or daemon-side MCU response timeout |
| `PROTOCOL_ERROR` | 5 | Daemon response not JSON, not an object, line too large, or daemon.json corrupt |
| `LOCAL_IO_ERROR` | 6 | Socket I/O failure, can't read daemon.json, can't launch daemon process |

### Daemon-internal errors (returned via UDS)

| Code | Description |
|------|-------------|
| `BAD_REQUEST` | Malformed UDS request (not JSON, missing fields, invalid args) |
| `NOT_READY` | Schema discovery not complete; try again shortly |
| `NOT_FOUND` | Parameter or command name not in schema |
| `BUSINESS_ERROR` | MCU-level failure (param report not OK, command failed, feature not enabled) |
| `TIMEOUT` | MCU didn't respond to the serial request |
| `TOO_LARGE` | Encoded frame exceeds negotiated `peer_max_decoded_frame` |
| `INTERNAL_ERROR` | Unexpected daemon exception |

---

## 15. Value types

Parameter and log field values use these wire types:

| Type name | Bytes | JSON representation | Range |
|-----------|-------|---------------------|-------|
| `bool` | 1 | `true` / `false` | — |
| `u8` | 1 | int | 0–255 |
| `i8` | 1 | int | −128–127 |
| `u16` | 2 | int | 0–65535 |
| `i16` | 2 | int | −32768–32767 |
| `u32` | 4 | int | 0–4294967295 |
| `i32` | 4 | int | −2147483648–2147483647 |
| `u64` | 8 | string (decimal) | 0–2⁶⁴−1 (string to avoid JSON precision loss) |
| `i64` | 8 | string (decimal) | −2⁶³–2⁶³−1 (string to avoid JSON precision loss) |
| `f32` | 4 | float | IEEE 754 single precision |
| `f64` | 8 | float | IEEE 754 double precision |
| `string` | 1+N | string | Max 255 UTF-8 bytes |
| `bytes` | 1+N | string (hex) | Max 255 bytes, represented as hex string |
| `enum_u8` | 1 | int | 0–255 (semantic meaning is firmware-specific) |

When setting values via `param set`, the CLI accepts:
- **Booleans:** `true`, `false`, `1`, `0`, `yes`, `no`, `on`, `off` (case-insensitive)
- **Integers:** decimal (`123`), hex (`0xFF`), octal (`0o77`), binary (`0b1010`) — only via direct UDS, not CLI `param set` which JSON-parses first
- **Floats:** standard decimal notation (`1.5`, `-0.3`, `1e-5`)
- **Strings:** any text that isn't valid JSON

---

## 16. Environment variables

| Variable | Used by | Description |
|----------|---------|-------------|
| `LITETUNE_PORT` | `daemon start` | Fallback serial port if `--port` is not passed and `daemon.json` has no port. |

---

## 17. Port resolution order

When `daemon start` needs a serial port, it checks in this order:

1. `--port` CLI argument
2. `port` field from existing `daemon.json` in the runtime directory
3. `LITETUNE_PORT` environment variable

If none are found, the command fails with `INVALID_ARGS`.
