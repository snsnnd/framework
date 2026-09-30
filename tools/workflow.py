#!/usr/bin/env python3
"""
EFW 全流程工具链

整合设计、开发、仿真、调试、部署为统一工具链。

使用方式：
  # 启动完整工作台
  python3 tools/efw.py workflow
  
  # 或分步骤执行
  python3 tools/efw.py design      # 设计阶段
  python3 tools/efw.py develop     # 开发阶段
  python3 tools/efw.py simulate    # 仿真阶段
  python3 tools/efw.py debug       # 调试阶段
  python3 tools/efw.py deploy      # 部署阶段
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional


# ─── 项目管理 ────────────────────────────────────────────────────────────────

class ProjectManager:
    """项目管理器"""
    
    def __init__(self, project_path: Optional[Path] = None):
        self.project_path = project_path or Path.cwd()
        self.config_path = self.project_path / ".efw_project.json"
        self.config: dict[str, Any] = {}
        
        if self.config_path.exists():
            self.load()
    
    def load(self):
        """加载项目配置"""
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)
    
    def save(self):
        """保存项目配置"""
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
    
    def create(self, name: str, chip: str = "", board: str = ""):
        """创建新项目"""
        self.config = {
            "name": name,
            "version": "1.0.0",
            "chip": chip,
            "board": board,
            "created": self._now(),
            "modified": self._now(),
            "stages": {
                "design": {"status": "pending", "graph": None},
                "develop": {"status": "pending", "files": []},
                "simulate": {"status": "pending", "scenarios": []},
                "debug": {"status": "pending", "sessions": []},
                "deploy": {"status": "pending", "outputs": []},
            },
            "settings": {
                "clock_mhz": 168,
                "tick_ms": 1,
            },
        }
        self.save()
    
    def _now(self) -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


# ─── 工作流阶段 ──────────────────────────────────────────────────────────────

class DesignStage:
    """设计阶段：图形化设计、组件选择、引脚配置"""
    
    @staticmethod
    def launch(project: ProjectManager):
        """启动设计工具"""
        print("启动设计工作台...")
        print("  - 图形化组件拖拽")
        print("  - 引脚配置")
        print("  - 数据流设计")
        print("  - 状态机设计")
        
        # 启动 Studio
        from studio.app import main as studio_main
        return studio_main()
    
    @staticmethod
    def validate(graph_path: Path) -> bool:
        """验证设计"""
        from codegen.validate import validate_graph
        
        try:
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
            validate_graph(graph)
            print("✓ 设计验证通过")
            return True
        except Exception as e:
            print(f"✗ 设计验证失败: {e}")
            return False


class DevelopStage:
    """开发阶段：代码生成、编译构建"""
    
    @staticmethod
    def generate(project: ProjectManager, graph_path: Path, output_dir: Path):
        """生成代码"""
        from codegen.cli import main as codegen_main
        
        print(f"生成代码: {graph_path} -> {output_dir}")
        return codegen_main([str(graph_path), "-o", str(output_dir), "--force"])
    
    @staticmethod
    def build(project: ProjectManager, build_dir: Path):
        """编译构建"""
        import subprocess
        
        print("编译项目...")
        result = subprocess.run(
            ["cmake", "-S", str(project.project_path), "-B", str(build_dir)],
            capture_output=False,
        )
        
        if result.returncode == 0:
            result = subprocess.run(
                ["cmake", "--build", str(build_dir)],
                capture_output=False,
            )
        
        return result.returncode


class SimulateStage:
    """仿真阶段：MCU仿真、性能测试"""
    
    @staticmethod
    def run(project: ProjectManager, chip: str, duration_ms: int = 1000):
        """运行仿真"""
        from tools.simulator.core import MCUSimulator
        from tools.simulator.perf import PerformanceMonitor
        
        print(f"启动仿真: {chip}")
        
        # 加载芯片
        mcu = MCUSimulator.from_chip(chip)
        print(f"  时钟: {mcu.clock.sysclk_hz / 1_000_000} MHz")
        
        # 创建监控器
        monitor = PerformanceMonitor()
        monitor.start()
        
        # 运行仿真
        cycles_per_ms = mcu.clock.sysclk_hz // 1000
        
        print(f"  仿真时长: {duration_ms} ms")
        
        for i in range(duration_ms):
            monitor.begin_frame()
            mcu.tick(cycles_per_ms)
            monitor.end_frame(cycles=cycles_per_ms, instructions=cycles_per_ms)
            
            if (i + 1) % 100 == 0:
                print(f"  进度: {i + 1}/{duration_ms}")
        
        print(monitor.get_performance_report())
        return monitor
    
    @staticmethod
    def benchmark(project: ProjectManager, chip: str):
        """性能基准测试"""
        from tools.simulator.core import MCUSimulator
        from tools.simulator.perf import PerformanceBenchmark
        
        print(f"运行基准测试: {chip}")
        
        mcu = MCUSimulator.from_chip(chip)
        benchmark = PerformanceBenchmark(mcu)
        results = benchmark.run_all()
        
        print(benchmark.format_report(results))
        return results


class DebugStage:
    """调试阶段：在线调试、数据分析"""
    
    @staticmethod
    def connect(project: ProjectManager, port: str, baud: int = 115200):
        """连接MCU"""
        from debug.collector import DebugCollector
        
        print(f"连接MCU: {port} @ {baud}")
        
        collector = DebugCollector(port=port, baud=baud)
        collector.connect()
        
        print("✓ 连接成功")
        return collector
    
    @staticmethod
    def snapshot(collector) -> dict:
        """获取快照"""
        return collector.read_snapshot()
    
    @staticmethod
    def record(project: ProjectManager, port: str, duration_sec: float, output: Path):
        """录制数据"""
        from debug.collector import DebugCollector
        from debug.recorder import DebugRecorder
        
        print(f"录制数据: {duration_sec}秒 -> {output}")
        
        collector = DebugCollector(port=port)
        collector.connect()
        
        recorder = DebugRecorder(output)
        recorder.start()
        
        import time
        start = time.time()
        
        while time.time() - start < duration_sec:
            snapshot = collector.read_snapshot()
            recorder.record(snapshot)
            time.sleep(0.1)
        
        stats = recorder.stop()
        collector.disconnect()
        
        print(f"✓ 录制完成: {stats['record_count']} 条记录")
        return stats
    
    @staticmethod
    def analyze(project: ProjectManager, log_path: Path):
        """分析数据"""
        from debug.analyzer import DebugAnalyzer
        
        print(f"分析数据: {log_path}")
        
        analyzer = DebugAnalyzer(log_path)
        analyzer.print_summary()
        
        return analyzer


class DeployStage:
    """部署阶段：打包、分发"""
    
    @staticmethod
    def package_sdk(project: ProjectManager, output: Path):
        """打包SDK"""
        import subprocess
        
        print("打包 Runtime SDK...")
        result = subprocess.run(
            [sys.executable, str(Path(__file__).parent / "package_efw.py")],
            capture_output=False,
        )
        return result.returncode
    
    @staticmethod
    def package_studio(project: ProjectManager, output: Path):
        """打包Studio"""
        import subprocess
        
        print("打包 Studio Portable...")
        result = subprocess.run(
            [sys.executable, str(Path(__file__).parent / "package_studio_portable.py")],
            capture_output=False,
        )
        return result.returncode


# ─── 全流程工作台 ────────────────────────────────────────────────────────────

class WorkflowManager:
    """工作流管理器"""
    
    def __init__(self, project_path: Optional[Path] = None):
        self.project = ProjectManager(project_path)
        self.design = DesignStage()
        self.develop = DevelopStage()
        self.simulate = SimulateStage()
        self.debug = DebugStage()
        self.deploy = DeployStage()
    
    def status(self) -> dict:
        """获取项目状态"""
        if not self.project.config:
            return {"status": "no_project"}
        
        return {
            "name": self.project.config.get("name"),
            "chip": self.project.config.get("chip"),
            "stages": self.project.config.get("stages", {}),
        }
    
    def print_status(self):
        """打印项目状态"""
        status = self.status()
        
        if status.get("status") == "no_project":
            print("未创建项目")
            return
        
        print(f"\n项目: {status['name']}")
        print(f"芯片: {status.get('chip', '未配置')}")
        print("\n阶段状态:")
        
        stage_names = {
            "design": "设计",
            "develop": "开发",
            "simulate": "仿真",
            "debug": "调试",
            "deploy": "部署",
        }
        
        for stage, name in stage_names.items():
            info = status.get("stages", {}).get(stage, {})
            state = info.get("status", "pending")
            
            if state == "completed":
                icon = "✓"
            elif state == "in_progress":
                icon = "►"
            else:
                icon = "○"
            
            print(f"  {icon} {name}: {state}")


# ─── CLI 入口 ────────────────────────────────────────────────────────────────

def cmd_workflow(argv: list[str]) -> int:
    """全流程工作流"""
    workflow = WorkflowManager()
    
    if not argv:
        workflow.print_status()
        return 0
    
    subcmd = argv[0]
    rest = argv[1:]
    
    if subcmd == "create":
        name = rest[0] if rest else "new_project"
        chip = ""
        board = ""
        
        for i, arg in enumerate(rest):
            if arg == "--chip" and i + 1 < len(rest):
                chip = rest[i + 1]
            elif arg == "--board" and i + 1 < len(rest):
                board = rest[i + 1]
        
        workflow.project.create(name, chip, board)
        print(f"✓ 项目已创建: {name}")
        return 0
    
    elif subcmd == "design":
        return workflow.design.launch(workflow.project)
    
    elif subcmd == "develop":
        graph_path = Path(rest[0]) if rest else None
        if not graph_path:
            print("错误: 请指定图文件", file=sys.stderr)
            return 1
        return workflow.develop.generate(workflow.project, graph_path, Path("application"))
    
    elif subcmd == "simulate":
        chip = workflow.project.config.get("chip", "STM32F407VGT6")
        for i, arg in enumerate(rest):
            if arg == "--chip" and i + 1 < len(rest):
                chip = rest[i + 1]
        
        workflow.simulate.run(workflow.project, chip)
        return 0
    
    elif subcmd == "debug":
        port = rest[0] if rest else "/dev/ttyUSB0"
        workflow.debug.connect(workflow.project, port)
        return 0
    
    elif subcmd == "deploy":
        workflow.deploy.package_sdk(workflow.project, Path("dist"))
        return 0
    
    else:
        print(f"未知命令: {subcmd}")
        return 1


# ─── 导出 ────────────────────────────────────────────────────────────────────

__all__ = [
    "ProjectManager",
    "WorkflowManager",
    "DesignStage",
    "DevelopStage",
    "SimulateStage",
    "DebugStage",
    "DeployStage",
    "cmd_workflow",
]
