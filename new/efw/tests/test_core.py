from __future__ import annotations

import copy
import json
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path

from studio_core import codegen, project, templates
from studio_core.debug import Session, find_cc, runtime_dir
from studio_core.fsutil import ServiceError
from studio_core.model import analyze, model_hash, validate
from studio_core.service import Service

RECIPES = ("thermostat", "traffic", "sampler", "blank")


def errors(model):
    return [d for d in validate(model) if d["level"] == "error"]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()


class ModelTests(Base):
    def test_recipes_are_valid_and_fully_implemented(self):
        for name in RECIPES:
            model, files, _ = templates.build(name, "x")
            self.assertEqual(errors(model), [], name)
            info = analyze(model, {k: v for k, v in files.items() if k.endswith(".c")})
            self.assertTrue(info["ok"], (name, info["diagnostics"]))
            self.assertTrue(all(f["defined"] and not f["mismatch"] for f in info["functions"]), name)

    def test_errors_point_to_a_place_and_offer_a_hint(self):
        model, _, _ = templates.build("thermostat", "x")
        broken = copy.deepcopy(model)
        broken["flows"][0]["steps"][1]["from"] = "nope"
        broken["flows"][0]["period_ms"] = 7
        broken["flows"][0]["steps"][1]["alpha"] = 3
        broken["machines"][0]["transitions"][0]["on"] = {"event": "ghost"}
        errs = errors(broken)
        self.assertGreaterEqual(len(errs), 3)
        self.assertTrue(any(e["at"].startswith("flows/control/filter") for e in errs))
        self.assertTrue(all(e["at"] and e["message"] for e in errs))
        self.assertTrue(any(e["hint"] for e in errs))

    def test_malformed_models_never_raise(self):
        for bad in (None, [], "x", {"version": 1}, {"version": 1, "name": "a", "flows": [1, 2]}, {"version": 1, "name": "a", "signals": {"a": 1}},
                    {"version": 1, "name": "a", "flows": [{"id": "f", "period_ms": "x", "steps": [None]}]},
                    {"version": 1, "name": "a", "machines": [{"id": "m", "states": "s", "transitions": 3}]}):
            self.assertIsInstance(validate(bad), list)
            self.assertIsInstance(analyze(bad, {}), dict)

    def test_one_machine_per_flow_and_signal_writer_warning(self):
        model, _, _ = templates.build("thermostat", "x")
        two = copy.deepcopy(model)
        two["machines"].append({"id": "other", "label": "", "initial": "a", "states": [{"id": "a", "run": ["control"], "set": {}}], "transitions": []})
        self.assertTrue(any("同时被状态机" in e["message"] for e in errors(two)))
        warns = [d for d in validate(model) if d["level"] == "warn"]
        self.assertTrue(any("被多个地方写入" in w["message"] for w in warns))  # duty: control + cooldown

    def test_missing_and_wrong_c_functions_are_reported(self):
        model, files, _ = templates.build("thermostat", "x")
        info = analyze(model, {"board/io.c": files["board/io.c"]})
        missing = [f["name"] for f in info["functions"] if not f["defined"]]
        self.assertEqual(missing, ["count_fault"])
        wrong = analyze(model, {**{k: v for k, v in files.items() if k.endswith(".c")}, "src/logic.c": "int count_fault(int x) { return 0; }"})
        self.assertFalse(wrong["ok"])
        self.assertTrue(any("签名不符" in d["message"] for d in wrong["diagnostics"]))


