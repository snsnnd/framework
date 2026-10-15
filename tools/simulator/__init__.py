"""
EFW 仿真核心引擎

提供完整的嵌入式系统仿真能力，供 Studio 可视化调用。
"""

from .engine import SimulationEngine
from .core import MCUSimulator, MCUType
from .peripherals import (
    GPIOPort, ADCChannel, PWMOutput, UARTPort, I2CBus, SPIBus
)
from .sensors import (
    LineSensor, Encoder, IMU, UltrasonicSensor
)
from .actuators import (
    Motor, Servo, LED
)
from .scenario import (
    Scenario, ScenarioConfig, load_scenario, save_scenario
)

__version__ = "0.1.0"
__all__ = [
    "SimulationEngine",
    "MCUSimulator",
    "MCUType",
    "GPIOPort",
    "ADCChannel",
    "PWMOutput",
    "UARTPort",
    "I2CBus",
    "SPIBus",
    "LineSensor",
    "Encoder",
    "IMU",
    "UltrasonicSensor",
    "Motor",
    "Servo",
    "LED",
    "Scenario",
    "ScenarioConfig",
    "load_scenario",
    "save_scenario",
]
