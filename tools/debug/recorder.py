"""数据记录器

将 MCU 调试数据记录到 JSONL 文件，支持流式写入、自动轮转、压缩存储。
"""

from __future__ import annotations

import gzip
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class DebugRecorder:
    """调试数据记录器
    
    将 MCU 快照数据记录到 JSONL 文件。
    
    使用方式：
        recorder = DebugRecorder("output/debug_session.jsonl")
        recorder.start()
        
        # 记录数据
        recorder.record(snapshot)
        
        # 停止记录
        recorder.stop()
    """
    
    def __init__(
        self,
        output_path: str | Path,
        max_size_mb: float = 100.0,
        rotate_count: int = 5,
        compress_rotated: bool = True,
        flush_interval: int = 10,
    ):
        """初始化记录器
        
        Args:
            output_path: 输出文件路径
            max_size_mb: 单个文件最大大小（MB），超过后自动轮转
            rotate_count: 保留的轮转文件数量
            compress_rotated: 是否压缩轮转的旧文件
            flush_interval: 每 N 条记录刷新一次磁盘
        """
        self.output_path = Path(output_path)
        self.max_size_bytes = int(max_size_mb * 1024 * 1024)
        self.rotate_count = rotate_count
        self.compress_rotated = compress_rotated
        self.flush_interval = flush_interval
        
        self._file = None
        self._record_count = 0
        self._start_time = None
        self._session_id = None
    
    def start(self) -> None:
        """开始记录"""
        # 创建输出目录
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 生成会话 ID
        self._session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._start_time = time.time()
        self._record_count = 0
        
        # 打开文件
        self._file = open(self.output_path, "a", encoding="utf-8")
        
        # 写入会话头
        header = {
            "type": "session_start",
            "session_id": self._session_id,
            "time": datetime.now(timezone.utc).isoformat(),
            "output_path": str(self.output_path),
        }
        self._write_line(header)
    
    def stop(self) -> dict:
        """停止记录
        
        Returns:
            记录统计信息
        """
        if not self._file:
            return {}
        
        # 写入会话结束标记
        elapsed = time.time() - self._start_time if self._start_time else 0
        footer = {
            "type": "session_end",
            "session_id": self._session_id,
            "time": datetime.now(timezone.utc).isoformat(),
            "record_count": self._record_count,
            "elapsed_seconds": round(elapsed, 2),
        }
        self._write_line(footer)
        
        # 关闭文件
        self._file.close()
        self._file = None
        
        return {
            "session_id": self._session_id,
            "record_count": self._record_count,
            "elapsed_seconds": round(elapsed, 2),
            "output_path": str(self.output_path),
        }
    
    def record(self, snapshot: dict) -> None:
        """记录一条快照
        
        Args:
            snapshot: 快照数据
        """
        if not self._file:
            raise RuntimeError("记录器未启动")
        
        # 添加序列号和时间戳
        record = {
            "type": "snapshot",
            "seq": self._record_count + 1,
            "record_time": datetime.now(timezone.utc).isoformat(),
            **snapshot,
        }
        
        self._write_line(record)
        self._record_count += 1
        
        # 检查是否需要轮转
        if self._should_rotate():
            self._rotate()
    
    def record_issue(self, issue: dict) -> None:
        """记录一条问题
        
        Args:
            issue: 问题数据
        """
        if not self._file:
            raise RuntimeError("记录器未启动")
        
        record = {
            "type": "issue",
            "seq": self._record_count + 1,
            "record_time": datetime.now(timezone.utc).isoformat(),
            **issue,
        }
        
        self._write_line(record)
        self._record_count += 1
    
    def record_event(self, event_type: str, data: dict = None) -> None:
        """记录一条事件
        
        Args:
            event_type: 事件类型
            data: 事件数据
        """
        if not self._file:
            raise RuntimeError("记录器未启动")
        
        record = {
            "type": "event",
            "event_type": event_type,
            "seq": self._record_count + 1,
            "record_time": datetime.now(timezone.utc).isoformat(),
            "data": data or {},
        }
        
        self._write_line(record)
        self._record_count += 1
    
    def _write_line(self, data: dict) -> None:
        """写入一行 JSON"""
        line = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        self._file.write(line + "\n")
        
        # 定期刷新
        if self._record_count % self.flush_interval == 0:
            self._file.flush()
    
    def _should_rotate(self) -> bool:
        """检查是否需要轮转"""
        if not self._file:
            return False
        
        try:
            return self._file.tell() >= self.max_size_bytes
        except (OSError, ValueError):
            return False
    
    def _rotate(self) -> None:
        """轮转日志文件"""
        if not self._file:
            return
        
        # 关闭当前文件
        self._file.close()
        self._file = None
        
        # 删除最旧的轮转文件
        for i in range(self.rotate_count, 0, -1):
            old_path = self._get_rotated_path(i)
            if old_path.exists():
                if i == self.rotate_count:
                    old_path.unlink()
                else:
                    new_path = self._get_rotated_path(i + 1)
                    old_path.rename(new_path)
        
        # 重命名当前文件
        rotated_path = self._get_rotated_path(1)
        self.output_path.rename(rotated_path)
        
        # 压缩旧文件
        if self.compress_rotated:
            self._compress_file(rotated_path)
        
        # 重新打开新文件
        self._file = open(self.output_path, "a", encoding="utf-8")
        
        # 写入轮转标记
        marker = {
            "type": "rotation",
            "time": datetime.now(timezone.utc).isoformat(),
            "rotated_to": str(rotated_path),
        }
        self._write_line(marker)
    
    def _get_rotated_path(self, index: int) -> Path:
        """获取轮转文件路径"""
        return self.output_path.with_suffix(f".{index}{self.output_path.suffix}")
    
    def _compress_file(self, path: Path) -> None:
        """压缩文件"""
        try:
            compressed_path = path.with_suffix(path.suffix + ".gz")
            with open(path, "rb") as f_in:
                with gzip.open(compressed_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            path.unlink()
        except Exception:
            pass  # 压缩失败不影响主流程
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False


class RecordingSession:
    """记录会话上下文管理器
    
    自动管理记录器的启动和停止，并可选择性地集成比对器。
    
    使用方式：
        with RecordingSession("output/debug.jsonl", comparator=my_comparator) as session:
            while running:
                snapshot = collector.read_snapshot()
                session.process(snapshot)
    """
    
    def __init__(
        self,
        output_path: str | Path,
        comparator=None,
        auto_compare: bool = True,
        **recorder_kwargs,
    ):
        """初始化会话
        
        Args:
            output_path: 输出文件路径
            comparator: 比对器实例（可选）
            auto_compare: 是否自动比对
            **recorder_kwargs: 传递给 DebugRecorder 的参数
        """
        self.recorder = DebugRecorder(output_path, **recorder_kwargs)
        self.comparator = comparator
        self.auto_compare = auto_compare
        
        self._total_snapshots = 0
        self._total_issues = 0
    
    def start(self) -> None:
        """启动会话"""
        self.recorder.start()
        self._total_snapshots = 0
        self._total_issues = 0
    
    def stop(self) -> dict:
        """停止会话"""
        stats = self.recorder.stop()
        stats["total_snapshots"] = self._total_snapshots
        stats["total_issues"] = self._total_issues
        return stats
    
    def process(self, snapshot: dict) -> list:
        """处理一条快照
        
        记录快照，如果启用了自动比对则执行比对并记录问题。
        
        Args:
            snapshot: 快照数据
            
        Returns:
            发现的问题列表
        """
        # 记录快照
        self.recorder.record(snapshot)
        self._total_snapshots += 1
        
        issues = []
        
        # 自动比对
        if self.auto_compare and self.comparator:
            result = self.comparator.compare(snapshot)
            
            if result.has_issues:
                for issue in result.issues:
                    issue_dict = {
                        "name": issue.name,
                        "type": issue.type.value,
                        "detail": issue.detail,
                        "actual": issue.actual,
                        "expected": issue.expected,
                        "severity": issue.severity,
                    }
                    self.recorder.record_issue(issue_dict)
                    issues.append(issue_dict)
                
                self._total_issues += len(result.issues)
        
        return issues
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False


# 命令行入口
if __name__ == "__main__":
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description="EFW 调试数据记录工具")
    parser.add_argument("action", choices=["info", "convert", "merge"],
                       help="操作类型")
    parser.add_argument("input", nargs="+", help="输入文件路径")
    parser.add_argument("--output", "-o", help="输出文件路径")
    parser.add_argument("--compress", action="store_true", help="压缩输出")
    
    args = parser.parse_args()
    
    try:
        if args.action == "info":
            # 显示记录文件信息
            for path in args.input:
                path = Path(path)
                if not path.exists():
                    print(f"文件不存在: {path}", file=sys.stderr)
                    continue
                
                stats = {
                    "path": str(path),
                    "size_bytes": path.stat().st_size,
                    "size_mb": round(path.stat().st_size / 1024 / 1024, 2),
                }
                
                # 统计记录数
                snapshot_count = 0
                issue_count = 0
                first_time = None
                last_time = None
                
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            record = json.loads(line)
                            if record.get("type") == "snapshot":
                                snapshot_count += 1
                                if not first_time:
                                    first_time = record.get("record_time")
                                last_time = record.get("record_time")
                            elif record.get("type") == "issue":
                                issue_count += 1
                        except json.JSONDecodeError:
                            pass
                
                stats["snapshot_count"] = snapshot_count
                stats["issue_count"] = issue_count
                stats["first_time"] = first_time
                stats["last_time"] = last_time
                
                print(json.dumps(stats, indent=2, ensure_ascii=False))
        
        elif args.action == "merge":
            # 合并多个记录文件
            if not args.output:
                print("合并操作需要 --output 参数", file=sys.stderr)
                sys.exit(1)
            
            with open(args.output, "w", encoding="utf-8") as out_f:
                for path in args.input:
                    path = Path(path)
                    if not path.exists():
                        print(f"跳过不存在的文件: {path}", file=sys.stderr)
                        continue
                    
                    with open(path, "r", encoding="utf-8") as in_f:
                        for line in in_f:
                            out_f.write(line)
            
            print(f"已合并 {len(args.input)} 个文件到 {args.output}")
    
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
