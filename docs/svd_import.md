# SVD 导入工具

## 功能

| 命令 | 说明 |
|------|------|
| `svd_import.py import` | 导入单个 SVD 文件 |
| `svd_import.py import-all` | 批量导入 SVD 数据 |
| `svd_import.py info` | 查看 SVD 信息 |
| `svd_import.py linker` | 从数据库生成链接脚本 |
| `svd_import.py startup` | 从数据库生成启动代码 |
| `svd_import.py list` | 列出已导入芯片 |

## 数据库格式

导入后的 JSON 格式包含完整信息：

```json
{
  "name": "STM32F407",
  "family": "STM32F4",
  "cpu": {
    "name": "CM4",
    "endian": "little",
    "fpu_present": false
  },
  "memory": {
    "flash": {"start": 0x08000000, "size_kb": 1024},
    "ram": {"start": 0x20000000, "size_kb": 192},
    "ccm": {"start": 0x10000000, "size_kb": 64}
  },
  "peripherals": [
    {
      "name": "GPIOA",
      "base_address": 0x40020000,
      "registers": [...]
    }
  ],
  "interrupts": [
    {"name": "WWDG", "value": 0, "description": "..."},
    {"name": "PVD", "value": 1, "description": "..."}
  ]
}
```

## 使用流程

```bash
# 1. 下载 SVD 数据
git clone https://github.com/cmsis-svd/cmsis-svd-data.git

# 2. 导入 SVD
python3 tools/svd_import.py import /path/to/STM32F407.svd --data-dir data/

# 3. 批量导入
python3 tools/svd_import.py import-all /path/to/cmsis-svd-data/data/STMicro/ --data-dir data/

# 4. 生成链接脚本
python3 tools/svd_import.py linker STM32F407 -o linker.ld --flash 1024 --ram 192

# 5. 生成启动代码
python3 tools/svd_import.py startup STM32F407 -o startup.s

# 6. 查看已导入芯片
python3 tools/svd_import.py list --data-dir data/
```

## 测试结果

```
$ python3 tools/svd_import.py import STM32F407.svd
导入 SVD: STM32F407.svd
✓ 导入成功: STM32F407
  CPU: CM4
  外设: 91 个
  中断: 83 个

$ python3 tools/svd_import.py linker STM32F407 -o linker.ld --flash 1024 --ram 192
✓ 链接脚本已生成: linker.ld

$ python3 tools/svd_import.py startup STM32F407 -o startup.s
✓ 启动代码已生成: startup.s
```

## 优势

1. **完整性** - 包含外设、中断、寄存器完整信息
2. **精确性** - 基于官方 SVD 数据
3. **可维护性** - 数据库更新后可重新生成
4. **统一性** - 所有工具从同一数据库读取
