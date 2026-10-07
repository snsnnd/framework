"""MCP server 的端到端测试：真的起一个 stdio server，用 MCP 客户端说协议。

    uv run python -m unittest tests.test_mcp
（只读与授权逻辑不依赖 mcp 包时也能跑；握手测试需要 `--group agent`。）
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studio_core import mcp as mcp_mod  # noqa: E402
from studio_core.fsutil import ServiceError  # noqa: E402
from studio_core.project import create_project  # noqa: E402

try:
    import mcp  # noqa: F401
    HAVE_MCP = True
except ImportError:
    HAVE_MCP = False


def runtime_env() -> dict[str, str]:
    env = dict(os.environ)
    env["EFW_RUNTIME"] = str(ROOT / "runtime")
    env["PYTHONPATH"] = str(ROOT)
    return env


async def _session(args: list[str]):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    params = StdioServerParameters(command=sys.executable, args=args, env=runtime_env(), cwd=str(ROOT))
    return stdio_client(params), ClientSession


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_is_refused_unless_explicitly_allowed(self):
        policy = mcp_mod.Policy(allow_write=False, targets=["virtual"], root=self.root)
        with self.assertRaises(ServiceError) as ctx:
            policy.check("efw_start", {"path": "x", "target": {"kind": "virtual"}})
        self.assertEqual(ctx.exception.code, "FORBIDDEN")
        self.assertIn("--allow-write", str(ctx.exception))
        self.assertFalse((self.root / ".efw" / "agent-audit.jsonl").exists())

    def test_real_targets_need_explicit_permission(self):
        policy = mcp_mod.Policy(allow_write=True, targets=["virtual"], root=self.root)
        policy.check("efw_set", {"session": "s", "key": "k", "value": 1})      # 只读参数不查目标
        with self.assertRaises(ServiceError) as ctx:
            policy.check("efw_start", {"path": "x", "target": {"kind": "serial", "port": "/dev/ttyUSB0"}})
        self.assertIn("不在允许列表", str(ctx.exception))
        policy.targets = ["virtual", "serial"]
        policy.check("efw_start", {"path": "x", "target": {"kind": "serial"}})   # 显式授权后放行

    def test_failed_writes_are_audited(self):
        policy = mcp_mod.Policy(allow_write=True, targets=["virtual"], root=self.root)
        policy.record("efw_start", {"path": "x", "target": {"kind": "tcp"}}, False, "被拒绝")
        policy.record("efw_set", {"session": "s", "key": "k", "value": 2}, True)
        rows = [json.loads(x) for x in (self.root / ".efw" / "agent-audit.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([r["tool"] for r in rows], ["efw_start", "efw_set"])
        self.assertFalse(rows[0]["ok"])
        self.assertTrue(rows[1]["ok"])
        self.assertEqual(rows[1]["args"]["key"], "k")


@unittest.skipUnless(HAVE_MCP, "需要 mcp（uv sync --group agent）")
class HandshakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.path = str(self.dir / "app")
        create_project(self.path, "恒温控制", "thermostat")

    def tearDown(self):
        self.tmp.cleanup()

    def call_tools(self, args: list[str], calls: list[tuple[str, dict]]) -> dict:
        async def run() -> dict:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            params = StdioServerParameters(command=sys.executable, args=args, env=runtime_env(), cwd=str(ROOT))
            out: dict = {}
            async with stdio_client(params) as (r, w):
                async with ClientSession(r, w) as session:
                    await session.initialize()
                    out["tools"] = sorted(t.name for t in (await session.list_tools()).tools)
                    for name, arguments in calls:
                        res = await session.call_tool(name, arguments)
                        out.setdefault(name, []).append(json.loads(res.content[0].text))
            return out

        return asyncio.run(asyncio.wait_for(run(), timeout=300))

    def test_read_only_session_exposes_analysis_and_hides_writes(self):
        result = self.call_tools(["-m", "studio_core.mcp", self.path], [
            ("efw_analyze", {}),
            ("efw_manifest", {}),
            ("efw_open_project", {}),
        ])
        tools = result["tools"]
        self.assertIn("efw_analyze", tools)
        self.assertIn("efw_replay", tools)
        self.assertNotIn("efw_start", tools)      # 只读模式不列出写工具
        self.assertNotIn("efw_set", tools)
        self.assertNotIn("efw_command", tools)
        analyze = result["efw_analyze"][0]
        self.assertTrue(analyze["ok"])
        self.assertIn("diagnostics", analyze)
        manifest = result["efw_manifest"][0]
        self.assertTrue(manifest["hash"])
        self.assertTrue(any(p["key"] for p in manifest["params"]))
        overview = result["efw_open_project"][0]
        self.assertEqual(overview["name"], "恒温控制")

    def test_authorized_session_can_run_and_control_a_virtual_target(self):
        """授权后的写操作全走 MCP 客户端：会话属于 server 进程，不能从测试进程直接调。"""
        compiler = shutil.which("cc") or shutil.which("gcc")

        async def run() -> dict:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            args = ["-m", "studio_core.mcp", self.path, "--allow-write", "--allow-targets", "virtual"]
            params = StdioServerParameters(command=sys.executable, args=args, env=runtime_env(), cwd=str(ROOT))
            out: dict = {}
            async with stdio_client(params) as (r, w):
                async with ClientSession(r, w) as session:
                    await session.initialize()
                    names = sorted(t.name for t in (await session.list_tools()).tools)
                    out["tools"] = names
                    res = await session.call_tool("efw_start", {"target": json.dumps({"kind": "virtual"})})
                    started = json.loads(res.content[0].text)
                    if "error" in started and not compiler:
                        out["skip"] = started["error"]["message"]
                        return out
                    out["efw_start"] = started
                    session_id = started["session"]
                    for name, arguments in [
                        ("efw_set", {"session": session_id, "key": "control.pid.kp", "value": 0.4}),
                        ("efw_fire", {"session": session_id, "event": "overheat"}),
                        # 遥控台：同一条文本命令，人工在界面里敲的和这个完全一样
                        ("efw_command", {"session": session_id, "line": "rate 100"}),
                        ("efw_state", {"session": session_id}),
                        ("efw_generate", {}),
                        ("efw_stop", {"session": session_id}),
                    ]:
                        res = await session.call_tool(name, arguments)
                        out[name] = json.loads(res.content[0].text)
            return out

        result = asyncio.run(asyncio.wait_for(run(), timeout=300))
        if "skip" in result:
            self.skipTest(result["skip"])
        # 授权后写工具全部开放
        for name in ("efw_start", "efw_set", "efw_fire", "efw_force", "efw_release", "efw_stop", "efw_generate", "efw_command"):
            self.assertIn(name, result["tools"])
        started = result["efw_start"]
        self.assertEqual(started["kind"], "virtual")
        self.assertTrue(started["session"])
        self.assertTrue(result["efw_set"].get("ok"))
        self.assertTrue(result["efw_fire"].get("ok"))
        self.assertEqual(result["efw_command"]["sent"], "rate 100")
        self.assertEqual(result["efw_state"]["source"], "live")
        # 生成默认只预览；显式 commit 才写盘
        self.assertFalse(result["efw_generate"]["committed"])
        self.assertFalse((Path(self.path) / "generated" / "app_core.c").exists())

        audit = Path(self.path) / ".efw" / "agent-audit.jsonl"
        rows = [json.loads(x) for x in audit.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([r["tool"] for r in rows], ["efw_start", "efw_set", "efw_fire", "efw_command", "efw_generate", "efw_stop"])
        self.assertTrue(all(r["ok"] for r in rows))

    def test_replay_tool_returns_the_recording_verbatim(self):
        compiler = shutil.which("cc") or shutil.which("gcc")
        if not compiler:
            self.skipTest("没有 C 编译器，无法产生录制")
        service = mcp_mod.Service(lambda event: None)
        started = service.dispatch("debug.start", {"path": self.path, "target": {"kind": "virtual"}})
        service.dispatch("debug.control", {"session": started["session"], "action": "speed", "value": 0})
        service.dispatch("debug.control", {"session": started["session"], "action": "play"})
        time.sleep(1.5)
        service.dispatch("debug.stop", {"session": started["session"]})
        service.stop_all()
        runs = service.dispatch("debug.runs", {"path": self.path})
        self.assertTrue(runs)

        limit = 200
        result = self.call_tools(["-m", "studio_core.mcp", self.path], [("efw_replay", {"run": runs[0]["name"], "limit": limit})])
        frames = result["efw_replay"][0]["frames"]
        on_disk = (Path(self.path) / ".efw" / "runs" / runs[0]["name"]).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(frames), min(len(on_disk), limit))
        self.assertEqual(frames[0].get("e"), "session")
        # 录制首行带模型哈希，回放/离线分析据此判断对不对得上
        self.assertEqual(frames[0].get("hash"), frames[1].get("hash"))
        self.assertTrue(any(f.get("e") == "snap" for f in frames))


if __name__ == "__main__":
    unittest.main()