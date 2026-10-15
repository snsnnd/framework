"""Strict STM32Cube SDK resource resolution for target builds."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from tools.firmware.manager import FIRMWARES, FirmwareManager
from tools.target import REPO_ROOT, TargetDescriptor


class STM32SDKError(ValueError):
    """Raised when an STM32 target cannot be backed by an installed Cube SDK."""


@dataclass(frozen=True)
class STM32BuildResources:
    sdk_root: Path
    include_dirs: tuple[Path, ...]
    sources: tuple[Path, ...]
    startup: Path
    linker: Path


def _required_dir(path: Path, description: str) -> Path:
    if not path.is_dir():
        raise STM32SDKError(f"STM32Cube SDK 缺少 {description}: {path}")
    return path


def _required_file(path: Path, description: str) -> Path:
    if not path.is_file():
        raise STM32SDKError(f"STM32Cube SDK 缺少 {description}: {path}")
    return path


def _sdk_root(path: Path) -> Path:
    if (path / "Drivers").is_dir():
        return path
    children = [child for child in path.iterdir() if child.is_dir()]
    if len(children) == 1 and (children[0] / "Drivers").is_dir():
        return children[0]
    raise STM32SDKError(f"STM32Cube SDK 根目录缺少 Drivers: {path}")


def _linker_script(target: TargetDescriptor) -> str:
    memory = target.memory
    return f"""/* Generated from EFW target {target.chip}. */
ENTRY(Reset_Handler)

_estack = ORIGIN(RAM) + LENGTH(RAM);
_Min_Heap_Size = 0x200;
_Min_Stack_Size = 0x400;

MEMORY
{{
  FLASH (rx)  : ORIGIN = {memory['flash_origin']}, LENGTH = {memory['flash_kb']}K
  RAM   (xrw) : ORIGIN = {memory['ram_origin']}, LENGTH = {memory['ram_kb']}K
}}

