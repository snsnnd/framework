# EFW 设计说明

## 1. ROS-like 通信（后续）
当前通过 `event_bus` 先实现最小发布/订阅接口，后续可演进为：
- Topic/QoS
- Request/Response 服务调用
- 节点与组件生命周期

## 2. 传感器注册表
- 统一接口：`init/read`
- 关键字段：`type` + `channel_count`
- 示例：4 路循迹与 8 路循迹可共享 `EFW_SENSOR_LINE_TRACKING` 类型并通过 `channel_count` 区分

## 3. 内置算法库
通过算法注册表统一挂载，支持以下分类：
- 控制：PID、MPC（后续）
- 滤波：均值、卡尔曼（后续）
- 建图：栅格/特征建图（后续）
- 规划：A*/DWA（后续）

## 4. 状态机注册表
统一注册状态机对象，应用层按名称拉取并驱动 `on_enter/on_tick/on_exit`。

## 5. 模块化上下层
- 下层：HAL 与驱动适配
- 上层：应用 API 调度

## 6. 领域扩展
默认面向智能车，但接口不耦合场景，可扩展到机器人、工业控制、无人设备。


## 7. 底层硬件如何关联
1. BSP 层实现 `efw_hal_ops_t` 并注册（如 `uart1`, `i2c2`）。
2. 驱动或通信组件只保存 HAL 名称（`hal_binding`）并在初始化时查询绑定。
3. 应用层仅通过组件名调用，不感知芯片差异。

## 8. 串口等通信模块实现建议
- 串口：定义 `open/close/send/recv`，底层映射到 HAL UART 的 `read/write/ioctl`。
- CAN：在 `send/recv` 内封装帧 ID、DLC、过滤器。
- I2C/SPI：可作为总线通信组件注册给传感器驱动复用。
- 以 `comm_registry` 统一管理实例（如 `dbg_uart`, `motor_can`）。
