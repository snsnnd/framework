"""
仿真引擎核心

管理整个仿真系统的运行，包括：
- MCU 实例管理
- 外设注册和交互
- 传感器/执行器管理
- 仿真循环控制
- 在线 Debug 数据导出
"""

from __future__ import annotations

import json
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from .core import MCUSimulator, MCUType
from .peripherals import (
    GPIOPort, ADCChannel, PWMOutput, UARTPort, I2CBus, SPIBus,
    PeripheralManager
)
from .sensors import (
    LineSensor, Encoder, IMU, UltrasonicSensor,
    SensorManager
)
from .actuators import (
    Motor, Servo, LED,
    ActuatorManager
)


@dataclass
class SimulationState:
    """仿真状态"""
    running: bool = False
    paused: bool = False
    speed_multiplier: float = 1.0
    current_time_us: int = 0
    frame_count: int = 0
    fps: float = 0.0


@dataclass
class DebugSnapshot:
    """调试快照（用于在线 Debug）"""
    timestamp: int = 0
    mcu_stats: dict = field(default_factory=dict)
    gpio_states: dict = field(default_factory=dict)
    adc_values: dict = field(default_factory=dict)
    pwm_duties: dict = field(default_factory=dict)
    sensor_data: dict = field(default_factory=dict)
    actuator_data: dict = field(default_factory=dict)
    task_info: dict = field(default_factory=dict)
    module_info: dict = field(default_factory=dict)


