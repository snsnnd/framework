"""
传感器模拟模块

模拟各种常见传感器：
- LineSensor（循迹传感器）
- Encoder（编码器）
- IMU（惯性测量单元）
- UltrasonicSensor（超声波传感器）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
import math


@dataclass
class LineSensor:
    """循迹传感器
    
    模拟 5/8 路循迹传感器阵列
    """
    name: str
    channels: int = 5
    values: list[int] = field(default_factory=list)
    raw_values: list[float] = field(default_factory=list)
    threshold: float = 0.5
    binary_mode: bool = True
    
    def __post_init__(self):
        if not self.values:
            self.values = [0] * self.channels
        if not self.raw_values:
            self.raw_values = [0.0] * self.channels
    
    def set_input(self, values: Any):
        """设置传感器输入
        
        Args:
            values: 可以是：
                - list[int]: 二值化后的值（0/1）
                - list[float]: 原始模拟值（0.0-1.0）
                - str: 轨道模式（如 "10101" 表示中间检测到线）
        """
        if isinstance(values, str):
            # 字符串模式
            for i, c in enumerate(values[:self.channels]):
                self.values[i] = 1 if c == '1' else 0
                self.raw_values[i] = 1.0 if c == '1' else 0.0
        elif isinstance(values, list):
            if len(values) > 0 and isinstance(values[0], float):
                # 模拟值模式
                for i, v in enumerate(values[:self.channels]):
                    self.raw_values[i] = v
                    self.values[i] = 1 if v > self.threshold else 0
            else:
                # 二值化模式
                for i, v in enumerate(values[:self.channels]):
                    self.values[i] = int(v) & 1
                    self.raw_values[i] = float(v)
    
    def read(self) -> list[int]:
        """读取二值化后的值"""
        return self.values.copy()
    
    def read_raw(self) -> list[float]:
        """读取原始模拟值"""
        return self.raw_values.copy()
    
    def get_error(self, weights: list[float] = None) -> float:
        """计算循迹误差（用于 PID 控制）"""
        if weights is None:
            # 默认权重：从左到右
            weights = [(-2 + i * 4 / (self.channels - 1)) for i in range(self.channels)]
        
        weighted_sum = 0.0
        total = 0.0
        
        for i in range(self.channels):
            if self.values[i]:
                weighted_sum += weights[i]
                total += 1.0
        
        return weighted_sum / total if total > 0 else 0.0
    
    def get_data(self) -> dict:
        return {
            "name": self.name,
            "type": "line",
            "channels": self.channels,
            "values": self.values,
            "raw_values": self.raw_values,
            "error": self.get_error(),
        }
    
    def get_info(self) -> dict:
        return {
            "name": self.name,
            "type": "line_sensor",
            "channels": self.channels,
            "binary_mode": self.binary_mode,
        }


@dataclass
class Encoder:
    """编码器
    
    模拟增量式旋转编码器
    """
    name: str
    ppr: int = 360           # 每转脉冲数
    position: int = 0        # 当前位置（脉冲数）
    velocity: float = 0.0    # 当前速度（RPM）
    direction: int = 1       # 方向（1 或 -1）
    last_time: float = 0.0
    
    # 仿真用
    _target_velocity: float = 0.0
    _acceleration: float = 100.0  # RPM/s
    
    def set_input(self, value: Any):
        """设置编码器输入
        
        Args:
            value: 可以是：
                - int: 直接设置位置
                - float: 设置目标速度（RPM）
                - dict: {"position": int} 或 {"velocity": float}
        """
        if isinstance(value, dict):
            if "position" in value:
                self.position = value["position"]
            if "velocity" in value:
                self._target_velocity = value["velocity"]
        elif isinstance(value, (int, float)):
            self._target_velocity = value
    
    def update(self, dt: float):
        """更新编码器状态"""
        # 平滑加速/减速
        if self.velocity < self._target_velocity:
            self.velocity = min(self._target_velocity, 
                              self.velocity + self._acceleration * dt)
        elif self.velocity > self._target_velocity:
            self.velocity = max(self._target_velocity,
                              self.velocity - self._acceleration * dt)
        
        # 更新位置
        pulses_per_second = self.velocity * self.ppr / 60.0
        self.position += int(pulses_per_second * dt * self.direction)
    
    def read(self) -> int:
        """读取位置"""
        return self.position
    
    def read_velocity(self) -> float:
        """读取速度（RPM）"""
        return self.velocity
    
    def reset(self):
        """重置编码器"""
        self.position = 0
        self.velocity = 0.0
    
    def get_data(self) -> dict:
        return {
            "name": self.name,
            "type": "encoder",
            "position": self.position,
            "velocity": self.velocity,
            "direction": self.direction,
        }
    
    def get_info(self) -> dict:
        return {
            "name": self.name,
            "type": "encoder",
            "ppr": self.ppr,
        }


@dataclass
class IMU:
    """惯性测量单元
    
    模拟 6 轴 IMU（加速度计 + 陀螺仪）
    """
    name: str
    
    # 加速度计（单位：g）
    accel_x: float = 0.0
    accel_y: float = 0.0
    accel_z: float = 1.0  # 默认重力
    
    # 陀螺仪（单位：deg/s）
    gyro_x: float = 0.0
    gyro_y: float = 0.0
    gyro_z: float = 0.0
    
    # 姿态（单位：度）
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    
    # 温度（单位：摄氏度）
    temperature: float = 25.0
    
    def set_input(self, value: Any):
        """设置 IMU 输入
        
        Args:
            value: dict，包含以下可选字段：
                - accel: [x, y, z] 加速度（g）
                - gyro: [x, y, z] 角速度（deg/s）
                - attitude: [roll, pitch, yaw] 姿态（度）
                - temperature: 温度（摄氏度）
        """
        if isinstance(value, dict):
            if "accel" in value:
                self.accel_x, self.accel_y, self.accel_z = value["accel"]
            if "gyro" in value:
                self.gyro_x, self.gyro_y, self.gyro_z = value["gyro"]
            if "attitude" in value:
                self.roll, self.pitch, self.yaw = value["attitude"]
            if "temperature" in value:
                self.temperature = value["temperature"]
    
    def read_accel(self) -> tuple[float, float, float]:
        """读取加速度"""
        return (self.accel_x, self.accel_y, self.accel_z)
    
    def read_gyro(self) -> tuple[float, float, float]:
        """读取角速度"""
        return (self.gyro_x, self.gyro_y, self.gyro_z)
    
    def read_attitude(self) -> tuple[float, float, float]:
        """读取姿态"""
        return (self.roll, self.pitch, self.yaw)
    
    def get_data(self) -> dict:
        return {
            "name": self.name,
            "type": "imu",
            "accel": [self.accel_x, self.accel_y, self.accel_z],
            "gyro": [self.gyro_x, self.gyro_y, self.gyro_z],
            "attitude": [self.roll, self.pitch, self.yaw],
            "temperature": self.temperature,
        }
    
    def get_info(self) -> dict:
        return {
            "name": self.name,
            "type": "imu",
            "axes": 6,
        }


@dataclass
class UltrasonicSensor:
    """超声波传感器
    
    模拟 HC-SR04 超声波测距模块
    """
    name: str
    distance_cm: float = 100.0  # 测量距离（厘米）
    min_distance: float = 2.0   # 最小距离
    max_distance: float = 400.0 # 最大距离
    temperature: float = 20.0   # 环境温度（影响声速）
    
    def set_input(self, value: Any):
        """设置超声波输入
        
        Args:
            value: 可以是：
                - float: 距离（厘米）
                - dict: {"distance_cm": float}
        """
        if isinstance(value, dict):
            self.distance_cm = value.get("distance_cm", self.distance_cm)
        elif isinstance(value, (int, float)):
            self.distance_cm = float(value)
        
        # 限制范围
        self.distance_cm = max(self.min_distance, min(self.max_distance, self.distance_cm))
    
    def read(self) -> float:
        """读取距离（厘米）"""
        return self.distance_cm
    
    def read_us(self) -> float:
        """读取往返时间（微秒）"""
        # 声速 = 331.3 + 0.606 * temperature (m/s)
        speed_of_sound = 331.3 + 0.606 * self.temperature  # m/s
        speed_of_sound_cm_us = speed_of_sound * 100 / 1_000_000  # cm/us
        return self.distance_cm * 2 / speed_of_sound_cm_us
    
    def get_data(self) -> dict:
        return {
            "name": self.name,
            "type": "ultrasonic",
            "distance_cm": self.distance_cm,
            "time_us": self.read_us(),
        }
    
    def get_info(self) -> dict:
        return {
            "name": self.name,
            "type": "ultrasonic",
            "min_cm": self.min_distance,
            "max_cm": self.max_distance,
        }


class SensorManager:
    """传感器管理器"""
    
    def __init__(self):
        self.sensors: dict[str, Any] = {}
    
    def add(self, sensor):
        self.sensors[sensor.name] = sensor
    
    def get(self, name: str):
        return self.sensors.get(name)
    
    def update(self, dt_cycles: int):
        """更新所有传感器"""
        dt = dt_cycles / 168_000_000.0  # 假设 168MHz
        for sensor in self.sensors.values():
            if isinstance(sensor, Encoder):
                sensor.update(dt)
    
    def get_all_data(self) -> dict:
        return {name: sensor.get_data() for name, sensor in self.sensors.items()}
    
    def get_all_info(self) -> dict:
        return {name: sensor.get_info() for name, sensor in self.sensors.items()}
