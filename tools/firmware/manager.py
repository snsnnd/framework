#!/usr/bin/env python3
"""
EFW 固件管理工具

管理嵌入式固件库，支持：
- 从 GitHub 下载固件库
- 管理多个固件版本
- 根据芯片自动选择固件
- 配置头文件和链接库

使用方式：
  # 列出支持的固件
  python3 tools/efw.py firmware list
  
  # 下载固件
  python3 tools/efw.py firmware download stm32f4
  
  # 查看固件信息
  python3 tools/efw.py firmware info stm32f4
  
  # 配置项目使用固件
  python3 tools/efw.py firmware config --chip STM32F407VGT6
  
  # 查看已下载固件
  python3 tools/efw.py firmware installed
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
import tarfile
from pathlib import Path
from typing import Optional
import urllib.request
import urllib.error


# ─── 固件定义 ────────────────────────────────────────────────────────────────

class FirmwareInfo:
    """固件信息"""
    
    def __init__(
        self,
        name: str,
        display_name: str,
        repo_url: str,
        chip_families: list[str],
        version: str = "latest",
        download_url: str = "",
        include_dirs: list[str] = None,
        source_dirs: list[str] = None,
        hal_lib: str = "",
        cmsis_dir: str = "",
        startup_dir: str = "",
        linker_dir: str = "",
    ):
        self.name = name
        self.display_name = display_name
        self.repo_url = repo_url
        self.chip_families = chip_families
        self.version = version
        self.download_url = download_url
        self.include_dirs = include_dirs or []
        self.source_dirs = source_dirs or []
        self.hal_lib = hal_lib
        self.cmsis_dir = cmsis_dir
        self.startup_dir = startup_dir
        self.linker_dir = linker_dir


# 支持的固件列表
FIRMWARES = {
    # ── STM32 系列 ──────────────────────────────────────────────────────
    "stm32f1": FirmwareInfo(
        name="stm32f1",
        display_name="STM32CubeF1 (STM32F1 系列)",
        repo_url="https://github.com/STMicroelectronics/STM32CubeF1",
        chip_families=["STM32F1"],
        download_url="https://github.com/STMicroelectronics/STM32CubeF1/archive/refs/heads/master.zip",
        include_dirs=[
            "Drivers/CMSIS/Include",
            "Drivers/CMSIS/Device/ST/STM32F1xx/Include",
            "Drivers/STM32F1xx_HAL_Driver/Inc",
        ],
        source_dirs=[
            "Drivers/STM32F1xx_HAL_Driver/Src",
        ],
        cmsis_dir="Drivers/CMSIS",
        startup_dir="Drivers/CMSIS/Device/ST/STM32F1xx/Source/Templates/gcc",
        linker_dir="Drivers/CMSIS/Device/ST/STM32F1xx/Source/Templates/gcc",
    ),
    
    "stm32f4": FirmwareInfo(
        name="stm32f4",
        display_name="STM32CubeF4 (STM32F4 系列)",
        repo_url="https://github.com/STMicroelectronics/STM32CubeF4",
        chip_families=["STM32F4"],
        download_url="https://github.com/STMicroelectronics/STM32CubeF4/archive/refs/heads/master.zip",
        include_dirs=[
            "Drivers/CMSIS/Include",
            "Drivers/CMSIS/Device/ST/STM32F4xx/Include",
            "Drivers/STM32F4xx_HAL_Driver/Inc",
        ],
        source_dirs=[
            "Drivers/STM32F4xx_HAL_Driver/Src",
        ],
        cmsis_dir="Drivers/CMSIS",
        startup_dir="Drivers/CMSIS/Device/ST/STM32F4xx/Source/Templates/gcc",
        linker_dir="Drivers/CMSIS/Device/ST/STM32F4xx/Source/Templates/gcc",
    ),
    
    "stm32g4": FirmwareInfo(
        name="stm32g4",
        display_name="STM32CubeG4 (STM32G4 系列)",
        repo_url="https://github.com/STMicroelectronics/STM32CubeG4",
        chip_families=["STM32G4"],
        download_url="https://github.com/STMicroelectronics/STM32CubeG4/archive/refs/heads/master.zip",
        include_dirs=[
            "Drivers/CMSIS/Include",
            "Drivers/CMSIS/Device/ST/STM32G4xx/Include",
            "Drivers/STM32G4xx_HAL_Driver/Inc",
        ],
        source_dirs=[
            "Drivers/STM32G4xx_HAL_Driver/Src",
        ],
        cmsis_dir="Drivers/CMSIS",
        startup_dir="Drivers/CMSIS/Device/ST/STM32G4xx/Source/Templates/gcc",
        linker_dir="Drivers/CMSIS/Device/ST/STM32G4xx/Source/Templates/gcc",
    ),
    
    "stm32h7": FirmwareInfo(
        name="stm32h7",
        display_name="STM32CubeH7 (STM32H7 系列)",
        repo_url="https://github.com/STMicroelectronics/STM32CubeH7",
        chip_families=["STM32H7"],
        download_url="https://github.com/STMicroelectronics/STM32CubeH7/archive/refs/heads/master.zip",
        include_dirs=[
            "Drivers/CMSIS/Include",
            "Drivers/CMSIS/Device/ST/STM32H7xx/Include",
            "Drivers/STM32H7xx_HAL_Driver/Inc",
        ],
        source_dirs=[
            "Drivers/STM32H7xx_HAL_Driver/Src",
        ],
        cmsis_dir="Drivers/CMSIS",
        startup_dir="Drivers/CMSIS/Device/ST/STM32H7xx/Source/Templates/gcc",
        linker_dir="Drivers/CMSIS/Device/ST/STM32H7xx/Source/Templates/gcc",
    ),
    
    # ── ESP 系列 ──────────────────────────────────────────────────────
    "esp-idf": FirmwareInfo(
        name="esp-idf",
        display_name="ESP-IDF (ESP32 系列)",
        repo_url="https://github.com/espressif/esp-idf",
        chip_families=["ESP32", "ESP32-S2", "ESP32-S3", "ESP32-C3", "ESP32-C6"],
        download_url="https://github.com/espressif/esp-idf/archive/refs/heads/master.zip",
        include_dirs=[
            "components/esp_common/include",
            "components/driver/include",
            "components/hal/include",
            "components/soc/include",
        ],
        source_dirs=[
            "components/driver",
            "components/hal",
        ],
    ),
    
    # ── Arduino 系列 ──────────────────────────────────────────────────
    "arduino-avr": FirmwareInfo(
        name="arduino-avr",
        display_name="Arduino AVR Core (Uno, Mega, Nano)",
        repo_url="https://github.com/arduino/ArduinoCore-avr",
        chip_families=["ATmega328P", "ATmega2560", "ATmega32U4"],
        download_url="https://github.com/arduino/ArduinoCore-avr/archive/refs/heads/master.zip",
        include_dirs=[
            "cores/arduino",
            "variants/standard",
        ],
        source_dirs=[
            "cores/arduino",
        ],
    ),
    
    "arduino-samd": FirmwareInfo(
        name="arduino-samd",
        display_name="Arduino SAMD Core (Zero, MKR, Nano 33 IoT)",
        repo_url="https://github.com/arduino/ArduinoCore-samd",
        chip_families=["SAMD21", "SAMD51"],
        download_url="https://github.com/arduino/ArduinoCore-samd/archive/refs/heads/master.zip",
        include_dirs=[
            "cores/arduino",
            "variants/arduino_zero",
        ],
        source_dirs=[
            "cores/arduino",
        ],
    ),
    
    "arduino-mbed": FirmwareInfo(
        name="arduino-mbed",
        display_name="Arduino Mbed Core (Nano RP2040, GIGA, Portenta)",
        repo_url="https://github.com/arduino/ArduinoCore-mbed",
        chip_families=["RP2040", "STM32H7", "NRF52840"],
        download_url="https://github.com/arduino/ArduinoCore-mbed/archive/refs/heads/master.zip",
        include_dirs=[
            "cores/arduino",
            "variants/PORTENTA_H7_M7",
        ],
        source_dirs=[
            "cores/arduino",
        ],
    ),
    
    # ── MSPM0 系列 ────────────────────────────────────────────────────
    "mspm0-sdk": FirmwareInfo(
        name="mspm0-sdk",
        display_name="MSPM0 SDK (TI MSPM0 系列)",
        repo_url="https://github.com/TexasInstruments/mspm0-sdk",
        chip_families=["MSPM0G3507", "MSPM0G3506", "MSPM0L1306", "MSPM0L1305"],
        download_url="https://github.com/TexasInstruments/mspm0-sdk/archive/refs/heads/main.zip",
        include_dirs=[
            "source/ti/devices/msp",
            "source/third_party/CMSIS/Core/Include",
        ],
        source_dirs=[
            "source/ti/driverlib",
        ],
    ),
    
    # ── GD32 系列 (国产 STM32 兼容) ──────────────────────────────────
    "gd32-standard": FirmwareInfo(
        name="gd32-standard",
        display_name="GD32 Standard Peripheral Library",
        repo_url="https://github.com/GigaDevice-Semiconductor/GD32StandardFirmware",
        chip_families=["GD32F103", "GD32F303", "GD32F407", "GD32E103"],
        download_url="https://github.com/GigaDevice-Semiconductor/GD32StandardFirmware/archive/refs/heads/main.zip",
        include_dirs=[
            "GD32F10x_standard_peripheral/Include",
            "CMSIS/Core/Include",
            "CMSIS/GD/GD32F10x/Include",
        ],
        source_dirs=[
            "GD32F10x_standard_peripheral/Source",
        ],
    ),
    
    # ── CH32V 系列 (RISC-V) ──────────────────────────────────────────
    "ch32v-sdk": FirmwareInfo(
        name="ch32v-sdk",
        display_name="CH32V SDK (WCH RISC-V 系列)",
        repo_url="https://github.com/openwch/ch32v003",
        chip_families=["CH32V003", "CH32V103", "CH32V203", "CH32V307"],
        download_url="https://github.com/openwch/ch32v003/archive/refs/heads/main.zip",
        include_dirs=[
            "EVT/EXAM/SRC/Core",
            "EVT/EXAM/SRC/Peripheral/inc",
        ],
        source_dirs=[
            "EVT/EXAM/SRC/Peripheral/src",
        ],
    ),
    
    # ── NXP 系列 ─────────────────────────────────────────────────────
    "nxp-lpc": FirmwareInfo(
        name="nxp-lpc",
        display_name="NXP LPC SDK",
        repo_url="https://github.com/nxp-mcuxpresso/mcux-sdk",
        chip_families=["LPC55S69", "LPC54608"],
        download_url="https://github.com/nxp-mcuxpresso/mcux-sdk/archive/refs/heads/main.zip",
        include_dirs=[
            "devices/LPC55S69",
            "CMSIS/Core/Include",
        ],
        source_dirs=[
            "devices/LPC55S69/drivers",
        ],
    ),
    
    # ── RP2040 系列 ──────────────────────────────────────────────────
    "rp2040": FirmwareInfo(
        name="rp2040",
        display_name="Raspberry Pi Pico SDK (RP2040)",
        repo_url="https://github.com/raspberrypi/pico-sdk",
        chip_families=["RP2040"],
        download_url="https://github.com/raspberrypi/pico-sdk/archive/refs/heads/master.zip",
        include_dirs=[
            "src/common/pico_stdlib/include",
            "src/rp2040/hardware_regs/include",
            "src/rp2040/hardware_structs/include",
        ],
        source_dirs=[
            "src/rp2040",
        ],
    ),
}


# 芯片到固件的映射
CHIP_TO_FIRMWARE = {
    # STM32
    "STM32F1": "stm32f1",
    "STM32F4": "stm32f4",
    "STM32G4": "stm32g4",
    "STM32H7": "stm32h7",
    # ESP
    "ESP32": "esp-idf",
    # Arduino
    "ATMEGA": "arduino-avr",
    "SAMD": "arduino-samd",
    "RP2040": "arduino-mbed",
    # MSPM0
    "MSPM0": "mspm0-sdk",
    # GD32
    "GD32": "gd32-standard",
    # CH32V
    "CH32V": "ch32v-sdk",
    # NXP
    "LPC": "nxp-lpc",
    # RP2040
    "RP2040": "rp2040",
}


# ─── 固件管理器 ──────────────────────────────────────────────────────────────

class FirmwareManager:
    """固件管理器"""
    
    def __init__(self, firmware_dir: Optional[Path] = None):
        self.firmware_dir = firmware_dir or Path.home() / ".efw" / "firmware"
        self.firmware_dir.mkdir(parents=True, exist_ok=True)
        
        self.config_file = self.firmware_dir / "config.json"
        self.config: dict[str, dict] = self._load_config()
    
    def _load_config(self) -> dict:
        """加载配置"""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}
    
    def _save_config(self):
        """保存配置"""
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2)
    
    def list_firmwares(self) -> list[dict]:
        """列出所有支持的固件"""
        result = []
        for name, fw in FIRMWARES.items():
            installed = name in self.config
            
            info = {
                "name": name,
                "display_name": fw.display_name,
                "chip_families": fw.chip_families,
                "repo_url": fw.repo_url,
                "installed": installed,
            }
            
            if installed:
                info["path"] = self.config[name].get("path")
                info["version"] = self.config[name].get("version")
            
            result.append(info)
        
        return result
    
    def get_installed(self) -> list[dict]:
        """获取已安装的固件"""
        result = []
        for name, config in self.config.items():
            path = Path(config.get("path", ""))
            if path.exists():
                result.append({
                    "name": name,
                    "display_name": FIRMWARES.get(name, FirmwareInfo(name, name, "", [])).display_name,
                    "path": str(path),
                    "version": config.get("version"),
                })
        return result
    
    def get_firmware_for_chip(self, chip: str) -> Optional[FirmwareInfo]:
        """根据芯片获取固件"""
        chip_upper = chip.upper()
        
        for prefix, fw_name in CHIP_TO_FIRMWARE.items():
            if chip_upper.startswith(prefix):
                return FIRMWARES.get(fw_name)
        
        return None
    
    def download(self, name: str, url: str = None, local_path: Path = None) -> bool:
        """下载固件
        
        Args:
            name: 固件名称
            url: 自定义下载 URL
            local_path: 本地固件路径
        """
        if name not in FIRMWARES and not url and not local_path:
            print(f"错误: 未知固件 '{name}'")
            print("请指定固件名称或使用 --url/--local 参数")
            return False
        
        fw = FIRMWARES.get(name)
        dest_dir = self.firmware_dir / name
        
        if dest_dir.exists():
            print(f"固件已存在: {dest_dir}")
            print("如需重新下载，请先删除: python3 tools/efw.py firmware remove " + name)
            return True
        
        # 确定下载 URL
        download_url = url
        if not download_url and fw:
            download_url = fw.download_url
        
        print(f"安装固件: {name}")
        if fw:
            print(f"  说明: {fw.display_name}")
        
        # 方式 1: 从本地路径安装
        if local_path:
            print(f"  来源: {local_path}")
            
            if not local_path.exists():
                print(f"错误: 本地路径不存在: {local_path}")
                return False
            
            print("复制中...")
            try:
                if local_path.is_dir():
                    shutil.copytree(local_path, dest_dir)
                else:
                    # 假设是压缩文件
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    if local_path.suffix == ".zip":
                        with zipfile.ZipFile(local_path, "r") as zip_ref:
                            zip_ref.extractall(dest_dir)
                    elif local_path.suffix in {".tar", ".tar.gz", ".tgz", ".tar.xz"}:
                        with tarfile.open(local_path, "r:*") as tar:
                            tar.extractall(dest_dir)
                    else:
                        print(f"错误: 不支持的文件格式: {local_path.suffix}")
                        return False
                
                print("复制完成")
            except Exception as e:
                print(f"复制失败: {e}")
                return False
        
        # 方式 2: 从 URL 下载
        elif download_url:
            print(f"  URL: {download_url}")
            print(f"  目标: {dest_dir}")
            print()
            
            # 下载文件
            download_path = self.firmware_dir / f"{name}.zip"
            
            try:
                print("下载中...")
                urllib.request.urlretrieve(download_url, str(download_path))
                print("下载完成")
            except Exception as e:
                print(f"下载失败: {e}")
                print(f"\n请尝试:")
                print(f"  1. 手动下载: {download_url}")
                print(f"  2. 使用本地安装: python3 tools/efw.py firmware download {name} --local /path/to/firmware")
                return False
            
            # 解压
            print("解压中...")
            try:
                with zipfile.ZipFile(download_path, "r") as zip_ref:
                    # 解压到临时目录
                    temp_dir = self.firmware_dir / f"{name}_temp"
                    zip_ref.extractall(temp_dir)
                    
                    # 移动到目标目录（跳过顶层目录）
                    extracted_dirs = list(temp_dir.iterdir())
                    if len(extracted_dirs) == 1 and extracted_dirs[0].is_dir():
                        extracted_dirs[0].rename(dest_dir)
                        temp_dir.rmdir()
                    else:
                        temp_dir.rename(dest_dir)
                
                # 删除下载文件
                download_path.unlink()
                
                print("解压完成")
            except Exception as e:
                print(f"解压失败: {e}")
                return False
        
        else:
            print("错误: 请指定下载 URL 或本地路径")
            print("用法:")
            print(f"  python3 tools/efw.py firmware download {name} --url https://example.com/firmware.zip")
            print(f"  python3 tools/efw.py firmware download {name} --local /path/to/firmware")
            return False
        
        # 保存配置
        self.config[name] = {
            "path": str(dest_dir),
            "version": fw.version if fw else "custom",
            "download_url": download_url or "",
            "local_path": str(local_path) if local_path else "",
        }
        self._save_config()
        
        print(f"✓ 固件已安装: {dest_dir}")
        return True
    
    def remove(self, name: str) -> bool:
        """删除固件"""
        if name not in self.config:
            print(f"错误: 固件 '{name}' 未安装")
            return False
        
        path = Path(self.config[name].get("path", ""))
        
        if path.exists():
            print(f"删除固件: {path}")
            shutil.rmtree(path)
        
        del self.config[name]
        self._save_config()
        
        print(f"✓ 固件已删除: {name}")
        return True
    
    def get_include_paths(self, name: str) -> list[Path]:
        """获取头文件路径"""
        if name not in self.config:
            return []
        
        base_path = Path(self.config[name]["path"])
        fw = FIRMWARES.get(name)
        
        if not fw:
            return []
        
        return [base_path / d for d in fw.include_dirs if (base_path / d).exists()]
    
    def get_source_files(self, name: str) -> list[Path]:
        """获取源文件"""
        if name not in self.config:
            return []
        
        base_path = Path(self.config[name]["path"])
        fw = FIRMWARES.get(name)
        
        if not fw:
            return []
        
        sources = []
        for src_dir in fw.source_dirs:
            dir_path = base_path / src_dir
            if dir_path.exists():
                sources.extend(dir_path.glob("*.c"))
        
        return sources
    
    def get_startup_file(self, name: str, chip: str) -> Optional[Path]:
        """获取启动文件"""
        if name not in self.config:
            return None
        
        base_path = Path(self.config[name]["path"])
        fw = FIRMWARES.get(name)
        
        if not fw or not fw.startup_dir:
            return None
        
        startup_dir = base_path / fw.startup_dir
        if not startup_dir.exists():
            return None
        
        # 查找匹配的启动文件
        chip_lower = chip.lower()
        for f in startup_dir.glob("*.s"):
            if chip_lower.replace("xx", "") in f.name.lower():
                return f
        
        return None
    
    def get_linker_script(self, name: str, chip: str) -> Optional[Path]:
        """获取链接脚本"""
        if name not in self.config:
            return None
        
        base_path = Path(self.config[name]["path"])
        fw = FIRMWARES.get(name)
        
        if not fw or not fw.linker_dir:
            return None
        
        linker_dir = base_path / fw.linker_dir
        if not linker_dir.exists():
            return None
        
        # 查找匹配的链接脚本
        chip_lower = chip.lower()
        for f in linker_dir.glob("*.ld"):
            if chip_lower.replace("xx", "") in f.name.lower():
                return f
        
        return None
    
    def generate_cmake_config(self, name: str, chip: str) -> str:
        """生成 CMake 配置"""
        if name not in self.config:
            return ""
        
        base_path = Path(self.config[name]["path"])
        fw = FIRMWARES.get(name)
        
        if not fw:
            return ""
        
        # 生成 CMake 片段
        lines = [
            f"# 固件配置: {fw.display_name}",
            f"set(FIRMWARE_ROOT {base_path})",
            "",
            "# 头文件路径",
        ]
        
        for inc_dir in fw.include_dirs:
            lines.append(f"include_directories(${{FIRMWARE_ROOT}}/{inc_dir})")
        
        lines.append("")
        lines.append("# 源文件")
        lines.append("set(FIRMWARE_SOURCES")
        
        for src_dir in fw.source_dirs:
            lines.append(f"    ${{FIRMWARE_ROOT}}/{src_dir}/*.c")
        
        lines.append(")")
        
        return "\n".join(lines)


# ─── CLI 入口 ────────────────────────────────────────────────────────────────

def cmd_firmware(argv: list[str]) -> int:
    """固件管理命令"""
    if not argv:
        print_firmware_help()
        return 0
    
    subcmd = argv[0]
    rest = argv[1:]
    
    if subcmd in {"help", "-h", "--help"}:
        print_firmware_help()
        return 0
    
    manager = FirmwareManager()
    
    if subcmd == "list":
        firmwares = manager.list_firmwares()
        
        print("\n支持的固件:")
        print("=" * 60)
        
        for fw in firmwares:
            status = "✓ 已安装" if fw["installed"] else "✗ 未安装"
            print(f"\n  {fw['display_name']}:")
            print(f"    状态: {status}")
            print(f"    芯片: {', '.join(fw['chip_families'])}")
            print(f"    仓库: {fw['repo_url']}")
            if fw.get("path"):
                print(f"    路径: {fw['path']}")
        
        return 0
    
    elif subcmd == "installed":
        installed = manager.get_installed()
        
        if not installed:
            print("未安装任何固件")
            print("运行: python3 tools/efw.py firmware download stm32f4")
            return 0
        
        print("\n已安装固件:")
        print("-" * 60)
        
        for fw in installed:
            print(f"  {fw['display_name']}:")
            print(f"    路径: {fw['path']}")
            print(f"    版本: {fw.get('version', 'N/A')}")
        
        return 0
    
    elif subcmd == "download":
        name = rest[0] if rest else None
        url = None
        local_path = None
        
        i = 1
        while i < len(rest):
            if rest[i] == "--url" and i + 1 < len(rest):
                url = rest[i + 1]
                i += 2
            elif rest[i] == "--local" and i + 1 < len(rest):
                local_path = Path(rest[i + 1])
                i += 2
            else:
                i += 1
        
        if not name:
            print("错误: 请指定固件名称")
            print("用法:")
            print("  python3 tools/efw.py firmware download stm32f4")
            print("  python3 tools/efw.py firmware download stm32f4 --url https://example.com/firmware.zip")
            print("  python3 tools/efw.py firmware download stm32f4 --local /path/to/firmware")
            return 1
        
        if manager.download(name, url=url, local_path=local_path):
            return 0
        else:
            return 1
    
    elif subcmd == "remove":
        name = rest[0] if rest else None
        
        if not name:
            print("错误: 请指定固件名称")
            return 1
        
        if manager.remove(name):
            return 0
        else:
            return 1
    
    elif subcmd == "info":
        name = rest[0] if rest else None
        
        if not name:
            print("错误: 请指定固件名称")
            return 1
        
        if name not in FIRMWARES:
            print(f"错误: 未知固件 '{name}'")
            return 1
        
        fw = FIRMWARES[name]
        
        print(f"\n固件信息: {fw.display_name}")
        print("=" * 60)
        print(f"  名称: {fw.name}")
        print(f"  仓库: {fw.repo_url}")
        print(f"  芯片: {', '.join(fw.chip_families)}")
        print(f"  下载: {fw.download_url}")
        
        if name in manager.config:
            config = manager.config[name]
            print(f"\n  已安装:")
            print(f"    路径: {config.get('path')}")
            print(f"    版本: {config.get('version')}")
        
        return 0
    
    elif subcmd == "config":
        chip = None
        
        i = 0
        while i < len(rest):
            if rest[i] == "--chip" and i + 1 < len(rest):
                chip = rest[i + 1]
                i += 2
            else:
                i += 1
        
        if not chip:
            print("错误: 请指定芯片 (--chip)")
            return 1
        
        # 查找固件
        fw = manager.get_firmware_for_chip(chip)
        if not fw:
            print(f"错误: 未找到芯片 {chip} 对应的固件")
            return 1
        
        print(f"芯片: {chip}")
        print(f"固件: {fw.display_name}")
        
        # 检查是否已安装
        if fw.name not in manager.config:
            print(f"\n固件未安装，是否下载? (y/N)")
            choice = input().strip().lower()
            if choice == 'y':
                if not manager.download(fw.name):
                    return 1
            else:
                return 0
        
        # 生成配置
        cmake_config = manager.generate_cmake_config(fw.name, chip)
        
        print(f"\nCMake 配置:")
        print("-" * 60)
        print(cmake_config)
        
        # 获取启动文件
        startup = manager.get_startup_file(fw.name, chip)
        if startup:
            print(f"\n启动文件: {startup}")
        
        # 获取链接脚本
        linker = manager.get_linker_script(fw.name, chip)
        if linker:
            print(f"链接脚本: {linker}")
        
        return 0
    
    else:
        print(f"未知子命令: {subcmd}")
        return 1


def print_firmware_help():
    """打印帮助信息"""
    print("""
