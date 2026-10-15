#!/usr/bin/env python3
"""
循迹车仿真示例

演示如何使用仿真引擎模拟一个完整的循迹小车系统。

使用方式：
    python3 -m tools.simulator.examples.line_tracker
"""

import json
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.simulator import (
    SimulationEngine, MCUSimulator, MCUType,
    LineSensor, Encoder, Motor, LED,
    Scenario, ScenarioConfig
)
from tools.simulator.scenario import save_scenario


class PIDController:
    """简单 PID 控制器"""
    
    def __init__(self, kp: float = 1.5, ki: float = 0.3, kd: float = 0.05):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.prev_error = 0.0
        self.integral = 0.0
    
    def update(self, error: float, dt: float) -> float:
        self.integral += error * dt
        derivative = (error - self.prev_error) / dt if dt > 0 else 0
        output = self.kp * error + self.ki * self.integral + self.kd * derivative
        self.prev_error = error
        return output


class LineTrackerSimulation:
    """循迹车仿真"""
    
    def __init__(self):
        self.engine = SimulationEngine()
        self.engine.create_mcu(MCUType.STM32F407)
        
        # 传感器
        self.line_sensor = LineSensor("line_sensor", channels=5)
        self.left_encoder = Encoder("left_encoder", ppr=360)
        self.right_encoder = Encoder("right_encoder", ppr=360)
        
        self.engine.add_sensor(self.line_sensor)
        self.engine.add_sensor(self.left_encoder)
        self.engine.add_sensor(self.right_encoder)
        
        # 执行器
        self.left_motor = Motor("left_motor", max_rpm=300)
        self.right_motor = Motor("right_motor", max_rpm=300)
        self.led = LED("status_led", color="green")
        
        self.engine.add_actuator(self.left_motor)
        self.engine.add_actuator(self.right_motor)
        self.engine.add_actuator(self.led)
        
        # PID
        self.pid = PIDController(kp=1.5, ki=0.3, kd=0.05)
        self.base_speed = 0.65
        self.weights = [-2.0, -1.0, 0.0, 1.0, 2.0]
    
    def control_step(self):
        """单步控制"""
        error = self.line_sensor.get_error(self.weights)
        correction = self.pid.update(error, 0.001)
        
        left = max(0, min(1, self.base_speed + correction))
        right = max(0, min(1, self.base_speed - correction))
        
        self.left_motor.set_command({"speed": left})
        self.right_motor.set_command({"speed": right})
        
        self.led.state = any(self.line_sensor.values)
    
    def run(self, steps: int = 100, track_changes: list = None):
        """运行仿真"""
        if track_changes is None:
            # 默认轨道变化序列
            track_changes = [
                (0, "10101"),    # 直道
                (20, "01100"),   # 左弯
                (40, "10100"),   # 轻微左偏
                (60, "00110"),   # 右弯
                (80, "10101"),   # 回到直道
            ]
        
        current_track = "10101"
        track_idx = 0
        
        results = []
        
        for step in range(steps):
            # 检查轨道变化
            while track_idx < len(track_changes) and step >= track_changes[track_idx][0]:
                current_track = track_changes[track_idx][1]
                track_idx += 1
            
            self.line_sensor.set_input(current_track)
            self.control_step()
            
            snapshot = self.engine.get_debug_snapshot()
            
            result = {
                "step": step,
                "track": current_track,
                "sensor_values": self.line_sensor.values.copy(),
                "error": self.line_sensor.get_error(self.weights),
                "left_speed": self.left_motor.speed,
                "right_speed": self.right_motor.speed,
            }
            results.append(result)
        
        return results


def print_results(results: list):
    """打印结果"""
    print("\n" + "=" * 70)
    print("仿真结果")
    print("=" * 70)
    print(f"{'Step':>6} | {'Track':^7} | {'Sensors':^7} | {'Error':>7} | {'Left':>7} | {'Right':>7}")
    print("-" * 70)
    
    for r in results[::10]:  # 每10步打印一次
        sensors = "".join(str(v) for v in r["sensor_values"])
        print(f"{r['step']:6d} | {r['track']:^7} | {sensors:^7} | {r['error']:+7.3f} | {r['left_speed']:7.3f} | {r['right_speed']:7.3f}")
    
    print("=" * 70)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="循迹车仿真演示")
    parser.add_argument("--steps", type=int, default=100, help="仿真步数")
    parser.add_argument("--export", type=str, help="导出调试数据路径")
    parser.add_argument("--save", type=str, help="保存场景配置路径")
    
    args = parser.parse_args()
    
    sim = LineTrackerSimulation()
    
    print("循迹车仿真开始...")
    results = sim.run(steps=args.steps)
    
    print_results(results)
    
    # 导出调试数据
    if args.export:
        data = sim.engine.get_debug_json()
        with open(args.export, "w", encoding="utf-8") as f:
            f.write(data)
        print(f"调试数据已导出到: {args.export}")
    
    # 保存场景
    if args.save:
        config = ScenarioConfig(
            name="line_tracker",
            description="循迹车仿真场景",
            mcu_type="STM32F407",
            sensors=[
                {"name": "line_sensor", "type": "line", "channels": 5},
                {"name": "left_encoder", "type": "encoder", "ppr": 360},
                {"name": "right_encoder", "type": "encoder", "ppr": 360},
            ],
            actuators=[
                {"name": "left_motor", "type": "motor", "max_rpm": 300},
                {"name": "right_motor", "type": "motor", "max_rpm": 300},
                {"name": "status_led", "type": "led", "color": "green"},
            ],
        )
        scenario = Scenario(config=config)
        save_scenario(scenario, args.save)
        print(f"场景配置已保存到: {args.save}")


if __name__ == "__main__":
    main()
