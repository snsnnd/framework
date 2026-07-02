# EFW 数据库

本目录包含 EFW Studio 和 Tools 使用的正式数据。

## 目录结构

```
data/
├── mcu/                        # MCU 芯片数据
│   ├── index.json             # 芯片索引
│   ├── STM32F1/               # STM32F1 系列
│   │   ├── STM32F103C8T6.json
│   │   └── STM32F103RBT6.json
│   ├── STM32F4/               # STM32F4 系列
│   │   ├── STM32F407VGT6.json
│   │   ├── STM32F411RET6.json
│   │   └── STM32F446RET6.json
│   └── STM32G4/               # STM32G4 系列
│       └── STM32G431CBT6.json
│
├── board_profiles/             # 开发板配置
│   ├── Blue_Pill.json
│   ├── Discovery_F407.json
│   ├── Nucleo_F103RB.json
│   ├── Nucleo_F411RE.json
│   ├── Nucleo_F446RE.json
│   └── Nucleo_G431CB.json
│
└── pin_templates/              # 引脚模板（待扩展）
```

## 芯片数据格式

每个芯片 JSON 文件包含：

```json
{
  "id": "STM32F407V(E-G)Tx",
  "name": "STM32F407VGT6",
  "family": "STM32F4",
  "core": "Arm Cortex-M4",
  "frequency_mhz": 168,
  "flash_kb": 1024,
  "ram_kb": 256,
  "package": "LQFP100",
  "board": "Discovery F407",
  "gpio_count": 82,
  "gpio_pins": ["PA0", "PA1", ...],
  "peripherals": {
    "adc": {
      "channels": {"IN0": "PA0", "IN1": "PA1", ...},
      "count": 16
    },
    "pwm": {
      "outputs": {"TIM1_CH1": "PA8", ...},
      "count": 38
    },
    "uart": {
      "ports": {"UART1": {"tx": ["PA9"], "rx": ["PA10"]}, ...},
      "count": 6
    },
    "i2c": {
      "ports": {"I2C1": {"sda": ["PB7"], "scl": ["PB6"]}, ...},
      "count": 3
    },
    "spi": {
      "ports": {"SPI1": {"mosi": ["PA7"], "miso": ["PA6"], "sck": ["PA5"], "nss": ["PA4"]}, ...},
      "count": 3
    }
  },
  "pins": {
    "PA0": {
      "pos": 1,
      "type": "I/O",
      "functions": {
        "gpio": true,
        "adc": [0],
        "pwm": ["TIM2_CH1"],
        "uart": {"tx": false, "rx": false},
        "i2c": {"sda": false, "scl": false},
        "spi": {"mosi": false, "miso": false, "sck": false, "nss": false}
      }
    },
    ...
  }
}
```

## Studio 使用方式

### 加载芯片数据

```python
import json
from pathlib import Path

def load_mcu(name: str) -> dict:
    """加载芯片数据"""
    index_path = Path("data/mcu/index.json")
    with open(index_path) as f:
        index = json.load(f)
    
    if name not in index:
        raise ValueError(f"Unknown MCU: {name}")
    
    chip_path = Path("data/mcu") / index[name]['path']
    with open(chip_path) as f:
        return json.load(f)

# 使用
mcu = load_mcu("STM32F407VGT6")
print(f"GPIO: {mcu['gpio_count']}")
print(f"ADC: {mcu['peripherals']['adc']['count']}")
```

### 获取可用引脚

```python
def get_adc_pins(mcu: dict) -> dict:
    """获取 ADC 可用引脚"""
    return mcu['peripherals']['adc']['channels']

def get_pwm_pins(mcu: dict) -> dict:
    """获取 PWM 可用引脚"""
    return mcu['peripherals']['pwm']['outputs']

def get_uart_pins(mcu: dict, port: str) -> dict:
    """获取 UART 引脚"""
    return mcu['peripherals']['uart']['ports'].get(port, {})
```

### 加载开发板配置

```python
def load_board_profile(name: str) -> dict:
    """加载开发板配置"""
    path = Path(f"data/board_profiles/{name.replace(' ', '_')}.json")
    with open(path) as f:
        return json.load(f)
```

## 添加新芯片

1. 在 `tools/mcu_convert.py` 的 `COMMON_MCUS` 中添加芯片配置
2. 运行转换工具：`python3 tools/mcu_convert.py`
3. 新数据会自动添加到对应目录

## 已支持芯片

| 芯片 | 核心 | 频率 | GPIO | ADC | PWM | UART | I2C | SPI |
|------|------|------|------|-----|-----|------|-----|-----|
| STM32F103C8T6 | Cortex-M3 | 72MHz | 37 | 10 | 19 | 3 | 2 | 2 |
| STM32F103RBT6 | Cortex-M3 | 72MHz | 51 | 16 | 19 | 3 | 2 | 2 |
| STM32F407VGT6 | Cortex-M4 | 168MHz | 82 | 16 | 38 | 6 | 3 | 3 |
| STM32F411RET6 | Cortex-M4 | 100MHz | 50 | 16 | 27 | 3 | 3 | 5 |
| STM32F446RET6 | Cortex-M4 | 180MHz | 50 | 16 | 38 | 6 | 3 | 3 |
| STM32G431CBT6 | Cortex-M4 | 170MHz | 38 | 12 | 33 | 3 | 3 | 3 |
