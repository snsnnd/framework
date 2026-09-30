"""由模型生成 C：app.h / app_core.c / app_virtual.c / manifest.json。"""
from __future__ import annotations

import json
from typing import Any

from .model import CTYPE, QUEUE_ITEMS, SIM_KINDS, STEPS, fn_signatures, items, model_hash, tunables

HEADER_NOTE = "/* 由 EFW Studio 自动生成，请勿手改；修改会在下次生成时被覆盖。 */\n"


def fl(v: Any) -> str:
    text = f"{float(v):.9g}"
    if not any(c in text for c in ".eE"):
        text += ".0"
    return text + "f"


def cstr(s: str) -> str:
    return json.dumps(s, ensure_ascii=True)


def c_literal(t: str, v: Any) -> str:
    if t == "float":
        return fl(v)
    if t == "bool":
        return "1" if v else "0"
    return str(int(v))


def put_macro(sig: dict) -> str:
    i = sig["id"]
    if sig["type"] == "float":
        return f"#define PUT_{i}(v) (g_sig_{i} = (float)(v))"
    if sig["type"] == "bool":
        return f"#define PUT_{i}(v) (g_sig_{i} = ((v) != 0.0f))"
    return f"#define PUT_{i}(v) (g_sig_{i} = (int32_t)(v))"


def out_conv(t: str, expr: str) -> str:
    return {"float": f"(float)({expr})", "int": f"(int32_t)({expr})", "bool": f"(({expr}) != 0.0f)"}[t]


def gen_header(m: dict) -> str:
    h = [HEADER_NOTE, "#ifndef APP_H\n#define APP_H\n\n#include \"efw/core/common.h\"\n#include <stdint.h>\n#include <stdbool.h>\n\n",
         f"#define APP_MODEL_HASH {cstr(model_hash(m))}\n#define APP_TICK_MS {int(m.get('tick_ms', 1))}u\n\n"]
    ev = items(m, "events")
    h.append("typedef enum {\n    APP_EVT_NONE = 0,\n")
    for n, e in enumerate(ev, 1):
        h.append(f"    APP_EVT_{e['id'].upper()} = {n},\n")
    h.append("    APP_EVT_COUNT_\n} app_event_t;\n\n")
    h.append("/* ---- 生命周期：在你的主循环里调用 ---- */\nefw_status_t app_init(void);\nefw_status_t app_tick(uint32_t now_ms); /* now_ms: 自启动起的绝对毫秒 */\n\n")
    h.append("/* ---- 信号 ---- */\n")
    for s in items(m, "signals"):
        t = CTYPE[s["type"]]
        h.append(f"{t} app_get_{s['id']}(void);\nvoid app_set_{s['id']}({t} value);\n")
    h.append("\n/* ---- 输出的最近写入值 ---- */\n")
    for o in items(m, "outputs"):
        h.append(f"float app_get_out_{o['id']}(void);\n")
    h.append("\n/* ---- 事件（可在中断中调用，需配置 EFW_CRITICAL_ENTER/EXIT） ---- */\n")
    for e in ev:
        h.append(f"efw_status_t app_emit_{e['id']}(void);\n")
    h.append("\n/* ---- 队列 ---- */\n")
    for q in items(m, "queues"):
        t = q["item"]
        h.append(f"efw_status_t app_queue_{q['id']}_push(const {t} *item);\nefw_status_t app_queue_{q['id']}_pop({t} *item);\nuint16_t app_queue_{q['id']}_count(void);\n")
    h.append("\n/* ---- 状态机 ---- */\n")
    for mc in items(m, "machines"):
        h.append(f"const char *app_state_{mc['id']}(void);\n")
    h.append("\n/* ---- 需要你实现的函数（签名由编译器检查） ---- */\n#ifndef APP_VIRTUAL\n")
    for fn in fn_signatures(m):
        if fn["kind"] in ("input", "output"):
            h.append(f"extern {fn['signature']}; /* board/ */\n")
    h.append("#endif\n")
    for fn in fn_signatures(m):
        if fn["kind"] not in ("input", "output"):
            h.append(f"extern {fn['signature']}; /* src/ */\n")
    h.append("\n/* ---- 调试观测（APP_OBSERVE_ENABLE=0 可整体关闭） ---- */\n"
             "void app_observe_poll(uint32_t now_ms);\nvoid app_observe_command(const char *line);\n"
             "void app_observe_write(const uint8_t *data, uint16_t len); /* 由 board/ 或虚拟目标提供 */\n"
             "int app_observe_read(void);                                 /* 无数据返回 -1 */\n")
    h.append("\n#ifdef APP_VIRTUAL\n")
    for i in items(m, "inputs"):
        h.append(f"efw_status_t app_sim_read_{i['id']}({CTYPE[i['type']]} *value);\n")
    h.append("void app_sim_step(uint32_t now_ms);\n#endif\n\n#endif\n")
    return "".join(h)


