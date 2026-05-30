#!/usr/bin/env bash
set -euo pipefail

export DISPLAY="${DISPLAY:-:1}"
export VNC_GEOMETRY="${VNC_GEOMETRY:-1920x1260}"
export VNC_DEPTH="${VNC_DEPTH:-24}"
export VNC_PASSWORD="${VNC_PASSWORD:-123456}"
export VNC_PORT="${VNC_PORT:-5901}"
export NOVNC_PORT="${NOVNC_PORT:-6080}"

# 可选值：
# xterm：最稳定，推荐
# xfce：完整桌面，但在 Codespaces 中可能更容易出问题
export VNC_SESSION="${VNC_SESSION:-xterm}"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "[FAIL] missing command: $1"
    echo "Please install it in Dockerfile and rebuild the container."
    exit 1
  }
}

need_cmd vncserver
need_cmd vncpasswd
need_cmd websockify

if [ "$VNC_SESSION" = "xterm" ]; then
  need_cmd xterm
fi

if [ "$VNC_SESSION" = "xfce" ]; then
  need_cmd xfce4-session
  need_cmd dbus-launch
fi

mkdir -p "$HOME/.vnc"
chmod 700 "$HOME/.vnc"

printf '%s\n' "$VNC_PASSWORD" | vncpasswd -f > "$HOME/.vnc/passwd"
chmod 600 "$HOME/.vnc/passwd"

if [ "$VNC_SESSION" = "xfce" ]; then
  cat > "$HOME/.vnc/xstartup" <<'EOF_XSTARTUP'
#!/usr/bin/env bash
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS

export XDG_SESSION_TYPE=x11
export XDG_CURRENT_DESKTOP=XFCE
export DESKTOP_SESSION=xfce

xrdb "$HOME/.Xresources" 2>/dev/null || true

exec dbus-launch --exit-with-session xfce4-session
EOF_XSTARTUP
else
  cat > "$HOME/.vnc/xstartup" <<'EOF_XSTARTUP'
#!/usr/bin/env bash
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS

exec xterm
EOF_XSTARTUP
fi

chmod +x "$HOME/.vnc/xstartup"

echo "[INFO] Stopping old VNC/noVNC processes..."

vncserver -kill "$DISPLAY" >/dev/null 2>&1 || true
pkill -f "websockify.*${NOVNC_PORT}" >/dev/null 2>&1 || true

rm -f "/tmp/.X${DISPLAY#:}-lock" "/tmp/.X11-unix/X${DISPLAY#:}" 2>/dev/null || true

echo "[INFO] Starting TigerVNC..."
echo "[INFO] DISPLAY=${DISPLAY}"
echo "[INFO] VNC_PORT=${VNC_PORT}"
echo "[INFO] VNC_GEOMETRY=${VNC_GEOMETRY}"
echo "[INFO] VNC_SESSION=${VNC_SESSION}"

if ! vncserver "$DISPLAY" \
  -geometry "$VNC_GEOMETRY" \
  -depth "$VNC_DEPTH" \
  -localhost no \
  -rfbport "$VNC_PORT" \
  -SecurityTypes VncAuth \
  > /tmp/efw-vncserver.log 2>&1; then

  echo "[FAIL] vncserver failed"
  echo
  echo "--- /tmp/efw-vncserver.log ---"
  cat /tmp/efw-vncserver.log || true

  echo
  echo "--- ~/.vnc logs ---"
  cat "$HOME"/.vnc/*.log 2>/dev/null || true

  exit 1
fi

echo "[INFO] Starting noVNC/websockify..."

NOVNC_WEB=""

if [ -d /usr/share/novnc ]; then
  NOVNC_WEB="/usr/share/novnc"
elif [ -d /usr/share/novnc-py ]; then
  NOVNC_WEB="/usr/share/novnc-py"
elif [ -d /usr/share/javascript/novnc ]; then
  NOVNC_WEB="/usr/share/javascript/novnc"
fi

if [ -n "$NOVNC_WEB" ]; then
  echo "[INFO] noVNC web root: $NOVNC_WEB"
  websockify --web="$NOVNC_WEB" "$NOVNC_PORT" "localhost:${VNC_PORT}" > /tmp/efw-novnc.log 2>&1 &
else
  echo "[WARN] noVNC web root not found, starting websocket proxy only."
  websockify "$NOVNC_PORT" "localhost:${VNC_PORT}" > /tmp/efw-novnc.log 2>&1 &
fi

sleep 2

echo
echo "[INFO] Current VNC sessions:"
vncserver -list || true

echo
echo "[OK] VNC/noVNC started."
echo "Open forwarded port: ${NOVNC_PORT}"
echo "noVNC page: /vnc.html"
echo "VNC password: ${VNC_PASSWORD}"
echo
echo "If you run GUI apps from VS Code terminal, use:"
echo "export DISPLAY=${DISPLAY}"
echo
echo "Example:"
echo "python3 tools/efw_studio.py"
