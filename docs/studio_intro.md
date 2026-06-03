# EFW Studio 介绍

## Studio 是什么

EFW Studio 是 EFW 的可视化工作台，用来把「项目配置」「蓝图装配」「代码补齐」「生成 application」放到同一个入口里完成。

它不是纯画图工具，而是围绕 EFW runtime 和 codegen 的建模前端。Studio 会：

- 管理 `.efw_project.json` 项目文件
- 编辑 Graph 节点、连线和页面结构
- 提示缺失回调、引用错误和资源冲突
- 生成可复制到真实工程中的 `application/` 目录

## 适合谁用

- 想快速装配一个 EFW 应用原型的人
- 想通过图形方式理解模块、输入、处理、输出关系的人
- 想先生成工程骨架，再补 BSP glue 和业务逻辑的人

## Studio 的核心页面

默认主流程只有五步：

1. 项目总览
2. 模块装配
3. 关系视图
4. 代码补齐
5. 生成发布

这样第一次打开不会被高级视图淹没。

## Studio 里的三类数据

为了更容易理解，建议把 Studio 里看到的数据分成三类：

### 1. 项目配置

由项目管理页维护，例如：

- 输出目录
- Board Profile
- notes
- graph 文件路径

### 2. Graph 蓝图

由装配页维护，例如：

- 模块
- 输入设备
- 处理逻辑
- 输出设备
- 通信与状态机
- 节点之间的连线

### 3. Custom Code

由代码补齐页维护，例如：

- `app_custom.c`
- 回调实现
- 条件函数
- 用户附加 `.c/.h` 文件

Studio 现在会把这三类未保存状态统一显示为：

- `未保存：项目`
- `未保存：Graph`
- `未保存：Code`

## 推荐使用方式

第一次使用时，建议直接打开示例项目：

`examples/projects/generic_embedded_app.efw_project.json`

然后按默认流程一步步走，不要一开始就打开高级面板。

## 高级面板是什么

常用面板默认只保留：

- 项目结构
- 属性表单
- 代码补齐
- 实时校验

如果你已经熟悉 EFW，可以点击 `显示高级` 查看：

- 生成映射
- 文件树预览
- 任务调度
- Board Profile / Pin Planner
- Graph JSON

## Studio 不替你做什么

Studio 会帮你完成建模、校验和生成，但不会自动替你完成以下真实项目工作：

- 板级 BSP 驱动实现
- HAL / SDK 适配
- 硬件引脚最终落地
- 业务算法细节

这些通常仍然由你在 `board_adapters` 或 `custom_files` 中补齐。
