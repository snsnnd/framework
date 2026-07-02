"""
MCU 核心模拟器

模拟 STM32F4 的核心功能：
- CPU 指令执行
- 内存管理
- 时钟系统
- 中断控制
- DMA

支持从 data/mcu/ 加载真实芯片配置
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from .chip_db import ChipDatabase, get_chip_database


class MCUType(str, Enum):
    """MCU 类型"""
    STM32F103 = "STM32F103"  # Cortex-M3, 72MHz
    STM32F407 = "STM32F407"  # Cortex-M4, 168MHz
    STM32F411 = "STM32F411"  # Cortex-M4, 100MHz
    ESP32 = "ESP32"          # Xtensa LX6, 240MHz


@dataclass
class ClockConfig:
    """时钟配置"""
    sysclk_hz: int = 168_000_000
    hclk_hz: int = 168_000_000
    pclk1_hz: int = 42_000_000
    pclk2_hz: int = 84_000_000


@dataclass
class GPIOConfig:
    """GPIO 配置"""
    mode: str = "input"
    pull: str = "none"
    speed: str = "low"
    output_type: str = "push_pull"
    value: int = 0


@dataclass
class ADCConfig:
    """ADC 配置"""
    resolution: int = 12
    channels: dict[int, float] = field(default_factory=dict)
    triggered: bool = False
    last_value: int = 0


@dataclass
class PWMConfig:
    """PWM 配置"""
    frequency_hz: int = 1000
    duty_cycle: float = 0.0
    enabled: bool = False


@dataclass
class UARTConfig:
    """UART 配置"""
    baudrate: int = 115200
    tx_buffer: bytearray = field(default_factory=bytearray)
    rx_buffer: bytearray = field(default_factory=bytearray)
    tx_callback: Optional[Callable] = None


@dataclass
class TimerConfig:
    """定时器配置"""
    prescaler: int = 0
    period: int = 0
    counter: int = 0
    auto_reload: bool = True
    callback: Optional[Callable] = None


class InterruptController:
    """中断控制器"""
    
    def __init__(self):
        self.pending: dict[int, bool] = {}
        self.enabled: dict[int, bool] = {}
        self.priority: dict[int, int] = {}
        self.handlers: dict[int, Callable] = {}
        self.nesting_level = 0
    
    def enable(self, irq: int):
        self.enabled[irq] = True
    
    def disable(self, irq: int):
        self.enabled[irq] = False
    
    def set_priority(self, irq: int, priority: int):
        self.priority[irq] = priority
    
    def register_handler(self, irq: int, handler: Callable):
        self.handlers[irq] = handler
    
    def trigger(self, irq: int):
        if self.enabled.get(irq, False):
            self.pending[irq] = True
    
    def clear(self, irq: int):
        self.pending[irq] = False
    
    def check_and_execute(self) -> bool:
        if not self.pending:
            return False
        
        highest_prio = -1
        highest_irq = -1
        
        for irq, pending in self.pending.items():
            if pending:
                prio = self.priority.get(irq, 255)
                if prio > highest_prio:
                    highest_prio = prio
                    highest_irq = irq
        
        if highest_irq >= 0:
            self.nesting_level += 1
            handler = self.handlers.get(highest_irq)
            if handler:
                handler()
            self.pending[highest_irq] = False
            self.nesting_level -= 1
            return True
        
        return False


class MCUSimulator:
    """MCU 模拟器主类
    
    支持两种初始化方式：
    1. 使用预定义类型：MCUSimulator(MCUType.STM32F407)
    2. 使用真实芯片数据：MCUSimulator.from_chip("STM32F407VGT6")
    """
    
    def __init__(self, mcu_type: MCUType = MCUType.STM32F407):
        self.mcu_type = mcu_type
        self.chip_name: str = ""  # 真实芯片名称
        self.chip_data: Optional[dict] = None  # 真实芯片数据
        self.running = False
        self.paused = False
        
        self.clock = ClockConfig()
        if mcu_type == MCUType.STM32F103:
            self.clock.sysclk_hz = 72_000_000
        elif mcu_type == MCUType.STM32F411:
            self.clock.sysclk_hz = 100_000_000
        
        self.flash = bytearray(1024 * 1024)
        self.sram = bytearray(128 * 1024)
        self.stack_pointer = 0x20020000
        
        self.gpio: dict[str, GPIOConfig] = {}
        self.adc: dict[int, ADCConfig] = {}
        self.pwm: dict[str, PWMConfig] = {}
        self.uart: dict[int, UARTConfig] = {}
        self.timers: dict[int, TimerConfig] = {}
        
        self.interrupts = InterruptController()
        
        self.cycle_count = 0
        self.instruction_count = 0
        self.start_time = 0
        self.elapsed_us = 0
        
        self.breakpoints: set[int] = set()
        self.watchpoints: set[int] = set()
        self.debug_mode = False
        
        self.on_tick: Optional[Callable] = None
        self.on_interrupt: Optional[Callable] = None
    
    @classmethod
    def from_chip(cls, chip_name: str, db: Optional[ChipDatabase] = None) -> "MCUSimulator":
        """从芯片数据库创建 MCU 模拟器
        
        Args:
            chip_name: 芯片名称（如 "STM32F407VGT6"）
            db: 芯片数据库实例（可选）
        
        Returns:
            配置好的 MCUSimulator 实例
        
        示例：
            mcu = MCUSimulator.from_chip("STM32F407VGT6")
        """
        # 获取数据库
        if db is None:
            db = get_chip_database()
        
        # 加载芯片数据
        chip_data = db.load_chip(chip_name)
        if not chip_data:
            raise ValueError(f"未找到芯片: {chip_name}")
        
        # 确定 MCU 类型
        family = chip_data.get("family", "")
        if "F1" in family:
            mcu_type = MCUType.STM32F103
        elif "F4" in family:
            mcu_type = MCUType.STM32F407
        elif "G4" in family:
            mcu_type = MCUType.STM32F411  # 使用 F411 作为替代
        else:
            mcu_type = MCUType.STM32F407
        
        # 创建实例
        instance = cls(mcu_type)
        instance.chip_name = chip_name
        instance.chip_data = chip_data
        
        # 配置时钟
        instance.clock.sysclk_hz = chip_data.get("frequency_mhz", 168) * 1_000_000
        
        # 配置内存
        flash_kb = chip_data.get("flash_kb", 1024)
        ram_kb = chip_data.get("ram_kb", 256)
        instance.flash = bytearray(flash_kb * 1024)
        instance.sram = bytearray(ram_kb * 1024)
        
        return instance
    
    @classmethod
    def from_chip_auto(cls) -> "MCUSimulator":
        """自动选择芯片创建模拟器
        
        如果数据库只有一个芯片，直接使用；
        如果有多个芯片，让用户选择。
        """
        db = get_chip_database()
        
        if not db.available:
            print("芯片数据库不可用，使用默认配置")
            return cls(MCUType.STM32F407)
        
        chips = db.list_chips()
        
        if len(chips) == 0:
            print("没有可用芯片，使用默认配置")
            return cls(MCUType.STM32F407)
        
        if len(chips) == 1:
            print(f"使用唯一可用芯片: {chips[0]}")
            return cls.from_chip(chips[0], db)
        
        # 多个芯片，让用户选择
        print(f"\n可用芯片 ({len(chips)} 个):")
        for i, chip in enumerate(chips, 1):
            info = db.get_chip_info(chip)
            print(f"  {i}. {chip} ({info.get('family')}, {info.get('frequency_mhz')} MHz)")
        
        while True:
            try:
                choice = input("\n请选择芯片编号: ").strip()
                idx = int(choice) - 1
                if 0 <= idx < len(chips):
                    return cls.from_chip(chips[idx], db)
                print("无效编号，请重新输入")
            except ValueError:
                print("请输入数字")
            except KeyboardInterrupt:
                print("\n使用默认配置")
                return cls(MCUType.STM32F407)
    
    def get_chip_info(self) -> dict:
        """获取芯片信息"""
        if self.chip_data:
            return {
                "name": self.chip_name,
                "family": self.chip_data.get("family", ""),
                "core": self.chip_data.get("core", ""),
                "frequency_mhz": self.chip_data.get("frequency_mhz", 0),
                "flash_kb": self.chip_data.get("flash_kb", 0),
                "ram_kb": self.chip_data.get("ram_kb", 0),
                "package": self.chip_data.get("package", ""),
                "gpio_count": self.chip_data.get("gpio_count", 0),
            }
        return {
            "type": self.mcu_type.value,
            "sysclk_hz": self.clock.sysclk_hz,
        }
    
    def init_gpio(self, port: str, pin: int, mode: str = "input", pull: str = "none"):
        name = f"{port}{pin}"
        self.gpio[name] = GPIOConfig(mode=mode, pull=pull)
        return self.gpio[name]
    
    def gpio_write(self, port: str, pin: int, value: int):
        name = f"{port}{pin}"
        if name in self.gpio:
            self.gpio[name].value = value & 1
    
    def gpio_read(self, port: str, pin: int) -> int:
        name = f"{port}{pin}"
        if name in self.gpio:
            return self.gpio[name].value
        return 0
    
    def init_adc(self, channel: int, resolution: int = 12):
        self.adc[channel] = ADCConfig(resolution=resolution)
        return self.adc[channel]
    
    def adc_read(self, channel: int) -> int:
        if channel in self.adc:
            config = self.adc[channel]
            voltage = config.channels.get(channel, 0.0)
            max_value = (1 << config.resolution) - 1
            return int(voltage / 3.3 * max_value)
        return 0
    
    def adc_set_voltage(self, channel: int, voltage: float):
        if channel in self.adc:
            self.adc[channel].channels[channel] = max(0.0, min(3.3, voltage))
    
    def init_pwm(self, timer: str, frequency_hz: int = 1000):
        self.pwm[timer] = PWMConfig(frequency_hz=frequency_hz)
        return self.pwm[timer]
    
    def pwm_set_duty(self, timer: str, duty_cycle: float):
        if timer in self.pwm:
            self.pwm[timer].duty_cycle = max(0.0, min(1.0, duty_cycle))
    
    def init_uart(self, port: int, baudrate: int = 115200):
        self.uart[port] = UARTConfig(baudrate=baudrate)
        return self.uart[port]
    
    def uart_send(self, port: int, data: bytes):
        if port in self.uart:
            self.uart[port].tx_buffer.extend(data)
            self.interrupts.trigger(37 if port == 1 else 38)
    
    def uart_receive(self, port: int, data: bytes):
        if port in self.uart:
            self.uart[port].rx_buffer.extend(data)
            self.interrupts.trigger(37 if port == 1 else 38)
    
    def uart_get_tx(self, port: int) -> bytes:
        if port in self.uart:
            data = bytes(self.uart[port].tx_buffer)
            self.uart[port].tx_buffer.clear()
            return data
        return b""
    
    def init_timer(self, timer_id: int, prescaler: int, period: int):
        self.timers[timer_id] = TimerConfig(prescaler=prescaler, period=period)
        return self.timers[timer_id]
    
    def timer_start(self, timer_id: int):
        if timer_id in self.timers:
            self.timers[timer_id].counter = 0
    
    def timer_stop(self, timer_id: int):
        pass
    
    def tick(self, cycles: int = 1):
        for _ in range(cycles):
            self.cycle_count += 1
            self.instruction_count += 1
            
            for timer_id, timer in self.timers.items():
                timer.counter += 1
                if timer.counter >= timer.period:
                    timer.counter = 0
                    if timer.callback:
                        timer.callback()
                    self.interrupts.trigger(28 + timer_id)
            
            self.interrupts.check_and_execute()
            
            if self.on_tick:
                self.on_tick()
    
    def run(self, duration_us: int = 1000):
        cycles_per_us = self.clock.sysclk_hz // 1_000_000
        total_cycles = duration_us * cycles_per_us
        
        self.start_time = time.monotonic_ns()
        self.tick(total_cycles)
        self.elapsed_us += duration_us
    
    def get_stats(self) -> dict:
        return {
            "mcu_type": self.mcu_type.value,
            "sysclk_hz": self.clock.sysclk_hz,
            "cycle_count": self.cycle_count,
            "instruction_count": self.instruction_count,
            "elapsed_us": self.elapsed_us,
            "gpio_count": len(self.gpio),
            "adc_count": len(self.adc),
            "pwm_count": len(self.pwm),
            "uart_count": len(self.uart),
            "timer_count": len(self.timers),
        }
