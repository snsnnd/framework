# AGENTS.md — EFW Studio 交接文档

> 给下一位接手的 agent / 开发者。先读本篇，再按需读 `docs/01`–`docs/05` 设计文档。
> 工作目录：`new/efw/`（旧目录 `../../` 的 Studio 已废弃，仅供参考，不要复制旧模型）。
> 当前工作已提交 git：分支 `tmp/new`，commit `2cb4a74`（"Add new EFW Studio: model, codegen, virtual debug and web UI"）。仓库根目录还有与本工作室无关的历史改动，未触碰。

## 0. 一句话定位

用**能一句话读懂的结构**（输入 / 输出 / 信号 / 数据流 / 状态机）描述嵌入式 C 应用，生成可运行、可观测的代码；同一套应用可在**虚拟目标**（电脑上、时间可控）与**真机**（串口/TCP）上用同一套界面调试。业务 C 代码永远是用户的真实文件。

## 1. 给下个 agent 的最重要八条

1. 端到端可用：`studio_core/` + `ui/` 七个导航页面（总览 / 数据流 / 状态机 / 通信 / 代码 / 调试 / 生成）全部实现；风格规范 `docs/05-ui-style.md`。**下一步主线是“页面内模型编辑”**（见第 7 节），即把浏览页（数据流 / 状态机 / 通信）变成结构化编辑器。
2. 测试：`32` 个后端测试全绿、`22` 条浏览器回归全过。任何改动后按第 8 节跑全套。
3. 只用 `uv` 管理 Python：`uv sync`、`uv run python ...`。唯一第三方依赖是 `pyserial`（真机串口）。
4. 模型 id 必须匹配 `^[a-z][a-z0-9_]{0,23}$`；中文只出现在 `label` 里。生成的 C 标识符由 id 直接决定，创建后不可改。
5. 生成器输出只写 `generated/`；`src/`、`board/` 永远由用户拥有。已有“预览 → token → 提交”与手改冲突保护，不要绕过。
6. 执行计划只有一个事实来源：`studio_core/model.py:analyze()` 产出 plan，`studio_core/codegen.py` 按同一模型生成，UI 只展示，不得自行推导调度、内存或关系。
7. 调试协议是文本命令（主机→目标）+ JSON 行（目标→主机），见 `docs/04`。虚拟目标与真机共用 `studio_core/debug.py` 的会话层，不要为真机另写一套。
8. 前端不再是脚手架：`ui/` 是正式界面；但 `package.json` 的 `main: desktop/main.mjs`、`start`、`test:bridge`、`package:backend` 仍指向不存在的 `desktop/`、`scripts/`，做 Electron 壳与打包时再修（`scripts/` 目录为空）。

## 2. 已验证可用的能力（不要重复实现）

