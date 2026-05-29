#!/usr/bin/env bash
set -euo pipefail

QUICK=0
if [ "${1:-}" = "--quick" ]; then
  QUICK=1
fi

export DISPLAY="${DISPLAY:-:1}"
export VNC_PORT="${VNC_PORT:-5901}"
export NOVNC_PORT="${NOVNC_PORT:-6080}"

fail() {
  echo "[FAIL] $*" >&2
  echo "--- /tmp/efw-vncserver.log ---" >&2
  tail -n 80 /tmp/efw-vncserver.log 2>/dev/null >&2 || true
  echo "--- /tmp/efw-novnc.log ---" >&2
  tail -n 80 /tmp/efw-novnc.log 2>/dev/null >&2 || true
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "missing command: $1"
}

wait_tcp() {
  local host="$1"
  local port="$2"
  local label="$3"
  python3 - "$host" "$port" "$label" <<'PY'
import socket
import sys
import time
host, port, label = sys.argv[1], int(sys.argv[2]), sys.argv[3]
deadline = time.time() + 20
last = None
while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=1):
            print(f"[OK] {label} is listening on {host}:{port}")
            raise SystemExit(0)
    except OSError as exc:
        last = exc
        time.sleep(0.5)
print(f"[FAIL] {label} is not reachable on {host}:{port}: {last}", file=sys.stderr)
raise SystemExit(1)
PY
}

need_cmd python3
need_cmd vncserver
need_cmd websockify
need_cmd fc-match

fc-match "Noto Sans CJK SC" | grep -qi "Noto" || fail "Noto CJK font is not available"
echo "[OK] Noto CJK font is available: $(fc-match 'Noto Sans CJK SC')"

python3 - <<'PY' || fail "PyQt6 import failed"
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import QApplication  # noqa: F401
print("[OK] PyQt6 import works")
print("[OK] Qt font database import works", QFontDatabase)
PY

vncserver -list | grep -q "${DISPLAY}" || fail "TigerVNC display ${DISPLAY} is not listed"
wait_tcp 127.0.0.1 "$VNC_PORT" "TigerVNC"
wait_tcp 127.0.0.1 "$NOVNC_PORT" "noVNC/websockify"

python3 - "$NOVNC_PORT" <<'PY' || fail "noVNC HTTP probe failed"
import http.client
import sys
port = int(sys.argv[1])
conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
conn.request("GET", "/vnc.html")
resp = conn.getresponse()
body = resp.read(4096)
if resp.status >= 400 or b"noVNC" not in body:
    raise SystemExit(f"unexpected noVNC response: status={resp.status}, contains_noVNC={b'noVNC' in body}")
print("[OK] noVNC /vnc.html responds")
PY

if [ "$QUICK" -eq 0 ]; then
  python3 - <<'PY' || fail "PyQt6 QApplication smoke test failed on DISPLAY"
import os
import sys
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QLabel
app = QApplication(sys.argv)
label = QLabel(f"EFW Qt smoke on {os.environ.get('DISPLAY')}")
label.show()
QTimer.singleShot(250, app.quit)
app.exec()
print("[OK] PyQt6 QApplication smoke test displayed on VNC")
PY
fi

echo "[OK] EFW VNC/noVNC environment checks passed"
