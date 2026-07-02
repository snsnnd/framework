#!/usr/bin/env python3
"""
SVD 导入工具

从 CMSIS-SVD 文件解析设备信息，导入到 EFW MCU 数据库。

功能：
- 解析 SVD 文件（外设、中断、寄存器）
- 扩展 MCU 数据库格式
- 批量导入 SVD 数据
- 生成链接脚本

使用方式：
  # 导入单个 SVD 文件
  python3 tools/svd_import.py import /path/to/STM32F407.svd
  
  # 批量导入 SVD 数据仓库
  python3 tools/svd_import.py import-all /path/to/cmsis-svd-data/data/
  
  # 查看 SVD 信息
  python3 tools/svd_import.py info /path/to/STM32F407.svd
  
  # 从数据库生成链接脚本
  python3 tools/svd_import.py linker STM32F407 -o linker.ld
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Optional


# ─── SVD 解析器 ──────────────────────────────────────────────────────────────

class SVDParser:
    """SVD 文件解析器（不依赖 lxml）"""
    
    def __init__(self, svd_path: Path):
        self.svd_path = svd_path
        self.tree = ET.parse(svd_path)
        self.root = self.tree.getroot()
    
    def parse(self) -> dict[str, Any]:
        """解析 SVD 文件，返回完整设备信息"""
        name = self._get_text("name", "")
        description = self._get_text("description", "")
        
        cpu = self._parse_cpu()
        peripherals = self._parse_peripherals()
        interrupts = self._collect_interrupts(peripherals)
        
        return {
            "name": name,
            "description": description,
            "cpu": cpu,
            "peripherals": peripherals,
            "interrupts": interrupts,
        }
    
    def _get_text(self, tag: str, default: str = "") -> str:
        elem = self.root.find(tag)
        return elem.text if elem is not None and elem.text else default
    
    def _parse_cpu(self) -> dict[str, Any]:
        """解析 CPU 信息"""
        cpu_elem = self.root.find("cpu")
        if cpu_elem is None:
            return {}
        
        def get_bool(tag: str) -> bool:
            elem = cpu_elem.find(tag)
            return elem is not None and elem.text is not None and elem.text.lower() in ("true", "1")
        
        def get_int(tag: str, default: int = 0) -> int:
            elem = cpu_elem.find(tag)
            if elem is None or elem.text is None:
                return default
            try:
                return int(elem.text)
            except ValueError:
                return default
        
        return {
            "name": cpu_elem.findtext("name", ""),
            "revision": cpu_elem.findtext("revision", ""),
            "endian": cpu_elem.findtext("endian", "little"),
            "mpu_present": get_bool("mpuPresent"),
            "fpu_present": get_bool("fpuPresent"),
            "nvic_prio_bits": get_int("nvicPrioBits", 4),
            "vendor_systick": get_bool("vendorSystickConfig"),
        }
    
    def _parse_peripherals(self) -> list[dict[str, Any]]:
        """解析外设信息"""
        peripherals = []
        
        for p_elem in self.root.findall(".//peripheral"):
            name = p_elem.findtext("name", "")
            description = p_elem.findtext("description", "")
            group_name = p_elem.findtext("groupName", "")
            
            # 基地址
            base_addr_text = p_elem.findtext("baseAddress", "0")
            try:
                base_address = int(base_addr_text, 0)
            except ValueError:
                base_address = 0
            
            # 地址块
            address_blocks = []
            for ab_elem in p_elem.findall("addressBlock"):
                offset = int(ab_elem.findtext("offset", "0"), 0)
                size = int(ab_elem.findtext("size", "0x400"), 0)
                usage = ab_elem.findtext("usage", "registers")
                address_blocks.append({
                    "offset": offset,
                    "size": size,
                    "usage": usage,
                })
            
            # 中断
            interrupts = []
            for i_elem in p_elem.findall("interrupt"):
                i_name = i_elem.findtext("name", "")
                i_desc = i_elem.findtext("description", "")
                i_value_text = i_elem.findtext("value", "0")
                try:
                    i_value = int(i_value_text)
                except ValueError:
                    i_value = 0
                interrupts.append({
                    "name": i_name,
                    "description": i_desc,
                    "value": i_value,
                })
            
            # 寄存器
            registers = self._parse_registers(p_elem)
            
            peripherals.append({
                "name": name,
                "description": description,
                "group_name": group_name,
                "base_address": base_address,
                "address_blocks": address_blocks,
                "interrupts": interrupts,
                "registers": registers,
            })
        
        return peripherals
    
    def _parse_registers(self, p_elem) -> list[dict[str, Any]]:
        """解析寄存器信息"""
        registers = []
        
        for r_elem in p_elem.findall(".//register"):
            name = r_elem.findtext("name", "")
            display_name = r_elem.findtext("displayName", name)
            description = r_elem.findtext("description", "")
            
            # 地址偏移
            offset_text = r_elem.findtext("addressOffset", "0")
            try:
                offset = int(offset_text, 0)
            except ValueError:
                offset = 0
            
            # 大小
            size_text = r_elem.findtext("size", "0x20")
            try:
                size = int(size_text, 0)
            except ValueError:
                size = 32
            
            # 访问权限
            access = r_elem.findtext("access", "read-write")
            
            # 复位值
            reset_text = r_elem.findtext("resetValue", "0")
            try:
                reset_value = int(reset_text, 0)
            except ValueError:
                reset_value = 0
            
            # 位域
            fields = self._parse_fields(r_elem)
            
            registers.append({
                "name": name,
                "display_name": display_name,
                "description": description,
                "offset": offset,
                "size": size,
                "access": access,
                "reset_value": reset_value,
                "fields": fields,
            })
        
        return registers
    
    def _parse_fields(self, r_elem) -> list[dict[str, Any]]:
        """解析位域信息"""
        fields = []
        
        for f_elem in r_elem.findall(".//field"):
            name = f_elem.findtext("name", "")
            description = f_elem.findtext("description", "")
            
            bit_offset_text = f_elem.findtext("bitOffset", "0")
            try:
                bit_offset = int(bit_offset_text)
            except ValueError:
                bit_offset = 0
            
            bit_width_text = f_elem.findtext("bitWidth", "1")
            try:
                bit_width = int(bit_width_text)
            except ValueError:
                bit_width = 1
            
            access = f_elem.findtext("access", "")
            
            fields.append({
                "name": name,
                "description": description,
                "bit_offset": bit_offset,
                "bit_width": bit_width,
                "access": access,
            })
        
        return fields
    
    def _collect_interrupts(self, peripherals: list[dict]) -> list[dict]:
        """收集并去重所有中断"""
        seen = set()
        interrupts = []
        
        for p in peripherals:
            for irq in p.get("interrupts", []):
                if irq["value"] not in seen:
                    seen.add(irq["value"])
                    interrupts.append({
                        "name": irq["name"],
                        "value": irq["value"],
                        "description": irq.get("description", ""),
                        "peripheral": p["name"],
                    })
        
        interrupts.sort(key=lambda x: x["value"])
        return interrupts


# ─── 数据库管理 ──────────────────────────────────────────────────────────────

class MCUDataManager:
    """MCU 数据库管理器"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.mcu_dir = data_dir / "mcu"
        self.svd_dir = data_dir / "svd"
        self.mcu_dir.mkdir(parents=True, exist_ok=True)
        self.svd_dir.mkdir(parents=True, exist_ok=True)
    
    def import_svd(self, svd_path: Path, chip_name: str = None, family: str = None) -> dict:
        """导入 SVD 文件到数据库"""
        # 解析 SVD
        parser = SVDParser(svd_path)
        svd_data = parser.parse()
        
        # 确定芯片名称和系列
        if not chip_name:
            chip_name = svd_data["name"]
        if not family:
            family = self._detect_family(chip_name)
        
        # 构建完整的 MCU 数据
        mcu_data = {
            "name": chip_name,
            "family": family,
            "description": svd_data.get("description", ""),
            
            # CPU 信息
            "cpu": svd_data.get("cpu", {}),
            
            # 内存布局（需要从其他来源获取或手动配置）
            "memory": {
                "flash": {
                    "start": 0x08000000,
                    "size_kb": 1024,  # 默认值，需要根据芯片调整
                },
                "ram": {
                    "start": 0x20000000,
                    "size_kb": 192,  # 默认值
                },
                "ccm": {
                    "start": 0x10000000,
                    "size_kb": 64,  # 默认值，部分芯片没有
                },
            },
            
            # 外设信息
            "peripherals": svd_data.get("peripherals", []),
            
            # 中断信息
            "interrupts": svd_data.get("interrupts", []),
            
            # SVD 来源
            "svd_source": str(svd_path.name),
        }
        
        # 保存到数据库
        self._save_mcu(chip_name, family, mcu_data)
        
        # 保存原始 SVD 文件
        self._save_svd(chip_name, svd_path)
        
        return mcu_data
    
    def _detect_family(self, chip_name: str) -> str:
        """检测芯片系列"""
        chip_upper = chip_name.upper()
        
        if "STM32F0" in chip_upper:
            return "STM32F0"
        elif "STM32F1" in chip_upper:
            return "STM32F1"
        elif "STM32F2" in chip_upper:
            return "STM32F2"
        elif "STM32F3" in chip_upper:
            return "STM32F3"
        elif "STM32F4" in chip_upper:
            return "STM32F4"
        elif "STM32F7" in chip_upper:
            return "STM32F7"
        elif "STM32G0" in chip_upper:
            return "STM32G0"
        elif "STM32G4" in chip_upper:
            return "STM32G4"
        elif "STM32H7" in chip_upper:
            return "STM32H7"
        elif "STM32L0" in chip_upper:
            return "STM32L0"
        elif "STM32L1" in chip_upper:
            return "STM32L1"
        elif "STM32L4" in chip_upper:
            return "STM32L4"
        elif "STM32" in chip_upper:
            return "STM32"
        elif "GD32" in chip_upper:
            return "GD32"
        elif "CH32V" in chip_upper:
            return "CH32V"
        else:
            return "Unknown"
    
    def _save_mcu(self, chip_name: str, family: str, mcu_data: dict):
        """保存 MCU 数据"""
        family_dir = self.mcu_dir / family
        family_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存完整数据
        mcu_path = family_dir / f"{chip_name}.json"
        with open(mcu_path, "w", encoding="utf-8") as f:
            json.dump(mcu_data, f, ensure_ascii=False, indent=2)
        
        # 更新索引
        self._update_index(chip_name, family, mcu_data)
    
    def _save_svd(self, chip_name: str, svd_path: Path):
        """保存原始 SVD 文件"""
        import shutil
        
        dest = self.svd_dir / f"{chip_name}.svd"
        shutil.copy2(svd_path, dest)
    
    def _update_index(self, chip_name: str, family: str, mcu_data: dict):
        """更新索引文件"""
        index_path = self.mcu_dir / "index.json"
        
        # 读取现有索引
        if index_path.exists():
            with open(index_path, "r", encoding="utf-8") as f:
                index = json.load(f)
        else:
            index = {}
        
        # 更新索引
        cpu = mcu_data.get("cpu", {})
        memory = mcu_data.get("memory", {})
        
        index[chip_name] = {
            "family": family,
            "core": cpu.get("name", ""),
            "frequency_mhz": 0,  # 需要从其他来源获取
            "flash_kb": memory.get("flash", {}).get("size_kb", 0),
            "ram_kb": memory.get("ram", {}).get("size_kb", 0),
            "gpio_count": 0,  # 需要从引脚数据获取
            "peripheral_count": len(mcu_data.get("peripherals", [])),
            "interrupt_count": len(mcu_data.get("interrupts", [])),
            "path": f"{family}/{chip_name}.json",
            "svd_source": mcu_data.get("svd_source", ""),
        }
        
        # 保存索引
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
    
    def get_mcu(self, chip_name: str) -> Optional[dict]:
        """获取 MCU 数据"""
        # 从索引查找
        index_path = self.mcu_dir / "index.json"
        if not index_path.exists():
            return None
        
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)
        
        if chip_name not in index:
            return None
        
        # 加载完整数据
        mcu_path = self.mcu_dir / index[chip_name]["path"]
        if not mcu_path.exists():
            return None
        
        with open(mcu_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def list_mcus(self) -> list[dict]:
        """列出所有 MCU"""
        index_path = self.mcu_dir / "index.json"
        if not index_path.exists():
            return []
        
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)
        
        return [{"name": name, **info} for name, info in index.items()]