EFW 固件管理工具

用法: python3 tools/efw.py firmware <subcommand>

子命令:
  list                列出支持的固件
  installed           查看已安装固件
  download <name>     下载固件
  remove <name>       删除固件
  info <name>         查看固件信息
  config --chip CHIP  配置项目使用固件

下载方式:
  # 从默认 GitHub 下载
  python3 tools/efw.py firmware download stm32f4
  
  # 从自定义 URL 下载
  python3 tools/efw.py firmware download stm32f4 --url https://example.com/STM32CubeF4.zip
  
  # 从本地路径安装
  python3 tools/efw.py firmware download stm32f4 --local /path/to/STM32CubeF4
  python3 tools/efw.py firmware download stm32f4 --local D:\\SDK\\STM32CubeF4

示例:
  # 列出固件
  python3 tools/efw.py firmware list
  
  # 下载固件
  python3 tools/efw.py firmware download stm32f4
  
  # 从自定义 URL 下载
  python3 tools/efw.py firmware download stm32f4 --url https://mirrors.example.com/STM32CubeF4.zip
  
  # 从本地目录安装
  python3 tools/efw.py firmware download stm32f4 --local /home/user/STM32CubeF4
  
  # 查看已安装固件
  python3 tools/efw.py firmware installed
  
  # 配置项目
  python3 tools/efw.py firmware config --chip STM32F407VGT6

支持的固件:
  ── STM32 系列 ──
  stm32f1          STM32CubeF1 (STM32F1)
  stm32f4          STM32CubeF4 (STM32F4)
  stm32g4          STM32CubeG4 (STM32G4)
  stm32h7          STM32CubeH7 (STM32H7)
  
  ── ESP 系列 ──
  esp-idf          ESP-IDF (ESP32, ESP32-S2, ESP32-S3, ESP32-C3)
  
  ── Arduino 系列 ──
  arduino-avr      Arduino AVR (Uno, Mega, Nano)
  arduino-samd     Arduino SAMD (Zero, MKR)
  arduino-mbed     Arduino Mbed (RP2040, Portenta)
  
  ── TI 系列 ──
  mspm0-sdk        MSPM0 SDK (MSPM0G3507, MSPM0L1306)
  
  ── 国产芯片 ──
  gd32-standard    GD32 标准库 (GD32F103, GD32F303)
  ch32v-sdk        CH32V SDK (CH32V003, CH32V203)
  
  ── 其他 ──
  nxp-lpc          NXP LPC SDK
  rp2040           Raspberry Pi Pico SDK

固件存储位置:
  ~/.efw/firmware/
""")
