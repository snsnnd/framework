# EFW 仿真器 API 文档

## 概述

EFW 仿真器提供完整的嵌入式系统仿真能力，供 Studio 可视化界面调用。

## 快速开始

```python
from tools.simulator import SimulationEngine, MCUSimulator, MCUType, LineSensor, Motor

# 创建仿真引擎
engine = SimulationEngine()
engine.create_mcu(MCUType.STM32F407)

# 添加传感器和执行器
engine.add_sensor(LineSensor("line_sensor", channels=5))
engine.add_actuator(Motor("left_motor", max_rpm=300))
engine.add_actuator(Motor("right_motor", max_rpm=300))

# 设置传感器输入
engine.get_sensor("line_sensor").set_input("10101")

# 执行仿真步进
engine.step(168000)  # 1ms @ 168MHz

# 获取快照（用于在线 Debug）
snapshot = engine.get_debug_snapshot()
```

## 核心 API

### SimulationEngine

仿真引擎主类，管理整个仿真系统。

#### 创建和配置

```python
engine = SimulationEngine()

# 创建 MCU
mcu = engine.create_mcu(MCUType.STM32F407)  # 或 STM32F103, ESP32 等
```

#### 添加外设

```python
# GPIO
gpio = engine.add_gpio("A", 0, mode="input")

# ADC
adc = engine.add_adc(channel=0, resolution=12)

# PWM
pwm = engine.add_pwm("TIM1", frequency_hz=1000)

# UART
uart = engine.add_uart(port=1, baudrate=115200)

# I2C
i2c = engine.add_i2c(bus_id=1, speed=100000)

# SPI
spi = engine.add_spi(bus_id=1, speed=1000000)
```

#### 添加传感器

```python
from tools.simulator import LineSensor, Encoder, IMU, UltrasonicSensor

# 循迹传感器
line = LineSensor("line_sensor", channels=5)
engine.add_sensor(line)

# 编码器
encoder = Encoder("encoder", ppr=360)
engine.add_sensor(encoder)

# IMU
imu = IMU("imu")
engine.add_sensor(imu)

# 超声波
ultrasonic = UltrasonicSensor("ultrasonic")
engine.add_sensor(ultrasonic)
```

#### 添加执行器

```python
from tools.simulator import Motor, Servo, LED

# 电机
motor = Motor("motor", max_rpm=300)
engine.add_actuator(motor)

# 舵机
servo = Servo("servo", min_angle=0, max_angle=180)
engine.add_actuator(servo)

# LED
led = LED("led", color="green")
engine.add_actuator(led)
```

#### 仿真控制

```python
# 启动仿真（异步，60 FPS）
engine.start()

# 暂停/恢复
engine.pause()
engine.resume()

# 停止仿真
engine.stop()

# 单步执行（同步）
engine.step(cycles=168000)  # 1ms @ 168MHz

# 设置速度倍率
engine.set_speed(2.0)  # 2倍速
```

#### 回调

```python
# 每个 tick 回调
def on_tick():
    # 在这里实现控制逻辑
    pass

engine.on_tick = on_tick

# 每帧回调（约 60 FPS）
def on_frame():
    # 在这里更新 UI
    pass

engine.on_frame = on_frame
```

#### 获取调试数据

```python
# 获取快照（用于在线 Debug）
snapshot = engine.get_debug_snapshot()

# 获取 JSON 格式数据
json_str = engine.get_debug_json()

# 获取仿真状态
state = engine.get_state()
# 返回: {"running": bool, "paused": bool, "speed_multiplier": float, ...}

# 获取外设信息
peripherals = engine.get_peripherals_info()

# 获取传感器信息
sensors = engine.get_sensors_info()

# 获取执行器信息
actuators = engine.get_actuators_info()
```

## 传感器 API

### LineSensor

循迹传感器，支持 5/8 路通道。

```python
sensor = LineSensor("name", channels=5)

# 设置输入
sensor.set_input("10101")  # 字符串模式
sensor.set_input([1, 0, 1, 0, 1])  # 列表模式

# 读取数据
values = sensor.read()  # [1, 0, 1, 0, 1]
raw = sensor.read_raw()  # [1.0, 0.0, 1.0, 0.0, 1.0]

# 计算循迹误差（用于 PID）
error = sensor.get_error(weights=[-2, -1, 0, 1, 2])
```

### Encoder

编码器，支持位置和速度读取。

