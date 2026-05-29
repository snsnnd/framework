#!/usr/bin/env bash
set -euo pipefail

echo "[INFO] Running post-create checks..."

chmod +x .devcontainer/start-vnc.sh || true
chmod +x .devcontainer/check-vnc.sh || true

if [ -f tools/efw_codegen.py ] && [ -f tools/efw_visual_editor.py ] && [ -f tools/efw_project_manager.py ]; then
  python3 -m py_compile \
    tools/efw_codegen.py \
    tools/efw_visual_editor.py \
    tools/efw_project_manager.py

  echo "[OK] Python tools compile check passed."
else
  echo "[WARN] Some tools/*.py files were not found. Skipping Python compile check."
fi

if [ -f CMakeLists.txt ]; then
  cmake -S . -B build -DEFW_BUILD_APPLICATIONS=ON || {
    echo "[WARN] CMake configure failed. You can fix project build files later."
  }

  cmake --build build || {
    echo "[WARN] CMake build failed. You can fix project build files later."
  }
else
  echo "[WARN] CMakeLists.txt not found. Skipping CMake build."
fi

cat <<'EOF'

EFW Codespace is ready.

VNC/noVNC:
- Display: :1
- VNC port: 5901
- noVNC port: 6080
- noVNC page: /vnc.html
- Default password: 123456

To start VNC manually:
  .devcontainer/start-vnc.sh

To check VNC:
  .devcontainer/check-vnc.sh

To run GUI tools:
  export DISPLAY=:1
  python3 tools/efw_project_manager.py

EOF