| 能力 | 入口 | 验证方式 |
| --- | --- | --- |
| 模型校验 + 结构化诊断（`at` / `message` / `hint`） | `model.validate` / `model.analyze` | `ModelTests` 通过 |
| 输入仿真字段表（`sim_specs`，含 `follow` 的输出选择） | `analyze` | `ModelTests.test_sim_specs_cover_every_sim_kind` |
| 模型哈希对整值浮点写法稳定（JS 传输 `0.0`→`0` 不改哈希） | `model.canonical` | `ModelTests.test_hash_ignores_integral_float_spelling` |
| 模型哈希对整值浮点写法稳定（JS 传输 `0.0`→`0` 不改哈希） | `model.canonical` | `ModelTests.test_hash_ignores_integral_float_spelling` |
| 步骤字段表（供界面渲染编辑表单，含读取/写入步骤的 `input`/`output`） | `analyze` 返回 `step_specs` | 数据流页回归 + `test_step_specs_expose_hardware_points_and_usage_tracks_them` |
| 四个模板（thermostat / traffic / sampler / blank） | `templates.build` | 全部通过校验；生成的 C 可编译运行 |
| C 代码生成（app.h / app_core.c / app_virtual.c / manifest.json / efw_app.cmake） | `codegen.generate` | `GeneratedCTests`：虚拟与真机目标在 `-Wall -Wextra -Werror` 下零告警 |
| 可整定信号回显（`app_tsig_t` 含 getter，`params` 帧包含信号） | `codegen` + `debug` | `BehaviourTests.test_tunable_signal_value_is_echoed_in_params` |
| 项目操作（CRUD、源码读写、路径防越界、符号链接拒绝） | `project.py` | `ProjectTests` 通过 |
| 生成所有权（预览 Diff、token、备份、冲突阻止、额外文件保留） | `project.preview/commit` | `ProjectTests` + 生成页浏览器回归 |
| 源码模板保护（`EFW USER BEGIN/END`，标记外只读） | `source_template.py` + `file.write` | `test_template_regions_are_protected`、`test_missing_function_is_added_with_protected_template`、代码页回归 |
| 用户函数缺失/签名不符检测 | `model.find_definitions` + `analyze` | `ModelTests` 通过 |
| 调试会话：virtual / serial / tcp / replay，录制到 `.efw/runs/*.jsonl` | `debug.py`、`service.debug_start` | `SessionTests`（录制回放、live/hash 不一致、构建错误）+ 调试页回归 |
| 真机链路实测：TCP 回环监听器、串口伪终端（PTY），不依赖硬件 | `tests/test_core.py` 的 `TcpBoard`/`PtyBoard` | `SessionTests.test_tcp_target_talks_to_a_real_socket` / `test_serial_target_talks_over_a_pseudo_terminal` / `test_serial_and_tcp_report_unreachable_endpoints` |
| 虚拟目标构建缓存 | `debug.build_virtual`（`.efw/build/<key>/`） | 键 = 模型哈希 + 用户源码摘要；改 codegen 后手工删缓存 |
| JSON Lines 服务 + CLI | `server.py`、`cli.py` | `ServiceTests` 通过 |
| C 运行库契约 | `tests/msgq_contract.c`、`tests/scheduler_contract.c` | 编译运行通过（cc -std=c99 -Wall -Wextra） |
| React UI + 开发桥 | `ui/`、`tools/bridge.mjs` | 22 条 Playwright 回归；Monaco/worker 本地打包、无 CDN |

## 3. 目录与职责

```
new/efw/
  docs/01-product.md        五个概念、目录约定、非目标（先读这个）
  docs/02-model.md          efw.json 字段、步骤类型、语义规则、通信页消费字段
  docs/03-runtime.md        运行时依赖、生成文件、用户函数签名、源码模板、内存估算
  docs/04-debug-and-api.md  调试帧协议、服务方法表、各界面已实现的行为
  docs/05-ui-style.md       界面风格、token、每页交互约定、代码组织
  runtime/                  EFW C 框架副本（唯一沿用旧代码的部分）
    include/efw/core/msgq.h 静态消息队列（容量/丢包统计/ISR 钩子）
    src/core/msgq.c
    src/core/scheduler.c    tick 参数=绝对毫秒
    include/efw/core/common.h 已补 <stdbool.h>
  studio_core/
    model.py     模型校验 / 分析 / 函数签名 / 可整定量 / 内存估算
    codegen.py   生成 C 与 manifest（观测层 APP_OBSERVE_ENABLE、虚拟仿真层）
    templates.py 四个配方 + 带模板标记的骨架生成
    source_template.py  fixed_parts / check_edit / protect_function
    fsutil.py    ServiceError / safe_path / atomic_write / digest
    project.py   项目 CRUD、源码读写（含 add_functions）、analyze、stub、预览→提交
    debug.py     传输层（Proc/Serial/Tcp/Replay）、Session、Recorder、虚拟构建
    service.py   调度表（UI 与 CLI 共用）
    server.py    stdio JSON Lines 服务（stdout 只输出协议）
    cli.py       new / check / preview / generate / run
  ui/
    App.tsx / main.tsx / store.tsx / rpc.ts / types.ts
    debug.ts     调试通知归约（帧 → 界面状态）
    template.ts  源码模板标记解析（与后端同规则）
    monaco.ts    编辑器与 Diff 共用的 Monaco 初始化
    model-edit.ts 页面内模型编辑：id 生成/校验、引用查询、增删改模型项（flows/machines 同样适用）
    focus.ts       诊断 `at` → 修复入口（页面 + 对象）；总览页点击与目标页定位都用它
    components/CellInput.tsx 行内输入（失焦提交、被拒回滚）
    pages/       七个页面，每页一个文件
    components/  SourceEditor / CurveChart / DiffView / CellInput
    styles/      tokens.css（唯一颜色来源）+ app.css
  tools/bridge.mjs          开发期 RPC/SSE 桥（Vite 中间件）
  tests/test_core.py         32 个测试（模型 / 生成 / 行为 / 项目 / 调试会话 / 真机链路 / 服务）
  tests/ui/*.spec.ts         Playwright 回归（22 条）
  tests/*_contract.c         C 契约测试
  playwright.config.ts       自动启动 Vite；测试自建临时项目并清理
  pyproject.toml + uv.lock   uv 管理；pyserial；packaging 组留给 PyInstaller
  package.json               React/Vite/Monaco/Playwright 依赖；含少量待修脚本（见第 1 节第 8 条）
```

