# AGENTS.md — EFW Studio 交接文档

> 给下一位接手的 agent / 开发者。先读本篇，再按需读 `docs/01`–`docs/04` 设计文档。
> 工作目录：`new/efw/`（旧目录 `../../` 的 Studio 已废弃，仅供参考，不要复制旧模型）。

## 0. 一句话定位

用**能一句话读懂的结构**（输入 / 输出 / 信号 / 数据流 / 状态机）描述嵌入式 C 应用，生成可运行、可观测的代码；同一套应用可在**虚拟目标**（电脑上、时间可控）与**真机**（串口/TCP）上用同一套界面调试。业务 C 代码永远是用户的真实文件。

## 1. 给下个 agent 的最重要八条

1. 后端核心已完成：`studio_core/`。UI 七个页面（欢迎/总览/数据流/状态机/通信/代码/调试/生成）全部可用，风格规范见 `docs/05-ui-style.md`。`ui/App.tsx` 的 `READY` 列表控制哪些导航可用。
2. 测试现状：`26` 个后端测试全绿、`11` 条浏览器回归全过（第 6 节问题均已修复，仅作历史记录）。
3. 只用 `uv` 管理 Python：`uv sync`、`uv run python ...`。新增依赖先确认必要（目前唯一第三方是 `pyserial`，用于真机串口）。
4. 模型 id 必须匹配 `^[a-z][a-z0-9_]{0,23}$`；中文只出现在 `label` 里。生成的 C 标识符由 id 直接决定，创建后不可改。
5. 生成器输出只写 `generated/`；`src/`、`board/` 永远由用户拥有，生成/调试构建都不得写入。已有“预览 → token → 提交”与手改冲突保护，不要绕过。
6. 执行计划只有一个事实来源：`studio_core/model.py:analyze()` 产出 plan，`studio_core/codegen.py` 按同一模型生成，UI 只展示，不得自行推导调度。
7. 调试协议是文本命令（主机→目标）+ JSON 行（目标→主机），见 `docs/04`。虚拟目标与真机共用 `studio_core/debug.py` 的会话层，不要为真机另写一套。
8. 根目录残留上一版前端的脚手架（`package.json` / `node_modules` / `tsconfig.json` / `vite.config.ts`，`scripts/` 已空）。重建 UI 时可复用依赖；`package.json` 里的 `main: desktop/main.mjs`、`dev`、`package` 等脚本指向已删除文件，需要重建时才修。

## 2. 已验证可用的能力（不要重复实现）

| 能力 | 入口 | 验证方式 |
| --- | --- | --- |
| 模型校验 + 结构化诊断（`at` / `message` / `hint`） | `model.validate` / `model.analyze` | `tests/test_core.py::ModelTests`（已通过） |
| 四个模板（thermostat / traffic / sampler / blank） | `templates.build` | 全部通过校验；生成的 C 可编译运行 |
| C 代码生成（app.h / app_core.c / app_virtual.c / manifest.json / efw_app.cmake） | `codegen.generate` | 手工端到端：`-DAPP_VIRTUAL` 编译运行，快照/事件/参数整定/force 全部工作 |
| 项目操作（create/open/save/read/write/create 文件、路径防越界、符号链接拒绝） | `project.py` | `ProjectTests` 大部分通过 |
| 生成所有权（预览 Diff、token、备份、冲突阻止、额外文件保留） | `project.preview/commit` | `ProjectTests` 通过 |
| 用户函数缺失/签名不符检测（正则解析 `.c` 定义） | `model.find_definitions` + `analyze` | `ModelTests` 通过 |
| 调试会话：virtual / serial / tcp / replay，录制到 `.efw/runs/*.jsonl` | `debug.py`、`service.debug_start` | 手工运行 thermostat 曲线正常；会话测试因一个 bug 暂挂（见 6.2） |
| JSON Lines 服务 + CLI | `server.py`、`cli.py` | `ServiceTests.test_stdio_server_round_trip` 通过 |
| C 运行库契约 | `tests/msgq_contract.c`、`tests/scheduler_contract.c` | 独立编译运行通过（cc -std=c99 -Wall -Wextra） |

