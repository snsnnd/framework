# 04 调试协议、服务接口与界面

## 目标 → 主机（每行一个 JSON，`\n` 结尾；非 `{` 开头的行忽略）

| `e` | 含义 |
| --- | --- |
| `hello` | `hash` 模型哈希、`name`、`tick`、`v` 协议版本 |
| `snap` | 快照：`t` 毫秒；`s` 信号；`o` 输出最近值；`f` 数据流统计 `{on,run,miss,over,err,late,max_late,us,max_us}`；`q` 队列统计（含 `events`）；`m` 状态机 `{s,since}`；`forced` 被强制的输入 |
| `trans` | 状态转换 `{t,m,from,to,by}`，`by` 为转换 id |
| `params` | 全部参数当前值：数据流步骤参数（`flow.step.field`）和可整定信号（信号 id）都包含在内 |
| `ack` / `err` | 命令回应 `{c,msg?}` |
| `idle` | 仅虚拟目标：一次 `run` 完成 `{t}` |

## 主机 → 目标（文本，一行一条）

`hello` · `dump` · `rate <ms>` · `set <key> <num>`（参数键 `flow.step.field` 或可整定信号 id，成功后会回发 `params`）· `force <input> <num>` · `release <input>` · `fire <event>` · `push <queue> <num>` · `pause <flow>` · `resume <flow>` · `state <machine> <state>`；虚拟目标另有 `run <ms>`、`quit`。

## 调试会话（服务）

目标类型：`virtual`（生成并编译主机进程，逐步推进仿真时间）· `serial`（`pyserial`）· `tcp` · `replay`（读取 `.efw/runs/*.jsonl`）。所有帧写入 `.efw/runs/`，首行含模型哈希，回放时与当前模型比对。

## 服务协议（JSON Lines over stdio）

请求 `{"id","method","params"}`；响应 `{"id","result"}` / `{"id","error":{"code","message"}}`；通知（无 id）`{"event":"debug.frames","session","frames":[...]}`、`{"event":"debug.status","session","state","t","speed","message","warning?","end?"}`（`end` 仅回放）。

| 方法 | 作用 |
| --- | --- |
| `system.info` / `templates.list` | 服务版本与四个新建模板 |
| `project.create/open/save/analyze` | 项目与模型；`create` 参数 `{path,name,template}`；`save` 使用 revision 防冲突 |
| `analyze` 附加返回 | `sim_specs`（输入仿真字段表）、`usage.inputs/outputs`（被读取/写入步骤引用）、`functions[].owner`（函数归属的模型路径） |
| `project.stub` | 为缺失函数生成骨架 |
| `file.read/write/create` | 用户源码（`src/`、`board/`） |
| `generate.preview/commit` | 逐文件 Diff → token → 写入 `generated/` |
| `debug.start` | `{path,target,model?}` → `{session,kind,manifest,state}`；目标 `{kind:virtual\|serial\|tcp\|replay, ...}`；模型有错误抛 `VALIDATION` |
| `debug.control` | `{session,action,value?}`：`play` · `pause` · `step`（仅虚拟且已暂停，`value` 为前进毫秒）· `speed`（1.0 正常，0 为最快）· `reset`（重建会话） |
| `debug.send/stop`、`debug.runs` | 文本命令、结束会话、列出 `.efw/runs/` 记录 |

状态机只读页消费 `project.open` 的 `model.machines` 与 `project.analyze` 的诊断；未增加协议方法或通知。切换状态机、选择状态、选择转换均为本地浏览操作，不调用 `debug.send`。

通信页消费同一模型与 `project.analyze.usage/memory`，分类、搜索和选择详情均为本地操作。

### 页面内模型编辑

数据流、状态机、通信页可以直接改模型，统一走 `store.updateModel(mutate)`：`structuredClone` 当前模型 → `mutate` 返回新模型 → `project.analyze` 校验（**不通过则不写盘**，返回错误诊断）→ `project.save`（带 revision）→ 就地更新项目与分析结果。所有编辑串行执行（store 内一条 promise 链），连续快速修改共用最新 revision，不会互相冲突。

