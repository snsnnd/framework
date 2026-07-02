"""
SVD 文件解析器

解析 CMSIS-SVD 文件，提取：
- 内存布局（Flash/RAM 地址和大小）
- 外设基地址
- 中断信息
- 寄存器定义

用于自动生成链接脚本和启动代码。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class SVDCpuInfo:
    """CPU 信息"""
    name: str = ""
    revision: str = ""
    endian: str = "little"
    mpu_present: bool = False
    fpu_present: bool = False
    nvic_prio_bits: int = 4
    vendor_systick: bool = False


@dataclass
class SVDMemoryRegion:
    """内存区域"""
    name: str
    start: int
    size: int
    access: str = "rw"  # rx, rw, rwx


@dataclass
class SVDInterrupt:
    """中断信息"""
    name: str
    description: str
    value: int  # 中断号


@dataclass
class SVDPeripheral:
    """外设信息"""
    name: str
    description: str
    base_address: int
    size: int = 0x400
    interrupts: list[SVDInterrupt] = field(default_factory=list)


@dataclass
class SVDDevice:
    """设备信息"""
    name: str
    description: str
    cpu: SVDCpuInfo
    memories: list[SVDMemoryRegion]
    peripherals: list[SVDPeripheral]
    interrupts: list[SVDInterrupt]


class SVDParser:
    """SVD 文件解析器"""
    
    def __init__(self, svd_path: Path):
        self.svd_path = svd_path
        self.tree = ET.parse(svd_path)
        self.root = self.tree.getroot()
    
    def parse(self) -> SVDDevice:
        """解析 SVD 文件"""
        name = self._get_text("name", "")
        description = self._get_text("description", "")
        
        cpu = self._parse_cpu()
        memories = self._parse_memories()
        peripherals = self._parse_peripherals()
        
        # 收集所有中断
        all_interrupts = []
        for p in peripherals:
            all_interrupts.extend(p.interrupts)
        
        # 按中断号排序
        all_interrupts.sort(key=lambda x: x.value)
        
        return SVDDevice(
            name=name,
            description=description,
            cpu=cpu,
            memories=memories,
            peripherals=peripherals,
            interrupts=all_interrupts,
        )
    
    def _get_text(self, tag: str, default: str = "") -> str:
        """获取 XML 元素文本"""
        elem = self.root.find(tag)
        return elem.text if elem is not None and elem.text else default
    
    def _parse_cpu(self) -> SVDCpuInfo:
        """解析 CPU 信息"""
        cpu_elem = self.root.find("cpu")
        if cpu_elem is None:
            return SVDCpuInfo()
        
        def get_bool(tag: str, default: bool = False) -> bool:
            elem = cpu_elem.find(tag)
            if elem is None or elem.text is None:
                return default
            return elem.text.lower() in ("true", "1", "yes")
        
        def get_int(tag: str, default: int = 0) -> int:
            elem = cpu_elem.find(tag)
            if elem is None or elem.text is None:
                return default
            try:
                return int(elem.text)
            except ValueError:
                return default
        
        return SVDCpuInfo(
            name=cpu_elem.findtext("name", ""),
            revision=cpu_elem.findtext("revision", ""),
            endian=cpu_elem.findtext("endian", "little"),
            mpu_present=get_bool("mpuPresent"),
            fpu_present=get_bool("fpuPresent"),
            nvic_prio_bits=get_int("nvicPrioBits", 4),
            vendor_systick=get_bool("vendorSystickConfig"),
        )
    
    def _parse_memories(self) -> list[SVDMemoryRegion]:
        """解析内存区域"""
        memories = []
        
        # SVD 文件通常不直接定义 Flash/RAM
        # 但我们可以从外设基地址推断
        # 或者使用默认值
        
        # 添加默认内存区域（STM32F4 典型配置）
        memories.append(SVDMemoryRegion(
            name="FLASH",
            start=0x08000000,
            size=1024 * 1024,  # 1MB
            access="rx",
        ))
        memories.append(SVDMemoryRegion(
            name="RAM",
            start=0x20000000,
            size=192 * 1024,  # 192KB
            access="rw",
        ))
        memories.append(SVDMemoryRegion(
            name="CCMRAM",
            start=0x10000000,
            size=64 * 1024,  # 64KB
            access="rw",
        ))
        
        return memories
    
    def _parse_peripherals(self) -> list[SVDPeripheral]:
        """解析外设信息"""
        peripherals = []
        
        for p_elem in self.root.findall(".//peripheral"):
            name = p_elem.findtext("name", "")
            description = p_elem.findtext("description", "")
            
            # 基地址
            base_addr_text = p_elem.findtext("baseAddress", "0")
            try:
                base_address = int(base_addr_text, 0)  # 支持十六进制
            except ValueError:
                base_address = 0
            
            # 地址块大小
            size = 0x400
            ab_elem = p_elem.find("addressBlock")
            if ab_elem is not None:
                size_text = ab_elem.findtext("size", "0x400")
                try:
                    size = int(size_text, 0)
                except ValueError:
                    size = 0x400
            
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
                
                interrupts.append(SVDInterrupt(
                    name=i_name,
                    description=i_desc,
                    value=i_value,
                ))
            
            peripherals.append(SVDPeripheral(
                name=name,
                description=description,
                base_address=base_address,
                size=size,
                interrupts=interrupts,
            ))
        
        return peripherals


class LinkerScriptGenerator:
    """链接脚本生成器（基于 SVD）"""
    
    def __init__(self, device: SVDDevice):
        self.device = device
    
    def generate(self, chip_config: dict = None) -> str:
        """生成链接脚本
        
        Args:
            chip_config: 芯片配置（可选，用于覆盖默认值）
        """
        # 获取内存配置
        flash_start, flash_size = self._get_flash_config(chip_config)
        ram_start, ram_size = self._get_ram_config(chip_config)
        ccm_start, ccm_size = self._get_ccm_config(chip_config)
        
        # 生成链接脚本
        content = f"""/*
 * 链接脚本 - {self.device.name}
 * 基于 SVD 文件自动生成
 * 
 * CPU: {self.device.cpu.name}
 * 字节序: {self.device.cpu.endian}
 * FPU: {'是' if self.device.cpu.fpu_present else '否'}
 */

