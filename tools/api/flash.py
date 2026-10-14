"""Flash command construction and execution for EFW CLI."""

from __future__ import annotations

import re
import subprocess
import unicodedata
from pathlib import Path

from tools.target import TargetDescriptor, resolve_target


_PROBE_SERIAL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
_SCRIPT_PATH_METACHARS = frozenset('";[]{}$\\`|&<>')


def _validate_inputs(path: Path, port: str | None) -> None:
    path_text = str(path)
    if any(
        unicodedata.category(char) in {"Cc", "Cf", "Cs", "Zl", "Zp"} or char in _SCRIPT_PATH_METACHARS
        for char in path_text
    ):
        raise ValueError("固件路径包含不安全字符")
    if port is not None and _PROBE_SERIAL_RE.fullmatch(port) is None:
        raise ValueError("probe serial 只能包含 ASCII 字母、数字、点、下划线、冒号和连字符")


def build_flash_command(bin_file: str | Path, *, target: TargetDescriptor | None = None, chip: str | None = None, tool: str | None = None, port: str | None = None, erase: bool = False) -> list[str]:
    path = Path(bin_file).resolve()
    _validate_inputs(path, port)
    if not path.is_file():
        raise FileNotFoundError(f"固件文件不存在: {path}")
    resolved_target = target or resolve_target(chip=chip)
    selected_tool = tool or resolved_target.flash["default_tool"]
    address = resolved_target.flash["address"]
    if selected_tool == "stlink":
        cmd = ["st-flash"]
        if port:
            cmd.extend(["--serial", port])
        cmd.extend(["--reset", "write", str(path), address])
        return cmd
    if selected_tool == "jlink":
        cmd = ["JLinkExe", "-device", resolved_target.flash["jlink_device"], "-if", resolved_target.flash["interface"], "-speed", "4000", "-autoconnect", "1", "-ExitOnError", "1"]
        if port:
            cmd.extend(["-SelectEmuBySN", port])
        return cmd
    if selected_tool == "openocd":
        cmd = ["openocd", "-f", resolved_target.flash["openocd_interface"], "-f", resolved_target.flash["openocd_target"]]
        if port:
            cmd.extend(["-c", f"adapter serial {port}"])
        if erase:
            cmd.extend(["-c", f"init; reset halt; {resolved_target.flash['openocd_erase_driver']} mass_erase 0"])
        cmd.extend(["-c", f"program {{{path}}} verify reset exit {address}"])
        return cmd
    raise ValueError(f"不支持的烧录工具: {selected_tool}")


def run_flash(bin_file: str | Path, *, target: TargetDescriptor | None = None, chip: str | None = None, tool: str | None = None, port: str | None = None, erase: bool = False, dry_run: bool = False) -> list[str]:
    path = Path(bin_file).resolve()
    resolved_target = target or resolve_target(chip=chip)
    selected_tool = tool or resolved_target.flash["default_tool"]
    cmd = build_flash_command(path, target=resolved_target, tool=selected_tool, port=port, erase=erase)
    if dry_run:
        return cmd

    if selected_tool == "stlink" and erase:
        erase_cmd = ["st-flash"]
        if port:
            erase_cmd.extend(["--serial", port])
        erase_cmd.append("erase")
        subprocess.run(erase_cmd, check=True)

    input_text = None
    if selected_tool == "jlink":
        erase_command = "erase\n" if erase else ""
        input_text = f'r\nh\n{erase_command}loadbin "{path}", {resolved_target.flash["address"]}\nr\ng\nexit\n'
    subprocess.run(cmd, check=True, text=input_text is not None, input=input_text)
    return cmd
