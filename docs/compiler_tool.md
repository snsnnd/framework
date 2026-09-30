# EFW 编译工具

## 支持的编译器

| 编译器 | 芯片系列 | 常见来源 |
|--------|----------|----------|
| ARM GCC | STM32 全系列 | ARM 官网, Keil, STM32CubeIDE |
| ARM Compiler | STM32 全系列 | Keil MDK |
| IAR | STM32 全系列 | IAR Embedded Workbench |
| ESP-IDF GCC | ESP32 系列 | ESP-IDF |
| TI ARM Clang | MSPM0 系列 | TI CCS |

## 命令

```bash
# 检测已安装的编译器
python3 tools/efw.py build detect

# 查看所有编译器信息
python3 tools/efw.py build info

# 设置编译器路径
python3 tools/efw.py build set --compiler arm-gcc --path "C:/Keil_v5/ARM/ARMCC/bin"

# 查看当前配置
python3 tools/efw.py build config

# 初始化项目
python3 tools/efw.py build init STM32F407VGT6

# 编译项目
python3 tools/efw.py build compile --chip STM32F407VGT6
```

## 测试结果

```
$ python3 tools/efw.py build detect
检测编译器...
------------------------------------------------------------
未检测到任何编译器

$ python3 tools/efw.py build info
编译器列表:
======================================================================

ARM GCC (arm-none-eabi-gcc):
  状态: 未检测到
  支持芯片: STM32F0, STM32F1, STM32F2, STM32F3, STM32F4...

ARM Compiler (Keil MDK):
  状态: 未检测到
  支持芯片: STM32F0, STM32F1, STM32F2, STM32F3, STM32F4...

IAR Embedded Workbench:
  状态: 未检测到
  支持芯片: STM32F0, STM32F1, STM32F2, STM32F3, STM32F4...

ESP-IDF GCC (Xtensa):
  状态: 未检测到
  支持芯片: ESP32, ESP32-S2, ESP32-S3, ESP32-C3...

TI ARM Clang (MSPM0):
  状态: 未检测到
  支持芯片: MSPM0G3507, MSPM0L1306...
```

## 功能特性

1. **自动检测**：扫描系统 PATH 和常见安装路径
2. **用户配置**：支持自定义编译器路径
3. **芯片匹配**：根据芯片自动选择合适的编译器
4. **多编译器支持**：ARM GCC、Keil、IAR、ESP-IDF、TI

## 配置文件

编译器配置保存在 `~/.efw/compilers.json`：

```json
{
  "arm-gcc": "C:/Keil_v5/ARM/ARMCC/bin",
  "esp-idf": "C:/Espressif/tools/xtensa-esp32-elf"
}
```

## 完整工作流

```bash
# 1. 检测编译器
python3 tools/efw.py build detect

# 2. 如果未检测到，手动设置
python3 tools/efw.py build set --compiler arm-gcc --path "/path/to/compiler"

# 3. 初始化项目
python3 tools/efw.py build init STM32F407VGT6

# 4. 编译项目
python3 tools/efw.py build compile --chip STM32F407VGT6

# 5. 烧录
python3 tools/efw.py flash --bin build/app.bin
```
