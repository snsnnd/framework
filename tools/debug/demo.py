#!/usr/bin/env python3
"""
EFW 在线 Debug 效果演示

模拟 MCU 连接后的实际显示效果。
"""

import json
import time
import random
from datetime import datetime, timezone

def generate_snapshot(seq: int) -> dict:
    """生成模拟快照数据"""
    base_time = 1000 + seq  # 模拟时间戳
    
    # 模拟传感器数据（有轻微波动）
    sensor_base = [1, 0, 1, 0, 1]
    sensor_values = []
    for i, base in enumerate(sensor_base):
        # 偶尔翻转
        if random.random() < 0.05:
            sensor_values.append(1 - base)
        else:
            sensor_values.append(base)
    
    # 模拟电机速度（有随机波动）
    left_speed = 65.0 + random.uniform(-2, 2)
    right_speed = 63.0 + random.uniform(-2, 2)
    
    # 模拟 PID 参数
    kp = 1.5 + random.uniform(-0.01, 0.01)
    ki = 0.3 + random.uniform(-0.005, 0.005)
    kd = 0.05 + random.uniform(-0.001, 0.001)
    
    # 模拟编码器
    left_encoder = 1234 + seq * 10 + random.randint(-5, 5)
    right_encoder = 1230 + seq * 10 + random.randint(-5, 5)
    
    # 模拟电池电压（缓慢下降）
    battery = 7.4 - seq * 0.001 + random.uniform(-0.02, 0.02)
    
    # 模拟状态机
    states = ["IDLE", "RUNNING", "RUNNING", "RUNNING", "STOPPED"]
    state = states[min(seq // 100, 4)]
    
    return {
        "time": datetime.now(timezone.utc).isoformat(),
        "seq": seq,
        "params": {
            "line_sensor_0": {"value": sensor_values[0], "type": "u8", "unit": "", "status": "OK"},
            "line_sensor_1": {"value": sensor_values[1], "type": "u8", "unit": "", "status": "OK"},
            "line_sensor_2": {"value": sensor_values[2], "type": "u8", "unit": "", "status": "OK"},
            "line_sensor_3": {"value": sensor_values[3], "type": "u8", "unit": "", "status": "OK"},
            "line_sensor_4": {"value": sensor_values[4], "type": "u8", "unit": "", "status": "OK"},
            "motor_speed_left": {"value": round(left_speed, 1), "type": "f32", "unit": "%", "status": "OK"},
            "motor_speed_right": {"value": round(right_speed, 1), "type": "f32", "unit": "%", "status": "OK"},
            "pid_kp": {"value": round(kp, 4), "type": "f32", "unit": "", "status": "OK"},
            "pid_ki": {"value": round(ki, 4), "type": "f32", "unit": "", "status": "OK"},
            "pid_kd": {"value": round(kd, 4), "type": "f32", "unit": "", "status": "OK"},
            "encoder_left": {"value": left_encoder, "type": "i32", "unit": "pulse", "status": "OK"},
            "encoder_right": {"value": right_encoder, "type": "i32", "unit": "pulse", "status": "OK"},
            "battery_voltage": {"value": round(battery, 2), "type": "f32", "unit": "V", "status": "OK"},
            "state_machine_main": {"value": state, "type": "string", "unit": "", "status": "OK"},
        }
    }

def check_issues(snapshot: dict, expected: dict) -> list:
    """检查问题"""
    issues = []
    params = snapshot.get("params", {})
    
    for name, rules in expected.get("params", {}).items():
        if name not in params:
            continue
        
        value = params[name].get("value")
        
        # 范围检查
        if "min" in rules and value < rules["min"]:
            issues.append({
                "name": name,
                "type": "out_of_range",
                "detail": f"{value} < min({rules['min']})",
                "severity": "error"
            })
        
        if "max" in rules and value > rules["max"]:
            issues.append({
                "name": name,
                "type": "out_of_range",
                "detail": f"{value} > max({rules['max']})",
                "severity": "error"
            })
        
        # 枚举检查
        if "enum" in rules and value not in rules["enum"]:
            issues.append({
                "name": name,
                "type": "unexpected_enum",
                "detail": f"{value} not in {rules['enum']}",
                "severity": "warning"
            })
    
    return issues

def format_value(value, unit: str) -> str:
    """格式化值"""
    if isinstance(value, float):
        return f"{value:.2f} {unit}".strip()
    return f"{value} {unit}".strip()

def print_snapshot(snapshot: dict, issues: list, compact: bool = False):
    """打印快照"""
    params = snapshot.get("params", {})
    
    if compact:
        # 紧凑模式：单行显示关键数据
        sensors = "".join(str(params.get(f"line_sensor_{i}", {}).get("value", "?")) for i in range(5))
        left = params.get("motor_speed_left", {}).get("value", 0)
        right = params.get("motor_speed_right", {}).get("value", 0)
        state = params.get("state_machine_main", {}).get("value", "?")
        battery = params.get("battery_voltage", {}).get("value", 0)
        
        issue_marker = f" ⚠{len(issues)}" if issues else ""
        print(f"[{snapshot['seq']:4d}] S:{sensors} | L:{left:5.1f}% R:{right:5.1f}% | Bat:{battery:.2f}V | {state}{issue_marker}")
        return
    
    # 详细模式
    print("\033[2J\033[H")  # 清屏
    print("╔══════════════════════════════════════════════════════════════════════════════╗")
    print("║                        EFW 在线调试面板                                      ║")
    print("╠══════════════════════════════════════════════════════════════════════════════╣")
    print(f"║  时间: {snapshot['time'][:19]}                                          ║")
    print(f"║  序列: {snapshot['seq']:<6}                                                            ║")
    print("╚══════════════════════════════════════════════════════════════════════════════╝")
    
    # 循迹传感器
    print("\n┌─────────────────────────────────────────────────────────────────────────────┐")
    print("│  循迹传感器                                                                 │")
    print("├─────────────────────────────────────────────────────────────────────────────┤")
    sensors = [params.get(f"line_sensor_{i}", {}).get("value", 0) for i in range(5)]
    line_display = "  ".join("█" if s else "░" for s in sensors)
    print(f"│    {line_display}                                                                    │")
    print(f"│    S0={sensors[0]}  S1={sensors[1]}  S2={sensors[2]}  S3={sensors[3]}  S4={sensors[4]}                                              │")
    print("└─────────────────────────────────────────────────────────────────────────────┘")
    
    # 电机
    print("\n┌─────────────────────────────────────────────────────────────────────────────┐")
    print("│  电机速度                                                                   │")
    print("├─────────────────────────────────────────────────────────────────────────────┤")
    left = params.get("motor_speed_left", {}).get("value", 0)
    right = params.get("motor_speed_right", {}).get("value", 0)
    left_bar = "█" * int(left / 5) + "░" * (20 - int(left / 5))
    right_bar = "█" * int(right / 5) + "░" * (20 - int(right / 5))
    print(f"│  左: [{left_bar}] {left:5.1f}%                                      │")
    print(f"│  右: [{right_bar}] {right:5.1f}%                                      │")
    print("└─────────────────────────────────────────────────────────────────────────────┘")
    
    # PID 参数
    print("\n┌─────────────────────────────────────────────────────────────────────────────┐")
    print("│  PID 参数                                                                   │")
    print("├─────────────────────────────────────────────────────────────────────────────┤")
    kp = params.get("pid_kp", {}).get("value", 0)
    ki = params.get("pid_ki", {}).get("value", 0)
    kd = params.get("pid_kd", {}).get("value", 0)
    print(f"│  Kp = {kp:8.4f}    Ki = {ki:8.4f}    Kd = {kd:8.4f}                            │")
    print("└─────────────────────────────────────────────────────────────────────────────┘")
    
    # 编码器
    print("\n┌─────────────────────────────────────────────────────────────────────────────┐")
    print("│  编码器                                                                     │")
    print("├─────────────────────────────────────────────────────────────────────────────┤")
    enc_l = params.get("encoder_left", {}).get("value", 0)
    enc_r = params.get("encoder_right", {}).get("value", 0)
    print(f"│  左: {enc_l:8d} pulse    右: {enc_r:8d} pulse                              │")
    print("└─────────────────────────────────────────────────────────────────────────────┘")
    
    # 状态
    print("\n┌─────────────────────────────────────────────────────────────────────────────┐")
    print("│  系统状态                                                                   │")
    print("├─────────────────────────────────────────────────────────────────────────────┤")
    state = params.get("state_machine_main", {}).get("value", "?")
    battery = params.get("battery_voltage", {}).get("value", 0)
    print(f"│  状态机: {state:<10}    电池: {battery:.2f}V                                │")
    print("└─────────────────────────────────────────────────────────────────────────────┘")
    
    # 问题
    if issues:
        print("\n┌─────────────────────────────────────────────────────────────────────────────┐")
        print(f"│  ⚠ 发现 {len(issues)} 个问题                                                          │")
        print("├─────────────────────────────────────────────────────────────────────────────┤")
        for issue in issues:
            icon = "✗" if issue["severity"] == "error" else "⚠"
            print(f"│    {icon} {issue['name']}: {issue['detail']:<60} │")
        print("└─────────────────────────────────────────────────────────────────────────────┘")
    
    print("\n按 Ctrl+C 退出...")

def main():
    """主演示函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="EFW 在线 Debug 效果演示")
    parser.add_argument("--mode", choices=["compact", "detail", "json"], 
                       default="compact", help="显示模式")
    parser.add_argument("--count", type=int, default=50, help="演示次数")
    parser.add_argument("--interval", type=float, default=0.1, help="刷新间隔（秒）")
    parser.add_argument("--expected", help="预期配置文件")
    parser.add_argument("--issues", action="store_true", help="模拟问题")
    
    args = parser.parse_args()
    
    # 加载预期配置
    expected = {}
    if args.expected:
        with open(args.expected, "r", encoding="utf-8") as f:
            expected = json.load(f)
    else:
        # 默认预期配置
        expected = {
            "params": {
                "motor_speed_left": {"min": 0, "max": 100},
                "motor_speed_right": {"min": 0, "max": 100},
                "battery_voltage": {"min": 6.0, "max": 8.4},
                "line_sensor_0": {"enum": [0, 1]},
                "line_sensor_1": {"enum": [0, 1]},
                "line_sensor_2": {"enum": [0, 1]},
                "line_sensor_3": {"enum": [0, 1]},
                "line_sensor_4": {"enum": [0, 1]},
            }
        }
    
    print("╔══════════════════════════════════════════════════════════════════════════════╗")
    print("║                    EFW 在线 Debug 效果演示                                  ║")
    print("╠══════════════════════════════════════════════════════════════════════════════╣")
    print(f"║  显示模式: {args.mode:<10}                                                      ║")
    print(f"║  演示次数: {args.count:<6}                                                            ║")
    print(f"║  刷新间隔: {args.interval*1000:.0f}ms                                                          ║")
    print("╚══════════════════════════════════════════════════════════════════════════════╝")
    
    time.sleep(1)
    
    # 记录开始
    records = []
    issue_count = 0
    
    try:
        for i in range(args.count):
            # 生成快照
            snapshot = generate_snapshot(i)
            
            # 模拟问题
            if args.issues and i > 20 and random.random() < 0.1:
                # 模拟电池电压过低
                snapshot["params"]["battery_voltage"]["value"] = 5.5
            if args.issues and i > 30 and random.random() < 0.05:
                # 模拟电机速度超限
                snapshot["params"]["motor_speed_left"]["value"] = 105.0
            
            # 检查问题
            issues = check_issues(snapshot, expected)
            if issues:
                issue_count += len(issues)
            
            # 记录
            records.append(snapshot)
            
            # 显示
            if args.mode == "json":
                print(json.dumps(snapshot, ensure_ascii=False))
            elif args.mode == "compact":
                print_snapshot(snapshot, issues, compact=True)
            else:
                print_snapshot(snapshot, issues, compact=False)
            
            time.sleep(args.interval)
    
    except KeyboardInterrupt:
        pass
    
    # 统计
    print("\n" + "=" * 80)
    print("演示结束")
    print("=" * 80)
    print(f"总快照数: {len(records)}")
    print(f"总问题数: {issue_count}")
    print(f"平均 FPS: {len(records) / (args.count * args.interval):.1f}")

if __name__ == "__main__":
    main()
