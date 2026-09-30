"""历史数据分析器

分析 JSONL 格式的调试记录文件，提供统计、查询、回放等功能。
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class DebugAnalyzer:
    """调试数据分析器
    
    分析 JSONL 格式的调试记录文件。
    
    使用方式：
        analyzer = DebugAnalyzer("debug_session.jsonl")
        
        # 获取摘要
        summary = analyzer.get_summary()
        
        # 查询特定时间范围
        data = analyzer.get_time_range("2026-07-01T12:00:00", "2026-07-01T13:00:00")
        
        # 查找所有问题
        issues = analyzer.find_all_issues()
        
        # 参数统计
        stats = analyzer.get_param_stats("motor_speed")
    """
    
    def __init__(self, log_path: str | Path):
        """初始化分析器
        
        Args:
            log_path: 日志文件路径
        """
        self.log_path = Path(log_path)
        
        if not self.log_path.exists():
            raise FileNotFoundError(f"日志文件不存在: {self.log_path}")
        
        # 缓存
        self._records: Optional[list[dict]] = None
        self._snapshots: Optional[list[dict]] = None
        self._issues: Optional[list[dict]] = None
    
    def _load_records(self) -> list[dict]:
        """加载所有记录"""
        if self._records is not None:
            return self._records
        
        records = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    record["_line"] = line_num
                    records.append(record)
                except json.JSONDecodeError:
                    pass  # 跳过无效行
        
        self._records = records
        return records
    
    def _get_snapshots(self) -> list[dict]:
        """获取所有快照记录"""
        if self._snapshots is not None:
            return self._snapshots
        
        records = self._load_records()
        self._snapshots = [r for r in records if r.get("type") == "snapshot"]
        return self._snapshots
    
    def _get_issues(self) -> list[dict]:
        """获取所有问题记录"""
        if self._issues is not None:
            return self._issues
        
        records = self._load_records()
        self._issues = [r for r in records if r.get("type") == "issue"]
        return self._issues
    
    def get_summary(self) -> dict:
        """获取记录摘要
        
        Returns:
            摘要信息
        """
        records = self._load_records()
        snapshots = self._get_snapshots()
        issues = self._get_issues()
        
        # 时间范围
        first_time = None
        last_time = None
        
        for r in records:
            t = r.get("record_time") or r.get("time")
            if t:
                if not first_time:
                    first_time = t
                last_time = t
        
        # 收集所有参数名
        param_names = set()
        for s in snapshots:
            param_names.update(s.get("params", {}).keys())
        
        # 问题统计
        issue_types = defaultdict(int)
        for issue in issues:
            issue_types[issue.get("type", "unknown")] += 1
        
        return {
            "file": str(self.log_path),
            "file_size_mb": round(self.log_path.stat().st_size / 1024 / 1024, 2),
            "total_records": len(records),
            "snapshot_count": len(snapshots),
            "issue_count": len(issues),
            "first_time": first_time,
            "last_time": last_time,
            "param_count": len(param_names),
            "param_names": sorted(param_names),
            "issue_types": dict(issue_types),
        }
    
    def get_time_range(
        self,
        start: str,
        end: str,
        include_issues: bool = True,
    ) -> list[dict]:
        """获取指定时间范围内的记录
        
        Args:
            start: 开始时间（ISO 格式）
            end: 结束时间（ISO 格式）
            include_issues: 是否包含问题记录
            
        Returns:
            记录列表
        """
        snapshots = self._get_snapshots()
        issues = self._get_issues() if include_issues else []
        
        # 解析时间范围
        start_dt = self._parse_time(start)
        end_dt = self._parse_time(end)
        
        result = []
        
        for record in snapshots + issues:
            record_time = self._parse_time(record.get("record_time") or record.get("time"))
            if record_time and start_dt <= record_time <= end_dt:
                result.append(record)
        
        # 按时间排序
        result.sort(key=lambda r: r.get("record_time") or r.get("time") or "")
        
        return result
    
    def get_last_n(self, n: int = 10) -> list[dict]:
        """获取最后 N 条快照
        
        Args:
            n: 数量
            
        Returns:
            快照列表
        """
        snapshots = self._get_snapshots()
        return snapshots[-n:]
    
    def find_all_issues(self) -> list[dict]:
        """查找所有问题记录
        
        Returns:
            问题列表
        """
        return self._get_issues()
    
    def find_issues_by_param(self, param_name: str) -> list[dict]:
        """查找指定参数的所有问题
        
        Args:
            param_name: 参数名称
            
        Returns:
            问题列表
        """
        issues = self._get_issues()
        return [i for i in issues if i.get("name") == param_name]
    
    def get_param_history(
        self,
        param_name: str,
        max_points: int = 1000,
    ) -> list[dict]:
        """获取参数的历史值
        
        Args:
            param_name: 参数名称
            max_points: 最大数据点数
            
        Returns:
            历史数据列表，每个元素包含 time 和 value
        """
        snapshots = self._get_snapshots()
        
        # 采样
        if len(snapshots) > max_points:
            step = len(snapshots) // max_points
            snapshots = snapshots[::step]
        
        history = []
        for s in snapshots:
            params = s.get("params", {})
            if param_name in params:
                history.append({
                    "time": s.get("record_time") or s.get("time"),
                    "value": params[param_name].get("value"),
                    "status": params[param_name].get("status"),
                })
        
        return history
    
    def get_param_stats(self, param_name: str) -> dict:
        """获取参数统计信息
        
        Args:
            param_name: 参数名称
            
        Returns:
            统计信息（min, max, avg, count 等）
        """
        history = self.get_param_history(param_name)
        
        if not history:
            return {
                "name": param_name,
                "count": 0,
                "error": "无数据",
            }
        
        values = []
        for h in history:
            try:
                v = float(h["value"])
                values.append(v)
            except (TypeError, ValueError):
                pass
        
        if not values:
            return {
                "name": param_name,
                "count": len(history),
                "error": "无数值数据",
            }
        
        return {
            "name": param_name,
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
            "first": values[0],
            "last": values[-1],
            "first_time": history[0]["time"],
            "last_time": history[-1]["time"],
        }
    
    def get_all_param_stats(self) -> dict[str, dict]:
        """获取所有参数的统计信息
        
        Returns:
            参数名 -> 统计信息的映射
        """
        summary = self.get_summary()
        stats = {}
        
        for name in summary.get("param_names", []):
            stats[name] = self.get_param_stats(name)
        
        return stats
    
    def find_anomalies(
        self,
        param_name: str,
        threshold_factor: float = 3.0,
    ) -> list[dict]:
        """查找参数异常值
        
        使用简单的 Z-score 方法检测异常。
        
        Args:
            param_name: 参数名称
            threshold_factor: 异常阈值因子（默认 3 倍标准差）
            
        Returns:
            异常数据点列表
        """
        history = self.get_param_history(param_name)
        
        values = []
        for h in history:
            try:
                values.append(float(h["value"]))
            except (TypeError, ValueError):
                pass
        
        if len(values) < 10:
            return []  # 数据太少，无法检测异常
        
        # 计算均值和标准差
        avg = sum(values) / len(values)
        variance = sum((v - avg) ** 2 for v in values) / len(values)
        std = variance ** 0.5
        
        if std == 0:
            return []  # 标准差为 0，无异常
        
        # 检测异常
        anomalies = []
        for i, (h, v) in enumerate(zip(history, values)):
            z_score = abs(v - avg) / std
            if z_score > threshold_factor:
                anomalies.append({
                    "time": h["time"],
                    "value": v,
                    "z_score": round(z_score, 2),
                    "deviation": round(v - avg, 4),
                })
        
        return anomalies
    
    def export_csv(
        self,
        output_path: str | Path,
        params: list[str] = None,
    ) -> None:
        """导出为 CSV 格式
        
        Args:
            output_path: 输出文件路径
            params: 要导出的参数列表，None 表示全部
        """
        snapshots = self._get_snapshots()
        
        if not snapshots:
            return
        
        # 收集参数名
        if params is None:
            all_params = set()
            for s in snapshots:
                all_params.update(s.get("params", {}).keys())
            params = sorted(all_params)
        
        output_path = Path(output_path)
        
        with open(output_path, "w", encoding="utf-8") as f:
            # 写入表头
            f.write("time,seq," + ",".join(params) + "\n")
            
            # 写入数据
            for s in snapshots:
                time_str = s.get("record_time", s.get("time", ""))
                seq = s.get("seq", "")
                row = [time_str, str(seq)]
                
                for p in params:
                    value = s.get("params", {}).get(p, {}).get("value", "")
                    row.append(str(value))
                
                f.write(",".join(row) + "\n")
    
    def _parse_time(self, time_str: str) -> Optional[datetime]:
        """解析时间字符串"""
        if not time_str:
            return None
        
        try:
            # 处理 ISO 格式
            time_str = time_str.replace("Z", "+00:00")
            return datetime.fromisoformat(time_str)
        except (ValueError, TypeError):
            return None
    
    def print_summary(self) -> None:
        """打印摘要信息"""
        summary = self.get_summary()
        
        print("=" * 60)
        print("  EFW 调试记录摘要")
        print("=" * 60)
        print(f"  文件: {summary['file']}")
        print(f"  大小: {summary['file_size_mb']} MB")
        print(f"  总记录数: {summary['total_records']}")
        print(f"  快照数: {summary['snapshot_count']}")
        print(f"  问题数: {summary['issue_count']}")
        print(f"  参数数: {summary['param_count']}")
        print(f"  时间范围: {summary['first_time']} ~ {summary['last_time']}")
        
        if summary.get("issue_types"):
            print("\n  问题类型统计:")
            for itype, count in summary["issue_types"].items():
                print(f"    - {itype}: {count}")
        
        print("=" * 60)


# 命令行入口
if __name__ == "__main__":
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description="EFW 调试记录分析工具")
    parser.add_argument("log_file", help="日志文件路径")
    parser.add_argument("--action", choices=["summary", "issues", "stats", "export", "anomalies"],
                       default="summary", help="操作类型")
    parser.add_argument("--param", help="参数名称")
    parser.add_argument("--output", "-o", help="输出文件路径")
    parser.add_argument("--start", help="开始时间")
    parser.add_argument("--end", help="结束时间")
    parser.add_argument("--limit", type=int, default=100, help="限制输出数量")
    
    args = parser.parse_args()
    
    try:
        analyzer = DebugAnalyzer(args.log_file)
        
        if args.action == "summary":
            analyzer.print_summary()
        
        elif args.action == "issues":
            issues = analyzer.find_all_issues()
            if args.param:
                issues = [i for i in issues if i.get("name") == args.param]
            
            for issue in issues[:args.limit]:
                print(json.dumps(issue, ensure_ascii=False))
        
        elif args.action == "stats":
            if args.param:
                stats = analyzer.get_param_stats(args.param)
            else:
                stats = analyzer.get_all_param_stats()
            
            print(json.dumps(stats, indent=2, ensure_ascii=False))
        
        elif args.action == "export":
            if not args.output:
                print("导出操作需要 --output 参数", file=sys.stderr)
                sys.exit(1)
            
            analyzer.export_csv(args.output, params=[args.param] if args.param else None)
            print(f"已导出到: {args.output}")
        
        elif args.action == "anomalies":
            if not args.param:
                print("异常检测需要 --param 参数", file=sys.stderr)
                sys.exit(1)
            
            anomalies = analyzer.find_anomalies(args.param)
            for a in anomalies[:args.limit]:
                print(json.dumps(a, ensure_ascii=False))
    
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