## 4. 常用命令

```bash
cd new/efw
uv sync
uv run python -m unittest discover -s tests -p 'test_*.py'   # 全部后端测试
uv run python -m studio_core.cli new /tmp/app --template thermostat
uv run python -m studio_core.cli check /tmp/app
uv run python -m studio_core.cli generate /tmp/app
uv run python -m studio_core.cli run /tmp/app --ms 8000 --set target=45 --fire overheat
# C 契约（无需 cmake）：
cc -std=c99 -Wall -Wextra -Iruntime/include tests/msgq_contract.c runtime/src/core/msgq.c -o /tmp/m && /tmp/m

# UI（本机 WSL 没有 Linux 版 node，先准备临时 node，见第 9 节）
export PATH=/tmp/opencode/node/bin:$PATH
node node_modules/typescript/bin/tsc --noEmit          # 类型检查
node node_modules/vite/bin/vite.js                     # 开发服务器 127.0.0.1:5173
node node_modules/@playwright/test/cli.js test          # 浏览器回归（自动起 Vite）
node node_modules/vite/bin/vite.js build               # 生产构建
```

`EFW_CC` 指定编译器；`EFW_RUNTIME` 覆盖 runtime 路径（打包用）。

## 5. 必须遵守的设计不变量

- **五个概念**：输入/输出（硬件）、信号（带类型的共享值）、数据流（周期 + 句子式步骤）、状态机（决定哪些数据流运行）、事件/队列（消息池）。不要向用户暴露“节点/端口/连线/契约/Topic/发布订阅”。
- **文件所有权**：`src/`、`board/` 用户所有；`generated/`、`.efw/` 工具所有。覆盖必须先预览 + token 校验；手改的生成文件视为冲突。
- **源码模板**：工具创建/补充的 `.c` 只在 `EFW USER BEGIN/END` 内可编辑；没有标记的既有文件不受限；不要给用户已有文件擅自加标记。前端（`ui/template.ts`）与 `file.write`（`check_edit`）双重校验，错误码 `TEMPLATE`。
- **生成代码规则**：只依赖 `scheduler.c` / `diagnostic.c` / `msgq.c`；无 malloc；`app_tick(now_ms)` 收绝对毫秒；用户函数签名在 `app.h` 声明，由编译器强制。
- **单事实来源**：调度计划、内存估算、可整定量、引用关系都出自 `model.analyze`，UI 不得自行推导。
- **可观测性是默认能力**：`manifest.json` + 文本命令协议；`APP_OBSERVE_ENABLE=0` 可整体关闭且零告警编译。
- **虚拟目标优先**：`board/` 不参与虚拟构建，仿真输入来自模型 `inputs[].sim`（const/sine/ramp/square/noise/follow）；同一份 `src/` 在电脑上可跑。真机只换传输层。
- **契约同步**：改服务方法/帧字段时同步 `docs/04`、`ui/types.ts`、`ui/debug.ts`；改模型字段时同步 `docs/02`。
- **错误风格**：后端只抛 `ServiceError(code, message)`；消息要可读、可行动（如“周期 7ms 不是节拍 1ms 的整数倍，改成 8”）。
- **路径安全**：一切文件操作走 `fsutil.safe_path` / `source_path`；拒绝 `..`、绝对路径、反斜杠、符号链接。