@unittest.skipUnless(shutil.which("cc") or shutil.which("gcc"), "需要 C 编译器")
class GeneratedCTests(Base):
    def compile_check(self, name, virtual):
        model, files, _ = templates.build(name, "x")
        out = self.dir / f"{name}-{'v' if virtual else 'r'}"
        (out / "src").mkdir(parents=True); (out / "board").mkdir()
        gen = codegen.generate(model)
        for k, v in gen.items():
            (out / k).write_text(v)
        rt = runtime_dir()
        srcs = [str(out / "app_core.c")] + [str(rt / "src/core" / n) for n in ("scheduler.c", "diagnostic.c", "msgq.c")]
        defs = []
        if virtual:
            srcs.append(str(out / "app_virtual.c")); defs = ["-DAPP_VIRTUAL"]
        for rel, text in files.items():
            if virtual and rel.startswith("board/"):
                continue
            (out / rel).write_text(text)
            if rel.endswith(".c"):
                srcs.append(str(out / rel))
        cmd = [find_cc(), "-std=c99", "-Wall", "-Wextra", "-Werror", *defs, f"-I{out}", f"-I{rt / 'include'}", "-c"]
        for s in srcs:  # -c 逐个编译：真机目标没有 main，也能检查签名与声明
            obj = self.dir / (Path(s).stem + f"-{name}-{virtual}.o")
            done = subprocess.run([*cmd, s, "-o", str(obj)], capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, f"{name} {s}\n{done.stderr[:1500]}")

    def test_virtual_and_real_target_builds_are_warning_free(self):
        for name in RECIPES:
            with self.subTest(recipe=name, target="virtual"):
                self.compile_check(name, True)
            with self.subTest(recipe=name, target="real"):
                self.compile_check(name, False)

    def test_observe_can_be_compiled_out(self):
        model, _, _ = templates.build("traffic", "x")
        (self.dir / "app.h").write_text(codegen.gen_header(model))
        (self.dir / "app_core.c").write_text(codegen.gen_core(model))
        rt = runtime_dir()
        done = subprocess.run([find_cc(), "-std=c99", "-Wall", "-Wextra", "-Werror", "-DAPP_OBSERVE_ENABLE=0", f"-I{self.dir}", f"-I{rt / 'include'}", "-c", str(self.dir / "app_core.c"), "-o", str(self.dir / "o.o")],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr[:1500])


def make_project(base: Path, template: str, name="demo") -> str:
    project.create_project(str(base / name), name, template)
    return str(base / name)


def run_virtual(path, ms, before=(), snap_only=True):
    """通过命令行同一实现运行虚拟目标，返回 (最后快照, 事件列表)。"""
    from studio_core.debug import ProcTransport, build_virtual
    state = project.open_project(path)
    transport = ProcTransport(build_virtual(project.project_root(path), state["model"]), project.project_root(path))
    snaps, events = [], []
    def pump():
        for line in transport.lines():
            if not line.startswith("{"):
                continue
            obj = json.loads(line)
            if obj["e"] == "idle":
                return
            (snaps if obj["e"] == "snap" else events).append(obj)
    try:
        for cmd in before:
            transport.write(cmd)
        transport.write(f"run {ms}")
        pump()
    finally:
        transport.close()
    return snaps, events


@unittest.skipUnless(shutil.which("cc") or shutil.which("gcc"), "需要 C 编译器")
class BehaviourTests(Base):
    def test_thermostat_closes_the_loop_then_trips_and_recovers(self):
        path = make_project(self.dir, "thermostat")
        snaps, events = run_virtual(path, 30000, ["set target 40"])
        temps = [s["s"]["temp"] for s in snaps]
        self.assertLess(temps[0], 25)
        self.assertGreater(temps[-1], 38)              # PID 把仿真对象拉到目标附近
        self.assertLess(max(temps), 46)                # 没有严重过冲
        self.assertFalse([e for e in events if e["e"] == "err"])
        snaps, events = run_virtual(path, 18000, ["set target 90"])   # 目标高于 75 → 触发过热
        trans = [(e["from"], e["to"], e["by"]) for e in events if e["e"] == "trans"]
        self.assertEqual(trans[0], ("running", "fault", "trip"))
        self.assertIn(("fault", "running", "recover"), trans)
        self.assertGreaterEqual(snaps[-1]["s"]["faults"], 1)      # 用户 C 钩子 count_fault 被调用
        fault = next(s for s in snaps if s["m"]["mode"]["s"] == "fault")
        self.assertEqual((fault["f"]["control"]["on"], fault["f"]["cooldown"]["on"]), (0, 1))

    def test_tunable_signal_value_is_echoed_in_params(self):
        path = make_project(self.dir, "thermostat")
        snaps, events = run_virtual(path, 1000, ["set target 45"])
        params = [e for e in events if e["e"] == "params"]
        self.assertTrue(params, "set 之后应回发 params 帧")
        self.assertEqual(params[-1]["p"]["target"], 45)           # 可整定信号也会上报
        self.assertEqual(snaps[-1]["s"]["target"], 45)
        set_ack = next(e for e in events if e["e"] == "ack" and e.get("c") == "set")
        self.assertEqual(set_ack.get("msg", ""), "")

    def test_traffic_light_is_pure_state_machine(self):
        path = make_project(self.dir, "traffic")
        snaps, events = run_virtual(path, 6500)
        seq = [(e["t"], e["to"]) for e in events if e["e"] == "trans"]
        self.assertEqual(seq[:2], [(3000, "green"), (6000, "yellow")])
        self.assertEqual(snaps[-1]["s"]["yellow"], 1)
        snaps, events = run_virtual(path, 4000, ["state light green", "fire button"])
        self.assertTrue(any(e.get("by") == "rush" for e in events if e["e"] == "trans"))

    def test_queue_handoff_and_drop_accounting(self):
        path = make_project(self.dir, "sampler")
        snaps, _ = run_virtual(path, 3000)
        q = snaps[-1]["q"]["samples"]
        self.assertGreater(q["push"], 500)
        self.assertEqual(q["drop"], 0)
        self.assertEqual(snaps[-1]["s"]["batch"], 10)   # 50ms / 5ms
        snaps, _ = run_virtual(path, 1, ["push samples 1"] * 30)
        q = snaps[-1]["q"]["samples"]
        self.assertGreaterEqual(q["drop"], 14)          # 容量 16、drop_oldest：30 次入队至少丢 14 个
        self.assertEqual(q["hw"], 16)

    def test_force_and_pause_and_ack_errors(self):
        path = make_project(self.dir, "thermostat")
        snaps, events = run_virtual(path, 1000, ["force sensor 42", "pause control", "bogus 1", "fire nothing"])
        self.assertEqual(snaps[-1]["forced"], ["sensor"])
        self.assertEqual(snaps[-1]["f"]["control"]["on"], 0)
        self.assertGreater(snaps[-1]["s"]["temp_raw"] + 0, 0)


