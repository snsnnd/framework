"""EFW 模型：结构、校验与分析。没有 UI 与文件系统依赖。"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,23}$")
FN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,47}$")
CTYPE = {"float": "float", "int": "int32_t", "bool": "bool"}
QUEUE_ITEMS = {"uint8_t": 1, "int8_t": 1, "uint16_t": 2, "int16_t": 2, "uint32_t": 4, "int32_t": 4, "float": 4}
OPS = (">", ">=", "<", "<=", "==", "!=")
POLICIES = ("drop_oldest", "drop_newest")
SIM_KINDS = {
    "const": {"value": 0.0},
    "sine": {"offset": 0.0, "amp": 1.0, "period_ms": 1000},
    "ramp": {"from": 0.0, "to": 1.0, "duration_ms": 1000},
    "square": {"low": 0.0, "high": 1.0, "period_ms": 1000},
    "noise": {"offset": 0.0, "amp": 1.0},
    "follow": {"output": "", "base": 0.0, "gain": 1.0, "tau_ms": 1000},
}

# 每种步骤：中文名、读取的信号字段、写入的信号字段、可整定参数默认值
STEPS: dict[str, dict[str, Any]] = {
    "read": {"label": "读取", "out": ["to"], "params": {}},
    "write": {"label": "写入", "inp": ["from"], "params": {}},
    "set": {"label": "设为常数", "out": ["to"], "params": {"value": 0.0}},
    "lowpass": {"label": "低通滤波", "inp": ["from"], "out": ["to"], "params": {"alpha": 0.2}},
    "avg": {"label": "滑动平均", "inp": ["from"], "out": ["to"], "params": {}, "static": {"window": 8}},
    "scale": {"label": "缩放", "inp": ["from"], "out": ["to"], "params": {"gain": 1.0, "offset": 0.0}},
    "clamp": {"label": "限幅", "inp": ["from"], "out": ["to"], "params": {"min": 0.0, "max": 100.0}},
    "pid": {"label": "PID", "inp": ["setpoint", "feedback"], "out": ["to"],
            "params": {"kp": 1.0, "ki": 0.0, "kd": 0.0, "out_min": 0.0, "out_max": 100.0}},
    "emit": {"label": "发出事件", "inp": ["signal"], "params": {"value": 0.0}},
    "custom": {"label": "自定义 C", "params": {}},
}

# 参数的滑块范围（仅用于界面，目标不强制）
PARAM_RANGE = {"alpha": (0.0, 1.0)}


def is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def canonical(model: dict) -> str:
    return json.dumps(model, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def model_hash(model: dict) -> str:
    return hashlib.sha1(canonical(model).encode("utf-8")).hexdigest()[:12]


def items(model: dict, key: str) -> list[dict]:
    value = model.get(key, [])
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def fn_signatures(model: dict) -> list[dict]:
    """模型要求用户实现的全部 C 函数。"""
    result: list[dict] = []
    for i in items(model, "inputs"):
        t = CTYPE.get(i.get("type"), "float")
        result.append({"name": f"{i['id']}_read", "kind": "input", "owner": f"inputs/{i['id']}", "file": "board/io.c",
                       "ret": "efw_status_t", "params": f"{t} *value", "role": f"读取输入“{i.get('label') or i['id']}”"})
    for o in items(model, "outputs"):
        t = CTYPE.get(o.get("type"), "float")
        result.append({"name": f"{o['id']}_write", "kind": "output", "owner": f"outputs/{o['id']}", "file": "board/io.c",
                       "ret": "efw_status_t", "params": f"{t} value", "role": f"写入输出“{o.get('label') or o['id']}”"})
    seen = {r["name"] for r in result}

    def add(name: Any, kind: str, owner: str, ret: str, role: str) -> None:
        if isinstance(name, str) and name and name not in seen:
            seen.add(name)
            result.append({"name": name, "kind": kind, "owner": owner, "file": "src/logic.c", "ret": ret, "params": "void", "role": role})

    for f in items(model, "flows"):
        for s in items(f, "steps"):
            if s.get("kind") == "custom":
                add(s.get("call"), "step", f"flows/{f.get('id')}/{s.get('id')}", "efw_status_t", "自定义步骤")
    for m in items(model, "machines"):
        for st in items(m, "states"):
            add(st.get("on_enter"), "hook", f"machines/{m.get('id')}/{st.get('id')}", "efw_status_t", "进入状态时调用")
            add(st.get("on_exit"), "hook", f"machines/{m.get('id')}/{st.get('id')}", "efw_status_t", "离开状态时调用")
        for t in items(m, "transitions"):
            on = t.get("on") if isinstance(t.get("on"), dict) else {}
            add(on.get("call"), "cond", f"machines/{m.get('id')}/{t.get('id')}", "int", "转换条件，返回非 0 触发")
    for r in result:
        r["signature"] = f"{r['ret']} {r['name']}({r['params']})"
    return result


def tunables(model: dict) -> list[dict]:
    """所有可在线整定的量：步骤参数与标记 tune 的信号。"""
    out = []
    for f in items(model, "flows"):
        for s in items(f, "steps"):
            spec = STEPS.get(s.get("kind"), {})
            for name, default in spec.get("params", {}).items():
                value = s.get(name, default)
                lo, hi = PARAM_RANGE.get(name, (None, None))
                if lo is None:
                    span = max(10.0, abs(float(value)) * 5) if is_num(value) else 10.0
                    lo, hi = (-span if name in {"offset", "value", "min", "max", "out_min", "out_max"} else 0.0), span
                out.append({"key": f"{f['id']}.{s['id']}.{name}", "label": f"{f.get('label') or f['id']} · {s.get('label') or STEPS[s['kind']]['label']} · {name}",
                            "value": value, "min": lo, "max": hi, "kind": "param"})
    for sig in items(model, "signals"):
        tune = sig.get("tune")
        if isinstance(tune, dict):
            out.append({"key": sig["id"], "label": sig.get("label") or sig["id"], "value": sig.get("init", 0),
                        "min": tune.get("min", 0), "max": tune.get("max", 100), "kind": "signal"})
    return out


class Diags:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, level: str, at: str, message: str, hint: str = "") -> None:
        self.items.append({"level": level, "at": at, "message": message, "hint": hint})

    def error(self, at: str, message: str, hint: str = "") -> None:
        self.add("error", at, message, hint)

    def warn(self, at: str, message: str, hint: str = "") -> None:
        self.add("warn", at, message, hint)

    def info(self, at: str, message: str, hint: str = "") -> None:
        self.add("info", at, message, hint)

    @property
    def has_error(self) -> bool:
        return any(d["level"] == "error" for d in self.items)


def _ident(d: Diags, at: str, value: Any, seen: set, what: str) -> bool:
    if not isinstance(value, str) or not ID_RE.match(value):
        d.error(at, f"{what}的标识符“{value}”不合法", "使用小写字母开头，只含小写字母、数字、下划线，最长 24 位，例如 temp_raw")
        return False
    if value in seen:
        d.error(at, f"{what}的标识符“{value}”重复", "同一类对象里每个标识符必须唯一")
        return False
    seen.add(value)
    return True


def validate(model: Any) -> list[dict]:
    d = Diags()
    if not isinstance(model, dict):
        d.error("project", "模型必须是 JSON 对象")
        return d.items
    if model.get("version") != 1:
        d.error("project", "不支持的模型版本", "此版本只支持 version=1")
    if not isinstance(model.get("name"), str) or not model["name"].strip():
        d.error("project", "项目名称不能为空")
    tick = model.get("tick_ms", 1)
    if not isinstance(tick, int) or isinstance(tick, bool) or not 1 <= tick <= 1000:
        d.error("project", "tick_ms 必须是 1..1000 的整数")
        tick = 1
    limits = model.get("limits", {})
    evcap = limits.get("event_queue", 16) if isinstance(limits, dict) else 16
    if not isinstance(evcap, int) or isinstance(evcap, bool) or not 1 <= evcap <= 256:
        d.error("comms/events", "事件队列容量必须是 1..256 的整数")
    for key in ("signals", "inputs", "outputs", "events", "queues", "flows", "machines"):
        if key in model and not isinstance(model[key], list):
            d.error("project", f"{key} 必须是数组")
        elif any(not isinstance(x, dict) for x in model.get(key, [])):
            d.error("project", f"{key} 里的每一项必须是对象")

    sig_ids: set = set(); in_ids: set = set(); out_ids: set = set(); ev_ids: set = set(); q_ids: set = set()
    for s in items(model, "signals"):
        at = f"signals/{s.get('id')}"
        if _ident(d, at, s.get("id"), sig_ids, "信号"):
            if s.get("type") not in CTYPE:
                d.error(at, f"信号“{s['id']}”的类型必须是 float / int / bool")
            if not is_num(s.get("init", 0)):
                d.error(at, f"信号“{s['id']}”的初值必须是数字")
            tune = s.get("tune")
            if tune is not None and not (isinstance(tune, dict) and is_num(tune.get("min")) and is_num(tune.get("max")) and tune["min"] < tune["max"]):
                d.error(at, f"信号“{s['id']}”的整定范围需要 min < max 两个数字")
    for i in items(model, "inputs"):
        at = f"comms/inputs/{i.get('id')}"
        if _ident(d, at, i.get("id"), in_ids, "输入"):
            if i.get("type") not in CTYPE:
                d.error(at, f"输入“{i['id']}”的类型必须是 float / int / bool")
    for o in items(model, "outputs"):
        at = f"comms/outputs/{o.get('id')}"
        if _ident(d, at, o.get("id"), out_ids, "输出") and o.get("type") not in CTYPE:
            d.error(at, f"输出“{o['id']}”的类型必须是 float / int / bool")
    for i in items(model, "inputs"):
        sim = i.get("sim")
        at = f"comms/inputs/{i.get('id')}"
        if sim is None:
            continue
        if not isinstance(sim, dict) or sim.get("kind") not in SIM_KINDS:
            d.error(at, f"输入“{i.get('id')}”的仿真类型无效", "可用：" + " / ".join(SIM_KINDS))
            continue
        for field, default in SIM_KINDS[sim["kind"]].items():
            if field == "output":
                if sim.get(field) not in out_ids:
                    d.error(at, f"仿真 follow 需要指向一个存在的输出", "选择被加热器/电机等输出驱动的响应对象")
            elif field.endswith("_ms"):
                if not is_num(sim.get(field, default)) or sim.get(field, default) <= 0:
                    d.error(at, f"仿真字段 {field} 必须是正数")
            elif not is_num(sim.get(field, default)):
                d.error(at, f"仿真字段 {field} 必须是数字")
        if "noise" in sim and not is_num(sim["noise"]):
            d.error(at, "仿真字段 noise 必须是数字")
    for e in items(model, "events"):
        _ident(d, f"comms/events/{e.get('id')}", e.get("id"), ev_ids, "事件")
    for q in items(model, "queues"):
        at = f"comms/queues/{q.get('id')}"
        if _ident(d, at, q.get("id"), q_ids, "队列"):
            if q.get("item") not in QUEUE_ITEMS:
                d.error(at, f"队列“{q['id']}”的条目类型无效", "可用：" + ", ".join(QUEUE_ITEMS))
            cap = q.get("capacity")
            if not isinstance(cap, int) or isinstance(cap, bool) or not 1 <= cap <= 1024:
                d.error(at, f"队列“{q['id']}”的容量必须是 1..1024 的整数")
            if q.get("policy", "drop_newest") not in POLICIES:
                d.error(at, f"队列“{q['id']}”的满队策略必须是 drop_oldest 或 drop_newest")

    if len(items(model, "flows")) > 15:
        d.error("flows", "数据流最多 15 个", "调度器默认最多 16 个任务（含状态机任务）；可合并数据流")
    flow_ids: set = set()
    for f in items(model, "flows"):
        fat = f"flows/{f.get('id')}"
        if not _ident(d, fat, f.get("id"), flow_ids, "数据流"):
            continue
        p = f.get("period_ms")
        if not isinstance(p, int) or isinstance(p, bool) or p < 1:
            d.error(fat, f"数据流“{f['id']}”的周期必须是正整数（毫秒）")
        elif p % tick:
            d.error(fat, f"数据流“{f['id']}”的周期 {p}ms 不是节拍 {tick}ms 的整数倍", f"改成 {tick} 的倍数，例如 {((p // tick) + 1) * tick}")
        steps = f.get("steps", [])
        if not isinstance(steps, list) or any(not isinstance(s, dict) for s in steps):
            d.error(fat, "steps 必须是对象数组")
            continue
        if not steps:
            d.warn(fat, f"数据流“{f['id']}”还没有步骤", "在“数据流”页添加：读取 → 处理 → 写入")
        step_ids: set = set()
        for s in steps:
            sat = f"{fat}/{s.get('id')}"
            if not _ident(d, sat, s.get("id"), step_ids, "步骤"):
                continue
            kind = s.get("kind")
            spec = STEPS.get(kind)
            if not spec:
                d.error(sat, f"未知步骤类型“{kind}”", "可用：" + " / ".join(STEPS))
                continue
            for field in spec.get("inp", []) + spec.get("out", []):
                if s.get(field) not in sig_ids:
                    d.error(sat, f"{spec['label']}步骤的“{field}”需要选择一个已有信号", "先到“通信”页创建信号，或在步骤里选择")
            if kind == "read" and s.get("input") not in in_ids:
                d.error(sat, "读取步骤需要选择一个输入", "先到“通信”页创建输入")
            if kind == "write" and s.get("output") not in out_ids:
                d.error(sat, "写入步骤需要选择一个输出", "先到“通信”页创建输出")
            if kind == "emit":
                if s.get("event") not in ev_ids:
                    d.error(sat, "发出事件步骤需要选择一个事件", "先到“通信”页创建事件")
                if s.get("op") not in OPS:
                    d.error(sat, "发出事件步骤的比较符必须是 " + " ".join(OPS))
            if kind == "custom":
                if not isinstance(s.get("call"), str) or not FN_RE.match(s.get("call", "")):
                    d.error(sat, "自定义步骤需要一个合法的 C 函数名")
                for key in ("reads", "writes"):
                    v = s.get(key, [])
                    if not isinstance(v, list) or any(x not in sig_ids for x in v):
                        d.error(sat, f"自定义步骤的 {key} 必须是已有信号列表")
            for name, default in spec.get("params", {}).items():
                if not is_num(s.get(name, default)):
                    d.error(sat, f"步骤参数 {name} 必须是数字")
            if kind == "lowpass" and is_num(s.get("alpha", 0.2)) and not 0 < s.get("alpha", 0.2) <= 1:
                d.error(sat, "低通系数 alpha 需要在 (0, 1] 内", "越小越平滑；1 表示不滤波")
            if kind == "avg":
                w = s.get("window", 8)
                if not isinstance(w, int) or isinstance(w, bool) or not 2 <= w <= 64:
                    d.error(sat, "滑动平均窗口必须是 2..64 的整数")
            if kind == "clamp" and is_num(s.get("min", 0)) and is_num(s.get("max", 100)) and s.get("min", 0) > s.get("max", 100):
                d.error(sat, "限幅的 min 不能大于 max")
            if kind == "pid" and is_num(s.get("out_min", 0)) and is_num(s.get("out_max", 100)) and s.get("out_min", 0) >= s.get("out_max", 100):
                d.error(sat, "PID 输出下限必须小于上限")

    controllers: dict[str, str] = {}
    mach_ids: set = set()
    for m in items(model, "machines"):
        mat = f"machines/{m.get('id')}"
        if not _ident(d, mat, m.get("id"), mach_ids, "状态机"):
            continue
        states = [s for s in m.get("states", []) if isinstance(s, dict)] if isinstance(m.get("states"), list) else []
        st_ids: set = set()
        if not states:
            d.error(mat, f"状态机“{m['id']}”至少需要一个状态")
        for st in states:
            sat = f"{mat}/{st.get('id')}"
            if not _ident(d, sat, st.get("id"), st_ids, "状态"):
                continue
            run = st.get("run", [])
            if not isinstance(run, list) or any(x not in flow_ids for x in run):
                d.error(sat, f"状态“{st['id']}”的 run 必须是已有数据流的列表")
            else:
                for fl in run:
                    if controllers.setdefault(fl, m["id"]) != m["id"]:
                        d.error(sat, f"数据流“{fl}”同时被状态机“{controllers[fl]}”和“{m['id']}”控制", "一个数据流只能由一个状态机启停")
            setv = st.get("set", {})
            if not isinstance(setv, dict) or any(k not in sig_ids or not is_num(v) for k, v in setv.items()):
                d.error(sat, f"状态“{st['id']}”的 set 必须是 {{信号: 数字}}")
            for hook in ("on_enter", "on_exit"):
                if st.get(hook) not in (None, "") and (not isinstance(st.get(hook), str) or not FN_RE.match(st[hook])):
                    d.error(sat, f"{hook} 必须是合法的 C 函数名")
        if states and m.get("initial") not in st_ids:
            d.error(mat, f"状态机“{m['id']}”的初始状态无效", "选择一个已有状态")
        trs = [t for t in m.get("transitions", []) if isinstance(t, dict)] if isinstance(m.get("transitions"), list) else []
        t_ids: set = set()
        reach = {m.get("initial")}
        shadow: set = set()
        for t in trs:
            tat = f"{mat}/{t.get('id')}"
            if not _ident(d, tat, t.get("id"), t_ids, "转换"):
                continue
            if t.get("from") != "*" and t.get("from") not in st_ids:
                d.error(tat, "转换的起点无效", "选择一个已有状态或“任意状态”")
            if t.get("to") not in st_ids:
                d.error(tat, "转换的终点无效", "选择一个已有状态")
            on = t.get("on")
            if not isinstance(on, dict):
                d.error(tat, "转换需要触发条件")
                continue
            if "event" in on:
                if on["event"] not in ev_ids:
                    d.error(tat, "转换的触发事件不存在", "先到“通信”页创建事件")
                key = (t.get("from"), "event", on["event"])
                if key in shadow:
                    d.warn(tat, "同一状态下相同事件已有更靠前的转换，本转换不会被触发")
                shadow.add(key)
            elif "after_ms" in on:
                if not isinstance(on["after_ms"], int) or isinstance(on["after_ms"], bool) or on["after_ms"] < 1:
                    d.error(tat, "超时必须是正整数毫秒")
            elif "signal" in on:
                if on["signal"] not in sig_ids or on.get("op") not in OPS or not is_num(on.get("value")):
                    d.error(tat, "信号条件需要：已有信号、比较符、数字")
            elif "call" in on:
                if not isinstance(on["call"], str) or not FN_RE.match(on["call"]):
                    d.error(tat, "条件函数名不合法")
            else:
                d.error(tat, "转换触发方式必须是 event / after_ms / signal / call 之一")
            if t.get("to") in st_ids:
                reach.add(t["to"])
        for st in states:
            if st.get("id") not in reach:
                d.warn(f"{mat}/{st.get('id')}", f"状态“{st.get('id')}”没有任何转换可以进入", "添加一条以它为终点的转换")

    if d.has_error:
        return d.items

    # ---- 语义警告 ----
    writers: dict[str, list[str]] = {}
    readers: set = set()
    emitted: set = set()
    consumed: set = set()
    used_in: set = set(); used_out: set = set()
    for f in items(model, "flows"):
        for s in items(f, "steps"):
            spec = STEPS[s["kind"]]
            for fld in spec.get("out", []):
                writers.setdefault(s[fld], []).append(f["id"])
            for fld in spec.get("inp", []):
                readers.add(s[fld])
            if s["kind"] == "custom":
                for x in s.get("writes", []):
                    writers.setdefault(x, []).append(f["id"])
                readers.update(s.get("reads", []))
            if s["kind"] == "read":
                used_in.add(s["input"])
            if s["kind"] == "write":
                used_out.add(s["output"])
            if s["kind"] == "emit":
                emitted.add(s["event"])
    for m in items(model, "machines"):
        for st in items(m, "states"):
            for k in st.get("set", {}):
                writers.setdefault(k, []).append(m["id"])
        for t in items(m, "transitions"):
            on = t["on"]
            if "event" in on:
                consumed.add(on["event"])
            if "signal" in on:
                readers.add(on["signal"])
    for sid, fl in writers.items():
        uniq = sorted(set(fl))
        if len(uniq) > 1:
            d.warn(f"signals/{sid}", f"信号“{sid}”被多个地方写入：{', '.join(uniq)}", "同一时刻只应有一个来源，否则后执行的会覆盖先执行的")
    for s in items(model, "signals"):
        tuned = isinstance(s.get("tune"), dict)
        if s["id"] not in writers and not tuned and s["id"] in readers:
            d.warn(f"signals/{s['id']}", f"信号“{s['id']}”被使用但没有任何来源，将一直是初值 {s.get('init', 0)}", "让某个数据流写入它，或把它设为“可整定”")
        if s["id"] not in writers and s["id"] not in readers and not tuned:
            d.info(f"signals/{s['id']}", f"信号“{s['id']}”还没有被使用")
    for i in items(model, "inputs"):
        if i["id"] not in used_in:
            d.info(f"comms/inputs/{i['id']}", f"输入“{i['id']}”还没有被“读取”步骤使用")
    for o in items(model, "outputs"):
        if o["id"] not in used_out:
            d.info(f"comms/outputs/{o['id']}", f"输出“{o['id']}”还没有被“写入”步骤使用")
    for e in items(model, "events"):
        if e["id"] not in emitted:
            d.info(f"comms/events/{e['id']}", f"事件“{e['id']}”没有自动触发来源", f"可在 C 中调用 app_emit_{e['id']}()，或在调试页手动触发")
        if e["id"] not in consumed:
            d.info(f"comms/events/{e['id']}", f"事件“{e['id']}”没有状态机转换在使用")
    return d.items


def find_definitions(sources: dict[str, str]) -> dict[str, list[str]]:
    """粗略解析 .c 文件里的函数定义：name -> 规范化后的参数类型列表。"""
    pattern = re.compile(r"(?:^|[;}\s])(?:static\s+|inline\s+)*[A-Za-z_][\w\s\*]*?\b([A-Za-z_]\w*)\s*\(([^;{}()]*)\)\s*\{")
    found: dict[str, list[str]] = {}
    for name, text in sources.items():
        if not name.endswith(".c"):
            continue
        stripped = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)
        for match in pattern.finditer(stripped):
            if match.group(1) in {"if", "for", "while", "switch", "return", "sizeof"}:
                continue
            found[match.group(1)] = normalize_params(match.group(2))
    return found


def normalize_params(params: str) -> list[str]:
    params = params.strip()
    if params in ("", "void"):
        return ["void"]
    out = []
    for p in params.split(","):
        p = re.sub(r"\s+", " ", p.strip())
        p = re.sub(r"\s*\*\s*", "*", p)
        m = re.match(r"^(.*?[\*\s])([A-Za-z_]\w*)$", p)
        if m:
            p = m.group(1)
        out.append(p.replace(" ", ""))
    return out


def analyze(model: dict, sources: dict[str, str]) -> dict:
    diags = validate(model)
    ok = not any(x["level"] == "error" for x in diags)
    result: dict[str, Any] = {"ok": ok, "diagnostics": diags, "hash": model_hash(model) if isinstance(model, dict) else "",
                              "functions": [], "plan": [], "usage": {}, "memory": {"total": 0, "parts": []}}
    if not isinstance(model, dict):
        return result
    if ok or isinstance(model.get("inputs"), list):
        try:
            defs = find_definitions(sources)
            for fn in fn_signatures(model):
                want = normalize_params(fn["params"])
                have = defs.get(fn["name"])
                fn["defined"] = have is not None
                fn["mismatch"] = None if have is None or have == want else f"参数应为 ({fn['params']})"
                result["functions"].append(fn)
        except (KeyError, TypeError):
            pass
    if not ok:
        return result
    for fn in result["functions"]:
        if not fn["defined"]:
            diags.append({"level": "warn", "at": fn["owner"], "message": f"C 函数 {fn['name']} 还没有实现", "hint": "在“代码”页一键创建骨架"})
        elif fn["mismatch"]:
            diags.append({"level": "error", "at": fn["owner"], "message": f"C 函数 {fn['name']} 的签名不符：{fn['mismatch']}", "hint": f"期望 {fn['signature']}"})
    result["ok"] = not any(x["level"] == "error" for x in diags)
    tick = model.get("tick_ms", 1)
    controlled: dict[str, str] = {}
    for m in items(model, "machines"):
        for st in items(m, "states"):
            for fl in st.get("run", []):
                controlled[fl] = m["id"]
    for f in items(model, "flows"):
        result["plan"].append({"id": f["id"], "label": f.get("label") or f["id"], "kind": "flow", "period_ms": f["period_ms"],
                               "steps": len(f.get("steps", [])), "controlled_by": controlled.get(f["id"])})
    if items(model, "machines") or items(model, "events"):
        result["plan"].append({"id": "_modes", "label": "状态机与事件处理", "kind": "system", "period_ms": tick, "steps": 0, "controlled_by": None})

    usage: dict[str, dict] = {"signals": {}, "events": {}}
    def sig(x: str) -> dict:
        return usage["signals"].setdefault(x, {"writers": [], "readers": []})
    def ev(x: str) -> dict:
        return usage["events"].setdefault(x, {"emitters": [], "consumers": []})
    for f in items(model, "flows"):
        for s in items(f, "steps"):
            ref = {"flow": f["id"], "step": s["id"]}
            spec = STEPS[s["kind"]]
            for fld in spec.get("out", []):
                sig(s[fld])["writers"].append(ref)
            for fld in spec.get("inp", []):
                sig(s[fld])["readers"].append(ref)
            for x in s.get("writes", []) if s["kind"] == "custom" else []:
                sig(x)["writers"].append(ref)
            for x in s.get("reads", []) if s["kind"] == "custom" else []:
                sig(x)["readers"].append(ref)
            if s["kind"] == "emit":
                ev(s["event"])["emitters"].append(ref)
    for m in items(model, "machines"):
        for st in items(m, "states"):
            for k in st.get("set", {}):
                sig(k)["writers"].append({"machine": m["id"], "state": st["id"]})
        for t in items(m, "transitions"):
            on = t["on"]
            ref = {"machine": m["id"], "transition": t["id"]}
            if "event" in on:
                ev(on["event"])["consumers"].append(ref)
            if "signal" in on:
                sig(on["signal"])["readers"].append(ref)
    result["usage"] = usage

    parts = []
    sizes = {"float": 4, "int": 4, "bool": 1}
    sig_bytes = sum(sizes[s["type"]] for s in items(model, "signals"))
    parts.append({"name": "信号", "bytes": sig_bytes})
    parts.append({"name": "输出缓存与强制值", "bytes": len(items(model, "outputs")) * 4 + len(items(model, "inputs")) * 6})
    evcap = model.get("limits", {}).get("event_queue", 16) if isinstance(model.get("limits"), dict) else 16
    parts.append({"name": "事件队列", "bytes": evcap * 2 + 40})
    q_bytes = sum(q["capacity"] * QUEUE_ITEMS[q["item"]] + 40 for q in items(model, "queues"))
    parts.append({"name": "用户队列", "bytes": q_bytes})
    step_bytes = 0
    for f in items(model, "flows"):
        for s in items(f, "steps"):
            spec = STEPS[s["kind"]]
            step_bytes += 4 * len(spec.get("params", {}))
            step_bytes += {"lowpass": 5, "pid": 13, "emit": 1, "avg": 4 * s.get("window", 8) + 2}.get(s["kind"], 0)
        step_bytes += 12
    parts.append({"name": "数据流参数与状态", "bytes": step_bytes})
    parts.append({"name": "调度器槽位", "bytes": len(result["plan"]) * 60})
    result["memory"] = {"total": sum(p["bytes"] for p in parts), "parts": parts}
    return result