# ─── 链接脚本生成器 ──────────────────────────────────────────────────────────

class LinkerScriptGenerator:
    """从数据库生成链接脚本"""
    
    def __init__(self, data_manager: MCUDataManager):
        self.data_manager = data_manager
    
    def generate(self, chip_name: str, overrides: dict = None) -> str:
        """从数据库生成链接脚本"""
        mcu_data = self.data_manager.get_mcu(chip_name)
        if not mcu_data:
            raise ValueError(f"未找到芯片: {chip_name}")
        
        memory = mcu_data.get("memory", {})
        
        # 获取内存配置（允许覆盖）
        flash = memory.get("flash", {})
        ram = memory.get("ram", {})
        ccm = memory.get("ccm", {})
        
        flash_start = flash.get("start", 0x08000000)
        flash_size = flash.get("size_kb", 1024)
        ram_start = ram.get("start", 0x20000000)
        ram_size = ram.get("size_kb", 192)
        ccm_start = ccm.get("start", 0x10000000)
        ccm_size = ccm.get("size_kb", 0)
        
        # 应用覆盖
        if overrides:
            flash_size = overrides.get("flash_kb", flash_size)
            ram_size = overrides.get("ram_kb", ram_size)
            ccm_size = overrides.get("ccm_kb", ccm_size)
        
        # 生成链接脚本
        return self._generate_linker(
            chip_name,
            flash_start, flash_size,
            ram_start, ram_size,
            ccm_start, ccm_size,
        )
    
    def _generate_linker(
        self,
        chip_name: str,
        flash_start: int, flash_size_kb: int,
        ram_start: int, ram_size_kb: int,
        ccm_start: int, ccm_size_kb: int,
    ) -> str:
        """生成链接脚本内容"""
        content = f"""/*
 * 链接脚本 - {chip_name}
 * 从 EFW MCU 数据库自动生成
 *
 * Flash: {flash_size_kb}KB @ 0x{flash_start:08X}
 * RAM:   {ram_size_kb}KB @ 0x{ram_start:08X}
 * CCM:   {ccm_size_kb}KB @ 0x{ccm_start:08X}
 */

ENTRY(Reset_Handler)

_estack = ORIGIN(RAM) + LENGTH(RAM);

_Min_Heap_Size = 0x200;
_Min_Stack_Size = 0x400;

MEMORY
{{
"""
        
        if ccm_size_kb > 0:
            content += f"  CCMRAM (xrw) : ORIGIN = 0x{ccm_start:08X}, LENGTH = {ccm_size_kb}K\n"
        
        content += f"""  RAM    (xrw) : ORIGIN = 0x{ram_start:08X}, LENGTH = {ram_size_kb}K
  FLASH  (rx)  : ORIGIN = 0x{flash_start:08X}, LENGTH = {flash_size_kb}K
}}

SECTIONS
{{
  .isr_vector :
  {{
    . = ALIGN(4);
    KEEP(*(.isr_vector))
    . = ALIGN(4);
  }} >FLASH

  .text :
  {{
    . = ALIGN(4);
    *(.text)
    *(.text*)
    *(.glue_7)
    *(.glue_7t)
    *(.eh_frame)
    KEEP(*(.init))
    KEEP(*(.fini))
    . = ALIGN(4);
    _etext = .;
  }} >FLASH

  .rodata :
  {{
    . = ALIGN(4);
    *(.rodata)
    *(.rodata*)
    . = ALIGN(4);
  }} >FLASH

  .ARM.extab :
  {{
    . = ALIGN(4);
    *(.ARM.extab* .gnu.linkonce.armextab.*)
    . = ALIGN(4);
  }} >FLASH

  .ARM :
  {{
    . = ALIGN(4);
    __exidx_start = .;
    *(.ARM.exidx*)
    __exidx_end = .;
    . = ALIGN(4);
  }} >FLASH

  .preinit_array :
  {{
    . = ALIGN(4);
    PROVIDE_HIDDEN(__preinit_array_start = .);
    KEEP(*(.preinit_array*))
    PROVIDE_HIDDEN(__preinit_array_end = .);
    . = ALIGN(4);
  }} >FLASH

  .init_array :
  {{
    . = ALIGN(4);
    PROVIDE_HIDDEN(__init_array_start = .);
    KEEP(*(SORT(.init_array.*)))
    KEEP(*(.init_array*))
    PROVIDE_HIDDEN(__init_array_end = .);
    . = ALIGN(4);
  }} >FLASH

  .fini_array :
  {{
    . = ALIGN(4);
    PROVIDE_HIDDEN(__fini_array_start = .);
    KEEP(*(SORT(.fini_array.*)))
    KEEP(*(.fini_array*))
    PROVIDE_HIDDEN(__fini_array_end = .);
    . = ALIGN(4);
  }} >FLASH

  _sidata = LOADADDR(.data);

  .data :
  {{
    . = ALIGN(4);
    _sdata = .;
    *(.data)
    *(.data*)
    *(.RamFunc)
    *(.RamFunc*)
    . = ALIGN(4);
    _edata = .;
  }} >RAM AT> FLASH

"""
        
        if ccm_size_kb > 0:
            content += """  _siccmram = LOADADDR(.ccmram);

  .ccmram :
  {
    . = ALIGN(4);
    _sccmram = .;
    *(.ccmram)
    *(.ccmram*)
    . = ALIGN(4);
    _eccmram = .;
  } >CCMRAM AT> FLASH

"""
        
        content += """  . = ALIGN(4);
  .bss :
  {
    _sbss = .;
    __bss_start__ = _sbss;
    *(.bss)
    *(.bss*)
    *(COMMON)
    . = ALIGN(4);
    _ebss = .;
    __bss_end__ = _ebss;
  } >RAM

  ._user_heap_stack :
  {
    . = ALIGN(8);
    PROVIDE(end = .);
    PROVIDE(_end = .);
    . = . + _Min_Heap_Size;
    . = . + _Min_Stack_Size;
    . = ALIGN(8);
  } >RAM

  /DISCARD/ :
  {
    libc.a(*)
    libm.a(*)
    libgcc.a(*)
  }

  .ARM.attributes 0 : { *(.ARM.attributes) }
}
"""
        
        return content


