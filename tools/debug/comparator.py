"""数据比对引擎

比较 MCU 实际数据与预期配置，检测异常和问题。
支持范围检查、精确值匹配、枚举验证等多种比对规则。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class IssueType(str, Enum):
    """问题类型枚举"""
    MISSING = "missing"              # 参数缺失
    OUT_OF_RANGE = "out_of_range"    # 超出范围
    MISMATCH = "mismatch"            # 值不匹配
    TYPE_ERROR = "type_error"        # 类型错误
    STATUS_ERROR = "status_error"    # 状态异常
    UNEXPECTED_ENUM = "unexpected_enum"  # 枚举值不合法


@dataclass
class Issue:
    """比对问题描述"""
    name: str                    # 参数名称
    type: IssueType              # 问题类型
    detail: str                  # 问题详情
    actual: Any = None           # 实际值
    expected: Any = None         # 期望值
    severity: str = "warning"    # 严重程度: info, warning, error


@dataclass
class CompareResult:
    """比对结果"""
    timestamp: str                                # 比对时间
    total_params: int = 0                         # 总参数数
    checked_params: int = 0                       # 已检查参数数
    issues: list[Issue] = field(default_factory=list)  # 问题列表
    
    @property
    def has_issues(self) -> bool:
        """是否有问题"""
        return len(self.issues) > 0
    
    @property
    def error_count(self) -> int:
        """错误数量"""
        return sum(1 for i in self.issues if i.severity == "error")
    
    @property
    def warning_count(self) -> int:
        """警告数量"""
        return sum(1 for i in self.issues if i.severity == "warning")
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "timestamp": self.timestamp,
            "total_params": self.total_params,
            "checked_params": self.checked_params,
            "issue_count": len(self.issues),
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "issues": [
                {
                    "name": i.name,
                    "type": i.type.value,
                    "detail": i.detail,
                    "actual": i.actual,
                    "expected": i.expected,
                    "severity": i.severity,
                }
                for i in self.issues
            ]
        }


@dataclass
class ParamExpectation:
    """参数预期配置"""
    name: str                          # 参数名称
    min_value: Optional[float] = None  # 最小值
    max_value: Optional[float] = None  # 最大值
    exact_value: Optional[Any] = None  # 精确值
    enum_values: Optional[list] = None # 允许的枚举值
    type_name: Optional[str] = None    # 期望类型
    unit: Optional[str] = None         # 期望单位
    required: bool = False             # 是否必需
    description: str = ""              # 描述


class DebugComparator:
    """调试数据比对器
    
    比较 MCU 实际数据与预期配置，检测异常。
    
    使用方式：
        # 加载预期配置
        comparator = DebugComparator.from_file("expected.json")
        
        # 或手动添加规则
        comparator = DebugComparator()
        comparator.add_expectation(ParamExpectation(
            name="motor_speed",
            min_value=0,
            max_value=100,
        ))
        
        # 执行比对
        result = comparator.compare(snapshot)
        
        if result.has_issues:
            for issue in result.issues:
                print(f"{issue.name}: {issue.detail}")
    """
    
    def __init__(self):
        """初始化比对器"""
        self._expectations: dict[str, ParamExpectation] = {}
    
    @classmethod
    def from_file(cls, path: str | Path) -> "DebugComparator":
        """从文件加载预期配置
        
        配置文件格式：
        {
            "version": "1.0",
            "params": {
                "param_name": {
                    "min": 0,
                    "max": 100,
                    "exact": 42,
                    "enum": [0, 1, 2],
                    "type": "f32",
                    "unit": "%",
                    "required": true,
                    "description": "电机速度"
                }
            }
        }
        
        Args:
            path: 配置文件路径
            
        Returns:
            比对器实例
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {path}")
        
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        comparator = cls()
        
        for name, rules in config.get("params", {}).items():
            expectation = ParamExpectation(
                name=name,
                min_value=rules.get("min"),
                max_value=rules.get("max"),
                exact_value=rules.get("exact"),
                enum_values=rules.get("enum"),
                type_name=rules.get("type"),
                unit=rules.get("unit"),
                required=rules.get("required", False),
                description=rules.get("description", ""),
            )
            comparator.add_expectation(expectation)
        
        return comparator
    
    def add_expectation(self, expectation: ParamExpectation) -> None:
        """添加参数预期配置
        
        Args:
            expectation: 预期配置
        """
        self._expectations[expectation.name] = expectation
    
    def remove_expectation(self, name: str) -> None:
        """移除参数预期配置
        
        Args:
            name: 参数名称
        """
        self._expectations.pop(name, None)
    
    def clear_expectations(self) -> None:
        """清除所有预期配置"""
        self._expectations.clear()
    
    def compare(self, snapshot: dict) -> CompareResult:
        """比较快照数据与预期配置
        
        Args:
            snapshot: 快照数据，格式：
                {
                    "time": "...",
                    "params": {
                        "param_name": {
                            "value": 3.14,
                            "type": "f32",
                            "unit": "%",
                            "status": "OK"
                        }
                    }
                }
        
        Returns:
            比对结果
        """
        from datetime import datetime, timezone
        
        result = CompareResult(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_params=len(snapshot.get("params", {})),
        )
        
        params = snapshot.get("params", {})
        
        # 检查必需参数是否存在
        for name, exp in self._expectations.items():
            if exp.required and name not in params:
                result.issues.append(Issue(
                    name=name,
                    type=IssueType.MISSING,
                    detail="必需参数缺失",
                    severity="error",
                ))
        
        # 检查每个参数
        for name, param_info in params.items():
            result.checked_params += 1
            
            # 如果有预期配置，进行比对
            if name in self._expectations:
                issues = self._check_param(name, param_info, self._expectations[name])
                result.issues.extend(issues)
        
        return result
    
    def _check_param(
        self,
        name: str,
        param_info: dict,
        expectation: ParamExpectation,
    ) -> list[Issue]:
        """检查单个参数"""
        issues = []
        value = param_info.get("value")
        status = param_info.get("status", "OK")
        
        # 检查状态
        if status != "OK":
            issues.append(Issue(
                name=name,
                type=IssueType.STATUS_ERROR,
                detail=f"参数状态异常: {status}",
                actual=status,
                expected="OK",
                severity="warning",
            ))
        
        # 检查类型
        if expectation.type_name:
            actual_type = param_info.get("type")
            if actual_type != expectation.type_name:
                issues.append(Issue(
                    name=name,
                    type=IssueType.TYPE_ERROR,
                    detail=f"类型不匹配: {actual_type} != {expectation.type_name}",
                    actual=actual_type,
                    expected=expectation.type_name,
                    severity="warning",
                ))
        
        # 检查单位
        if expectation.unit:
            actual_unit = param_info.get("unit", "")
            if actual_unit != expectation.unit:
                issues.append(Issue(
                    name=name,
                    type=IssueType.MISMATCH,
                    detail=f"单位不匹配: {actual_unit} != {expectation.unit}",
                    actual=actual_unit,
                    expected=expectation.unit,
                    severity="info",
                ))
        
        # 如果值为 None，跳过值检查
        if value is None:
            return issues
        
        # 尝试转换为数值进行比较
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            numeric_value = None
        
        # 检查范围
        if numeric_value is not None:
            if expectation.min_value is not None and numeric_value < expectation.min_value:
                issues.append(Issue(
                    name=name,
                    type=IssueType.OUT_OF_RANGE,
                    detail=f"值 {numeric_value} 小于最小值 {expectation.min_value}",
                    actual=numeric_value,
                    expected=f">= {expectation.min_value}",
                    severity="error",
                ))
            
            if expectation.max_value is not None and numeric_value > expectation.max_value:
                issues.append(Issue(
                    name=name,
                    type=IssueType.OUT_OF_RANGE,
                    detail=f"值 {numeric_value} 大于最大值 {expectation.max_value}",
                    actual=numeric_value,
                    expected=f"<= {expectation.max_value}",
                    severity="error",
                ))
        
        # 检查精确值
        if expectation.exact_value is not None:
            if value != expectation.exact_value:
                issues.append(Issue(
                    name=name,
                    type=IssueType.MISMATCH,
                    detail=f"值不匹配: {value} != {expectation.exact_value}",
                    actual=value,
                    expected=expectation.exact_value,
                    severity="error",
                ))
        
        # 检查枚举值
        if expectation.enum_values is not None:
            if value not in expectation.enum_values:
                issues.append(Issue(
                    name=name,
                    type=IssueType.UNEXPECTED_ENUM,
                    detail=f"值 {value} 不在允许的枚举值中: {expectation.enum_values}",
                    actual=value,
                    expected=expectation.enum_values,
                    severity="error",
                ))
        
        return issues
    
    def format_report(self, result: CompareResult, colorize: bool = True) -> str:
        """格式化比对报告
        
        Args:
            result: 比对结果
            colorize: 是否使用颜色
            
        Returns:
            格式化的报告字符串
        """
        lines = []
        
        # 标题
        lines.append("=" * 60)
        lines.append("  EFW 调试数据比对报告")
        lines.append("=" * 60)
        lines.append(f"  时间: {result.timestamp}")
        lines.append(f"  总参数: {result.total_params}")
        lines.append(f"  已检查: {result.checked_params}")
        lines.append(f"  问题数: {len(result.issues)}")
        lines.append("-" * 60)
        
        if not result.has_issues:
            lines.append("  ✓ 所有检查通过")
        else:
            # 按严重程度分组
            errors = [i for i in result.issues if i.severity == "error"]
            warnings = [i for i in result.issues if i.severity == "warning"]
            infos = [i for i in result.issues if i.severity == "info"]
            
            if errors:
                lines.append(f"\n  ✗ 错误 ({len(errors)}):")
                for issue in errors:
                    lines.append(f"    - {issue.name}: {issue.detail}")
            
            if warnings:
                lines.append(f"\n  ⚠ 警告 ({len(warnings)}):")
                for issue in warnings:
                    lines.append(f"    - {issue.name}: {issue.detail}")
            
            if infos:
                lines.append(f"\n  ℹ 信息 ({len(infos)}):")
                for issue in infos:
                    lines.append(f"    - {issue.name}: {issue.detail}")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)


# 命令行入口
if __name__ == "__main__":
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description="EFW 调试数据比对工具")
    parser.add_argument("snapshot", help="快照文件路径 (JSON)")
    parser.add_argument("--expected", required=True, help="预期配置文件路径 (JSON)")
    parser.add_argument("--pretty", action="store_true", help="美化输出")
    
    args = parser.parse_args()
    
    try:
        # 加载快照
        with open(args.snapshot, "r", encoding="utf-8") as f:
            snapshot = json.load(f)
        
        # 加载预期配置
        comparator = DebugComparator.from_file(args.expected)
        
        # 执行比对
        result = comparator.compare(snapshot)
        
        if args.pretty:
            print(comparator.format_report(result))
        else:
            print(json.dumps(result.to_dict(), ensure_ascii=False))
        
        sys.exit(1 if result.error_count > 0 else 0)
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}), file=sys.stderr)
        sys.exit(1)
