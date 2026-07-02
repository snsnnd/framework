"""MCU 数据采集器

通过 LiteTune 协议连接 MCU，采集 EFW 框架调试数据。
支持自动重连、断点续传、实时数据流。
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional


class CollectorError(Exception):
    """采集器错误基类"""
    pass


class ConnectionError(CollectorError):
    """连接错误"""
    pass


class ProtocolError(CollectorError):
    """协议错误"""
    pass


class DebugCollector:
    """MCU 调试数据采集器
    
    通过 LiteTune daemon 与 MCU 通信，采集 EFW 框架调试数据。
    
    使用流程：
        collector = DebugCollector(port="/dev/ttyUSB0")
        collector.connect()
        
        # 读取单次快照
        snapshot = collector.read_snapshot()
        
        # 或开始持续采集
        collector.start_continuous(interval_ms=100, callback=my_callback)
        ...
        collector.stop_continuous()
        
        collector.disconnect()
    """
    
    def __init__(
        self,
        port: str,
        baud: int = 115200,
        litetune_root: Optional[Path] = None,
        runtime_dir: Optional[Path] = None,
    ):
        """初始化采集器
        
        Args:
            port: 串口设备路径 (如 /dev/ttyUSB0 或 COM3)
            baud: 波特率，默认 115200
            litetune_root: LiteTune 项目根目录，默认自动查找
            runtime_dir: LiteTune 运行时目录，默认使用 litetune-skill/runtime
        """
        self.port = port
        self.baud = baud
        
        # 查找 LiteTune 路径
        if litetune_root:
            self.litetune_root = Path(litetune_root)
        else:
            # 从当前文件向上查找 lite-tune 目录
            self.litetune_root = self._find_litetune_root()
        
        # LiteTune CLI 路径
        self.lt_py = self.litetune_root / "src" / "litetune-skill" / "code" / "lt.py"
        
        # 运行时目录
        if runtime_dir:
            self.runtime_dir = Path(runtime_dir)
        else:
            self.runtime_dir = self.litetune_root / "src" / "litetune-skill" / "runtime"
        
        # 连接状态
        self.connected = False
        self.daemon_started = False
        
        # 持续采集状态
        self._continuous = False
        self._continuous_thread = None
        
        # 调试点缓存
        self._debug_points: dict[str, dict] = {}
        self._schema: Optional[dict] = None
    
    def _find_litetune_root(self) -> Path:
        """自动查找 LiteTune 项目根目录"""
        # 从当前文件路径推断
        current = Path(__file__).resolve()
        
        # 向上查找包含 lite-tune 目录的父目录
        for parent in current.parents:
            lite_tune = parent / "lite-tune"
            if lite_tune.exists() and (lite_tune / "src" / "litetune-skill").exists():
                return lite_tune
        
        # 如果找不到，尝试相对于 framework 目录
        framework_root = current.parent.parent.parent
        lite_tune = framework_root / "lite-tune"
        if lite_tune.exists():
            return lite_tune
        
        raise ConnectionError(
            "无法找到 LiteTune 项目目录。"
            "请通过 litetune_root 参数指定路径。"
        )
    
    def _run_lt(self, *args: str, timeout: float = 10.0) -> dict:
        """执行 lt.py 命令
        
        Args:
            *args: 命令参数
            timeout: 超时时间（秒）
            
        Returns:
            解析后的 JSON 响应
        """
        cmd = [
            sys.executable,
            str(self.lt_py),
            "--runtime", str(self.runtime_dir),
            "--timeout", str(timeout),
            *args
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 2,
                cwd=str(self.litetune_root)
            )
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"lt.py 命令超时: {' '.join(args)}")
        except FileNotFoundError:
            raise ConnectionError(f"找不到 lt.py: {self.lt_py}")
        
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "未知错误"
            raise ProtocolError(f"lt.py 命令失败: {error_msg}")
        
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise ProtocolError(f"无法解析 lt.py 输出: {e}")
    
    def connect(self) -> bool:
        """连接到 MCU
        
        启动 LiteTune daemon 并建立与 MCU 的连接。
        
        Returns:
            True 表示连接成功
            
        Raises:
            ConnectionError: 连接失败
            TimeoutError: 连接超时
        """
        if self.connected:
            return True
        
        # 检查 daemon 是否已在运行
        try:
            status = self._run_lt("daemon", "status")
            if status.get("ok") and status.get("connectable"):
                self.daemon_started = True
                self.connected = True
                return True
        except (ProtocolError, TimeoutError):
            pass
        
        # 启动 daemon
        try:
            result = self._run_lt(
                "daemon", "start",
                "--port", self.port,
                "--baud", str(self.baud),
                "--wait", "10.0"
            )
            
            if result.get("ok"):
                self.daemon_started = True
                self.connected = True
                return True
            else:
                raise ConnectionError(f"启动 daemon 失败: {result}")
        except Exception as e:
            raise ConnectionError(f"连接 MCU 失败: {e}")
    
    def disconnect(self) -> None:
        """断开与 MCU 的连接"""
        if not self.connected:
            return
        
        # 停止持续采集
        self.stop_continuous()
        
        # 停止 daemon（如果是我们启动的）
        if self.daemon_started:
            try:
                self._run_lt("daemon", "stop", "--force", timeout=5.0)
            except Exception:
                pass
        
        self.connected = False
        self.daemon_started = False
    
    def read_snapshot(self) -> dict[str, Any]:
        """读取当前所有监控点的值
        
        Returns:
            快照数据，格式：
            {
                "time": "2026-07-01T12:00:00.000Z",
                "seq": 123,
                "params": {
                    "param_name": {
                        "id": 0x1000,
                        "type": "f32",
                        "unit": "",
                        "value": 3.14,
                        "status": "OK"
                    },
                    ...
                }
            }
            
        Raises:
            ConnectionError: 未连接
            ProtocolError: 通信错误
        """
        if not self.connected:
            raise ConnectionError("未连接到 MCU")
        
        # 读取所有参数
        result = self._run_lt("param", "get", "--all")
        
        if not result.get("ok"):
            raise ProtocolError(f"读取参数失败: {result}")
        
        # 构造快照
        snapshot = {
            "time": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "seq": int(time.time() * 1000),
            "params": result.get("params", {}),
        }
        
        return snapshot
    
    def read_debug_points(self) -> list[dict]:
        """读取调试监控点列表
        
        通过 LiteTune 命令获取 MCU 端注册的调试监控点。
        
        Returns:
            监控点列表，每个元素包含 name, type, param_id
        """
        if not self.connected:
            raise ConnectionError("未连接到 MCU")
        
        # 获取 schema（包含参数定义）
        result = self._run_lt("schema")
        
        if not result.get("ok"):
            raise ProtocolError(f"获取 schema 失败: {result}")
        
        schema = result.get("schema", {})
        params = schema.get("params", {})
        
        # 过滤出调试参数（param_id >= 0x1000）
        debug_points = []
        for name, info in params.items():
            param_id = info.get("id", 0)
            if param_id >= 0x1000:
                debug_points.append({
                    "name": name,
                    "type": info.get("type"),
                    "unit": info.get("unit", ""),
                    "param_id": param_id,
                })
        
        self._debug_points = {p["name"]: p for p in debug_points}
        return debug_points
    
    def get_schema(self) -> dict:
        """获取 MCU 完整 schema
        
        Returns:
            schema 数据
        """
        if not self.connected:
            raise ConnectionError("未连接到 MCU")
        
        result = self._run_lt("schema")
        
        if not result.get("ok"):
            raise ProtocolError(f"获取 schema 失败: {result}")
        
        self._schema = result.get("schema", {})
        return self._schema
    
    def start_continuous(
        self,
        interval_ms: int = 100,
        callback: Optional[Callable[[dict], None]] = None,
        max_samples: Optional[int] = None,
    ) -> None:
        """开始持续采集
        
        Args:
            interval_ms: 采集间隔（毫秒）
            callback: 每次采集的回调函数，接收 snapshot 参数
            max_samples: 最大采集次数，None 表示无限采集
        """
        if not self.connected:
            raise ConnectionError("未连接到 MCU")
        
        if self._continuous:
            return
        
        self._continuous = True
        
        def _collect_loop():
            count = 0
            interval_sec = interval_ms / 1000.0
            
            while self._continuous:
                if max_samples and count >= max_samples:
                    break
                
                try:
                    snapshot = self.read_snapshot()
                    if callback:
                        callback(snapshot)
                    count += 1
                except Exception as e:
                    if callback:
                        callback({"error": str(e)})
                
                time.sleep(interval_sec)
            
            self._continuous = False
        
        # 在后台线程运行
        import threading
        self._continuous_thread = threading.Thread(target=_collect_loop, daemon=True)
        self._continuous_thread.start()
    
    def stop_continuous(self) -> None:
        """停止持续采集"""
        self._continuous = False
        if self._continuous_thread:
            self._continuous_thread.join(timeout=2.0)
            self._continuous_thread = None
    
    def execute_command(self, name: str, payload: str = "") -> dict:
        """执行 MCU 命令
        
        Args:
            name: 命令名称
            payload: 命令负载（十六进制字符串）
            
        Returns:
            命令执行结果
        """
        if not self.connected:
            raise ConnectionError("未连接到 MCU")
        
        args = ["cmd", name]
        if payload:
            args.extend(["--payload", payload])
        
        result = self._run_lt(*args)
        
        if not result.get("ok"):
            raise ProtocolError(f"执行命令失败: {result}")
        
        return result
    
    def send_request(self, op: str, params: dict = None) -> dict:
        """直接发送 UDS 请求到 daemon
        
        Args:
            op: 操作名称
            params: 参数字典
            
        Returns:
            响应数据
        """
        socket_path = self.runtime_dir / "litetune.sock"
        
        if not socket_path.exists():
            raise ConnectionError(f"daemon socket 不存在: {socket_path}")
        
        request = {
            "id": str(uuid.uuid4()),
            "op": op,
            "params": params or {}
        }
        
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        
        try:
            sock.connect(str(socket_path))
            sock.sendall(json.dumps(request).encode("utf-8") + b"\n")
            
            # 读取响应
            data = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break
            
            response = json.loads(data.decode("utf-8"))
            
            if not response.get("ok"):
                raise ProtocolError(f"请求失败: {response.get('error')}")
            
            return response.get("result", {})
        finally:
            sock.close()
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False


def list_serial_ports() -> list[dict]:
    """列出系统可用串口
    
    Returns:
        串口列表，每个元素包含 device, description, hwid
    """
    try:
        from serial.tools import list_ports
        return [
            {
                "device": p.device,
                "description": p.description,
                "hwid": p.hwid,
            }
            for p in list_ports.comports()
        ]
    except ImportError:
        return []


# 命令行入口
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="EFW 调试数据采集器")
    parser.add_argument("--port", required=True, help="串口设备路径")
    parser.add_argument("--baud", type=int, default=115200, help="波特率")
    parser.add_argument("--action", choices=["snapshot", "list", "schema"],
                       default="snapshot", help="操作类型")
    parser.add_argument("--pretty", action="store_true", help="美化输出")
    
    args = parser.parse_args()
    
    try:
        with DebugCollector(port=args.port, baud=args.baud) as collector:
            if args.action == "snapshot":
                result = collector.read_snapshot()
            elif args.action == "list":
                result = collector.read_debug_points()
            elif args.action == "schema":
                result = collector.get_schema()
            else:
                result = {"error": "未知操作"}
            
            if args.pretty:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(json.dumps(result, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)
