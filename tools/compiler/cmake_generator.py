"""
CMake 配置生成器

根据芯片和固件库自动生成 CMake 配置。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional


class CMakeGenerator:
    """CMake 配置生成器"""
    
    def __init__(self, project_dir: Path, firmware_root: Optional[Path] = None):
        self.project_dir = project_dir
        self.firmware_root = firmware_root
    
    def generate(
        self,
        chip: str,
        sources: list[str] = None,
        includes: list[str] = None,
        defines: list[str] = None,
    ) -> str:
        """生成 CMakeLists.txt"""
        
        # 解析芯片信息
        chip_info = self._parse_chip(chip)
        
        # 生成内容
        content = f"""cmake_minimum_required(VERSION 3.15)
project(efw_app C ASM)

set(CMAKE_C_STANDARD 99)

# ====================================================================
# 芯片配置
# ====================================================================

set(CHIP_FAMILY "{chip_info['family']}")
set(CHIP_DEVICE "{chip_info['device']}")
set(CPU_TYPE "{chip_info['cpu']}")

# CPU 标志
if(CPU_TYPE STREQUAL "cortex-m4")
    set(CPU_FLAGS "-mcpu=cortex-m4 -mthumb -mfloat-abi=hard -mfpu=fpv4-sp-d16")
elseif(CPU_TYPE STREQUAL "cortex-m3")
    set(CPU_FLAGS "-mcpu=cortex-m3 -mthumb")
elseif(CPU_TYPE STREQUAL "cortex-m0")
    set(CPU_FLAGS "-mcpu=cortex-m0 -mthumb")
else()
    set(CPU_FLAGS "-mcpu=cortex-m4 -mthumb")
endif()

# ====================================================================
# 固件库配置
# ====================================================================

"""
        
        # 添加固件库配置
        if self.firmware_root:
            content += self._generate_firmware_config(chip_info)
        
        # 添加 EFW 框架配置
        content += self._generate_efw_config()
        
        # 添加应用源文件
        content += self._generate_app_config(sources, includes, defines)
        
        # 添加编译和链接选项
        content += self._generate_compile_options(chip_info)
        
        # 添加构建目标
        content += self._generate_build_targets(chip_info)
        
        return content
    
    def _parse_chip(self, chip: str) -> dict[str, str]:
        """解析芯片名称"""
        chip_upper = chip.upper()
        
        # 默认值
        info = {
            "family": "STM32F4",
            "device": "STM32F407xx",
            "cpu": "cortex-m4",
            "flash_size": "1024K",
            "ram_size": "192K",
        }
        
        # 解析系列
        if "F103" in chip_upper:
            info.update(family="STM32F1", device="STM32F103xB", cpu="cortex-m3",
                       flash_size="128K", ram_size="20K")
        elif "F407" in chip_upper:
            info.update(family="STM32F4", device="STM32F407xx", cpu="cortex-m4",
                       flash_size="1024K", ram_size="192K")
        elif "F411" in chip_upper:
            info.update(family="STM32F4", device="STM32F411xE", cpu="cortex-m4",
                       flash_size="512K", ram_size="128K")
        elif "F446" in chip_upper:
            info.update(family="STM32F4", device="STM32F446xx", cpu="cortex-m4",
                       flash_size="512K", ram_size="128K")
        elif "G431" in chip_upper:
            info.update(family="STM32G4", device="STM32G431xx", cpu="cortex-m4",
                       flash_size="128K", ram_size="32K")
        elif "H743" in chip_upper:
            info.update(family="STM32H7", device="STM32H743xx", cpu="cortex-m7",
                       flash_size="2048K", ram_size="1024K")
        
        return info
    
    def _generate_firmware_config(self, chip_info: dict) -> str:
        """生成固件库配置"""
        family = chip_info["family"].lower()
        
        # 根据系列确定 HAL 目录名
        hal_dir_name = f"{chip_info['family']}xx_HAL_Driver"
        device_dir_name = f"{chip_info['family']}xx"
        
        return f"""# 固件库路径
set(FIRMWARE_ROOT "{self.firmware_root}")

# CMSIS
set(CMSIS_DIR "${{FIRMWARE_ROOT}}/Drivers/CMSIS")
include_directories(${{CMSIS_DIR}}/Include)
include_directories(${{CMSIS_DIR}}/Device/ST/{device_dir_name}/Include)

