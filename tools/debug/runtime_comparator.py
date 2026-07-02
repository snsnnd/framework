"""离线/在线对比引擎

将离线 debug（静态分析）的结果与在线实际运行数据进行对比，
自动检测异常并告警。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class AnomalyType(str, Enum):
    """异常类型"""
    # 任务相关
    TASK_MISSING = "task_missing"                    # 任务未运行
    TASK_OVERRUN = "task_overrun"                    # 任务超时
    TASK_PERIOD_DEVIATION = "task_period_deviation"  # 周期偏差过大
    TASK_STATE_MISMATCH = "task_state_mismatch"      # 状态不匹配
    
    # 模块相关
    MODULE_MISSING = "module_missing"                # 模块未运行
    MODULE_STUCK = "module_stuck"                    # 模块卡住
    MODULE_ERROR = "module_error"                    # 模块错误
    MODULE_SLOW_POLL = "module_slow_poll"            # 轮询过慢
    
    # 事件相关
    TOPIC_NO_PUBLISHER = "topic_no_publisher"        # 无发布者
    TOPIC_NO_SUBSCRIBER = "topic_no_subscriber"      # 无订阅者
    TOPIC_NO_ACTIVITY = "topic_no_activity"          # 无活动
    TOPIC_HIGH_DROP_RATE = "topic_high_drop_rate"    # 高丢弃率
    
    # 数据流相关
    DATAFLOW_MISSING = "dataflow_missing"            # 数据流未激活
    DATAFLOW_STALLED = "dataflow_stalled"            # 数据流停滞
    
    # 资源相关
    CPU_OVERLOAD = "cpu_overload"                    # CPU 过载
    STACK_OVERFLOW_RISK = "stack_overflow_risk"      # 栈溢出风险


class AnomalySeverity(str, Enum):
    """异常严重程度"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Anomaly:
    """异常描述"""
    type: AnomalyType
    severity: AnomalySeverity
    name: str                           # 相关组件名称
    detail: str                         # 详细描述
    expected: Any = None                # 预期值
    actual: Any = None                  # 实际值
    suggestion: str = ""                # 修复建议
    timestamp: str = ""                 # 检测时间
    
    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "severity": self.severity.value,
            "name": self.name,
            "detail": self.detail,
            "expected": self.expected,
            "actual": self.actual,
            "suggestion": self.suggestion,
            "timestamp": self.timestamp,
        }


@dataclass
class OfflineSpec:
    """离线 debug 规格（从 graph JSON 静态分析得到）"""
    
    # 任务定义
    tasks: dict[str, dict] = field(default_factory=dict)
    # {name: {"period_ms": 1, "type": "periodic", "call": "func_name"}}
    
    # 模块定义
    modules: dict[str, dict] = field(default_factory=dict)
    # {name: {"init": True, "start": True, "poll": True}}
    
    # 话题定义
    topics: dict[str, dict] = field(default_factory=dict)
    # {name: {"topic_id": 1, "publishers": [...], "subscribers": [...]}}
    
    # 数据流定义
    dataflows: list[dict] = field(default_factory=list)
    # [{"source": "sensor", "sink": "pid", "period_ms": 1}]
    
    # 资源限制
    cpu_limit_percent: int = 80
    stack_limit_bytes: int = 1024
    
    @classmethod
    def from_graph_json(cls, path: str | Path) -> "OfflineSpec":
        """从 graph JSON 加载离线规格"""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Graph file not found: {path}")
        
        with open(path, "r", encoding="utf-8") as f:
            graph = json.load(f)
        
        spec = cls()
        
        # 解析任务
        for task in graph.get("tasks", []):
            name = task.get("id", "unnamed")
            spec.tasks[name] = {
                "period_ms": task.get("period_ms", graph.get("project", {}).get("tick_ms", 1)),
                "type": task.get("type", "periodic"),
                "call": task.get("call", ""),
            }
        
        # 解析模块
        for node in graph.get("nodes", []):
            ntype = node.get("type", "")
            if ntype.startswith("module.") or ntype == "project.module":
                name = node.get("id", "unnamed")
                spec.modules[name] = {
                    "init": True,
                    "start": True,
                    "poll": True,
                }
        
        # 解析话题
        for node in graph.get("nodes", []):
            if node.get("type") == "event.topic":
                name = node.get("id", "unnamed")
                spec.topics[name] = {
                    "topic_id": node.get("topic_id", 0),
                    "publishers": [],
                    "subscribers": [],
                }
        
        # 解析发布者/订阅者
        for node in graph.get("nodes", []):
            ntype = node.get("type", "")
            topic_ref = node.get("topic")
            
            if ntype == "event.publisher" and topic_ref:
                if topic_ref in spec.topics:
                    spec.topics[topic_ref]["publishers"].append(node.get("id"))
            
            if ntype == "event.subscriber" and topic_ref:
                if topic_ref in spec.topics:
                    spec.topics[topic_ref]["subscribers"].append(node.get("id"))
        
        # 解析数据流
        for edge in graph.get("edges", []):
            if edge.get("kind") == "data_flow":
                spec.dataflows.append({
                    "source": edge.get("source"),
                    "sink": edge.get("target"),
                })
        
        return spec


