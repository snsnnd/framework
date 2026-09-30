# EFW Studio 操作手册

## 1. 启动

### 便携版 Windows

双击：

`start_studio.bat`

### 源码仓库方式

```bash
python3 -m pip install -r tools/requirements-visual.txt
python3 tools/efw.py studio
```

## 2. 第一次打开建议做什么

推荐直接打开示例项目：

`examples/projects/generic_embedded_app.efw_project.json`

然后按下面五步走：

1. 看项目总览
2. 在模块装配里确认模块
3. 到关系视图连线
4. 到代码补齐页生成回调
5. 到生成发布页生成 application

## 3. 创建或打开项目

### 新建项目

在项目管理页点击：

- `新建`
- 或 `项目创建向导`

### 打开现有项目

点击：

- `打开`

或直接从最近项目列表中选择。

## 4. 模块装配

在 `模块装配` 页面里：

1. 先点击 `新增模块`
2. 进入模块
3. 从左侧模板库添加：
   - 输入设备
   - 处理逻辑
   - 输出设备

## 5. 关系视图

进入 `关系视图` 后：

1. 从节点右侧输出端口拖到目标节点左侧输入端口
2. 如果连线无效，Studio 会提示原因
3. 双击模块、状态机或 Topic 可以进入它们的专用页面

### 如果连错了怎么办

现在支持：

1. 点击连线选中
2. 选中后会高亮
3. 按 `Delete` 或 `Backspace` 删除这条连线

## 6. 属性表单

选中节点后，右侧 `属性表单` 可以直接修改常用字段。

常见颜色语义：

- 红色：错误/必填缺失
- 黄色：重要字段或回调
- 蓝色：引用字段

如果字段比较复杂，也可以在同一面板下方使用 `高级 JSON` 修改当前节点。

### 通信与状态机字段说明

1. `event.publisher` 连接好 `topic` 和 `source` 后，生成代码里会提供：
   - `app_publish_xxx(data, size)`
   - 如果 payload 类型可推断，还会提供 `app_publish_xxx_typed(...)`
   - 对标量类型，还会提供 `app_publish_xxx_value(...)`
2. `event.subscriber` 需要填写 `callback`，生成代码会自动完成 `efw_topic_subscribe(...)` 绑定。
3. `state.transition.event_trigger` 现在必须写成明确格式：
   - `topic:<event.topic节点id>`
   - `event:<事件名>`
4. 例子：
   - `topic:root__topic__start_evt`
   - `event:start`
5. `topic:` 形式适合把通信层事件直接送进状态机；`event:` 形式适合应用内部自定义事件。

## 7. 代码补齐

进入 `代码补齐` 页后，可以：

- 创建自定义 `.c/.h` 文件
- 编辑 `app_custom.c`
- 一键生成缺失回调
- 一键创建条件函数

如果文件切换前有未保存修改，Studio 会先提示是否保存。

### 运行时入口

当前生成代码会提供这些运行时入口：

- `app_main()`：完整系统主入口
- `app_poll_forever()`：持续轮询主循环
- `app_dispatch_event(event_name, topic_id, data, size)`：系统级事件分发入口
- `app_sm_xxx_tick()`：单个状态机 tick
- `app_sm_xxx_dispatch_event(...)`：单个状态机事件分发
- `app_sm_xxx_transition_to(...)`：强制切换到指定状态
- `app_sm_xxx_current_state()`：查询当前状态名

如果你在应用代码里主动推事件，推荐统一调用：

```c
app_dispatch_event("start", 0u, 0, 0u);
app_dispatch_event(0, APP_TOPIC_ROOT__TOPIC__START_EVT, &payload, sizeof(payload));
```

## 8. 实时校验

`实时校验` 面板会显示：

- 错误数量
- 警告数量
- 当前是否可以生成
- 建议动作

点击问题列表里的条目可以直接定位到相关节点。

## 9. 生成 application

在 `生成发布` 页面里：

1. 先看检查清单是否尽量都是 `[OK]`
2. 点击 `生成 application`
3. 如果输出目录非空，Studio 会先让你确认

生成后建议：

1. 查看文件树预览和生成映射
2. 在真实工程里补 `board_adapters`
3. 做一次编译验证

## 10. 保存语义

Studio 现在会统一显示未保存状态，例如：

- `未保存：项目`
- `未保存：Graph`
- `未保存：Code`

在项目工作台里点击 `保存全部` 会同时保存：

- 项目配置
- 当前 Graph
- 已应用到 Graph 的代码文件内容

## 11. 高级面板什么时候用

如果你只是第一次上手，建议不要急着开高级面板。

只有在这些场景下再用：

- 想看生成映射：打开 `生成映射`
- 想看文件结构：打开 `文件树预览`
- 想分析顺序：打开 `任务调度`
- 想规划引脚：打开 `Board Profile / Pin Planner`
- 想整体改 Graph：打开 `Graph JSON`
