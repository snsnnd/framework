---
name: litetune
description: |
  How to use the LiteTune CLI (`lt.py`) to communicate with microcontrollers (MCUs) over serial.
  Covers the full workflow: environment setup, daemon lifecycle, schema discovery, parameter
  read/write, command execution, log inspection, and troubleshooting. Use this skill whenever
  the user mentions LiteTune, MCU tuning, serial parameter adjustment, embedded device
  configuration, or wants to read/write values on a microcontroller. Also use it when you see
  a `src/litetune-skill/` directory in the project, or the user asks about daemon management
  for serial devices, even if they don't say "LiteTune" explicitly.
---

# LiteTune Skill

LiteTune is a daemon + CLI system for talking to microcontrollers over serial. A background
daemon (`daemon.py`) holds the serial connection open and speaks the LiteTune binary protocol;
the CLI (`lt.py`) sends JSON-over-Unix-Domain-Socket requests to the daemon and prints
structured JSON to stdout. Every CLI output is machine-readable JSON — parse it, don't
regex-scrape it.

## Reference

For exact argument names, full response schemas, every error code, and value type details,
read [`ref.md`](ref.md) (in the same directory as this file). This SKILL.md covers the
workflow and common usage; ref.md is the exhaustive per-command specification.

## 1. Locate the code

The LiteTune source lives at a path like `src/litetune-skill/code/`. Before doing anything,
confirm the path exists:

```bash
ls src/litetune-skill/code/lt.py
```

All `lt.py` invocations below assume you `cd` into the repo root first. The runtime directory
(where the daemon keeps its socket, log, and metadata) defaults to `src/litetune-skill/runtime/`.

## 2. Environment setup

LiteTune needs `pyserial` and `pyserial-asyncio`. Prefer **uv**; fall back to a standard venv
if uv is unavailable.

### With uv (preferred)

```bash
cd src/litetune-skill/code

# One-shot: uv will create .venv and install deps from pyproject.toml automatically
uv run python lt.py --help

# Or set up explicitly
uv venv
uv pip install -e .
# Then run via:
uv run python lt.py --help
```

### With python venv (fallback)

```bash
cd src/litetune-skill/code
python -m venv .venv

# Activate
# Linux/macOS:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

pip install pyserial pyserial-asyncio
python lt.py --help
```

From here on, examples use `python lt.py` — substitute `uv run python lt.py` if using uv
without activating the venv.

## 3. Core workflow

The typical session is a straight pipeline:

```
1. Find the serial port        →  lt.py port-list
2. Start the daemon            →  lt.py daemon start --port <PORT>
3. Inspect the MCU schema      →  lt.py schema
4. Read / write parameters     →  lt.py param get / param set
5. Run MCU commands             →  lt.py cmd <name>
6. Check logs if needed        →  lt.py log
7. Stop the daemon             →  lt.py daemon stop
```

### 3.1 Find the serial port

```bash
python lt.py port-list
```

Returns `{"ok": true, "ports": [...]}`. Each port object has `device`, `description`, `hwid`.
Pick the device path (e.g. `/dev/ttyUSB0`, `COM3`) for the next step. If the list is empty,
the MCU is not physically connected or the serial driver is missing.

### 3.2 Start the daemon

```bash
python lt.py daemon start --port /dev/ttyUSB0
```

Key options:
| Flag | Default | Purpose |
|------|---------|---------|
| `--port` | *(required)* | Serial port device path |
| `--baud` | `115200` | Baud rate — must match the MCU firmware |
| `--wait` | `5.0` | Seconds to wait for the daemon to become connectable |
| `--runtime` | `../runtime` | Directory for socket, log, daemon.json |
| `--host-max-decoded-frame` | `2048` | Max decoded frame size the host accepts |
| `--log-max-bytes` | `0` (unlimited) | Rotate the log file when it exceeds this size |
| `--telemetry-log` | `all` | `all`, `off`, or `decimate:N` |

On success you get `{"ok": true, "started": true, ...}`. If the daemon is already running
you get `{"ok": true, "started": false, "reason": "already_running", ...}` — this is
idempotent and safe.

**What happens at startup:** the daemon opens the serial port, sends a DISCOVER frame, waits
for the MCU to reply with its full schema (parameters, commands, log layouts). Once schema
discovery completes, the daemon state moves to `"ready"`. If discovery fails, state is
`"error"` — check `lt.py log` for details.

### 3.3 Check daemon status

```bash
python lt.py daemon status
```

The response includes `connectable` (can we talk to the daemon?), `pid_alive`, `metadata`,
and the daemon's self-reported status including `state`, `schema_ready`, and `stats`.

### 3.4 Get the MCU schema

```bash
python lt.py schema
```

Returns the full discovered schema: `device` info, `features` enabled on the MCU, `params`
(name → id/type/unit), `commands` (name → id/flags), and `layouts` (telemetry log formats).

To force a re-discovery (e.g. after MCU firmware update):

```bash
python lt.py schema --refresh
```

### 3.5 Parameters

**List available parameters** (names, types, units):

```bash
python lt.py param list
```

**Read parameter values:**

```bash
# Read specific parameters by name
python lt.py param get motor_speed pid_kp

# Read all parameters at once
python lt.py param get --all
```

The response `params` object maps each name to `{id, type, unit, value, status}`.

**Write parameter values:**

