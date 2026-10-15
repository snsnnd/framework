#!/usr/bin/env python3
"""
EFW 编译工具

当前经过端到端验证的编译器：
- ARM GCC (受支持的 STM32 目标)

功能：
- 自动检测已安装的编译器
- 用户自定义编译器路径
- 根据芯片选择编译器
- 编译项目

使用方式：
  # 检测所有编译器
  python3 tools/efw.py build detect
  
  # 查看编译器详情
  python3 tools/efw.py build info
  
  # 设置编译器路径
  python3 tools/efw.py build set --compiler arm-gcc --path /path/to/gcc
  
  # 编译项目
  python3 tools/efw.py build compile --chip STM32F407VGT6
"""

from __future__ import annotations

import json
import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from tools.target import TargetDescriptor, TargetResolutionError, resolve_target

# Windows 注册表（仅在 Windows 上可用）
try:
    import winreg
except ImportError:
    winreg = None


# ─── 编译器定义 ──────────────────────────────────────────────────────────────

class CompilerInfo:
    """编译器信息"""
    
    def __init__(
        self,
        name: str,
        display_name: str,
        chip_families: list[str],
        executable: str,
        common_paths: list[str],
        version_cmd: list[str] = None,
        toolchain_type: str = "gcc",
    ):
        self.name = name
        self.display_name = display_name
        self.chip_families = chip_families
        self.executable = executable
        self.common_paths = common_paths
        self.version_cmd = version_cmd or [executable, "--version"]
        self.toolchain_type = toolchain_type
        
        # 检测到的路径
        self.found_path: Optional[Path] = None
        self.version: Optional[str] = None


# Only adapters with an authoritative target, SDK resolver, and real build
# verification are exposed through public toolchain APIs.
SUPPORTED_COMPILERS = frozenset({"arm-gcc"})

