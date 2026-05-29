#!/usr/bin/env bash
set -euo pipefail

export DISPLAY="${DISPLAY:-:1}"
export VNC_GEOMETRY="${VNC_GEOMETRY:-1440x900}"
export VNC_DEPTH="${VNC_DEPTH:-24}"
export VNC_PASSWORD="${VNC_PASSWORD:-codespaces}"

mkdir -p "$HOME/.vnc"
chmod 700 "$HOME/.vnc"

if [ ! -f "$HOME/.vnc/passwd" ]; then
  printf '%s\n%s\n\n' "$VNC_PASSWORD" "$VNC_PASSWORD" | vncpasswd > /dev/null
  chmod 600 "$HOME/.vnc/passwd"
fi

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
  -SecurityTypes VncAuth \
  >/tmp/efw-vncserver.log 2>&1

pkill -f "websockify.*6080" >/dev/null 2>&1 || true
if [ -d /usr/share/novnc ]; then
  websockify --web=/usr/share/novnc 6080 localhost:5901 >/tmp/efw-novnc.log 2>&1 &
else
  websockify 6080 localhost:5901 >/tmp/efw-novnc.log 2>&1 &
fi

echo "EFW VNC desktop is running. Open forwarded port 6080; VNC password: ${VNC_PASSWORD}"
