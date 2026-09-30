"""
MCU 芯片数据库加载器

从 data/mcu/ 目录加载真实芯片数据，供仿真器使用。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


# 数据目录
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
MCU_DIR = DATA_DIR / "mcu"


class ChipDatabase:
    """芯片数据库"""
    
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or DATA_DIR
        self.mcu_dir = self.data_dir / "mcu"
        self._index: Optional[dict] = None
        self._cache: dict[str, dict] = {}
    
    @property
    def available(self) -> bool:
        """数据库是否可用"""
        return self.mcu_dir.exists() and (self.mcu_dir / "index.json").exists()
    
    def load_index(self) -> dict:
        """加载芯片索引"""
        if self._index is not None:
            return self._index
        
        index_path = self.mcu_dir / "index.json"
        if not index_path.exists():
            self._index = {}
            return self._index
        
        with open(index_path, "r", encoding="utf-8") as f:
            self._index = json.load(f)
        
        return self._index
    
    def list_chips(self) -> list[str]:
        """列出所有可用芯片"""
        index = self.load_index()
        return list(index.keys())
    
    def get_chip_info(self, chip_name: str) -> Optional[dict]:
        """获取芯片基本信息"""
        index = self.load_index()
        return index.get(chip_name)
    
    def load_chip(self, chip_name: str) -> Optional[dict]:
        """加载芯片完整数据"""
        # 检查缓存
        if chip_name in self._cache:
            return self._cache[chip_name]
        
        # 从索引获取路径
        index = self.load_index()
        if chip_name not in index:
            return None
        
        chip_path = self.mcu_dir / index[chip_name]["path"]
        if not chip_path.exists():
            return None
        
        # 加载数据
        with open(chip_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # 缓存
        self._cache[chip_name] = data
        
        return data
    
    def get_gpio_pins(self, chip_name: str) -> list[str]:
        """获取 GPIO 引脚列表"""
        chip = self.load_chip(chip_name)
        if not chip:
            return []
        return chip.get("gpio_pins", [])
    
    def get_adc_channels(self, chip_name: str) -> dict[str, str]:
        """获取 ADC 通道映射"""
        chip = self.load_chip(chip_name)
        if not chip:
            return {}
        return chip.get("peripherals", {}).get("adc", {}).get("channels", {})
    
    def get_pwm_outputs(self, chip_name: str) -> dict[str, str]:
        """获取 PWM 输出映射"""
        chip = self.load_chip(chip_name)
        if not chip:
            return {}
        return chip.get("peripherals", {}).get("pwm", {}).get("outputs", {})
    
    def get_uart_ports(self, chip_name: str) -> dict[str, dict]:
        """获取 UART 端口映射"""
        chip = self.load_chip(chip_name)
        if not chip:
            return {}
        return chip.get("peripherals", {}).get("uart", {}).get("ports", {})
    
    def get_i2c_ports(self, chip_name: str) -> dict[str, dict]:
        """获取 I2C 端口映射"""
        chip = self.load_chip(chip_name)
        if not chip:
            return {}
        return chip.get("peripherals", {}).get("i2c", {}).get("ports", {})
    
    def get_spi_ports(self, chip_name: str) -> dict[str, dict]:
        """获取 SPI 端口映射"""
        chip = self.load_chip(chip_name)
        if not chip:
            return {}
        return chip.get("peripherals", {}).get("spi", {}).get("ports", {})
    
    def get_pin_functions(self, chip_name: str, pin_name: str) -> Optional[dict]:
        """获取引脚功能"""
        chip = self.load_chip(chip_name)
        if not chip:
            return None
        return chip.get("pins", {}).get(pin_name)
    
    def search_chips(self, query: str) -> list[str]:
        """搜索芯片"""
        index = self.load_index()
        query = query.upper()
        
        results = []
        for name in index.keys():
            if query in name.upper():
                results.append(name)
        
        return sorted(results)
    
    def get_chips_by_family(self, family: str) -> list[str]:
        """按系列获取芯片"""
        index = self.load_index()
        
        results = []
        for name, info in index.items():
            if info.get("family", "").upper() == family.upper():
                results.append(name)
        
        return sorted(results)
    
    def get_families(self) -> list[str]:
        """获取所有系列"""
        index = self.load_index()
        
        families = set()
        for info in index.values():
            families.add(info.get("family", ""))
        
        return sorted(families)


# 全局实例
_default_db: Optional[ChipDatabase] = None


def get_chip_database() -> ChipDatabase:
    """获取默认芯片数据库"""
    global _default_db
    if _default_db is None:
        _default_db = ChipDatabase()
    return _default_db


def list_available_chips() -> list[str]:
    """列出所有可用芯片"""
    return get_chip_database().list_chips()


def load_chip_data(chip_name: str) -> Optional[dict]:
    """加载芯片数据"""
    return get_chip_database().load_chip(chip_name)


# ─── 使用示例 ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    db = get_chip_database()
    
    if not db.available:
        print("芯片数据库不可用，请先运行导入工具:")
        print("  python3 tools/stm32_toolkit.py import")
        exit(1)
    
    print(f"芯片数据库: {db.mcu_dir}")
    print(f"可用芯片: {len(db.list_chips())} 个")
    print()
    
    # 列出所有芯片
    print("芯片列表:")
    for chip in db.list_chips():
        info = db.get_chip_info(chip)
        print(f"  {chip}: {info.get('family')}, {info.get('core')}, {info.get('frequency_mhz')} MHz")
