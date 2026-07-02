# SVD 增强的链接脚本生成

## 功能

使用 CMSIS-SVD 数据自动生成：
- **链接脚本** - 精确的内存布局
- **启动代码** - 完整的中断向量表

## 数据来源

- [cmsis-svd](https://github.com/cmsis-svd/cmsis-svd) - SVD 解析器
- [cmsis-svd-data](https://github.com/cmsis-svd/cmsis-svd-data) - SVD 数据仓库

## SVD 文件包含的信息

| 信息 | 用途 |
|------|------|
| CPU 类型 | 配置编译器 |
| 外设基地址 | 生成寄存器定义 |
| 中断号 | 生成中断向量表 |
| 寄存器位域 | 生成头文件 |

## 使用方式

### 命令行

```bash
# 查看设备信息
python3 tools/svd_linker.py /path/to/STM32F407.svd --info

# 生成链接脚本和启动代码
python3 tools/svd_linker.py /path/to/STM32F407.svd -o output/ --flash 1024 --ram 192
```

### 代码中使用

```python
from tools.svd_linker import generate_from_svd

generated = generate_from_svd(
    svd_path=Path("STM32F407.svd"),
    output_dir=Path("output/"),
    flash_size_kb=1024,
    ram_size_kb=192,
    ccm_size_kb=64,
)
```

## 测试结果

```
$ python3 tools/svd_linker.py /tmp/cmsis-svd-data/data/STMicro/STM32F407.svd --info

设备: STM32F407
CPU: CM4
字节序: little
FPU: False
外设数量: 91
中断数量: 83

外设列表:
  RNG: 0x50060800
  DCMI: 0x50050000
  GPIOA: 0x40020000
  ...

中断列表:
    0: WWDG
    1: PVD
    5: RCC
    11: DMA1_Stream0
    ...
```

## 生成的文件

### linker.ld

```ld
MEMORY
{
  CCMRAM (xrw) : ORIGIN = 0x10000000, LENGTH = 64K
  RAM    (xrw) : ORIGIN = 0x20000000, LENGTH = 192K
  FLASH  (rx)  : ORIGIN = 0x08000000, LENGTH = 1024K
}
```

### startup_stm32f407.s

```asm
g_pfnVectors:
  .word _estack
  .word Reset_Handler
  .word NMI_Handler
  .word HardFault_Handler
  ...
  /* 83 个外设中断 */
  .word WWDG_Handler
  .word PVD_Handler
  ...
```

## 下载 SVD 数据

```bash
# 下载 SVD 数据仓库到 ~/.efw/svd/
python3 -c "
from tools.svd_linker import SVDManager
manager = SVDManager()
manager.download_svd_data()
"
```
