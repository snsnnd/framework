#!/usr/bin/env bash
set -euo pipefail

export DISPLAY="${DISPLAY:-:1}"
export VNC_GEOMETRY="${VNC_GEOMETRY:-1440x900}"
export VNC_DEPTH="${VNC_DEPTH:-24}"
export VNC_PASSWORD="${VNC_PASSWORD:-codespaces}"
export VNC_PORT="${VNC_PORT:-5901}"
export NOVNC_PORT="${NOVNC_PORT:-6080}"

mkdir -p "$HOME/.vnc"
chmod 700 "$HOME/.vnc"

# TigerVNC supports a non-interactive password mode via `vncpasswd -f`.
# Regenerate the password on each container start so changing VNC_PASSWORD takes effect.
printf '%s\n' "$VNC_PASSWORD" | vncpasswd -f > "$HOME/.vnc/passwd"
chmod 600 "$HOME/.vnc/passwd"

cat > "$HOME/.vnc/xstartup" <<'EOF'
#!/usr/bin/env bash
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS
xrdb "$HOME/.Xresources" 2>/dev/null || true
startxfce4 &
EOF
chmod +x "$HOME/.vnc/xstartup"

vncserver -kill "$DISPLAY" >/dev/null 2>&1 || true
rm -f "/tmp/.X${DISPLAY#:}-lock" "/tmp/.X11-unix/X${DISPLAY#:}" 2>/dev/null || true

vncserver "$DISPLAY" \
  -geometry "$VNC_GEOMETRY" \
  -depth "$VNC_DEPTH" \
  -localhost no \
  -rfbport "$VNC_PORT" \
  -SecurityTypes VncAuth \
  > /tmp/efw-vncserver.log 2>&1

pkill -f "websockify.*${NOVNC_PORT}.*localhost:${VNC_PORT}" >/dev/null 2>&1 || true
if [ -d /usr/share/novnc ]; then
  websockify --web=/usr/share/novnc "$NOVNC_PORT" "localhost:${VNC_PORT}" > /tmp/efw-novnc.log 2>&1 &
else
  websockify "$NOVNC_PORT" "localhost:${VNC_PORT}" > /tmp/efw-novnc.log 2>&1 &
fi

# Fail early in Codespaces if the desktop or noVNC proxy did not come up.
bash .devcontainer/check-vnc.sh --quick

echo "EFW VNC desktop is running. Open forwarded port ${NOVNC_PORT}; VNC password: ${VNC_PASSWORD}"
echo "noVNC URL path: /vnc.html?host=localhost&port=${NOVNC_PORT}"
