"""Target descriptor loading and project target resolution."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET_INDEX_PATH = REPO_ROOT / "data" / "targets" / "index.json"
MCU_INDEX_PATH = REPO_ROOT / "data" / "mcu" / "index.json"
GENERIC_BOARD_PROFILES = frozenset({"", "stm32-basic", "generic-mock"})


class TargetResolutionError(ValueError):
    """Raised when target inputs are missing, unsupported, or contradictory."""


@dataclass(frozen=True)
class TargetDescriptor:
    chip: str
    platform: str
    family: str
    core: str
    abi: str
    toolchain: str
    sdk: str
    cpu_flags: tuple[str, ...]
    defines: tuple[str, ...]
    startup: str
    startup_source: str
    linker: str
    artifact: str
    memory: dict[str, str | int]
    board_profiles: tuple[str, ...]
    flash: dict[str, str]


def _load_object(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TargetResolutionError(f"目标数据不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TargetResolutionError(f"目标数据不是有效 JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise TargetResolutionError(f"目标数据必须是 JSON object: {path}")
    return data


def load_targets() -> dict[str, TargetDescriptor]:
    raw_targets = _load_object(TARGET_INDEX_PATH)
    mcu_index = _load_object(MCU_INDEX_PATH)
    targets: dict[str, TargetDescriptor] = {}
    required = (
        "platform", "family", "core", "abi", "toolchain", "sdk", "cpu_flags", "defines",
        "startup", "startup_source", "linker", "artifact", "memory", "board_profiles", "flash",
    )
    flash_required = ("default_tool", "address", "jlink_device", "interface", "openocd_interface", "openocd_target", "openocd_erase_driver")

    for raw_chip, data in raw_targets.items():
        chip = str(raw_chip).strip().upper()
        if not isinstance(data, dict):
            raise TargetResolutionError(f"目标 {chip} 必须是 JSON object")
        missing = [field for field in required if not data.get(field)]
        if missing:
            raise TargetResolutionError(f"目标 {chip} 缺少字段: {', '.join(missing)}")
        if chip not in mcu_index:
            raise TargetResolutionError(f"目标 {chip} 没有对应的 MCU 数据")
        if str(mcu_index[chip].get("family", "")) != str(data["family"]):
            raise TargetResolutionError(f"目标 {chip} 与 MCU 数据的 family 不一致")
        board_profiles = data["board_profiles"]
        cpu_flags = data["cpu_flags"]
        defines = data["defines"]
        memory = data["memory"]
        flash = data["flash"]
        if not isinstance(board_profiles, list) or not all(isinstance(item, str) and item for item in board_profiles):
            raise TargetResolutionError(f"目标 {chip} 的 board_profiles 无效")
        if not isinstance(cpu_flags, list) or not all(isinstance(item, str) and item for item in cpu_flags):
            raise TargetResolutionError(f"目标 {chip} 的 cpu_flags 无效")
        if not isinstance(defines, list) or not all(isinstance(item, str) and item for item in defines):
            raise TargetResolutionError(f"目标 {chip} 的 defines 无效")
        memory_required = ("flash_origin", "flash_kb", "ram_origin", "ram_kb")
        if not isinstance(memory, dict) or any(not memory.get(field) for field in memory_required):
            raise TargetResolutionError(f"目标 {chip} 的 memory 配置无效")
        if not isinstance(flash, dict):
            raise TargetResolutionError(f"目标 {chip} 的 flash 配置无效")
        missing_flash = [field for field in flash_required if not flash.get(field)]
        if missing_flash:
            raise TargetResolutionError(f"目标 {chip} 的 flash 配置缺少字段: {', '.join(missing_flash)}")
        targets[chip] = TargetDescriptor(
            chip=chip,
            platform=str(data["platform"]),
            family=str(data["family"]),
            core=str(data["core"]),
            abi=str(data["abi"]),
            toolchain=str(data["toolchain"]),
            sdk=str(data["sdk"]),
            cpu_flags=tuple(cpu_flags),
            defines=tuple(defines),
            startup=str(data["startup"]),
            startup_source=str(data["startup_source"]),
            linker=str(data["linker"]),
            artifact=str(data["artifact"]),
            memory={str(key): value for key, value in memory.items()},
            board_profiles=tuple(board_profiles),
            flash={str(key): str(value) for key, value in flash.items()},
        )
    return targets


def load_mcu_data(chip: str) -> dict[str, Any]:
    target = resolve_target(chip=chip)
    mcu_index = _load_object(MCU_INDEX_PATH)
    entry = mcu_index.get(target.chip)
    if not isinstance(entry, dict) or not str(entry.get("path") or "").strip():
        raise TargetResolutionError(f"目标 {target.chip} 没有 MCU 数据路径")
    path = REPO_ROOT / "data" / "mcu" / str(entry["path"])
    data = _load_object(path)
    if str(data.get("name") or "").upper() != target.chip:
        raise TargetResolutionError(f"目标 {target.chip} 与 MCU 数据名称不一致: {path}")
    return data


def resolve_target(*, chip: str | None = None, board_profile: str | None = None) -> TargetDescriptor:
    targets = load_targets()
    chip_name = str(chip or "").strip().upper()
    board_name = str(board_profile or "").strip()
    board_key = board_name.casefold()

    board_target: TargetDescriptor | None = None
    if board_key and board_key not in GENERIC_BOARD_PROFILES:
        matches = [
            target
            for target in targets.values()
            if board_key in {profile.casefold() for profile in target.board_profiles}
            or board_key == target.chip.casefold().replace("-", "_")
        ]
        if not matches:
            raise TargetResolutionError(f"Board Profile 没有目标描述: {board_name}")
        if len(matches) != 1:
            raise TargetResolutionError(f"Board Profile 对应多个目标: {board_name}")
        board_target = matches[0]

    chip_target = targets.get(chip_name) if chip_name else None
    if chip_name and chip_target is None:
        raise TargetResolutionError(f"不支持的目标芯片: {chip_name}")
    if chip_target and board_target and chip_target.chip != board_target.chip:
        raise TargetResolutionError(
            f"目标冲突: 芯片 {chip_target.chip} 与 Board Profile {board_name} ({board_target.chip}) 不一致"
        )
    target = chip_target or board_target
    if target is None:
        raise TargetResolutionError("项目缺少可解析的目标；请设置受支持的 chip 或 Board Profile")
    return target


def resolve_project_target(project: dict[str, Any], graph: dict[str, Any] | None = None, *, chip: str | None = None) -> TargetDescriptor:
    project_chip = str(project.get("chip") or "").strip()
    graph_chip = str((graph or {}).get("project", {}).get("chip") or "").strip()
    chip_inputs = [name for name in (str(chip or "").strip(), project_chip, graph_chip) if name]
    if len({name.casefold() for name in chip_inputs}) > 1:
        raise TargetResolutionError(f"目标芯片不一致: {', '.join(chip_inputs)}")

    project_board = str(project.get("board_profile") or "").strip()
    graph_board = str((graph or {}).get("board", {}).get("profile") or "").strip()
    specific_boards = [name for name in (project_board, graph_board) if name.casefold() not in GENERIC_BOARD_PROFILES]
    if len({name.casefold() for name in specific_boards}) > 1:
        raise TargetResolutionError(f"项目 Board Profile {project_board} 与 Graph Board Profile {graph_board} 不一致")

    resolved_chip = chip_inputs[0] if chip_inputs else ""
    resolved_board = specific_boards[0] if specific_boards else project_board or graph_board
    return resolve_target(chip=resolved_chip, board_profile=resolved_board)