# ─── 启动代码生成器 ──────────────────────────────────────────────────────────

class StartupGenerator:
    """从数据库生成启动代码"""
    
    def __init__(self, data_manager: MCUDataManager):
        self.data_manager = data_manager
    
    def generate(self, chip_name: str) -> str:
        """从数据库生成启动代码"""
        mcu_data = self.data_manager.get_mcu(chip_name)
        if not mcu_data:
            raise ValueError(f"未找到芯片: {chip_name}")
        
        interrupts = mcu_data.get("interrupts", [])
        cpu = mcu_data.get("cpu", {})
        
        return self._generate_startup(chip_name, cpu, interrupts)
    
    def _generate_startup(self, chip_name: str, cpu: dict, interrupts: list) -> str:
        """生成启动代码内容"""
        content = f"""/**
 * @file    startup_{chip_name.lower()}.s
 * @brief   启动代码 - 从 EFW MCU 数据库自动生成
 * @device  {chip_name}
 * @cpu     {cpu.get('name', 'CM4')}
 */

  .syntax unified
  .cpu cortex-m4
  .fpu softvfp
  .thumb

.global g_pfnVectors
.global Default_Handler

.word _estack

.section .text.Reset_Handler
  .weak Reset_Handler
  .type Reset_Handler, %function
Reset_Handler:
  ldr   sp, =_estack

  ldr r0, =_sdata
  ldr r1, =_edata
  ldr r2, =_sidata
  movs r3, #0
  b LoopCopyDataInit

CopyDataInit:
  ldr r4, [r2, r3]
  str r4, [r0, r3]
  adds r3, r3, #4

LoopCopyDataInit:
  adds r4, r0, r3
  cmp r4, r1
  bcc CopyDataInit

  ldr r2, =__bss_start__
  ldr r4, =__bss_end__
  movs r3, #0
  b LoopFillZerobss

FillZerobss:
  str r3, [r2]
  adds r2, r2, #4

LoopFillZerobss:
  cmp r2, r4
  bcc FillZerobss

  bl SystemInit
  bl main

LoopForever:
  b LoopForever

.size Reset_Handler, .-Reset_Handler

.section .text.Default_Handler,"ax",%progbits
Default_Handler:
Infinite_Loop:
  b Infinite_Loop
  .size Default_Handler, .-Default_Handler

.section .isr_vector,"a",%progbits
  .type g_pfnVectors, %object
  .size g_pfnVectors, .-g_pfnVectors

g_pfnVectors:
  .word _estack
  .word Reset_Handler
  .word NMI_Handler
  .word HardFault_Handler
  .word MemManage_Handler
  .word BusFault_Handler
  .word UsageFault_Handler
  .word 0
  .word 0
  .word 0
  .word 0
  .word SVC_Handler
  .word DebugMon_Handler
  .word 0
  .word PendSV_Handler
  .word SysTick_Handler

"""
        
        # 添加外设中断
        if interrupts:
            content += "  /* 外设中断 */\n"
            for irq in interrupts:
                content += f"  .word {irq['name']}_Handler  /* {irq['value']}: {irq.get('description', '')} */\n"
        
        content += """
  .weak NMI_Handler
  .thumb_set NMI_Handler, Default_Handler

  .weak HardFault_Handler
  .thumb_set HardFault_Handler, Default_Handler

  .weak MemManage_Handler
  .thumb_set MemManage_Handler, Default_Handler

  .weak BusFault_Handler
  .thumb_set BusFault_Handler, Default_Handler

  .weak UsageFault_Handler
  .thumb_set UsageFault_Handler, Default_Handler

  .weak SVC_Handler
  .thumb_set SVC_Handler, Default_Handler

  .weak DebugMon_Handler
  .thumb_set DebugMon_Handler, Default_Handler

  .weak PendSV_Handler
  .thumb_set PendSV_Handler, Default_Handler

  .weak SysTick_Handler
  .thumb_set SysTick_Handler, Default_Handler

"""
        
        # 添加外设中断弱符号
        if interrupts:
            for irq in interrupts:
                content += f"  .weak {irq['name']}_Handler\n"
                content += f"  .thumb_set {irq['name']}_Handler, Default_Handler\n\n"
        
        return content