```bash
# Set one or more parameters (comma-separated NAME=VALUE pairs)
python lt.py param set "motor_speed=1200"
python lt.py param set "pid_kp=1.5,pid_ki=0.3,pid_kd=0.05"
```

Values are auto-parsed: numbers become int/float, `true`/`false` become booleans, everything
else stays a string. The type must match what the MCU schema declares for that parameter.

After a set, the MCU sends back a PARAM_REPORT confirming the new values — the response
contains the actual values read back from the MCU (which may differ if the MCU clamped them).

### 3.6 Commands

```bash
python lt.py cmd save_config
python lt.py cmd factory_reset
```

Only commands with the `HOST_TO_MCU` flag can be invoked from the host side. The response
includes the command's status and any payload the MCU returned (as `payload_hex`).

You can add a timeout for slow commands:

```bash
python lt.py cmd calibrate --command-timeout 10.0
```

### 3.7 Logs

**Tail recent events:**

```bash
python lt.py log                     # last 10 events
python lt.py log --num 50            # last 50 events
python lt.py log --type PARAM_REPORT # filter by event type
```

**Follow the log in real time** (like `tail -f`):

```bash
python lt.py log --follow
```

Press Ctrl+C to stop following.

### 3.8 Stop the daemon

```bash
python lt.py daemon stop
```

If the daemon is unresponsive, force-kill by PID:

```bash
python lt.py daemon stop --force
```

To stop and immediately restart (e.g. after changing baud):

```bash
python lt.py daemon restart --port /dev/ttyUSB0 --baud 230400
```

## 4. Global options

These apply to every subcommand:

| Flag | Default | Purpose |
|------|---------|---------|
| `--runtime` | `src/litetune-skill/runtime/` | Runtime directory path |
| `--timeout` | `5.0` | UDS request timeout in seconds |
| `--pretty` | off | Pretty-print JSON output for human debugging; agents should omit it to save tokens |

## 5. Output format and error handling

**All output is JSON.** On success: `{"ok": true, ...}`. On failure: `{"ok": false, "error": {"code": "...", "message": "...", ...}}`.

Exit codes tell you the failure category without parsing JSON:

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Invalid arguments |
| 2 | Daemon not running / config mismatch |
| 3 | MCU-level business error |
| 4 | Timeout |
| 5 | Protocol error |
| 6 | Local I/O error |

**Common error codes in the JSON `error.code`:**

- `DAEMON_NOT_RUNNING` — daemon isn't started; run `daemon start`
- `DAEMON_CONFIG_MISMATCH` — daemon is running with different --port/--baud than requested
- `NOT_READY` — schema discovery hasn't completed; wait or check `daemon status`
- `NOT_FOUND` — parameter or command name doesn't exist in the MCU schema
- `TIMEOUT` — MCU didn't respond in time; check wiring, baud rate, MCU firmware
- `TOO_LARGE` — request frame exceeds what the MCU can handle
- `BAD_REQUEST` — malformed request (wrong syntax, missing arguments)

## 6. Troubleshooting

### Daemon won't start
1. Is the serial port correct? Run `port-list` to enumerate.
2. Is another process using the port? Close serial monitors, other daemons.
3. Check `src/litetune-skill/runtime/daemon.stdout.log` for Python tracebacks.

### Schema discovery fails
1. Baud rate mismatch — the most common cause. Confirm with firmware docs.
2. MCU not running LiteTune firmware — the device must implement the LiteTune protocol.
3. Wiring issue — check TX/RX connections (they should be crossed: host TX → MCU RX).
4. Try `lt.py schema --refresh` to retry discovery.

### Parameter set reports clamped values
This is normal. The MCU validates ranges and returns the actual stored value. Compare the
`value` in the response to what you sent. If they differ, the MCU clamped or rejected it.

### Daemon becomes unresponsive
```bash
python lt.py daemon stop --force
python lt.py daemon start --port /dev/ttyUSB0
```

## 7. Typical agent session — complete example

```bash
cd src/litetune-skill/code

# 1. Find the port
uv run python lt.py port-list

# 2. Start daemon
uv run python lt.py daemon start --port /dev/ttyUSB0 --baud 115200

# 3. Verify it's ready
uv run python lt.py daemon status

# 4. See what the MCU exposes
uv run python lt.py schema

# 5. Read current tuning
uv run python lt.py param get --all

# 6. Adjust a parameter
uv run python lt.py param set "pid_kp=2.0"

# 7. Verify the new value took effect
uv run python lt.py param get pid_kp

# 8. Trigger a save so it persists across MCU reboot
uv run python lt.py cmd save_config

# 9. Check recent log for any issues
uv run python lt.py log --num 20

# 10. Done — shut down
uv run python lt.py daemon stop
```

## 8. Reference: all subcommands at a glance

| Command | Purpose |
|---------|---------|
| `port-list` | List serial ports on the system |
| `daemon start` | Launch the background daemon |
| `daemon stop` | Gracefully stop the daemon |
| `daemon restart` | Stop then start |
| `daemon status` | Report daemon health and metadata |
| `schema` | Get the discovered MCU schema |
| `schema --refresh` | Force schema re-discovery |
| `param list` | List parameter names/types from schema |
| `param get <names...>` | Read parameter values from MCU |
| `param get --all` | Read all parameter values |
| `param set "N=V,..."` | Write parameter values to MCU |
| `cmd <name>` | Execute an MCU command |
| `log` | Tail recent log events |
| `log --follow` | Stream log events in real time |