# 编译器元数据列表
COMPILERS = {
    "arm-gcc": CompilerInfo(
        name="arm-gcc",
        display_name="ARM GCC (arm-none-eabi-gcc)",
        chip_families=["STM32F1", "STM32F4", "STM32G4"],
        executable="arm-none-eabi-gcc",
        common_paths=[
            # WSL 访问 Windows 路径
            "/mnt/c/Program Files/GNU Arm Embedded Toolchain/*/bin",
            "/mnt/c/Program Files (x86)/GNU Arm Embedded Toolchain/*/bin",
            "/mnt/c/Program Files/ARM GNU Toolchain arm-none-eabi/*/bin",
            "/mnt/c/Keil_v5/ARM/ARMCC/bin",
            "/mnt/c/Keil_v5/ARM/ARMCLANG/bin",
            "/mnt/c/ST/STM32CubeIDE_*/plugins/com.st.tools.mcu.productdb.debug.armcu_*/tools/gnu/arm/*/bin",
            # Windows 原生路径
            "C:/Program Files/GNU Arm Embedded Toolchain/*/bin",
            "C:/Program Files (x86)/GNU Arm Embedded Toolchain/*/bin",
            "C:/Program Files/ARM GNU Toolchain arm-none-eabi/*/bin",
            "C:/Keil_v5/ARM/ARMCC/bin",
            "C:/Keil_v5/ARM/ARMCLANG/bin",
            # Linux 原生
            "/usr/bin",
            "/usr/local/bin",
            "~/.local/bin",
            # macOS
            "/opt/homebrew/bin",
            # 手动安装
            "~/.efw/toolchain/*/bin",
        ],
        version_cmd=["arm-none-eabi-gcc", "--version"],
    ),
    
    "arm-compiler": CompilerInfo(
        name="arm-compiler",
        display_name="ARM Compiler (Keil MDK)",
        chip_families=["STM32F0", "STM32F1", "STM32F2", "STM32F3", "STM32F4", 
                       "STM32F7", "STM32G0", "STM32G4", "STM32H7", "STM32L0", 
                       "STM32L1", "STM32L4", "STM32L5", "STM32U5", "STM32WB"],
        executable="armcc.exe",
        common_paths=[
            # WSL 访问 Windows 路径
            "/mnt/c/Keil_v5/ARM/ARMCC/bin",
            "/mnt/c/Keil_v5/ARM/ARMCLANG/bin",
            # Windows 原生路径
            "C:/Keil_v5/ARM/ARMCC/bin",
            "C:/Keil_v5/ARM/ARMCLANG/bin",
        ],
        version_cmd=["armcc", "--version"],
        toolchain_type="armcc",
    ),
    
    "riscv-gcc": CompilerInfo(
        name="riscv-gcc",
        display_name="RISC-V GCC",
        chip_families=["GD32VF103", "ESP32-C3", "CH32V", "BL602"],
        executable="riscv32-unknown-elf-gcc",
        common_paths=[
            # WSL 路径
            "/mnt/c/**/riscv*/bin",
            "/mnt/c/**/RISC-V*/bin",
            # Linux 原生
            "/usr/bin",
            "/usr/local/bin",
            "~/.local/bin",
            # 常见安装路径
            "/opt/riscv/bin",
            "~/.riscv/bin",
            # Nuclei RISC-V
            "/opt/nuclei/*/bin",
            # MounRiver Studio
            "/mnt/c/**/MounRiver*/toolchain/*/bin",
        ],
        version_cmd=["riscv32-unknown-elf-gcc", "--version"],
    ),
    
    "riscv-gcc-alt": CompilerInfo(
        name="riscv-gcc-alt",
        display_name="RISC-V GCC (备选名称)",
        chip_families=["GD32VF103", "ESP32-C3", "CH32V", "BL602"],
        executable="riscv-none-embed-gcc",
        common_paths=[
            "/usr/bin",
            "/usr/local/bin",
            "/opt/**/riscv*/bin",
        ],
        version_cmd=["riscv-none-embed-gcc", "--version"],
    ),
    
    "iar": CompilerInfo(
        name="iar",
        display_name="IAR Embedded Workbench",
        chip_families=["STM32F0", "STM32F1", "STM32F2", "STM32F3", "STM32F4", 
                       "STM32F7", "STM32G0", "STM32G4", "STM32H7", "STM32L0", 
                       "STM32L1", "STM32L4", "STM32L5", "STM32U5", "STM32WB"],
        executable="iccarm.exe",
        common_paths=[
            "C:/Program Files (x86)/IAR Systems/Embedded Workbench */arm/bin",
            "C:/Program Files/IAR Systems/Embedded Workbench */arm/bin",
        ],
        version_cmd=["iccarm", "--version"],
        toolchain_type="iar",
    ),
    
    "esp-idf": CompilerInfo(
        name="esp-idf",
        display_name="ESP-IDF GCC (Xtensa)",
        chip_families=["ESP32", "ESP32-S2", "ESP32-S3", "ESP32-C3"],
        executable="xtensa-esp32-elf-gcc",
        common_paths=[
            # Windows
            "%USERPROFILE%/.espressif/tools/xtensa-esp32-elf/*/xtensa-esp32-elf/bin",
            "C:/Espressif/tools/xtensa-esp32-elf/*/xtensa-esp32-elf/bin",
            # Linux/macOS
            "~/.espressif/tools/xtensa-esp32-elf/*/xtensa-esp32-elf/bin",
        ],
        version_cmd=["xtensa-esp32-elf-gcc", "--version"],
    ),
    
    "ti-arm-clang": CompilerInfo(
        name="ti-arm-clang",
        display_name="TI ARM Clang (MSPM0)",
        chip_families=["MSPM0G3507", "MSPM0L1306"],
        executable="tiarmclang",
        common_paths=[
            "C:/ti/ccs*/ccs/tools/compiler/ti-cgt-armllvm_*/bin",
        ],
        version_cmd=["tiarmclang", "--version"],
        toolchain_type="ti",
    ),
}


# 芯片到编译器的映射
CHIP_TO_COMPILER = {
    # STM32 系列
    "STM32F103": "arm-gcc",
    "STM32F407": "arm-gcc",
    "STM32F411": "arm-gcc",
    "STM32F446": "arm-gcc",
    "STM32G431": "arm-gcc",
    # ESP32 系列
    "ESP32": "esp-idf",
    "ESP32-S3": "esp-idf",
    "ESP32-C3": "esp-idf",
    # MSPM0 系列
    "MSPM0G3507": "ti-arm-clang",
    "MSPM0L1306": "ti-arm-clang",
}


# ─── 编译器管理器 ────────────────────────────────────────────────────────────