class RuntimeComparator:
    """离线/在线对比器
    
    使用方式：
        # 加载离线规格
        spec = OfflineSpec.from_graph_json("graph.json")
        
        # 创建对比器
        comparator = RuntimeComparator(spec)
        
        # 在线对比
        anomalies = comparator.compare_online_snapshot(online_snapshot)
        
        # 打印告警
        for a in anomalies:
            print(f"[{a.severity}] {a.name}: {a.detail}")
    """
    
    def __init__(self, spec: OfflineSpec):
        self.spec = spec
        self._prev_snapshot: Optional[dict] = None
        self._anomaly_history: list[Anomaly] = []
    
    def compare_online_snapshot(self, snapshot: dict) -> list[Anomaly]:
        """对比在线快照与离线规格
        
        Args:
            snapshot: 在线运行时快照
            
        Returns:
            检测到的异常列表
        """
        anomalies = []
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # 检查任务
        anomalies.extend(self._check_tasks(snapshot, timestamp))
        
        # 检查模块
        anomalies.extend(self._check_modules(snapshot, timestamp))
        
        # 检查话题
        anomalies.extend(self._check_topics(snapshot, timestamp))
        
        # 检查数据流
        anomalies.extend(self._check_dataflows(snapshot, timestamp))
        
        # 检查资源
        anomalies.extend(self._check_resources(snapshot, timestamp))
        
        # 保存历史
        self._prev_snapshot = snapshot
        self._anomaly_history.extend(anomalies)
        
        return anomalies
    
    def _check_tasks(self, snapshot: dict, timestamp: str) -> list[Anomaly]:
        """检查任务"""
        anomalies = []
        online_tasks = snapshot.get("tasks", {})
        
        # 检查离线定义的任务是否都在线运行
        for task_name, task_spec in self.spec.tasks.items():
            if task_name not in online_tasks:
                anomalies.append(Anomaly(
                    type=AnomalyType.TASK_MISSING,
                    severity=AnomalySeverity.ERROR,
                    name=task_name,
                    detail=f"任务 {task_name} 在离线定义中存在，但在线未检测到运行",
                    expected="running",
                    actual="missing",
                    suggestion="检查任务是否正确注册到调度器",
                    timestamp=timestamp,
                ))
                continue
            
            online_task = online_tasks[task_name]
            
            # 检查超时
            expected_period = task_spec.get("period_ms", 1) * 1000  # 转换为微秒
            actual_execution = online_task.get("execution_time_us", 0)
            
            if actual_execution > expected_period:
                anomalies.append(Anomaly(
                    type=AnomalyType.TASK_OVERRUN,
                    severity=AnomalySeverity.WARNING,
                    name=task_name,
                    detail=f"任务 {task_name} 执行时间 ({actual_execution}us) 超过预期周期 ({expected_period}us)",
                    expected=f"<= {expected_period} us",
                    actual=f"{actual_execution} us",
                    suggestion="优化任务执行时间或增加周期",
                    timestamp=timestamp,
                ))
            
            # 检查周期偏差
            actual_period = online_task.get("actual_period_us", 0)
            if expected_period > 0 and actual_period > 0:
                deviation = abs(actual_period - expected_period) / expected_period * 100
                if deviation > 20:  # 偏差超过 20%
                    anomalies.append(Anomaly(
                        type=AnomalyType.TASK_PERIOD_DEVIATION,
                        severity=AnomalySeverity.WARNING,
                        name=task_name,
                        detail=f"任务 {task_name} 实际周期偏差 {deviation:.1f}%",
                        expected=f"{expected_period} us",
                        actual=f"{actual_period} us",
                        suggestion="检查调度器负载或中断优先级",
                        timestamp=timestamp,
                    ))
            
            # 检查超时次数
            overrun_count = online_task.get("overrun_count", 0)
            if overrun_count > 0:
                anomalies.append(Anomaly(
                    type=AnomalyType.TASK_OVERRUN,
                    severity=AnomalySeverity.WARNING,
                    name=task_name,
                    detail=f"任务 {task_name} 已超时 {overrun_count} 次",
                    expected=0,
                    actual=overrun_count,
                    suggestion="分析超时原因并优化",
                    timestamp=timestamp,
                ))
        
        return anomalies
    
    def _check_modules(self, snapshot: dict, timestamp: str) -> list[Anomaly]:
        """检查模块"""
        anomalies = []
        online_modules = snapshot.get("modules", {})
        
        for module_name, module_spec in self.spec.modules.items():
            if module_name not in online_modules:
                anomalies.append(Anomaly(
                    type=AnomalyType.MODULE_MISSING,
                    severity=AnomalySeverity.ERROR,
                    name=module_name,
                    detail=f"模块 {module_name} 在离线定义中存在，但在线未检测到",
                    expected="registered",
                    actual="missing",
                    suggestion="检查模块是否正确注册",
                    timestamp=timestamp,
                ))
                continue
            
            online_module = online_modules[module_name]
            state = online_module.get("state", "unknown")
            
            # 检查错误状态
            if state == "error":
                anomalies.append(Anomaly(
                    type=AnomalyType.MODULE_ERROR,
                    severity=AnomalySeverity.ERROR,
                    name=module_name,
                    detail=f"模块 {module_name} 处于错误状态",
                    expected="running",
                    actual="error",
                    suggestion="检查模块日志查找错误原因",
                    timestamp=timestamp,
                ))
            
            # 检查是否卡住（长时间无活动）
            last_activity = online_module.get("last_activity_time", 0)
            uptime = snapshot.get("uptime_ms", 0) * 1000
            if uptime > 0 and last_activity > 0:
                inactive_time = uptime - last_activity
                if inactive_time > 1000000:  # 超过 1 秒无活动
                    anomalies.append(Anomaly(
                        type=AnomalyType.MODULE_STUCK,
                        severity=AnomalySeverity.WARNING,
                        name=module_name,
                        detail=f"模块 {module_name} 已 {inactive_time/1000:.1f}ms 无活动",
                        expected="active",
                        actual=f"inactive for {inactive_time/1000:.1f}ms",
                        suggestion="检查模块是否被阻塞或死锁",
                        timestamp=timestamp,
                    ))
            
            # 检查轮询时间
            avg_poll = online_module.get("avg_poll_time_us", 0)
            max_poll = online_module.get("max_poll_time_us", 0)
            if max_poll > 1000:  # 超过 1ms
                anomalies.append(Anomaly(
                    type=AnomalyType.MODULE_SLOW_POLL,
                    severity=AnomalySeverity.WARNING,
                    name=module_name,
                    detail=f"模块 {module_name} 最大轮询时间 {max_poll}us",
                    expected="< 1000 us",
                    actual=f"{max_poll} us",
                    suggestion="优化模块轮询逻辑",
                    timestamp=timestamp,
                ))
        
        return anomalies
    
    def _check_topics(self, snapshot: dict, timestamp: str) -> list[Anomaly]:
        """检查话题"""
        anomalies = []
        online_topics = snapshot.get("topics", {})
        
        for topic_name, topic_spec in self.spec.topics.items():
            if topic_name not in online_topics:
                # 检查是否有发布者/订阅者
                publishers = topic_spec.get("publishers", [])
                subscribers = topic_spec.get("subscribers", [])
                
                if publishers and not subscribers:
                    anomalies.append(Anomaly(
                        type=AnomalyType.TOPIC_NO_SUBSCRIBER,
                        severity=AnomalySeverity.WARNING,
                        name=topic_name,
                        detail=f"话题 {topic_name} 有发布者但无订阅者",
                        expected="has subscribers",
                        actual="no subscribers",
                        suggestion="添加订阅者或移除无用的话题",
                        timestamp=timestamp,
                    ))
                elif subscribers and not publishers:
                    anomalies.append(Anomaly(
                        type=AnomalyType.TOPIC_NO_PUBLISHER,
                        severity=AnomalySeverity.WARNING,
                        name=topic_name,
                        detail=f"话题 {topic_name} 有订阅者但无发布者",
                        expected="has publishers",
                        actual="no publishers",
                        suggestion="添加发布者或移除无用的话题",
                        timestamp=timestamp,
                    ))
                continue
            
            online_topic = online_topics[topic_name]
            
            # 检查是否有活动
            publish_count = online_topic.get("publish_count", 0)
            receive_count = online_topic.get("receive_count", 0)
            
            if publish_count == 0 and receive_count == 0:
                anomalies.append(Anomaly(
                    type=AnomalyType.TOPIC_NO_ACTIVITY,
                    severity=AnomalySeverity.INFO,
                    name=topic_name,
                    detail=f"话题 {topic_name} 无发布/接收活动",
                    expected="active",
                    actual="inactive",
                    suggestion="检查发布者是否正常工作",
                    timestamp=timestamp,
                ))
            
            # 检查丢弃率
            drop_count = online_topic.get("drop_count", 0)
            if receive_count > 0 and drop_count > 0:
                drop_rate = drop_count / (receive_count + drop_count) * 100
                if drop_rate > 10:  # 丢弃率超过 10%
                    anomalies.append(Anomaly(
                        type=AnomalyType.TOPIC_HIGH_DROP_RATE,
                        severity=AnomalySeverity.WARNING,
                        name=topic_name,
                        detail=f"话题 {topic_name} 丢弃率 {drop_rate:.1f}%",
                        expected="< 10%",
                        actual=f"{drop_rate:.1f}%",
                        suggestion="增加缓冲区或优化处理速度",
                        timestamp=timestamp,
                    ))
        
        return anomalies
    
    def _check_dataflows(self, snapshot: dict, timestamp: str) -> list[Anomaly]:
        """检查数据流"""
        anomalies = []
        online_dataflows = snapshot.get("dataflows", {})
        
        for flow_spec in self.spec.dataflows:
            source = flow_spec.get("source")
            sink = flow_spec.get("sink")
            flow_key = f"{source}->{sink}"
            
            if flow_key not in online_dataflows:
                anomalies.append(Anomaly(
                    type=AnomalyType.DATAFLOW_MISSING,
                    severity=AnomalySeverity.WARNING,
                    name=flow_key,
                    detail=f"数据流 {flow_key} 在离线定义中存在，但在线未激活",
                    expected="active",
                    actual="inactive",
                    suggestion="检查源和目标模块是否正常工作",
                    timestamp=timestamp,
                ))
                continue
            
            online_flow = online_dataflows[flow_key]
            
            # 检查是否停滞
            transfer_count = online_flow.get("transfer_count", 0)
            last_transfer = online_flow.get("last_transfer_time", 0)
            uptime = snapshot.get("uptime_ms", 0) * 1000
            
            if transfer_count > 0 and uptime > 0 and last_transfer > 0:
                stall_time = uptime - last_transfer
                if stall_time > 1000000:  # 超过 1 秒无传输
                    anomalies.append(Anomaly(
                        type=AnomalyType.DATAFLOW_STALLED,
                        severity=AnomalySeverity.WARNING,
                        name=flow_key,
                        detail=f"数据流 {flow_key} 已停滞 {stall_time/1000:.1f}ms",
                        expected="flowing",
                        actual=f"stalled for {stall_time/1000:.1f}ms",
                        suggestion="检查数据源是否正常产生数据",
                        timestamp=timestamp,
                    ))
        
        return anomalies
    
    def _check_resources(self, snapshot: dict, timestamp: str) -> list[Anomaly]:
        """检查资源"""
        anomalies = []
        resources = snapshot.get("resources", {})
        
        # 检查 CPU 使用率
        cpu_usage = resources.get("cpu_usage_percent", 0)
        if cpu_usage > self.spec.cpu_limit_percent:
            anomalies.append(Anomaly(
                type=AnomalyType.CPU_OVERLOAD,
                severity=AnomalySeverity.ERROR,
                name="cpu",
                detail=f"CPU 使用率 {cpu_usage}% 超过限制 {self.spec.cpu_limit_percent}%",
                expected=f"<= {self.spec.cpu_limit_percent}%",
                actual=f"{cpu_usage}%",
                suggestion="优化算法或降低任务频率",
                timestamp=timestamp,
            ))
        
        # 检查栈使用
        stack_used = resources.get("stack_used_bytes", 0)
        if stack_used > self.spec.stack_limit_bytes * 0.9:  # 超过 90%
            anomalies.append(Anomaly(
                type=AnomalyType.STACK_OVERFLOW_RISK,
                severity=AnomalySeverity.ERROR,
                name="stack",
                detail=f"栈使用 {stack_used} 字节接近限制 {self.spec.stack_limit_bytes} 字节",
                expected=f"< {self.spec.stack_limit_bytes * 0.9} bytes",
                actual=f"{stack_used} bytes",
                suggestion="减少栈使用或增加栈大小",
                timestamp=timestamp,
            ))
        
        return anomalies
    
    def get_summary(self) -> dict:
        """获取异常汇总"""
        summary = {
            "total": len(self._anomaly_history),
            "by_severity": {},
            "by_type": {},
        }
        
        for a in self._anomaly_history:
            summary["by_severity"][a.severity.value] = summary["by_severity"].get(a.severity.value, 0) + 1
            summary["by_type"][a.type.value] = summary["by_type"].get(a.type.value, 0) + 1
        
        return summary
    
    def format_report(self, anomalies: list[Anomaly]) -> str:
        """格式化异常报告"""
        if not anomalies:
            return "✓ 未检测到异常"
        
        lines = [
            "=" * 70,
            "  离线/在线对比告警",
            "=" * 70,
            f"  检测时间: {datetime.now(timezone.utc).isoformat()[:19]}",
            f"  异常数量: {len(anomalies)}",
            "-" * 70,
        ]
        
        # 按严重程度分组
        critical = [a for a in anomalies if a.severity == AnomalySeverity.CRITICAL]
        error = [a for a in anomalies if a.severity == AnomalySeverity.ERROR]
        warning = [a for a in anomalies if a.severity == AnomalySeverity.WARNING]
        info = [a for a in anomalies if a.severity == AnomalySeverity.INFO]
        
        if critical:
            lines.append("\n  [CRITICAL] 严重问题:")
            for a in critical:
                lines.append(f"    ✗ {a.name}: {a.detail}")
                if a.suggestion:
                    lines.append(f"      建议: {a.suggestion}")
        
        if error:
            lines.append("\n  [ERROR] 错误:")
            for a in error:
                lines.append(f"    ✗ {a.name}: {a.detail}")
                if a.suggestion:
                    lines.append(f"      建议: {a.suggestion}")
        
        if warning:
            lines.append("\n  [WARNING] 警告:")
            for a in warning:
                lines.append(f"    ⚠ {a.name}: {a.detail}")
                if a.suggestion:
                    lines.append(f"      建议: {a.suggestion}")
        
        if info:
            lines.append("\n  [INFO] 信息:")
            for a in info:
                lines.append(f"    ℹ {a.name}: {a.detail}")
        
        lines.append("=" * 70)
        
        return "\n".join(lines)