# HAL 库
set(HAL_DIR "${{FIRMWARE_ROOT}}/Drivers/{hal_dir_name}")
include_directories(${{HAL_DIR}}/Inc)

        # HAL 源文件（排除模板文件）
        file(GLOB HAL_SOURCES_ALL ${{HAL_DIR}}/Src/*.c)
        set(HAL_SOURCES "")
        foreach(src ${{HAL_SOURCES_ALL}})
            if(NOT src MATCHES "template")
                list(APPEND HAL_SOURCES ${{src}})
            endif()
        endforeach()

# 启动文件
set(STARTUP_FILE "${{CMSIS_DIR}}/Device/ST/{device_dir_name}/Source/Templates/gcc/startup_{chip_info['device'].lower().replace('xx', '')}.s")

# 链接脚本
set(LINKER_SCRIPT "${{CMSIS_DIR}}/Device/ST/{device_dir_name}/Source/Templates/gcc/{chip_info['device'].lower().replace('xx', '')}_FLASH.ld")

# 芯片定义
add_definitions(-D{chip_info['device']} -DUSE_HAL_DRIVER -DUSE_STM32_HAL)

"""
    
    def _generate_efw_config(self) -> str:
        """生成 EFW 框架配置"""
        # 使用绝对路径指向 EFW 框架
        efw_root = Path(__file__).parent.parent.absolute()
        
        return f"""# ====================================================================
# EFW 框架配置
# ====================================================================

set(EFW_ROOT {efw_root})
include_directories(${{EFW_ROOT}}/include)

# EFW 源文件（排除平台特定文件）
file(GLOB_RECURSE EFW_SOURCES_ALL
    ${{EFW_ROOT}}/src/core/*.c
    ${{EFW_ROOT}}/src/hal/*.c
    ${{EFW_ROOT}}/src/comm/*.c
    ${{EFW_ROOT}}/src/device/*.c
    ${{EFW_ROOT}}/src/algorithm/*.c
    ${{EFW_ROOT}}/src/module/*.c
    ${{EFW_ROOT}}/src/state/*.c
)

# 排除平台特定文件（由 hal_adapter.c 替代）
set(EFW_SOURCES "")
foreach(src ${{EFW_SOURCES_ALL}})
    if(NOT src MATCHES "hal_adapter_stm32" AND NOT src MATCHES "hal_adapter_esp32")
        list(APPEND EFW_SOURCES ${{src}})
    endif()
endforeach()

"""
    
    def _generate_app_config(
        self,
        sources: list[str] = None,
        includes: list[str] = None,
        defines: list[str] = None,
    ) -> str:
        """生成应用配置"""
        content = "# ====================================================================\n"
        content += "# 应用配置\n"
        content += "# ====================================================================\n\n"
        
        # 应用源文件
        content += "set(APP_SOURCES\n"
        content += "    main.c\n"
        content += "    hal_adapter.c\n"
        
        if sources:
            for src in sources:
                content += f"    {src}\n"
        
        content += ")\n\n"
        
        # 启动文件（如果存在）
        content += """# 启动文件
if(EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/startup.s)
    list(APPEND APP_SOURCES startup.s)
endif()

"""
        
        # 应用头文件路径
        content += "include_directories(${CMAKE_CURRENT_SOURCE_DIR}/include)\n"
        
        if includes:
            for inc in includes:
                content += f"include_directories({inc})\n"
        
        content += "\n"
        
        # 应用定义
        if defines:
            content += "# 应用定义\n"
            for define in defines:
                content += f"add_definitions(-D{define})\n"
            content += "\n"
        
        return content
    
    def _generate_compile_options(self, chip_info: dict) -> str:
        """生成编译选项"""
        return f"""# ====================================================================
# 编译选项
# ====================================================================

set(CMAKE_C_FLAGS "${{CPU_FLAGS}} -fdata-sections -ffunction-sections -Wall -Wextra")
set(CMAKE_C_FLAGS_DEBUG "-O0 -g -DDEBUG")
set(CMAKE_C_FLAGS_RELEASE "-Os -DNDEBUG")

set(CMAKE_ASM_FLAGS "${{CPU_FLAGS}}")

set(CMAKE_EXE_LINKER_FLAGS "${{CPU_FLAGS}} -Wl,--gc-sections -specs=nosys.specs -specs=nano.specs")

"""
    
    def _generate_build_targets(self, chip_info: dict) -> str:
        """生成构建目标"""
        return f"""# ====================================================================
# 构建目标
# ====================================================================

# 生成可执行文件
add_executable(app.elf ${{APP_SOURCES}} ${{EFW_SOURCES}} ${{HAL_SOURCES}})

# 链接库
target_link_libraries(app.elf PRIVATE m c gcc)

# 链接脚本
if(EXISTS "${{LINKER_SCRIPT}}")
    target_link_options(app.elf PRIVATE -T ${{LINKER_SCRIPT}})
endif()

# 生成 .bin 和 .hex
add_custom_command(TARGET app.elf POST_BUILD
    COMMAND ${{CMAKE_OBJCOPY}} -O binary app.elf app.bin
    COMMAND ${{CMAKE_OBJCOPY}} -O ihex app.elf app.hex
    COMMAND ${{CMAKE_SIZE}} app.elf
    COMMENT "Generating app.bin and app.hex"
)

"""
    
    def generate_toolchain_file(self) -> str:
        """生成工具链文件"""
        return """set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR arm)

# 编译器路径（可通过环境变量或命令行覆盖）
if(DEFINED ENV{ARM_GCC_PATH})
    set(TOOLCHAIN_PREFIX $ENV{ARM_GCC_PATH}/arm-none-eabi-)
else()
    set(TOOLCHAIN_PREFIX arm-none-eabi-)
endif()

set(CMAKE_C_COMPILER ${{TOOLCHAIN_PREFIX}}gcc)
set(CMAKE_CXX_COMPILER ${{TOOLCHAIN_PREFIX}}g++)
set(CMAKE_ASM_COMPILER ${{TOOLCHAIN_PREFIX}}gcc)
set(CMAKE_OBJCOPY ${{TOOLCHAIN_PREFIX}}objcopy)
set(CMAKE_OBJDUMP ${{TOOLCHAIN_PREFIX}}objdump)
set(CMAKE_SIZE ${{TOOLCHAIN_PREFIX}}size)

set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
"""


def generate_cmake_for_chip(
    chip: str,
    project_dir: Path,
    firmware_root: Optional[Path] = None,
    output_path: Optional[Path] = None,
) -> Path:
    """为指定芯片生成 CMakeLists.txt
    
    Args:
        chip: 芯片名称
        project_dir: 项目目录
        firmware_root: 固件库根目录
        output_path: 输出文件路径
    
    Returns:
        生成的 CMakeLists.txt 路径
    """
    generator = CMakeGenerator(project_dir, firmware_root)
    content = generator.generate(chip)
    
    if output_path is None:
        output_path = project_dir / "CMakeLists.txt"
    
    output_path.write_text(content)
    return output_path
