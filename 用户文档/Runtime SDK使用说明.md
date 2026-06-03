# EFW Runtime SDK 使用说明

## 1. 这个包是给谁用的

`EFW Runtime SDK` 面向把 EFW 运行时集成进真实嵌入式工程的开发者。

它适合这些场景：

- Keil 工程直接接入源码
- STM32CubeIDE 工程接入源码
- ESP-IDF / CMake 工程接入源码
- 想手动调用 EFW API，而不是先用 Studio 建模的人

## 2. 包里有什么

通常包含：

- `include/`：公开头文件
- `src/`：运行时源码
- `CMakeLists.txt`：主机侧构建入口
- `README.md`：项目总览
- `PACKAGE_README.md`：分发包说明

## 3. 最常用的接入方式

最推荐的方式是：

1. 把 `include/` 加入头文件搜索路径
2. 把 `src/efw_all.c` 加入你的工程
3. 在应用代码里包含：

```c
#include "efw/efw.h"
```

4. 系统启动后调用：

```c
efw_init();
```

5. 然后注册你的 HAL、通信对象、传感器、算法和模块

## 4. Keil 接入步骤

### 第一步：加入头文件路径

在 `Options for Target > C/C++ > Include Paths` 中加入：

```text
<你的工程路径>/framework/include
```

### 第二步：加入源码

推荐只加入：

```text
src/efw_all.c
```

这样由 `EFW_ENABLE_*` 宏决定实际编译哪些模块。

### 第三步：在代码中初始化

```c
#include "efw/efw.h"

int main(void) {
    efw_init();
    /* 注册 HAL / COMM / SENSOR / MODULE */
    while (1) {
        /* 业务循环 */
    }
}
```

## 5. 如果不想用 efw_all.c

你也可以按需把 `src/` 里的模块源码手动加进工程。

这种方式适合：

- 想非常精细地控制编译单元
- 不想使用聚合入口
- 想在旧工程里渐进式接入

但对大多数用户来说，优先还是推荐 `src/efw_all.c`。

## 6. 常见功能开关

EFW 支持按宏裁剪功能，例如：

- `EFW_ENABLE_HAL`
- `EFW_ENABLE_COMM`
- `EFW_ENABLE_MODULE`
- `EFW_ENABLE_SENSOR`
- `EFW_ENABLE_ACTUATOR`
- `EFW_ENABLE_ALGORITHM`
- `EFW_ENABLE_STATE_MACHINE`
- `EFW_ENABLE_EVENT`

如果你关闭某些模块，需要在工程编译选项中同步设置这些宏。

## 7. 接入后通常会做什么

接入完成后，典型流程是：

1. 调用 `efw_init()`
2. 注册平台 HAL
3. 注册通信对象
4. 注册传感器 / 执行器 / 算法 / 模块
5. 在主循环或周期任务中调用：
   - `efw_sensor_read()`
   - `efw_algo_run()`
   - `efw_module_poll_all()`

## 8. 如果你也想用可视化工具

如果你不仅想接入运行时库，还想通过图形方式建模和生成 application，请使用：

- `EFW Studio Portable`

对应的文档在：

- `用户文档/Studio介绍.md`
- `用户文档/Studio操作手册.md`
