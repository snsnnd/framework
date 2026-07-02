#!/usr/bin/env python3
"""
EFW 在线 Debug 完整功能演示

展示：
1. 数据流可视化
2. 任务监控和周期对比
3. 事件话题监控
4. 离线/在线对比告警
"""

import json
import random
import time
from datetime import datetime, timezone
from typing import Any


class MockGraph:
    """模拟 graph JSON（离线规格）"""
    
    @staticmethod
    def get_example() -> dict:
        """返回示例 graph"""
        return {
            "project": {
                "name": "line_tracking_car",
                "tick_ms": 1,
            },
            "tasks": [
                {"id": "control_loop", "period_ms": 1, "type": "periodic", "call": "app_loop_1ms"},
                {"id": "sensor_read", "period_ms": 5, "type": "periodic", "call": "read_sensors"},
                {"id": "telemetry", "period_ms": 100, "type": "periodic", "call": "send_telemetry"},
            ],
            "nodes": [
                {"id": "line_sensor", "type": "sensor.line_tracking"},
                {"id": "left_motor", "type": "actuator.motor"},
                {"id": "right_motor", "type": "actuator.motor"},
                {"id": "line_pid", "type": "algorithm.pid"},
                {"id": "motor_control", "type": "module.custom"},
                {"id": "telemetry_module", "type": "module.custom"},
                {"id": "sensor_data_topic", "type": "event.topic", "topic_id": 1},
                {"id": "motor_cmd_topic", "type": "event.topic", "topic_id": 2},
                {"id": "sensor_publisher", "type": "event.publisher", "topic": "sensor_data_topic"},
                {"id": "motor_subscriber", "type": "event.subscriber", "topic": "motor_cmd_topic"},
            ],
            "edges": [
                {"source": "line_sensor", "target": "line_pid", "kind": "data_flow"},
                {"source": "line_pid", "target": "left_motor", "kind": "data_flow"},
                {"source": "line_pid", "target": "right_motor", "kind": "data_flow"},
            ],
            "flows": [
                {
                    "id": "line_follow",
                    "sensor": "line_sensor",
                    "pid": "line_pid",
                    "left_motor": "left_motor",
                    "right_motor": "right_motor",
                    "period_ms": 1,
                }
            ],
        }


class MockRuntimeData:
    """模拟在线运行时数据"""
    
    def __init__(self):
        self.seq = 0
        self.anomaly_mode = False
        self.anomaly_counter = 0
    
    def generate_snapshot(self) -> dict:
        """生成运行时快照"""
        self.seq += 1
        now = time.time() * 1000000  # 微秒
        
        # 模拟任务数据
        tasks = {
            "control_loop": {
                "state": "running",
                "expected_period_us": 1000,
                "actual_period_us": 1000 + random.randint(-50, 50),
                "execution_time_us": 120 + random.randint(-10, 10),
                "max_execution_time_us": 180,
                "run_count": self.seq,
                "overrun_count": 0,
                "last_run_time": now,
            },
            "sensor_read": {
                "state": "running",
                "expected_period_us": 5000,
                "actual_period_us": 5000 + random.randint(-100, 100),
                "execution_time_us": 450 + random.randint(-20, 20),
                "max_execution_time_us": 600,
                "run_count": self.seq // 5,
                "overrun_count": 0,
                "last_run_time": now,
            },
            "telemetry": {
                "state": "running",
                "expected_period_us": 100000,
                "actual_period_us": 100000 + random.randint(-1000, 1000),
                "execution_time_us": 2500 + random.randint(-100, 100),
                "max_execution_time_us": 3000,
                "run_count": self.seq // 100,
                "overrun_count": 0,
                "last_run_time": now,
            },
        }
        
        # 模拟模块数据
        modules = {
            "motor_control": {
                "state": "started",
                "poll_count": self.seq,
                "avg_poll_time_us": 15 + random.randint(-2, 2),
                "max_poll_time_us": 25,
                "last_activity_time": now,
            },
            "telemetry_module": {
                "state": "started",
                "poll_count": self.seq // 100,
                "avg_poll_time_us": 1200 + random.randint(-50, 50),
                "max_poll_time_us": 1500,
                "last_activity_time": now,
            },
        }
        
        # 模拟话题数据
        topics = {
            "sensor_data_topic": {
                "topic_id": 1,
                "publisher_count": 1,
                "subscriber_count": 2,
                "publish_count": self.seq,
                "receive_count": self.seq * 2,
                "drop_count": random.randint(0, 5),
                "last_publish_time": now,
                "last_receive_time": now,
            },
            "motor_cmd_topic": {
                "topic_id": 2,
                "publisher_count": 1,
                "subscriber_count": 1,
                "publish_count": self.seq,
                "receive_count": self.seq,
                "drop_count": 0,
                "last_publish_time": now,
                "last_receive_time": now,
            },
        }
        
        # 模拟数据流
        dataflows = {
            "line_sensor->line_pid": {
                "transfer_count": self.seq,
                "last_value_size": 4,
                "last_transfer_time": now,
            },
            "line_pid->left_motor": {
                "transfer_count": self.seq,
                "last_value_size": 4,
                "last_transfer_time": now,
            },
            "line_pid->right_motor": {
                "transfer_count": self.seq,
                "last_value_size": 4,
                "last_transfer_time": now,
            },
        }
        
        # 模拟异常场景
        self.anomaly_counter += 1
        if self.anomaly_mode and self.anomaly_counter % 50 == 0:
            # 模拟任务超时
            tasks["control_loop"]["execution_time_us"] = 1200
            tasks["control_loop"]["overrun_count"] = 10
        
        if self.anomaly_mode and self.anomaly_counter % 70 == 0:
            # 模拟模块卡住
            modules["motor_control"]["last_activity_time"] = now - 2000000
        
        return {
            "timestamp": now,
            "uptime_ms": self.seq,
            "tasks": tasks,
            "modules": modules,
            "topics": topics,
            "dataflows": dataflows,
            "resources": {
                "cpu_usage_percent": 35 + random.randint(-5, 5),
                "stack_used_bytes": 512 + random.randint(-20, 20),
            },
        }


