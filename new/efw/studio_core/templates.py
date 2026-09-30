"""三个入门配方：每个都是完整、可编译、可在虚拟目标上运行的项目。"""
from __future__ import annotations

from .model import CTYPE
from .source_template import protect_function

IO_HEADER = '#include "app.h"\n\n/* 硬件相关的读写放在 board/。这些是占位实现：替换成你的 ADC / GPIO / PWM 调用。 */\n'


def _stub(fn: dict) -> str:
    """为一个需要用户实现的函数生成骨架。"""
    head = f"{fn['ret']} {fn['name']}({fn['params']})"
    if fn["kind"] == "input":
        return f"{head} {{\n    if (!value) return EFW_ERR_INVALID;\n    /* TODO: 从硬件读取 */\n    *value = 0;\n    return EFW_OK;\n}}\n"
    if fn["kind"] == "output":
        return f"{head} {{\n    /* TODO: 写到硬件 */\n    (void)value;\n    return EFW_OK;\n}}\n"
    if fn["kind"] == "cond":
        return f"{head} {{\n    /* TODO: 返回非 0 时触发转换 */\n    return 0;\n}}\n"
    return f"{head} {{\n    /* TODO: 你的逻辑 */\n    return EFW_OK;\n}}\n"


def stub(fn: dict) -> str:
    return protect_function(_stub(fn), fn['name'])


OBSERVE_PORT = '''#include "app.h"

/* 调试通道（真机）：把这两个函数接到 UART / USB CDC。虚拟目标不使用本文件。 */
void app_observe_write(const uint8_t *data, uint16_t len) {
    /* EFW USER BEGIN app_observe_write */
    (void)data; (void)len; /* TODO: 逐字节发送 */
    /* EFW USER END app_observe_write */
}

int app_observe_read(void) {
    /* EFW USER BEGIN app_observe_read */
    return -1; /* TODO: 有数据时返回一个字节，否则返回 -1 */
    /* EFW USER END app_observe_read */
}
'''

LOGIC_HEADER = '#include "app.h"\n\n/* 纯逻辑放在 src/：不碰硬件，因此可在电脑上直接运行调试。 */\n'


def sim_follow(output: str) -> dict:
    return {"kind": "follow", "output": output, "base": 20.0, "gain": 60.0, "tau_ms": 4000, "noise": 0.05}