def step_code(f: dict, s: dict, m: dict, sigs: dict) -> str:
    fid, sid, kind = f["id"], s["id"], s["kind"]
    key = f"{fid}_{sid}"
    period_s = fl(f["period_ms"] / 1000.0)
    P = lambda name: f"g_p_{key}_{name}"
    lines = [f"    /* {sid}: {STEPS[kind]['label']} */"]
    add = lines.append
    if kind == "read":
        i = next(x for x in items(m, "inputs") if x["id"] == s["input"])
        ct = CTYPE[i["type"]]
        add("    {")
        add("        float v;")
        add(f"        if (g_force_on_{i['id']}) {{ v = g_force_val_{i['id']}; }}")
        add(f"        else {{ {ct} raw; efw_status_t rs = APP_READ_{i['id']}(&raw); if (rs != EFW_OK) {{ g_ferr_{fid}++; return EFW_OK; }} v = (float)raw; }}")
        add(f"        PUT_{s['to']}(v);")
        add("    }")
    elif kind == "write":
        o = next(x for x in items(m, "outputs") if x["id"] == s["output"])
        add("    {")
        add(f"        float v = GET_{s['from']}();")
        add(f"        g_out_{o['id']} = v;")
        add(f"        if (APP_WRITE_{o['id']}({out_conv(o['type'], 'v')}) != EFW_OK) {{ g_ferr_{fid}++; return EFW_OK; }}")
        add("    }")
    elif kind == "set":
        add(f"    PUT_{s['to']}({P('value')});")
    elif kind == "lowpass":
        add("    {")
        add(f"        float x = GET_{s['from']}();")
        add(f"        if (!g_st_{key}_init) {{ g_st_{key}_y = x; g_st_{key}_init = 1; }} else {{ g_st_{key}_y += {P('alpha')} * (x - g_st_{key}_y); }}")
        add(f"        PUT_{s['to']}(g_st_{key}_y);")
        add("    }")
    elif kind == "avg":
        w = int(s.get("window", 8))
        add("    {")
        add(f"        float sum = 0.0f; uint8_t k;")
        add(f"        g_st_{key}_buf[g_st_{key}_idx] = GET_{s['from']}();")
        add(f"        g_st_{key}_idx = (uint8_t)((g_st_{key}_idx + 1u) % {w}u);")
        add(f"        if (g_st_{key}_cnt < {w}u) g_st_{key}_cnt++;")
        add(f"        for (k = 0; k < g_st_{key}_cnt; ++k) sum += g_st_{key}_buf[k];")
        add(f"        PUT_{s['to']}(sum / (float)g_st_{key}_cnt);")
        add("    }")
    elif kind == "scale":
        add(f"    PUT_{s['to']}(GET_{s['from']}() * {P('gain')} + {P('offset')});")
    elif kind == "clamp":
        add("    {")
        add(f"        float v = GET_{s['from']}();")
        add(f"        if (v < {P('min')}) v = {P('min')};")
        add(f"        if (v > {P('max')}) v = {P('max')};")
        add(f"        PUT_{s['to']}(v);")
        add("    }")
    elif kind == "pid":
        add("    {")
        add(f"        float err = GET_{s['setpoint']}() - GET_{s['feedback']}();")
        add(f"        float dt = {period_s};")
        add(f"        float d = g_st_{key}_init ? (err - g_st_{key}_prev) / dt : 0.0f;")
        add(f"        float out;")
        add(f"        g_st_{key}_i += {P('ki')} * err * dt;")
        add(f"        if (g_st_{key}_i > {P('out_max')}) g_st_{key}_i = {P('out_max')};")
        add(f"        if (g_st_{key}_i < {P('out_min')}) g_st_{key}_i = {P('out_min')};")
        add(f"        g_st_{key}_prev = err; g_st_{key}_init = 1;")
        add(f"        out = {P('kp')} * err + g_st_{key}_i + {P('kd')} * d;")
        add(f"        if (out > {P('out_max')}) out = {P('out_max')};")
        add(f"        if (out < {P('out_min')}) out = {P('out_min')};")
        add(f"        PUT_{s['to']}(out);")
        add("    }")
    elif kind == "emit":
        add("    {")
        add(f"        uint8_t c = (GET_{s['signal']}() {s['op']} {P('value')});")
        add(f"        if (c && !g_st_{key}_prev) (void)app_emit_{s['event']}();")
        add(f"        g_st_{key}_prev = c;")
        add("    }")
    elif kind == "custom":
        add(f"    if ({s['call']}() != EFW_OK) {{ g_ferr_{fid}++; return EFW_OK; }}")
    return "\n".join(lines) + "\n"


def step_state_decls(f: dict, s: dict) -> list[str]:
    key = f"{f['id']}_{s['id']}"
    spec = STEPS[s["kind"]]
    d = [f"static float g_p_{key}_{n} = {fl(s.get(n, dv))};" for n, dv in spec.get("params", {}).items()]
    k = s["kind"]
    if k == "lowpass":
        d += [f"static float g_st_{key}_y; static uint8_t g_st_{key}_init;"]
    elif k == "avg":
        d += [f"static float g_st_{key}_buf[{int(s.get('window', 8))}]; static uint8_t g_st_{key}_idx, g_st_{key}_cnt;"]
    elif k == "pid":
        d += [f"static float g_st_{key}_i, g_st_{key}_prev; static uint8_t g_st_{key}_init;"]
    elif k == "emit":
        d += [f"static uint8_t g_st_{key}_prev;"]
    return d