def print_header():
    """打印标题"""
    print("\033[2J\033[H")  # 清屏
    print("╔════════════════════════════════════════════════════════════════════════════════════════╗")
    print("║                           EFW 在线 Debug 完整功能演示                                  ║")
    print("╠════════════════════════════════════════════════════════════════════════════════════════╣")
    print("║  功能: 数据流 | 任务监控 | 事件话题 | 离线/在线对比 | 自动告警                          ║")
    print("╚════════════════════════════════════════════════════════════════════════════════════════╝")


def print_dataflow(dataflows: dict):
    """打印数据流"""
    print("\n┌────────────────────────────────────────────────────────────────────────────────────────┐")
    print("│  📊 数据流                                                                             │")
    print("├────────────────────────────────────────────────────────────────────────────────────────┤")
    
    for flow_name, flow_info in dataflows.items():
        source, sink = flow_name.split("->")
        count = flow_info.get("transfer_count", 0)
        last_time = flow_info.get("last_transfer_time", 0)
        
        # 简化显示
        print(f"│    {source:<15} ──────► {sink:<15}   (传输次数: {count:>6})                        │")
    
    print("└────────────────────────────────────────────────────────────────────────────────────────┘")


def print_tasks(tasks: dict, spec_tasks: dict):
    """打印任务监控"""
    print("\n┌────────────────────────────────────────────────────────────────────────────────────────┐")
    print("│  ⏱️  任务监控                                                                          │")
    print("├────────────────────────────────────────────────────────────────────────────────────────┤")
    print("│  任务名称           │ 状态    │ 预期周期 │ 实际周期 │ 执行时间 │ 运行次数 │ 超时次数 │")
    print("├─────────────────────┼─────────┼──────────┼──────────┼──────────┼──────────┼──────────┤")
    
    for task_name, task_info in tasks.items():
        state = task_info.get("state", "unknown")
        expected = task_info.get("expected_period_us", 0)
        actual = task_info.get("actual_period_us", 0)
        execution = task_info.get("execution_time_us", 0)
        run_count = task_info.get("run_count", 0)
        overrun = task_info.get("overrun_count", 0)
        
        # 状态颜色标记
        state_icon = "●" if state == "running" else "○"
        overrun_str = f"{overrun}" if overrun > 0 else "-"
        
        print(f"│  {task_name:<19} │ {state_icon} {state:<6} │ {expected:>6}us │ {actual:>6}us │ {execution:>6}us │ {run_count:>8} │ {overrun_str:>8} │")
    
    print("└─────────────────────┴─────────┴──────────┴──────────┴──────────┴──────────┴──────────┘")