## 3. 目录与职责

```
new/efw/
  docs/01-product.md        五个概念、目录约定、非目标（先读这个）
  docs/02-model.md          efw.json 字段、步骤类型、语义规则
  docs/03-runtime.md        运行时依赖、生成文件、用户函数签名、内存估算
  docs/04-debug-and-api.md  调试帧协议、服务方法表、界面结构
  runtime/                  EFW C 框架副本（唯一沿用旧代码的部分）
    include/efw/core/msgq.h 新增：静态消息队列（容量/丢包统计/ISR 钩子）
    src/core/msgq.c
    src/core/scheduler.c    已修：tick 参数=绝对毫秒（旧版重复累加已删）
    include/efw/core/common.h 已补 <stdbool.h>
  studio_core/
    model.py     模型校验 / 分析 / 函数签名 / 可整定量 / 内存估算
    codegen.py   生成 C 与 manifest（含观测层 APP_OBSERVE_ENABLE、虚拟仿真层）
    templates.py 四个配方 + 骨架生成（stub）
    source_template.py  源码模板标记：fixed_parts / check_edit / protect_function
    fsutil.py    ServiceError / safe_path / atomic_write / digest
    project.py   项目 CRUD、源码读写（含 add_functions）、analyze、stub、预览→提交
    debug.py     传输层（Proc/Serial/Tcp/Replay）、Session、Recorder、虚拟构建
    service.py   调度表（UI 与 CLI 共用）
    server.py    stdio JSON Lines 服务（stdout 只输出协议）
    cli.py       new / check / preview / generate / run
  ui/                       React 界面；见 docs/05-ui-style.md 与第 9 节
  tools/bridge.mjs          开发期 RPC/SSE 桥（Vite 中间件）
  tests/test_core.py         26 个测试（模型 / 生成 / 行为 / 项目 / 调试会话 / 服务）  tests/ui/*.spec.ts         Playwright 回归（9 条）
  tests/*_contract.c         C 契约测试
  pyproject.toml + uv.lock   uv 管理；pyserial
  package.json 等            上一版前端残留（见第 1 节第 8 条）
```

## 4. 常用命令

```bash
cd new/efw
uv sync                                  # 环境（服务只用标准库 + pyserial）
uv run python -m unittest discover -s tests -p 'test_*.py'   # 全部测试
uv run python -m studio_core.cli new /tmp/app --template thermostat
uv run python -m studio_core.cli check /tmp/app
uv run python -m studio_core.cli generate /tmp/app
uv run python -m studio_core.cli run /tmp/app --ms 8000 --set target=45 --fire overheat
# C 契约（无需 cmake）：
cc -std=c99 -Wall -Wextra -Iruntime/include tests/msgq_contract.c runtime/src/core/msgq.c -o /tmp/m && /tmp/m
```

`EFW_CC` 指定编译器；`EFW_RUNTIME` 覆盖 runtime 路径（打包用）。

## 5. 必须遵守的设计不变量

- **五个概念**：输入/输出（硬件）、信号（带类型的共享值）、数据流（周期 + 句子式步骤）、状态机（决定哪些数据流运行）、事件/队列（消息池）。不要向用户暴露“节点/端口/连线/契约/Topic/发布订阅”。
- **文件所有权**：`src/`、`board/` 用户所有；`generated/`、`.efw/` 工具所有。覆盖必须先预览 + token 校验；手改的生成文件视为冲突。
- **生成代码规则**：只依赖 `scheduler.c` / `diagnostic.c` / `msgq.c`；无 malloc；`app_tick(now_ms)` 收绝对毫秒；用户函数签名在 `app.h` 声明，由编译器强制。
- **单事实来源**：调度计划、内存估算、可整定量都出自 `model.analyze`，UI 不得自行推导。
- **可观测性是默认能力**：`manifest.json` + 文本命令协议；`APP_OBSERVE_ENABLE=0` 可整体关闭；关闭时也能编译（当前有告警 bug，见 6.1）。
- **虚拟目标优先**：`board/` 不参与虚拟构建，仿真输入来自模型 `inputs[].sim`（const/sine/ramp/square/noise/follow）；同一份 `src/` 在电脑上可跑。真机只换传输层。
- **错误风格**：后端只抛 `ServiceError(code, message)`；消息要可读、可行动（如“周期 7ms 不是节拍 1ms 的整数倍，改成 8”）。
- **路径安全**：一切文件操作走 `fsutil.safe_path` / `source_path`；拒绝 `..`、绝对路径、反斜杠、符号链接。

