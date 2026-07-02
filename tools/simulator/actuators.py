"""
执行器模拟模块

模拟各种常见执行器：
- Motor（电机）
- Servo（舵机）
- LED（发光二极管）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Motor:
    """直流电机
    
    模拟带编码器的直流电机
    """
    name: str
    max_rpm: int = 300          # 最大转速
    acceleration: float = 100.0 # 加速度（RPM/s）
    
    # 状态
    speed: float = 0.0          # 当前速度（-1.0 到 1.0，负值表示反转）
    rpm: float = 0.0            # 当前转速
    position: int = 0           # 位置（脉冲数）
    ppr: int = 360              # 每转脉冲数
    
    # PWM 输入
    pwm_duty: float = 0.0       # PWM 占空比
    direction: int = 1          # 方向引脚（1 或 -1）
    
    def set_command(self, command: dict):
        """设置电机命令
        
        Args:
            command: dict，包含以下可选字段：
                - speed: float (-1.0 到 1.0)
                - rpm: float
                - pwm: float (0.0 到 1.0)
                - direction: int (1 或 -1)
                - brake: bool
        """
        if "speed" in command:
            self.speed = max(-1.0, min(1.0, command["speed"]))
        
        if "rpm" in command:
            target_rpm = command["rpm"]
            self.speed = target_rpm / self.max_rpm if self.max_rpm > 0 else 0
        
        if "pwm" in command:
            self.pwm_duty = max(0.0, min(1.0, command["pwm"]))
            self.speed = self.pwm_duty * self.direction
        
        if "direction" in command:
            self.direction = 1 if command["direction"] >= 0 else -1
        
        if command.get("brake"):
            self.speed = 0.0
            self.rpm = 0.0
    
    def update(self, dt: float):
        """更新电机状态"""
        # 目标转速
        target_rpm = self.speed * self.max_rpm
        
        # 平滑加速/减速
        if self.rpm < target_rpm:
            self.rpm = min(target_rpm, self.rpm + self.acceleration * dt)
        elif self.rpm > target_rpm:
            self.rpm = max(target_rpm, self.rpm - self.acceleration * dt)
        
        # 更新位置
        pulses_per_second = self.rpm * self.ppr / 60.0
        self.position += int(pulses_per_second * dt)
    
    def get_speed(self) -> float:
        """获取当前速度（-1.0 到 1.0）"""
        return self.speed
    
    def get_rpm(self) -> float:
        """获取当前转速"""
        return self.rpm
    
    def get_position(self) -> int:
        """获取位置"""
        return self.position
    
    def get_data(self) -> dict:
        return {
            "name": self.name,
            "type": "motor",
            "speed": self.speed,
            "rpm": self.rpm,
            "position": self.position,
            "pwm_duty": self.pwm_duty,
            "direction": self.direction,
        }
    
    def get_info(self) -> dict:
        return {
            "name": self.name,
            "type": "motor",
            "max_rpm": self.max_rpm,
            "ppr": self.ppr,
        }


@dataclass
class Servo:
    """舵机
    
    模拟标准舵机（180度或360度）
    """
    name: str
    min_angle: float = 0.0      # 最小角度
    max_angle: float = 180.0    # 最大角度
    min_pulse_us: int = 500     # 最小脉宽（微秒）
    max_pulse_us: int = 2500    # 最大脉宽（微秒）
    
    # 状态
    angle: float = 90.0         # 当前角度
    target_angle: float = 90.0  # 目标角度
    speed: float = 180.0        # 运动速度（度/秒）
    
    def set_command(self, command: dict):
        """设置舵机命令
        
        Args:
            command: dict，包含以下可选字段：
                - angle: float（目标角度）
                - pulse_us: int（脉宽）
                - speed: float（运动速度）
        """
        if "angle" in command:
            self.target_angle = max(self.min_angle, min(self.max_angle, command["angle"]))
        
        if "pulse_us" in command:
            # 将脉宽转换为角度
            pulse = command["pulse_us"]
            ratio = (pulse - self.min_pulse_us) / (self.max_pulse_us - self.min_pulse_us)
            self.target_angle = self.min_angle + ratio * (self.max_angle - self.min_angle)
        
        if "speed" in command:
            self.speed = max(1.0, command["speed"])
    
    def update(self, dt: float):
        """更新舵机状态"""
        if abs(self.angle - self.target_angle) > 0.1:
            # 计算运动量
            max_move = self.speed * dt
            
            if self.angle < self.target_angle:
                self.angle = min(self.target_angle, self.angle + max_move)
            else:
                self.angle = max(self.target_angle, self.angle - max_move)
    
    def get_angle(self) -> float:
        """获取当前角度"""
        return self.angle
    
    def set_angle(self, angle: float):
        """直接设置角度"""
        self.angle = max(self.min_angle, min(self.max_angle, angle))
        self.target_angle = self.angle
    
    def get_data(self) -> dict:
        return {
            "name": self.name,
            "type": "servo",
            "angle": self.angle,
            "target_angle": self.target_angle,
            "speed": self.speed,
        }
    
    def get_info(self) -> dict:
        return {
            "name": self.name,
            "type": "servo",
            "min_angle": self.min_angle,
            "max_angle": self.max_angle,
        }


@dataclass
class LED:
    """LED 发光二极管"""
    name: str
    color: str = "red"          # 颜色
    brightness: float = 0.0     # 亮度（0.0 到 1.0）
    state: bool = False         # 开关状态
    blink_interval_ms: int = 0  # 闪烁间隔（0 表示不闪烁）
    _blink_timer: float = 0.0
    
    def set_command(self, command: dict):
        """设置 LED 命令
        
        Args:
            command: dict，包含以下可选字段：
                - state: bool（开关）
                - brightness: float（亮度）
                - blink: int（闪烁间隔，毫秒）
                - toggle: bool（切换状态）
        """
        if "state" in command:
            self.state = command["state"]
        
        if "brightness" in command:
            self.brightness = max(0.0, min(1.0, command["brightness"]))
            self.state = self.brightness > 0
        
        if "blink" in command:
            self.blink_interval_ms = command["blink"]
        
        if command.get("toggle"):
            self.state = not self.state
    
    def update(self, dt: float):
        """更新 LED 状态"""
        if self.blink_interval_ms > 0:
            self._blink_timer += dt * 1000
            if self._blink_timer >= self.blink_interval_ms:
                self._blink_timer = 0
                self.state = not self.state
    
    def on(self):
        """打开 LED"""
        self.state = True
        self.brightness = 1.0
    
    def off(self):
        """关闭 LED"""
        self.state = False
        self.brightness = 0.0
    
    def toggle(self):
        """切换 LED 状态"""
        self.state = not self.state
    
    def is_on(self) -> bool:
        return self.state
    
    def get_data(self) -> dict:
        return {
            "name": self.name,
            "type": "led",
            "state": self.state,
            "brightness": self.brightness,
            "color": self.color,
            "blink_interval_ms": self.blink_interval_ms,
        }
    
    def get_info(self) -> dict:
        return {
            "name": self.name,
            "type": "led",
            "color": self.color,
        }


class ActuatorManager:
    """执行器管理器"""
    
    def __init__(self):
        self.actuators: dict[str, Any] = {}
    
    def add(self, actuator):
        self.actuators[actuator.name] = actuator
    
    def get(self, name: str):
        return self.actuators.get(name)
    
    def update(self, dt_cycles: int):
        """更新所有执行器"""
        dt = dt_cycles / 168_000_000.0  # 假设 168MHz
        for actuator in self.actuators.values():
            actuator.update(dt)
    
    def get_all_data(self) -> dict:
        return {name: actuator.get_data() for name, actuator in self.actuators.items()}
    
    def get_all_info(self) -> dict:
        return {name: actuator.get_info() for name, actuator in self.actuators.items()}