def print_modules(modules: dict):
    """打印模块状态"""
    print("\n┌────────────────────────────────────────────────────────────────────────────────────────┐")
    print("│  📦 模块状态                                                                           │")
    print("├────────────────────────────────────────────────────────────────────────────────────────┤")
    print("│  模块名称           │ 状态    │ 轮询次数 │ 平均时间 │ 最大时间 │ 最后活动              │")
    print("├─────────────────────┼─────────┼──────────┼──────────┼──────────┼───────────────────────┤")
    
    for mod_name, mod_info in modules.items():
        state = mod_info.get("state", "unknown")
        poll_count = mod_info.get("poll_count", 0)
        avg_poll = mod_info.get("avg_poll_time_us", 0)
        max_poll = mod_info.get("max_poll_time_us", 0)
        last_activity = mod_info.get("last_activity_time", 0)
        
        # 状态图标
        state_icon = "●" if state == "started" else "○"
        
        # 格式化最后活动时间
        last_activity_str = f"{last_activity/1000000:.1f}s ago"
        
        print(f"│  {mod_name:<19} │ {state_icon} {state:<6} │ {poll_count:>8} │ {avg_poll:>6}us │ {max_poll:>6}us │ {last_activity_str:<21} │")
    
    print("└─────────────────────┴─────────┴──────────┴──────────┴──────────┴───────────────────────┘")


def print_topics(topics: dict):
    """打印事件话题"""
    print("\n┌────────────────────────────────────────────────────────────────────────────────────────┐")
    print("│  📢 事件话题                                                                           │")
    print("├────────────────────────────────────────────────────────────────────────────────────────┤")
    print("│  话题名称           │ ID  │ 发布者 │ 订阅者 │ 发布次数 │ 接收次数 │ 丢弃次数 │ 丢弃率 │")
    print("├─────────────────────┼─────┼────────┼────────┼──────────┼──────────┼──────────┼────────┤")
    
    for topic_name, topic_info in topics.items():
        topic_id = topic_info.get("topic_id", 0)
        pub_count = topic_info.get("publisher_count", 0)
        sub_count = topic_info.get("subscriber_count", 0)
        publish = topic_info.get("publish_count", 0)
        receive = topic_info.get("receive_count", 0)
        drop = topic_info.get("drop_count", 0)
        
        # 计算丢弃率
        total = receive + drop
        drop_rate = f"{drop/total*100:.1f}%" if total > 0 else "-"
        
        print(f"│  {topic_name:<19} │ {topic_id:>3} │ {pub_count:>6} │ {sub_count:>6} │ {publish:>8} │ {receive:>8} │ {drop:>8} │ {drop_rate:>6} │")
    
    print("└─────────────────────┴─────┴────────┴────────┴──────────┴──────────┴──────────┴────────┘")


def print_resources(resources: dict):
    """打印资源使用"""
    print("\n┌────────────────────────────────────────────────────────────────────────────────────────┐")
    print("│  💻 资源使用                                                                           │")
    print("├────────────────────────────────────────────────────────────────────────────────────────┤")
    
    cpu = resources.get("cpu_usage_percent", 0)
    stack = resources.get("stack_used_bytes", 0)
    
    # CPU 进度条
    cpu_bar_len = int(cpu / 5)
    cpu_bar = "█" * cpu_bar_len + "░" * (20 - cpu_bar_len)
    cpu_status = "✓" if cpu < 80 else "⚠" if cpu < 90 else "✗"
    
    # 栈进度条
    stack_limit = 1024
    stack_percent = stack / stack_limit * 100
    stack_bar_len = int(stack_percent / 5)
    stack_bar = "█" * stack_bar_len + "░" * (20 - stack_bar_len)
    stack_status = "✓" if stack_percent < 80 else "⚠" if stack_percent < 90 else "✗"
    
    print(f"│  CPU 使用率: [{cpu_bar}] {cpu:>3}% {cpu_status}                              │")
    print(f"│  栈使用量:   [{stack_bar}] {stack:>4}/{stack_limit} bytes {stack_status}                   │")
    
    print("└────────────────────────────────────────────────────────────────────────────────────────┘")


def print_anomalies(anomalies: list):
    """打印异常告警"""
    print("\n┌────────────────────────────────────────────────────────────────────────────────────────┐")
    print(f"│  ⚠️  离线/在线对比告警 ({len(anomalies)} 个异常)                                                    │")
    print("├────────────────────────────────────────────────────────────────────────────────────────┤")
    
    if not anomalies:
        print("│  ✓ 所有检查通过，未发现异常                                                              │")
    else:
        for a in anomalies:
            severity = a.get("severity", "info")
            name = a.get("name", "")
            detail = a.get("detail", "")
            suggestion = a.get("suggestion", "")
            
            # 严重程度图标
            if severity == "critical":
                icon = "🔴"
            elif severity == "error":
                icon = "❌"
            elif severity == "warning":
                icon = "⚠️ "
            else:
                icon = "ℹ️ "
            
            print(f"│  {icon} [{severity.upper():>8}] {name:<20}                                   │")
            print(f"│      {detail:<84} │")
            if suggestion:
                print(f"│      建议: {suggestion:<78} │")
    
    print("└────────────────────────────────────────────────────────────────────────────────────────┘")