## 6. 历史问题与修复记录（全部已修复，仅作参考）

### 6.1 生成代码未使用符号告警（已修）

采用方案 A：`codegen.gen_core` 输出 `APP_MAYBE_UNUSED`（GNU 为 `__attribute__((unused))`），观测辅助函数与 `g_params` / `g_tsigs` / `g_m_*_trs` / `g_hist_*` 全部注解；虚拟层 `sim_rand` 单独加 `__attribute__((unused))`。现在 `test_observe_can_be_compiled_out` 与 `test_virtual_and_real_target_builds_are_warning_free` 全绿。

### 6.2 Recorder 初始化顺序（已修）

`debug.py:Recorder.__init__` 在 `write()` 之前先设 `self.last_flush`。

### 6.3 blank 项目缺 `src/`（已修）

`project.create_project` 先建 `src/` 与 `board/` 目录。

### 6.4 两个测试预期（已修）

thermostat 运行窗口 12s→18s；traffic 转换时刻 3001/6002→3000/6000，黄灯窗口改 6500ms。

### 6.5 仍未处理的小问题

- `efw.h` 未聚合 `core/msgq.h`，`efw_all.c` 未包含 `core/msgq.c`；Keil 单编译单元用户暂时用不了消息队列。生成应用不受影响。
- `pyproject.toml` 的 `packaging` 依赖组保留给将来的 PyInstaller 打包，尚未使用。
- 源码草稿只在内存：刷新/崩溃会丢；顶栏没有保存/撤销/重做（代码页的“保存文件”是唯一写盘入口）。

### 6.6 `debug.stop` 在 TCP 上永久卡死（已修）

`TcpTransport` 用 `sock.makefile("r")` 读，停止时先 `self.f.close()`——而 `close()` 会等读到 EOF，真机不会主动发 EOF，于是点“停止”整个界面挂住（连同 Python 服务）。改成和 `SerialTransport` 一样的 `recv` + 超时循环（`settimeout(0.2)`），`close()` 只做 `shutdown` + `close`。**写新传输时永远不要用阻塞式 `makefile().readline()`。**

这个缺陷是补真机链路集成测试时抓到的（`TcpBoard` 停止后卡住），单靠 `FakeTransport` 永远不会暴露。

顺带清掉两个 `ResourceWarning`：`list_runs` 的 `p.open(...).readline()` 漏了句柄（UI 会反复调 `debug.runs`）；`ProcTransport.close` 没关 `stdout/stderr/stdin`。现在 `python -W error::ResourceWarning -m unittest` 干净。

## 7. 下一步路线（按优先级）

### 7.1 页面内模型编辑（主线，通信页已完成）

已落地的基础设施（数据流、状态机页直接复用）：

