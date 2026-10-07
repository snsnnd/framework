# 03 运行时与生成代码

## 运行时（`runtime/`）

生成代码只依赖三个运行时源文件：`core/scheduler.c`、`core/diagnostic.c`、`core/msgq.c`。

- **调度器**：`efw_scheduler_tick(now_ms)`，`now_ms` 是自启动起的绝对毫秒数；协作式，迟到只执行一次并累计 `missed_releases`，统计迟到/耗时/超限。
- **消息队列 `efw_msgq_t`（新增）**：静态存储、固定条目大小；策略 `drop_oldest / drop_newest`；统计 `pushed / popped / dropped / high_water`；临界区钩子 `EFW_CRITICAL_ENTER/EXIT`（默认空，MCU 上映射为关中断即可在 ISR 中 `push`）。

## 生成文件（`generated/`）

| 文件 | 内容 |
| --- | --- |
| `app.h` | 事件枚举、`app_init/app_tick`、信号读写、`app_emit_*`、队列 API、需要用户实现的函数声明（签名由编译器强制） |
| `app_core.c` | 信号、参数、数据流、状态机、事件与队列、可观测层（`APP_OBSERVE_ENABLE` 可整体关闭） |
| `app_virtual.c` | 仅虚拟目标：仿真输入、`main`、时间控制 |
| `manifest.json` | 调试清单：信号/参数/数据流/状态机/队列及其范围、模型哈希 |

用户在自己的主循环中：

```c
app_init();
for (;;) { uint32_t now = board_ms(); app_tick(now); app_observe_poll(now); }
```

真机需要在 `board/` 提供 `app_observe_write` / `app_observe_read`（UART/USB 字节读写）；不需要调试则不编译 `APP_OBSERVE_ENABLE`。

## 用户函数签名

| 位置 | 签名 |
| --- | --- |
| `board/` 输入 `x` | `efw_status_t x_read(T *value)` |
| `board/` 输出 `y` | `efw_status_t y_write(T value)` |
| `src/` 自定义步骤 / 状态钩子 | `efw_status_t fn(void)` |
| `src/` 转换 `call` | `int fn(void)`（非 0 为真） |

`T` 为 `float / int32_t / bool`。函数缺失时，界面提供一键创建；签名不符时 C 编译器报错（生成的 `app.h` 声明了它们）。

## 源码模板与固定结构

工具创建或补充的源码（模板项目与函数骨架）带固定结构标记，只有标记内是用户逻辑：

```c
efw_status_t count_fault(void) {
    /* EFW USER BEGIN count_fault */
    app_set_faults(app_get_faults() + 1);
    return EFW_OK;
    /* EFW USER END count_fault */
}
```

- `/* EFW USER BEGIN <name> */` 与 `/* EFW USER END <name> */` 成对、不嵌套、不重名；`name` 是函数名或槽位名。
- 标记之外（函数签名、花括号、标记行、`#include`、注释等）由工具维护：代码页拒绝在这些区域输入，保存接口 `file.write` 也会拒绝（错误码 `TEMPLATE`）。
- 已有用户文件如果完全不含标记，则不加限制，按普通 C 文件编辑。用户自己写的文件不需要套模板。
- 函数骨架通过 `file.write` 的 `add_functions: ["fn", ...]` 在保存时由工具追加，用户只能修改追加后的标记内逻辑。
- 模板标记只是注释，不影响 C 编译；生成代码与运行时不受影响。
- 结构化配置区（`efw.json`）不写进 `.c` 文件：模型配置以 `efw.json` 为单一事实来源，`.c` 只保存实现。

## 静态内存

`analysis.memory` 给出估算：信号、参数、每步状态（滤波/PID/平均窗口）、事件队列、用户队列。所有存储在编译期确定，无 `malloc`。

## 虚拟目标构建缓存

`build_virtual` 把生成文件与可执行文件放在 `.efw/build/<key>/`，`key = 模型哈希 + 全部用户源码摘要`。因此：只改 `src/`/`board/` 或 `efw.json` 会得到新 key；**修改 `codegen.py` 不会让旧缓存失效**，开发调试生成器时要手工删除 `.efw/build/`。最多保留最近 7 份缓存。

## 单编译单元（Keil 等）

不方便维护源文件列表的工程只把 `runtime/src/efw_all.c` 加进编译单元，其余 `.c` 用 `#if EFW_ENABLE_*` 裁剪。消息队列也已纳入聚合：`efw.h` 包含 `efw/core/msgq.h`，`efw_all.c` 包含 `efw/core/msgq.c`，开关是 `EFW_ENABLE_MSGQ`（默认 1）。`msgq.c` 没有 `static` 符号，因此与其他模块放进同一编译单元不会冲突。

## 真机链路（串口 / TCP）

主机侧用 `SerialTransport`（pyserial，设备 + 波特率）与 `TcpTransport`（主机 + 端口），两者都是 `recv` + 超时循环 + 自行拼行：不要用 `socket.makefile()`，它的 `close()` 会等读到 EOF，而固件不会主动发 EOF，会让“停止调试”永久卡住。目标侧是 `board/observe_port.c`（已带 `EFW USER` 标记），用同一套文本命令协议。主机不接管真机的节拍，因此播放/暂停/单步只对虚拟目标可用。

## 可观测性开销

每个数据流一个 `run/miss/over/err/late/us` 统计（来自调度器）；每个队列 `n/push/drop/hw`；快照默认 200 ms 一帧，约 1 KB，115200 波特下约 45% 带宽；可用 `rate` 调整。

## Agent 接入（MCP server）

EFW 对外是一套 JSON Lines 服务 + 文本调试协议。为了让 agent 直接检测与控制，额外提供 MCP server：

```bash
uv run --group agent python -m studio_core.mcp [项目路径]          # 只读（默认）
uv run --group agent python -m studio_core.mcp <路径> --allow-write --allow-targets virtual,serial,tcp
```

**默认只读。** 写操作（启动会话、改参数、触发事件、强制输出、生成代码）在没有 `--allow-write` 时既不出现在 `tools/list`，直接调用也会被拒；真机目标还要显式列进 `--allow-targets`。每一次写（含被拒的）都记进项目的 `.efw/agent-audit.jsonl`。

| 工具 | 档位 | 作用 |
| --- | --- | --- |
| `efw_open_project` / `efw_analyze` / `efw_manifest` / `efw_sources` | 读 | 项目结构、诊断与执行计划、固件暴露的信号与可整定参数、用户源文件 |
| `efw_runs` / `efw_replay` / `efw_state` | 读 | 已录制记录、离线回放任意一段帧、取一次实时或最近录制的状态 |
| `efw_start` / `efw_set` / `efw_fire` / `efw_force` / `efw_release` / `efw_stop` | 写 | 启动会话与控制目标（对应协议的 `set`/`fire`/`force`/`release`） |
| `efw_generate` | 写 | 预览生成结果，`commit=true` 才写盘 |

会话属于 server 进程：agent 用 `efw_start` 拿到 `session` 后，后续控制都带这个 `session`；进程退出会自动停掉会话。响应是 JSON 文本，失败时是 `{"error": {"code", "message"}}`，不抛异常打断对话。
