# EFW 编译工具

## 功能

| 命令 | 说明 |
|------|------|
| `build check` | 检查 ARM GCC 编译器状态 |
| `build install` | 安装 ARM GCC 编译器 |
| `build init [chip]` | 初始化项目结构 |
| `build config --chip CHIP` | 配置项目（运行 CMake） |
| `build compile` | 编译项目 |
| `build clean` | 清理构建目录 |

## 使用流程

```bash
# 1. 检查编译器
python3 tools/efw.py build check

# 2. 安装编译器（如果未安装）
python3 tools/efw.py build install

# 3. 初始化项目
python3 tools/efw.py build init STM32F407VGT6

# 4. 配置项目
python3 tools/efw.py build config --chip STM32F407VGT6

# 5. 编译项目
python3 tools/efw.py build compile

# 6. 清理构建
python3 tools/efw.py build clean
```

## 测试结果

```
$ python3 tools/efw.py build check
编译器状态:
----------------------------------------
  已安装: ✗
  工具链目录: /home/aaa/.efw/toolchain

$ python3 tools/efw.py build init STM32F407VGT6
初始化项目: STM32F407VGT6
✓ 生成 CMakeLists.txt: CMakeLists.txt
✓ 生成链接脚本: linker.ld
✓ 项目已初始化
  下一步: python3 tools/efw.py build config --chip STM32F407VGT6
```

## 生成的文件

初始化项目后会生成：

```
项目目录/
├── CMakeLists.txt    # CMake 构建配置
├── linker.ld         # 链接脚本
├── src/              # 源代码目录
└── include/          # 头文件目录
```

## 完整工作流

```bash
# 1. 芯片选择
python3 tools/efw.py mcu list
python3 tools/efw.py mcu info STM32F407VGT6

# 2. 项目设计
python3 tools/efw.py project create build_demo --chip STM32F407VGT6 --board Discovery_F407

# 3. 代码生成
python3 tools/efw.py project generate build_demo
python3 tools/efw.py project build build_demo

# 4. 编译构建
python3 tools/efw.py build check
python3 tools/efw.py build init STM32F407VGT6
python3 tools/efw.py build config --chip STM32F407VGT6
python3 tools/efw.py build compile

# 5. 烧录运行
python3 tools/efw.py flash --bin build/app.bin --port COM3

# 6. 在线调试
python3 tools/efw.py debug snapshot --port /dev/ttyUSB0
```

## 编译器安装

编译器会自动下载到 `~/.efw/toolchain/` 目录。

支持的操作系统：
- Windows
- Linux
- macOS

下载地址：https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads
