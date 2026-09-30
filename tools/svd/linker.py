"""
SVD 增强的链接脚本生成器

使用 cmsis-svd 解析器从 SVD 文件提取：
- 内存布局
- 外设基地址
- 中断向量表

自动生成精确的链接脚本和启动代码。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# 添加 cmsis-svd 解析器路径
CMSIS_SVD_PATH = Path.home() / ".efw" / "tools" / "cmsis-svd" / "python"
if CMSIS_SVD_PATH.exists():
    sys.path.insert(0, str(CMSIS_SVD_PATH))


def parse_svd_file(svd_path: Path) -> dict:
    """解析 SVD 文件，返回设备信息"""
    try:
        from cmsis_svd.parser import SVDParser
        parser = SVDParser.for_xml_file(str(svd_path))
        device = parser.get_device()
    except ImportError:
        # 如果 cmsis-svd 不可用，使用简单的 XML 解析
        return parse_svd_simple(svd_path)
    
    # 收集中断
    interrupts = []
    for p in device.peripherals:
        for i in p.interrupts:
            interrupts.append({
                "name": i.name,
                "value": i.value,
                "description": i.description,
            })
    
    # 按中断号排序
    interrupts.sort(key=lambda x: x["value"])
    
    # 去重
    seen = set()
    unique_interrupts = []
    for irq in interrupts:
        if irq["value"] not in seen:
            seen.add(irq["value"])
            unique_interrupts.append(irq)
    
    return {
        "name": device.name,
        "description": device.description,
        "cpu": {
            "name": str(device.cpu.name).split(".")[-1],
            "endian": str(device.cpu.endian).split(".")[-1].lower(),
            "fpu_present": device.cpu.fpu_present,
            "mpu_present": device.cpu.mpu_present,
            "nvic_prio_bits": device.cpu.nvic_prio_bits,
        },
        "peripherals": [
            {
                "name": p.name,
                "description": p.description,
                "base_address": p.base_address,
            }
            for p in device.peripherals
        ],
        "interrupts": unique_interrupts,
    }


def parse_svd_simple(svd_path: Path) -> dict:
    """简单的 SVD 解析（不依赖 lxml）"""
    import xml.etree.ElementTree as ET
    
    tree = ET.parse(svd_path)
    root = tree.getroot()
    
    name = root.findtext("name", "")
    description = root.findtext("description", "")
    
    # CPU 信息
    cpu_elem = root.find("cpu")
    cpu = {
        "name": cpu_elem.findtext("name", "") if cpu_elem is not None else "",
        "endian": cpu_elem.findtext("endian", "little") if cpu_elem is not None else "little",
        "fpu_present": cpu_elem.findtext("fpuPresent", "false").lower() == "true" if cpu_elem is not None else False,
    }
    
    # 外设信息
    peripherals = []
    for p_elem in root.findall(".//peripheral"):
        p_name = p_elem.findtext("name", "")
        p_desc = p_elem.findtext("description", "")
        p_addr_text = p_elem.findtext("baseAddress", "0")
        try:
            p_addr = int(p_addr_text, 0)
        except ValueError:
            p_addr = 0
        
        peripherals.append({
            "name": p_name,
            "description": p_desc,
            "base_address": p_addr,
        })
    
    # 中断信息
    interrupts = []
    for p_elem in root.findall(".//peripheral"):
        for i_elem in p_elem.findall("interrupt"):
            i_name = i_elem.findtext("name", "")
            i_value_text = i_elem.findtext("value", "0")
            i_desc = i_elem.findtext("description", "")
            try:
                i_value = int(i_value_text)
            except ValueError:
                i_value = 0
            
            interrupts.append({
                "name": i_name,
                "value": i_value,
                "description": i_desc,
            })
    
    # 去重并排序
    interrupts.sort(key=lambda x: x["value"])
    seen = set()
    unique_interrupts = []
    for irq in interrupts:
        if irq["value"] not in seen:
            seen.add(irq["value"])
            unique_interrupts.append(irq)
    
    return {
        "name": name,
        "description": description,
        "cpu": cpu,
        "peripherals": peripherals,
        "interrupts": unique_interrupts,
    }


def generate_linker_script(
    device_info: dict,
    flash_size_kb: int = 1024,
    ram_size_kb: int = 192,
    ccm_size_kb: int = 64,
) -> str:
    """生成链接脚本"""
    
    device_name = device_info["name"]
    
    content = f"""/*
 * 链接脚本 - {device_name}
 * 基于 SVD 数据自动生成
 *
 * Flash: {flash_size_kb}KB
 * RAM:   {ram_size_kb}KB
 * CCM:   {ccm_size_kb}KB
 */