class ProjectTests(Base):
    def test_user_sources_are_never_touched_by_generation(self):
        path = make_project(self.dir, "thermostat")
        state = project.open_project(path)
        logic = Path(path) / "src/logic.c"
        logic.write_text(logic.read_text() + "\n/* mine */\n")
        before = {f: (Path(path) / f).read_bytes() for f in state["files"]}
        pv = project.preview(path, state["model"])
        self.assertFalse(pv["blocked"], pv.get("reason"))
        project.commit(path, state["model"], pv["token"])
        again = project.preview(path, state["model"])
        self.assertTrue(all(f["status"] == "same" for f in again["files"]))
        self.assertEqual(before, {f: (Path(path) / f).read_bytes() for f in state["files"]})
        self.assertTrue((Path(path) / "generated/app_core.c").exists())
        self.assertFalse((Path(path) / "generated/app_virtual.c").exists())

    def test_hand_edited_generated_file_is_a_conflict_and_extras_survive(self):
        path = make_project(self.dir, "traffic")
        model = project.open_project(path)["model"]
        project.commit(path, model, project.preview(path, model)["token"])
        core = Path(path) / "generated/app_core.c"
        core.write_text(core.read_text() + "/* hand */")
        (Path(path) / "generated/notes.txt").write_text("keep")
        model["tick_ms"] = 1
        model["flows"][0]["period_ms"] = 20
        pv = project.preview(path, model)
        self.assertTrue(pv["blocked"])
        with self.assertRaises(ServiceError):
            project.commit(path, model, pv["token"])
        self.assertTrue(core.read_text().endswith("/* hand */"))
        self.assertEqual((Path(path) / "generated/notes.txt").read_text(), "keep")

    def test_stale_token_and_external_changes(self):
        path = make_project(self.dir, "traffic")
        state = project.open_project(path)
        pv = project.preview(path, state["model"])
        changed = copy.deepcopy(state["model"]); changed["flows"][0]["period_ms"] = 30
        with self.assertRaises(ServiceError):
            project.commit(path, changed, pv["token"])
        (Path(path) / "efw.json").write_text((Path(path) / "efw.json").read_text() + " ")
        with self.assertRaises(ServiceError) as ctx:
            project.save_project(path, state["model"], state["layout"], state["revision"])
        self.assertEqual(ctx.exception.code, "CONFLICT")
        f = project.read_file(path, "board/io.c")
        (Path(path) / "board/io.c").write_text("// external\n")
        with self.assertRaises(ServiceError):
            project.write_file(path, "board/io.c", "x", f["revision"])

    def test_layout_changes_do_not_affect_generation(self):
        path = make_project(self.dir, "thermostat")
        state = project.open_project(path)
        a = project.preview(path, state["model"])["token"]
        project.save_project(path, state["model"], {"machines": {"mode": {"running": {"x": 5, "y": 6}}}}, state["revision"])
        self.assertEqual(a, project.preview(path, state["model"])["token"])

    def test_paths_are_confined(self):
        path = make_project(self.dir, "blank")
        for bad in ("../x.c", "src/../../x.c", "/tmp/x.c", "src\\x.c", "generated/x.c", "src/x.txt"):
            with self.assertRaises(ServiceError):
                project.create_file(path, bad)
        (Path(path) / "src/link").symlink_to(self.dir, target_is_directory=True)
        with self.assertRaises(ServiceError):
            project.create_file(path, "src/link/x.c")

    def test_stubs_group_by_target_file(self):
        model, _, _ = templates.build("thermostat", "x")
        groups = {g["file"]: g["text"] for g in project.stubs(model, ["sensor_read", "heater_write", "count_fault"])}
        self.assertEqual(set(groups), {"board/io.c", "src/logic.c"})
        self.assertIn("efw_status_t sensor_read(float *value)", groups["board/io.c"])
        self.assertIn("/* EFW USER BEGIN sensor_read */", groups["board/io.c"])

    def test_template_regions_are_protected(self):
        path = make_project(self.dir, "thermostat")
        first = project.read_file(path, "src/logic.c")
        self.assertIn("/* EFW USER BEGIN count_fault */", first["content"])
        edited = first["content"].replace("app_set_faults(app_get_faults() + 1);", "app_set_faults(7);")
        project.write_file(path, "src/logic.c", edited, first["revision"])
        current = project.read_file(path, "src/logic.c")
        outside = current["content"].replace('#include "app.h"', '#include "app.h"\n/* note */')
        with self.assertRaises(ServiceError) as ctx:
            project.write_file(path, "src/logic.c", outside, current["revision"])
        self.assertEqual(ctx.exception.code, "TEMPLATE")
        with self.assertRaises(ServiceError) as ctx:
            project.write_file(path, "src/logic.c", current["content"].replace("/* EFW USER END count_fault */", ""), current["revision"])
        self.assertEqual(ctx.exception.code, "TEMPLATE")
        with self.assertRaises(ServiceError) as ctx:
            project.create_file(path, "src/bad.c", "/* EFW USER BEGIN x */\n")
        self.assertEqual(ctx.exception.code, "TEMPLATE")

    def test_missing_function_is_added_with_protected_template(self):
        path = make_project(self.dir, "thermostat")
        model = project.open_project(path)["model"]
        (Path(path) / "src/logic.c").write_text('#include "app.h"\n')
        first = project.read_file(path, "src/logic.c")
        content = first["content"] + "\n" + project.stubs(model, ["count_fault"])[0]["text"] + "\n"
        saved = project.write_file(path, "src/logic.c", content, first["revision"], add_functions=["count_fault"])
        self.assertIn("/* EFW USER BEGIN count_fault */", saved["content"])
        with self.assertRaises(ServiceError) as ctx:
            project.write_file(path, "src/logic.c", saved["content"] + "// tail\n", saved["revision"])
        self.assertEqual(ctx.exception.code, "TEMPLATE")

    def test_create_requires_empty_directory(self):
        (self.dir / "full").mkdir(); (self.dir / "full/a").write_text("x")
        with self.assertRaises(ServiceError):
            project.create_project(str(self.dir / "full"), "n", "blank")


