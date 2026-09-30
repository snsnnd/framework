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

请求 `{"id","method","params"}`；响应 `{"id","result"}` / `{"id","error":{"code","message"}}`；通知（无 id）`{"event":"debug.frames","session","frames":[...]}`、`{"event":"debug.status","session","state","t","message"}`。

| 方法 | 作用 |
| --- | --- |
| `project.create/open/save/analyze` | 项目与模型；`save` 使用 revision 防冲突 |
| `project.stub` | 为缺失函数生成骨架 |
| `file.read/write/create` | 用户源码（`src/`、`board/`） |
| `generate.preview/commit` | 逐文件 Diff → token → 写入 `generated/` |
| `debug.start/control/send/stop`、`debug.runs` | 调试会话与记录 |

状态机只读页消费 `project.open` 的 `model.machines` 与 `project.analyze` 的诊断；未增加协议方法或通知。切换状态机、选择状态、选择转换均为本地浏览操作，不调用 `debug.send`。

通信页消费同一模型与 `project.analyze.usage/memory`，分类、搜索和选择详情均为本地操作。

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

左侧图标导航：总览 · 数据流 · 状态机 · 通信 · 代码 · 调试 · 生成。顶栏：项目名、保存、撤销/重做、“运行”（一键进入虚拟调试）。底部状态栏：诊断计数、目标连接状态、仿真时间。

设计语言：示波器式工程界面。中性石墨底 + 单一钴蓝强调色；绿/黄/红只表示状态；等宽字体显示标识符与数值，界面文字用系统中文字体；明暗主题跟随系统；1366×768 下无需横向滚动；所有交互控件有键盘焦点与文字标签。

状态机页已提供：状态机选择器、初始状态标记、有向关系图、状态详情、按声明顺序排列的转换规则。规则可选中以高亮对应路径；状态按钮支持键盘操作。窄窗口下详情移至图下方，大图只在图区域内部滚动。当前为只读模型预览，编辑和调试运行高亮尚未接入。

通信页已提供信号 / 事件 / 队列分类、名称与 id 搜索、配置表、关系详情和相关诊断。代码页支持本地 Monaco 编辑、创建 C/H 草稿、带 revision 保存及缺失函数骨架。Monaco 按需加载，worker 本地打包，无 CDN。

代码页把固定结构标为只读：`EFW USER BEGIN/END` 之外的区域显示底色，键盘输入、删除与粘贴在标记外被拦截；`efw.json` 列入文件列表作为应用配置，保存后全局刷新。草稿在内存中跨页面保留，函数模板必须先保存到磁盘才参与分析。

调试页已提供：顶栏“运行”启动虚拟目标并跳转；启动卡片可选虚拟目标或 `.efw/runs/` 里的记录回放；控制条有播放/暂停、单步（虚拟目标，前进 500 ms）、速度（0.5×–4× 与最快）、重新开始与停止。曲线按 `manifest` 的 id 管理通道，纵轴自动量程；任务统计、状态机当前状态与转换记录、队列深度来自快照帧；参数整定用滑杆与数字框发送 `set`（滑杆 150 ms 去抖），事件按钮发 `fire`，输入可 `force`/`release`。回放时发送类控件禁用并提示“回放中不能发送命令”。停止后保留曲线用于查看，并在启动卡片中列出新录制。

未保存源码草稿会禁用顶栏“运行”和调试页的启动按钮（`sourcesDirty` 由代码页维护）；模型有错误时同样禁用，错误原因在启动卡片中给出。

生成页已提供：打开或模型变化时自动 `generate.preview`；文件列表按 `path` 列出新增/更新/删除/冲突/未变化；选中文件用 Monaco DiffEditor 展示磁盘版本与将生成版本的差异（未变化显示说明文字）。`提交生成` 用预览 token 调 `generate.commit`，成功后重新预览并显示写入数量与输出目录；被手改的生成文件令预览 `blocked`，提交禁用并显示原因，删除手改文件后重新预览即可恢复。模型有错误时预览返回 blocked 与原因。