OBS_HELPERS = r'''
#if APP_OBSERVE_ENABLE
#include <stdlib.h>
#include <string.h>
static char g_obs_buf[APP_OBS_BUF];
static uint16_t g_obs_len;
static uint8_t g_obs_over;
static uint16_t g_obs_dropped;
static uint32_t g_obs_next;
static uint16_t g_obs_rate = 200u;
static char g_obs_line[96];
static uint8_t g_obs_line_len;

static void obs_raw(const char *s) {
    while (*s) {
        if (g_obs_len + 2u >= APP_OBS_BUF) { g_obs_over = 1; return; }
        g_obs_buf[g_obs_len++] = *s++;
    }
}
static APP_MAYBE_UNUSED void obs_u(uint32_t v) {
    char t[11]; uint8_t n = 0;
    if (v == 0u) { obs_raw("0"); return; }
    while (v) { t[n++] = (char)('0' + v % 10u); v /= 10u; }
    { char o[11]; uint8_t k; for (k = 0; k < n; ++k) o[k] = t[n - 1u - k]; o[n] = 0; obs_raw(o); }
}
static APP_MAYBE_UNUSED void obs_i(int32_t v) {
    if (v < 0) { obs_raw("-"); obs_u((uint32_t)(-(int64_t)v)); } else obs_u((uint32_t)v);
}
static APP_MAYBE_UNUSED void obs_f(float v) {
    uint32_t ip, frac;
    if (v != v || v > 3.0e9f || v < -3.0e9f) { obs_raw("null"); return; }
    if (v < 0.0f) { obs_raw("-"); v = -v; }
    ip = (uint32_t)v;
    frac = (uint32_t)((v - (float)ip) * 10000.0f + 0.5f);
    if (frac >= 10000u) { ip++; frac -= 10000u; }
    obs_u(ip);
    obs_raw(".");
    if (frac < 1000u) obs_raw("0");
    if (frac < 100u) obs_raw("0");
    if (frac < 10u) obs_raw("0");
    obs_u(frac);
}
static void obs_begin(void) { g_obs_len = 0; g_obs_over = 0; }
static void obs_end(void) {
    if (g_obs_over) { g_obs_dropped++; return; }
    g_obs_buf[g_obs_len++] = '\n';
    app_observe_write((const uint8_t *)g_obs_buf, g_obs_len);
}
static APP_MAYBE_UNUSED void obs_flow(const char *name, uint8_t on, uint32_t err) {
    const efw_scheduler_slot_t *sl;
    obs_raw("\""); obs_raw(name); obs_raw("\":{\"on\":"); obs_u(on);
    obs_raw(",\"err\":"); obs_u(err);
    if (efw_scheduler_get(name, &sl) == EFW_OK) {
        obs_raw(",\"run\":"); obs_u(sl->run_count);
        obs_raw(",\"miss\":"); obs_u(sl->missed_releases);
        obs_raw(",\"over\":"); obs_u(sl->overrun_count);
        obs_raw(",\"late\":"); obs_u(sl->last_start_lateness_ms);
        obs_raw(",\"max_late\":"); obs_u(sl->max_start_lateness_ms);
        obs_raw(",\"us\":"); obs_u(sl->last_runtime_us);
        obs_raw(",\"max_us\":"); obs_u(sl->max_runtime_us);
    }
    obs_raw("}");
}
static APP_MAYBE_UNUSED void obs_queue(const char *name, const efw_msgq_t *q) {
    obs_raw("\""); obs_raw(name); obs_raw("\":{\"n\":"); obs_u(q->count);
    obs_raw(",\"cap\":"); obs_u(q->capacity);
    obs_raw(",\"push\":"); obs_u(q->pushed);
    obs_raw(",\"drop\":"); obs_u(q->dropped);
    obs_raw(",\"hw\":"); obs_u(q->high_water);
    obs_raw("}");
}
static APP_MAYBE_UNUSED void obs_ack(const char *cmd, int ok, const char *msg) {
    obs_begin(); obs_raw(ok ? "{\"e\":\"ack\",\"c\":\"" : "{\"e\":\"err\",\"c\":\"");
    obs_raw(cmd); obs_raw("\"");
    if (!ok && msg) { obs_raw(",\"msg\":\""); obs_raw(msg); obs_raw("\""); }
    obs_raw("}"); obs_end();
}
static APP_MAYBE_UNUSED void obs_hello(void) {
    obs_begin();
    obs_raw("{\"e\":\"hello\",\"v\":1,\"hash\":\"" APP_MODEL_HASH "\",\"tick\":"); obs_u(APP_TICK_MS);
    obs_raw(",\"name\":\"" APP_NAME_C "\"}"); obs_end();
}
#endif
'''