def print_status_bar(seq: int, fps: float, anomaly_mode: bool):
    """打印状态栏"""
    print("\n┌────────────────────────────────────────────────────────────────────────────────────────┐")
    mode_str = "🔴 异常模式" if anomaly_mode else "🟢 正常模式"
    print(f"│  序列: {seq:<8}  FPS: {fps:.1f}  模式: {mode_str:<12}  按 Ctrl+C 退出  按 'a' 切换异常模式 │")
    print("└────────────────────────────────────────────────────────────────────────────────────────┘")


def main():
    """主演示函数"""
    import argparse
    import select
    import sys
    import tty
    import termios
    
    parser = argparse.ArgumentParser(description="EFW 在线 Debug 完整功能演示")
    parser.add_argument("--interval", type=float, default=0.2, help="刷新间隔（秒）")
    parser.add_argument("--anomaly", action="store_true", help="启用异常模拟")
    parser.add_argument("--count", type=int, default=0, help="运行次数（0=无限）")
    
    args = parser.parse_args()
    
    # 初始化
    mock_graph = MockGraph.get_example()
    mock_runtime = MockRuntimeData()
    mock_runtime.anomaly_mode = args.anomaly
    
    # 离线规格
    spec_tasks = {t["id"]: t for t in mock_graph.get("tasks", [])}
    
    print("╔════════════════════════════════════════════════════════════════════════════════════════╗")
    print("║                    EFW 在线 Debug 完整功能演示启动中...                                ║")
    print("╚════════════════════════════════════════════════════════════════════════════════════════╝")
    time.sleep(1)
    
    # 设置非阻塞输入（如果可能）
    fd = sys.stdin.fileno()
    old_settings = None
    try:
        old_settings = termios.tcgetattr(fd)
        tty.setcbreak(fd)
    except:
        pass
    
    count = 0
    try:
        while True:
            # 检查键盘输入
            try:
                if select.select([sys.stdin], [], [], 0)[0]:
                    key = sys.stdin.read(1)
                    if key == 'a':
                        mock_runtime.anomaly_mode = not mock_runtime.anomaly_mode
            except:
                pass
            
            # 生成快照
            snapshot = mock_runtime.generate_snapshot()
            
            # 离线/在线对比（简化版）
            anomalies = []
            for task_name, task_info in snapshot["tasks"].items():
                expected = task_info.get("expected_period_us", 0)
                execution = task_info.get("execution_time_us", 0)
                overrun = task_info.get("overrun_count", 0)
                
                if execution > expected:
                    anomalies.append({
                        "type": "task_overrun",
                        "severity": "warning",
                        "name": task_name,
                        "detail": f"任务 {task_name} 执行时间 ({execution}us) 超过预期周期 ({expected}us)",
                        "suggestion": "优化任务执行时间或增加周期",
                    })
                
                if overrun > 0:
                    anomalies.append({
                        "type": "task_overrun",
                        "severity": "error",
                        "name": task_name,
                        "detail": f"任务 {task_name} 已超时 {overrun} 次",
                        "suggestion": "分析超时原因并优化",
                    })
            
            # 检查模块活动
            now = time.time() * 1000000
            for mod_name, mod_info in snapshot["modules"].items():
                last_activity = mod_info.get("last_activity_time", 0)
                if now - last_activity > 1000000:
                    anomalies.append({
                        "type": "module_stuck",
                        "severity": "warning",
                        "name": mod_name,
                        "detail": f"模块 {mod_name} 已 {(now-last_activity)/1000:.1f}ms 无活动",
                        "suggestion": "检查模块是否被阻塞",
                    })
            
            # 打印界面
            print_header()
            print_dataflow(snapshot.get("dataflows", {}))
            print_tasks(snapshot.get("tasks", {}), spec_tasks)
            print_modules(snapshot.get("modules", {}))
            print_topics(snapshot.get("topics", {}))
            print_resources(snapshot.get("resources", {}))
            print_anomalies(anomalies)
            
            count += 1
            fps = 1.0 / args.interval if args.interval > 0 else 0
            print_status_bar(count, fps, mock_runtime.anomaly_mode)
            
            # 检查退出条件
            if args.count > 0 and count >= args.count:
                break
            
            time.sleep(args.interval)
    
    except KeyboardInterrupt:
        pass
    finally:
        # 恢复终端设置
        if old_settings:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            except:
                pass
    
    print("\n\n演示结束！")


if __name__ == "__main__":
    main()