ENTRY(Reset_Handler)

_estack = ORIGIN(RAM) + LENGTH(RAM);

_Min_Heap_Size = 0x200;
_Min_Stack_Size = 0x400;

MEMORY
{{
"""
    
    if ccm_size_kb > 0:
        content += f"  CCMRAM (xrw) : ORIGIN = 0x10000000, LENGTH = {ccm_size_kb}K\n"
    
    content += f"""  RAM    (xrw) : ORIGIN = 0x20000000, LENGTH = {ram_size_kb}K
  FLASH  (rx)  : ORIGIN = 0x08000000, LENGTH = {flash_size_kb}K
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


def generate_startup_code(device_info: dict) -> str:
    """生成启动代码"""
    
    device_name = device_info["name"]
    interrupts = device_info.get("interrupts", [])
    
    content = f"""/**
 * @file    startup_{device_name.lower()}.s
 * @brief   启动代码 - 基于 SVD 自动生成
 * @device  {device_name}
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


def generate_from_svd(
    svd_path: Path,
    output_dir: Path,
    flash_size_kb: int = 1024,
    ram_size_kb: int = 192,
    ccm_size_kb: int = 64,
) -> dict[str, Path]:
    """从 SVD 文件生成链接脚本和启动代码
    
    Args:
        svd_path: SVD 文件路径
        output_dir: 输出目录
        flash_size_kb: Flash 大小 (KB)
        ram_size_kb: RAM 大小 (KB)
        ccm_size_kb: CCMRAM 大小 (KB)
    
    Returns:
        生成的文件路径字典
    """
    # 解析 SVD
    device_info = parse_svd_file(svd_path)
    
    # 创建输出目录
    output_dir.mkdir(parents=True, exist_ok=True)
    
    generated = {}
    
    # 生成链接脚本
    linker_content = generate_linker_script(
        device_info,
        flash_size_kb=flash_size_kb,
        ram_size_kb=ram_size_kb,
        ccm_size_kb=ccm_size_kb,
    )
    linker_path = output_dir / "linker.ld"
    linker_path.write_text(linker_content)
    generated["linker"] = linker_path
    
    # 生成启动代码
    startup_content = generate_startup_code(device_info)
    startup_path = output_dir / f"startup_{device_info['name'].lower()}.s"
    startup_path.write_text(startup_content)
    generated["startup"] = startup_path
    
    return generated


# ─── CLI 入口 ────────────────────────────────────────────────────────────────

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="SVD 链接脚本生成器")
    parser.add_argument("svd", help="SVD 文件路径")
    parser.add_argument("-o", "--output", default=".", help="输出目录")
    parser.add_argument("--flash", type=int, default=1024, help="Flash 大小 (KB)")
    parser.add_argument("--ram", type=int, default=192, help="RAM 大小 (KB)")
    parser.add_argument("--ccm", type=int, default=64, help="CCMRAM 大小 (KB)")
    parser.add_argument("--info", action="store_true", help="只显示设备信息")
    
    args = parser.parse_args()
    
    svd_path = Path(args.svd)
    if not svd_path.exists():
        print(f"错误: SVD 文件不存在: {svd_path}")
        return 1
    
    # 解析 SVD
    device_info = parse_svd_file(svd_path)
    
    if args.info:
        print(f"设备: {device_info['name']}")
        print(f"CPU: {device_info['cpu']['name']}")
        print(f"字节序: {device_info['cpu']['endian']}")
        print(f"FPU: {device_info['cpu']['fpu_present']}")
        print(f"外设数量: {len(device_info['peripherals'])}")
        print(f"中断数量: {len(device_info['interrupts'])}")
        print()
        print("外设列表:")
        for p in device_info['peripherals'][:20]:
            print(f"  {p['name']}: 0x{p['base_address']:08X}")
        print()
        print("中断列表:")
        for irq in device_info['interrupts'][:20]:
            print(f"  {irq['value']:3d}: {irq['name']}")
        return 0
    
    # 生成文件
    output_dir = Path(args.output)
    generated = generate_from_svd(
        svd_path,
        output_dir,
        flash_size_kb=args.flash,
        ram_size_kb=args.ram,
        ccm_size_kb=args.ccm,
    )
    
    print("生成完成:")
    for name, path in generated.items():
        print(f"  {name}: {path}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