class CompilerManager:
    """编译器管理器"""
    
    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or Path.home() / ".efw"
        self.config_file = self.config_dir / "compilers.json"
        self.system = platform.system()
        
        # 用户配置
        self.user_config: dict[str, str] = {}
        
        # 检测到的编译器
        self.detected: dict[str, CompilerInfo] = {}
        
        # 加载配置
        self._load_config()
    
    def _load_config(self):
        """加载用户配置"""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    self.user_config = json.load(f)
            except Exception:
                self.user_config = {}
    
    def _save_config(self):
        """保存用户配置"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self.user_config, f, indent=2)
    
    def detect_all(self) -> dict[str, CompilerInfo]:
        """检测所有编译器"""
        self.detected = {}
        
        for name, compiler in COMPILERS.items():
            if name not in SUPPORTED_COMPILERS:
                continue
            # 1. 检查用户配置
            if name in self.user_config:
                path = Path(self.user_config[name])
                if path.exists():
                    compiler.found_path = path
                    compiler.version = self._get_version(compiler)
                    self.detected[name] = compiler
                    continue
            
            # 2. 检查 PATH
            found = shutil.which(compiler.executable)
            if found:
                compiler.found_path = Path(found).parent
                compiler.version = self._get_version(compiler)
                self.detected[name] = compiler
                continue
            
            # 3. 检查常见路径（支持 glob 模式）
            for pattern in compiler.common_paths:
                # 展开 ~ 和环境变量
                expanded = pattern.replace("~", str(Path.home()))
                expanded = os.path.expandvars(expanded)
                
                # 处理 WSL 路径
                if expanded.startswith("/mnt/c/") and self.system != "Linux":
                    continue  # 非 WSL 环境跳过
                
                # 使用 glob 匹配
                try:
                    for path in Path(expanded).parent.glob(Path(expanded).name):
                        if path.is_dir():
                            exe = path / compiler.executable
                            if exe.exists():
                                compiler.found_path = path
                                compiler.version = self._get_version(compiler)
                                self.detected[name] = compiler
                                break
                            
                            # Windows 下检查 .exe
                            if self.system == "Windows":
                                exe = exe.with_suffix(".exe")
                                if exe.exists():
                                    compiler.found_path = path
                                    compiler.version = self._get_version(compiler)
                                    self.detected[name] = compiler
                                    break
                except (OSError, ValueError):
                    pass
                
                if name in self.detected:
                    break
        
        return self.detected
    
    def _get_version(self, compiler: CompilerInfo) -> Optional[str]:
        """获取编译器版本"""
        try:
            cmd = compiler.version_cmd.copy()
            if compiler.found_path:
                exe = compiler.found_path / compiler.executable
                if exe.exists():
                    cmd[0] = str(exe)
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                first_line = result.stdout.split("\n")[0].strip()
                return first_line
        except Exception:
            pass
        return None
    
    def get_compiler_for_chip(self, chip: str) -> Optional[CompilerInfo]:
        """根据芯片获取推荐的编译器"""
        try:
            compiler_name = resolve_target(chip=chip).toolchain
        except TargetResolutionError:
            return None
        
        # 检查是否已检测到
        if compiler_name in self.detected:
            return self.detected[compiler_name]
        
        # 尝试检测
        if compiler_name in COMPILERS:
            compiler = COMPILERS[compiler_name]
            
            # 检查用户配置
            if compiler_name in self.user_config:
                path = Path(self.user_config[compiler_name])
                if path.exists():
                    compiler.found_path = path
                    compiler.version = self._get_version(compiler)
                    return compiler
            
            # 检查 PATH
            found = shutil.which(compiler.executable)
            if found:
                compiler.found_path = Path(found).parent
                compiler.version = self._get_version(compiler)
                return compiler
        
        return None

    def get_compiler(self, name: str) -> Optional[CompilerInfo]:
        """Get a configured compiler by target descriptor name."""
        if name not in SUPPORTED_COMPILERS or name not in COMPILERS:
            return None
        if name in self.detected:
            return self.detected[name]

        compiler = COMPILERS[name]
        if name in self.user_config:
            path = Path(self.user_config[name])
            if path.exists():
                compiler.found_path = path
                compiler.version = self._get_version(compiler)
                return compiler

        found = shutil.which(compiler.executable)
        if found:
            compiler.found_path = Path(found).parent
            compiler.version = self._get_version(compiler)
            return compiler
        return None
    
    def set_compiler_path(self, name: str, path: Path) -> bool:
        """设置编译器路径"""
        if name not in SUPPORTED_COMPILERS or name not in COMPILERS:
            print(f"错误: 编译器 '{name}' 尚无经过验证的端到端构建支持")
            return False
        
        if not path.exists():
            print(f"错误: 路径不存在: {path}")
            return False
        
        # 验证编译器
        compiler = COMPILERS[name]
        exe = path / compiler.executable
        if not exe.exists():
            # 检查 .exe 后缀
            exe = exe.with_suffix(".exe")
            if not exe.exists():
                print(f"错误: 找不到编译器: {compiler.executable}")
                return False
        
        # 保存配置
        self.user_config[name] = str(path)
        self._save_config()
        
        # 更新检测结果
        compiler.found_path = path
        compiler.version = self._get_version(compiler)
        self.detected[name] = compiler
        
        print(f"✓ 已设置 {compiler.display_name}: {path}")
        return True
    
    def list_compilers(self) -> list[dict]:
        """列出所有编译器"""
        # 先执行检测
        if not self.detected:
            self.detect_all()
        
        result = []
        for name, compiler in COMPILERS.items():
            if name not in SUPPORTED_COMPILERS:
                continue
            info = {
                "name": name,
                "display_name": compiler.display_name,
                "chip_families": compiler.chip_families,
                "toolchain_type": compiler.toolchain_type,
            }
            
            if name in self.detected:
                detected = self.detected[name]
                info["status"] = "已安装"
                info["path"] = str(detected.found_path)
                info["version"] = detected.version
            else:
                info["status"] = "未检测到"
                info["path"] = None
                info["version"] = None
            
            result.append(info)
        
        return result
    
    def get_config(self) -> dict:
        """获取当前配置"""
        return {
            "compilers": self.list_compilers(),
            "user_config": {name: path for name, path in self.user_config.items() if name in SUPPORTED_COMPILERS},
        }


# ─── 编译器适配器 ────────────────────────────────────────────────────────────

class CompilerAdapter:
    """编译器适配器基类"""
    
    def __init__(self, compiler: CompilerInfo, chip: str):
        self.compiler = compiler
        self.chip = chip
    
    def get_compile_command(self, sources: list[str], output: str, **kwargs) -> list[str]:
        """获取编译命令"""
        raise NotImplementedError
    
    def get_link_command(self, objects: list[str], output: str, **kwargs) -> list[str]:
        """获取链接命令"""
        raise NotImplementedError


class ARMGCCAdapter(CompilerAdapter):
    """ARM GCC 适配器"""
    
    def get_compile_command(self, sources: list[str], output: str, **kwargs) -> list[str]:
        cmd = [
            str(self.compiler.found_path / "arm-none-eabi-gcc"),
            "-c",
            *kwargs.get("cpu_flags", ["-mcpu=cortex-m4", "-mthumb"]),
            "-Wall",
            "-fdata-sections",
            "-ffunction-sections",
        ]
        
        # 添加头文件路径
        for inc in kwargs.get("includes", []):
            cmd.extend(["-I", inc])
        
        # 添加定义
        for define in kwargs.get("defines", []):
            cmd.extend(["-D", define])
        
        # 添加源文件
        cmd.extend(sources)
        
        # 输出文件
        cmd.extend(["-o", output])
        
        return cmd
    
    def get_link_command(self, objects: list[str], output: str, **kwargs) -> list[str]:
        cmd = [
            str(self.compiler.found_path / "arm-none-eabi-gcc"),
            *kwargs.get("cpu_flags", ["-mcpu=cortex-m4", "-mthumb"]),
            "-specs=nosys.specs",
            "-specs=nano.specs",
            "-Wl,--gc-sections",
        ]
        
        # 添加链接脚本
        if "linker_script" in kwargs:
            cmd.extend(["-T", kwargs["linker_script"]])
        
        # 添加对象文件
        cmd.extend(objects)
        
        # 输出文件
        cmd.extend(["-o", output])
        
        # 链接库
        cmd.extend(["-lm", "-lc", "-lgcc"])
        
        return cmd


def get_adapter(compiler: CompilerInfo, chip: str) -> CompilerAdapter:
    """获取编译器适配器"""
    target = resolve_target(chip=chip)
    if compiler.name != "arm-gcc" or target.toolchain != "arm-gcc" or target.platform != "stm32":
        raise ValueError(f"目标 {chip} 没有经过验证的编译器适配器: {compiler.name}")
    return ARMGCCAdapter(compiler, target.chip)


# ─── 项目编译器 ──────────────────────────────────────────────────────────────

class ProjectCompiler:
    """项目编译器"""
    
    def __init__(self, project_dir: Path, build_dir: Optional[Path] = None, firmware_manager=None, board_profile: str | None = None):
        self.project_dir = project_dir
        self.build_dir = build_dir or project_dir / "build"
        self.compiler_manager = CompilerManager()
        self.firmware_manager = firmware_manager
        self.board_profile = board_profile
    
    def compile(self, chip: str, sources: list[str] = None, **kwargs) -> bool:
        """编译项目"""
        try:
            target: TargetDescriptor = resolve_target(chip=chip)
        except TargetResolutionError as exc:
            print(f"错误: {exc}")
            return False
        print(f"编译项目: {target.chip}")

        try:
            has_user_board = any(
                re.search(r"\befw_status_t\s+app_board_init\s*\(\s*void\s*\)\s*\{", path.read_text(encoding="utf-8", errors="ignore"))
                for path in self.project_dir.rglob("*.c") if ".efw_target" not in path.parts and "build" not in path.parts
            )
            if self.board_profile and not has_user_board:
                from tools.board.stm32_bsp import generate_stm32_bsp
                generate_stm32_bsp(self.project_dir, target, self.board_profile)
            from tools.firmware.stm32 import prepare_stm32_build
            resources = prepare_stm32_build(self.project_dir, target, self.firmware_manager)
        except ValueError as exc:
            print(f"错误: {exc}")
            return False
        
        # 检测编译器
        compiler = self.compiler_manager.get_compiler(target.toolchain)
        if not compiler:
            print("错误: 未找到合适的编译器")
            print("请运行: python3 tools/efw.py build detect")
            return False
        
        print(f"使用编译器: {compiler.display_name}")
        print(f"路径: {compiler.found_path}")
        
        # 获取适配器
        adapter = get_adapter(compiler, target.chip)
        
        # 创建构建目录
        self.build_dir.mkdir(parents=True, exist_ok=True)
        obj_dir = self.build_dir / "obj"
        obj_dir.mkdir(exist_ok=True)
        
        # 查找源文件
        if sources is None:
            sources = [
                path for path in self.project_dir.rglob("*.c")
                if "build" not in path.parts and ".efw_target" not in path.parts and ".efw_backup" not in path.parts
            ]
        generated_board = self.project_dir / ".efw_target" / "board_adapter.c"
        if generated_board.is_file() and not has_user_board and generated_board not in {Path(source) for source in sources}:
            sources.append(generated_board)
        sources = [*sources, *resources.sources, resources.startup]
        
        if not sources:
            print("错误: 未找到源文件")
            return False
        
        print(f"源文件: {len(sources)} 个")
        
        # 编译每个源文件
        objects = []
        for source in sources:
            src = Path(source)
            try:
                relative = src.resolve().relative_to(self.project_dir.resolve())
                obj = obj_dir / relative.with_suffix(".o")
            except ValueError:
                digest = hashlib.sha256(str(src.resolve()).encode()).hexdigest()[:12]
                obj = obj_dir / digest / src.with_suffix(".o").name
            obj.parent.mkdir(parents=True, exist_ok=True)
            objects.append(str(obj))
            
            cmd = adapter.get_compile_command(
                [str(src)],
                str(obj),
                includes=[str(path) for path in resources.include_dirs],
                defines=[*target.defines, *kwargs.get("defines", [])],
                cpu_flags=list(target.cpu_flags),
            )
            
            print(f"编译: {src.name}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"编译失败: {src.name}")
                print(result.stderr)
                return False
        
        # 链接
        output = self.build_dir / "app.elf"
        cmd = adapter.get_link_command(
            objects,
            str(output),
            linker_script=str(resources.linker),
            cpu_flags=list(target.cpu_flags),
        )
        
        print("链接...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print("链接失败")
            print(result.stderr)
            return False
        if not output.is_file():
            print(f"链接失败: 未生成产物 {output}")
            return False
        
        print(f"✓ 编译成功: {output}")
        
        # 生成 .bin 和 .hex
        if not self._generate_bin(output, compiler):
            return False
        
        return True
    
    def _generate_bin(self, elf_file: Path, compiler: CompilerInfo) -> bool:
        """生成 .bin 和 .hex 文件"""
        bin_file = elf_file.with_suffix(".bin")
        hex_file = elf_file.with_suffix(".hex")
        
        # 生成 .bin
        cmd = [str(compiler.found_path / "arm-none-eabi-objcopy"), "-O", "binary", str(elf_file), str(bin_file)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print("生成 .bin 失败")
            print(result.stderr)
            return False
        if not bin_file.is_file():
            print(f"生成 .bin 失败: 未生成产物 {bin_file}")
            return False
        
        # 生成 .hex
        cmd = [str(compiler.found_path / "arm-none-eabi-objcopy"), "-O", "ihex", str(elf_file), str(hex_file)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print("生成 .hex 失败")
            print(result.stderr)
            return False
        if not hex_file.is_file():
            print(f"生成 .hex 失败: 未生成产物 {hex_file}")
            return False
        
        # 显示大小
        size_cmd = [str(compiler.found_path / "arm-none-eabi-size"), str(elf_file)]
        result = subprocess.run(size_cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"\n固件大小:")
            print(result.stdout)
        return True


# ─── CLI 入口 ────────────────────────────────────────────────────────────────

def cmd_build(argv: list[str]) -> int:
    """编译工具命令"""
    if not argv:
        print_build_help()
        return 0
    
    subcmd = argv[0]
    rest = argv[1:]
    
    if subcmd in {"help", "-h", "--help"}:
        print_build_help()
        return 0
    
    manager = CompilerManager()
    
    if subcmd == "detect":
        print("检测编译器...")
        print("-" * 60)
        
        detected = manager.detect_all()
        
        if not detected:
            print("未检测到任何编译器")
            print("\n请安装:")
            print("  - ARM GCC: https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads")
            return 1
        
        print(f"检测到 {len(detected)} 个编译器:")
        for name, compiler in detected.items():
            print(f"\n  {compiler.display_name}:")
            print(f"    路径: {compiler.found_path}")
            print(f"    版本: {compiler.version}")
        
        return 0
    
    elif subcmd == "info":
        configs = manager.list_compilers()
        
        print("\n编译器列表:")
        print("=" * 70)
        
        for config in configs:
            print(f"\n{config['display_name']}:")
            print(f"  状态: {config['status']}")
            if config['path']:
                print(f"  路径: {config['path']}")
            if config['version']:
                print(f"  版本: {config['version']}")
            print(f"  支持芯片: {', '.join(config['chip_families'][:5])}...")
        
        return 0
    
    elif subcmd == "set":
        compiler_name = None
        path = None
        
        i = 0
        while i < len(rest):
            if rest[i] == "--compiler" and i + 1 < len(rest):
                compiler_name = rest[i + 1]
                i += 2
            elif rest[i] == "--path" and i + 1 < len(rest):
                path = Path(rest[i + 1])
                i += 2
            else:
                i += 1
        
        if not compiler_name or not path:
            print("错误: 请指定编译器和路径")
            print("用法: python3 tools/efw.py build set --compiler arm-gcc --path /path/to/compiler")
            return 1
        
        return 0 if manager.set_compiler_path(compiler_name, path) else 1
    
    elif subcmd == "unset":
        compiler_name = None
        
        i = 0
        while i < len(rest):
            if rest[i] == "--compiler" and i + 1 < len(rest):
                compiler_name = rest[i + 1]
                i += 2
            else:
                i += 1
        
        if not compiler_name:
            print("错误: 请指定编译器")
            print("用法: python3 tools/efw.py build unset --compiler arm-gcc")
            return 1
        
        if compiler_name in manager.user_config:
            del manager.user_config[compiler_name]
            manager._save_config()
            print(f"✓ 已删除 {compiler_name} 配置")
        else:
            print(f"未找到 {compiler_name} 的配置")
        
        return 0
    
    elif subcmd == "config":
        configs = manager.get_config()
        print(json.dumps(configs, indent=2, ensure_ascii=False))
        return 0
    
    elif subcmd == "find":
        # 查找特定可执行文件
        exe_name = rest[0] if rest else None
        
        if not exe_name:
            print("错误: 请指定要查找的可执行文件")
            print("用法: python3 tools/efw.py build find <executable>")
            print("示例: python3 tools/efw.py build find arm-none-eabi-gcc")
            return 1
        
        print(f"查找: {exe_name}")
        print("-" * 60)
        
        # 检查 PATH
        found = shutil.which(exe_name)
        if found:
            print(f"在 PATH 中找到: {found}")
        
        # 检查常见路径
        search_paths = [
            "/usr/bin",
            "/usr/local/bin",
            "~/.local/bin",
            "/opt/homebrew/bin",
            "~/.efw/toolchain/*/bin",
            # WSL 访问 Windows
            "/mnt/c/Keil_v5/ARM/*/bin",
            "/mnt/c/Program Files/*/bin",
            "/mnt/c/Program Files (x86)/*/bin",
        ]
        
        found_any = False
        for pattern in search_paths:
            expanded = pattern.replace("~", str(Path.home()))
            try:
                for path in Path(expanded).parent.glob(Path(expanded).name):
                    if path.is_dir():
                        exe = path / exe_name
                        if exe.exists():
                            print(f"找到: {exe}")
                            found_any = True
                        # 检查 .exe
                        exe = exe.with_suffix(".exe")
                        if exe.exists():
                            print(f"找到: {exe}")
                            found_any = True
            except (OSError, ValueError):
                pass
        
        if not found and not found_any:
            print(f"未找到 {exe_name}")
            print(f"\n请确保已安装对应的编译器，并添加到 PATH 或使用 set 命令设置路径")
        
        return 0
    
    elif subcmd == "compile":
        chip = None
        project_dir = Path(".")
        
        i = 0
        while i < len(rest):
            if rest[i] == "--chip" and i + 1 < len(rest):
                chip = rest[i + 1]
                i += 2
            elif rest[i] == "--dir" and i + 1 < len(rest):
                project_dir = Path(rest[i + 1])
                i += 2
            else:
                i += 1
        
        if not chip:
            print("错误: 请指定芯片 (--chip)")
            return 1
        
        compiler = ProjectCompiler(project_dir)
        return 0 if compiler.compile(chip) else 1
    
    elif subcmd == "init":
        chip = rest[0] if rest else "STM32F407VGT6"
        project_dir = Path(".")
        
        print(f"初始化项目: {chip}")
        
        # 创建目录
        Path("src").mkdir(exist_ok=True)
        Path("include").mkdir(exist_ok=True)
        
        # 生成 main.c
        main_c = f"""/**
 * @file    main.c
 * @brief   主程序
 * @chip    {chip}
 */

