# 02 模型 `efw.json`（version 1）

```jsonc
{
  "version": 1,
  "name": "恒温控制",
  "tick_ms": 1,                      // 应用节拍；所有周期必须是它的整数倍
  "limits": { "event_queue": 16 },   // 事件队列容量
  "signals": [ { "id": "temp", "label": "温度", "type": "float|int|bool",
                 "init": 0, "unit": "°C", "tune": { "min": 0, "max": 100 } | null } ],
  "inputs":  [ { "id": "sensor", "label": "..", "type": "float", "unit": "",
                 "sim": { "kind": "const|sine|ramp|square|noise|follow", ... } } ],
  "outputs": [ { "id": "heater", "label": "..", "type": "float", "unit": "" } ],
  "events":  [ { "id": "start", "label": "启动" } ],
  "queues":  [ { "id": "adc", "label": "..", "item": "uint16_t", "capacity": 16,
                 "policy": "drop_oldest|drop_newest" } ],
  "flows":   [ { "id": "heat", "label": "..", "period_ms": 10, "steps": [ { "id": "s1", "kind": "...", ... } ] } ],
  "machines":[ { "id": "mode", "label": "..", "initial": "idle",
                 "states": [ { "id": "idle", "label": "..", "run": ["heat"], "set": {"sig": 1},
                               "on_enter": "fn", "on_exit": "fn" } ],
                 "transitions": [ { "id": "t1", "from": "idle|*", "to": "heating",
                                    "on": { "event": "start" } | { "after_ms": 1000 }
                                        | { "signal": "temp", "op": ">", "value": 80 } | { "call": "fn" } } ] } ]
}
```

标识符：`^[a-z][a-z0-9_]{0,23}$`。`label` 是给人看的名字，可用中文。同一类对象内 id 唯一。

## 步骤（`flows[].steps[]`）

| kind | 字段 | 语义 |
| --- | --- | --- |
| `read` | `input`, `to` | 调用输入的读取函数，写入信号。失败则本周期剩余步骤中止，`err` 计数 +1 |
| `write` | `output`, `from` | 把信号写到输出 |
| `set` | `to`, `value` | 写常数 |
| `lowpass` | `from`, `to`, `alpha` | `y += alpha·(x−y)`，首次直通 |
| `avg` | `from`, `to`, `window` | 滑动平均，窗口 2..64 |
| `scale` | `from`, `to`, `gain`, `offset` | `y = gain·x + offset` |
| `clamp` | `from`, `to`, `min`, `max` | 限幅 |
| `pid` | `setpoint`, `feedback`, `to`, `kp`, `ki`, `kd`, `out_min`, `out_max` | `dt = period_ms/1000`；积分项以输出单位累计并限幅（调 ki 不会跳变） |
| `emit` | `event`, `signal`, `op`, `value` | 条件由假变真时发出事件（边沿触发） |
| `custom` | `call`, `reads[]`, `writes[]` | 调用 `efw_status_t call(void)`；`reads/writes` 用于依赖显示 |

所有**数值字段**自动成为可整定参数，键为 `flow.step.field`（如 `heat.s3.kp`）。

## 语义规则

### 状态机字段与界面展示

| 字段 | 状态机页展示 |
| --- | --- |
| `machines[].initial` | “初始”标记；不代表当前目标的运行状态 |
| `states[].run` | 选中状态下允许运行的数据流，显示 label 与 id |
| `states[].set` | 进入时写入的信号和值 |
| `states[].on_enter/on_exit` | 进入后 / 离开前调用的 C 函数；省略时显示“无” |
| `transitions[].from/to` | 图中的有向关系；`from: "*"` 显示独立的“任意状态”来源 |
| `transitions[].on` | 事件、停留时长、信号比较或 C 条件，展示为中文句子 |

图上数字对应转换在模型中的声明顺序，包括自转换与同一对状态的多条转换。界面选中只控制详情展示，不改模型、不推导调度、不向目标发命令。

- 流程内信号“先读后写”读到的是上个周期的值（用于反馈）。
- 同一信号被多个数据流写入 → 警告。信号无来源且不可整定 → 警告。
- 状态的 `run` 列出该状态下运行的数据流；任何状态的 `run` 里出现过的数据流即“受该状态机控制”，其余状态里没列出则暂停。数据流不被任何状态机控制则始终运行。同一数据流不可被两个状态机控制。
- 进入状态时：先执行 `set`，再 `on_enter`。离开时先 `on_exit`。初始状态在 `app_init` 中进入。
- 转换按声明顺序评估，第一个匹配生效；`from: "*"` 匹配任意状态。事件转换只在该事件被消费时评估；超时、信号、`call` 转换每个 tick 评估。
- 每个 tick 顺序：所有数据流（按声明顺序）→ 状态机任务（先消费本 tick 开始时已排队的事件，再评估条件类转换）。
- 事件队列满：丢弃最新（计数）。队列可选 `drop_oldest / drop_newest`。

## 输入仿真（仅虚拟目标）

| kind | 字段 |
| --- | --- |
| `const` | `value` |
| `sine` | `offset, amp, period_ms` |
| `ramp` | `from, to, duration_ms`（循环） |
| `square` | `low, high, period_ms` |
| `noise` | `offset, amp` |
| `follow` | `output, base, gain, tau_ms`：一阶响应 `y' = (base + gain·u − y)/tau`，`u` 为该输出的最近写入值——用来闭环演示 PID |

所有 kind 可附加 `noise`（均匀 ±幅度，确定性伪随机）。

## 分析结果

`project.analyze` 返回：结构化诊断（`at` 路径、`message`、`hint`）、需要实现的 C 函数（含期望签名与是否已定义）、调度计划、信号/事件的生产者与消费者、静态内存估算。

通信页直接消费以下字段，不自行推导关系或内存：

| 分析字段 | 展示 |
| --- | --- |
| `usage.signals[id].writers/readers` | 信号的写入来源 / 读取位置 |
| `usage.events[id].emitters/consumers` | 事件的发出 / 消费位置 |
| 引用 `{flow, step}` | 数据流名称与步骤 id |
| 引用 `{machine, state}` 或 `{machine, transition}` | 状态机名称与状态 / 转换 id |
| `memory.parts[].name/bytes` | 信号、事件队列、用户队列各类别的合计估算（搜索不会改变合计） |

`signals[].init` 在界面中明确标记为初始值，`tune` 展示整定范围；均不视作实时数据。当前分析接口不提供队列的引用关系或逐队列内存。源码页依据 `functions[].defined/mismatch` 提示缺失函数与签名错误，保存文件后重新分析磁盘源码。
