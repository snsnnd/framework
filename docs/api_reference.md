# EFW API 参考手册

## 目录

1. [初始化](#1-初始化)
2. [诊断系统](#2-诊断系统)
3. [HAL 硬件抽象层](#3-hal-硬件抽象层)
4. [COMM 通信层](#4-comm-通信层)
5. [Sensor 传感器](#5-sensor-传感器)
6. [Actuator 执行器](#6-actuator-执行器)
7. [Algorithm 算法](#7-algorithm-算法)
8. [Module 模块](#8-module-模块)
9. [状态机引擎](#9-状态机引擎)
10. [事件总线](#10-事件总线)
11. [调度器](#11-调度器)
12. [数据结构](#12-数据结构)

---

## 1. 初始化

### `efw_init()`

按依赖顺序初始化所有已启用的注册表。

```c
efw_status_t efw_init(void);
```

**初始化顺序**: HAL → COMM → MODULE → SENSOR → ACTUATOR → ALGORITHM → STATE_MACHINE → EVENT → SCHEDULER

**返回**: `EFW_OK` 成功，否则返回第一个失败的错误码。

**示例**:
```c
int main(void) {
    if (efw_init() != EFW_OK) {
        // 处理初始化失败
    }
    // 注册组件...
}
```

---

## 2. 诊断系统

### `efw_diag_clear()`

清除所有诊断状态（最后错误、历史、计数器）。

```c
void efw_diag_clear(void);
```

### `efw_diag_set()`

记录一条错误到诊断系统。同时更新最后错误和环形历史缓冲区。

```c
void efw_diag_set(efw_status_t code, const char *module, const char *name, const char *message);
```

**参数**:
- `code` - 错误码
- `module` - 模块标识（如 `"sensor"`、`"hal"`）
- `name` - 组件名（可为 NULL）
- `message` - 错误描述

### `efw_diag_last_error()`

获取最后一条错误。

```c
const efw_error_t *efw_diag_last_error(void);
```

**返回**: 指向静态 `efw_error_t` 的指针，始终有效。

### `efw_diag_error_count()`

获取累计错误总数。

```c
uint32_t efw_diag_error_count(void);
```

### `efw_diag_history_entry()`

按索引读取历史错误（环形缓冲区）。

```c
const efw_error_t *efw_diag_history_entry(uint8_t index);
```

**参数**: `index` - 0 到 `EFW_ERROR_HISTORY_SIZE-1`

**示例**:
```c
const efw_error_t *err = efw_diag_last_error();
if (err->code != EFW_OK) {
    printf("[%s] %s: %s\n", err->module, err->name, err->message);
}
```

---

## 3. HAL 硬件抽象层

### `efw_hal_register()`

注册一个 HAL 实例。

```c
efw_status_t efw_hal_register(const efw_hal_ops_t *ops);
```

### `efw_hal_get()`

按名称查找 HAL。

```c
efw_status_t efw_hal_get(const char *name, const efw_hal_ops_t **out_ops);
```

### `efw_hal_read()` / `efw_hal_write()` / `efw_hal_ioctl()`

便捷操作：查找 + 调用回调。

```c
efw_status_t efw_hal_read(const char *name, void *buf, uint16_t len, uint16_t *actual);
efw_status_t efw_hal_write(const char *name, const void *buf, uint16_t len, uint16_t *actual);
efw_status_t efw_hal_ioctl(const char *name, uint32_t cmd, void *arg);
```

### `efw_hal_registry_init_pool()`

使用自定义容量的指针池初始化注册表。

```c
efw_status_t efw_hal_registry_init_pool(const efw_hal_ops_t **pool, size_t capacity);
```

### `efw_hal_ops_t` 结构体

```c
typedef struct {
    const char *name;
    efw_hal_type_t type;
    uint8_t bus_id;
    void *ctx;
    efw_status_t (*init)(void *ctx);
    efw_status_t (*read)(void *ctx, void *buf, uint16_t len, uint16_t *actual);
    efw_status_t (*write)(void *ctx, const void *buf, uint16_t len, uint16_t *actual);
    efw_status_t (*ioctl)(void *ctx, uint32_t cmd, void *arg);
} efw_hal_ops_t;
```

---

## 4. COMM 通信层

### `efw_comm_register()`

注册一个 COMM 实例。注册时校验 `hal_name` 引用的 HAL 是否存在。

```c
efw_status_t efw_comm_register(const efw_comm_ops_t *ops);
```

### `efw_comm_registry_init_pool()`

使用自定义容量初始化 COMM 注册表。

```c
efw_status_t efw_comm_registry_init_pool(const efw_comm_ops_t **pool, size_t capacity);
```

### `efw_comm_send()` / `efw_comm_recv()`

```c
efw_status_t efw_comm_send(const char *name, const uint8_t *data, uint16_t len, uint16_t *actual);
efw_status_t efw_comm_recv(const char *name, uint8_t *data, uint16_t len, uint16_t *actual);
```

---

## 5. Sensor 传感器

### `efw_sensor_register()`

注册传感器。注册时校验 `hal_name`/`comm_name` 引用是否存在。

```c
efw_status_t efw_sensor_register(const efw_sensor_ops_t *ops);
```

### `efw_sensor_read()`

按名称读取传感器数据。

```c
efw_status_t efw_sensor_read(const char *name, void *out);
```

### `efw_sensor_ops_t` 结构体

```c
typedef struct {
    const char *name;
    efw_sensor_type_t type;
    uint8_t channel_count;
    const char *hal_name;
    const char *comm_name;
    void *ctx;
    efw_status_t (*init)(void *ctx);
    efw_status_t (*read)(void *ctx, void *out);
} efw_sensor_ops_t;
```

---

## 6. Actuator 执行器

### `efw_actuator_register()`

注册执行器。

```c
efw_status_t efw_actuator_register(const efw_actuator_ops_t *ops);
```

### `efw_actuator_enable()` / `efw_actuator_disable()` / `efw_actuator_write()`

```c
efw_status_t efw_actuator_enable(const char *name);
efw_status_t efw_actuator_disable(const char *name);
efw_status_t efw_actuator_write(const char *name, const void *cmd);
```

---

## 7. Algorithm 算法

### `efw_algo_register()`

注册算法实例。

```c
efw_status_t efw_algo_register(const efw_algo_ops_t *ops);
```

### `efw_algo_run()`

按名称运行算法 = 查找 + 调用 run 回调。

```c
efw_status_t efw_algo_run(const char *name, const void *in, void *out);
```

### `efw_algo_ops_t` 结构体

```c
typedef struct {
    const char *name;
    efw_algo_type_t type;
    void *ctx;
    efw_status_t (*run)(void *ctx, const void *in, void *out);
} efw_algo_ops_t;
```

### 内置算法: PID

```c
typedef struct {
    float kp, ki, kd, kff;
    float integral, prev_error;
    float integral_min, integral_max;
    float out_min, out_max;
    uint8_t anti_windup;
} efw_pid_t;

void efw_pid_reset(efw_pid_t *pid);
efw_status_t efw_pid_run(void *ctx, const void *in, void *out);
```

---

## 8. Module 模块

### `efw_module_register()`

注册模块。

```c
efw_status_t efw_module_register(const efw_module_ops_t *ops);
```

### 批量操作

```c
efw_status_t efw_module_init_all(void);
efw_status_t efw_module_start_all(void);
efw_status_t efw_module_poll_all(void);
```

**注意**: `poll_all` 不会因单个模块失败而停止。失败的模块错误记录到诊断系统，继续执行后续模块。返回第一个失败的错误码。

### `efw_module_ops_t` 结构体

```c
typedef struct {
    const char *name;
    efw_module_type_t type;
    void *ctx;
    efw_status_t (*init)(void *ctx);
    efw_status_t (*start)(void *ctx);
    efw_status_t (*stop)(void *ctx);
    efw_status_t (*poll)(void *ctx);
} efw_module_ops_t;
```

---

## 9. 状态机引擎

### 概述

状态机引擎提供完整的状态转移支持，包括：
- 状态定义（on_enter/on_tick/on_exit）
- 转移表（条件 + 超时 + 优先级）
- 自动 on_exit/on_enter 调用
- 当前状态追踪

### `efw_sm_init()`

初始化状态机上下文。

```c
efw_status_t efw_sm_init(efw_sm_context_t *ctx, const efw_state_def_t *initial,
                          const efw_sm_transition_t *transitions, uint8_t count);
```

**参数**:
- `ctx` - 状态机上下文（调用方分配）
- `initial` - 初始状态定义
- `transitions` - 转移表数组
- `count` - 转移表条目数

### `efw_sm_tick()`

状态机主循环调用。执行当前状态的 on_tick，然后按优先级评估转移条件。

```c
efw_status_t efw_sm_tick(efw_sm_context_t *ctx);
```

**转移评估逻辑**:
1. 执行当前状态的 `on_tick`
2. 按优先级从高到低遍历转移表
3. 对每个转移检查：from 匹配当前状态、condition() 为真或 timeout 到达
4. 第一个满足的转移执行：调用 action() → on_exit → 切换状态 → on_enter

### `efw_sm_transition_to()`

强制转移到指定状态（跳过条件评估）。

```c
efw_status_t efw_sm_transition_to(efw_sm_context_t *ctx, const efw_state_def_t *target);
```

### `efw_sm_set_elapsed()`

更新状态机的经过时间（用于超时转移）。

```c
void efw_sm_set_elapsed(efw_sm_context_t *ctx, uint32_t elapsed_ms);
```

### 查询函数

```c
const char *efw_sm_current_state(const efw_sm_context_t *ctx);
const efw_state_def_t *efw_sm_current_def(const efw_sm_context_t *ctx);
uint32_t efw_sm_time_in_state(const efw_sm_context_t *ctx);
```

### `efw_state_def_t` 结构体

```c
typedef struct {
    const char *name;
    void *ctx;
    efw_status_t (*on_enter)(void *ctx);
    efw_status_t (*on_tick)(void *ctx);
    efw_status_t (*on_exit)(void *ctx);
} efw_state_def_t;
```

### `efw_sm_transition_t` 结构体

```c
typedef struct {
    const efw_state_def_t *from;   // NULL = 任意状态
    const efw_state_def_t *to;     // 目标状态
    int (*condition)(void);        // NULL = 不检查条件
    efw_status_t (*action)(void);  // NULL = 无动作
    uint32_t timeout_ms;           // 0 = 不检查超时
    uint8_t priority;              // 越大越先评估
} efw_sm_transition_t;
```

### 完整示例

```c
static efw_status_t state_idle_on_enter(void *ctx) { /* 初始化 */ return EFW_OK; }
static efw_status_t state_idle_on_tick(void *ctx) { /* 空闲逻辑 */ return EFW_OK; }
static efw_status_t state_run_on_tick(void *ctx) { /* 运行逻辑 */ return EFW_OK; }
static int check_sensor_ready(void) { return sensor_data_available(); }
static efw_status_t start_motors(void) { motor_enable(); return EFW_OK; }

static const efw_state_def_t s_idle = {
    .name = "idle", .on_enter = state_idle_on_enter, .on_tick = state_idle_on_tick
};
static const efw_state_def_t s_running = {
    .name = "running", .on_tick = state_run_on_tick
};

static const efw_sm_transition_t s_transitions[] = {
    { .from = &s_idle, .to = &s_running, .condition = check_sensor_ready,
      .action = start_motors, .priority = 10 },
    { .from = &s_idle, .to = &s_running, .timeout_ms = 5000, .priority = 1 },
};

static efw_sm_context_t s_sm;

void app_init(void) {
    efw_sm_init(&s_sm, &s_idle, s_transitions, 2);
}

void app_loop(void) {
    efw_sm_set_elapsed(&s_sm, get_tick_ms());
    efw_sm_tick(&s_sm);
}
```

---

## 10. 事件总线

### 订阅/取消订阅

```c
efw_status_t efw_topic_subscribe(uint16_t topic_id, efw_topic_cb_t cb, void *user);
efw_status_t efw_topic_unsubscribe(uint16_t topic_id, efw_topic_cb_t cb);
```

### 发布

```c
efw_status_t efw_topic_publish(uint16_t topic_id, const void *data, uint16_t size);
```

同步调用所有匹配 topic_id 的订阅者回调。

### 事件队列

延迟发布机制。post 将事件入队，process 遍历队列并调用 publish。

```c
efw_status_t efw_event_queue_init(void);
efw_status_t efw_event_queue_post(uint16_t topic_id, const void *data, uint16_t size);
efw_status_t efw_event_queue_process(void);
uint8_t efw_event_queue_count(void);
```

**示例**:
```c
#define TOPIC_SENSOR_DATA 1

void on_sensor(uint16_t id, const void *data, uint16_t size, void *user) {
    // 处理传感器数据
}

void app_init(void) {
    efw_topic_subscribe(TOPIC_SENSOR_DATA, on_sensor, NULL);
}

void app_loop(void) {
    float value = read_sensor();
    efw_event_queue_post(TOPIC_SENSOR_DATA, &value, sizeof(value));
    efw_event_queue_process();  // 同步派发所有排队事件
}
```

---

## 11. 调度器

多周期任务调度器。注册任务时指定周期，tick 时自动执行到期任务。

### `efw_scheduler_init()`

初始化调度器。

```c
efw_status_t efw_scheduler_init(void);
```

### `efw_scheduler_register()`

注册一个周期任务。

```c
efw_status_t efw_scheduler_register(const efw_scheduler_task_t *task);
```

### `efw_scheduler_tick()`

主循环调用，执行所有到期任务。

```c
efw_status_t efw_scheduler_tick(uint32_t elapsed_ms);
```

### `efw_scheduler_task_t` 结构体

```c
typedef struct {
    const char *name;
    uint32_t period_ms;
    efw_task_fn_t fn;      // efw_status_t (*)(void *ctx)
    void *ctx;
} efw_scheduler_task_t;
```

### 示例

```c
static efw_status_t read_sensors(void *ctx) {
    float *data = (float *)ctx;
    *data = read_adc();
    return EFW_OK;
}

static efw_status_t update_pid(void *ctx) {
    return efw_algo_run("motor_pid", &pid_in, &pid_out);
}

static const efw_scheduler_task_t s_tasks[] = {
    { .name = "sensor_read", .period_ms = 10, .fn = read_sensors, .ctx = &sensor_data },
    { .name = "pid_update",  .period_ms = 1,  .fn = update_pid,  .ctx = 0 },
};

void app_init(void) {
    efw_scheduler_init();
    for (int i = 0; i < 2; ++i) {
        efw_scheduler_register(&s_tasks[i]);
    }
}

void app_loop_1ms(void) {
    efw_scheduler_tick(get_elapsed_ms());
}
```

---

## 12. 数据结构

### 环形缓冲区 `efw_ringbuf_t`

字节级环形缓冲区，适用于 UART 接收缓冲等。

```c
efw_status_t efw_ringbuf_init(efw_ringbuf_t *rb, void *buffer, size_t capacity);
efw_status_t efw_ringbuf_push(efw_ringbuf_t *rb, uint8_t value);
efw_status_t efw_ringbuf_pop(efw_ringbuf_t *rb, uint8_t *out);
size_t efw_ringbuf_write(efw_ringbuf_t *rb, const void *data, size_t len);
size_t efw_ringbuf_read(efw_ringbuf_t *rb, void *out, size_t len);
int efw_ringbuf_empty(const efw_ringbuf_t *rb);
int efw_ringbuf_full(const efw_ringbuf_t *rb);
```

### 队列 `efw_queue_t`

固定长度 FIFO，适用于命令队列等。

```c
efw_status_t efw_queue_init(efw_queue_t *q, void *buffer, size_t item_size, size_t capacity);
efw_status_t efw_queue_push(efw_queue_t *q, const void *item);
efw_status_t efw_queue_pop(efw_queue_t *q, void *out);
efw_status_t efw_queue_peek(const efw_queue_t *q, void *out);
```

### 栈 `efw_stack_t`

固定长度 LIFO。

```c
efw_status_t efw_stack_init(efw_stack_t *s, void *buffer, size_t item_size, size_t capacity);
efw_status_t efw_stack_push(efw_stack_t *s, const void *item);
efw_status_t efw_stack_pop(efw_stack_t *s, void *out);
```

---

## 状态码

| 状态码 | 值 | 含义 |
|--------|-----|------|
| `EFW_OK` | 0 | 成功 |
| `EFW_ERR_INVALID` | -1 | 参数无效 |
| `EFW_ERR_FULL` | -2 | 注册表已满 |
| `EFW_ERR_NOT_FOUND` | -3 | 未找到 |
| `EFW_ERR_ALREADY_EXISTS` | -4 | 名称冲突 |
| `EFW_ERR_NOT_READY` | -5 | 未就绪 |
| `EFW_ERR_IO` | -6 | IO 错误 |
| `EFW_ERR_RANGE` | -7 | 参数越界 |
| `EFW_ERR_UNSUPPORTED` | -8 | 不支持 |

---

## 编译配置

通过编译器 `-D` 选项或在 `config.h` 前定义宏来裁剪功能：

```bash
gcc -DEFW_ENABLE_COMM=0 -DEFW_MAX_SENSORS=64 ...
```

| 宏 | 默认值 | 说明 |
|----|--------|------|
| `EFW_ENABLE_HAL` | 1 | HAL 层 |
| `EFW_ENABLE_COMM` | 1 | 通信层 |
| `EFW_ENABLE_MODULE` | 1 | 模块层 |
| `EFW_ENABLE_SENSOR` | 1 | 传感器层 |
| `EFW_ENABLE_ACTUATOR` | 1 | 执行器层 |
| `EFW_ENABLE_ALGORITHM` | 1 | 算法层 |
| `EFW_ENABLE_STATE_MACHINE` | 1 | 状态机 |
| `EFW_ENABLE_EVENT` | 1 | 事件总线 |
| `EFW_ENABLE_SCHEDULER` | 1 | 调度器 |
| `EFW_MAX_HALS` | 16 | HAL 最大数量 |
| `EFW_MAX_COMMS` | 16 | COMM 最大数量 |
| `EFW_MAX_MODULES` | 32 | 模块最大数量 |
| `EFW_MAX_SENSORS` | 32 | 传感器最大数量 |
| `EFW_MAX_ACTUATORS` | 16 | 执行器最大数量 |
| `EFW_MAX_ALGOS` | 16 | 算法最大数量 |
| `EFW_MAX_STATE_MACHINES` | 8 | 状态机最大数量 |
| `EFW_MAX_SCHEDULER_TASKS` | 16 | 调度任务最大数量 |
| `EFW_MAX_TOPIC_SUBS` | 8 | 事件订阅最大数量 |
| `EFW_EVENT_QUEUE_CAPACITY` | 8 | 事件队列容量 |
| `EFW_ERROR_HISTORY_SIZE` | 4 | 错误历史缓冲区大小 |