## 6. 当前失败清单（含根因与建议修法）

运行：`uv run python -m unittest discover -s tests -p 'test_*.py'`

### 6.1 生成代码的未使用符号告警（6 个失败，属代码生成卫生问题）

症状（`-Wall -Wextra -Werror` 下编译失败）：

- `traffic`：`obs_i` 未使用（该配方没有 int 信号）。
- `blank`：`obs_flow`、`record_trans`、`obs_i` 未使用（无数据流/无状态机/无 int 信号）。
- `APP_OBSERVE_ENABLE=0` 时：`g_params`、`g_tsigs`、`g_m_light_trs`、`g_hist_r` 未使用。
- `blank` 项目 `-Werror` 下同类告警。

根因：观测层辅助函数与参数表是无条件生成的 `static`，但只在特定模型/观测开启时被引用。

建议修法（二选一，推荐 A）：

- A. 在 `codegen.gen_core` 头部输出可移植的未使用属性宏，并给观测辅助函数与表加注解：
  ```c
  #if defined(__GNUC__)
  #define APP_MAYBE_UNUSED __attribute__((unused))
  #else
  #define APP_MAYBE_UNUSED
  #endif
  ```
  注解对象：`obs_u/obs_i/obs_f/obs_flow/obs_queue/obs_ack/obs_hello/obs_snapshot/obs_params/record_trans`、`g_params`、`g_tsigs`、`g_m_*_trs`、`g_hist_w/g_hist_r`、`g_mach_*` 表。MSVC 无此告警级别时可留空。
- B. 按需生成：`obs_i` 仅当存在 int 信号；`obs_flow` 仅当有数据流；`record_trans`/历史环/`g_m_*_trs` 整体包进 `#if APP_OBSERVE_ENABLE`，`m_*_goto` 里的 `record_trans` 调用同样包 `#if`；`g_params/g_tsigs` 包进观测块。更省 Flash，但 `gen_core` 分支变多。
- 修完后 `test_observe_can_be_compiled_out`、`test_virtual_and_real_target_builds_are_warning_free` 应全绿。

### 6.2 `Recorder.__init__` 顺序 bug（1 个 error）

`studio_core/debug.py`：`Recorder.__init__` 先调用 `self.write(...)`，但 `self.last_flush` 在 `write()` 里被读取、之后才赋值 → `AttributeError`。
修法：在调用 `write` 前先 `self.last_flush = time.monotonic()`（或 `0.0`）。修好后 `test_virtual_session_record_and_replay` 应能跑通。

### 6.3 blank 项目没有 `src/` 目录（1 个 error，产品性问题）

`project.create_project` 只写入模板里的文件，`blank` 模板没有 src 文件，因此 `src/` 不存在；测试里对 `src/link` 建符号链接报 `FileNotFoundError`。
修法（推荐产品侧）：`create_project` 在写文件前 `mkdir` 出 `src/` 与 `board/`（可各放一个 `.gitkeep`），保证界面上“新建源码/回调骨架”总有落点，也符合 `docs/01` 的目录约定。修完后 `test_paths_are_confined` 通过。

### 6.4 两个测试预期需要修正（代码本身正确）

