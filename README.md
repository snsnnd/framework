# Embedded Framework (EFW)

一个面向嵌入式（当前以智能车为主，但不局限于智能车）的通用框架。

## 目标
- 传感器/执行器/算法/状态机统一注册与调用
- 模块可插拔：同类不同型号可通过同一 API 接入
- 分层设计：用户只需做 BSP/驱动适配 + 应用层编排
- 为后续 ROS-like 通信机制预留接口

## 分层架构
1. **HAL 适配层**：GPIO/I2C/SPI/UART/Timer 等底层接口
2. **驱动抽象层**：传感器、执行器统一驱动接口
3. **核心服务层**：注册表、状态机、算法调度、事件总线
4. **应用层**：任务逻辑与场景编排

## 当前已提供（骨架）
- 传感器注册表（支持同类多实例、不同型号统一接入）
- 算法注册表（控制、滤波、建图、路径规划）
- 状态机注册表
- 事件总线接口（后续扩展 ROS-like 通信）

## 目录
- `include/efw/`：公开头文件
- `src/`：核心实现
- `examples/`：示例代码
- `docs/`：设计文档

## 后续路线
- 增加参数服务器与组件生命周期管理
- 完善 ROS-like 发布订阅/服务调用机制
- 增加任务调度器与软实时执行模型


## 底层硬件关联（新增）
- 通过 `hal_registry` 注册硬件抽象对象（GPIO/I2C/SPI/UART/TIMER/PWM/ADC）。
- 上层模块只通过 HAL 名称绑定，不直接依赖芯片 SDK，便于跨平台迁移。
- 通信模块（UART/CAN/I2C/SPI/ETH）通过 `comm_registry` 注册，并通过 `hal_binding` 绑定到底层 HAL。

### 当前传感器注册表示例类型
- 循迹传感器（`EFW_SENSOR_LINE_TRACKING`）
- IMU（`EFW_SENSOR_IMU`）
- 编码器（`EFW_SENSOR_ENCODER`）
- 超声（`EFW_SENSOR_ULTRASONIC`）
- 自定义（`EFW_SENSOR_CUSTOM`）
