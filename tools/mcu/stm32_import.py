#!/usr/bin/env python3
"""
STM32 MCU 数据导入一体化工具

自动扫描 STM32CUBEMX 数据库，列出所有可用芯片，让用户选择导入。

使用方式：
  # 交互式选择（推荐）
  python3 tools/stm32_toolkit.py import
  
  # 自动扫描并列出所有芯片
  python3 tools/stm32_toolkit.py scan
  
  # 按系列导入
  python3 tools/stm32_toolkit.py import --family STM32F4
  
  # 按名称模式导入
  python3 tools/stm32_toolkit.py import --filter "STM32F407*"
  
  # 导入所有常用芯片
  python3 tools/stm32_toolkit.py import --common
  
  # 查看芯片信息
  python3 tools/stm32_toolkit.py info STM32F407VGT6
  
  # 列出已导入芯片
  python3 tools/stm32_toolkit.py list
  
  # 导出特定格式
  python3 tools/stm32_toolkit.py export STM32F407VGT6 --format studio
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


# ─── 配置 ────────────────────────────────────────────────────────────────────

# 默认 STM32CUBEMX 数据库路径（可通过命令行参数覆盖）
DEFAULT_DB_PATHS = [
    Path("/mnt/d/STM32/STM32CUBEMX/db/mcu"),
    Path("C:/STM32/STM32CUBEMX/db/mcu"),
    Path.home() / "STM32CubeMX/db/mcu",
]

# 输出目录
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent / "data"

# 常用芯片列表
COMMON_MCUS = [
    "STM32F103C8T6",
    "STM32F103RBT6",
    "STM32F407VGT6",
    "STM32F411RET6",
    "STM32F446RET6",
    "STM32G431CBT6",
]


# ─── 数据结构 ────────────────────────────────────────────────────────────────

@dataclass
class PinData:
    """引脚数据"""
    name: str
    position: int
    pin_type: str
    signals: list[str]
    functions: dict[str, Any]


@dataclass
class MCUData:
    """MCU 完整数据"""
    ref_name: str
    display_name: str
    family: str
    core: str
    frequency_mhz: int
    flash_kb: int
    ram_kb: int
    package: str
    board: str
    pins: list[PinData]
    peripherals: dict[str, list[str]]


@dataclass
class MCUIndex:
    """MCU 索引信息"""
    file_name: str
    ref_name: str
    family: str
    package: str
    core: str = ""
    frequency_mhz: int = 0
    flash_kb: int = 0
    ram_kb: int = 0
    io_count: int = 0


# ─── XML 解析器 ──────────────────────────────────────────────────────────────

class STM32XMLParser:
    """STM32 XML 解析器"""
    
    NAMESPACE = {'mcu': 'http://mcd.rou.st.com/modules.php?name=mcu'}
    
    @classmethod
    def parse(cls, xml_path: Path, display_name: str = "", board: str = "") -> Optional[MCUData]:
        """解析 XML 文件"""
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            # 基本信息
            ref_name = root.get('RefName', '')
            family = root.get('Family', '')
            package = root.get('Package', '')
            
            core = cls._find_text(root, 'mcu:Core')
            frequency = cls._find_int(root, 'mcu:Frequency')
            flash_kb = cls._find_max_int(root, 'mcu:Flash')
            ram_kb = cls._find_sum_int(root, 'mcu:Ram')
            
            # 解析引脚
            pins = []
            for pin_elem in root.findall('mcu:Pin', cls.NAMESPACE):
                pin = cls._parse_pin(pin_elem)
                pins.append(pin)
            
            # 解析外设
            peripherals = {}
            for ip_elem in root.findall('mcu:IP', cls.NAMESPACE):
                ip_name = ip_elem.get('InstanceName', '')
                ip_type = ip_elem.get('Name', '')
                if ip_type not in peripherals:
                    peripherals[ip_type] = []
                peripherals[ip_type].append(ip_name)
            
            return MCUData(
                ref_name=ref_name,
                display_name=display_name or ref_name,
                family=family,
                core=core,
                frequency_mhz=frequency,
                flash_kb=flash_kb,
                ram_kb=ram_kb,
                package=package,
                board=board,
                pins=pins,
                peripherals=peripherals,
            )
        
        except Exception as e:
            print(f"解析错误: {e}", file=sys.stderr)
            return None
    
    @classmethod
    def parse_quick(cls, xml_path: Path) -> Optional[MCUIndex]:
        """快速解析（只读取基本信息，用于扫描）"""
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            ref_name = root.get('RefName', '')
            family = root.get('Family', '')
            package = root.get('Package', '')
            io_count = int(root.find('mcu:IONb', cls.NAMESPACE).text or '0')
            
            return MCUIndex(
                file_name=xml_path.stem,
                ref_name=ref_name,
                family=family,
                package=package,
                io_count=io_count,
            )
        except Exception:
            return None
    
    @classmethod
    def _parse_pin(cls, pin_elem) -> PinData:
        """解析引脚"""
        name = pin_elem.get('Name', '')
        position = int(pin_elem.get('Position', '0'))
        pin_type = pin_elem.get('Type', '')
        
        signals = []
        functions = {
            'gpio': False,
            'adc': [],
            'pwm': [],
            'uart': {'tx': False, 'rx': False},
            'i2c': {'sda': False, 'scl': False},
            'spi': {'mosi': False, 'miso': False, 'sck': False, 'nss': False},
        }
        
        for signal_elem in pin_elem.findall('{http://mcd.rou.st.com/modules.php?name=mcu}Signal'):
            signal_name = signal_elem.get('Name', '')
            signals.append(signal_name)
            
            if signal_name == 'GPIO':
                functions['gpio'] = True
            
            adc_match = re.match(r'ADC\d+_IN(\d+)', signal_name)
            if adc_match:
                functions['adc'].append(int(adc_match.group(1)))
            
            pwm_match = re.match(r'TIM(\d+)_CH(\d+N?)', signal_name)
            if pwm_match:
                functions['pwm'].append(f"TIM{pwm_match.group(1)}_CH{pwm_match.group(2)}")
            
            if re.match(r'U(S)?ART\d+_TX', signal_name):
                functions['uart']['tx'] = True
            if re.match(r'U(S)?ART\d+_RX', signal_name):
                functions['uart']['rx'] = True
            
            if re.match(r'I2C\d+_SDA', signal_name):
                functions['i2c']['sda'] = True
            if re.match(r'I2C\d+_SCL', signal_name):
                functions['i2c']['scl'] = True
            
            if re.match(r'SPI\d+_MOSI', signal_name):
                functions['spi']['mosi'] = True
            if re.match(r'SPI\d+_MISO', signal_name):
                functions['spi']['miso'] = True
            if re.match(r'SPI\d+_SCK', signal_name):
                functions['spi']['sck'] = True
            if re.match(r'SPI\d+_NSS', signal_name):
                functions['spi']['nss'] = True
        
        return PinData(
            name=name,
            position=position,
            pin_type=pin_type,
            signals=signals,
            functions=functions,
        )
    
    @classmethod
    def _find_text(cls, root, tag: str) -> str:
        elem = root.find(tag, cls.NAMESPACE)
        return elem.text if elem is not None else ''
    
    @classmethod
    def _find_int(cls, root, tag: str) -> int:
        elem = root.find(tag, cls.NAMESPACE)
        return int(elem.text) if elem is not None and elem.text else 0
    
    @classmethod
    def _find_max_int(cls, root, tag: str) -> int:
        elems = root.findall(tag, cls.NAMESPACE)
        return max(int(e.text) for e in elems if e.text) if elems else 0
    
    @classmethod
    def _find_sum_int(cls, root, tag: str) -> int:
        elems = root.findall(tag, cls.NAMESPACE)
        return sum(int(e.text) for e in elems if e.text) if elems else 0


# ─── 数据转换器 ──────────────────────────────────────────────────────────────

class DataConverter:
    """数据格式转换器"""
    
    @staticmethod
    def to_studio_format(mcu: MCUData) -> dict:
        """转换为 Studio 格式"""
        ports = []
        for pin in mcu.pins:
            match = re.match(r'P([A-Z])', pin.name)
            if match and match.group(1) not in ports:
                ports.append(match.group(1))
        
        timers = set()
        for pin in mcu.pins:
            for pwm in pin.functions.get('pwm', []):
                match = re.match(r'TIM(\d+)', pwm)
                if match:
                    timers.add(int(match.group(1)))
        
        pin_map = {}
        for pin in mcu.pins:
            pin_map[pin.name] = {
                'pos': pin.position,
                'type': pin.pin_type,
                'functions': pin.functions,
            }
        
        adc_channels = {}
        pwm_outputs = {}
        uart_ports = {}
        i2c_ports = {}
        spi_ports = {}
        
        for pin in mcu.pins:
            for ch in pin.functions.get('adc', []):
                adc_channels[f"IN{ch}"] = pin.name
            
            for tim in pin.functions.get('pwm', []):
                pwm_outputs[tim] = pin.name
            
            if pin.functions['uart']['tx'] or pin.functions['uart']['rx']:
                for sig in pin.signals:
                    uart_match = re.match(r'U(S)?ART(\d+)', sig)
                    if uart_match:
                        uart_name = f"UART{uart_match.group(2)}"
                        if uart_name not in uart_ports:
                            uart_ports[uart_name] = {'tx': [], 'rx': []}
                        if pin.functions['uart']['tx']:
                            uart_ports[uart_name]['tx'].append(pin.name)
                        if pin.functions['uart']['rx']:
                            uart_ports[uart_name]['rx'].append(pin.name)
            
            if pin.functions['i2c']['sda'] or pin.functions['i2c']['scl']:
                for sig in pin.signals:
                    i2c_match = re.match(r'I2C(\d+)', sig)
                    if i2c_match:
                        i2c_name = f"I2C{i2c_match.group(1)}"
                        if i2c_name not in i2c_ports:
                            i2c_ports[i2c_name] = {'sda': [], 'scl': []}
                        if pin.functions['i2c']['sda']:
                            i2c_ports[i2c_name]['sda'].append(pin.name)
                        if pin.functions['i2c']['scl']:
                            i2c_ports[i2c_name]['scl'].append(pin.name)
            
            if any(pin.functions['spi'].values()):
                for sig in pin.signals:
                    spi_match = re.match(r'SPI(\d+)', sig)
                    if spi_match:
                        spi_name = f"SPI{spi_match.group(1)}"
                        if spi_name not in spi_ports:
                            spi_ports[spi_name] = {'mosi': [], 'miso': [], 'sck': [], 'nss': []}
                        if pin.functions['spi']['mosi']:
                            spi_ports[spi_name]['mosi'].append(pin.name)
                        if pin.functions['spi']['miso']:
                            spi_ports[spi_name]['miso'].append(pin.name)
                        if pin.functions['spi']['sck']:
                            spi_ports[spi_name]['sck'].append(pin.name)
                        if pin.functions['spi']['nss']:
                            spi_ports[spi_name]['nss'].append(pin.name)
        
        gpio_pins = [p.name for p in mcu.pins if p.functions['gpio']]
        
        return {
            'id': mcu.ref_name,
            'name': mcu.display_name,
            'family': mcu.family,
            'core': mcu.core,
            'frequency_mhz': mcu.frequency_mhz,
            'flash_kb': mcu.flash_kb,
            'ram_kb': mcu.ram_kb,
            'package': mcu.package,
            'board': mcu.board,
            'gpio_count': len(gpio_pins),
            'gpio_pins': gpio_pins,
            'peripherals': {
                'adc': {'channels': adc_channels, 'count': len(adc_channels)},
                'pwm': {'outputs': pwm_outputs, 'count': len(pwm_outputs)},
                'uart': {'ports': uart_ports, 'count': len(uart_ports)},
                'i2c': {'ports': i2c_ports, 'count': len(i2c_ports)},
                'spi': {'ports': spi_ports, 'count': len(spi_ports)},
            },
            'pins': pin_map,
        }
    
    @staticmethod
    def to_efw_format(studio_data: dict) -> dict:
        """转换为 EFW 格式"""
        return {
            'mcu': studio_data['name'],
            'family': studio_data['family'],
            'core': studio_data['core'],
            'frequency_mhz': studio_data['frequency_mhz'],
            'flash_kb': studio_data['flash_kb'],
            'ram_kb': studio_data['ram_kb'],
            'package': studio_data['package'],
            'gpio_pins': studio_data['gpio_pins'],
            'adc': studio_data['peripherals']['adc']['channels'],
            'pwm': studio_data['peripherals']['pwm']['outputs'],
            'uart': studio_data['peripherals']['uart']['ports'],
            'i2c': studio_data['peripherals']['i2c']['ports'],
            'spi': studio_data['peripherals']['spi']['ports'],
        }


# ─── 工具函数 ────────────────────────────────────────────────────────────────

def find_database_path() -> Optional[Path]:
    """自动查找 STM32CUBEMX 数据库路径"""
    # 1. 检查环境变量
    env_path = os.environ.get('STM32CUBEMX_PATH')
    if env_path:
        path = Path(env_path) / "db" / "mcu"
        if path.exists():
            return path
        path = Path(env_path)
        if path.exists() and list(path.glob("*.xml")):
            return path
    
    # 2. 检查默认路径
    for path in DEFAULT_DB_PATHS:
        if path.exists() and list(path.glob("*.xml")):
            return path
    
    # 3. 在当前目录及父目录查找
    current = Path.cwd()
    for _ in range(5):
        # 检查常见位置
        candidates = [
            current / "STM32CUBEMX" / "db" / "mcu",
            current / "stm32cubemx" / "db" / "mcu",
            current / "db" / "mcu",
        ]
        for candidate in candidates:
            if candidate.exists() and list(candidate.glob("*.xml")):
                return candidate
        current = current.parent
    
    return None


def prompt_database_path() -> Path:
    """提示用户输入数据库路径"""
    print("\n未找到 STM32CUBEMX 数据库。")
    print("请提供数据库路径（包含 XML 文件的目录）:")
    print("  示例: C:\\STM32\\STM32CUBEMX\\db\\mcu")
    print("        /home/user/STM32CubeMX/db/mcu")
    
    while True:
        path_str = input("\n路径: ").strip()
        if not path_str:
            continue
        
        path = Path(path_str)
        if path.exists():
            xml_files = list(path.glob("*.xml"))
            if xml_files:
                print(f"✓ 找到 {len(xml_files)} 个 XML 文件")
                return path
            else:
                print("✗ 该目录下没有 XML 文件")
        else:
            print("✗ 路径不存在")


# ─── 主工具类 ────────────────────────────────────────────────────────────────

class STM32Toolkit:
    """STM32 数据工具包"""
    
    def __init__(self, db_path: Optional[Path] = None, output_dir: Optional[Path] = None):
        # 数据库路径：优先使用参数，否则自动查找
        if db_path:
            self.db_path = db_path
        else:
            self.db_path = find_database_path()
        
        # 输出目录
        self.output_dir = output_dir or DEFAULT_OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def scan_database(self, prompt_if_missing: bool = True) -> list[MCUIndex]:
        """扫描数据库，返回所有可用芯片"""
        # 如果没有数据库路径，尝试查找或提示用户
        if not self.db_path or not self.db_path.exists():
            if prompt_if_missing:
                self.db_path = prompt_database_path()
            else:
                print("错误: 未找到 STM32CUBEMX 数据库", file=sys.stderr)
                return []
        
        print(f"扫描数据库: {self.db_path}")
        
        xml_files = list(self.db_path.glob('*.xml'))
        print(f"找到 {len(xml_files)} 个 XML 文件")
        
        mcus = []
        for xml_file in xml_files:
            mcu = STM32XMLParser.parse_quick(xml_file)
            if mcu:
                mcus.append(mcu)
        
        # 按系列和名称排序
        mcus.sort(key=lambda x: (x.family, x.ref_name))
        
        return mcus
    
    def list_families(self, mcus: list[MCUIndex]) -> dict[str, list[MCUIndex]]:
        """按系列分组"""
        families = {}
        for mcu in mcus:
            if mcu.family not in families:
                families[mcu.family] = []
            families[mcu.family].append(mcu)
        return families
    
    def interactive_select(self, mcus: list[MCUIndex]) -> list[MCUIndex]:
        """交互式选择芯片"""
        families = self.list_families(mcus)
        
        print("\n" + "=" * 70)
        print("STM32 芯片选择")
        print("=" * 70)
        
        # 显示系列列表
        print("\n可用系列:")
        family_list = sorted(families.keys())
        for i, family in enumerate(family_list, 1):
            print(f"  {i:2d}. {family} ({len(families[family])} 个芯片)")
        
        print("\n选择方式:")
        print("  - 输入系列编号（如 1,3,5）导入整个系列")
        print("  - 输入 'all' 导入所有芯片")
        print("  - 输入 'common' 导入常用芯片")
        print("  - 输入 'q' 退出")
        
        choice = input("\n请选择: ").strip()
        
        if choice.lower() == 'q':
            return []
        
        if choice.lower() == 'all':
            return mcus
        
        if choice.lower() == 'common':
            return [m for m in mcus if m.ref_name in COMMON_MCUS]
        
        # 解析编号
        selected = []
        try:
            indices = [int(x.strip()) for x in choice.split(',')]
            for idx in indices:
                if 1 <= idx <= len(family_list):
                    family = family_list[idx - 1]
                    selected.extend(families[family])
        except ValueError:
            print("无效输入")
            return []
        
        return selected
    
    def import_mcus(self, mcus: list[MCUIndex], show_progress: bool = True) -> dict[str, MCUData]:
        """导入选中的芯片"""
        results = {}
        total = len(mcus)
        
        print(f"\n导入 {total} 个芯片:")
        print("-" * 60)
        
        for i, mcu_index in enumerate(mcus, 1):
            xml_path = self.db_path / f"{mcu_index.file_name}.xml"
            
            if show_progress:
                print(f"  [{i}/{total}] {mcu_index.ref_name}...", end=" ")
            
            # 解析完整数据
            mcu_data = STM32XMLParser.parse(xml_path)
            
            if mcu_data:
                results[mcu_index.ref_name] = mcu_data
                if show_progress:
                    print(f"✓ {len(mcu_data.pins)} pins")
            else:
                if show_progress:
                    print("✗ 失败")
        
        return results
    
    def save_mcu_data(self, mcu_name: str, mcu_data: MCUData) -> Path:
        """保存 MCU 数据到文件"""
        studio_data = DataConverter.to_studio_format(mcu_data)
        
        family = mcu_data.family
        family_dir = self.output_dir / 'mcu' / family
        family_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存 Studio 格式
        studio_path = family_dir / f"{mcu_name}.json"
        with open(studio_path, 'w', encoding='utf-8') as f:
            json.dump(studio_data, f, ensure_ascii=False, indent=2)
        
        # 保存 EFW 格式
        efw_data = DataConverter.to_efw_format(studio_data)
        efw_path = family_dir / f"{mcu_name}_efw.json"
        with open(efw_path, 'w', encoding='utf-8') as f:
            json.dump(efw_data, f, ensure_ascii=False, indent=2)
        
        # 保存开发板配置
        board_data = {
            'name': mcu_data.board or mcu_name,
            'mcu': mcu_name,
            'family': mcu_data.family,
            'core': mcu_data.core,
            'frequency_mhz': mcu_data.frequency_mhz,
            'flash_kb': mcu_data.flash_kb,
            'ram_kb': mcu_data.ram_kb,
            'package': mcu_data.package,
            'gpio_count': studio_data['gpio_count'],
            'gpio_pins': studio_data['gpio_pins'],
            'peripherals': studio_data['peripherals'],
        }
        board_dir = self.output_dir / 'board_profiles'
        board_dir.mkdir(parents=True, exist_ok=True)
        board_name = (mcu_data.board or mcu_name).replace(' ', '_')
        board_path = board_dir / f"{board_name}.json"
        with open(board_path, 'w', encoding='utf-8') as f:
            json.dump(board_data, f, ensure_ascii=False, indent=2)
        
        return studio_path
    
    def update_index(self, mcus: dict[str, MCUData]) -> Path:
        """更新索引文件"""
        index = {}
        
        for mcu_name, mcu_data in mcus.items():
            gpio_count = sum(1 for p in mcu_data.pins if p.functions['gpio'])
            index[mcu_name] = {
                'family': mcu_data.family,
                'core': mcu_data.core,
                'frequency_mhz': mcu_data.frequency_mhz,
                'flash_kb': mcu_data.flash_kb,
                'ram_kb': mcu_data.ram_kb,
                'package': mcu_data.package,
                'gpio_count': gpio_count,
                'board': mcu_data.board,
                'path': f"{mcu_data.family}/{mcu_name}.json",
            }
        
        index_path = self.output_dir / 'mcu' / 'index.json'
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        
        return index_path
    
    def get_mcu_info(self, mcu_name: str) -> Optional[dict]:
        """获取芯片信息"""
        index_path = self.output_dir / 'mcu' / 'index.json'
        if not index_path.exists():
            return None
        
        with open(index_path, 'r', encoding='utf-8') as f:
            index = json.load(f)
        
        if mcu_name not in index:
            return None
        
        chip_path = self.output_dir / 'mcu' / index[mcu_name]['path']
        if not chip_path.exists():
            return None
        
        with open(chip_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def list_imported(self) -> list[dict]:
        """列出已导入芯片"""
        index_path = self.output_dir / 'mcu' / 'index.json'
        if not index_path.exists():
            return []
        
        with open(index_path, 'r', encoding='utf-8') as f:
            index = json.load(f)
        
        return [{'name': name, **info} for name, info in index.items()]


# ─── CLI 入口 ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='STM32 MCU 数据导入一体化工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 交互式选择（自动查找数据库）
  python3 stm32_toolkit.py import
  
  # 指定数据库路径
  python3 stm32_toolkit.py import --db /path/to/STM32CUBEMX/db/mcu
  
  # 扫描数据库
  python3 stm32_toolkit.py scan
  
  # 按系列导入
  python3 stm32_toolkit.py import --family STM32F4
  
  # 按名称模式导入
  python3 stm32_toolkit.py import --filter "STM32F407*"
  
  # 导入常用芯片
  python3 stm32_toolkit.py import --common
  
  # 列出已导入芯片
  python3 stm32_toolkit.py list
  
  # 查看芯片信息
  python3 stm32_toolkit.py info STM32F407VGT6
        """
    )
    
    # 全局参数
    parser.add_argument('--db', type=Path, help='STM32CUBEMX 数据库路径')
    parser.add_argument('--output', '-o', type=Path, default=DEFAULT_OUTPUT_DIR, help='输出目录')
    parser.add_argument('--auto', action='store_true', help='自动查找数据库路径')
    
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # scan 命令
    subparsers.add_parser('scan', help='扫描数据库')
    
    # import 命令
    import_parser = subparsers.add_parser('import', help='导入芯片数据')
    import_parser.add_argument('--family', help='按系列导入（如 STM32F4）')
    import_parser.add_argument('--filter', help='按名称模式导入（如 STM32F407*）')
    import_parser.add_argument('--common', action='store_true', help='导入常用芯片')
    import_parser.add_argument('--interactive', '-i', action='store_true', default=True, help='交互式选择')
    
    # list 命令
    subparsers.add_parser('list', help='列出已导入芯片')
    
    # info 命令
    info_parser = subparsers.add_parser('info', help='查看芯片信息')
    info_parser.add_argument('mcu', help='芯片名称')
    
    # export 命令
    export_parser = subparsers.add_parser('export', help='导出芯片数据')
    export_parser.add_argument('mcu', help='芯片名称')
    export_parser.add_argument('--format', choices=['studio', 'efw'], default='studio', help='输出格式')
    
    # config 命令（显示/设置配置）
    config_parser = subparsers.add_parser('config', help='显示/设置配置')
    config_parser.add_argument('--show', action='store_true', help='显示当前配置')
    config_parser.add_argument('--set-db', type=Path, help='设置默认数据库路径')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 0
    
    # 创建工具实例
    toolkit = STM32Toolkit(
        db_path=args.db,
        output_dir=args.output,
    )
    
    # config 命令特殊处理
    if args.command == 'config':
        if args.show:
            print(f"数据库路径: {toolkit.db_path or '未设置'}")
            print(f"输出目录: {toolkit.output_dir}")
            print(f"\n默认搜索路径:")
            for path in DEFAULT_DB_PATHS:
                exists = "✓" if path.exists() else "✗"
                print(f"  {exists} {path}")
        elif args.set_db:
            print(f"数据库路径已设置为: {args.set_db}")
            # 这里可以保存到配置文件
        return 0
    
    # 执行命令
    if args.command == 'scan':
        mcus = toolkit.scan_database()
        families = toolkit.list_families(mcus)
        
        print(f"\n扫描完成，共 {len(mcus)} 个芯片")
        print("\n各系列统计:")
        for family in sorted(families.keys()):
            print(f"  {family}: {len(families[family])} 个")
        
        # 显示前 20 个
        print(f"\n前 20 个芯片:")
        for mcu in mcus[:20]:
            print(f"  {mcu.ref_name} ({mcu.package}, {mcu.io_count} IO)")
        if len(mcus) > 20:
            print(f"  ... 还有 {len(mcus) - 20} 个")
    
    elif args.command == 'import':
        # 扫描数据库
        all_mcus = toolkit.scan_database()
        
        # 筛选芯片
        if args.family:
            selected = [m for m in all_mcus if m.family == args.family]
            print(f"\n按系列 '{args.family}' 筛选: {len(selected)} 个芯片")
        elif args.filter:
            selected = [m for m in all_mcus if fnmatch.fnmatch(m.ref_name, args.filter)]
            print(f"\n按模式 '{args.filter}' 筛选: {len(selected)} 个芯片")
        elif args.common:
            selected = [m for m in all_mcus if m.ref_name in COMMON_MCUS]
            print(f"\n常用芯片: {len(selected)} 个")
        else:
            # 交互式选择
            selected = toolkit.interactive_select(all_mcus)
        
        if not selected:
            print("未选择任何芯片")
            return 0
        
        # 确认导入
        print(f"\n将导入 {len(selected)} 个芯片:")
        for mcu in selected[:10]:
            print(f"  - {mcu.ref_name}")
        if len(selected) > 10:
            print(f"  ... 还有 {len(selected) - 10} 个")
        
        confirm = input("\n确认导入? (y/N): ").strip().lower()
        if confirm != 'y':
            print("已取消")
            return 0
        
        # 导入
        mcus = toolkit.import_mcus(selected)
        
        if mcus:
            print(f"\n保存数据...")
            for mcu_name, mcu_data in mcus.items():
                path = toolkit.save_mcu_data(mcu_name, mcu_data)
            
            index_path = toolkit.update_index(mcus)
            print(f"\n索引已更新: {index_path}")
        
        print("\n" + "=" * 60)
        print(f"导入完成！共 {len(mcus)} 个芯片")
        print("=" * 60)
    
    elif args.command == 'list':
        mcus = toolkit.list_imported()
        
        if not mcus:
            print("没有已导入芯片，请先运行 import 命令")
            return 0
        
        print(f"\n已导入芯片 ({len(mcus)} 个):")
        print("-" * 60)
        
        for mcu in mcus:
            print(f"  {mcu['name']}:")
            print(f"    系列: {mcu['family']}")
            print(f"    核心: {mcu['core']}")
            print(f"    频率: {mcu['frequency_mhz']} MHz")
            print(f"    GPIO: {mcu['gpio_count']} 个")
            print(f"    开发板: {mcu.get('board', 'N/A')}")
            print()
    
    elif args.command == 'info':
        info = toolkit.get_mcu_info(args.mcu)
        
        if not info:
            print(f"未找到芯片: {args.mcu}")
            return 1
        
        print(f"\n芯片信息: {info['name']}")
        print("=" * 60)
        print(f"  系列: {info['family']}")
        print(f"  核心: {info['core']}")
        print(f"  频率: {info['frequency_mhz']} MHz")
        print(f"  Flash: {info['flash_kb']} KB")
        print(f"  RAM: {info['ram_kb']} KB")
        print(f"  封装: {info['package']}")
        print(f"  GPIO: {info['gpio_count']} 个")
        print()
        
        print("外设:")
        peripherals = info.get('peripherals', {})
        print(f"  ADC: {peripherals.get('adc', {}).get('count', 0)} 通道")
        print(f"  PWM: {peripherals.get('pwm', {}).get('count', 0)} 路")
        print(f"  UART: {list(peripherals.get('uart', {}).get('ports', {}).keys())}")
        print(f"  I2C: {list(peripherals.get('i2c', {}).get('ports', {}).keys())}")
        print(f"  SPI: {list(peripherals.get('spi', {}).get('ports', {}).keys())}")
    
    elif args.command == 'export':
        info = toolkit.get_mcu_info(args.mcu)
        
        if not info:
            print(f"未找到芯片: {args.mcu}")
            return 1
        
        if args.format == 'efw':
            # 转换为 EFW 格式
            from tools.studio.chip_database import DataConverter
            output = DataConverter.to_efw_format(info)
        else:
            output = info
        
        print(json.dumps(output, ensure_ascii=False, indent=2))
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
