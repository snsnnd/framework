# EFW 固件集成状态

## 已完成

| 组件 | 状态 | 文件 |
|------|------|------|
| 固件管理工具 | ✅ | `tools/firmware.py` |
| CMake 生成器 | ✅ | `tools/cmake_generator.py` |
| HAL 适配层接口 | ✅ | `include/efw/hal/hal_adapter.h` |
| STM32 HAL 适配实现 | ✅ | `src/hal/hal_adapter_stm32.c` |
| 编译器管理 | ✅ | `tools/compiler.py` |
| MCU 数据库 | ✅ | `data/mcu/` |
| CLI 工具链 | ✅ | `tools/efw.py` |

## 待完成

| 组件 | 说明 | 优先级 |
|------|------|--------|
| codegen 集成 | 让 codegen 自动调用固件库 | P0 |
| ESP32 HAL 适配 | ESP-IDF 适配层 | P1 |
| 裸机 HAL 适配 | 寄存器直接操作 | P2 |
| 启动代码生成 | 根据芯片生成启动文件 | P1 |
| 链接脚本生成 | 根据芯片生成链接脚本 | P1 |

## 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户代码                                  │
│                    main.c, app.c                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     EFW 框架 API                                │
│              efw_hal_gpio_read(), etc                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    HAL 适配层                                    │
│                hal_adapter.h                                    │
│    ┌─────────────┬─────────────┬─────────────┐                  │
│    │ STM32 HAL   │ ESP-IDF     │ 裸机寄存器   │                  │
│    └─────────────┴─────────────┴─────────────┘                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     固件库                                       │
│    ┌─────────────┬─────────────┬─────────────┐                  │
│    │STM32CubeF4  │ ESP-IDF     │ CMSIS       │                  │
│    └─────────────┴─────────────┴─────────────┘                  │
└─────────────────────────────────────────────────────────────────┘
```

## 使用流程

```bash
# 1. 下载固件库
python3 tools/efw.py firmware download stm32f4

# 2. 检测编译器
python3 tools/efw.py build detect

# 3. 设计项目
python3 tools/efw.py project create firmware_demo --chip STM32F407VGT6 --board Discovery_F407

# 4. 生成代码（自动配置固件库）
python3 tools/efw.py project generate firmware_demo

# 5. 编译项目
python3 tools/efw.py build compile --chip STM32F407VGT6

# 6. 烧录运行
python3 tools/efw.py flash --bin build/app.bin
```

## codegen 集成计划

codegen 需要自动完成以下工作：

1. **读取芯片配置**
   - 从 `data/mcu/` 加载芯片信息
   - 确定使用的固件库

2. **生成 HAL 适配代码**
   - 根据芯片生成 `app_platform.c`
   - 配置 GPIO/ADC/PWM/UART 映射

3. **生成 CMakeLists.txt**
   - 配置固件库路径
   - 配置头文件路径
   - 配置源文件

4. **生成启动代码**
   - 从固件库复制启动文件
   - 配置中断向量表

5. **生成链接脚本**
   - 根据芯片内存配置生成
   - 配置 Flash/RAM 地址

## 示例：codegen 生成的文件

```
application/
├── CMakeLists.txt          # 自动生成，包含固件库配置
├── app_board_config.h      # 引脚配置
├── app_platform.c          # HAL 初始化（调用固件库）
├── app_components.c        # 组件注册
├── main.c                  # 主程序
├── startup_stm32f407xx.s   # 启动文件（从固件库复制）
└── STM32F407xx_FLASH.ld    # 链接脚本（从固件库复制）
```
