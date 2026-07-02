#!/usr/bin/env python3
"""
EFW 硬件配置工具

管理 MCU 引脚配置、外设配置、时钟配置等。

功能：
- 从 MCU 数据库加载引脚信息
- 引脚功能分配和冲突检测
- 外设配置管理
- 生成配置代码
- 与仿真器集成

使用方式：
  # 查看芯片引脚
  python3 tools/efw.py hw pins --chip STM32F407VGT6
  
  # 配置引脚
  python3 tools/efw.py hw config --chip STM32F407VGT6 --assign PA0=ADC_IN0,PB6=TIM4_CH1
  
  # 检查冲突
  python3 tools/efw.py hw check --chip STM32F407VGT6 --config hw_config.json
  
  # 生成代码
  python3 tools/efw.py hw generate --chip STM32F407VGT6 --config hw_config.json -o src/
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


# ─── 引脚功能定义 ────────────────────────────────────────────────────────────

class PinFunction:
    """引脚功能类型"""
    GPIO = "gpio"
    ADC = "adc"
    PWM = "pwm"
    UART_TX = "uart_tx"
    UART_RX = "uart_rx"
    I2C_SDA = "i2c_sda"
    I2C_SCL = "i2c_scl"
    SPI_MOSI = "spi_mosi"
    SPI_MISO = "spi_miso"
    SPI_SCK = "spi_sck"
    SPI_NSS = "spi_nss"
    TIM_CH = "tim_ch"
    EXTI = "exti"
    SWD = "swd"
    USB = "usb"
    CAN = "can"


@dataclass
class PinAssignment:
    """引脚分配"""
    pin_name: str               # 引脚名称 (如 PA0)
    function: str               # 功能类型
    peripheral: str = ""        # 外设名称 (如 ADC1)
    channel: str = ""           # 通道 (如 IN0)
    label: str = ""             # 用户标签 (如 "line_sensor_0")
    config: dict = field(default_factory=dict)  # 额外配置
    
    @property
    def full_function(self) -> str:
        """完整功能描述"""
        if self.peripheral:
            return f"{self.peripheral}_{self.channel}"
        return self.function


@dataclass
class PinConflict:
    """引脚冲突"""
    pin_name: str
    function1: str
    function2: str
    description: str


@dataclass
class HardwareConfig:
    """硬件配置"""
    chip: str
    assignments: dict[str, PinAssignment] = field(default_factory=dict)
    peripherals: dict[str, dict] = field(default_factory=dict)
    clock_config: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "chip": self.chip,
            "assignments": {
                name: {
                    "pin": a.pin_name,
                    "function": a.function,
                    "peripheral": a.peripheral,
                    "channel": a.channel,
                    "label": a.label,
                    "config": a.config,
                }
                for name, a in self.assignments.items()
            },
            "peripherals": self.peripherals,
            "clock_config": self.clock_config,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "HardwareConfig":
        config = cls(chip=data.get("chip", ""))
        
        for name, a_data in data.get("assignments", {}).items():
            config.assignments[name] = PinAssignment(
                pin_name=a_data.get("pin", ""),
                function=a_data.get("function", ""),
                peripheral=a_data.get("peripheral", ""),
                channel=a_data.get("channel", ""),
                label=a_data.get("label", ""),
                config=a_data.get("config", {}),
            )
        
        config.peripherals = data.get("peripherals", {})
        config.clock_config = data.get("clock_config", {})
        
        return config


# ─── 硬件配置管理器 ──────────────────────────────────────────────────────────

class HardwareConfigManager:
    """硬件配置管理器"""
    
    def __init__(self, data_dir: Optional[Path] = None):
        # 从 tools/hw/config.py 向上找到项目根目录
        self.data_dir = data_dir or Path(__file__).parent.parent.parent / "data"
        self.mcu_dir = self.data_dir / "mcu"
        
        # 缓存
        self._chip_data: dict[str, dict] = {}
    
    def load_chip(self, chip_name: str) -> Optional[dict]:
        """加载芯片数据"""
        if chip_name in self._chip_data:
            return self._chip_data[chip_name]
        
        index_path = self.mcu_dir / "index.json"
        if not index_path.exists():
            return None
        
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)
        
        if chip_name not in index:
            return None
        
        chip_path = self.mcu_dir / index[chip_name]["path"]
        if not chip_path.exists():
            return None
        
        with open(chip_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        self._chip_data[chip_name] = data
        return data
    
    def get_pin_info(self, chip_name: str, pin_name: str) -> Optional[dict]:
        """获取引脚信息"""
        chip_data = self.load_chip(chip_name)
        if not chip_data:
            return None
        
        pins = chip_data.get("pins", {})
        
        # 精确匹配
        if pin_name in pins:
            return pins[pin_name]
        
        # 模糊匹配（如 PA0 匹配 PA0-WKUP）
        for pin_key, pin_info in pins.items():
            if pin_key.startswith(pin_name):
                return pin_info
        
        return None
    
    def get_available_functions(self, chip_name: str, pin_name: str) -> list[dict]:
        """获取引脚可用功能"""
        pin_info = self.get_pin_info(chip_name, pin_name)
        if not pin_info:
            return []
        
        functions = []
        funcs = pin_info.get("functions", {})
        
        # GPIO
        if funcs.get("gpio"):
            functions.append({"type": PinFunction.GPIO, "name": "GPIO"})
        
        # ADC
        for ch in funcs.get("adc", []):
            functions.append({
                "type": PinFunction.ADC,
                "name": f"ADC_IN{ch}",
                "peripheral": "ADC",
                "channel": f"IN{ch}",
            })
        
        # PWM
        for tim in funcs.get("pwm", []):
            functions.append({
                "type": PinFunction.PWM,
                "name": tim,
                "peripheral": tim.split("_")[0],
                "channel": tim.split("_")[1] if "_" in tim else "",
            })
        
        # UART
        uart = funcs.get("uart", {})
        if uart.get("tx"):
            functions.append({"type": PinFunction.UART_TX, "name": "UART_TX"})
        if uart.get("rx"):
            functions.append({"type": PinFunction.UART_RX, "name": "UART_RX"})
        
        # I2C
        i2c = funcs.get("i2c", {})
        if i2c.get("sda"):
            functions.append({"type": PinFunction.I2C_SDA, "name": "I2C_SDA"})
        if i2c.get("scl"):
            functions.append({"type": PinFunction.I2C_SCL, "name": "I2C_SCL"})
        
        # SPI
        spi = funcs.get("spi", {})
        if spi.get("mosi"):
            functions.append({"type": PinFunction.SPI_MOSI, "name": "SPI_MOSI"})
        if spi.get("miso"):
            functions.append({"type": PinFunction.SPI_MISO, "name": "SPI_MISO"})
        if spi.get("sck"):
            functions.append({"type": PinFunction.SPI_SCK, "name": "SPI_SCK"})
        if spi.get("nss"):
            functions.append({"type": PinFunction.SPI_NSS, "name": "SPI_NSS"})
        
        return functions
    
    def check_conflicts(self, config: HardwareConfig) -> list[PinConflict]:
        """检查引脚冲突"""
        conflicts = []
        
        # 检查同一引脚是否被多次分配
        pin_usage: dict[str, list[tuple[str, str]]] = {}
        
        for name, assignment in config.assignments.items():
            pin = assignment.pin_name
            if pin not in pin_usage:
                pin_usage[pin] = []
            pin_usage[pin].append((name, assignment.full_function))
        
        for pin, usages in pin_usage.items():
            if len(usages) > 1:
                for i in range(len(usages)):
                    for j in range(i + 1, len(usages)):
                        conflicts.append(PinConflict(
                            pin_name=pin,
                            function1=usages[i][1],
                            function2=usages[j][1],
                            description=f"引脚 {pin} 被 {usages[i][0]} 和 {usages[j][0]} 同时使用",
                        ))
        
        # 检查功能是否可用
        for name, assignment in config.assignments.items():
            available = self.get_available_functions(config.chip, assignment.pin_name)
            available_names = [f["name"] for f in available]
            
            # 检查精确匹配或前缀匹配
            found = False
            for avail_name in available_names:
                if assignment.full_function == avail_name:
                    found = True
                    break
                # 检查前缀匹配（如 ADC_IN0 匹配 ADC_IN0）
                if assignment.function == PinFunction.ADC and avail_name.startswith("ADC_"):
                    found = True
                    break
                # 检查 GPIO 匹配
                if assignment.function == PinFunction.GPIO and avail_name == "GPIO":
                    found = True
                    break
                # 检查 PWM 匹配
                if assignment.function == PinFunction.PWM and "_" in avail_name:
                    found = True
                    break
                # 检查 UART TX 匹配
                if assignment.function == PinFunction.UART_TX and avail_name == "UART_TX":
                    found = True
                    break
                # 检查 UART RX 匹配
                if assignment.function == PinFunction.UART_RX and avail_name == "UART_RX":
                    found = True
                    break
                # 检查 I2C 匹配
                if assignment.function in (PinFunction.I2C_SDA, PinFunction.I2C_SCL) and avail_name.startswith("I2C_"):
                    found = True
                    break
                # 检查 SPI 匹配
                if assignment.function.startswith("spi_") and avail_name.startswith("SPI_"):
                    found = True
                    break
            
            if not found:
                conflicts.append(PinConflict(
                    pin_name=assignment.pin_name,
                    function1=assignment.full_function,
                    function2="",
                    description=f"引脚 {assignment.pin_name} 不支持功能 {assignment.full_function}",
                ))
        
        return conflicts
    
    def generate_pin_config(self, config: HardwareConfig) -> str:
        """生成引脚配置代码"""
        lines = [
            "/**",
            " * @file    pin_config.h",
            " * @brief   引脚配置 - 自动生成",
            f" * @chip    {config.chip}",
            " */",
            "",
            "#ifndef PIN_CONFIG_H",
            "#define PIN_CONFIG_H",
            "",
            "/* ==================================================================",
            " *  引脚定义",
            " * ================================================================== */",
            "",
        ]
        
        # 按功能分组
        gpio_pins = []
        adc_pins = []
        pwm_pins = []
        uart_pins = []
        i2c_pins = []
        spi_pins = []
        
        for name, assignment in config.assignments.items():
            label = assignment.label or name
            
            if assignment.function == PinFunction.GPIO:
                gpio_pins.append((label, assignment.pin_name))
            elif assignment.function == PinFunction.ADC:
                adc_pins.append((label, assignment.pin_name, assignment.channel))
            elif assignment.function == PinFunction.PWM:
                pwm_pins.append((label, assignment.pin_name, assignment.full_function))
            elif assignment.function in (PinFunction.UART_TX, PinFunction.UART_RX):
                uart_pins.append((label, assignment.pin_name, assignment.function))
            elif assignment.function in (PinFunction.I2C_SDA, PinFunction.I2C_SCL):
                i2c_pins.append((label, assignment.pin_name, assignment.function))
            elif assignment.function in (PinFunction.SPI_MOSI, PinFunction.SPI_MISO, 
                                         PinFunction.SPI_SCK, PinFunction.SPI_NSS):
                spi_pins.append((label, assignment.pin_name, assignment.function))
        
        # GPIO 引脚
        if gpio_pins:
            lines.append("/* GPIO 引脚 */")
            for label, pin in gpio_pins:
                lines.append(f"#define PIN_{label.upper():<20} \"{pin}\"")
            lines.append("")
        
        # ADC 引脚
        if adc_pins:
            lines.append("/* ADC 引脚 */")
            for label, pin, channel in adc_pins:
                lines.append(f"#define PIN_{label.upper():<20} \"{pin}\"")
                lines.append(f"#define {label.upper()}_CHANNEL  {channel.replace('IN', '')}")
            lines.append("")
        
        # PWM 引脚
        if pwm_pins:
            lines.append("/* PWM 引脚 */")
            for label, pin, timer in pwm_pins:
                lines.append(f"#define PIN_{label.upper():<20} \"{pin}\"")
                lines.append(f"#define {label.upper()}_TIMER   \"{timer.split('_')[0]}\"")
            lines.append("")
        
        # UART 引脚
        if uart_pins:
            lines.append("/* UART 引脚 */")
            for label, pin, func in uart_pins:
                suffix = "TX" if func == PinFunction.UART_TX else "RX"
                lines.append(f"#define PIN_{label.upper()}_{suffix:<15} \"{pin}\"")
            lines.append("")
        
        # I2C 引脚
        if i2c_pins:
            lines.append("/* I2C 引脚 */")
            for label, pin, func in i2c_pins:
                suffix = "SDA" if func == PinFunction.I2C_SDA else "SCL"
                lines.append(f"#define PIN_{label.upper()}_{suffix:<15} \"{pin}\"")
            lines.append("")
        
        # SPI 引脚
        if spi_pins:
            lines.append("/* SPI 引脚 */")
            for label, pin, func in spi_pins:
                suffix = func.replace("spi_", "").upper()
                lines.append(f"#define PIN_{label.upper()}_{suffix:<15} \"{pin}\"")
            lines.append("")
        
        lines.append("#endif /* PIN_CONFIG_H */")
        
        return "\n".join(lines)
    
    def generate_hal_init(self, config: HardwareConfig) -> str:
        """生成 HAL 初始化代码"""
        lines = [
            "/**",
            " * @file    hal_init.c",
            " * @brief   HAL 初始化 - 自动生成",
            f" * @chip    {config.chip}",
            " */",
            "",
            '#include "pin_config.h"',
            '#include "efw/efw.h"',
            "",
            "void hal_init(void) {",
            "    /* GPIO 初始化 */",
        ]
        
        for name, assignment in config.assignments.items():
            if assignment.function == PinFunction.GPIO:
                label = assignment.label or name
                lines.append(f'    efw_hal_gpio_init("{label}", PIN_{label.upper()});')
        
        lines.append("")
        lines.append("    /* ADC 初始化 */")
        
        for name, assignment in config.assignments.items():
            if assignment.function == PinFunction.ADC:
                label = assignment.label or name
                lines.append(f'    efw_hal_adc_init("{label}", PIN_{label.upper()});')
        
        lines.append("")
        lines.append("    /* PWM 初始化 */")
        
        for name, assignment in config.assignments.items():
            if assignment.function == PinFunction.PWM:
                label = assignment.label or name
                lines.append(f'    efw_hal_pwm_init("{label}", PIN_{label.upper()}, 1000);')
        
        lines.append("}")
        
        return "\n".join(lines)


# ─── CLI 入口 ────────────────────────────────────────────────────────────────

def cmd_hw(argv: list[str]) -> int:
    """硬件配置命令"""
    if not argv:
        print_hw_help()
        return 0
    
    subcmd = argv[0]
    rest = argv[1:]
    
    if subcmd in {"help", "-h", "--help"}:
        print_hw_help()
        return 0
    
    # 解析全局参数
    data_dir = None
    chip = None
    
    i = 0
    while i < len(rest):
        if rest[i] == "--data-dir" and i + 1 < len(rest):
            data_dir = Path(rest[i + 1])
            i += 2
        elif rest[i] == "--chip" and i + 1 < len(rest):
            chip = rest[i + 1]
            i += 2
        else:
            i += 1
    
    manager = HardwareConfigManager(data_dir)
    
    if subcmd == "pins":
        if not chip:
            print("错误: 请指定芯片 (--chip)")
            return 1
        
        chip_data = manager.load_chip(chip)
        if not chip_data:
            print(f"错误: 未找到芯片 {chip}")
            return 1
        
        pins = chip_data.get("pins", {})
        
        print(f"\n芯片 {chip} 引脚列表:")
        print("=" * 70)
        print(f"{'引脚':<10} {'位置':<6} {'类型':<8} {'功能':<40}")
        print("-" * 70)
        
        for pin_name, pin_info in sorted(pins.items()):
            pos = pin_info.get("pos", "")
            pin_type = pin_info.get("type", "")
            funcs = pin_info.get("functions", {})
            
            # 构建功能列表
            func_list = []
            if funcs.get("gpio"):
                func_list.append("GPIO")
            for ch in funcs.get("adc", []):
                func_list.append(f"ADC_IN{ch}")
            for tim in funcs.get("pwm", []):
                func_list.append(tim)
            
            func_str = ", ".join(func_list[:3])
            if len(func_list) > 3:
                func_str += "..."
            
            print(f"{pin_name:<10} {pos:<6} {pin_type:<8} {func_str:<40}")
        
        return 0
    
    elif subcmd == "check":
        # 加载配置文件
        config_file = None
        for i, arg in enumerate(rest):
            if arg == "--config" and i + 1 < len(rest):
                config_file = Path(rest[i + 1])
        
        if not config_file:
            print("错误: 请指定配置文件 (--config)")
            return 1
        
        if not config_file.exists():
            print(f"错误: 配置文件不存在: {config_file}")
            return 1
        
        with open(config_file, "r", encoding="utf-8") as f:
            config_data = json.load(f)
        
        config = HardwareConfig.from_dict(config_data)
        
        # 检查冲突
        conflicts = manager.check_conflicts(config)
        
        if not conflicts:
            print("✓ 未发现引脚冲突")
        else:
            print(f"发现 {len(conflicts)} 个冲突:")
            for conflict in conflicts:
                print(f"  ✗ {conflict.description}")
        
        return 0
    
    elif subcmd == "generate":
        # 加载配置文件
        config_file = None
        output_dir = Path(".")
        
        i = 0
        while i < len(rest):
            if rest[i] == "--config" and i + 1 < len(rest):
                config_file = Path(rest[i + 1])
                i += 2
            elif rest[i] in {"-o", "--output"} and i + 1 < len(rest):
                output_dir = Path(rest[i + 1])
                i += 2
            else:
                i += 1
        
        if not config_file:
            print("错误: 请指定配置文件 (--config)")
            return 1
        
        with open(config_file, "r", encoding="utf-8") as f:
            config_data = json.load(f)
        
        config = HardwareConfig.from_dict(config_data)
        
        # 生成代码
        output_dir.mkdir(parents=True, exist_ok=True)
        
        pin_config = manager.generate_pin_config(config)
        (output_dir / "pin_config.h").write_text(pin_config)
        
        hal_init = manager.generate_hal_init(config)
        (output_dir / "hal_init.c").write_text(hal_init)
        
        print(f"✓ 代码已生成:")
        print(f"  {output_dir / 'pin_config.h'}")
        print(f"  {output_dir / 'hal_init.c'}")
        
        return 0
    
    else:
        print(f"未知命令: {subcmd}")
        return 1


def print_hw_help():
    """打印帮助信息"""
    print("""
EFW 硬件配置工具

用法: python3 tools/efw.py hw <subcommand>

子命令:
  pins                列出芯片引脚
  check               检查引脚冲突
  generate            生成配置代码

选项:
  --chip CHIP         芯片名称
  --config FILE       配置文件路径
  -o, --output DIR    输出目录

示例:
  # 查看引脚
  python3 tools/efw.py hw pins --chip STM32F407VGT6
  
  # 检查冲突
  python3 tools/efw.py hw check --chip STM32F407VGT6 --config hw.json
  
  # 生成代码
  python3 tools/efw.py hw generate --config hw.json -o src/
""")
