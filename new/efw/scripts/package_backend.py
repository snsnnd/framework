"""用 PyInstaller 把 studio_core 打成单文件后端，供 Electron 分发。

    uv run --group packaging python scripts/package_backend.py

产物在 backend-bin/：Linux/macOS 为 efw-backend，Windows 为 efw-backend.exe。
生成代码与虚拟目标构建仍需要 C 编译器与 runtime/，后者由 electron-builder
作为 extraResources 一起打包，主进程用 EFW_RUNTIME 指过去。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "backend-bin"
NAME = "efw-backend.exe" if sys.platform == "win32" else "efw-backend"


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("缺少 PyInstaller，请先执行：uv sync --group packaging", file=sys.stderr)
        return 1
    if shutil.which("cc") is None and shutil.which("gcc") is None and sys.platform != "win32":
        print("提示：打包出的后端仍会在用户机器上编译虚拟目标，建议随包说明需要 cc/gcc。", file=sys.stderr)

    cmd = [
        sys.executable, "-m", "PyInstaller", "--onefile", "--clean", "--noconfirm",
        "--name", NAME.removesuffix(".exe"),
        "--distpath", str(OUT), "--workpath", str(OUT / ".build"), "--specpath", str(OUT / ".build"),
        # pyserial 是真机串口的唯一依赖；标准库里的 socket/threading 等由 PyInstaller 自动收集
        "--paths", str(ROOT),
        "--hidden-import", "serial", "--collect-submodules", "studio_core",
        str(ROOT / "scripts" / "backend_entry.py"),
    ]
    print("$", " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        return result.returncode
    binary = OUT / NAME
    if not binary.exists():
        print(f"没有找到产物：{binary}", file=sys.stderr)
        return 1
    print(f"已生成 {binary}（{binary.stat().st_size // 1024} KB）")
    print("把它复制/链接到项目根的 backend-bin/ 后，electron-builder 会带进 resources/backend-bin/。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())