def build(template: str, name: str):
    from .model import fn_signatures
    if template == "thermostat":
        model = {
            "version": 1, "name": name, "tick_ms": 1, "limits": {"event_queue": 8},
            "signals": [
                {"id": "temp_raw", "label": "原始温度", "type": "float", "init": 20, "unit": "°C", "tune": None},
                {"id": "temp", "label": "温度", "type": "float", "init": 20, "unit": "°C", "tune": None},
                {"id": "target", "label": "目标温度", "type": "float", "init": 50, "unit": "°C", "tune": {"min": 20, "max": 90}},
                {"id": "duty", "label": "加热占空比", "type": "float", "init": 0, "unit": "", "tune": None},
                {"id": "faults", "label": "过热次数", "type": "int", "init": 0, "unit": "", "tune": None},
            ],
            "inputs": [{"id": "sensor", "label": "温度传感器", "type": "float", "unit": "°C", "sim": sim_follow("heater")}],
            "outputs": [{"id": "heater", "label": "加热器", "type": "float", "unit": ""}],
            "events": [{"id": "overheat", "label": "过热"}],
            "queues": [],
            "flows": [
                {"id": "control", "label": "温度控制", "period_ms": 10, "steps": [
                    {"id": "read", "kind": "read", "input": "sensor", "to": "temp_raw"},
                    {"id": "filter", "kind": "lowpass", "from": "temp_raw", "to": "temp", "alpha": 0.2},
                    {"id": "guard", "kind": "emit", "event": "overheat", "signal": "temp", "op": ">", "value": 75},
                    {"id": "pid", "kind": "pid", "setpoint": "target", "feedback": "temp", "to": "duty", "kp": 0.08, "ki": 0.05, "kd": 0.0, "out_min": 0, "out_max": 1},
                    {"id": "drive", "kind": "write", "output": "heater", "from": "duty"}]},
                {"id": "cooldown", "label": "强制冷却", "period_ms": 10, "steps": [
                    {"id": "off", "kind": "set", "to": "duty", "value": 0},
                    {"id": "drive", "kind": "write", "output": "heater", "from": "duty"}]},
            ],
            "machines": [{"id": "mode", "label": "工作模式", "initial": "running",
                          "states": [{"id": "running", "label": "正常控制", "run": ["control"], "set": {}},
                                     {"id": "fault", "label": "过热保护", "run": ["cooldown"], "set": {}, "on_enter": "count_fault"}],
                          "transitions": [{"id": "trip", "from": "running", "to": "fault", "on": {"event": "overheat"}},
                                          {"id": "recover", "from": "fault", "to": "running", "on": {"after_ms": 4000}}]}],
        }
        custom = {"count_fault": "efw_status_t count_fault(void) {\n    app_set_faults(app_get_faults() + 1);\n    return EFW_OK;\n}\n"}
    elif template == "traffic":
        def st(i, label, r, y, g):
            return {"id": i, "label": label, "run": [], "set": {"red": r, "yellow": y, "green": g}}
        model = {
            "version": 1, "name": name, "tick_ms": 1, "limits": {"event_queue": 8},
            "signals": [{"id": k, "label": v, "type": "bool", "init": 0, "unit": "", "tune": None} for k, v in (("red", "红灯"), ("yellow", "黄灯"), ("green", "绿灯"))],
            "inputs": [],
            "outputs": [{"id": f"lamp_{k}", "label": v, "type": "bool", "unit": ""} for k, v in (("red", "红灯"), ("yellow", "黄灯"), ("green", "绿灯"))],
            "events": [{"id": "button", "label": "行人按钮"}], "queues": [],
            "flows": [{"id": "drive", "label": "驱动灯", "period_ms": 10, "steps": [
                {"id": f"w_{k}", "kind": "write", "output": f"lamp_{k}", "from": k} for k in ("red", "yellow", "green")]}],
            "machines": [{"id": "light", "label": "信号灯", "initial": "red",
                          "states": [st("red", "红", 1, 0, 0), st("green", "绿", 0, 0, 1), st("yellow", "黄", 0, 1, 0)],
                          "transitions": [{"id": "to_green", "from": "red", "to": "green", "on": {"after_ms": 3000}},
                                          {"id": "to_yellow", "from": "green", "to": "yellow", "on": {"after_ms": 3000}},
                                          {"id": "rush", "from": "green", "to": "yellow", "on": {"event": "button"}},
                                          {"id": "to_red", "from": "yellow", "to": "red", "on": {"after_ms": 1000}}]}],
        }
        custom = {}
    elif template == "sampler":
        model = {
            "version": 1, "name": name, "tick_ms": 1, "limits": {"event_queue": 8},
            "signals": [
                {"id": "raw", "label": "采样值", "type": "float", "init": 0, "unit": "", "tune": None},
                {"id": "mean", "label": "批平均", "type": "float", "init": 0, "unit": "", "tune": None},
                {"id": "smooth", "label": "平滑值", "type": "float", "init": 0, "unit": "", "tune": None},
                {"id": "limit", "label": "报警阈值", "type": "float", "init": 800, "unit": "", "tune": {"min": 0, "max": 1000}},
                {"id": "batch", "label": "本批条数", "type": "int", "init": 0, "unit": "", "tune": None},
                {"id": "led", "label": "报警灯状态", "type": "bool", "init": 0, "unit": "", "tune": None},
            ],
            "inputs": [{"id": "adc", "label": "ADC 通道", "type": "float", "unit": "", "sim": {"kind": "sine", "offset": 500, "amp": 400, "period_ms": 2000, "noise": 20}}],
            "outputs": [{"id": "alarm_led", "label": "报警灯", "type": "bool", "unit": ""}],
            "events": [{"id": "high", "label": "超阈值"}, {"id": "normal", "label": "恢复"}],
            "queues": [{"id": "samples", "label": "采样队列", "item": "uint16_t", "capacity": 16, "policy": "drop_oldest"}],
            "flows": [
                {"id": "sample", "label": "高速采样", "period_ms": 5, "steps": [
                    {"id": "read", "kind": "read", "input": "adc", "to": "raw"},
                    {"id": "enqueue", "kind": "custom", "call": "enqueue_sample", "reads": ["raw"], "writes": []}]},
                {"id": "process", "label": "批处理", "period_ms": 50, "steps": [
                    {"id": "drain", "kind": "custom", "call": "drain_samples", "reads": [], "writes": ["mean", "batch"]},
                    {"id": "smooth", "kind": "lowpass", "from": "mean", "to": "smooth", "alpha": 0.3},
                    {"id": "over", "kind": "emit", "event": "high", "signal": "smooth", "op": ">", "value": 800},
                    {"id": "under", "kind": "emit", "event": "normal", "signal": "smooth", "op": "<", "value": 700}]},
                {"id": "indicate", "label": "指示", "period_ms": 20, "steps": [{"id": "led", "kind": "write", "output": "alarm_led", "from": "led"}]},
            ],
            "machines": [{"id": "alarm", "label": "报警状态", "initial": "ok",
                          "states": [{"id": "ok", "label": "正常", "run": [], "set": {"led": 0}}, {"id": "alert", "label": "报警", "run": [], "set": {"led": 1}}],
                          "transitions": [{"id": "up", "from": "ok", "to": "alert", "on": {"event": "high"}},
                                          {"id": "down", "from": "alert", "to": "ok", "on": {"event": "normal"}}]}],
        }
        custom = {
            "enqueue_sample": "efw_status_t enqueue_sample(void) {\n    uint16_t v = (uint16_t)app_get_raw();\n    (void)app_queue_samples_push(&v); /* 满了按 drop_oldest 丢旧，可在调试页看到 drop 计数 */\n    return EFW_OK;\n}\n",
            "drain_samples": "efw_status_t drain_samples(void) {\n    uint16_t v;\n    uint32_t n = 0, sum = 0;\n    while (app_queue_samples_pop(&v) == EFW_OK) { sum += v; ++n; }\n    if (n) app_set_mean((float)sum / (float)n);\n    app_set_batch((int32_t)n);\n    return EFW_OK;\n}\n",
        }
    elif template == "blank":
        model = {"version": 1, "name": name, "tick_ms": 1, "limits": {"event_queue": 16}, "signals": [], "inputs": [], "outputs": [],
                 "events": [], "queues": [], "flows": [], "machines": []}
        custom = {}
    else:
        raise ValueError(f"未知配方：{template}")
    io_fns = [f for f in fn_signatures(model) if f["kind"] in ("input", "output")]
    other = [f for f in fn_signatures(model) if f["kind"] not in ("input", "output")]
    files = {"board/observe_port.c": OBSERVE_PORT}
    if io_fns:
        files["board/io.c"] = IO_HEADER + "\n".join(stub(f) for f in io_fns)
    if other:
        files["src/logic.c"] = LOGIC_HEADER + "\n".join(protect_function(custom[f["name"]], f["name"]) if f["name"] in custom else stub(f) for f in other)
    layout = {"machines": {}}
    return model, files, layout