SECTIONS
{{
  .isr_vector : {{ . = ALIGN(4); KEEP(*(.isr_vector)) . = ALIGN(4); }} > FLASH
  .text :
  {{
    . = ALIGN(4); *(.text) *(.text*) *(.glue_7) *(.glue_7t)
    *(.eh_frame) KEEP(*(.init)) KEEP(*(.fini)) . = ALIGN(4); _etext = .;
  }} > FLASH
  .rodata : {{ . = ALIGN(4); *(.rodata) *(.rodata*) . = ALIGN(4); }} > FLASH
  .ARM.extab : {{ *(.ARM.extab* .gnu.linkonce.armextab.*) }} > FLASH
  .ARM.exidx : {{ __exidx_start = .; *(.ARM.exidx*) __exidx_end = .; }} > FLASH
  .preinit_array : {{ PROVIDE_HIDDEN(__preinit_array_start = .); KEEP(*(.preinit_array*)) PROVIDE_HIDDEN(__preinit_array_end = .); }} > FLASH
  .init_array : {{ PROVIDE_HIDDEN(__init_array_start = .); KEEP(*(SORT(.init_array.*))) KEEP(*(.init_array*)) PROVIDE_HIDDEN(__init_array_end = .); }} > FLASH
  .fini_array : {{ PROVIDE_HIDDEN(__fini_array_start = .); KEEP(*(SORT(.fini_array.*))) KEEP(*(.fini_array*)) PROVIDE_HIDDEN(__fini_array_end = .); }} > FLASH
  _sidata = LOADADDR(.data);
  .data :
  {{
    . = ALIGN(4); _sdata = .; *(.data) *(.data*) *(.RamFunc) *(.RamFunc*)
    . = ALIGN(4); _edata = .;
  }} > RAM AT > FLASH
  .bss (NOLOAD) :
  {{
    . = ALIGN(4); _sbss = .; __bss_start__ = _sbss; *(.bss) *(.bss*) *(COMMON)
    . = ALIGN(4); _ebss = .; __bss_end__ = _ebss;
  }} > RAM
  ._user_heap_stack (NOLOAD) :
  {{
    . = ALIGN(8); PROVIDE(end = .); PROVIDE(_end = .);
    . = . + _Min_Heap_Size; . = . + _Min_Stack_Size; . = ALIGN(8);
  }} > RAM
  .ARM.attributes 0 : {{ *(.ARM.attributes) }}
}}
"""


def _has_board_init(project_dir: Path) -> bool:
    pattern = re.compile(r"\befw_status_t\s+app_board_init\s*\(\s*void\s*\)\s*\{")
    for source in project_dir.rglob("*.c"):
        if "build" in source.parts or ".efw_target" in source.parts:
            continue
        if pattern.search(source.read_text(encoding="utf-8", errors="ignore")):
            return True
    return False


def _main_calls_board_init(project_dir: Path) -> bool:
    main_file = project_dir / "main.c"
    if not main_file.is_file():
        return False
    content = main_file.read_text(encoding="utf-8", errors="ignore")
    return re.search(r"\bif\s*\(\s*app_board_init\s*\(\s*\)", content) is not None


def prepare_stm32_build(
    project_dir: Path,
    target: TargetDescriptor,
    manager: FirmwareManager | None = None,
) -> STM32BuildResources:
    if target.platform != "stm32":
        raise STM32SDKError(f"目标不是 STM32: {target.chip}")
    manager = manager or FirmwareManager()
    config = manager.config.get(target.sdk)
    if not isinstance(config, dict) or not str(config.get("path", "")).strip():
        raise STM32SDKError(
            f"目标 {target.chip} 需要已安装的 {target.sdk}；请运行 `python3 tools/efw.py firmware download {target.sdk}`"
        )
    sdk_root = Path(str(config["path"])).expanduser().resolve()
    if not sdk_root.is_dir():
        raise STM32SDKError(f"已配置的 {target.sdk} 路径不存在: {sdk_root}")
    sdk_root = _sdk_root(sdk_root)
    firmware = FIRMWARES.get(target.sdk)
    if firmware is None:
        raise STM32SDKError(f"目标 {target.chip} 引用了未知 SDK: {target.sdk}")

    family = target.family
    family_lower = family.lower()
    cmsis = _required_dir(sdk_root / "Drivers" / "CMSIS" / "Include", "CMSIS Core headers")
    device_root = _required_dir(sdk_root / "Drivers" / "CMSIS" / "Device" / "ST" / f"{family}xx", "CMSIS device package")
    device_include = _required_dir(device_root / "Include", "CMSIS device headers")
    startup_source = _required_file(device_root / "Source" / "Templates" / "gcc" / target.startup_source, "startup file")
    system_source = _required_file(device_root / "Source" / "Templates" / f"system_{family_lower}xx.c", "system source")
    hal_root = _required_dir(sdk_root / "Drivers" / f"{family}xx_HAL_Driver", "HAL driver")
    hal_include = _required_dir(hal_root / "Inc", "HAL headers")
    hal_source_dir = _required_dir(hal_root / "Src", "HAL sources")
    generated_include = project_dir / ".efw_target" / "include"
    local_hal_config = project_dir / "include" / f"{family_lower}xx_hal_conf.h"
    generated_hal_config = generated_include / f"{family_lower}xx_hal_conf.h"
    has_user_board = _has_board_init(project_dir)
    hal_config = local_hal_config if local_hal_config.is_file() else generated_hal_config if not has_user_board else local_hal_config
    if not hal_config.is_file():
        raise STM32SDKError(
            f"目标 {target.chip} 缺少 BSP HAL 配置: {hal_config}；请由 Board Adapter 提供"
        )
    hal_sources = tuple(sorted(
        path for path in hal_source_dir.glob(f"{family_lower}xx_hal*.c")
        if "template" not in path.name.lower()
    ))
    if not hal_sources:
        raise STM32SDKError(f"STM32Cube SDK 没有 HAL C 源文件: {hal_source_dir}")
    generated_board = project_dir / ".efw_target" / "board_adapter.c"
    if not has_user_board and not generated_board.is_file():
        raise STM32SDKError(
            f"目标 {target.chip} 缺少 BSP 入口 app_board_init(void)；请在 Graph board_adapters 中实现"
        )
    if not _main_calls_board_init(project_dir):
        raise STM32SDKError(
            f"目标 {target.chip} 的 main.c 未调用 app_board_init()；请重新执行 project generate"
        )

    generated_dir = project_dir / ".efw_target"
    generated_dir.mkdir(parents=True, exist_ok=True)
    startup = project_dir / target.startup
    linker = project_dir / target.linker
    startup.parent.mkdir(parents=True, exist_ok=True)
    linker.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(startup_source, startup)
    linker.write_text(_linker_script(target), encoding="utf-8")

    include_dirs = [project_dir, project_dir / "include", generated_include, REPO_ROOT / "include", cmsis, device_include, hal_include]
    legacy_include = hal_include / "Legacy"
    if legacy_include.is_dir():
        include_dirs.append(legacy_include)
    sources = (system_source, *hal_sources, REPO_ROOT / "src" / "efw_all.c")
    return STM32BuildResources(
        sdk_root=sdk_root,
        include_dirs=tuple(include_dirs),
        sources=tuple(sources),
        startup=startup,
        linker=linker,
    )