- 新增对象时校验 id：`^[a-z][a-z0-9_]{0,23}$` 且同类唯一（`ui/model-edit.ts` 的 `idProblem`/`suggestId`）；id 创建后不可修改，界面里只读展示。
- 删除前用 `project.analyze` 的 `usage` 判断引用：信号看 `writers/readers`，事件看 `emitters/consumers`，输入/输出看 `steps`（被“读取”/“写入”步骤引用）；有引用时拒绝删除并列出位置。队列没有引用分析，允许删除但提示用户 C 代码可能仍在调用。
- 后端拒绝的编辑（类型不符、容量越界、周期不是节拍整数倍等）保留原模型，输入框回滚到模型值，页面顶部用诊断条显示 `message` 与 `hint`。
- 编辑模型不会影响正在运行的调试会话；调试页在 `manifest.hash` 与当前 `analysis.hash` 不一致时提示“模型已修改，重新开始以应用新模型”。

状态机页同样可编辑：改状态名、勾选该状态运行的数据流（已被别的状态机控制的下拉禁用并标注）、增删进入时设置的信号、`on_enter`/`on_exit` 钩子、设为初始状态；转换规则可增删、上下调整评估顺序，改起点/终点（起点含“任意状态”）与触发方式（事件 / 超时 / 信号比较 / C 函数）。删除状态前检查是否被转换引用。

数据流页与通信页共用这套编辑：数据流可改周期、展开步骤改字段（信号/输入/输出/事件/数值参数，字段与可选项由后端 `analyze` 返回的 `step_specs` 给出，不在界面硬编码）、上下移动步骤、增删步骤与数据流。新增步骤时必填引用字段会预填默认值，避免新步骤让模型非法而被拒。删除数据流前检查是否有状态机在 `run` 里引用它。

通信页有五个分类：信号、输入、输出、事件、队列。输入/输出可改名称、类型、单位，并可增删；输入另有“虚拟目标里自动产生这个输入”，仿真类型与字段由后端 `analyze.sim_specs`（`const`/`sine`/`ramp`/`square`/`noise`/`follow`，字段名、默认值与正数约束都来自 `SIM_KINDS`）驱动，切换类型时预填默认值（含 `follow` 跟随的第一个输出），否则模型非法会被后端拒绝而无法完成配置。详情区同时列出该输入/输出需要用户实现的 C 函数（`analyze.functions` 里 `owner` 为 `inputs/<id>` 或 `outputs/<id>` 的项，含所在文件与是否已实现）。

### 源码页使用的现有协议

| 方法 | 参数 / 返回与界面流程 |
| --- | --- |
| `file.read` | `{path,name}` → `{name,content,revision}`；编辑草稿保留该 revision |
| `file.write` | `{path,name,content,rev,add_functions?}`；成功返回新内容与 revision；冲突保留草稿，显示后端错误 |
| `file.create` | `{path,name,content}`；仅显式点击“保存文件”时调用；已有文件不会被覆盖 |
| `project.stub` | `{model,names}` → `[{file,header,text}]`；已有文件把模板加入草稿，新文件用 header 初始化；保存时用 `add_functions` 追加 |
| `project.save` | `{path,model,layout,rev}`；代码页编辑 `efw.json` 保存后重新 `project.open`，各页面按新模型刷新 |

`add_functions` 只对带模板标记的已有文件生效：后端把同一骨架追加到磁盘基线的固定结构上再校验。保存接口在写盘前用 `source_template.check_edit` 核对固定部分；`TEMPLATE` 表示用户改动了标记外的结构。

切换页面与文件时保留源码草稿，刷新或关闭窗口有未保存提示；草稿尚未持久化，不能恢复浏览器崩溃。顶栏重新载入项目不丢弃源码草稿；源码页“载入磁盘版本”会确认后丢弃当前文件草稿。签名错误打开源码修正，不自动追加同名函数。模板标记由代码页和 `file.write` 双重保护；代码页对标记外输入直接拦截并提示，保存端再校验一次。

## 界面结构

