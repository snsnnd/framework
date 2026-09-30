# 03 运行时与生成代码

## 运行时（`runtime/`）

生成代码只依赖三个运行时源文件：`core/scheduler.c`、`core/diagnostic.c`、`core/msgq.c`。

- **调度器**：`efw_scheduler_tick(now_ms)`，`now_ms` 是自启动起的绝对毫秒数；协作式，迟到只执行一次并累计 `missed_releases`，统计迟到/耗时/超限。
- **消息队列 `efw_msgq_t`（新增）**：静态存储、固定条目大小；策略 `drop_oldest / drop_newest`；统计 `pushed / popped / dropped / high_water`；临界区钩子 `EFW_CRITICAL_ENTER/EXIT`（默认空，MCU 上映射为关中断即可在 ISR 中 `push`）。

## 生成文件（`generated/`）

| 文件 | 内容 |
| --- | --- |
| `app.h` | 事件枚举、`app_init/app_tick`、信号读写、`app_emit_*`、队列 API、需要用户实现的函数声明（签名由编译器强制） |
| `app_core.c` | 信号、参数、数据流、状态机、事件与队列、可观测层（`APP_OBSERVE_ENABLE` 可整体关闭） |
| `app_virtual.c` | 仅虚拟目标：仿真输入、`main`、时间控制 |
| `manifest.json` | 调试清单：信号/参数/数据流/状态机/队列及其范围、模型哈希 |

用户在自己的主循环中：

```c
app_init();
for (;;) { uint32_t now = board_ms(); app_tick(now); app_observe_poll(now); }
```

真机需要在 `board/` 提供 `app_observe_write` / `app_observe_read`（UART/USB 字节读写）；不需要调试则不编译 `APP_OBSERVE_ENABLE`。

## 用户函数签名

| 位置 | 签名 |
| --- | --- |
| `board/` 输入 `x` | `efw_status_t x_read(T *value)` |
| `board/` 输出 `y` | `efw_status_t y_write(T value)` |
| `src/` 自定义步骤 / 状态钩子 | `efw_status_t fn(void)` |
| `src/` 转换 `call` | `int fn(void)`（非 0 为真） |

`T` 为 `float / int32_t / bool`。函数缺失时，界面提供一键创建；签名不符时 C 编译器报错（生成的 `app.h` 声明了它们）。

## 源码模板与固定结构

工具创建或补充的源码（模板项目与函数骨架）带固定结构标记，只有标记内是用户逻辑：

```c
efw_status_t count_fault(void) {
    /* EFW USER BEGIN count_fault */
    app_set_faults(app_get_faults() + 1);
    return EFW_OK;
    /* EFW USER END count_fault */
}
```

- `/* EFW USER BEGIN <name> */` 与 `/* EFW USER END <name> */` 成对、不嵌套、不重名；`name` 是函数名或槽位名。
- 标记之外（函数签名、花括号、标记行、`#include`、注释等）由工具维护：代码页拒绝在这些区域输入，保存接口 `file.write` 也会拒绝（错误码 `TEMPLATE`）。
- 已有用户文件如果完全不含标记，则不加限制，按普通 C 文件编辑。用户自己写的文件不需要套模板。
- 函数骨架通过 `file.write` 的 `add_functions: ["fn", ...]` 在保存时由工具追加，用户只能修改追加后的标记内逻辑。
- 模板标记只是注释，不影响 C 编译；生成代码与运行时不受影响。
- 结构化配置区（`efw.json`）不写进 `.c` 文件：模型配置以 `efw.json` 为单一事实来源，`.c` 只保存实现。

## 静态内存

`analysis.memory` 给出估算：信号、参数、每步状态（滤波/PID/平均窗口）、事件队列、用户队列。所有存储在编译期确定，无 `malloc`。

## 可观测性开销

每个数据流一个 `run/miss/over/err/late/us` 统计（来自调度器）；每个队列 `n/push/drop/hw`；快照默认 200 ms 一帧，约 1 KB，115200 波特下约 45% 带宽；可用 `rate` 调整。
