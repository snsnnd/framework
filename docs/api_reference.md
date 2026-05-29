# EFW 框架 API 参考手册

## 目录

1. [基础类型与状态码](#1-基础类型与状态码)
2. [编译期配置](#2-编译期配置)
3. [框架入口](#3-框架入口)
4. [HAL 硬件抽象层](#4-hal-硬件抽象层)
5. [COMM 通信抽象层](#5-comm-通信抽象层)
6. [SENSOR 传感器设备层](#6-sensor-传感器设备层)
7. [ACTUATOR 执行器设备层](#7-actuator-执行器设备层)
8. [ALGORITHM 算法层](#8-algorithm-算法层)
9. [MODULE 模块生命周期层](#9-module-模块生命周期层)
10. [STATE MACHINE 状态机层](#10-state-machine-状态机层)
11. [传感器专项 API](#11-传感器专项-api)
12. [执行器专项 API](#12-执行器专项-api)
13. [算法专项 API](#13-算法专项-api)
14. [诊断系统](#14-诊断系统)
15. [事件总线](#15-事件总线)
16. [新增算法专项](#16-新增算法专项)
17. [注册表扩展功能](#17-注册表扩展功能)

---

## 1. 基础类型与状态码

**头文件：** `efw/core/common.h`

### 状态码枚举 `efw_status_t`

所有框架 API 均返回此枚举值。调用方**必须**检查返回值是否为 `EFW_OK`。

| 值 | 常量 | 含义 |
|----|------|------|
| `0` | `EFW_OK` | 操作成功 |
| `-1` | `EFW_ERR_INVALID` | 参数无效：传入了 NULL 指针、空名称、dt≤0 等 |
| `-2` | `EFW_ERR_FULL` | 注册表已满：实例数达到编译期上限 |
| `-3` | `EFW_ERR_NOT_FOUND` | 按名称查找失败：该名称的组件未注册 |
| `-4` | `EFW_ERR_ALREADY_EXISTS` | 名称冲突：尝试注册已被使用的名称 |
| `-5` | `EFW_ERR_NOT_READY` | 设备未就绪：组件未初始化或未打开 |
| `-6` | `EFW_ERR_IO` | IO 错误：底层硬件读写失败 |

### 通用宏

```c
#define EFW_UNUSED(x) ((void)(x))
```

| 宏 | 作用 |
|----|------|
| `EFW_UNUSED(x)` | 消除"未使用参数/变量"编译警告。用于回调中不需要的参数 |

---

## 2. 编译期配置

**头文件：** `efw/core/config.h`

### 模块开关 (值为 1 启用, 0 禁用)

所有开关均可通过编译器 `-D` 选项覆写，例如 `gcc -DEFW_ENABLE_COMM=0`。

| 宏 | 默认 | 含义 |
|----|------|------|
| `EFW_ENABLE_HAL` | 1 | HAL 硬件抽象层 |
| `EFW_ENABLE_COMM` | 1 | COMM 通信层 (依赖 HAL) |
| `EFW_ENABLE_MODULE` | 1 | Module 模块生命周期 |
| `EFW_ENABLE_SENSOR` | 1 | Sensor 传感器设备 (依赖 HAL/COMM) |
| `EFW_ENABLE_SENSOR_LINE_TRACKING` | 1 | 循迹传感器子模块 |
| `EFW_ENABLE_SENSOR_IMU` | 1 | IMU 传感器子模块 |
| `EFW_ENABLE_SENSOR_ENCODER` | 1 | 编码器传感器子模块 |
| `EFW_ENABLE_SENSOR_ULTRASONIC` | 1 | 超声波传感器子模块 |
| `EFW_ENABLE_SENSOR_CUSTOM` | 1 | 自定义传感器子模块 |
| `EFW_ENABLE_ACTUATOR` | 1 | Actuator 执行器 (依赖 HAL/COMM) |
| `EFW_ENABLE_ACTUATOR_MOTOR` | 1 | 电机执行器子模块 |
| `EFW_ENABLE_ALGORITHM` | 1 | Algorithm 算法注册表 |
| `EFW_ENABLE_ALGO_PID` | 1 | PID 控制器 |
| `EFW_ENABLE_ALGO_MOVING_AVG` | 1 | 滑动均值滤波器 |
| `EFW_ENABLE_ALGO_LOW_PASS` | 1 | 一阶低通滤波器 |
| `EFW_ENABLE_ALGO_RAMP` | 1 | 斜坡控制器 |
| `EFW_ENABLE_ALGO_ENCODER_SPEED` | 1 | 编码器速度估算器 |
| `EFW_ENABLE_ALGO_ATTITUDE_COMPLEMENTARY` | 1 | 互补滤波器（姿态估计） |
| `EFW_ENABLE_STATE_MACHINE` | 1 | StateMachine 状态机注册表 |
| `EFW_ENABLE_EVENT` | 1 | 事件总线 |

### 容量上限

| 宏 | 默认值 | 说明 |
|----|--------|------|
| `EFW_MAX_HALS` | 16 | HAL 最大实例数 |
| `EFW_MAX_COMMS` | 16 | COMM 最大实例数 |
| `EFW_MAX_MODULES` | 32 | Module 最大实例数 |
| `EFW_MAX_SENSORS` | 32 | 传感器最大实例数 |
| `EFW_LINE_TRACKING_MAX_CHANNELS` | 8 | 循迹传感器最大通道数 |
| `EFW_MAX_ACTUATORS` | 16 | 执行器最大实例数 |
| `EFW_MAX_TOPIC_SUBS` | 8 | 事件总线最大订阅者数 |
| `EFW_MAX_ALGOS` | 16 | 算法最大实例数 |
| `EFW_MAX_STATE_MACHINES` | 8 | 状态机最大实例数 |

---

## 3. 框架入口

**头文件：** `efw/efw.h`

### `efw_init()`

```c
efw_status_t efw_init(void);
```

| 项目 | 说明 |
|------|------|
| **作用** | 按依赖顺序初始化全部已启用的注册表 |
| **参数** | 无 |
| **返回值** | `EFW_OK` 全部成功；否则返回第一个失败的注册表初始化错误码 |
| **初始化顺序** | HAL → COMM → MODULE → SENSOR → ACTUATOR → ALGORITHM → STATE_MACHINE |
| **失败策略** | Fail-fast：任一步失败立即返回，不继续后续初始化 |
| **注意** | 仅初始化被 `EFW_ENABLE_*=1` 启用的模块，禁用的自动跳过 |

---

## 4. HAL 硬件抽象层

**头文件：** `efw/hal/hal.h`

### 类型定义

#### `efw_hal_type_t` — 硬件类型枚举

| 枚举值 | 含义 |
|--------|------|
| `EFW_HAL_GPIO` | 通用数字 IO |
| `EFW_HAL_I2C` | I2C 总线 |
| `EFW_HAL_SPI` | SPI 总线 |
| `EFW_HAL_UART` | UART 串口 |
| `EFW_HAL_TIMER` | 定时器 |
| `EFW_HAL_PWM` | PWM 输出 |
| `EFW_HAL_ADC` | ADC 模数转换 |
| `EFW_HAL_CUSTOM` | 自定义外设 |

#### `efw_hal_ops_t` — HAL 操作接口

```c
typedef struct {
    const char *name;       // [必填] 全局唯一名称
    efw_hal_type_t type;    // [必填] 硬件类型
    uint8_t bus_id;         // [可选] 总线编号
    void *ctx;              // [可选] 用户私有上下文指针
    efw_status_t (*init)(void *ctx);
    efw_status_t (*read)(void *ctx, void *buf, uint16_t len, uint16_t *actual);
    efw_status_t (*write)(void *ctx, const void *buf, uint16_t len, uint16_t *actual);
    efw_status_t (*ioctl)(void *ctx, uint32_t cmd, void *arg);
} efw_hal_ops_t;
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | `const char*` | **是** | HAL 实例的唯一标识名称，如 `"adc1"`, `"uart2"` |
| `type` | `efw_hal_type_t` | 否 | 硬件类型分类，用于按类型统计 |
| `bus_id` | `uint8_t` | 否 | 总线编号，如 UART2 的 bus_id=2 |
| `ctx` | `void*` | 否 | 用户自定义的私有数据指针，传递给所有回调 |
| `init` | 函数指针 | 否 | 硬件初始化回调。为 NULL 则跳过 |
| `read` | 函数指针 | 否 | 硬件读取回调。为 NULL 则 `efw_hal_read` 返回错误 |
| `write` | 函数指针 | 否 | 硬件写入回调。为 NULL 则 `efw_hal_write` 返回错误 |
| `ioctl` | 函数指针 | 否 | IO 控制回调。为 NULL 则 `efw_hal_ioctl` 返回错误 |

---

### API 函数

#### `efw_hal_registry_init()`

```c
efw_status_t efw_hal_registry_init(void);
```

| 项目 | 说明 |
|------|------|
| **作用** | 清空 HAL 注册表（将已注册计数归零） |
| **参数** | 无 |
| **返回值** | 始终返回 `EFW_OK` |

---

#### `efw_hal_register()`

```c
efw_status_t efw_hal_register(const efw_hal_ops_t *ops);
```

| 项目 | 说明 |
|------|------|
| **作用** | 注册一个新的 HAL 实例 |
| **参数** | `ops` — 指向 HAL 操作结构体的指针（`name` 必须非空） |
| **返回值** | `EFW_OK` 成功 |
|  | `EFW_ERR_INVALID` — `ops` 或 `ops->name` 为 NULL |
|  | `EFW_ERR_ALREADY_EXISTS` — 名称与已注册 HAL 冲突 |
|  | `EFW_ERR_FULL` — 注册表已满（达到 `EFW_MAX_HALS`） |

---

#### `efw_hal_get()`

```c
efw_status_t efw_hal_get(const char *name, const efw_hal_ops_t **out_ops);
```

| 项目 | 说明 |
|------|------|
| **作用** | 按名称查找 HAL 实例 |
| **参数** | `name` — 要查找的 HAL 名称；`out_ops` — [输出] 匹配的 HAL ops 指针 |
| **返回值** | `EFW_OK` 找到（`*out_ops` 指向匹配的 HAL） |
|  | `EFW_ERR_INVALID` — `name` 或 `out_ops` 为 NULL |
|  | `EFW_ERR_NOT_FOUND` — 未找到匹配的 HAL |

---

#### `efw_hal_count_by_type()`

```c
size_t efw_hal_count_by_type(efw_hal_type_t type);
```

| 项目 | 说明 |
|------|------|
| **作用** | 查询特定类型的 HAL 已注册数量 |
| **参数** | `type` — 硬件类型（`EFW_HAL_ADC` 等） |
| **返回值** | 该类型的已注册实例数 |

---

#### `efw_hal_init_device()`

```c
efw_status_t efw_hal_init_device(const char *name);
```

| 项目 | 说明 |
|------|------|
| **作用** | 初始化指定名称的 HAL 设备 |
| **参数** | `name` — HAL 名称 |
| **返回值** | `EFW_OK` 成功（init 为 NULL 也返回 OK） |
|  | `EFW_ERR_NOT_FOUND` — 未找到该名称的 HAL |
| **注意** | init 回调为 NULL 时视为合法跳过，不报错 |

---

#### `efw_hal_read()`

```c
efw_status_t efw_hal_read(const char *name, void *buf, uint16_t len, uint16_t *actual);
```

| 项目 | 说明 |
|------|------|
| **作用** | 通过 HAL 读取数据 |
| **参数** | `name` — HAL 名称 |
|  | `buf` — 接收数据的缓冲区 |
|  | `len` — 期望读取的字节数 |
|  | `actual` — [输出] 实际读取的字节数。可传 NULL 不关心 |
| **返回值** | `EFW_OK` 成功 |
|  | `EFW_ERR_NOT_FOUND` — 未找到 HAL |
|  | `EFW_ERR_INVALID` — read 回调为 NULL |

---

#### `efw_hal_write()`

```c
efw_status_t efw_hal_write(const char *name, const void *buf, uint16_t len, uint16_t *actual);
```

| 项目 | 说明 |
|------|------|
| **作用** | 通过 HAL 写入数据 |
| **参数** | `name` — HAL 名称 |
|  | `buf` — 待写入的数据缓冲区 |
|  | `len` — 期望写入的字节数 |
|  | `actual` — [输出] 实际写入的字节数。可传 NULL |
| **返回值** | `EFW_OK` 成功；`EFW_ERR_NOT_FOUND` 未找到；`EFW_ERR_INVALID` write 回调为空 |

---

#### `efw_hal_ioctl()`

```c
efw_status_t efw_hal_ioctl(const char *name, uint32_t cmd, void *arg);
```

| 项目 | 说明 |
|------|------|
| **作用** | 执行 HAL 控制命令（通用配置接口） |
| **参数** | `name` — HAL 名称 |
|  | `cmd` — 用户自定义命令码（如 `SET_BAUDRATE=1`） |
|  | `arg` — 命令参数指针（指向配置值） |
| **返回值** | `EFW_OK` 成功；`EFW_ERR_NOT_FOUND` 未找到；`EFW_ERR_INVALID` ioctl 回调为空 |
| **典型用途** | 设置波特率、切换采样通道、配置中断触发条件等 |

---

## 5. COMM 通信抽象层

**头文件：** `efw/comm/comm.h`

### 类型定义

#### `efw_comm_type_t` — 通信类型枚举

| 枚举值 | 含义 |
|--------|------|
| `EFW_COMM_UART` | 基于 UART 的通信协议 |
| `EFW_COMM_CAN` | 基于 CAN 总线的通信 |
| `EFW_COMM_I2C` | 基于 I2C 总线的通信 |
| `EFW_COMM_SPI` | 基于 SPI 总线的通信 |
| `EFW_COMM_ETH` | 基于以太网的通信 |
| `EFW_COMM_CUSTOM` | 自定义通信方式 |

#### `efw_comm_ops_t` — COMM 操作接口

```c
typedef struct {
    const char *name;       // [必填] 全局唯一名称
    efw_comm_type_t type;   // [必填] 通信类型
    const char *hal_name;   // [可选] 绑定的 HAL 名称
    void *ctx;              // [可选] 用户私有上下文
    efw_status_t (*open)(void *ctx);
    efw_status_t (*close)(void *ctx);
    efw_status_t (*send)(void *ctx, const uint8_t *data, uint16_t len, uint16_t *actual);
    efw_status_t (*recv)(void *ctx, uint8_t *data, uint16_t len, uint16_t *actual);
} efw_comm_ops_t;
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | `const char*` | **是** | COMM 实例的唯一名称，如 `"dbg_uart"` |
| `type` | `efw_comm_type_t` | 否 | 通信类型分类 |
| `hal_name` | `const char*` | 否 | 绑定的 HAL 名称。**注册时必须已存在**，否则注册失败 |
| `ctx` | `void*` | 否 | 用户私有数据指针 |
| `open` | 函数指针 | 否 | 打开通道回调（可空） |
| `close` | 函数指针 | 否 | 关闭通道回调（可空） |
| `send` | 函数指针 | **是** | 发送数据回调。注册时校验非空 |
| `recv` | 函数指针 | **是** | 接收数据回调。注册时校验非空 |

---

### API 函数

#### `efw_comm_registry_init()`

```c
efw_status_t efw_comm_registry_init(void);
```

| 项目 | 说明 |
|------|------|
| **作用** | 清空 COMM 注册表 |
| **参数** | 无 |
| **返回值** | 始终返回 `EFW_OK` |

---

#### `efw_comm_register()`

```c
efw_status_t efw_comm_register(const efw_comm_ops_t *ops);
```

| 项目 | 说明 |
|------|------|
| **作用** | 注册一个新的 COMM 实例。**若指定 hal_name，立即校验 HAL 存在性** |
| **参数** | `ops` — COMM 操作结构体（`name`, `send`, `recv` 必填） |
| **返回值** | `EFW_OK` 成功 |
|  | `EFW_ERR_INVALID` — ops/name/send/recv 为空，或 HAL 禁用时尝试绑定 hal_name |
|  | `EFW_ERR_NOT_FOUND` — hal_name 引用的 HAL 不存在 |
|  | `EFW_ERR_ALREADY_EXISTS` — 名称冲突 |
|  | `EFW_ERR_FULL` — 注册表已满 |

---

#### `efw_comm_get()`

```c
efw_status_t efw_comm_get(const char *name, const efw_comm_ops_t **out_ops);
```

| 项目 | 说明 |
|------|------|
| **作用** | 按名称查找 COMM 实例 |
| **参数** | `name` — COMM 名称；`out_ops` — [输出] 匹配的 ops 指针 |
| **返回值** | `EFW_OK` 找到；`EFW_ERR_INVALID` 参数错误；`EFW_ERR_NOT_FOUND` 未找到 |

---

#### `efw_comm_count_by_type()`

```c
size_t efw_comm_count_by_type(efw_comm_type_t type);
```

| 项目 | 说明 |
|------|------|
| **作用** | 查询特定类型的 COMM 已注册数量 |
| **参数** | `type` — 通信类型 |
| **返回值** | 该类型的已注册实例数 |

---

#### `efw_comm_bind_hal()`

```c
efw_status_t efw_comm_bind_hal(const char *comm_name, const efw_hal_ops_t **out_hal);
```

| 项目 | 说明 |
|------|------|
| **作用** | 查询 COMM 绑定的底层 HAL |
| **参数** | `comm_name` — COMM 名称；`out_hal` — [输出] 绑定的 HAL ops 指针 |
| **返回值** | `EFW_OK` 找到；`EFW_ERR_NOT_FOUND` — COMM 不存在或未绑定 HAL |
|  | `EFW_ERR_INVALID` — HAL 被禁用时返回 |

---

#### `efw_comm_open()`

```c
efw_status_t efw_comm_open(const char *name);
```

| 项目 | 说明 |
|------|------|
| **作用** | 打开通信通道（调用 open 回调） |
| **参数** | `name` — COMM 名称 |
| **返回值** | `EFW_OK` 成功（open 为 NULL 也返回 OK）；`EFW_ERR_NOT_FOUND` 未找到 |

---

#### `efw_comm_close()`

```c
efw_status_t efw_comm_close(const char *name);
```

| 项目 | 说明 |
|------|------|
| **作用** | 关闭通信通道（调用 close 回调） |
| **参数** | `name` — COMM 名称 |
| **返回值** | `EFW_OK` 成功（close 为 NULL 也返回 OK）；`EFW_ERR_NOT_FOUND` 未找到 |

---

#### `efw_comm_send()`

```c
efw_status_t efw_comm_send(const char *name, const uint8_t *data, uint16_t len, uint16_t *actual);
```

| 项目 | 说明 |
|------|------|
| **作用** | 通过 COMM 发送数据 |
| **参数** | `name` — COMM 名称 |
|  | `data` — 待发送的字节数组 |
|  | `len` — 数组长度 |
|  | `actual` — [输出] 实际发送的字节数（非阻塞下可能 < len） |
| **返回值** | `EFW_OK` 成功；`EFW_ERR_NOT_FOUND` 未找到；其他来自 send 回调 |

---

#### `efw_comm_recv()`

```c
efw_status_t efw_comm_recv(const char *name, uint8_t *data, uint16_t len, uint16_t *actual);
```

| 项目 | 说明 |
|------|------|
| **作用** | 从 COMM 接收数据 |
| **参数** | `name` — COMM 名称 |
|  | `data` — 接收缓冲区 |
|  | `len` — 期望接收的字节数 |
|  | `actual` — [输出] 实际接收的字节数 |
| **返回值** | `EFW_OK` 成功；`EFW_ERR_NOT_FOUND` 未找到；其他来自 recv 回调 |

---

## 6. SENSOR 传感器设备层

**头文件：** `efw/device/sensor.h`

### 类型定义

#### `efw_sensor_type_t` — 传感器类型枚举

| 枚举值 | 含义 |
|--------|------|
| `EFW_SENSOR_LINE_TRACKING` | 循迹传感器 |
| `EFW_SENSOR_IMU` | 惯性测量单元 |
| `EFW_SENSOR_ENCODER` | 编码器 |
| `EFW_SENSOR_ULTRASONIC` | 超声波距离传感器 |
| `EFW_SENSOR_CUSTOM` | 自定义传感器 |

#### `efw_sensor_ops_t` — 传感器操作接口

```c
typedef struct {
    const char *name;           // [必填] 全局唯一名称
    efw_sensor_type_t type;     // [必填] 传感器类型
    uint8_t channel_count;      // [可选] 通道数
    const char *hal_name;       // [可选] 绑定的 HAL 名称
    const char *comm_name;      // [可选] 绑定的 COMM 名称
    void *ctx;                  // [可选] 用户私有上下文
    efw_status_t (*init)(void *ctx);
    efw_status_t (*read)(void *ctx, void *out);
} efw_sensor_ops_t;
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | `const char*` | **是** | 传感器唯一名称，如 `"line5"`, `"imu_head"` |
| `type` | `efw_sensor_type_t` | 否 | 传感器类型分类 |
| `channel_count` | `uint8_t` | 否 | 通道数（如 4 路循迹=4），用户定义，框架仅做标记 |
| `hal_name` | `const char*` | 否 | 绑定的 HAL 名称。**注册时必须已存在** |
| `comm_name` | `const char*` | 否 | 绑定的 COMM 名称。**注册时必须已存在** |
| `ctx` | `void*` | 否 | 用户私有数据 |
| `init` | 函数指针 | 否 | 初始化回调（可空） |
| `read` | 函数指针 | **是** | 读取回调。注册时校验非空 |

---

### API 函数

#### `efw_sensor_registry_init()`

```c
efw_status_t efw_sensor_registry_init(void);
```

| 项目 | 说明 |
|------|------|
| **作用** | 清空传感器注册表 |
| **参数** | 无 |
| **返回值** | 始终返回 `EFW_OK` |

---

#### `efw_sensor_register()`

```c
efw_status_t efw_sensor_register(const efw_sensor_ops_t *ops);
```

| 项目 | 说明 |
|------|------|
| **作用** | 注册传感器实例。**若指定 hal_name/comm_name，立即校验绑定存在性** |
| **参数** | `ops` — 传感器操作结构体（`name`, `read` 必填） |
| **返回值** | `EFW_OK` 成功 |
|  | `EFW_ERR_INVALID` — ops/name/read 为空，或 HAL/COMM 禁用时尝试绑定 |
|  | `EFW_ERR_NOT_FOUND` — hal_name 或 comm_name 引用的 HAL/COMM 不存在 |
|  | `EFW_ERR_ALREADY_EXISTS` — 名称冲突 |
|  | `EFW_ERR_FULL` — 注册表已满 |

---

#### `efw_sensor_get()`

```c
efw_status_t efw_sensor_get(const char *name, const efw_sensor_ops_t **out_ops);
```

| 项目 | 说明 |
|------|------|
| **作用** | 按名称查找传感器 |
| **参数** | `name` — 传感器名称；`out_ops` — [输出] 匹配的 ops 指针 |
| **返回值** | `EFW_OK` 找到；`EFW_ERR_INVALID` 参数错误；`EFW_ERR_NOT_FOUND` 未找到 |

---

#### `efw_sensor_count_by_type()`

```c
size_t efw_sensor_count_by_type(efw_sensor_type_t type);
```

| 项目 | 说明 |
|------|------|
| **作用** | 查询特定类型的传感器已注册数量 |
| **参数** | `type` — 传感器类型 |
| **返回值** | 该类型的已注册实例数 |

---

#### `efw_sensor_bind_hal()`

```c
efw_status_t efw_sensor_bind_hal(const char *sensor_name, const efw_hal_ops_t **out_hal);
```

| 项目 | 说明 |
|------|------|
| **作用** | 查询传感器绑定的底层 HAL |
| **参数** | `sensor_name` — 传感器名称；`out_hal` — [输出] 绑定的 HAL ops 指针 |
| **返回值** | `EFW_OK` 找到；`EFW_ERR_NOT_FOUND` 传感器不存在或未绑定 HAL |

---

#### `efw_sensor_bind_comm()`

```c
efw_status_t efw_sensor_bind_comm(const char *sensor_name, const efw_comm_ops_t **out_comm);
```

| 项目 | 说明 |
|------|------|
| **作用** | 查询传感器绑定的底层 COMM |
| **参数** | `sensor_name` — 传感器名称；`out_comm` — [输出] 绑定的 COMM ops 指针 |
| **返回值** | `EFW_OK` 找到；`EFW_ERR_NOT_FOUND` 传感器不存在或未绑定 COMM |

---

#### `efw_sensor_init_device()`

```c
efw_status_t efw_sensor_init_device(const char *name);
```

| 项目 | 说明 |
|------|------|
| **作用** | 初始化指定名称的传感器（调用 init 回调） |
| **参数** | `name` — 传感器名称 |
| **返回值** | `EFW_OK` 成功（init 为 NULL 也返回 OK）；`EFW_ERR_NOT_FOUND` 未找到 |

---

#### `efw_sensor_read()`

```c
efw_status_t efw_sensor_read(const char *name, void *out);
```

| 项目 | 说明 |
|------|------|
| **作用** | **★ 最常用的传感器 API** — 按名称读取传感器数据 |
| **参数** | `name` — 传感器名称；`out` — 输出缓冲区（类型由传感器定义） |
| **返回值** | `EFW_OK` 成功；`EFW_ERR_NOT_FOUND` 未找到；其他来自 read 回调 |

---

## 7. ACTUATOR 执行器设备层

**头文件：** `efw/device/actuator.h`

### 类型定义

#### `efw_actuator_type_t` — 执行器类型枚举

| 枚举值 | 含义 |
|--------|------|
| `EFW_ACTUATOR_MOTOR` | 电机 |
| `EFW_ACTUATOR_SERVO` | 舵机 |
| `EFW_ACTUATOR_RELAY` | 继电器 |
| `EFW_ACTUATOR_LED` | LED |
| `EFW_ACTUATOR_CUSTOM` | 自定义执行器 |

#### `efw_actuator_cmd_t` — 通用执行器命令

```c
typedef struct {
    float value;  // 控制值（LED 亮度 0~1，继电器 0/1 等）
} efw_actuator_cmd_t;
```

#### `efw_motor_cmd_t` — 电机专用命令

```c
typedef struct {
    float speed;       // 速度值
    float direction;   // 方向（1.0=正转, -1.0=反转, 0.0=停止）
} efw_motor_cmd_t;
```

#### `efw_actuator_ops_t` — 执行器操作接口

```c
typedef struct {
    const char *name;           // [必填] 全局唯一名称
    efw_actuator_type_t type;   // [必填] 执行器类型
    const char *hal_name;       // [可选] 绑定的 HAL 名称
    const char *comm_name;      // [可选] 绑定的 COMM 名称
    void *ctx;                  // [可选] 用户私有上下文
    efw_status_t (*init)(void *ctx);
    efw_status_t (*enable)(void *ctx);
    efw_status_t (*disable)(void *ctx);
    efw_status_t (*write)(void *ctx, const void *cmd);
} efw_actuator_ops_t;
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | `const char*` | **是** | 执行器唯一名称，如 `"left_motor"` |
| `type` | `efw_actuator_type_t` | 否 | 执行器类型分类 |
| `hal_name` | `const char*` | 否 | 绑定的 HAL 名称。注册时校验存在性 |
| `comm_name` | `const char*` | 否 | 绑定的 COMM 名称。注册时校验存在性 |
| `ctx` | `void*` | 否 | 用户私有数据 |
| `init` | 函数指针 | 否 | 初始化回调（可空） |
| `enable` | 函数指针 | 否 | 使能回调（可空） |
| `disable` | 函数指针 | 否 | 禁用回调（可空） |
| `write` | 函数指针 | **是** | 写入控制指令回调。注册时校验非空 |

---

### API 函数

#### `efw_actuator_registry_init()`

```c
efw_status_t efw_actuator_registry_init(void);
```

| 项目 | 说明 |
|------|------|
| **作用** | 清空执行器注册表 |
| **参数** | 无 |
| **返回值** | 始终返回 `EFW_OK` |

---

#### `efw_actuator_register()`

```c
efw_status_t efw_actuator_register(const efw_actuator_ops_t *ops);
```

| 项目 | 说明 |
|------|------|
| **作用** | 注册执行器实例。含 HAL/COMM 绑定校验 |
| **参数** | `ops` — 执行器操作结构体（`name`, `write` 必填） |
| **返回值** | `EFW_OK`；`EFW_ERR_INVALID` 参数错误；`EFW_ERR_NOT_FOUND` HAL/COMM 绑定失败 |
|  | `EFW_ERR_ALREADY_EXISTS` 名称冲突；`EFW_ERR_FULL` 已满 |

---

#### `efw_actuator_get()`

```c
efw_status_t efw_actuator_get(const char *name, const efw_actuator_ops_t **out_ops);
```

| 项目 | 说明 |
|------|------|
| **作用** | 按名称查找执行器 |
| **参数** | `name` — 执行器名称；`out_ops` — [输出] 匹配的 ops 指针 |
| **返回值** | `EFW_OK`；`EFW_ERR_INVALID`；`EFW_ERR_NOT_FOUND` |

---

#### `efw_actuator_count_by_type()`

```c
size_t efw_actuator_count_by_type(efw_actuator_type_t type);
```

| 项目 | 说明 |
|------|------|
| **作用** | 查询特定类型的执行器已注册数量 |
| **参数** | `type` — 执行器类型 |
| **返回值** | 该类型的已注册实例数 |

---

#### `efw_actuator_bind_hal()`

```c
efw_status_t efw_actuator_bind_hal(const char *actuator_name, const efw_hal_ops_t **out_hal);
```

| 项目 | 说明 |
|------|------|
| **作用** | 查询执行器绑定的 HAL |
| **参数** | `actuator_name` — 执行器名称；`out_hal` — [输出] HAL ops 指针 |
| **返回值** | `EFW_OK`；`EFW_ERR_NOT_FOUND` 未绑定或不存在 |

---

#### `efw_actuator_bind_comm()`

```c
efw_status_t efw_actuator_bind_comm(const char *actuator_name, const efw_comm_ops_t **out_comm);
```

| 项目 | 说明 |
|------|------|
| **作用** | 查询执行器绑定的 COMM |
| **参数** | `actuator_name` — 执行器名称；`out_comm` — [输出] COMM ops 指针 |
| **返回值** | `EFW_OK`；`EFW_ERR_NOT_FOUND` 未绑定或不存在 |

---

#### `efw_actuator_init_device()`

```c
efw_status_t efw_actuator_init_device(const char *name);
```

| 项目 | 说明 |
|------|------|
| **作用** | 初始化执行器（init 为 NULL 时跳过） |
| **参数** | `name` — 执行器名称 |
| **返回值** | `EFW_OK`；`EFW_ERR_NOT_FOUND` |

---

#### `efw_actuator_enable()`

```c
efw_status_t efw_actuator_enable(const char *name);
```

| 项目 | 说明 |
|------|------|
| **作用** | 使能执行器（enable 为 NULL 时跳过） |
| **参数** | `name` — 执行器名称 |
| **返回值** | `EFW_OK`；`EFW_ERR_NOT_FOUND` |

---

#### `efw_actuator_disable()`

```c
efw_status_t efw_actuator_disable(const char *name);
```

| 项目 | 说明 |
|------|------|
| **作用** | 禁用执行器（disable 为 NULL 时跳过） |
| **参数** | `name` — 执行器名称 |
| **返回值** | `EFW_OK`；`EFW_ERR_NOT_FOUND` |

---

#### `efw_actuator_write()`

```c
efw_status_t efw_actuator_write(const char *name, const void *cmd);
```

| 项目 | 说明 |
|------|------|
| **作用** | **★ 最常用的执行器 API** — 写入控制指令 |
| **参数** | `name` — 执行器名称；`cmd` — 命令数据指针（`efw_actuator_cmd_t*` / `efw_motor_cmd_t*` / 自定义） |
| **返回值** | `EFW_OK`；`EFW_ERR_INVALID` cmd 为空；`EFW_ERR_NOT_FOUND` 未找到 |

---

## 8. ALGORITHM 算法层

**头文件：** `efw/algorithm/registry.h`

### 类型定义

#### `efw_algo_type_t` — 算法类型枚举

| 枚举值 | 含义 |
|--------|------|
| `EFW_ALGO_CONTROL` | 控制类算法（PID 等） |
| `EFW_ALGO_FILTER` | 滤波类算法（滑动均值等） |
| `EFW_ALGO_MAPPING` | 映射/变换类算法 |
| `EFW_ALGO_PLANNING` | 规划类算法 |
| `EFW_ALGO_CUSTOM` | 自定义算法 |

#### `efw_algo_ops_t` — 算法操作接口

```c
typedef struct {
    const char *name;       // [必填] 全局唯一名称
    efw_algo_type_t type;   // [必填] 算法类型
    void *ctx;              // [可选] 算法私有上下文
    efw_status_t (*run)(void *ctx, const void *in, void *out);
} efw_algo_ops_t;
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | `const char*` | **是** | 算法唯一名称，如 `"motor_pid"`, `"adc_filter"` |
| `type` | `efw_algo_type_t` | 否 | 算法类型分类 |
| `ctx` | `void*` | 否 | 算法私有上下文（如 `efw_pid_t*`） |
| `run` | 函数指针 | **是** | 算法执行函数。`in`/`out` 类型由各算法定义。注册时校验非空 |

---

### API 函数

#### `efw_algo_registry_init()`

```c
efw_status_t efw_algo_registry_init(void);
```

| 项目 | 说明 |
|------|------|
| **作用** | 清空算法注册表 |
| **参数** | 无 |
| **返回值** | 始终返回 `EFW_OK` |

---

#### `efw_algo_register()`

```c
efw_status_t efw_algo_register(const efw_algo_ops_t *ops);
```

| 项目 | 说明 |
|------|------|
| **作用** | 注册算法实例 |
| **参数** | `ops` — 算法操作结构体（`name`, `run` 必填） |
| **返回值** | `EFW_OK`；`EFW_ERR_INVALID`；`EFW_ERR_ALREADY_EXISTS`；`EFW_ERR_FULL` |

---

#### `efw_algo_get()`

```c
efw_status_t efw_algo_get(const char *name, const efw_algo_ops_t **out_ops);
```

| 项目 | 说明 |
|------|------|
| **作用** | 按名称查找算法。**高频路径可预取指针跳过后续查找** |
| **参数** | `name` — 算法名称；`out_ops` — [输出] 匹配的 ops 指针 |
| **返回值** | `EFW_OK`；`EFW_ERR_INVALID`；`EFW_ERR_NOT_FOUND` |

---

#### `efw_algo_run()`

```c
efw_status_t efw_algo_run(const char *name, const void *in, void *out);
```

| 项目 | 说明 |
|------|------|
| **作用** | **★ 最常用的算法 API** — 按名称运行算法 |
| **参数** | `name` — 算法名称 |
|  | `in` — 输入数据指针（类型由算法定义，如 PID 需 `efw_pid_input_t*`） |
|  | `out` — 输出数据指针（类型由算法定义，如 PID 需 `efw_pid_output_t*`） |
| **返回值** | `EFW_OK`；`EFW_ERR_NOT_FOUND` 未找到；其他来自 run 回调 |
| **性能提示** | 内部先做 O(n) 名称查找再调用 run。高频场景建议用 `efw_algo_get()` 预取 ops 直接调用 |

---

## 9. MODULE 模块生命周期层

**头文件：** `efw/module/module.h`

### 类型定义

#### `efw_module_type_t` — 模块类型枚举

| 枚举值 | 含义 |
|--------|------|
| `EFW_MODULE_DRIVER` | 驱动封装模块 |
| `EFW_MODULE_SERVICE` | 后台服务模块 |
| `EFW_MODULE_APP` | 应用任务模块 |
| `EFW_MODULE_CUSTOM` | 自定义模块 |

#### `efw_module_ops_t` — 模块操作接口

```c
typedef struct {
    const char *name;       // [必填] 全局唯一名称
    efw_module_type_t type; // [必填] 模块类型
    void *ctx;              // [可选] 用户私有上下文
    efw_status_t (*init)(void *ctx);
    efw_status_t (*start)(void *ctx);
    efw_status_t (*stop)(void *ctx);
    efw_status_t (*poll)(void *ctx);
} efw_module_ops_t;
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | `const char*` | **是** | 模块唯一名称 |
| `type` | `efw_module_type_t` | 否 | 模块类型分类 |
| `ctx` | `void*` | 否 | 用户私有数据 |
| `init` | 函数指针 | 否 | 初始化回调（可空） |
| `start` | 函数指针 | 否 | 启动回调（可空） |
| `stop` | 函数指针 | 否 | 停止回调（可空） |
| `poll` | 函数指针 | 否 | 轮询回调（可空） |

---

### API 函数

#### `efw_module_registry_init()`

```c
efw_status_t efw_module_registry_init(void);
```

| 项目 | 说明 |
|------|------|
| **作用** | 清空模块注册表 |
| **返回值** | 始终返回 `EFW_OK` |

---

#### `efw_module_register()`

```c
efw_status_t efw_module_register(const efw_module_ops_t *ops);
```

| 项目 | 说明 |
|------|------|
| **作用** | 注册模块实例（init/start/stop/poll 均可空） |
| **参数** | `ops` — 模块操作结构体（`name` 必填） |
| **返回值** | `EFW_OK`；`EFW_ERR_INVALID`；`EFW_ERR_ALREADY_EXISTS`；`EFW_ERR_FULL` |

---

#### `efw_module_get()`

```c
efw_status_t efw_module_get(const char *name, const efw_module_ops_t **out_ops);
```

| 项目 | 说明 |
|------|------|
| **作用** | 按名称查找模块 |
| **返回值** | `EFW_OK`；`EFW_ERR_INVALID`；`EFW_ERR_NOT_FOUND` |

---

#### 单模块操作

```c
efw_status_t efw_module_init(const char *name);
efw_status_t efw_module_start(const char *name);
efw_status_t efw_module_stop(const char *name);
efw_status_t efw_module_poll(const char *name);
```

| 项目 | 说明 |
|------|------|
| **作用** | 对单个模块执行 init/start/stop/poll |
| **参数** | `name` — 模块名称 |
| **返回值** | `EFW_OK`（回调为 NULL 时也返回 OK）；`EFW_ERR_NOT_FOUND` 未找到 |

---

#### 批量操作

```c
efw_status_t efw_module_init_all(void);
efw_status_t efw_module_start_all(void);
efw_status_t efw_module_poll_all(void);
```

| 函数 | 说明 |
|------|------|
| `efw_module_init_all()` | 按注册顺序初始化**所有**模块。任一步失败立即停止 |
| `efw_module_start_all()` | 按注册顺序启动**所有**模块。任一步失败立即停止 |
| `efw_module_poll_all()` | **★ 主循环核心** — 按注册顺序轮询所有模块。应在 `while(1)` 中反复调用 |

| 项目 | 说明 |
|------|------|
| **参数** | 无 |
| **返回值** | `EFW_OK`；或第一个失败模块的错误码 |

---

#### `efw_module_count_by_type()`

```c
size_t efw_module_count_by_type(efw_module_type_t type);
```

| 项目 | 说明 |
|------|------|
| **作用** | 查询特定类型的模块已注册数量 |
| **返回值** | 该类型的已注册实例数 |

---

## 10. STATE MACHINE 状态机层

**头文件：** `efw/state/state_machine.h`

### 类型定义

#### `efw_state_machine_ops_t` — 状态机操作接口

```c
typedef struct {
    const char *name;       // [必填] 全局唯一名称
    void *ctx;              // [可选] 用户私有上下文
    efw_status_t (*on_enter)(void *ctx);
    efw_status_t (*on_tick)(void *ctx);
    efw_status_t (*on_exit)(void *ctx);
} efw_state_machine_ops_t;
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | `const char*` | **是** | 状态唯一名称 |
| `ctx` | `void*` | 否 | 用户私有数据 |
| `on_enter` | 函数指针 | 否 | 进入状态回调（可空） |
| `on_tick` | 函数指针 | **是** | 状态保持回调。注册时校验非空 |
| `on_exit` | 函数指针 | 否 | 离开状态回调（可空） |

> **注意**：每个 `efw_state_machine_ops_t` 代表**一个状态**（非整个状态机）。多个状态实例组合成完整状态机。状态转移由用户在上层自行管理。

---

### API 函数

#### `efw_sm_registry_init()`

```c
efw_status_t efw_sm_registry_init(void);
```

| 项目 | 说明 |
|------|------|
| **作用** | 清空状态机注册表 |
| **返回值** | 始终返回 `EFW_OK` |

---

#### `efw_sm_register()`

```c
efw_status_t efw_sm_register(const efw_state_machine_ops_t *ops);
```

| 项目 | 说明 |
|------|------|
| **作用** | 注册一个状态实例 |
| **参数** | `ops` — 状态操作结构体（`name`, `on_tick` 必填） |
| **返回值** | `EFW_OK`；`EFW_ERR_INVALID`；`EFW_ERR_ALREADY_EXISTS`；`EFW_ERR_FULL` |

---

#### `efw_sm_get()`

```c
efw_status_t efw_sm_get(const char *name, const efw_state_machine_ops_t **out_ops);
```

| 项目 | 说明 |
|------|------|
| **作用** | 按名称查找状态实例 |
| **返回值** | `EFW_OK`；`EFW_ERR_INVALID`；`EFW_ERR_NOT_FOUND` |

---

## 11. 传感器专项 API

### 11.1 循迹传感器

**头文件：** `efw/device/sensor/line_tracking.h`

#### 数据结构

```c
typedef struct {
    uint8_t count;                                          // 实际有效通道数
    uint16_t value[EFW_LINE_TRACKING_MAX_CHANNELS];         // 各通道读数（0~65535）
} efw_line_tracking_data_t;

typedef struct {
    const efw_sensor_ops_t *sensor;       // [内部] 传感器 ops（bind 时缓存）
    const efw_algo_ops_t *pid;            // [内部] PID ops
    const efw_actuator_ops_t *left_motor; // [内部] 左电机 ops
    const efw_actuator_ops_t *right_motor;// [内部] 右电机 ops
    const float *weights;                 // 权重数组指针
    uint16_t active_value;                // 数字循迹有效电平
    float base_speed;                     // 基础巡航速度
    float min_speed;                      // 最小速度限制
    float max_speed;                      // 最大速度限制
    float dt;                             // 控制周期（秒）
} efw_line_follower_t;
```

#### `efw_line_tracking_read()`

```c
efw_status_t efw_line_tracking_read(const char *name, efw_line_tracking_data_t *out);
```

| 项目 | 说明 |
|------|------|
| **作用** | 读取循迹传感器数据（对 `efw_sensor_read()` 的类型安全包装） |
| **参数** | `name` — 传感器名称；`out` — [输出] 循迹数据（count + value[]） |
| **返回值** | `EFW_OK`；`EFW_ERR_INVALID` out 为空；其他来自底层 read |

---

#### `efw_line_tracking_error_weighted()`

```c
float efw_line_tracking_error_weighted(const efw_line_tracking_data_t *data, const float *weights);
```

| 项目 | 说明 |
|------|------|
| **作用** | **加权误差（模拟量）** — 以亮度为权重的质心位置。正=偏右, 负=偏左, 0=居中 |
| **参数** | `data` — 传感器读数；`weights` — 各通道空间权重（如 `{-2,-1,0,1,2}`） |
| **返回值** | 加权偏差值（float）。数据无效时返回 0.0 |
| **公式** | `error = Σ(w[i] × v[i]) / Σ(v[i])` |
| **用途** | 返回值可直接作为 PID 的 feedback 输入 |

---

#### `efw_line_tracking_active_mask()`

```c
uint16_t efw_line_tracking_active_mask(const efw_line_tracking_data_t *data, uint16_t active_value);
```

| 项目 | 说明 |
|------|------|
| **作用** | 返回位掩码：bit i = 1 表示通道 i 检测到线（value[i] == active_value） |
| **参数** | `data` — 传感器读数；`active_value` — "有线"的电平值（0 或 1） |
| **返回值** | 16 位掩码（最多 16 通道）。data 为 NULL 返回 0 |

---

#### `efw_line_tracking_error_binary()`

```c
float efw_line_tracking_error_binary(const efw_line_tracking_data_t *data,
                                     const float *error_table, uint16_t active_value);
```

| 项目 | 说明 |
|------|------|
| **作用** | **二值化偏差（数字量）** — 所有检测到线的通道的平均偏差 |
| **参数** | `data` — 传感器读数；`error_table` — 各通道预定义偏差（如 `{-2,-1,0,1,2}`） |
|  | `active_value` — "有线"的电平值 |
| **返回值** | 平均偏差。正=偏右, 负=偏左, 无信号返回 0.0 |
| **注意** | 与 weighted 不同——这里不按信号强度加权，激活通道等权 |

---

#### `efw_line_tracking_follow_diff()`

```c
efw_status_t efw_line_tracking_follow_diff(const char *sensor_name, const char *pid_name,
                                           const char *left_motor, const char *right_motor,
                                           const float *weights, float base_speed, float dt,
                                           float *out_error, float *out_turn);
```

| 项目 | 说明 |
|------|------|
| **作用** | **一步差速循迹（旧版 API）** — read → weighted_error → PID → motor_set_diff |
| **参数** | `sensor_name` — 传感器名称；`pid_name` — PID 名称 |
|  | `left_motor` — 左电机名称；`right_motor` — 右电机名称 |
|  | `weights` — 权重数组；`base_speed` — 基础速度；`dt` — 控制周期（秒） |
|  | `out_error` — [输出] 加权误差值（可 NULL）；`out_turn` — [输出] PID 输出（可 NULL） |
| **返回值** | `EFW_OK`；`EFW_ERR_INVALID` weights 为空或 dt≤0 |
| **注意** | 使用无速度限制的 `set_diff`；推荐使用新版 `efw_line_follower_*` API |

---

#### `efw_line_follower_bind()`

```c
efw_status_t efw_line_follower_bind(efw_line_follower_t *follower,
                                    const char *sensor_name, const char *pid_name,
                                    const char *left_motor, const char *right_motor,
                                    const float *weights, float base_speed,
                                    float min_speed, float max_speed, float dt);
```

| 项目 | 说明 |
|------|------|
| **作用** | **★ 新版推荐** — 绑定巡线跟随器，一次性预取所有 ops 指针 |
| **参数** | `follower` — [输出] 巡线跟随器对象 |
|  | `sensor_name` — 传感器名称；`pid_name` — PID 名称 |
|  | `left_motor` — 左电机名称；`right_motor` — 右电机名称 |
|  | `weights` — 权重数组（必须是静态/全局生命周期） |
|  | `base_speed` — 基础巡航速度 |
|  | `min_speed` — 最小速度限制（≥0 防反转） |
|  | `max_speed` — 最大速度限制（如 100） |
|  | `dt` — 控制周期（秒） |
| **返回值** | `EFW_OK`；`EFW_ERR_INVALID` follower/weights 为空或 dt≤0；`EFW_ERR_NOT_FOUND` 组件未注册 |
| **注意** | 必须在所有组件注册完成后调用 |

---

#### `efw_line_follower_update()`

```c
efw_status_t efw_line_follower_update(efw_line_follower_t *follower, float *out_error, float *out_turn);
```

| 项目 | 说明 |
|------|------|
| **作用** | **★ 每控制周期调用** — 使用缓存指针的完整循迹链路（read → weighted_error → PID → 限速差速） |
| **参数** | `follower` — 已绑定的巡线跟随器 |
|  | `out_error` — [输出] 本次加权误差（可 NULL） |
|  | `out_turn` — [输出] 本次 PID 输出转向量（可 NULL） |
| **返回值** | `EFW_OK`；`EFW_ERR_INVALID` follower 为空 |
| **优势** | ① 免字符串查找（O(1)）；② 自带速度限幅（min_speed/max_speed 防反转/超速） |

---

### 11.2 IMU 传感器

**头文件：** `efw/device/sensor/imu.h`

#### 数据结构

```c
typedef struct {
    float ax, ay, az;       // 加速度（m/s² 或 g）
    float gx, gy, gz;       // 角速度（°/s 或 rad/s）
    float mx, my, mz;       // 磁场强度（μT 或 Gauss，可选）
    float roll, pitch, yaw; // 融合姿态角（度）
} efw_imu_data_t;
```

#### `efw_imu_read()`

```c
efw_status_t efw_imu_read(const char *name, efw_imu_data_t *out);
```

| 项目 | 说明 |
|------|------|
| **作用** | 读取 IMU 数据（类型安全包装） |
| **参数** | `name` — 传感器名称；`out` — [输出] 12 字段 IMU 数据 |
| **返回值** | `EFW_OK`；`EFW_ERR_INVALID` out 为空 |

---

### 11.3 编码器传感器

**头文件：** `efw/device/sensor/encoder.h`

#### 数据结构

```c
typedef struct {
    int32_t count;      // 原始脉冲计数
    float position;     // 物理位置（count × 换算系数）
    float speed;        // 当前速度（position 时间差分）
} efw_encoder_data_t;
```

#### `efw_encoder_read()`

```c
efw_status_t efw_encoder_read(const char *name, efw_encoder_data_t *out);
```

| 项目 | 说明 |
|------|------|
| **作用** | 读取编码器数据 |
| **参数** | `name` — 传感器名称；`out` — [输出] 编码器数据 |
| **返回值** | `EFW_OK`；`EFW_ERR_INVALID` out 为空 |

---

### 11.4 超声波传感器

**头文件：** `efw/device/sensor/ultrasonic.h`

#### 数据结构

```c
typedef struct {
    float distance_m;   // 测量距离（米）
} efw_ultrasonic_data_t;
```

#### `efw_ultrasonic_read()`

```c
efw_status_t efw_ultrasonic_read(const char *name, efw_ultrasonic_data_t *out);
```

| 项目 | 说明 |
|------|------|
| **作用** | 读取超声波距离数据 |
| **参数** | `name` — 传感器名称；`out` — [输出] 距离数据 |
| **返回值** | `EFW_OK`；`EFW_ERR_INVALID` out 为空 |

---

### 11.5 自定义传感器

**头文件：** `efw/device/sensor/custom.h`

#### 数据结构

```c
typedef struct {
    uint32_t type_id;   // 用户自定义类型标识
    void *data;         // 数据指针
    uint16_t size;      // 数据大小（字节）
} efw_custom_sensor_data_t;
```

#### `efw_custom_sensor_read()`

```c
efw_status_t efw_custom_sensor_read(const char *name, void *out);
```

| 项目 | 说明 |
|------|------|
| **作用** | 读取自定义传感器（泛型版，仅校验 out 非空） |
| **参数** | `name` — 传感器名称；`out` — 输出缓冲区 |
| **返回值** | `EFW_OK`；`EFW_ERR_INVALID` out 为空 |

---

#### `efw_custom_sensor_read_data()`

```c
efw_status_t efw_custom_sensor_read_data(const char *name, efw_custom_sensor_data_t *out);
```

| 项目 | 说明 |
|------|------|
| **作用** | 读取自定义传感器（增强版，额外校验 data 非空 + size>0） |
| **参数** | `name` — 传感器名称；`out` — 含 type_id + data + size 的描述符 |
| **返回值** | `EFW_OK`；`EFW_ERR_INVALID` out/data 为空或 size 为 0 |

---

## 12. 执行器专项 API

### 12.1 电机执行器

**头文件：** `efw/device/actuator/motor.h`

#### 数据结构

```c
typedef struct {
    const char *left_motor;     // 左电机名称
    const char *right_motor;    // 右电机名称
    float base_speed;           // 基础速度
    float turn;                 // 转向修正量
} efw_motor_diff_cmd_t;
```

#### `efw_motor_write()`

```c
efw_status_t efw_motor_write(const char *name, float speed, float direction);
```

| 项目 | 说明 |
|------|------|
| **作用** | **底层 API** — 直接写入速度和方向 |
| **参数** | `name` — 电机名称；`speed` — 速度幅值（≥0） |
|  | `direction` — 方向（1.0=正转, -1.0=反转, 0.0=停止） |
| **返回值** | `EFW_OK`；其他来自 `efw_actuator_write` |

---

#### `efw_motor_set_speed()`

```c
efw_status_t efw_motor_set_speed(const char *name, float speed);
```

| 项目 | 说明 |
|------|------|
| **作用** | **★ 最常用单电机 API** — 符号自动分离。正=前进, 负=后退 |
| **参数** | `name` — 电机名称；`speed` — 带方向的速率值 |
| **返回值** | `EFW_OK`；其他来自底层 |
| **内部逻辑** | `abs(speed)` → 幅值，`sign(speed)` → 方向 |

---

#### `efw_motor_stop()`

```c
efw_status_t efw_motor_stop(const char *name);
```

| 项目 | 说明 |
|------|------|
| **作用** | 紧急停止 — speed=0, direction=0 |
| **参数** | `name` — 电机名称 |

---

#### `efw_motor_set_diff()`

```c
efw_status_t efw_motor_set_diff(const char *left_motor, const char *right_motor,
                                float base_speed, float turn);
```

| 项目 | 说明 |
|------|------|
| **作用** | **差速驱动（无速度限制）** |
| **参数** | `left_motor` — 左电机名称；`right_motor` — 右电机名称 |
|  | `base_speed` — 基础巡航速度；`turn` — 转向修正量（正=右转, 负=左转） |
| **公式** | `left = base_speed - turn`，`right = base_speed + turn` |
| **警告** | 无速度限制！turn 过大可导致反转。推荐使用 `_limited` 版本 |

---

#### `efw_motor_set_diff_limited()`

```c
efw_status_t efw_motor_set_diff_limited(const char *left_motor, const char *right_motor,
                                        float base_speed, float turn,
                                        float min_speed, float max_speed);
```

| 项目 | 说明 |
|------|------|
| **作用** | **★ 限速差速驱动（推荐）** — 每轮速度 clamp 在 [min, max] |
| **参数** | 前 4 个同 `set_diff` |
|  | `min_speed` — 最小速度限制（设 0 可防反转） |
|  | `max_speed` — 最大速度限制（如 100） |
| **公式** | `left = clamp(base-turn, min, max)`，`right = clamp(base+turn, min, max)` |

---

## 13. 算法专项 API

### 13.1 PID 控制器

**头文件：** `efw/algorithm/control/pid.h`

#### 数据结构

```c
typedef struct {
    float kp;               // 比例系数
    float ki;               // 积分系数
    float kd;               // 微分系数
    float kff;              // 前馈系数（Kff × setpoint = 静态前馈，0=不用）
    float integral;         // [内部] 积分累积值
    float prev_error;       // [内部] 上一次误差
    float integral_min;     // 积分下限（integral_min < integral_max 时生效）
    float integral_max;     // 积分上限
    float out_min;          // 输出下限
    float out_max;          // 输出上限
    uint8_t anti_windup;    // 抗积分饱和开关（1=开启）
} efw_pid_t;

typedef struct {
    float setpoint;         // 设定值（目标）
    float feedback;         // 反馈值（实测）
    float dt;               // 时间间隔（秒），必须 > 0
    float feedforward;      // 动态前馈（每次可不同），默认填 0
} efw_pid_input_t;

typedef struct {
    float output;           // 控制器输出（已限幅）
    float error;            // 当前误差（setpoint - feedback）
    float feedforward;      // 本次实际总前馈量（input.ff + Kff×setpoint）
} efw_pid_output_t;
```

#### `efw_pid_reset()`

```c
void efw_pid_reset(efw_pid_t *pid);
```

| 项目 | 说明 |
|------|------|
| **作用** | 重置 PID 状态：清零 integral 和 prev_error |
| **参数** | `pid` — PID 实例指针。为 NULL 则安全返回 |
| **调用时机** | 设定值大幅跳变、系统重启、手动切回自动时 |

---

#### `efw_pid_run()`

```c
efw_status_t efw_pid_run(void *ctx, const void *in, void *out);
```

| 项目 | 说明 |
|------|------|
| **作用** | **★ 执行一次 PID 计算**（可注册为 algo_ops.run） |
| **参数** | `ctx` — 指向 `efw_pid_t`；`in` — 指向 `efw_pid_input_t` |
|  | `out` — 指向 `efw_pid_output_t`（结果写回） |
| **返回值** | `EFW_OK`；`EFW_ERR_INVALID` — ctx/in/out 为空或 dt≤0 |
| **公式** | 见 pid.h 完整公式（前馈 + 积分限幅 + 抗积分饱和 + 输出钳位） |

---

### 13.2 滑动均值滤波器

**头文件：** `efw/algorithm/filter/moving_average.h`

#### 数据结构

```c
typedef struct {
    float *buffer;          // [用户分配] 环形缓冲区
    uint16_t capacity;      // 窗口大小 N（必须 > 0）
    uint16_t count;         // [内部] 当前样本数（≤ capacity）
    uint16_t index;         // [内部] 写入位置
    float sum;              // [内部] 当前窗口总和（O(1) 关键）
} efw_moving_avg_t;
```

#### `efw_moving_avg_reset()`

```c
void efw_moving_avg_reset(efw_moving_avg_t *avg);
```

| 项目 | 说明 |
|------|------|
| **作用** | 重置滤波器：清零 count/index/sum。下次从填窗阶段重新开始 |
| **参数** | `avg` — 滤波器实例。为 NULL 则安全返回 |
| **调用时机** | 切换信号源、传感器重标定、系统唤醒 |

---

#### `efw_moving_avg_run()`

```c
efw_status_t efw_moving_avg_run(void *ctx, const void *in, void *out);
```

| 项目 | 说明 |
|------|------|
| **作用** | **★ 执行一次滑动均值计算（O(1)）** — 可注册为 algo_ops.run |
| **参数** | `ctx` — 指向 `efw_moving_avg_t`；`in` — 指向 float（新采样值） |
|  | `out` — 指向 float（滤波后的均值写回） |
| **返回值** | `EFW_OK`；`EFW_ERR_INVALID` — buffer/ctx/in/out 为空或 capacity=0 |
| **两阶段** | 填窗期（count<N）直接追加；稳定期（count=N）增量替换 |
| **复杂度** | O(1)，与窗口大小 N 无关 |

---

## 14. 诊断系统

**头文件：** `efw/core/diagnostic.h`
**源文件：** `src/core/diagnostic.c`

诊断系统提供全局"最后一次错误"记录，用于调试和错误定位。所有注册表在注册失败时自动调用 `efw_diag_set()` 记录失败原因。

### 数据结构

#### `efw_error_t` — 错误信息

```c
typedef struct {
    efw_status_t code;      // 错误码（与 API 返回值一致）
    const char *module;     // 出错模块名（"hal", "sensor", "actuator", "algo"）
    const char *name;       // 出错组件名（可为 NULL）
    const char *message;    // 错误描述（"invalid pool", "duplicate name", "pool full"）
} efw_error_t;
```

### API 函数

#### `efw_diag_clear()`

```c
void efw_diag_clear(void);
```

| 项目 | 说明 |
|------|------|
| **作用** | 清除诊断状态：code=EFW_OK, 所有指针设为 NULL |
| **调用时机** | 初始化前调用，避免残留旧错误 |

#### `efw_diag_set()`

```c
void efw_diag_set(efw_status_t code, const char *module, const char *name, const char *message);
```

| 项目 | 说明 |
|------|------|
| **作用** | 记录错误信息。框架内部自动调用。用户也可在自定义回调中调用 |
| **参数** | `code` — 错误码；`module` — 模块标识字符串 |
|  | `name` — 组件名称（无名称传 NULL）；`message` — 错误描述字符串 |
| **注意** | 所有字符串参数应指向字面量或静态缓冲区——本函数不拷贝，只存指针 |

#### `efw_diag_last_error()`

```c
const efw_error_t *efw_diag_last_error(void);
```

| 项目 | 说明 |
|------|------|
| **作用** | 获取最后一次错误信息 |
| **返回值** | 指向全局静态 `efw_error_t` 的指针（始终有效，永不返回 NULL） |

### 使用示例

```c
efw_status_t s = efw_sensor_register(&my_sensor);
if (s != EFW_OK) {
    const efw_error_t *e = efw_diag_last_error();
    // e->code    → EFW_ERR_FULL (或其它错误码)
    // e->module  → "sensor"
    // e->name    → "my_sensor" (或 NULL)
    // e->message → "pool full" (或 "duplicate name", "invalid ops")
}
```

---

## 15. 事件总线

**头文件：** `efw/core/event.h`
**源文件：** `src/core/event.c`
**编译开关：** `EFW_ENABLE_EVENT`（默认 1）

基于 topic_id 的发布-订阅轻量级消息系统，允许多个模块间解耦通信。

### 类型定义

#### `efw_topic_cb_t` — 话题回调函数类型

```c
typedef void (*efw_topic_cb_t)(uint16_t topic_id, const void *data, uint16_t size, void *user);
```

| 参数 | 说明 |
|------|------|
| `topic_id` | 触发回调的话题 ID |
| `data` | 发布者传入的数据指针（类型由 topic 约定） |
| `size` | 数据大小（字节） |
| `user` | 订阅时传入的用户自定义指针 |

### API 函数

#### `efw_topic_clear()`

```c
efw_status_t efw_topic_clear(void);
```

| 项目 | 说明 |
|------|------|
| **作用** | 清空所有订阅关系（计数归零） |

#### `efw_topic_subscribe()`

```c
efw_status_t efw_topic_subscribe(uint16_t topic_id, efw_topic_cb_t cb, void *user);
```

| 项目 | 说明 |
|------|------|
| **作用** | 订阅指定话题 |
| **参数** | `topic_id` — 话题 ID；`cb` — 回调函数（不可为空）；`user` — 用户指针（可为 NULL） |
| **返回值** | `EFW_OK` / `EFW_ERR_INVALID`（cb为空）/ `EFW_ERR_FULL`（订阅者达上限） |
| **容量** | 最大订阅数由 `EFW_MAX_TOPIC_SUBS`（默认 8）控制 |

#### `efw_topic_publish()`

```c
efw_status_t efw_topic_publish(uint16_t topic_id, const void *data, uint16_t size);
```

| 项目 | 说明 |
|------|------|
| **作用** | 发布话题 —— 同步遍历所有订阅者，匹配 topic_id 则调用回调 |
| **参数** | `topic_id` — 话题 ID；`data` — 数据指针（可为 NULL）；`size` — 数据大小 |
| **返回值** | 始终返回 `EFW_OK`（单个回调失败不影响其他订阅者） |
| **复杂度** | O(n)，n=总订阅数 |

---

## 16. 新增算法专项

### 16.1 一阶低通滤波器

**头文件：** `efw/algorithm/filter/low_pass.h`
**编译开关：** `EFW_ENABLE_ALGO_LOW_PASS`（默认 1）

#### 公式

```
state += α × (sample - state)
等价于: state = α×sample + (1-α)×state
```

- `α=1.0` → 无滤波（完全信任新值）
- `α=0.5` → 中度平滑
- `α=0.01` → 强平滑（响应慢，噪声抑制强）

#### 数据结构

```c
typedef struct {
    float alpha;           // 平滑系数 [0, 1]
    float state;           // [内部] 当前滤波输出
    uint8_t initialized;   // [内部] 首次调用标记
} efw_low_pass_t;
```

#### `efw_low_pass_reset()`

```c
void efw_low_pass_reset(efw_low_pass_t *filter, float value);
```

| 项目 | 说明 |
|------|------|
| **作用** | 重置滤波器，直接设 state=value 并标记已初始化 |
| **参数** | `filter` — 滤波器实例；`value` — 初始值 |

#### `efw_low_pass_run()`

```c
efw_status_t efw_low_pass_run(void *ctx, const void *in, void *out);
```

| 项目 | 说明 |
|------|------|
| **作用** | 执行一次低通滤波。首次调用自动用 sample 初始化 state |
| **参数** | `ctx` → `efw_low_pass_t*`；`in` → `float*`；`out` → `float*` |
| **返回值** | `EFW_OK` / `EFW_ERR_INVALID`（alpha 超出 [0,1] 或参数为空） |

#### 参数调节

| α 范围 | 平滑程度 | 适用场景 |
|--------|---------|---------|
| 0.01~0.05 | 强平滑 | 温度、湿度等缓变信号 |
| 0.1~0.2 | 中度平滑 | ADC 采样、电池电压 |
| 0.3~0.5 | 轻度平滑 | IMU 角速度等高频信号 |
| 0.8~1.0 | 几乎无滤波 | 仅去极端毛刺 |

等效截止频率估算：fc ≈ α / (2π × dt)

---

### 16.2 斜坡控制器

**头文件：** `efw/algorithm/control/ramp.h`
**编译开关：** `EFW_ENABLE_ALGO_RAMP`（默认 1）

限制输出值的变化速率，防止目标值阶跃导致执行器冲击。

#### 公式

```
delta = target - value
limit = rate × dt              （上升用 rise_rate，下降用 fall_rate）
if (delta > limit)  delta = limit
if (delta < -limit) delta = -limit
value += delta
```

#### 数据结构

```c
typedef struct {
    float value;        // [内部] 当前斜坡输出
    float rise_rate;    // 上升速率 (>0, 单位/秒)
    float fall_rate;    // 下降速率 (>0, 单位/秒)
} efw_ramp_t;

typedef struct {
    float target;       // 目标值
    float dt;           // 时间间隔 (秒)
} efw_ramp_input_t;
```

#### `efw_ramp_reset()`

```c
void efw_ramp_reset(efw_ramp_t *ramp, float value);
```

| 项目 | 说明 |
|------|------|
| **作用** | 直接跳到指定值（跳过斜坡），用于初始化 |
| **参数** | `ramp` — 控制器实例；`value` — 起始值 |

#### `efw_ramp_run()`

```c
efw_status_t efw_ramp_run(void *ctx, const void *in, void *out);
```

| 项目 | 说明 |
|------|------|
| **作用** | 执行一次斜坡计算 |
| **参数** | `ctx` → `efw_ramp_t*`；`in` → `efw_ramp_input_t*`；`out` → `float*` |
| **返回值** | `EFW_OK` / `EFW_ERR_INVALID`（dt≤0 或 rate<0） |

#### 参数调节

- `rise_rate` — 上升速率。电机：100~500 单位/秒；LED 渐变：50~200
- `fall_rate` — 下降速率。通常 ≤ rise_rate（减速比加速更平滑）
- 建议从较小值开始测试，逐步增大到响应可接受

---

### 16.3 编码器速度估算器

**头文件：** `efw/algorithm/estimator/encoder_speed.h`
**编译开关：** `EFW_ENABLE_ALGO_ENCODER_SPEED`（默认 1）

从编码器脉冲计数推算转速/线速度。首次调用自动记录初始 count 并返回 speed=0。

#### 公式

```
speed = ((count_now - count_prev) / pulses_per_unit) / dt
```

#### 数据结构

```c
typedef struct {
    int32_t prev_count;         // [内部] 上次脉冲计数
    float pulses_per_unit;      // 每物理单位的脉冲数 (必须 > 0)
    uint8_t initialized;        // [内部] 首次调用标记
} efw_encoder_speed_t;

typedef struct {
    int32_t count;              // 当前脉冲计数值
    float dt;                   // 时间间隔 (秒)
} efw_encoder_speed_input_t;
```

#### `efw_encoder_speed_run()`

```c
efw_status_t efw_encoder_speed_run(void *ctx, const void *in, void *out);
```

| 项目 | 说明 |
|------|------|
| **作用** | 执行一次速度估算 |
| **参数** | `ctx` → `efw_encoder_speed_t*`；`in` → `efw_encoder_speed_input_t*`；`out` → `float*` |
| **返回值** | `EFW_OK` / `EFW_ERR_INVALID`（pulses_per_unit=0 或参数非法） |

#### 参数调节

- `pulses_per_unit` — 唯一需要设置的参数。例如：编码器 1000 线 + 4 倍频 = 4000 脉冲/转
- 低速时速度分辨率低（相邻 count 差为 0/1），推荐配合低通滤波使用

---

### 16.4 互补滤波器（姿态估计）

**头文件：** `efw/algorithm/estimator/attitude_complementary.h`
**编译开关：** `EFW_ENABLE_ALGO_ATTITUDE_COMPLEMENTARY`（默认 1）

融合加速度计和陀螺仪数据，估算 roll/pitch 姿态角。只计算 roll 和 pitch，不支持 yaw。

#### 公式

```
accel_roll  = atan2(ay, az) × 180/π
accel_pitch = atan2(-ax, √(ay²+az²)) × 180/π

roll  = α×(roll + gx×dt)  + (1-α)×accel_roll
pitch = α×(pitch + gy×dt) + (1-α)×accel_pitch
```

- α=0.98：98% 信任陀螺仪（动态快），2% 信任加速度计（缓慢修正漂移）

#### 数据结构

```c
typedef struct {
    float roll, pitch;      // [内部] 姿态角 (度)
    float alpha;            // 陀螺仪权重 (0~1, 推荐 0.98)
    uint8_t initialized;    // [内部] 首次调用标记
} efw_attitude_complementary_t;

typedef struct {
    float ax, ay, az;       // 加速度计 (任意单位)
    float gx, gy;           // 陀螺仪角速度 (°/s)
    float dt;               // 时间间隔 (秒)
} efw_attitude_input_t;

typedef struct {
    float roll;             // 横滚角 (度)
    float pitch;            // 俯仰角 (度)
} efw_attitude_output_t;
```

#### `efw_attitude_complementary_run()`

```c
efw_status_t efw_attitude_complementary_run(void *ctx, const void *in, void *out);
```

| 项目 | 说明 |
|------|------|
| **作用** | 执行一次互补滤波姿态估计。首次调用用加速度计角度初始化 |
| **参数** | `ctx` → `efw_attitude_complementary_t*`；`in` → `efw_attitude_input_t*`；`out` → `efw_attitude_output_t*` |
| **返回值** | `EFW_OK` / `EFW_ERR_INVALID`（alpha 超出 [0,1] 或参数非法） |
| **依赖** | 需要链接 `atan2()` 和 `sqrt()`（标准库 math） |

#### 参数调节

| α 值 | 特性 | 适用场景 |
|------|------|---------|
| 0.98 | 陀螺仪主导 | **推荐默认值**，适合大多数场景 |
| 0.95 | 更多加速度计修正 | 振动环境（加速度计噪声大） |
| 0.99 | 几乎纯陀螺仪 | 剧烈运动（运动加速度干扰大） |

口诀：角度漂移（不准）→ 减小 α；角度抖动（噪声）→ 增大 α

---

## 17. 注册表扩展功能

### 17.1 自定义内存池（`_init_pool` 系列）

HAL、SENSOR、ACTUATOR、ALGORITHM 四个注册表支持用户自定义内存池，替代框架默认的静态数组。

**背景：** 默认注册表使用 `g_xxx[EFW_MAX_XXX]` 静态数组。在 RAM 极度紧张的场景下，用户可以提供恰好大小的池，避免浪费。

```c
// HAL
efw_status_t efw_hal_registry_init_pool(const efw_hal_ops_t **pool, size_t capacity);

// SENSOR
efw_status_t efw_sensor_registry_init_pool(const efw_sensor_ops_t **pool, size_t capacity);

// ACTUATOR
efw_status_t efw_actuator_registry_init_pool(const efw_actuator_ops_t **pool, size_t capacity);

// ALGORITHM
efw_status_t efw_algo_registry_init_pool(const efw_algo_ops_t **pool, size_t capacity);
```

| 项目 | 说明 |
|------|------|
| **作用** | 用用户提供的指针数组替代默认静态数组 |
| **参数** | `pool` — 用户分配的指针数组（必须非空，capacity>0）；`capacity` — 池容量 |
| **返回值** | `EFW_OK` / `EFW_ERR_INVALID`（pool 为空或 capacity=0） |
| **调用时机** | 在注册任何实例之前调用，替代 `efw_xxx_registry_init()` |

**使用示例：**

```c
// 已知只需要 3 个传感器，而不是默认的 32 个
const efw_sensor_ops_t *my_sensor_pool[3];
efw_sensor_registry_init_pool(my_sensor_pool, 3);  // 仅占 12 字节 (3×4)
efw_sensor_register(&sensor1);
efw_sensor_register(&sensor2);
efw_sensor_register(&sensor3);
// efw_sensor_register(&sensor4);  // → EFW_ERR_FULL（池已满）
```

**RAM 对比：** 默认 32 槽 × 4 字节 = 128 字节 → 自定义 3 槽 = 12 字节（节省 116 字节）

### 17.2 诊断集成的注册失败信息

所有带 `_pool` 的注册表在失败时自动调用 `efw_diag_set()`，记录以下信息：

| 失败原因 | module | name | message |
|---------|--------|------|---------|
| 参数非法（name 为空） | "hal"/"sensor"/"actuator"/"algo" | NULL | "invalid ops" |
| 名称重复 | 同上 | ops->name | "duplicate name" |
| 池已满 | 同上 | ops->name | "pool full" |
| 池无效（init_pool） | 同上 | NULL | "invalid pool" |

这使得调试注册失败时可以通过 `efw_diag_last_error()` 获取精确的错误上下文。

### 17.3 Keil 单文件编译入口

**文件：** `src/efw_all.c`

提供聚合编译入口，Keil/IAR 等 IDE 只需将这一个 .c 文件加入工程。CMake 项目不使用此文件。

```c
#include "core/init.c"
#include "core/diagnostic.c"
#if EFW_ENABLE_EVENT
#include "core/event.c"
#endif
// ... 条件包含所有模块的 .c 文件
```

`same_name` 和 `clamp_float` 等静态函数通过 `#define` 重命名避免链接冲突。
