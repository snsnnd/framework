"""
仿真器优化方案

1. 实时性优化 - 使用真实定时器
2. 外设行为优化 - 添加噪声和电气特性
3. 传感器优化 - 添加动态数据源
4. 物理引擎集成 - 添加简单物理模拟
5. 状态可视化 - 添加实时状态输出
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ─── 1. 实时性优化 ──────────────────────────────────────────────────────────

class RealtimeScheduler:
    """实时调度器 - 使用真实时间而非模拟时间"""
    
    def __init__(self, tick_hz: int = 1000):
        self.tick_hz = tick_hz
        self.tick_interval = 1.0 / tick_hz
        self.last_tick = time.monotonic()
        self.callbacks: list[Callable] = []
        self.running = False
    
    def register(self, callback: Callable, period_ticks: int = 1):
        """注册周期回调"""
        self.callbacks.append({
            'func': callback,
            'period': period_ticks,
            'counter': 0,
        })
    
    def start(self):
        """启动实时调度"""
        self.running = True
        self.last_tick = time.monotonic()
    
    def stop(self):
        """停止调度"""
        self.running = False
    
    def update(self) -> bool:
        """更新调度，返回是否执行了 tick"""
        if not self.running:
            return False
        
        now = time.monotonic()
        elapsed = now - self.last_tick
        
        if elapsed >= self.tick_interval:
            self.last_tick = now
            
            # 执行回调
            for cb in self.callbacks:
                cb['counter'] += 1
                if cb['counter'] >= cb['period']:
                    cb['counter'] = 0
                    cb['func']()
            
            return True
        
        return False


# ─── 2. 外设行为优化 ────────────────────────────────────────────────────────

@dataclass
class NoisyADC:
    """带噪声的 ADC 模拟"""
    
    channel: int
    base_voltage: float = 0.0
    noise_amplitude: float = 0.01  # 噪声幅度 (V)
    noise_frequency: float = 50.0  # 噪声频率 (Hz)
    offset_error: float = 0.0      # 偏移误差 (V)
    gain_error: float = 1.0        # 增益误差
    resolution: int = 12           # 分辨率
    
    def read(self, time_s: float) -> int:
        """读取 ADC 值（带噪声）"""
        # 基础值 + 偏移误差
        voltage = self.base_voltage + self.offset_error
        
        # 增益误差
        voltage *= self.gain_error
        
        # 添加 50Hz 工频噪声
        voltage += self.noise_amplitude * math.sin(2 * math.pi * self.noise_frequency * time_s)
        
        # 添加随机噪声
        voltage += random.gauss(0, self.noise_amplitude / 3)
        
        # 量化
        max_value = (1 << self.resolution) - 1
        adc_value = int(voltage / 3.3 * max_value)
        
        return max(0, min(max_value, adc_value))


@dataclass
class NoisyGPIO:
    """带噪声的 GPIO 模拟"""
    
    pin: str
    value: int = 0
    bounce_time_ms: float = 5.0  # 抖动时间
    _last_change: float = 0.0
    _stable_value: int = 0
    
    def write(self, value: int, current_time_ms: float):
        """写入 GPIO（带抖动）"""
        if value != self._stable_value:
            self._stable_value = value
            self._last_change = current_time_ms
            # 抖动期间随机翻转
            self.value = value if random.random() > 0.5 else (1 - value)
        else:
            # 抖动结束后稳定
            if current_time_ms - self._last_change > self.bounce_time_ms:
                self.value = self._stable_value
    
    def read(self) -> int:
        """读取 GPIO"""
        return self.value


# ─── 3. 传感器优化 ──────────────────────────────────────────────────────────

class DynamicLineSensor:
    """动态循迹传感器 - 模拟真实轨道变化"""
    
    def __init__(self, channels: int = 5, track_width_mm: float = 20.0):
        self.channels = channels
        self.track_width_mm = track_width_mm
        
        # 传感器位置（相对于轨道中心，单位 mm）
        self.sensor_positions = [
            (i - (channels - 1) / 2) * (track_width_mm / (channels - 1))
            for i in range(channels)
        ]
        
        # 轨道参数
        self.line_position = 0.0  # 线位置（mm）
        self.line_width_mm = 20.0  # 线宽
        
        # 车辆位置
        self.vehicle_x = 0.0  # 车辆横向位置（mm）
        self.vehicle_speed = 0.0  # 车辆速度（mm/s）
        
        # 传感器响应
        self.sensitivity = 1.0
        self.background_value = 0.1
        self.line_value = 0.9
    
    def update(self, dt_s: float):
        """更新传感器状态"""
        # 更新车辆位置
        self.vehicle_x += self.vehicle_speed * dt_s
        
        # 模拟轨道变化（正弦曲线）
        self.line_position = 10 * math.sin(0.1 * self.vehicle_x)
    
    def read(self) -> list[float]:
        """读取传感器值"""
        values = []
        
        for i, sensor_pos in enumerate(self.sensor_positions):
            # 传感器实际位置
            actual_pos = self.vehicle_x + sensor_pos
            
            # 距离线中心的距离
            distance = abs(actual_pos - self.line_position)
            
            # 高斯响应函数
            sigma = self.line_width_mm / 2
            response = math.exp(-(distance ** 2) / (2 * sigma ** 2))
            
            # 添加噪声
            noise = random.gauss(0, 0.05)
            
            # 最终值
            value = self.background_value + (self.line_value - self.background_value) * response
            value = max(0, min(1, value + noise))
            
            values.append(value)
        
        return values
    
    def read_binary(self, threshold: float = 0.5) -> list[int]:
        """读取二值化后的传感器值"""
        return [1 if v > threshold else 0 for v in self.read()]


class DynamicEncoder:
    """动态编码器 - 模拟真实电机响应"""
    
    def __init__(self, ppr: int = 360):
        self.ppr = ppr
        
        # 电机参数
        self.target_rpm = 0.0
        self.current_rpm = 0.0
        self.acceleration = 100.0  # RPM/s
        self.friction = 50.0  # 摩擦损耗 RPM/s
        
        # 编码器状态
        self.position = 0
        self.last_time = 0.0
    
    def set_target(self, rpm: float):
        """设置目标转速"""
        self.target_rpm = rpm
    
    def update(self, dt_s: float):
        """更新电机状态"""
        # 计算加速度
        if self.current_rpm < self.target_rpm:
            accel = self.acceleration
        elif self.current_rpm > self.target_rpm:
            accel = -self.acceleration
        else:
            accel = 0
        
        # 应用摩擦
        if abs(self.current_rpm) > 0:
            friction = -self.friction * (1 if self.current_rpm > 0 else -1)
        else:
            friction = 0
        
        # 更新转速
        self.current_rpm += (accel + friction) * dt_s
        
        # 限制范围
        self.current_rpm = max(-1000, min(1000, self.current_rpm))
        
        # 更新位置
        pulses_per_second = self.current_rpm * self.ppr / 60
        self.position += int(pulses_per_second * dt_s)
    
    def read_position(self) -> int:
        """读取位置"""
        return self.position
    
    def read_velocity(self) -> float:
        """读取速度（RPM）"""
        return self.current_rpm


# ─── 4. 简单物理引擎 ────────────────────────────────────────────────────────

@dataclass
class SimpleVehicle:
    """简单车辆物理模型"""
    
    # 质量和尺寸
    mass_kg: float = 1.0
    wheelbase_mm: float = 150.0
    track_width_mm: float = 100.0
    
    # 状态
    x: float = 0.0  # 位置 X (mm)
    y: float = 0.0  # 位置 Y (mm)
    heading: float = 0.0  # 航向角 (rad)
    speed: float = 0.0  # 速度 (mm/s)
    
    # 电机输入
    left_speed: float = 0.0  # 左轮速度 (mm/s)
    right_speed: float = 0.0  # 右轮速度 (mm/s)
    
    def update(self, dt_s: float):
        """更新车辆状态"""
        # 差速转向模型
        v = (self.left_speed + self.right_speed) / 2
        omega = (self.right_speed - self.left_speed) / self.track_width_mm
        
        # 更新航向
        self.heading += omega * dt_s
        
        # 归一化航向角
        self.heading = self.heading % (2 * math.pi)
        
        # 更新位置
        self.x += v * math.cos(self.heading) * dt_s
        self.y += v * math.sin(self.heading) * dt_s
        
        self.speed = v
    
    def set_motors(self, left_mm_s: float, right_mm_s: float):
        """设置电机速度"""
        self.left_speed = left_mm_s
        self.right_speed = right_mm_s
    
    def get_state(self) -> dict:
        """获取状态"""
        return {
            'x': self.x,
            'y': self.y,
            'heading_deg': math.degrees(self.heading),
            'speed_mm_s': self.speed,
            'left_speed': self.left_speed,
            'right_speed': self.right_speed,
        }


# ─── 5. 状态可视化输出 ──────────────────────────────────────────────────────

class StateVisualizer:
    """状态可视化输出"""
    
    def __init__(self, output_file: str = None):
        self.output_file = output_file
        self.history: list[dict] = []
        self.max_history = 1000
    
    def log_state(self, timestamp: float, state: dict):
        """记录状态"""
        entry = {
            'time': timestamp,
            **state,
        }
        
        self.history.append(entry)
        
        # 限制历史长度
        if len(self.history) > self.max_history:
            self.history.pop(0)
        
        # 写入文件
        if self.output_file:
            import json
            with open(self.output_file, 'a') as f:
                f.write(json.dumps(entry) + '\n')
    
    def print_state(self, state: dict, clear: bool = True):
        """打印状态到终端"""
        if clear:
            print('\033[2J\033[H', end='')  # 清屏
        
        print('=' * 60)
        print('仿真状态')
        print('=' * 60)
        
        for key, value in state.items():
            if isinstance(value, float):
                print(f'{key:>20}: {value:.3f}')
            elif isinstance(value, list):
                print(f'{key:>20}: {value}')
            else:
                print(f'{key:>20}: {value}')
        
        print('=' * 60)
    
    def export_csv(self, filename: str):
        """导出为 CSV"""
        if not self.history:
            return
        
        import csv
        
        keys = self.history[0].keys()
        
        with open(filename, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(self.history)


# ─── 使用示例 ────────────────────────────────────────────────────────────────

def demo_optimized_simulation():
    """优化后的仿真示例"""
    
    # 创建组件
    line_sensor = DynamicLineSensor(channels=5)
    left_encoder = DynamicEncoder(ppr=360)
    right_encoder = DynamicEncoder(ppr=360)
    vehicle = SimpleVehicle()
    visualizer = StateVisualizer()
    
    # 创建实时调度器
    scheduler = RealtimeScheduler(tick_hz=100)
    
    # 控制参数
    base_speed = 100  # mm/s
    kp = 2.0
    
    def control_loop():
        """控制循环（10ms 周期）"""
        # 读取传感器
        sensor_values = line_sensor.read_binary()
        
        # 计算误差
        weights = [-2, -1, 0, 1, 2]
        error = sum(v * w for v, w in zip(sensor_values, weights)) / sum(sensor_values) if sum(sensor_values) > 0 else 0
        
        # PID 控制
        correction = kp * error
        
        # 设置电机
        left_speed = base_speed + correction
        right_speed = base_speed - correction
        
        vehicle.set_motors(left_speed, right_speed)
        left_encoder.set_target(left_speed * 60 / (2 * math.pi * 30))  # 转换为 RPM
        right_encoder.set_target(right_speed * 60 / (2 * math.pi * 30))
    
    def sensor_update():
        """传感器更新（10ms 周期）"""
        line_sensor.update(0.01)
        left_encoder.update(0.01)
        right_encoder.update(0.01)
        vehicle.update(0.01)
    
    def state_log():
        """状态记录（100ms 周期）"""
        state = {
            'sensors': line_sensor.read_binary(),
            'left_rpm': left_encoder.read_velocity(),
            'right_rpm': right_encoder.read_velocity(),
            **vehicle.get_state(),
        }
        visualizer.log_state(time.monotonic(), state)
    
    # 注册回调
    scheduler.register(control_loop, period_ticks=1)  # 10ms
    scheduler.register(sensor_update, period_ticks=1)  # 10ms
    scheduler.register(state_log, period_ticks=10)    # 100ms
    
    # 运行仿真
    print("启动优化仿真...")
    scheduler.start()
    
    try:
        for _ in range(1000):  # 运行 10 秒
            scheduler.update()
            time.sleep(0.001)  # 1ms 休眠
    except KeyboardInterrupt:
        pass
    
    scheduler.stop()
    
    # 导出数据
    visualizer.export_csv('simulation_log.csv')
    print("仿真完成，数据已导出到 simulation_log.csv")


if __name__ == '__main__':
    demo_optimized_simulation()