/* 入口点 */
ENTRY(Reset_Handler)

/* 栈顶地址 */
_estack = ORIGIN(RAM) + LENGTH(RAM);

/* 堆栈大小 */
_Min_Heap_Size = 0x200;
_Min_Stack_Size = 0x400;

/* 内存定义 */
MEMORY
{{
"""
        
        # 添加 CCMRAM（如果存在）
        if ccm_size > 0:
            content += f"  CCMRAM (xrw) : ORIGIN = 0x{ccm_start:08X}, LENGTH = {ccm_size // 1024}K\n"
        
        content += f"""  RAM    (xrw) : ORIGIN = 0x{ram_start:08X}, LENGTH = {ram_size // 1024}K
  FLASH  (rx)  : ORIGIN = 0x{flash_start:08X}, LENGTH = {flash_size // 1024}K
}}

/* 段定义 */
SECTIONS
{{
  /* 中断向量表 */
  .isr_vector :
  {{
    . = ALIGN(4);
    KEEP(*(.isr_vector))
    . = ALIGN(4);
  }} >FLASH

  /* 代码段 */
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

  /* 只读数据 */
  .rodata :
  {{
    . = ALIGN(4);
    *(.rodata)
    *(.rodata*)
    . = ALIGN(4);
  }} >FLASH

  /* ARM 异常处理 */
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

  /* 初始化数组 */
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

  /* 初始化数据的加载地址 */
  _sidata = LOADADDR(.data);

  /* 已初始化数据 */
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
        
        # 添加 CCMRAM 段（如果存在）
        if ccm_size > 0:
            content += f"""
  /* CCM-RAM 段 */
  _siccmram = LOADADDR(.ccmram);

  .ccmram :
  {{
    . = ALIGN(4);
    _sccmram = .;
    *(.ccmram)
    *(.ccmram*)
    . = ALIGN(4);
    _eccmram = .;
  }} >CCMRAM AT> FLASH
"""
        
        content += """
  /* 未初始化数据 */
  . = ALIGN(4);
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

  /* 用户堆栈 */
  ._user_heap_stack :
  {
    . = ALIGN(8);
    PROVIDE(end = .);
    PROVIDE(_end = .);
    . = . + _Min_Heap_Size;
    . = . + _Min_Stack_Size;
    . = ALIGN(8);
  } >RAM

  /* 删除编译器库信息 */
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
    
    def _get_flash_config(self, chip_config: dict = None) -> tuple[int, int]:
        """获取 Flash 配置"""
        if chip_config:
            flash_kb = chip_config.get("flash_kb", 1024)
            return (0x08000000, flash_kb * 1024)
        
        # 默认值
        return (0x08000000, 1024 * 1024)
    
    def _get_ram_config(self, chip_config: dict = None) -> tuple[int, int]:
        """获取 RAM 配置"""
        if chip_config:
            ram_kb = chip_config.get("ram_kb", 192)
            return (0x20000000, ram_kb * 1024)
        
        # 默认值
        return (0x20000000, 192 * 1024)
    
    def _get_ccm_config(self, chip_config: dict = None) -> tuple[int, int]:
        """获取 CCMRAM 配置"""
        # CCMRAM 只有部分 STM32 有
        if chip_config:
            ccm_kb = chip_config.get("ccm_kb", 64)
            if ccm_kb > 0:
                return (0x10000000, ccm_kb * 1024)
        
        # 默认值（STM32F4 有 64KB CCMRAM）
        return (0x10000000, 64 * 1024)


class StartupGenerator:
    """启动代码生成器（基于 SVD）"""
    
    def __init__(self, device: SVDDevice):
        self.device = device
    
    def generate(self) -> str:
        """生成启动代码"""
        # 获取中断列表
        interrupts = self.device.interrupts
        
        # 生成中断向量表
        vector_table = self._generate_vector_table(interrupts)
        
        content = f"""/**
 * @file    startup_{self.device.name.lower()}.s
 * @brief   启动代码 - 基于 SVD 自动生成
 * @device  {self.device.name}
 * @cpu      {self.device.cpu.name}
 *
 * 自动生成，请勿手动修改
 */

  .syntax unified
  .cpu cortex-m4
  .fpu softvfp
  .thumb

.global g_pfnVectors
.global Default_Handler

/* 栈顶地址 */
.word _estack

/* 初始化段 */
.section .text.Reset_Handler
  .weak Reset_Handler
  .type Reset_Handler, %function
Reset_Handler:
  ldr   sp, =_estack

/* 拷贝 .data 段 */
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

/* 清零 .bss 段 */
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

/* 调用系统初始化 */
  bl SystemInit
/* 调用 main 函数 */
  bl main

LoopForever:
  b LoopForever

.size Reset_Handler, .-Reset_Handler

/* 默认中断处理函数 */
.section .text.Default_Handler,"ax",%progbits
Default_Handler:
Infinite_Loop:
  b Infinite_Loop
  .size Default_Handler, .-Default_Handler

/* 中断向量表 */
.section .isr_vector,"a",%progbits
  .type g_pfnVectors, %object
  .size g_pfnVectors, .-g_pfnVectors

g_pfnVectors:
  /* Cortex-M4 系统异常 */
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
        content += "  /* 外设中断 */\n"
        
        # 按中断号排序
        sorted_interrupts = sorted(interrupts, key=lambda x: x.value)
        
        for irq in sorted_interrupts:
            content += f"  .word {irq.name}_Handler  /* {irq.value}: {irq.description} */\n"
        
        content += """
/* 弱符号定义 */
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
        for irq in sorted_interrupts:
            content += f"  .weak {irq.name}_Handler\n"
            content += f"  .thumb_set {irq.name}_Handler, Default_Handler\n\n"
        
        return content
    
    def _generate_vector_table(self, interrupts: list[SVDInterrupt]) -> str:
        """生成中断向量表"""
        lines = []
        
        # 系统异常
        lines.append("  /* Cortex-M4 系统异常 */")
        lines.append("  .word _estack                /* 栈顶 */")
        lines.append("  .word Reset_Handler          /* 复位 */")
        lines.append("  .word NMI_Handler            /* NMI */")
        lines.append("  .word HardFault_Handler      /* 硬件错误 */")
        lines.append("  .word MemManage_Handler      /* 内存管理错误 */")
        lines.append("  .word BusFault_Handler       /* 总线错误 */")
        lines.append("  .word UsageFault_Handler     /* 用法错误 */")
        lines.append("  .word 0                      /* 保留 */")
        lines.append("  .word 0                      /* 保留 */")
        lines.append("  .word 0                      /* 保留 */")
        lines.append("  .word 0                      /* 保留 */")
        lines.append("  .word SVC_Handler            /* SVCall */")
        lines.append("  .word DebugMon_Handler       /* 调试监视器 */")
        lines.append("  .word 0                      /* 保留 */")
        lines.append("  .word PendSV_Handler         /* PendSV */")
        lines.append("  .word SysTick_Handler        /* SysTick */")
        lines.append("")
        lines.append("  /* 外设中断 */")
        
        # 外设中断
        for irq in sorted(interrupts, key=lambda x: x.value):
            lines.append(f"  .word {irq.name}_Handler  /* {irq.value}: {irq.description} */")
        
        return "\n".join(lines)


# ─── 便捷函数 ────────────────────────────────────────────────────────────────

def parse_svd(svd_path: Path) -> SVDDevice:
    """解析 SVD 文件"""
    parser = SVDParser(svd_path)
    return parser.parse()


def generate_linker_from_svd(
    svd_path: Path,
    chip_config: dict = None,
) -> str:
    """从 SVD 文件生成链接脚本"""
    device = parse_svd(svd_path)
    generator = LinkerScriptGenerator(device)
    return generator.generate(chip_config)


def generate_startup_from_svd(svd_path: Path) -> str:
    """从 SVD 文件生成启动代码"""
    device = parse_svd(svd_path)
    generator = StartupGenerator(device)
    return generator.generate()


# ─── SVD 数据管理 ────────────────────────────────────────────────────────────

class SVDManager:
    """SVD 数据管理器"""
    
    def __init__(self, svd_dir: Optional[Path] = None):
        self.svd_dir = svd_dir or Path.home() / ".efw" / "svd"
        self.svd_dir.mkdir(parents=True, exist_ok=True)
    
    def list_devices(self) -> list[str]:
        """列出可用设备"""
        devices = []
        for svd_file in self.svd_dir.rglob("*.svd"):
            devices.append(svd_file.stem)
        return sorted(devices)
    
    def find_svd(self, device_name: str) -> Optional[Path]:
        """查找设备 SVD 文件"""
        # 精确匹配
        for svd_file in self.svd_dir.rglob("*.svd"):
            if svd_file.stem.upper() == device_name.upper():
                return svd_file
        
        # 模糊匹配
        device_upper = device_name.upper()
        for svd_file in self.svd_dir.rglob("*.svd"):
            if device_upper in svd_file.stem.upper():
                return svd_file
        
        return None
    
    def download_svd_data(self) -> bool:
        """下载 SVD 数据仓库"""
        import subprocess
        
        url = "https://github.com/cmsis-svd/cmsis-svd-data/archive/refs/heads/main.zip"
        zip_path = self.svd_dir / "svd-data.zip"
        
        print(f"下载 SVD 数据...")
        try:
            import urllib.request
            urllib.request.urlretrieve(url, str(zip_path))
        except Exception as e:
            print(f"下载失败: {e}")
            return False
        
        print("解压中...")
        try:
            import zipfile
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(self.svd_dir)
            
            # 移动数据目录
            extracted = self.svd_dir / "cmsis-svd-data-main" / "data"
            if extracted.exists():
                import shutil
                shutil.move(str(extracted), str(self.svd_dir / "data"))
                shutil.rmtree(self.svd_dir / "cmsis-svd-data-main")
            
            zip_path.unlink()
            print("✓ SVD 数据已下载")
            return True
        except Exception as e:
            print(f"解压失败: {e}")
            return False