def gen_core(m: dict) -> str:
    signals = items(m, "signals"); inputs = items(m, "inputs"); outputs = items(m, "outputs")
    events = items(m, "events"); queues = items(m, "queues"); flows = items(m, "flows"); machines = items(m, "machines")
    sig_by = {s["id"]: s for s in signals}
    evcap = int(m.get("limits", {}).get("event_queue", 16))
    params = tunables(m)
    obs_buf = max(768, ((len(signals) * 28 + len(flows) * 190 + (len(queues) + 1) * 90 + len(machines) * 60 + len(outputs) * 28 + 512) // 128 + 1) * 128)
    c: list[str] = [HEADER_NOTE, '#include "app.h"\n#include "efw/core/msgq.h"\n#include "efw/core/scheduler.h"\n#include <string.h>\n\n#if defined(__GNUC__)\n#define APP_MAYBE_UNUSED __attribute__((unused))\n#else\n#define APP_MAYBE_UNUSED\n#endif\n\n',
                    "#ifndef APP_OBSERVE_ENABLE\n#define APP_OBSERVE_ENABLE 1\n#endif\n", f"#define APP_OBS_BUF {obs_buf}\n",
                    f"#define APP_NAME_C {cstr(''.join(ch if ch.isascii() and ch.isprintable() and ch not in chr(34)+chr(92) else '_' for ch in m['name']))}\n\n",
                    "static uint32_t g_now;\n\n/* ================= 信号 ================= */\n"]
    for s in signals:
        t = CTYPE[s["type"]]
        i = s["id"]
        c.append(f"static {t} g_sig_{i} = {c_literal(s['type'], s.get('init', 0))};\n")
        c.append(f"{t} app_get_{i}(void) {{ return g_sig_{i}; }}\nvoid app_set_{i}({t} value) {{ g_sig_{i} = value; }}\n")
        c.append(f"#define GET_{i}() ((float)g_sig_{i})\n{put_macro(s)}\n")
    c.append("\n/* ================= 输入 / 输出 ================= */\n")
    for i in inputs:
        c.append(f"static uint8_t g_force_on_{i['id']}; static float g_force_val_{i['id']};\n#ifdef APP_VIRTUAL\n#define APP_READ_{i['id']} app_sim_read_{i['id']}\n#else\n#define APP_READ_{i['id']} {i['id']}_read\n#endif\n")
    for o in outputs:
        c.append(f"static float g_out_{o['id']};\nfloat app_get_out_{o['id']}(void) {{ return g_out_{o['id']}; }}\n#ifdef APP_VIRTUAL\n#define APP_WRITE_{o['id']}(v) ((void)(v), EFW_OK)\n#else\n#define APP_WRITE_{o['id']} {o['id']}_write\n#endif\n")
    c.append(f"\n/* ================= 事件与队列 ================= */\nstatic uint16_t g_evq_store[{evcap}];\nstatic efw_msgq_t g_evq;\n")
    for e in events:
        c.append(f"efw_status_t app_emit_{e['id']}(void) {{ uint16_t e = APP_EVT_{e['id'].upper()}; return efw_msgq_push(&g_evq, &e); }}\n")
    for q in queues:
        t, i = q["item"], q["id"]
        c.append(f"static {t} g_q_{i}_store[{q['capacity']}];\nstatic efw_msgq_t g_q_{i};\n"
                 f"efw_status_t app_queue_{i}_push(const {t} *item) {{ return efw_msgq_push(&g_q_{i}, item); }}\n"
                 f"efw_status_t app_queue_{i}_pop({t} *item) {{ return efw_msgq_pop(&g_q_{i}, item); }}\n"
                 f"uint16_t app_queue_{i}_count(void) {{ return efw_msgq_count(&g_q_{i}); }}\n")
    c.append("\n/* ================= 数据流 ================= */\n")
    for f in flows:
        c.append(f"static uint8_t g_fm_{f['id']} = 1; /* 状态机允许 */\nstatic uint8_t g_fx_{f['id']};     /* 调试暂停 */\nstatic uint32_t g_ferr_{f['id']};\n")
        for s in items(f, "steps"):
            c.extend(d + "\n" for d in step_state_decls(f, s))
    for f in flows:
        c.append(f"static efw_status_t flow_{f['id']}(void *ctx) {{\n    (void)ctx;\n    if (!g_fm_{f['id']} || g_fx_{f['id']}) return EFW_OK;\n")
        for s in items(f, "steps"):
            c.append(step_code(f, s, m, sig_by))
        c.append("    return EFW_OK;\n}\n")
        c.append(f"static const efw_scheduler_task_def_t g_task_{f['id']} = {{ {cstr(f['id'])}, {f['period_ms']}u, flow_{f['id']}, 0 }};\n\n")

    c.append("/* ================= 状态机 ================= */\n")
    c.append("typedef struct { uint32_t t; uint8_t m, from, to, tr; } app_trans_t;\nstatic app_trans_t g_hist[8];\nstatic APP_MAYBE_UNUSED uint8_t g_hist_w, g_hist_r;\n"
             "static APP_MAYBE_UNUSED void record_trans(uint8_t m, uint8_t from, uint8_t to, uint8_t tr) {\n    app_trans_t *h = &g_hist[g_hist_w & 7u];\n    h->t = g_now; h->m = m; h->from = from; h->to = to; h->tr = tr; g_hist_w++;\n}\n")
    controlled = {}
    for mc in machines:
        for st in items(mc, "states"):
            for fl_id in st.get("run", []):
                controlled[fl_id] = mc["id"]
    for mi, mc in enumerate(machines):
        mid = mc["id"]
        states = items(mc, "states")
        sidx = {s["id"]: n for n, s in enumerate(states)}
        c.append(f"static uint8_t g_m_{mid}_cur; static uint32_t g_m_{mid}_since;\n")
        c.append(f"static const char *const g_m_{mid}_states[] = {{ " + ", ".join(cstr(s["id"]) for s in states) + " };\n")
        trs = items(mc, "transitions")
        c.append(f"static APP_MAYBE_UNUSED const char *const g_m_{mid}_trs[] = {{ " + ", ".join(cstr(t["id"]) for t in trs) + (", " if trs else "") + '"debug" };\n')
        c.append(f"const char *app_state_{mid}(void) {{ return g_m_{mid}_states[g_m_{mid}_cur]; }}\n")
        ctrl = sorted({fid for st in states for fid in st.get("run", [])})
        c.append(f"static void m_{mid}_enter(uint8_t s) {{\n    switch (s) {{\n")
        for n, st in enumerate(states):
            c.append(f"    case {n}:\n")
            for fid in ctrl:
                c.append(f"        g_fm_{fid} = {1 if fid in st.get('run', []) else 0};\n")
            for k, v in st.get("set", {}).items():
                c.append(f"        PUT_{k}({fl(v)});\n")
            if st.get("on_enter"):
                c.append(f"        (void){st['on_enter']}();\n")
            c.append("        break;\n")
        c.append("    default: break;\n    }\n}\n")
        c.append(f"static void m_{mid}_goto(uint8_t to, uint8_t tr) {{\n    uint8_t from = g_m_{mid}_cur;\n    switch (from) {{\n")
        for n, st in enumerate(states):
            if st.get("on_exit"):
                c.append(f"    case {n}: (void){st['on_exit']}(); break;\n")
        c.append(f"    default: break;\n    }}\n    g_m_{mid}_cur = to; g_m_{mid}_since = g_now;\n    record_trans({mi}u, from, to, tr);\n    m_{mid}_enter(to);\n}}\n")
        c.append(f"static void m_{mid}_step(uint16_t ev) {{\n    uint8_t cur = g_m_{mid}_cur;\n    (void)ev; (void)cur;\n")
        for n, t in enumerate(trs):
            on = t["on"]
            frm = "1" if t["from"] == "*" else f"cur == {sidx[t['from']]}"
            if "event" in on:
                cond = f"ev == APP_EVT_{on['event'].upper()}"
            elif "after_ms" in on:
                cond = f"(uint32_t)(g_now - g_m_{mid}_since) >= {int(on['after_ms'])}u"
            elif "signal" in on:
                cond = f"GET_{on['signal']}() {on['op']} {fl(on['value'])}"
            else:
                cond = f"{on['call']}() != 0"
            c.append(f"    if (({frm}) && ({cond})) {{ m_{mid}_goto({sidx[t['to']]}u, {n}u); return; }}\n")
        c.append("}\n\n")
    have_modes = bool(machines or events)
    if have_modes:
        c.append("static efw_status_t task_modes(void *ctx) {\n    uint16_t n = efw_msgq_count(&g_evq);\n    (void)ctx;\n    while (n--) {\n        uint16_t ev;\n        if (efw_msgq_pop(&g_evq, &ev) != EFW_OK) break;\n")
        for mc in machines:
            c.append(f"        m_{mc['id']}_step(ev);\n")
        c.append("    }\n")
        for mc in machines:
            c.append(f"    m_{mc['id']}_step(APP_EVT_NONE);\n")
        c.append("    return EFW_OK;\n}\n")
        c.append(f"static const efw_scheduler_task_def_t g_task_modes = {{ \"_modes\", {int(m.get('tick_ms', 1))}u, task_modes, 0 }};\n\n")

    c.append("/* ================= 参数表 ================= */\ntypedef struct { const char *key; float *ptr; } app_param_t;\nstatic APP_MAYBE_UNUSED const app_param_t g_params[] = {\n")
    for p in params:
        if p["kind"] == "param":
            fid, sid, name = p["key"].split(".")
            c.append(f"    {{ {cstr(p['key'])}, &g_p_{fid}_{sid}_{name} }},\n")
    c.append("    { 0, 0 }\n};\n")
    c.append("typedef struct { const char *key; float (*get)(void); void (*set)(float); float lo, hi; } app_tsig_t;\n")
    tsigs = [s for s in signals if isinstance(s.get("tune"), dict)]
    for s in tsigs:
        c.append(f"static float tget_{s['id']}(void) {{ return GET_{s['id']}(); }}\n")
        c.append(f"static void tset_{s['id']}(float v) {{ PUT_{s['id']}(v); }}\n")
    c.append("static APP_MAYBE_UNUSED const app_tsig_t g_tsigs[] = {\n" + "".join(f"    {{ {cstr(s['id'])}, tget_{s['id']}, tset_{s['id']}, {fl(s['tune']['min'])}, {fl(s['tune']['max'])} }},\n" for s in tsigs) + "    { 0, 0, 0, 0, 0 }\n};\n\n")

    c.append("/* ================= 生命周期 ================= */\nefw_status_t app_init(void) {\n    efw_status_t s;\n    g_now = 0;\n    s = efw_scheduler_init(); if (s != EFW_OK) return s;\n"
             f"    s = efw_msgq_init(&g_evq, g_evq_store, sizeof(uint16_t), {evcap}u, EFW_MSGQ_DROP_NEWEST); if (s != EFW_OK) return s;\n")
    for q in queues:
        pol = "EFW_MSGQ_DROP_OLDEST" if q.get("policy") == "drop_oldest" else "EFW_MSGQ_DROP_NEWEST"
        c.append(f"    s = efw_msgq_init(&g_q_{q['id']}, g_q_{q['id']}_store, sizeof(g_q_{q['id']}_store[0]), {q['capacity']}u, {pol}); if (s != EFW_OK) return s;\n")
    for mc in machines:
        init = next(n for n, st in enumerate(items(mc, "states")) if st["id"] == mc["initial"])
        c.append(f"    g_m_{mc['id']}_cur = {init}u; g_m_{mc['id']}_since = 0; m_{mc['id']}_enter({init}u);\n")
    for f in flows:
        c.append(f"    s = efw_scheduler_register(&g_task_{f['id']}); if (s != EFW_OK) return s;\n")
    if have_modes:
        c.append("    s = efw_scheduler_register(&g_task_modes); if (s != EFW_OK) return s;\n")
    c.append("    return EFW_OK;\n}\n\nefw_status_t app_tick(uint32_t now_ms) {\n    g_now = now_ms;\n    return efw_scheduler_tick(now_ms);\n}\n\n")

    # ---------- 观测层 ----------
    c.append("/* ================= 调试观测 ================= */\n")
    c.append(OBS_HELPERS)
    c.append("#if APP_OBSERVE_ENABLE\n")
    # snapshot
    c.append("static APP_MAYBE_UNUSED void obs_snapshot(void) {\n    obs_begin();\n    obs_raw(\"{\\\"e\\\":\\\"snap\\\",\\\"t\\\":\"); obs_u(g_now);\n    obs_raw(\",\\\"s\\\":{\");\n")
    for n, s in enumerate(signals):
        fn = {"float": "obs_f", "int": "obs_i", "bool": "obs_u"}[s["type"]]
        c.append(f"    obs_raw(\"{',' if n else ''}\\\"{s['id']}\\\":\"); {fn}(g_sig_{s['id']});\n")
    c.append("    obs_raw(\"},\\\"o\\\":{\");\n")
    for n, o in enumerate(outputs):
        c.append(f"    obs_raw(\"{',' if n else ''}\\\"{o['id']}\\\":\"); obs_f(g_out_{o['id']});\n")
    c.append("    obs_raw(\"},\\\"f\\\":{\");\n")
    for n, f in enumerate(flows):
        if n:
            c.append("    obs_raw(\",\");\n")
        c.append(f"    obs_flow({cstr(f['id'])}, (uint8_t)(g_fm_{f['id']} && !g_fx_{f['id']}), g_ferr_{f['id']});\n")
    c.append("    obs_raw(\"},\\\"q\\\":{\"); obs_queue(\"events\", &g_evq);\n")
    for q in queues:
        c.append(f"    obs_raw(\",\"); obs_queue({cstr(q['id'])}, &g_q_{q['id']});\n")
    c.append("    obs_raw(\"},\\\"m\\\":{\");\n")
    for n, mc in enumerate(machines):
        c.append(f"    obs_raw(\"{',' if n else ''}\\\"{mc['id']}\\\":{{\\\"s\\\":\\\"\"); obs_raw(g_m_{mc['id']}_states[g_m_{mc['id']}_cur]); obs_raw(\"\\\",\\\"since\\\":\"); obs_u(g_m_{mc['id']}_since); obs_raw(\"}}\");\n")
    c.append("    obs_raw(\"},\\\"forced\\\":[\");\n")
    for n, i in enumerate(inputs):
        c.append(f"    if (g_force_on_{i['id']}) {{ obs_raw(\"\\\"{i['id']}\\\",\"); }}\n")
    c.append("    if (g_obs_len && g_obs_buf[g_obs_len - 1u] == ',') g_obs_len--;\n"
             "    obs_raw(\"],\\\"od\\\":\"); obs_u(g_obs_dropped);\n    obs_raw(\"}\"); obs_end();\n}\n")
    # trans flush
    mnames = ", ".join(f"g_m_{mc['id']}_states" for mc in machines) or "0"
    tnames = ", ".join(f"g_m_{mc['id']}_trs" for mc in machines) or "0"
    mids = ", ".join(cstr(mc["id"]) for mc in machines) or '""'
    c.append(f"static const char *const g_mach_ids[] = {{ {mids} }};\nstatic const char *const *const g_mach_states[] = {{ {mnames} }};\nstatic const char *const *const g_mach_trs[] = {{ {tnames} }};\n")
    c.append("static APP_MAYBE_UNUSED void obs_flush_trans(void) {\n    if ((uint8_t)(g_hist_w - g_hist_r) > 8u) g_hist_r = (uint8_t)(g_hist_w - 8u);\n    while (g_hist_r != g_hist_w) {\n"
             "        const app_trans_t *h = &g_hist[g_hist_r & 7u];\n        obs_begin();\n        obs_raw(\"{\\\"e\\\":\\\"trans\\\",\\\"t\\\":\"); obs_u(h->t);\n"
             "        obs_raw(\",\\\"m\\\":\\\"\"); obs_raw(g_mach_ids[h->m]);\n        obs_raw(\"\\\",\\\"from\\\":\\\"\"); obs_raw(g_mach_states[h->m][h->from]);\n"
             "        obs_raw(\"\\\",\\\"to\\\":\\\"\"); obs_raw(g_mach_states[h->m][h->to]);\n        obs_raw(\"\\\",\\\"by\\\":\\\"\"); obs_raw(h->tr == 255u ? \"debug\" : g_mach_trs[h->m][h->tr]);\n"
             "        obs_raw(\"\\\"}\"); obs_end();\n        g_hist_r++;\n    }\n}\n")
    # params
    c.append("static APP_MAYBE_UNUSED void obs_params(void) {\n    uint8_t n = 0; const app_param_t *p; const app_tsig_t *t;\n    obs_begin(); obs_raw(\"{\\\"e\\\":\\\"params\\\",\\\"p\\\":{\");\n"
             "    for (p = g_params; p->key; ++p) { if (n++) obs_raw(\",\"); obs_raw(\"\\\"\"); obs_raw(p->key); obs_raw(\"\\\":\"); obs_f(*p->ptr); }\n"
             "    for (t = g_tsigs; t->key; ++t) { if (n++) obs_raw(\",\"); obs_raw(\"\\\"\"); obs_raw(t->key); obs_raw(\"\\\":\"); obs_f(t->get()); }\n"
             "    obs_raw(\"}}\"); obs_end();\n}\n")
    # command helpers
    c.append("static int cmd_set(const char *key, float v) {\n    const app_param_t *p; const app_tsig_t *t;\n"
             "    for (p = g_params; p->key; ++p) if (strcmp(p->key, key) == 0) { *p->ptr = v; return 1; }\n"
             "    for (t = g_tsigs; t->key; ++t) if (strcmp(t->key, key) == 0) { if (v < t->lo) v = t->lo; if (v > t->hi) v = t->hi; t->set(v); return 1; }\n    return 0;\n}\n")
    c.append("static int cmd_force(const char *name, int on, float v) {\n    (void)name; (void)on; (void)v;\n")
    for i in inputs:
        c.append(f"    if (strcmp(name, {cstr(i['id'])}) == 0) {{ g_force_on_{i['id']} = (uint8_t)on; g_force_val_{i['id']} = v; return 1; }}\n")
    c.append("    return 0;\n}\n")
    c.append("static int cmd_fire(const char *name) {\n    (void)name;\n")
    for e in events:
        c.append(f"    if (strcmp(name, {cstr(e['id'])}) == 0) {{ (void)app_emit_{e['id']}(); return 1; }}\n")
    c.append("    return 0;\n}\n")
    c.append("static int cmd_push(const char *name, float v) {\n    (void)name; (void)v;\n")
    for q in queues:
        c.append(f"    if (strcmp(name, {cstr(q['id'])}) == 0) {{ {q['item']} x = ({q['item']})v; (void)app_queue_{q['id']}_push(&x); return 1; }}\n")
    c.append("    return 0;\n}\n")
    c.append("static int cmd_flow(const char *name, uint8_t paused) {\n    (void)name; (void)paused;\n")
    for f in flows:
        c.append(f"    if (strcmp(name, {cstr(f['id'])}) == 0) {{ g_fx_{f['id']} = paused; return 1; }}\n")
    c.append("    return 0;\n}\n")
    c.append("static int cmd_state(const char *mach, const char *state) {\n    (void)mach; (void)state;\n")
    for mc in machines:
        c.append(f"    if (strcmp(mach, {cstr(mc['id'])}) == 0) {{ uint8_t k; for (k = 0; k < {len(items(mc, 'states'))}u; ++k) if (strcmp(state, g_m_{mc['id']}_states[k]) == 0) {{ m_{mc['id']}_goto(k, 255u); return 1; }} }}\n")
    c.append("    return 0;\n}\n")
    c.append(r'''void app_observe_command(const char *line) {
    char buf[96]; char *a[4] = {0, 0, 0, 0}; uint8_t n = 0; char *p;
    strncpy(buf, line, sizeof(buf) - 1u); buf[sizeof(buf) - 1u] = 0;
    for (p = buf; *p && n < 4u; ) {
        while (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n') *p++ = 0;
        if (!*p) break;
        a[n++] = p;
        while (*p && *p != ' ' && *p != '\t' && *p != '\r' && *p != '\n') ++p;
    }
    if (n == 0u) return;
    if (strcmp(a[0], "hello") == 0) { obs_hello(); return; }
    if (strcmp(a[0], "dump") == 0) { obs_hello(); obs_params(); return; }
    if (strcmp(a[0], "rate") == 0 && n == 2u) { int r = atoi(a[1]); if (r < 20) r = 20; if (r > 10000) r = 10000; g_obs_rate = (uint16_t)r; obs_ack("rate", 1, 0); return; }
    if (strcmp(a[0], "set") == 0 && n == 3u) { if (cmd_set(a[1], (float)atof(a[2]))) { obs_ack("set", 1, 0); obs_params(); } else obs_ack("set", 0, "unknown key"); return; }
    if (strcmp(a[0], "force") == 0 && n == 3u) { obs_ack("force", cmd_force(a[1], 1, (float)atof(a[2])), "unknown input"); return; }
    if (strcmp(a[0], "release") == 0 && n == 2u) { obs_ack("release", cmd_force(a[1], 0, 0.0f), "unknown input"); return; }
    if (strcmp(a[0], "fire") == 0 && n == 2u) { obs_ack("fire", cmd_fire(a[1]), "unknown event"); return; }
    if (strcmp(a[0], "push") == 0 && n == 3u) { obs_ack("push", cmd_push(a[1], (float)atof(a[2])), "unknown queue"); return; }
    if (strcmp(a[0], "pause") == 0 && n == 2u) { obs_ack("pause", cmd_flow(a[1], 1u), "unknown flow"); return; }
    if (strcmp(a[0], "resume") == 0 && n == 2u) { obs_ack("resume", cmd_flow(a[1], 0u), "unknown flow"); return; }
    if (strcmp(a[0], "state") == 0 && n == 3u) { obs_ack("state", cmd_state(a[1], a[2]), "unknown machine or state"); return; }
    obs_ack(a[0], 0, "bad command");
}

void app_observe_poll(uint32_t now_ms) {
    int ch;
    g_now = now_ms;
    while ((ch = app_observe_read()) >= 0) {
        if (ch == '\n') { g_obs_line[g_obs_line_len] = 0; g_obs_line_len = 0; app_observe_command(g_obs_line); }
        else if (ch != '\r' && g_obs_line_len + 1u < sizeof(g_obs_line)) g_obs_line[g_obs_line_len++] = (char)ch;
    }
    obs_flush_trans();
    if ((int32_t)(now_ms - g_obs_next) >= 0) { obs_snapshot(); g_obs_next = now_ms + g_obs_rate; }
}
#else
void app_observe_poll(uint32_t now_ms) { (void)now_ms; }
void app_observe_command(const char *line) { (void)line; }
#endif
''')
    return "".join(c)


def gen_virtual(m: dict) -> str:
    inputs = items(m, "inputs")
    c = [HEADER_NOTE, "/* 虚拟目标：在电脑上运行，用模型里的仿真配置代替 board/ 硬件。 */\n#ifndef APP_VIRTUAL\n#define APP_VIRTUAL 1\n#endif\n#include \"app.h\"\n#include <math.h>\n#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n\n",
         "static uint32_t g_rng = 12345u;\n#if defined(__GNUC__)\n__attribute__((unused))\n#endif\nstatic float sim_rand(void) { g_rng = g_rng * 1664525u + 1013904223u; return ((float)((g_rng >> 8) & 0xFFFFu) / 32767.5f) - 1.0f; }\n"]
    for i in inputs:
        sim = dict(i.get("sim") or {"kind": "const"})
        kind = sim["kind"]
        d = {**SIM_KINDS[kind], **sim}
        noise = fl(sim.get("noise", 0.0))
        c.append(f"static float g_simv_{i['id']};\n")
        if kind == "follow":
            c.append(f"static float g_simy_{i['id']} = {fl(d['base'])};\n")
    c.append("void app_sim_step(uint32_t t) {\n    const float dt = (float)APP_TICK_MS;\n    (void)t; (void)dt;\n")
    for i in inputs:
        sim = dict(i.get("sim") or {"kind": "const"})
        kind = sim["kind"]
        d = {**SIM_KINDS[kind], **sim}
        noise = fl(sim.get("noise", 0.0))
        v = f"g_simv_{i['id']}"
        if kind == "const":
            expr = fl(d["value"])
        elif kind == "sine":
            expr = f"{fl(d['offset'])} + {fl(d['amp'])} * sinf(6.28318530718f * (float)(t % {int(d['period_ms'])}u) / {fl(d['period_ms'])})"
        elif kind == "ramp":
            expr = f"{fl(d['from'])} + ({fl(d['to'])} - {fl(d['from'])}) * ((float)(t % {int(d['duration_ms'])}u) / {fl(d['duration_ms'])})"
        elif kind == "square":
            expr = f"((t % {int(d['period_ms'])}u) < {int(d['period_ms']) // 2}u ? {fl(d['low'])} : {fl(d['high'])})"
        elif kind == "noise":
            expr = f"{fl(d['offset'])} + {fl(d['amp'])} * sim_rand()"
        else:
            y = f"g_simy_{i['id']}"
            c.append(f"    {y} += (({fl(d['base'])} + {fl(d['gain'])} * app_get_out_{d['output']}()) - {y}) * dt / {fl(d['tau_ms'])};\n")
            expr = y
        c.append(f"    {v} = {expr} + {noise} * sim_rand();\n")
    c.append("}\n")
    for i in inputs:
        ct = CTYPE[i["type"]]
        conv = f"g_simv_{i['id']} != 0.0f" if i["type"] == "bool" else f"({ct})g_simv_{i['id']}"
        c.append(f"efw_status_t app_sim_read_{i['id']}({ct} *value) {{ *value = {conv}; return EFW_OK; }}\n")
    c.append(r'''
void app_observe_write(const uint8_t *data, uint16_t len) { fwrite(data, 1, len, stdout); }
int app_observe_read(void) { return -1; }

int main(void) {
    char line[160];
    uint32_t t = 0;
    setvbuf(stdout, NULL, _IOFBF, 1 << 16);
    if (app_init() != EFW_OK) { printf("{\"e\":\"err\",\"c\":\"init\",\"msg\":\"app_init failed\"}\n"); fflush(stdout); return 1; }
    app_observe_command("hello");
    fflush(stdout);
    while (fgets(line, sizeof(line), stdin)) {
        if (strncmp(line, "quit", 4) == 0) break;
        if (strncmp(line, "run ", 4) == 0) {
            long n = atol(line + 4);
            long ticks = n / (long)APP_TICK_MS;
            long i;
            for (i = 0; i < ticks; ++i) {
                efw_status_t s;
                t += APP_TICK_MS;
                app_sim_step(t);
                s = app_tick(t);
                app_observe_poll(t);
                if (s != EFW_OK) { printf("{\"e\":\"err\",\"c\":\"tick\",\"msg\":\"scheduler status %d\"}\n", (int)s); break; }
            }
            printf("{\"e\":\"idle\",\"t\":%lu}\n", (unsigned long)t);
        } else {
            app_observe_command(line);
        }
        fflush(stdout);
    }
    return 0;
}
''')
    return "".join(c)


def gen_manifest(m: dict) -> str:
    out = {
        "schema": 1, "hash": model_hash(m), "name": m["name"], "tick_ms": m.get("tick_ms", 1),
        "signals": [{"id": s["id"], "label": s.get("label") or s["id"], "type": s["type"], "unit": s.get("unit", ""), "tune": s.get("tune")} for s in items(m, "signals")],
        "inputs": [{"id": i["id"], "label": i.get("label") or i["id"], "type": i["type"], "unit": i.get("unit", "")} for i in items(m, "inputs")],
        "outputs": [{"id": o["id"], "label": o.get("label") or o["id"], "type": o["type"], "unit": o.get("unit", "")} for o in items(m, "outputs")],
        "events": [{"id": e["id"], "label": e.get("label") or e["id"]} for e in items(m, "events")],
        "queues": [{"id": q["id"], "label": q.get("label") or q["id"], "item": q["item"], "capacity": q["capacity"]} for q in items(m, "queues")],
        "flows": [{"id": f["id"], "label": f.get("label") or f["id"], "period_ms": f["period_ms"],
                   "steps": [{"id": s["id"], "kind": s["kind"]} for s in items(f, "steps")]} for f in items(m, "flows")],
        "machines": [{"id": mc["id"], "label": mc.get("label") or mc["id"], "initial": mc["initial"],
                      "states": [{"id": s["id"], "label": s.get("label") or s["id"]} for s in items(mc, "states")]} for mc in items(m, "machines")],
        "params": tunables(m),
    }
    return json.dumps(out, ensure_ascii=False, indent=2) + "\n"


def generate(model: dict) -> dict[str, str]:
    return {"app.h": gen_header(model), "app_core.c": gen_core(model), "app_virtual.c": gen_virtual(model), "manifest.json": gen_manifest(model)}