- `store.updateModel(mutate)`：校验 → `project.save`（带 revision）→ 就地刷新；失败返回错误诊断并保留原模型。编辑在 store 内**串行排队**，连续修改共用最新 revision。
- `ui/model-edit.ts`：id 生成与校验、引用查询（来自 `analyze.usage`，不在前端推导）、`patchItem/appendItem/removeItem`、诊断路径前缀（信号是 `signals/<id>`，事件/队列是 `comms/<kind>/<id>`）。
- `ui/components/CellInput.tsx`：行内输入（文本/数字/下拉），失焦或选择时提交，外部值变化或提交被拒（`resetKey`）时回滚；值为空的下拉带“选择…”占位项。
- 通信页已可增删改信号、输入、输出、事件、队列；删除前查引用，被后端拒绝的编辑回滚并给诊断。保存期间输入框仍可编辑（store 串行排队），按钮才禁用。
- 踩过的坑：桥接层 `JSON.stringify` 会把 `0.0` 变成 `0`，因此 `model.canonical` 统一把整值浮点归一为整数，否则前端与后端算出的 `model_hash` 不一致（会误报“模型已修改”）。

数据流页已完成：周期、步骤字段（下拉 + 数值，由后端 `step_specs` 驱动）、上移/下移排序、增删步骤、增删数据流（受状态机控制的不给删）。状态机页已完成：状态名/run 复选/set 增删/钩子/设为初始/删除（有转换引用时拒绝）、转换增删与上下排序、起点终点与四种触发条件。通信页补上了输入/输出（此前 UI 里完全没有编辑器）：名称/类型/单位、输入的虚拟仿真（字段表来自后端 `sim_specs`，切换类型时预填默认值），详情区列出需要用户实现的 C 函数。

顺带修掉的三个真实缺陷：`step_specs` 从不为 `read` 产出 `input`、为 `write` 产出 `output`（数据流页因此**无法选择硬件输入输出**，新增步骤里选输入的分支是死代码）；`analyze.usage` 缺 `inputs`/`outputs`，删除保护形同虚设；桥接层把无法解析的 stdout 行静默丢弃（丢掉响应会让请求永不返回）。`ui/rpc.ts` 另加了 120 秒超时与网络错误码，避免界面永远停在“保存中”。

总览页“下一步”也已变成可点击的修复入口：`ui/focus.ts` 按诊断 `at` 前缀映射到页面与对象（缺失的 C 函数按 `file` 跳代码页），`App` 持有带 token 的 `repair`，四个目标页各用一次 `useEffect` 定位并选中；定位只改前端状态，不发 RPC。

调试页真机目标也已完成：串口设备+波特率、TCP 主机+端口，复用 `debug.py` 的 `Serial`/`Tcp` 传输；`store.target` 是唯一的目标选择，顶栏“运行”与启动按钮共用；`targetProblem` 在参数不全时禁用按钮并说明缺什么；顺带修掉“启动失败没有 session → 错误无处可看”的缺陷。

真机链路也已用回环监听器与伪终端（PTY）实测，`debug.stop` 的 TCP 卡死问题就是被这组测试抓出来的（见 6.6）。

下一步：

- 硬件在环验证（可选）：真板子上跑 `board/observe_port.c`，看串口丢帧与延迟。
- 之后是 Electron 壳与打包。

### 7.2 真机链路

`serial` / `tcp` 传输已用**真实 socket 与伪终端**测过（见第 2 节表格），不需要硬件就能验证握手、收帧、发命令、哈希不符提醒、录制与停止。仍然缺的只有硬件在环：真机串口吞吐下的丢帧表现、以及把 `board/observe_port.c` 烧进板子后的端到端。写新的传输时照 `TcpBoard`/`PtyBoard` 的做法加测试，别再只靠 `FakeTransport`。

### 7.3 Electron 壳与打包

`desktop/` 不存在，目前只有浏览器开发环境。主进程以 stdio 启动 `python -m studio_core.server`（或 PyInstaller 产物），把 `debug.frames` / `debug.status` 转 IPC；渲染进程只经受限 preload 调白名单方法；输出现已满足离线要求（Monaco worker 本地、无 CDN）。打包：`uv run --group packaging python -m PyInstaller` + electron-builder，修好 `package.json` 中的 `main`/`start`/`package:backend`。

### 7.4 可选增强

多速率独立采样（当前路径级 max 周期）、`signal` 条件转换去抖、数据流依赖图自动布局、模型版本迁移、撤销/重做、源码草稿持久化（localStorage 或 `.efw/`）。

