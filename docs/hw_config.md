# 硬件配置工具

## 功能

| 命令 | 说明 |
|------|------|
| `hw pins --chip <chip>` | 查看芯片引脚 |
| `hw check --config <file>` | 检查引脚冲突 |
| `hw generate --config <file>` | 生成配置代码 |

## 使用示例

```bash
# 查看引脚
python3 tools/efw.py hw pins --chip STM32F407VGT6

# 检查冲突
python3 tools/efw.py hw check --config hw_config.json

# 生成代码
python3 tools/efw.py hw generate --config hw_config.json -o src/
```

## 配置文件格式

```json
{
  "chip": "STM32F407VGT6",
  "assignments": {
    "line_sensor_0": {
      "pin": "PA0",
      "function": "adc",
      "peripheral": "ADC1",
      "channel": "IN0",
      "label": "line_sensor_0"
    },
    "left_motor_pwm": {
      "pin": "PB6",
      "function": "pwm",
      "peripheral": "TIM4",
      "channel": "CH1",
      "label": "left_motor_pwm"
    }
  }
}
```

## 生成的文件

### pin_config.h

```c
/* GPIO 引脚 */
#define PIN_LEFT_MOTOR_DIR       "PB8"
#define PIN_RIGHT_MOTOR_DIR      "PB9"

/* ADC 引脚 */
#define PIN_LINE_SENSOR_0        "PA0"
#define LINE_SENSOR_0_CHANNEL  0

/* PWM 引脚 */
#define PIN_LEFT_MOTOR_PWM       "PB6"
#define LEFT_MOTOR_PWM_TIMER   "TIM4"
```

### hal_init.c

```c
void hal_init(void) {
    /* GPIO 初始化 */
    efw_hal_gpio_init("left_motor_dir", PIN_LEFT_MOTOR_DIR);
    
    /* ADC 初始化 */
    efw_hal_adc_init("line_sensor_0", PIN_LINE_SENSOR_0);
    
    /* PWM 初始化 */
    efw_hal_pwm_init("left_motor_pwm", PIN_LEFT_MOTOR_PWM, 1000);
}
```

## 测试结果

```
$ python3 tools/efw.py hw check --config hw_config.json
✓ 未发现引脚冲突

$ python3 tools/efw.py hw generate --config hw_config.json -o src/
✓ 代码已生成:
  src/pin_config.h
  src/hal_init.c
```

## 支持的引脚功能

| 功能 | 说明 |
|------|------|
| gpio | 通用输入输出 |
| adc | 模数转换 |
| pwm | 脉宽调制 |
| uart_tx/rx | 串口发送/接收 |
| i2c_sda/scl | I2C 数据/时钟 |
| spi_mosi/miso/sck/nss | SPI 接口 |