- `test_thermostat_closes_the_loop_then_trips_and_recovers`：trip 发生在约 9.9s（target=90、follow 仿真 tau=4000ms、75°C 阈值），12s 的窗口不足以等到 `recover`（+4000ms）。把运行时长改为 `18000`（或提高 `gain`/降低阈值）即可；不要改状态机代码。
- `test_traffic_light_is_pure_state_machine`：`after_ms 3000` 在 `t=3000` 正好触发（初始状态 entered at 0），预期应改为 `(3000, 'green'), (6000, 'yellow')`，不是 3001/6002。

### 6.5 其它小问题（非失败）

- 测试有 `ResourceWarning: unclosed file`：`ProcTransport.close` 只关了 stdin 子进程，建议同时 `self.p.stdout.close()` / `self.p.stderr.close()`；测试的 `run_virtual` 也应使用 `with` 或 try/finally 关闭。保持测试输出干净，便于将来用 `-W error`。
- `efw.h` 未聚合 `core/msgq.h`，`efw_all.c` 未包含 `core/msgq.c`。生成应用直接包含/编译这两个文件，所以现在不影响；若要让 Keil 单编译单元用户也能用消息队列，需把 `msgq.c` 加进 `efw_all.c`（注意 `same_name` 重命名惯例）并在 `efw.h` 聚合。做出决定后同步 `docs/03`。
- `pyproject.toml` 里的 `packaging` 依赖组（PyInstaller）保留用于将来打包独立服务。

## 7. 下一步路线（按优先级）

1. **让测试全绿**：按第 6 节修 6.1–6.4（预计 1–2 小时），然后补一个“真机编译”冒烟测试：用模板生成 → 编译 `app_core.c` + `src/*.c` + `board/io.c` + `board/observe_port.c`（不含 main）验证可链接为一个静态库。
2. **重建 UI（主要工作）**：React + TypeScript + Vite；Electron 壳。页面：总览 / 数据流 / 状态机 / 通信 / 代码 / 调试 / 生成。设计语言见 `docs/04`（示波器式：中性石墨底 + 单一钴蓝、绿/黄/红只表示状态、等宽字体显示标识符、明暗跟随系统、1366×768 无横向滚动）。
   - 关键交互：步骤用“句子”编辑（读/滤波/PID/写），拖动排序；状态机用状态图 + “当…时从…到…”；通信页表格显示容量/内存；代码页 Monaco + 一键创建缺失函数；调试页曲线/任务统计/状态高亮/参数整定；生成页逐文件 Diff。
   - 桥接：Electron 主进程以 stdio 启动 `python -m studio_core.server`，把 `debug.frames` / `debug.status` 通知转 IPC；渲染进程只经受限 preload 调白名单方法。参考已废弃的旧实现思路可以，但**不要**复制旧节点画布模型。
3. **调试体验闭环**：虚拟目标播放/暂停/单步/变速已在服务端实现；UI 需要“运行”按钮直达虚拟调试、曲线叠加、转换历史时间线、录制列表与回放。
4. **真机链路**：串口（pyserial）与 TCP 传输已实现但未实测；用回环/伪终端补集成测试；真机验证 hash 不一致提示、`app_observe_write/read` 模板。
5. **打包**：`uv run --group packaging python -m PyInstaller` 打独立服务（保留旧脚本思路即可），Electron Builder 出安装包；离线要求：Monaco worker 本地、无 CDN。
6. **可选增强**：多速率独立采样（当前是路径级 max 周期）、数据流依赖图自动布局、`signal` 条件转换去抖（防两状态同时为真来回跳）、模型版本迁移。

## 8. 验证习惯（要求）

- 任何生成器改动后必须跑：`unittest` 全套 + 手工 `cli run` 一次（确认快照/事件正确）。
- 新增 C 特性必须带主机契约测试（参照 `tests/msgq_contract.c`），并用 `-Wall -Wextra -Werror` 编译通过。
- 行为断言优先于字符串断言：优先用 `cli run`/调试会话的快照与事件验证，不要断言生成 C 的文本格式（除非是接口/宏名）。
- 每次改动更新 `docs/04` 的协议表与 `docs/02` 的字段表（单一事实来源）。