总览页的“下一步”把每条诊断变成修复入口：按 `at` 前缀（`flows/`、`machines/`、`signals/`、`comms/<分类>/`）用 `ui/focus.ts` 映射到页面与对象，缺失的 C 函数按 `functions[].file` 跳到代码页；点击只改前端状态，不发 RPC。目标页读 `repair`（含单调递增的 `token`）做一次定位：`ui/App.tsx` 持有该状态，`Overview` 通过 `onRepair` 发起。

左侧图标导航：总览 · 数据流 · 状态机 · 通信 · 代码 · 调试 · 生成。顶栏：项目名与路径、重新载入、运行/停止（启动虚拟目标并跳到调试页，有未保存源码草稿或模型错误时禁用）。底部状态栏：诊断计数、目标连接状态（占位）、模型 hash。撤销/重做尚未实现。

设计语言：示波器式工程界面。中性石墨底 + 单一钴蓝强调色；绿/黄/红只表示状态；等宽字体显示标识符与数值，界面文字用系统中文字体；明暗主题跟随系统；1366×768 下无需横向滚动；所有交互控件有键盘焦点与文字标签。

状态机页：状态机选择器、初始状态标记、有向关系图、按声明顺序排列的转换规则；图与规则表都可选中，选中状态/规则会互相高亮对应路径。详情区与规则展开区是编辑器（见“页面内模型编辑”）。窄窗口下详情移至图下方，大图只在图区域内部滚动。目标运行时的状态高亮尚未接入。

通信页已提供信号 / 事件 / 队列分类、名称与 id 搜索、配置表、关系详情和相关诊断。代码页支持本地 Monaco 编辑、创建 C/H 草稿、带 revision 保存及缺失函数骨架。Monaco 按需加载，worker 本地打包，无 CDN。

代码页把固定结构标为只读：`EFW USER BEGIN/END` 之外的区域显示底色，键盘输入、删除与粘贴在标记外被拦截；`efw.json` 列入文件列表作为应用配置，保存后全局刷新。草稿在内存中跨页面保留，函数模板必须先保存到磁盘才参与分析。

调试页已提供：启动卡片可选**虚拟目标 / 串口 / TCP**，并可回放 `.efw/runs/` 里的记录。目标选择存在 store 里（`target`），顶栏“运行”与调试页的启动按钮用的是同一个目标，不会出现“页面上选了串口、顶栏却启动虚拟目标”的分裂。串口填设备（`/dev/ttyUSB0` 或 `COM3`）与波特率（预设下拉），TCP 填主机与端口；参数不全时按钮禁用并在 `title` 里说明缺什么（`store.targetProblem`），避免后端抛 `KeyError`。启动失败（串口打不开、TCP 连不上、模型哈希不符）没有 session，因此错误直接渲染在启动卡片上的 `role="alert"` 诊断条里。控制条有播放/暂停、单步（仅虚拟目标，前进 500 ms）、速度（0.5×–4× 与最快）、重新开始（仅虚拟目标）与停止；顶栏显示当前目标类型与串口/TCP 地址。曲线按 `manifest` 的 id 管理通道，纵轴自动量程；任务统计、状态机当前状态与转换记录、队列深度来自快照帧；参数整定用滑杆与数字框发送 `set`（滑杆 150 ms 去抖），事件按钮发 `fire`，输入可 `force`/`release`。回放时发送类控件禁用并提示“回放中不能发送命令”。停止后保留曲线用于查看，并在启动卡片中列出新录制。

未保存源码草稿会禁用顶栏“运行”和调试页的启动按钮（`sourcesDirty` 由代码页维护）；模型有错误时同样禁用，错误原因在启动卡片中给出。

生成页已提供：打开或模型变化时自动 `generate.preview`；文件列表按 `path` 列出新增/更新/删除/冲突/未变化；选中文件用 Monaco DiffEditor 展示磁盘版本与将生成版本的差异（未变化显示说明文字）。`提交生成` 用预览 token 调 `generate.commit`，成功后重新预览并显示写入数量与输出目录；被手改的生成文件令预览 `blocked`，提交禁用并显示原因，删除手改文件后重新预览即可恢复。模型有错误时预览返回 blocked 与原因。
