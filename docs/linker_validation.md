# 链接脚本验证报告

## 验证方法

### 1. 内存地址验证

| 区域 | 起始地址 | 大小 | 芯片手册 | 链接脚本 | 状态 |
|------|----------|------|----------|----------|------|
| Flash | 0x08000000 | 1024KB | ✓ | 2048KB | ⚠️ 需要调整 |
| RAM | 0x20000000 | 192KB | ✓ | 192KB | ✓ |
| CCMRAM | 0x10000000 | 64KB | ✓ | 64KB | ✓ |

### 2. 段定义验证

| 段名 | 用途 | 验证 |
|------|------|------|
| .isr_vector | 中断向量表 | ✓ |
| .text | 代码段 | ✓ |
| .rodata | 只读数据 | ✓ |
| .data | 已初始化数据 | ✓ |
| .bss | 未初始化数据 | ✓ |
| ._user_heap_stack | 堆栈 | ✓ |

### 3. 入口点验证

```
ENTRY(Reset_Handler)  ✓
```

## 发现的问题

### 问题 1: Flash 大小不匹配

**问题描述**：
- STM32F407VGT6: 1024KB Flash
- 链接脚本: 2048KB Flash (来自 F429)

**解决方案**：
需要修改链接脚本，将 Flash 大小改为 1024K

```ld
MEMORY
{
  CCMRAM (xrw) : ORIGIN = 0x10000000, LENGTH = 64K
  RAM    (xrw) : ORIGIN = 0x20000000, LENGTH = 192K
  ROM    (rx)  : ORIGIN = 0x08000000, LENGTH = 1024K  # 修改这里
}
```

### 问题 2: 启动文件格式

**问题描述**：
- 找到的启动文件是 STM32CubeIDE 格式
- 需要确认是否兼容 ARM GCC

**验证**：
- STM32CubeIDE 使用 ARM GCC
- 启动文件格式兼容

## 验证步骤

### 1. 编译验证

```bash
# 配置项目
python3 tools/efw.py build config --chip STM32F407VGT6

# 编译项目
python3 tools/efw.py build compile --chip STM32F407VGT6
```

### 2. 烧录验证

```bash
# 烧录到 MCU
python3 tools/efw.py flash --bin build/app.bin --tool stlink

# 观察运行状态
python3 tools/efw.py debug snapshot --port /dev/ttyUSB0
```

### 3. 功能验证

- [ ] LED 闪烁
- [ ] GPIO 读写
- [ ] ADC 采样
- [ ] PWM 输出
- [ ] UART 通信

## 结论

链接脚本基本正确，但需要根据具体芯片调整 Flash 大小。

## 下一步

1. 修改链接脚本生成逻辑，根据芯片自动调整内存大小
2. 测试编译流程
3. 测试烧录和运行