# ─── CLI 入口 ────────────────────────────────────────────────────────────────

def main(argv=None):
    import argparse
    
    parser = argparse.ArgumentParser(prog="efw svd", description="SVD 导入工具")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # import 命令
    import_parser = subparsers.add_parser("import", help="导入 SVD 文件")
    import_parser.add_argument("svd", help="SVD 文件路径")
    import_parser.add_argument("--name", help="芯片名称（可选）")
    import_parser.add_argument("--family", help="芯片系列（可选）")
    import_parser.add_argument("--data-dir", default="data", help="数据目录")
    
    # import-all 命令
    import_all_parser = subparsers.add_parser("import-all", help="批量导入 SVD")
    import_all_parser.add_argument("dir", help="SVD 数据目录")
    import_all_parser.add_argument("--data-dir", default="data", help="数据目录")
    
    # info 命令
    info_parser = subparsers.add_parser("info", help="查看 SVD 信息")
    info_parser.add_argument("svd", help="SVD 文件路径")
    
    # linker 命令
    linker_parser = subparsers.add_parser("linker", help="生成链接脚本")
    linker_parser.add_argument("chip", help="芯片名称")
    linker_parser.add_argument("-o", "--output", default="linker.ld", help="输出文件")
    linker_parser.add_argument("--flash", type=int, help="Flash 大小 (KB)")
    linker_parser.add_argument("--ram", type=int, help="RAM 大小 (KB)")
    linker_parser.add_argument("--ccm", type=int, help="CCMRAM 大小 (KB)")
    linker_parser.add_argument("--data-dir", default="data", help="数据目录")
    
    # startup 命令
    startup_parser = subparsers.add_parser("startup", help="生成启动代码")
    startup_parser.add_argument("chip", help="芯片名称")
    startup_parser.add_argument("-o", "--output", help="输出文件")
    startup_parser.add_argument("--data-dir", default="data", help="数据目录")
    
    # list 命令
    list_parser = subparsers.add_parser("list", help="列出已导入的芯片")
    list_parser.add_argument("--data-dir", default="data", help="数据目录")
    
    args = parser.parse_args(argv)
    
    if not args.command:
        parser.print_help()
        return 0
    
    data_dir = Path(args.data_dir) if hasattr(args, "data_dir") else Path("data")
    manager = MCUDataManager(data_dir)
    
    if args.command == "import":
        svd_path = Path(args.svd)
        if not svd_path.exists():
            print(f"错误: SVD 文件不存在: {svd_path}")
            return 1
        
        print(f"导入 SVD: {svd_path}")
        mcu_data = manager.import_svd(svd_path, args.name, args.family)
        print(f"✓ 导入成功: {mcu_data['name']}")
        print(f"  CPU: {mcu_data['cpu'].get('name', 'Unknown')}")
        print(f"  外设: {len(mcu_data['peripherals'])} 个")
        print(f"  中断: {len(mcu_data['interrupts'])} 个")
        return 0
    
    elif args.command == "import-all":
        svd_dir = Path(args.dir)
        if not svd_dir.exists():
            print(f"错误: 目录不存在: {svd_dir}")
            return 1
        
        svd_files = list(svd_dir.rglob("*.svd"))
        print(f"找到 {len(svd_files)} 个 SVD 文件")
        
        success = 0
        for svd_file in svd_files:
            try:
                manager.import_svd(svd_file)
                print(f"  ✓ {svd_file.name}")
                success += 1
            except Exception as e:
                print(f"  ✗ {svd_file.name}: {e}")
        
        print(f"\n导入完成: {success}/{len(svd_files)}")
        return 0
    
    elif args.command == "info":
        svd_path = Path(args.svd)
        if not svd_path.exists():
            print(f"错误: SVD 文件不存在: {svd_path}")
            return 1
        
        parser = SVDParser(svd_path)
        info = parser.parse()
        
        print(f"设备: {info['name']}")
        print(f"CPU: {info['cpu'].get('name', 'Unknown')}")
        print(f"外设: {len(info['peripherals'])} 个")
        print(f"中断: {len(info['interrupts'])} 个")
        
        print("\n外设:")
        for p in info['peripherals'][:20]:
            print(f"  {p['name']}: 0x{p['base_address']:08X}")
        
        print("\n中断:")
        for irq in info['interrupts'][:20]:
            print(f"  {irq['value']:3d}: {irq['name']}")
        
        return 0
    
    elif args.command == "linker":
        overrides = {}
        if args.flash:
            overrides["flash_kb"] = args.flash
        if args.ram:
            overrides["ram_kb"] = args.ram
        if args.ccm:
            overrides["ccm_kb"] = args.ccm
        
        generator = LinkerScriptGenerator(manager)
        
        try:
            content = generator.generate(args.chip, overrides or None)
            
            output_path = Path(args.output)
            output_path.write_text(content)
            print(f"✓ 链接脚本已生成: {output_path}")
        except ValueError as e:
            print(f"错误: {e}")
            return 1
        
        return 0
    
    elif args.command == "startup":
        generator = StartupGenerator(manager)
        
        try:
            content = generator.generate(args.chip)
            
            if args.output:
                output_path = Path(args.output)
            else:
                output_path = Path(f"startup_{args.chip.lower()}.s")
            
            output_path.write_text(content)
            print(f"✓ 启动代码已生成: {output_path}")
        except ValueError as e:
            print(f"错误: {e}")
            return 1
        
        return 0
    
    elif args.command == "list":
        mcus = manager.list_mcus()
        
        if not mcus:
            print("数据库为空，请先导入 SVD 文件")
            return 0
        
        print(f"已导入 {len(mcus)} 个芯片:")
        for mcu in mcus:
            print(f"  {mcu['name']}: {mcu['family']}, {mcu.get('peripheral_count', 0)} 外设, {mcu.get('interrupt_count', 0)} 中断")
        
        return 0
    
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
