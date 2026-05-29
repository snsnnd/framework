#!/usr/bin/env bash
set -euo pipefail

python3 -m py_compile tools/efw_codegen.py tools/efw_visual_editor.py tools/efw_project_manager.py
cmake -S . -B build -DEFW_BUILD_APPLICATIONS=ON
cmake --build build

cat <<'EOF'

EFW Codespace is ready.
- VNC/noVNC starts automatically on port 6080 when the container starts.
- Open the forwarded "noVNC desktop for PyQt tools" port in a browser.
- In the desktop terminal, run: python3 tools/efw_project_manager.py
EOF