## 9. UI 开发环境（已验证）

- 本机 WSL 没有 Linux 版 node，而 `node_modules` 是 Linux 二进制。临时方案：下载 Linux node 到 `/tmp/opencode/node`，`export PATH=/tmp/opencode/node/bin:$PATH`，再 `node node_modules/typescript/bin/tsc --noEmit`、`node node_modules/vite/bin/vite.js`（开发）/ `... build`。
- 开发时 `tools/bridge.mjs`（Vite 中间件）用 `uv run python -m studio_core.server` 提供 `POST /rpc` 与 `GET /events`（SSE）；界面只经 `ui/rpc.ts` 通信。
- 状态机页已完成只读浏览：切换状态机、状态图、详情、顺序转换规则、路径高亮。编辑与实时运行状态尚未接入。
- 通信页已完成：分类、搜索、配置表、信号/事件引用、队列策略、类别合计内存与诊断。引用和内存来自后端分析，无前端估算。
- 代码页已完成：本地按需加载 Monaco 与 worker、源码编辑/保存、新文件草稿、缺失函数骨架、revision 冲突提示。代码页保持挂载以保留跨页面草稿；草稿只在内存，尚无崩溃恢复。函数骨架需用户检查后保存。
- 源码模板已实现（`studio_core/source_template.py`）：工具创建的 `.c` 用 `/* EFW USER BEGIN <name> */` … `END` 标记用户逻辑区，标记外固定只读。代码页在标记外拦截按键/粘贴（`ui/template.ts` 与 `ui/components/SourceEditor.tsx`），`file.write` 用 `check_edit` 再校验（错误码 `TEMPLATE`），`add_functions` 负责追加带标记的骨架。无标记的旧文件不受限。
- `efw.json` 已列入代码页“应用配置”：编辑后保存走 `project.save`，各页面按新模型刷新。模型配置只以 `efw.json` 为准，不写进 `.c`。
- 调试页已完成：顶栏“运行”一键启动虚拟目标（有未保存源码草稿或模型错误时禁用，见 `ui/store.tsx` 的 `sourcesDirty`）；播放/暂停/单步/速度/重新开始/停止；曲线、任务统计、状态机、参数整定、事件/强制输入、队列；`.efw/runs/` 列表与回放。通知经 `onEvent` 归约（`ui/debug.ts`），帧字段见 `docs/04`。
- codegen 变更注意：可整定信号经 `app_tsig_t`（含 `get`）在 `params` 帧回发；表尾哨兵是 5 个字段。`build_virtual` 缓存键只看模型哈希与用户源码，改 `codegen.py` 后旧缓存不会自动失效，手工删 `.efw/build/` 即可。
- 生成页已完成：自动预览、逐文件 Diff（`ui/components/DiffView.tsx`，与编辑器共用 `ui/monaco.ts`）、token 提交、冲突阻止与恢复。
- 下一步 UI：真机串口/TCP 实测（回环/伪终端集成测试、hash 不一致提示）、Electron 壳与打包（`desktop/` 不存在，只有浏览器开发环境）、页面内模型编辑（当前只能手改 efw.json）。
- 浏览器回归：`node node_modules/@playwright/test/cli.js test`，由 `playwright.config.ts` 自动启动 Vite，测试创建临时真实项目并在结束后清理。当前 11 条测试覆盖状态机、通信页、代码页、调试页（草稿门禁、整定往返、事件触发、回放）与生成页（预览、提交、冲突恢复）。截图保存在忽略的 `test-results/`。
- 后端 `unittest` 26 条全绿，含 `ProjectTests.test_template_regions_are_protected`、`test_missing_function_is_added_with_protected_template` 与 `BehaviourTests.test_tunable_signal_value_is_echoed_in_params`。
- Vite 7 要求 Node 20.19+ 或 22.12+；当前临时 Node 22.11 可完成构建与测试但有版本提示，正式开发环境应升级到满足要求的版本。