#include "efw/efw.h"

int main(void)
{{
    efw_init();
    
    while (1)
    {{
        // 主循环
    }}
    
    return 0;
}}
"""
        Path("src/main.c").write_text(main_c)
        
        print(f"✓ 项目已初始化")
        print(f"  下一步: python3 tools/efw.py build detect")
        print(f"  然后: python3 tools/efw.py build compile --chip {chip}")
        
        return 0
    
    else:
        print(f"未知子命令: {subcmd}")
        return 1


def print_build_help():
    """打印帮助信息"""
    print("""
EFW 编译工具

用法: python3 tools/efw.py build <subcommand>

子命令:
  detect              检测已安装的编译器
  info                显示所有编译器信息
  find <executable>   查找特定编译器
  set                 设置编译器路径（自动保存）
  unset               删除编译器配置
  config              显示当前配置
  init [chip]         初始化项目
  compile --chip      编译项目

示例:
  # 检测编译器
  python3 tools/efw.py build detect
  
  # 查看编译器信息
  python3 tools/efw.py build info
  
  # 查找特定编译器
  python3 tools/efw.py build find arm-none-eabi-gcc
  
  # 设置编译器路径（会自动保存到 ~/.efw/compilers.json）
  python3 tools/efw.py build set --compiler arm-gcc --path "/opt/arm-gnu-toolchain/bin"
  
  # 删除编译器配置
  python3 tools/efw.py build unset --compiler arm-gcc
  
  # 查看当前配置
  python3 tools/efw.py build config
  
  # 初始化项目
  python3 tools/efw.py build init STM32F407VGT6
  
  # 编译项目
  python3 tools/efw.py build compile --chip STM32F407VGT6

经过验证的端到端编译器:
  arm-gcc           ARM GCC (受支持的 STM32 目标)

配置文件位置:
  ~/.efw/compilers.json
""")
