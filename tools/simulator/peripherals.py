"""
外设模拟模块

模拟 STM32 的各种外设：
- GPIO（通用输入输出）
- ADC（模数转换）
- PWM（脉宽调制）
- UART（串口）
- I2C（I2C 总线）
- SPI（SPI 总线）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class GPIOPort:
    """GPIO 端口"""
    port: str           # 端口名（A, B, C...）
    pin: int            # 引脚号（0-15）
    mode: str = "input" # input/output/alternate/analog
    pull: str = "none"  # none/up/down
    value: int = 0      # 当前值
    callback: Optional[Callable] = None
    
    @property
    def name(self) -> str:
        return f"{self.port}{self.pin}"
    
    def write(self, value: int):
        """写入值"""
        self.value = value & 1
        if self.callback:
            self.callback(self.name, self.value)
    
    def read(self) -> int:
        """读取值"""
        return self.value


@dataclass
class ADCChannel:
    """ADC 通道"""
    channel: int            # 通道号
    resolution: int = 12    # 分辨率（位）
    voltage: float = 0.0    # 输入电压（0-3.3V）
    value: int = 0          # 转换后的数字值
    
    @property
    def name(self) -> str:
        return f"ADC_CH{self.channel}"
    
    def set_voltage(self, voltage: float):
        """设置输入电压"""
        self.voltage = max(0.0, min(3.3, voltage))
        max_value = (1 << self.resolution) - 1
        self.value = int(self.voltage / 3.3 * max_value)
    
    def read(self) -> int:
        """读取数字值"""
        return self.value


@dataclass
class PWMOutput:
    """PWM 输出"""
    timer: str              # 定时器名（TIM1, TIM2...）
    frequency_hz: int = 1000
    duty_cycle: float = 0.0 # 0.0 - 1.0
    enabled: bool = True
    
    @property
    def name(self) -> str:
        return self.timer
    
    def set_duty(self, duty: float):
        """设置占空比"""
        self.duty_cycle = max(0.0, min(1.0, duty))
    
    def set_frequency(self, freq: int):
        """设置频率"""
        self.frequency_hz = max(1, freq)


@dataclass
class UARTPort:
    """UART 端口"""
    port: int               # 端口号（1, 2, 3...）
    baudrate: int = 115200
    tx_buffer: bytearray = field(default_factory=bytearray)
    rx_buffer: bytearray = field(default_factory=bytearray)
    tx_callback: Optional[Callable] = None
    rx_callback: Optional[Callable] = None
    
    @property
    def name(self) -> str:
        return f"UART{self.port}"
    
    def send(self, data: bytes):
        """发送数据"""
        self.tx_buffer.extend(data)
        if self.tx_callback:
            self.tx_callback(data)
    
    def receive(self, data: bytes):
        """接收数据（仿真用）"""
        self.rx_buffer.extend(data)
        if self.rx_callback:
            self.rx_callback(data)
    
    def read_rx(self) -> bytes:
        """读取接收缓冲区"""
        data = bytes(self.rx_buffer)
        self.rx_buffer.clear()
        return data
    
    def read_tx(self) -> bytes:
        """读取发送缓冲区"""
        data = bytes(self.tx_buffer)
        self.tx_buffer.clear()
        return data


@dataclass
class I2CDevice:
    """I2C 设备"""
    address: int
    registers: dict[int, int] = field(default_factory=dict)
    
    def read_register(self, reg: int) -> int:
        return self.registers.get(reg, 0)
    
    def write_register(self, reg: int, value: int):
        self.registers[reg] = value & 0xFF


class I2CBus:
    """I2C 总线"""
    
    def __init__(self, bus_id: int, speed: int = 100000):
        self.bus_id = bus_id
        self.speed = speed
        self.devices: dict[int, I2CDevice] = {}
    
    @property
    def name(self) -> str:
        return f"I2C{self.bus_id}"
    
    def add_device(self, address: int) -> I2CDevice:
        device = I2CDevice(address)
        self.devices[address] = device
        return device
    
    def read(self, address: int, reg: int) -> int:
        device = self.devices.get(address)
        if device:
            return device.read_register(reg)
        return 0
    
    def write(self, address: int, reg: int, value: int):
        device = self.devices.get(address)
        if device:
            device.write_register(reg, value)


@dataclass
class SPIDevice:
    """SPI 设备"""
    cs_pin: str
    data: bytearray = field(default_factory=bytearray)


class SPIBus:
    """SPI 总线"""
    
    def __init__(self, bus_id: int, speed: int = 1000000):
        self.bus_id = bus_id
        self.speed = speed
        self.devices: dict[str, SPIDevice] = {}
    
    @property
    def name(self) -> str:
        return f"SPI{self.bus_id}"
    
    def add_device(self, cs_pin: str) -> SPIDevice:
        device = SPIDevice(cs_pin)
        self.devices[cs_pin] = device
        return device
    
    def transfer(self, cs_pin: str, data: bytes) -> bytes:
        device = self.devices.get(cs_pin)
        if device:
            device.data.extend(data)
        return data


class PeripheralManager:
    """外设管理器"""
    
    def __init__(self):
        self.gpios: dict[str, GPIOPort] = {}
        self.adcs: dict[int, ADCChannel] = {}
        self.pwms: dict[str, PWMOutput] = {}
        self.uarts: dict[int, UARTPort] = {}
        self.i2cs: dict[int, I2CBus] = {}
        self.spis: dict[int, SPIBus] = {}
    
    def add_gpio(self, gpio: GPIOPort):
        self.gpios[gpio.name] = gpio
    
    def add_adc(self, adc: ADCChannel):
        self.adcs[adc.channel] = adc
    
    def add_pwm(self, pwm: PWMOutput):
        self.pwms[pwm.name] = pwm
    
    def add_uart(self, uart: UARTPort):
        self.uarts[uart.port] = uart
    
    def add_i2c(self, i2c: I2CBus):
        self.i2cs[i2c.bus_id] = i2c
    
    def add_spi(self, spi: SPIBus):
        self.spis[spi.bus_id] = spi
    
    def get_gpio_states(self) -> dict:
        return {name: {"mode": g.mode, "value": g.value} 
                for name, g in self.gpios.items()}
    
    def get_adc_values(self) -> dict:
        return {ch: {"voltage": a.voltage, "value": a.value} 
                for ch, a in self.adcs.items()}
    
    def get_pwm_duties(self) -> dict:
        return {name: {"frequency": p.frequency_hz, "duty": p.duty_cycle}
                for name, p in self.pwms.items()}