class FakeTransport:
    def __init__(self):
        self.q, self.sent, self.closed = [], [], False

    def feed(self, obj):
        self.q.append(json.dumps(obj) if isinstance(obj, dict) else obj)

    def lines(self):
        while not self.closed:
            if self.q:
                yield self.q.pop(0) + "\n"
            else:
                time.sleep(0.01)

    def write(self, line): self.sent.append(line)
    def close(self): self.closed = True


class SessionTests(Base):
    def wait(self, cond, timeout=15):
        end = time.time() + timeout
        while time.time() < end:
            if cond():
                return True
            time.sleep(0.02)
        return False

    @unittest.skipUnless(shutil.which("cc") or shutil.which("gcc"), "需要 C 编译器")
    def test_virtual_session_record_and_replay(self):
        path = make_project(self.dir, "thermostat")
        events: list[dict] = []
        svc = Service(events.append)
        started = svc.dispatch("debug.start", {"path": path, "target": {"kind": "virtual"}})
        sid = started["session"]
        self.assertEqual(started["state"], "paused")
        self.assertIn("params", started["manifest"])
        svc.dispatch("debug.control", {"session": sid, "action": "speed", "value": 0})
        svc.dispatch("debug.control", {"session": sid, "action": "play"})
        frames = lambda: [f for e in events if e.get("event") == "debug.frames" for f in e["frames"]]
        self.assertTrue(self.wait(lambda: any(f.get("e") == "snap" and f["t"] >= 5000 for f in frames())))
        svc.dispatch("debug.send", {"session": sid, "line": "fire overheat"})
        self.assertTrue(self.wait(lambda: any(f.get("e") == "trans" for f in frames())))
        svc.dispatch("debug.control", {"session": sid, "action": "pause"})
        with self.assertRaises(ServiceError):
            svc.dispatch("debug.send", {"session": sid, "line": "rm -rf /"})
        with self.assertRaises(ServiceError):
            svc.dispatch("debug.send", {"session": sid, "line": "set a 1\nquit"})
        svc.dispatch("debug.stop", {"session": sid})
        runs = svc.dispatch("debug.runs", {"path": path})
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["kind"], "virtual")

        events.clear()
        rep = svc.dispatch("debug.start", {"path": path, "target": {"kind": "replay", "run": runs[0]["name"]}})
        svc.dispatch("debug.control", {"session": rep["session"], "action": "speed", "value": 0})
        svc.dispatch("debug.control", {"session": rep["session"], "action": "play"})
        self.assertTrue(self.wait(lambda: any(e.get("event") == "debug.status" and e["state"] == "ended" for e in events)))
        self.assertTrue(any(f.get("e") == "trans" for f in frames()))
        with self.assertRaises(ServiceError):
            svc.dispatch("debug.send", {"session": rep["session"], "line": "hello"})
        svc.stop_all()

    @unittest.skipUnless(shutil.which("cc") or shutil.which("gcc"), "需要 C 编译器")
    def test_virtual_build_errors_are_reported_readably(self):
        path = make_project(self.dir, "thermostat")
        (Path(path) / "src/logic.c").write_text('#include "app.h"\nefw_status_t count_fault(void) { return oops; }\n')
        with self.assertRaises(ServiceError) as ctx:
            Service().dispatch("debug.start", {"path": path, "target": {"kind": "virtual"}})
        self.assertEqual(ctx.exception.code, "BUILD")
        self.assertIn("oops", str(ctx.exception))

    def test_live_transport_path_and_hash_mismatch(self):
        model, _, _ = templates.build("traffic", "x")
        events: list[dict] = []
        t = FakeTransport()
        s = Session("s1", "serial", t, events.append, None, model_hash(model), 1, False)
        s.start()
        t.feed("boot noise, not json")
        t.feed({"e": "hello", "hash": "deadbeef0000", "tick": 1})
        t.feed({"e": "snap", "t": 250, "s": {"red": 1}})
        self.assertTrue(self.wait(lambda: any(e.get("warning") for e in events)))
        self.assertTrue(self.wait(lambda: any(e.get("event") == "debug.frames" and any(f["e"] == "snap" for f in e["frames"]) for e in events)))
        self.assertEqual(t.sent[0], "dump")
        s.send("set target 3.5")
        self.assertEqual(t.sent[-1], "set target 3.5")
        with self.assertRaises(ServiceError):
            s.control("pause")
        s.stop()
        self.assertTrue(t.closed)


class ServiceTests(Base):
    def test_unknown_method_and_bad_params(self):
        svc = Service()
        with self.assertRaises(ServiceError):
            svc.dispatch("shell.exec", {})
        with self.assertRaises(ServiceError):
            svc.dispatch("project.open", {"nope": 1})

    def test_stdio_server_round_trip(self):
        proc = subprocess.Popen(["python3", "-m", "studio_core.server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, cwd=Path(__file__).resolve().parents[1])
        out, _ = proc.communicate('{"id":1,"method":"system.info","params":{}}\nnot json\n{"id":3,"method":"templates.list"}\n', timeout=30)
        rows = [json.loads(x) for x in out.splitlines()]
        self.assertEqual(rows[0]["result"]["protocol"], 2)
        self.assertEqual(rows[1]["error"]["code"], "INVALID")
        self.assertEqual(len(rows[2]["result"]), 4)


if __name__ == "__main__":
    unittest.main()
