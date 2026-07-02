"""
仿真器性能检测模块

提供全面的性能监控和分析功能：
- CPU 使用率
- 内存使用情况
- 仿真速度（FPS）
- 任务执行时间
- 外设访问统计
- 性能瓶颈分析
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class PerformanceMetrics:
    """性能指标"""
    timestamp: float = 0.0
    
    # 时间指标
    frame_time_ms: float = 0.0      # 帧时间
    cpu_time_ms: float = 0.0        # CPU 使用时间
    idle_time_ms: float = 0.0       # 空闲时间
    
    # 仿真指标
    cycles_executed: int = 0         # 执行的周期数
    instructions_executed: int = 0   # 执行的指令数
    simulation_speed: float = 0.0    # 仿真速度（相对于实时）
    
    # 内存指标
    flash_used_kb: float = 0.0      # Flash 使用量
    sram_used_kb: float = 0.0       # SRAM 使用量
    stack_used_kb: float = 0.0      # 栈使用量
    
    # 外设指标
    gpio_reads: int = 0             # GPIO 读取次数
    gpio_writes: int = 0            # GPIO 写入次数
    adc_reads: int = 0              # ADC 读取次数
    pwm_updates: int = 0            # PWM 更新次数
    uart_transfers: int = 0         # UART 传输次数
    i2c_transfers: int = 0          # I2C 传输次数
    spi_transfers: int = 0          # SPI 传输次数
    
    # 中断指标
    interrupt_count: int = 0         # 中断次数
    interrupt_time_ms: float = 0.0   # 中断处理时间


@dataclass
class TaskProfile:
    """任务性能分析"""
    name: str
    call_count: int = 0
    total_time_ms: float = 0.0
    min_time_ms: float = float('inf')
    max_time_ms: float = 0.0
    avg_time_ms: float = 0.0
    last_time_ms: float = 0.0
    
    def update(self, time_ms: float):
        """更新统计"""
        self.call_count += 1
        self.total_time_ms += time_ms
        self.last_time_ms = time_ms
        self.min_time_ms = min(self.min_time_ms, time_ms)
        self.max_time_ms = max(self.max_time_ms, time_ms)
        self.avg_time_ms = self.total_time_ms / self.call_count


class PerformanceMonitor:
    """性能监控器
    
    使用方式：
        monitor = PerformanceMonitor()
        monitor.start()
        
        # 在仿真循环中
        monitor.begin_frame()
        # ... 仿真代码 ...
        monitor.end_frame()
        
        # 获取统计
        stats = monitor.get_stats()
    """
    
    def __init__(self, history_size: int = 1000):
        self.history_size = history_size
        self.history: deque[PerformanceMetrics] = deque(maxlen=history_size)
        
        self.running = False
        self.start_time = 0.0
        self.frame_count = 0
        
        # 当前帧数据
        self._frame_start = 0.0
        self._frame_cycles = 0
        self._frame_instructions = 0
        
        # 累计数据
        self._total_cycles = 0
        self._total_instructions = 0
        self._total_cpu_time = 0.0
        
        # 外设访问计数
        self._peripheral_counts = {
            'gpio_reads': 0,
            'gpio_writes': 0,
            'adc_reads': 0,
            'pwm_updates': 0,
            'uart_transfers': 0,
            'i2c_transfers': 0,
            'spi_transfers': 0,
        }
        
        # 任务分析
        self._tasks: dict[str, TaskProfile] = {}
        self._current_task: Optional[str] = None
        self._task_start = 0.0
        
        # 中断统计
        self._interrupt_count = 0
        self._interrupt_time = 0.0
        
        # 实时速度计算
        self._real_time_start = 0.0
        self._sim_time_us = 0.0
    
    def start(self):
        """开始监控"""
        self.running = True
        self.start_time = time.monotonic()
        self._real_time_start = self.start_time
        self.frame_count = 0
    
    def stop(self):
        """停止监控"""
        self.running = False
    
    def reset(self):
        """重置统计"""
        self.history.clear()
        self.frame_count = 0
        self._total_cycles = 0
        self._total_instructions = 0
        self._total_cpu_time = 0.0
        self._peripheral_counts = {k: 0 for k in self._peripheral_counts}
        self._tasks.clear()
        self._interrupt_count = 0
        self._interrupt_time = 0.0
    
    def begin_frame(self):
        """开始一帧"""
        if not self.running:
            return
        
        self._frame_start = time.monotonic()
        self._frame_cycles = 0
        self._frame_instructions = 0
    
    def end_frame(self, cycles: int = 0, instructions: int = 0):
        """结束一帧"""
        if not self.running:
            return
        
        now = time.monotonic()
        frame_time = (now - self._frame_start) * 1000  # ms
        
        self._frame_cycles = cycles
        self._frame_instructions = instructions
        self._total_cycles += cycles
        self._total_instructions += instructions
        self._total_cpu_time += frame_time
        self.frame_count += 1
        
        # 计算仿真速度
        sim_time_us = cycles / 168  # 假设 168MHz
        real_time_us = frame_time * 1000
        sim_speed = sim_time_us / real_time_us if real_time_us > 0 else 0
        
        # 创建指标
        metrics = PerformanceMetrics(
            timestamp=now,
            frame_time_ms=frame_time,
            cpu_time_ms=frame_time,
            idle_time_ms=max(0, 1.0 - frame_time),  # 假设 1ms 目标帧时间
            cycles_executed=cycles,
            instructions_executed=instructions,
            simulation_speed=sim_speed,
            **self._peripheral_counts,
            interrupt_count=self._interrupt_count,
            interrupt_time_ms=self._interrupt_time,
        )
        
        self.history.append(metrics)
        
        # 重置帧数据
        self._peripheral_counts = {k: 0 for k in self._peripheral_counts}
        self._interrupt_count = 0
        self._interrupt_time = 0.0
    
    def record_peripheral_access(self, peripheral: str, count: int = 1):
        """记录外设访问"""
        key = f"{peripheral}s" if not peripheral.endswith('s') else peripheral
        if key in self._peripheral_counts:
            self._peripheral_counts[key] += count
    
    def begin_interrupt(self):
        """开始中断处理"""
        self._interrupt_start = time.monotonic()
    
    def end_interrupt(self):
        """结束中断处理"""
        self._interrupt_count += 1
        self._interrupt_time += (time.monotonic() - self._interrupt_start) * 1000
    
    def begin_task(self, name: str):
        """开始任务分析"""
        if self._current_task:
            self.end_task()
        
        self._current_task = name
        self._task_start = time.monotonic()
    
    def end_task(self):
        """结束任务分析"""
        if not self._current_task:
            return
        
        elapsed = (time.monotonic() - self._task_start) * 1000
        
        if self._current_task not in self._tasks:
            self._tasks[self._current_task] = TaskProfile(name=self._current_task)
        
        self._tasks[self._current_task].update(elapsed)
        self._current_task = None
    
    def update_sim_time(self, us: float):
        """更新仿真时间"""
        self._sim_time_us += us
    
    def get_current_metrics(self) -> PerformanceMetrics:
        """获取当前指标"""
        if not self.history:
            return PerformanceMetrics()
        return self.history[-1]
    
    def get_average_metrics(self, last_n: int = 100) -> PerformanceMetrics:
        """获取平均指标"""
        if not self.history:
            return PerformanceMetrics()
        
        samples = list(self.history)[-last_n:]
        n = len(samples)
        
        avg = PerformanceMetrics()
        avg.frame_time_ms = sum(m.frame_time_ms for m in samples) / n
        avg.cpu_time_ms = sum(m.cpu_time_ms for m in samples) / n
        avg.simulation_speed = sum(m.simulation_speed for m in samples) / n
        avg.cycles_executed = sum(m.cycles_executed for m in samples) // n
        avg.instructions_executed = sum(m.instructions_executed for m in samples) // n
        
        return avg
    
    def get_stats(self) -> dict[str, Any]:
        """获取完整统计"""
        current = self.get_current_metrics()
        average = self.get_average_metrics()
        
        elapsed = time.monotonic() - self.start_time if self.start_time else 0
        
        return {
            'running': self.running,
            'elapsed_seconds': elapsed,
            'frame_count': self.frame_count,
            'total_cycles': self._total_cycles,
            'total_instructions': self._total_instructions,
            'current': {
                'frame_time_ms': current.frame_time_ms,
                'cpu_time_ms': current.cpu_time_ms,
                'simulation_speed': current.simulation_speed,
                'cycles': current.cycles_executed,
                'instructions': current.instructions_executed,
            },
            'average': {
                'frame_time_ms': average.frame_time_ms,
                'cpu_time_ms': average.cpu_time_ms,
                'simulation_speed': average.simulation_speed,
            },
            'fps': self.frame_count / elapsed if elapsed > 0 else 0,
            'tasks': {name: {
                'call_count': t.call_count,
                'avg_time_ms': t.avg_time_ms,
                'min_time_ms': t.min_time_ms,
                'max_time_ms': t.max_time_ms,
                'total_time_ms': t.total_time_ms,
            } for name, t in self._tasks.items()},
            'peripherals': self._peripheral_counts.copy(),
        }
    
    def get_task_report(self) -> str:
        """获取任务分析报告"""
        if not self._tasks:
            return "无任务数据"
        
        lines = [
            "=" * 60,
            "任务性能分析报告",
            "=" * 60,
            f"{'任务名':<20} {'调用次数':>10} {'平均时间':>12} {'最小时间':>12} {'最大时间':>12}",
            "-" * 60,
        ]
        
        for name, task in sorted(self._tasks.items(), key=lambda x: x[1].total_time_ms, reverse=True):
            lines.append(
                f"{name:<20} {task.call_count:>10} "
                f"{task.avg_time_ms:>10.3f}ms {task.min_time_ms:>10.3f}ms {task.max_time_ms:>10.3f}ms"
            )
        
        lines.append("=" * 60)
        
        return "\n".join(lines)
    
    def get_performance_report(self) -> str:
        """获取完整性能报告"""
        stats = self.get_stats()
        
        lines = [
            "=" * 60,
            "仿真器性能报告",
            "=" * 60,
            "",
            "运行状态:",
            f"  运行时间: {stats['elapsed_seconds']:.1f} 秒",
            f"  帧数量: {stats['frame_count']}",
            f"  FPS: {stats['fps']:.1f}",
            "",
            "当前帧:",
            f"  帧时间: {stats['current']['frame_time_ms']:.3f} ms",
            f"  CPU 时间: {stats['current']['cpu_time_ms']:.3f} ms",
            f"  仿真速度: {stats['current']['simulation_speed']:.2f}x",
            f"  周期数: {stats['current']['cycles']}",
            f"  指令数: {stats['current']['instructions']}",
            "",
            "平均值（最近 100 帧）:",
            f"  帧时间: {stats['average']['frame_time_ms']:.3f} ms",
            f"  CPU 时间: {stats['average']['cpu_time_ms']:.3f} ms",
            f"  仿真速度: {stats['average']['simulation_speed']:.2f}x",
            "",
            "累计数据:",
            f"  总周期数: {stats['total_cycles']:,}",
            f"  总指令数: {stats['total_instructions']:,}",
            "",
            "外设访问:",
        ]
        
        for name, count in stats['peripherals'].items():
            if count > 0:
                lines.append(f"  {name}: {count:,}")
        
        if self._tasks:
            lines.append("")
            lines.append(self.get_task_report())
        
        lines.append("=" * 60)
        
        return "\n".join(lines)


class PerformanceBenchmark:
    """性能基准测试
    
    使用方式：
        benchmark = PerformanceBenchmark(mcu)
        
        # 运行基准测试
        results = benchmark.run_all()
        
        # 打印报告
        print(benchmark.format_report(results))
    """
    
    def __init__(self, mcu=None):
        self.mcu = mcu
        self.results: dict[str, dict] = {}
    
    def run_cpu_benchmark(self, iterations: int = 1000000) -> dict:
        """CPU 性能测试"""
        start = time.perf_counter()
        
        # 模拟 CPU 计算
        result = 0
        for i in range(iterations):
            result += i * i
        
        elapsed = time.perf_counter() - start
        
        return {
            'name': 'CPU 计算',
            'iterations': iterations,
            'elapsed_seconds': elapsed,
            'iterations_per_second': iterations / elapsed,
            'mips': iterations / elapsed / 1_000_000,
        }
    
    def run_memory_benchmark(self, size_kb: int = 1024) -> dict:
        """内存性能测试"""
        # 分配
        start = time.perf_counter()
        data = bytearray(size_kb * 1024)
        alloc_time = time.perf_counter() - start
        
        # 写入
        start = time.perf_counter()
        for i in range(0, len(data), 4):
            data[i] = i & 0xFF
        write_time = time.perf_counter() - start
        
        # 读取
        start = time.perf_counter()
        checksum = 0
        for i in range(0, len(data), 4):
            checksum += data[i]
        read_time = time.perf_counter() - start
        
        del data
        
        return {
            'name': '内存访问',
            'size_kb': size_kb,
            'alloc_time_ms': alloc_time * 1000,
            'write_time_ms': write_time * 1000,
            'read_time_ms': read_time * 1000,
            'write_speed_mb_s': size_kb / 1024 / write_time,
            'read_speed_mb_s': size_kb / 1024 / read_time,
        }
    
    def run_peripheral_benchmark(self, iterations: int = 10000) -> dict:
        """外设访问性能测试"""
        if not self.mcu:
            return {'name': '外设访问', 'error': '未配置 MCU'}
        
        # GPIO 测试
        start = time.perf_counter()
        for _ in range(iterations):
            self.mcu.gpio_write('A', 0, 1)
            self.mcu.gpio_read('A', 0)
        gpio_time = time.perf_counter() - start
        
        # ADC 测试
        start = time.perf_counter()
        for _ in range(iterations):
            self.mcu.adc_read(0)
        adc_time = time.perf_counter() - start
        
        return {
            'name': '外设访问',
            'iterations': iterations,
            'gpio_time_ms': gpio_time * 1000,
            'gpio_ops_per_second': iterations * 2 / gpio_time,
            'adc_time_ms': adc_time * 1000,
            'adc_ops_per_second': iterations / adc_time,
        }
    
    def run_simulation_benchmark(self, duration_ms: float = 1000) -> dict:
        """仿真性能测试"""
        if not self.mcu:
            return {'name': '仿真', 'error': '未配置 MCU'}
        
        cycles_per_ms = self.mcu.clock.sysclk_hz // 1000
        total_cycles = int(duration_ms * cycles_per_ms)
        
        start = time.perf_counter()
        self.mcu.tick(total_cycles)
        elapsed = time.perf_counter() - start
        
        sim_time_s = total_cycles / self.mcu.clock.sysclk_hz
        
        return {
            'name': '仿真',
            'target_ms': duration_ms,
            'elapsed_ms': elapsed * 1000,
            'cycles': total_cycles,
            'sim_speed': sim_time_s / elapsed if elapsed > 0 else 0,
            'cycles_per_second': total_cycles / elapsed if elapsed > 0 else 0,
        }
    
    def run_all(self) -> dict[str, dict]:
        """运行所有基准测试"""
        self.results = {
            'cpu': self.run_cpu_benchmark(),
            'memory': self.run_memory_benchmark(),
            'peripheral': self.run_peripheral_benchmark(),
            'simulation': self.run_simulation_benchmark(),
        }
        return self.results
    
    def format_report(self, results: Optional[dict] = None) -> str:
        """格式化报告"""
        if results is None:
            results = self.results
        
        lines = [
            "=" * 60,
            "仿真器性能基准测试报告",
            "=" * 60,
        ]
        
        for name, data in results.items():
            lines.append(f"\n{data.get('name', name)}:")
            
            if 'error' in data:
                lines.append(f"  错误: {data['error']}")
                continue
            
            for key, value in data.items():
                if key == 'name':
                    continue
                
                if isinstance(value, float):
                    if value < 0.001:
                        lines.append(f"  {key}: {value*1000000:.1f} us")
                    elif value < 1:
                        lines.append(f"  {key}: {value*1000:.3f} ms")
                    else:
                        lines.append(f"  {key}: {value:.3f}")
                else:
                    lines.append(f"  {key}: {value:,}" if isinstance(value, int) else f"  {key}: {value}")
        
        lines.append("\n" + "=" * 60)
        
        return "\n".join(lines)


# ─── 使用示例 ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from .core import MCUSimulator, MCUType
    
    print("性能基准测试")
    print()
    
    # 创建 MCU
    mcu = MCUSimulator(MCUType.STM32F407)
    
    # 运行基准测试
    benchmark = PerformanceBenchmark(mcu)
    results = benchmark.run_all()
    print(benchmark.format_report(results))
    
    print()
    
    # 运行性能监控示例
    print("性能监控示例")
    print()
    
    monitor = PerformanceMonitor()
    monitor.start()
    
    # 模拟仿真循环
    for i in range(100):
        monitor.begin_frame()
        monitor.begin_task("control_loop")
        
        # 模拟控制逻辑
        mcu.tick(168000)  # 1ms
        
        monitor.end_task()
        monitor.end_frame(cycles=168000, instructions=168000)
    
    print(monitor.get_performance_report())