## 8. 验证习惯（要求）

- 任何生成器改动后必须跑：`unittest` 全套 + 手工 `cli run` 一次（确认快照/事件/参数回显正确）。
- 新增 C 特性必须带主机契约测试（参照 `tests/msgq_contract.c`），并用 `-Wall -Wextra -Werror` 编译通过。
- 行为断言优先于字符串断言：优先用 `cli run` / 调试会话的快照与事件验证，不要断言生成 C 的文本格式（除非是接口/宏名）。
- UI 改动跑 `tsc --noEmit` + `@playwright/test` 全套；测试定位用稳定 id（`data-id`/`data-key`），不要用中文展示文案。
- 每次改动更新对应文档：模型字段 → `docs/02`；协议与界面行为 → `docs/04`；风格与交互约定 → `docs/05`；本文件的第 6/7/9 节随状态更新。

## 9. UI 开发现状与环境（已验证）

### 运行环境

- 本机 WSL 没有 Linux 版 node，`node_modules` 是 Linux 二进制。临时方案：下载 Linux node 到 `/tmp/opencode/node`，`export PATH=/tmp/opencode/node/bin:$PATH`，再执行第 4 节的 UI 命令。
- Vite 7 要求 Node 20.19+ / 22.12+；当前临时 Node 22.11 可完成构建与测试但有版本提示，正式环境应升级。
- 开发时 `tools/bridge.mjs`（Vite 中间件）用 `uv run python -m studio_core.server` 提供 `POST /rpc` 与 `GET /events`（SSE）；界面只经 `ui/rpc.ts` 通信。

### 页面现状

- 总览：只读统计（结构、执行计划、内存）+ “下一步”修复入口（按诊断 `at` 跳到对应页并选中对象，见 `ui/focus.ts`）。数据流页与状态机页：均可编辑（周期/步骤/排序/增删；状态/初始状态/run/set/钩子/转换条件/排序）。
- 通信页：**行内编辑**（信号/输入/输出/事件/队列的增删改，删除前查 `usage` 引用，被拒编辑回滚并给诊断；输入可配虚拟仿真，字段表来自后端 `sim_specs`）。
- 代码页：Monaco 按需加载，模板标记外只读（按键/粘贴拦截 + 保存端 `TEMPLATE` 校验）；新文件与函数模板先进草稿，保存后重新分析；`efw.json` 作为“应用配置”可整体编辑，保存后全页刷新。页面常驻以保留跨页草稿。
- 调试页：启动卡片选虚拟目标 / 串口（设备+波特率）/ TCP（主机+端口），目标存 store 里，顶栏“运行”共用同一目标（参数不全时按钮禁用并说明缺什么）；启动失败的错误显示在启动卡上；播放/暂停/单步 500 ms/速度/重新开始/停止；曲线、任务统计、状态机、参数整定、事件/强制输入、队列、录制列表与回放。通知经 `ui/debug.ts` 归约。
- 生成页：自动预览、逐文件 Monaco Diff、token 提交、冲突阻止与恢复。
- 顶栏：项目名/路径、重新载入、运行（运行中变停止）；状态栏：诊断计数、目标连接占位、模型 hash。撤销/重做与“保存”按钮不存在。

### 测试现状

- 后端 `unittest` 32 条全绿；浏览器 `@playwright/test` 22 条全绿（状态机含编辑、通信含输入输出、数据流、代码、调试含真机目标、生成页、总览修复入口）。
- 测试创建临时真实项目（`/tmp`），结束后清理；截图保存在被忽略的 `test-results/`。
- 全局 `expect.timeout` 放宽到 20 秒（本机负载高时保存一趟要好几秒）；Monaco 按需加载，输入要整段重写并确认草稿变“未保存”，否则首次输入可能被丢弃。
- 注意：`build_virtual` 缓存键只看模型哈希与用户源码，修改 `codegen.py` 后旧缓存不会失效，开发时手工删 `.efw/build/`。