```python
encoder = Encoder("name", ppr=360)

# 设置目标速度（仿真用）
encoder.set_input(100.0)  # 100 RPM

# 读取数据
position = encoder.read()
velocity = encoder.read_velocity()  # RPM

# 重置
encoder.reset()
```

### IMU

6 轴惯性测量单元。

```python
imu = IMU("name")

# 设置输入（仿真用）
imu.set_input({
    "accel": [0.0, 0.0, 1.0],  # 加速度（g）
    "gyro": [0.0, 0.0, 0.0],   # 角速度（deg/s）
    "attitude": [0.0, 0.0, 0.0],  # 姿态（度）
    "temperature": 25.0,
})

# 读取数据
accel = imu.read_accel()  # (x, y, z)
gyro = imu.read_gyro()  # (x, y, z)
attitude = imu.read_attitude()  # (roll, pitch, yaw)
```

### UltrasonicSensor

超声波测距传感器。

```python
sensor = UltrasonicSensor("name")

# 设置距离（仿真用）
sensor.set_input(100.0)  # 100 cm

# 读取数据
distance = sensor.read()  # cm
time_us = sensor.read_us()  # 微秒
```

## 执行器 API

### Motor

直流电机。

```python
motor = Motor("name", max_rpm=300)

# 设置命令
motor.set_command({
    "speed": 0.5,      # 速度（-1.0 到 1.0）
    "direction": 1,     # 方向（1 或 -1）
    "brake": False,     # 刹车
})

# 读取数据
speed = motor.get_speed()
rpm = motor.get_rpm()
position = motor.get_position()
```

### Servo

舵机。

```python
servo = Servo("name", min_angle=0, max_angle=180)

# 设置命令
servo.set_command({
    "angle": 90,        # 目标角度
    "speed": 180,       # 运动速度（度/秒）
})

# 读取数据
angle = servo.get_angle()

# 直接设置角度
servo.set_angle(45)
```

### LED

LED 发光二极管。

```python
led = LED("name", color="green")

# 设置命令
led.set_command({
    "state": True,      # 开关
    "brightness": 0.5,  # 亮度
    "blink": 500,       # 闪烁间隔（毫秒）
    "toggle": False,    # 切换状态
})

# 便捷方法
led.on()
led.off()
led.toggle()
```

## 场景管理

### 加载内置场景

```python
from tools.simulator.scenario import get_builtin_scenario

# 获取循迹车场景
scenario = get_builtin_scenario("line_tracker")
```

### 保存/加载场景

```python
from tools.simulator import save_scenario, load_scenario

# 保存场景
save_scenario(scenario, "my_scenario.json")

# 加载场景
scenario = load_scenario("my_scenario.json")

# 应用场景到引擎
engine.load_scenario("my_scenario.json")
```

### 自定义场景

```python
from tools.simulator import Scenario, ScenarioConfig

config = ScenarioConfig(
    name="my_scenario",
    description="自定义场景",
    mcu_type="STM32F407",
    sensors=[
        {"name": "line_sensor", "type": "line", "channels": 5},
    ],
    actuators=[
        {"name": "motor", "type": "motor", "max_rpm": 300},
    ],
)

scenario = Scenario(config=config)
```

## 与在线 Debug 集成

仿真引擎可以无缝接入 EFW 在线 Debug 系统：

```python
from tools.simulator import SimulationEngine
from tools.debug.recorder import DebugRecorder

# 创建仿真引擎
engine = SimulationEngine()
# ... 配置 ...

# 创建记录器
recorder = DebugRecorder("simulation_log.jsonl")
recorder.start()

# 运行仿真并记录
for i in range(1000):
    engine.step(168)  # 1us @ 168MHz
    
    # 获取快照
    snapshot = engine.get_debug_snapshot()
    
    # 转换为 Debug 格式并记录
    debug_data = {
        "time": snapshot.timestamp,
        "params": {
            "line_sensor": {"value": snapshot.sensor_data.get("line_sensor", {}).get("values", [])},
            "left_motor": {"value": snapshot.actuator_data.get("left_motor", {}).get("speed", 0)},
        }
    }
    recorder.record(debug_data)

recorder.stop()
```

## 文件结构

```
tools/simulator/
├── __init__.py          # 包入口
├── core.py              # MCU 核心模拟器
├── peripherals.py       # 外设模拟
├── sensors.py           # 传感器模拟
├── actuators.py         # 执行器模拟
├── engine.py            # 仿真引擎
├── scenario.py          # 场景配置
└── examples/
    └── line_tracker.py  # 循迹车示例
```
