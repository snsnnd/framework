# EFW 编译工具 - 改进版

## 改进内容

### 1. WSL 支持
- 自动扫描 `/mnt/c/` 路径下的 Windows 编译器
- 支持 Keil MDK、STM32CubeIDE 等 Windows 工具

### 2. RISC-V 支持
- 添加 RISC-V GCC 编译器
- 支持 GD32VF103、ESP32-C3、CH32V 等芯片

### 3. 新增命令
- `build find <executable>` - 查找特定编译器

## 测试结果

```
$ python3 tools/efw.py build detect
检测编译器...
------------------------------------------------------------
检测到 1 个编译器:

  RISC-V GCC:
    路径: /home/aaa/gcc_riscv32/bin
    版本: riscv32-unknown-elf-gcc (GCC) 7.3.0

$ python3 tools/efw.py build info
编译器列表:
======================================================================

ARM GCC (arm-none-eabi-gcc):
  状态: 未检测到
  支持芯片: STM32F0, STM32F1, STM32F2, STM32F3, STM32F4...

RISC-V GCC:
  状态: 已安装
  路径: /home/aaa/gcc_riscv32/bin
  版本: riscv32-unknown-elf-gcc (GCC) 7.3.0
  支持芯片: GD32VF103, ESP32-C3, CH32V, BL602...
```

## 支持的编译器

| 编译器 | 芯片系列 | 可执行文件 |
|--------|----------|------------|
| arm-gcc | STM32 全系列 | arm-none-eabi-gcc |
| arm-compiler | STM32 全系列 | armcc.exe (Keil) |
| riscv-gcc | RISC-V 系列 | riscv32-unknown-elf-gcc |
| esp-idf | ESP32 系列 | xtensa-esp32-elf-gcc |
| ti-arm-clang | MSPM0 系列 | tiarmclang |

## 命令

```bash
# 检测编译器
python3 tools/efw.py build detect

# 查看编译器信息
python3 tools/efw.py build info

# 查找特定编译器
python3 tools/efw.py build find arm-none-eabi-gcc
python3 tools/efw.py build find gcc_riscv32

# 设置编译器路径
python3 tools/efw.py build set --compiler arm-gcc --path "/path/to/compiler"

# 编译项目
python3 tools/efw.py build compile --chip STM32F407VGT6
```

## WSL 环境下的路径

WSL 可以通过 `/mnt/c/` 访问 Windows 文件系统：

```
Windows: C:\Keil_v5\ARM\ARMCC\bin
WSL:     /mnt/c/Keil_v5/ARM/ARMCC/bin
```

## 配置文件

编译器配置保存在 `~/.efw/compilers.json`：

```json
{
  "arm-gcc": "/mnt/c/Keil_v5/ARM/ARMCC/bin",
  "riscv-gcc": "/home/aaa/gcc_riscv32/bin"
}
```