class SimulationEngine:
    """仿真引擎
    
    使用方式：
        # 创建引擎
        engine = SimulationEngine()
        
        # 配置 MCU
        engine.create_mcu(MCUType.STM32F407)
        
        # 添加外设
        engine.add_sensor(LineSensor("line_sensor", channels=5))
        engine.add_actuator(Motor("left_motor"))
        engine.add_actuator(Motor("right_motor"))
        
        # 启动仿真
        engine.start()
        
        # 获取快照（用于在线 Debug）
        snapshot = engine.get_debug_snapshot()
    """
    
    def __init__(self):
        """初始化仿真引擎"""
        self.mcu: Optional[MCUSimulator] = None
        self.peripherals = PeripheralManager()
        self.sensors = SensorManager()
        self.actuators = ActuatorManager()
        
        self.state = SimulationState()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        
        # 用户回调
        self.on_tick: Optional[Callable] = None
        self.on_frame: Optional[Callable] = None
        
        # 调试数据缓存
        self._debug_data: dict = {}
    
    def create_mcu(self, mcu_type: MCUType = MCUType.STM32F407) -> MCUSimulator:
        """创建 MCU 实例"""
        self.mcu = MCUSimulator(mcu_type)
        return self.mcu
    
    def get_mcu(self) -> Optional[MCUSimulator]:
        """获取 MCU 实例"""
        return self.mcu
    
    # ===== 外设管理 =====
    
    def add_gpio(self, port: str, pin: int, mode: str = "input") -> GPIOPort:
        """添加 GPIO"""
        gpio = GPIOPort(port, pin, mode)
        self.peripherals.add_gpio(gpio)
        if self.mcu:
            self.mcu.init_gpio(port, pin, mode)
        return gpio
    
    def add_adc(self, channel: int, resolution: int = 12) -> ADCChannel:
        """添加 ADC"""
        adc = ADCChannel(channel, resolution)
        self.peripherals.add_adc(adc)
        if self.mcu:
            self.mcu.init_adc(channel, resolution)
        return adc
    
    def add_pwm(self, timer: str, frequency_hz: int = 1000) -> PWMOutput:
        """添加 PWM"""
        pwm = PWMOutput(timer, frequency_hz)
        self.peripherals.add_pwm(pwm)
        if self.mcu:
            self.mcu.init_pwm(timer, frequency_hz)
        return pwm
    
    def add_uart(self, port: int, baudrate: int = 115200) -> UARTPort:
        """添加 UART"""
        uart = UARTPort(port, baudrate)
        self.peripherals.add_uart(uart)
        if self.mcu:
            self.mcu.init_uart(port, baudrate)
        return uart
    
    def add_i2c(self, bus_id: int, speed: int = 100000) -> I2CBus:
        """添加 I2C"""
        i2c = I2CBus(bus_id, speed)
        self.peripherals.add_i2c(i2c)
        return i2c
    
    def add_spi(self, bus_id: int, speed: int = 1000000) -> SPIBus:
        """添加 SPI"""
        spi = SPIBus(bus_id, speed)
        self.peripherals.add_spi(spi)
        return spi
    
    # ===== 传感器管理 =====
    
    def add_sensor(self, sensor) -> None:
        """添加传感器"""
        self.sensors.add(sensor)
    
    def get_sensor(self, name: str):
        """获取传感器"""
        return self.sensors.get(name)
    
    # ===== 执行器管理 =====
    
    def add_actuator(self, actuator) -> None:
        """添加执行器"""
        self.actuators.add(actuator)
    
    def get_actuator(self, name: str):
        """获取执行器"""
        return self.actuators.get(name)
    
    # ===== 仿真控制 =====
    
    def start(self) -> None:
        """启动仿真"""
        if self.state.running:
            return
        
        self.state.running = True
        self.state.paused = False
        
        # 启动仿真线程
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
    
    def stop(self) -> None:
        """停止仿真"""
        self.state.running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
    
    def pause(self) -> None:
        """暂停仿真"""
        self.state.paused = True
    
    def resume(self) -> None:
        """恢复仿真"""
        self.state.paused = False
    
    def step(self, cycles: int = 1) -> None:
        """单步执行"""
        self._execute_cycles(cycles)
    
    def set_speed(self, multiplier: float) -> None:
        """设置仿真速度倍率"""
        self.state.speed_multiplier = max(0.1, min(100.0, multiplier))
    
    def _run_loop(self):
        """仿真主循环"""
        frame_time = 1.0 / 60.0  # 60 FPS
        last_time = time.monotonic()
        frame_count = 0
        fps_timer = time.monotonic()
        
        while self.state.running:
            if self.state.paused:
                time.sleep(0.01)
                continue
            
            current_time = time.monotonic()
            delta = current_time - last_time
            
            if delta >= frame_time:
                # 计算需要执行的周期数
                cycles = int(delta * self.mcu.clock.sysclk_hz * self.state.speed_multiplier)
                self._execute_cycles(min(cycles, 100000))  # 限制单帧最大周期
                
                last_time = current_time
                frame_count += 1
                
                # 更新 FPS
                if current_time - fps_timer >= 1.0:
                    self.state.fps = frame_count / (current_time - fps_timer)
                    frame_count = 0
                    fps_timer = current_time
                
                # 调用帧回调
                if self.on_frame:
                    self.on_frame()
            else:
                time.sleep(0.001)
    
    def _execute_cycles(self, cycles: int):
        """执行指定周期数"""
        with self._lock:
            if self.mcu:
                self.mcu.tick(cycles)
            
            # 更新传感器
            self.sensors.update(cycles)
            
            # 更新执行器
            self.actuators.update(cycles)
            
            # 更新仿真时间
            self.state.current_time_us += cycles * 1_000_000 // self.mcu.clock.sysclk_hz
            self.state.frame_count += 1
            
            # 调用 tick 回调
            if self.on_tick:
                self.on_tick()
    
    # ===== 调试数据导出 =====
    
    def get_debug_snapshot(self) -> DebugSnapshot:
        """获取调试快照（用于在线 Debug）"""
        with self._lock:
            snapshot = DebugSnapshot()
            snapshot.timestamp = self.state.current_time_us
            
            # MCU 统计
            if self.mcu:
                snapshot.mcu_stats = self.mcu.get_stats()
            
            # GPIO 状态
            snapshot.gpio_states = self.peripherals.get_gpio_states()
            
            # ADC 值
            snapshot.adc_values = self.peripherals.get_adc_values()
            
            # PWM 占空比
            snapshot.pwm_duties = self.peripherals.get_pwm_duties()
            
            # 传感器数据
            snapshot.sensor_data = self.sensors.get_all_data()
            
            # 执行器数据
            snapshot.actuator_data = self.actuators.get_all_data()
            
            return snapshot
    
    def get_debug_json(self) -> str:
        """获取调试数据 JSON"""
        snapshot = self.get_debug_snapshot()
        return json.dumps({
            "timestamp": snapshot.timestamp,
            "mcu_stats": snapshot.mcu_stats,
            "gpio_states": snapshot.gpio_states,
            "adc_values": snapshot.adc_values,
            "pwm_duties": snapshot.pwm_duties,
            "sensor_data": snapshot.sensor_data,
            "actuator_data": snapshot.actuator_data,
        }, ensure_ascii=False, indent=2)
    
    # ===== 场景管理 =====
    
    def load_scenario(self, path: str | Path) -> None:
        """加载仿真场景"""
        from .scenario import load_scenario
        scenario = load_scenario(path)
        self._apply_scenario(scenario)
    
    def save_scenario(self, path: str | Path) -> None:
        """保存当前场景"""
        from .scenario import save_scenario, Scenario
        scenario = self._export_scenario()
        save_scenario(scenario, path)
    
    def _apply_scenario(self, scenario) -> None:
        """应用场景配置"""
        # 创建 MCU
        self.create_mcu(scenario.mcu_type)
        
        # 添加外设
        for gpio_cfg in scenario.gpios:
            self.add_gpio(gpio_cfg["port"], gpio_cfg["pin"], gpio_cfg.get("mode", "input"))
        
        for adc_cfg in scenario.adcs:
            self.add_adc(adc_cfg["channel"], adc_cfg.get("resolution", 12))
        
        for pwm_cfg in scenario.pwms:
            self.add_pwm(pwm_cfg["timer"], pwm_cfg.get("frequency_hz", 1000))
        
        for uart_cfg in scenario.uarts:
            self.add_uart(uart_cfg["port"], uart_cfg.get("baudrate", 115200))
        
        # 添加传感器
        for sensor_cfg in scenario.sensors:
            sensor = self._create_sensor(sensor_cfg)
            if sensor:
                self.add_sensor(sensor)
        
        # 添加执行器
        for actuator_cfg in scenario.actuators:
            actuator = self._create_actuator(actuator_cfg)
            if actuator:
                self.add_actuator(actuator)
    
    def _export_scenario(self):
        """导出当前场景"""
        from .scenario import Scenario
        scenario = Scenario()
        scenario.mcu_type = self.mcu.mcu_type if self.mcu else MCUType.STM32F407
        return scenario
    
    def _create_sensor(self, cfg: dict):
        """根据配置创建传感器"""
        from .sensors import LineSensor, Encoder, IMU, UltrasonicSensor
        
        sensor_type = cfg.get("type")
        name = cfg.get("name", "unnamed")
        
        if sensor_type == "line":
            return LineSensor(name, channels=cfg.get("channels", 5))
        elif sensor_type == "encoder":
            return Encoder(name, ppr=cfg.get("ppr", 360))
        elif sensor_type == "imu":
            return IMU(name)
        elif sensor_type == "ultrasonic":
            return UltrasonicSensor(name)
        
        return None
    
    def _create_actuator(self, cfg: dict):
        """根据配置创建执行器"""
        from .actuators import Motor, Servo, LED
        
        actuator_type = cfg.get("type")
        name = cfg.get("name", "unnamed")
        
        if actuator_type == "motor":
            return Motor(name, max_rpm=cfg.get("max_rpm", 300))
        elif actuator_type == "servo":
            return Servo(name, min_angle=cfg.get("min_angle", 0), max_angle=cfg.get("max_angle", 180))
        elif actuator_type == "led":
            return LED(name)
        
        return None
    
    # ===== API 供 Studio 调用 =====
    
    def get_state(self) -> dict:
        """获取仿真状态（Studio API）"""
        return {
            "running": self.state.running,
            "paused": self.state.paused,
            "speed_multiplier": self.state.speed_multiplier,
            "current_time_us": self.state.current_time_us,
            "frame_count": self.state.frame_count,
            "fps": self.state.fps,
        }
    
    def get_peripherals_info(self) -> dict:
        """获取外设信息（Studio API）"""
        return {
            "gpio": [{"name": g.name, "mode": g.mode, "value": g.value} 
                    for g in self.peripherals.gpios.values()],
            "adc": [{"name": a.name, "channel": a.channel, "value": a.value}
                   for a in self.peripherals.adcs.values()],
            "pwm": [{"name": p.name, "timer": p.timer, "duty_cycle": p.duty_cycle}
                   for p in self.peripherals.pwms.values()],
            "uart": [{"name": u.name, "port": u.port, "baudrate": u.baudrate}
                    for u in self.peripherals.uarts.values()],
        }
    
    def get_sensors_info(self) -> dict:
        """获取传感器信息（Studio API）"""
        return self.sensors.get_all_info()
    
    def get_actuators_info(self) -> dict:
        """获取执行器信息（Studio API）"""
        return self.actuators.get_all_info()
    
    def set_sensor_input(self, name: str, value: Any) -> None:
        """设置传感器输入（Studio API，用于交互）"""
        sensor = self.sensors.get(name)
        if sensor:
            sensor.set_input(value)
    
    def set_actuator_command(self, name: str, command: dict) -> None:
        """设置执行器命令（Studio API）"""
        actuator = self.actuators.get(name)
        if actuator:
            actuator.set_command(command)
