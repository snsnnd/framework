# Multi-Input Mapping

`processor.custom`、`algorithm.custom`、`module.custom` 现在共享一套多输入映射模型，用于把多个输入来源统一整理成一个固定输出契约。

## 适用节点

- `processor.custom`
- `algorithm.custom`
- `module.custom`

其中：

- `processor.custom` / `algorithm.custom` 支持自动组包到 `out`
- `module.custom` 支持在 `poll(...)` 里基于多输入缓存做输出映射；若被 `event.publisher` 作为 source 使用，映射结果会进入 source cache

## 核心字段

### 输入声明

```json
{
  "input_ports": {
    "sensor": {"contract": "float", "type": "float", "size": 4, "align": 4},
    "event": {"contract": "event_payload_t", "type": "event_payload_t", "size": 8, "align": 4}
  },
  "primary_input_port": "sensor",
  "trigger_policy": "primary_only"
}
```

### 输出声明

```json
{
  "output_contract": "efw_pid_input_t",
  "output_type": "efw_pid_input_t",
  "output_size": 16,
  "output_align": 4,
  "output_mode": "assemble_struct"
}
```

### 映射声明

```json
{
  "process_mode": "mapping_then_custom",
  "field_mappings": [
    {"field": "setpoint", "source": "const", "value": 0.0},
    {"field": "feedback", "source": "sensor", "path": ""},
    {"field": "dt", "source": "const", "value": 0.01},
    {"field": "feedforward", "source": "const", "value": 0.0}
  ]
}
```

## 模式

### `process_mode`

- `full_custom`
  - 仅执行用户回调
- `mapping_then_custom`
  - 先按 `field_mappings` 组包，再执行用户回调
- `mapping_only`
  - 仅按 `field_mappings` 组包，不执行用户回调

### `output_mode`

- `passthrough`
- `assemble_struct`
- `scalar_compute`
- `custom_code`

当前最常用的是：

- struct 输出：`assemble_struct`
- 标量输出：`scalar_compute`

## `field_mappings`

每一项描述一个输出字段如何填充。

```json
{
  "field": "feedback",
  "source": "sensor",
  "path": "nested.value",
  "transform": "identity",
  "required": true
}
```

### `source`

- `sensor`
- `algorithm`
- `event`
- `module_input`
- `const`
- `expr`

### `transform`

- `identity`
- `to_float`
- `to_uint16`
- `scale`
- `offset`

## 路径语法

`path` 支持简单嵌套字段：

- `value`
- `nested.value`
- `imu.euler.yaw`

当前 validate/codegen 支持：

- 多层 `.` 字段访问
- Studio 提示最多展开到有限深度

当前不支持完整数组语法生成；如果需要数组元素，请先在自定义回调里处理。

## 校验规则

系统会检查：

- `field` 是否属于输出 struct
- `source` 是否合法
- `path` 是否是输入类型的合法字段路径
- `expr` 是否只包含基础表达式字符
- `transform` 是否与目标字段类型匹配
- `mapping_only` 模式下必须存在至少一项映射

## Studio 行为

- builtin struct 输出时，`field` 列自动提供字段下拉
- `source=const` 时，`value` 可编辑，`path/expr` 灰掉
- `source=expr` 时，`expr` 可编辑，`value/path` 灰掉
- `path` 列会对 struct 输入给出路径建议

## 事件即时触发

- `processor.custom` / `algorithm.custom` 支持 `event` 到达即触发
- `module.custom` 可通过 `poll_on_event=true` 启用 `event -> poll`

事件即时触发的最后状态可通过：

- `app_last_immediate_status()`
- `app_last_immediate_target()`
- `app_last_immediate_port()`

查询。
