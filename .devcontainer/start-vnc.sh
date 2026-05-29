#!/usr/bin/env bash

set -e

export USER=${USER:-vscode}
export HOME=${HOME:-/home/vscode}
export DISPLAY=:1

mkdir -p "$HOME/.vnc"

cat > "$HOME/.vnc/xstartup" << 'EOF'
#!/bin/sh
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS
startxfce4 &
EOF

chmod +x "$HOME/.vnc/xstartup"

# 设置 VNC 密码：123456
# 注意：这个密码只是 VNC 内部密码，Codespaces 端口建议保持 Private
if [ ! -f "$HOME/.vnc/passwd" ]; then
    echo "123456" | vncpasswd -f > "$HOME/.vnc/passwd"
    chmod 600 "$HOME/.vnc/passwd"
fi

# 清理旧进程
vncserver -kill :1 >/dev/null 2>&1 || true
pkill -f "websockify.*6080" >/dev/null 2>&1 || true

# 启动 VNC 桌面
vncserver :1 -geometry 2800x1840 -depth 24 -localhost no

# 启动 noVNC
websockify --web=/usr/share/novnc/ 6080 localhost:5901
