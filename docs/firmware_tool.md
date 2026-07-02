# EFW 固件管理工具

## 功能

| 命令 | 说明 |
|------|------|
| `firmware list` | 列出支持的固件 |
| `firmware installed` | 查看已安装固件 |
| `firmware download <name>` | 下载固件 |
| `firmware remove <name>` | 删除固件 |
| `firmware info <name>` | 查看固件信息 |
| `firmware config --chip CHIP` | 配置项目使用固件 |

## 下载方式

### 1. 从默认 GitHub 下载

```bash
python3 tools/efw.py firmware download stm32f4
```

### 2. 从自定义 URL 下载

```bash
python3 tools/efw.py firmware download stm32f4 --url https://example.com/STM32CubeF4.zip
```

### 3. 从本地路径安装

```bash
# Linux/macOS
python3 tools/efw.py firmware download stm32f4 --local /path/to/STM32CubeF4

# Windows
python3 tools/efw.py firmware download stm32f4 --local D:\SDK\STM32CubeF4

# WSL 访问 Windows 路径
python3 tools/efw.py firmware download stm32f4 --local /mnt/d/SDK/STM32CubeF4
```

## 支持的固件

| 固件 | 芯片系列 | 默认 GitHub URL |
|------|----------|-----------------|
| stm32f1 | STM32F1 | STMicroelectronics/STM32CubeF1 |
| stm32f4 | STM32F4 | STMicroelectronics/STM32CubeF4 |
| stm32g4 | STM32G4 | STMicroelectronics/STM32CubeG4 |
| stm32h7 | STM32H7 | STMicroelectronics/STM32CubeH7 |
| esp-idf | ESP32 | espressif/esp-idf |

## 使用流程

```bash
# 1. 列出支持的固件
python3 tools/efw.py firmware list

# 2. 下载固件（选择一种方式）
python3 tools/efw.py firmware download stm32f4
python3 tools/efw.py firmware download stm32f4 --url https://mirrors.example.com/STM32CubeF4.zip
python3 tools/efw.py firmware download stm32f4 --local /home/user/STM32CubeF4

# 3. 查看已安装固件
python3 tools/efw.py firmware installed

# 4. 配置项目使用固件
python3 tools/efw.py firmware config --chip STM32F407VGT6
```

## 测试结果

```
$ python3 tools/efw.py firmware help

EFW 固件管理工具

用法: python3 tools/efw.py firmware <subcommand>

下载方式:
  # 从默认 GitHub 下载
  python3 tools/efw.py firmware download stm32f4
  
  # 从自定义 URL 下载
  python3 tools/efw.py firmware download stm32f4 --url https://example.com/STM32CubeF4.zip
  
  # 从本地路径安装
  python3 tools/efw.py firmware download stm32f4 --local /path/to/STM32CubeF4
```

## 固件存储位置

```
~/.efw/firmware/
├── config.json           # 配置文件
├── stm32f4/              # STM32CubeF4
│   ├── Drivers/
│   │   ├── CMSIS/
│   │   └── STM32F4xx_HAL_Driver/
│   └── ...
├── stm32f1/              # STM32CubeF1
└── ...
```

## 完整工作流

```bash
# 1. 芯片选择
python3 tools/efw.py mcu list
python3 tools/efw.py mcu info STM32F407VGT6

# 2. 下载固件
python3 tools/efw.py firmware download stm32f4

# 3. 配置编译器
python3 tools/efw.py build detect

# 4. 设计项目
python3 tools/efw.py project create firmware_demo --chip STM32F407VGT6 --board Discovery_F407

# 5. 生成代码
python3 tools/efw.py project generate firmware_demo

# 6. 编译项目
python3 tools/efw.py build compile --chip STM32F407VGT6

# 7. 烧录运行
python3 tools/efw.py flash --bin build/app.bin
```
