# EFW 固件管理工具 - 完整芯片支持

## 支持的固件

### STM32 系列

| 固件名称 | 芯片系列 | GitHub 仓库 |
|----------|----------|--------------|
| stm32f1 | STM32F1 | STMicroelectronics/STM32CubeF1 |
| stm32f4 | STM32F4 | STMicroelectronics/STM32CubeF4 |
| stm32g4 | STM32G4 | STMicroelectronics/STM32CubeG4 |
| stm32h7 | STM32H7 | STMicroelectronics/STM32CubeH7 |

### ESP 系列

| 固件名称 | 芯片系列 | GitHub 仓库 |
|----------|----------|--------------|
| esp-idf | ESP32, ESP32-S2, ESP32-S3, ESP32-C3, ESP32-C6 | espressif/esp-idf |

### Arduino 系列

| 固件名称 | 芯片系列 | GitHub 仓库 |
|----------|----------|--------------|
| arduino-avr | ATmega328P, ATmega2560, ATmega32U4 | arduino/ArduinoCore-avr |
| arduino-samd | SAMD21, SAMD51 | arduino/ArduinoCore-samd |
| arduino-mbed | RP2040, STM32H7, NRF52840 | arduino/ArduinoCore-mbed |

### TI 系列

| 固件名称 | 芯片系列 | GitHub 仓库 |
|----------|----------|--------------|
| mspm0-sdk | MSPM0G3507, MSPM0G3506, MSPM0L1306, MSPM0L1305 | TexasInstruments/mspm0-sdk |

### 国产芯片

| 固件名称 | 芯片系列 | GitHub 仓库 |
|----------|----------|--------------|
| gd32-standard | GD32F103, GD32F303, GD32F407, GD32E103 | GigaDevice-Semiconductor/GD32StandardFirmware |
| ch32v-sdk | CH32V003, CH32V103, CH32V203, CH32V307 | openwch/ch32v003 |

### 其他

| 固件名称 | 芯片系列 | GitHub 仓库 |
|----------|----------|--------------|
| nxp-lpc | LPC55S69, LPC54608 | nxp-mcuxpresso/mcux-sdk |
| rp2040 | RP2040 | raspberrypi/pico-sdk |

## 使用示例

```bash
# STM32 项目
python3 tools/efw.py firmware download stm32f4
python3 tools/efw.py firmware config --chip STM32F407VGT6

# ESP32 项目
python3 tools/efw.py firmware download esp-idf
python3 tools/efw.py firmware config --chip ESP32

# Arduino 项目
python3 tools/efw.py firmware download arduino-avr
python3 tools/efw.py firmware config --chip ATmega328P

# MSPM0 项目
python3 tools/efw.py firmware download mspm0-sdk
python3 tools/efw.py firmware config --chip MSPM0G3507

# GD32 项目
python3 tools/efw.py firmware download gd32-standard
python3 tools/efw.py firmware config --chip GD32F103

# CH32V 项目
python3 tools/efw.py firmware download ch32v-sdk
python3 tools/efw.py firmware config --chip CH32V003

# RP2040 项目
python3 tools/efw.py firmware download rp2040
python3 tools/efw.py firmware config --chip RP2040
```

## 测试结果

```
$ python3 tools/efw.py firmware list

支持的固件:
============================================================
  STM32CubeF1 (STM32F1 系列):
    芯片: STM32F1
  STM32CubeF4 (STM32F4 系列):
    芯片: STM32F4
  ESP-IDF (ESP32 系列):
    芯片: ESP32, ESP32-S2, ESP32-S3, ESP32-C3, ESP32-C6
  Arduino AVR Core (Uno, Mega, Nano):
    芯片: ATmega328P, ATmega2560, ATmega32U4
  MSPM0 SDK (TI MSPM0 系列):
    芯片: MSPM0G3507, MSPM0G3506, MSPM0L1306, MSPM0L1305
  GD32 Standard Peripheral Library:
    芯片: GD32F103, GD32F303, GD32F407, GD32E103
  CH32V SDK (WCH RISC-V 系列):
    芯片: CH32V003, CH32V103, CH32V203, CH32V307
  Raspberry Pi Pico SDK (RP2040):
    芯片: RP2040
```
