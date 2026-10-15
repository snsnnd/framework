#!/usr/bin/env python3
"""Chip selection wizard dialog for EFW Studio."""

from __future__ import annotations

from typing import Any

import importlib.util

if importlib.util.find_spec("PyQt6") is not None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import (
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QPushButton,
        QSplitter,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
    QT_LIB = "PyQt6"
elif importlib.util.find_spec("PyQt5") is not None:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import (
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QPushButton,
        QSplitter,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
    QT_LIB = "PyQt5"
else:
    QDialog = QWidget = object
    QT_LIB = "missing"

from studio.chip_database import (
    CHIP_DATABASE,
    chip_to_board_profile,
    get_models,
    get_series,
    get_vendors,
)


class ChipSelectionDialog(QDialog):
    """Dialog for selecting a chip from the built-in database."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("芯片选择向导")
        self.setMinimumSize(700, 500)
        self.selected_chip: str | None = None
        self.selected_profile: dict[str, Any] | None = None
        self._build_ui()
        self._populate_filters()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Filter section
        filter_group = QGroupBox("筛选芯片")
        filter_layout = QHBoxLayout(filter_group)

        filter_layout.addWidget(QLabel("厂商:"))
        self.vendor_combo = QComboBox()
        self.vendor_combo.currentTextChanged.connect(self._on_vendor_changed)
        filter_layout.addWidget(self.vendor_combo)

        filter_layout.addWidget(QLabel("系列:"))
        self.series_combo = QComboBox()
        self.series_combo.currentTextChanged.connect(self._on_series_changed)
        filter_layout.addWidget(self.series_combo)

        filter_layout.addWidget(QLabel("搜索:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("输入型号关键词...")
        self.search_edit.textChanged.connect(self._on_search_changed)
        filter_layout.addWidget(self.search_edit)

        layout.addWidget(filter_group)

        # Main content: list + details
        splitter = QSplitter(Qt.Orientation.Horizontal if hasattr(Qt, "Orientation") else Qt.Horizontal)

        # Chip list
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.addWidget(QLabel("可用芯片:"))
        self.chip_list = QListWidget()
        self.chip_list.currentItemChanged.connect(self._on_chip_selected)
        self.chip_list.itemDoubleClicked.connect(self._on_chip_double_click)
        list_layout.addWidget(self.chip_list)
        splitter.addWidget(list_widget)

        # Chip details
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.addWidget(QLabel("芯片详情:"))
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        detail_layout.addWidget(self.detail_text)
        splitter.addWidget(detail_widget)

        splitter.setSizes([250, 450])
        layout.addWidget(splitter)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            if hasattr(QDialogButtonBox, "StandardButton")
            else QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok if hasattr(QDialogButtonBox, "StandardButton") else QDialogButtonBox.Ok)
        self.ok_button.setEnabled(False)

    def _populate_filters(self) -> None:
        """Populate filter combo boxes."""
        self.vendor_combo.addItem("全部厂商")
        for vendor in get_vendors():
            self.vendor_combo.addItem(vendor)

        self.series_combo.addItem("全部系列")
        for series in get_series():
            self.series_combo.addItem(series)

        self._update_chip_list()

    def _on_vendor_changed(self, vendor: str) -> None:
        """Handle vendor filter change."""
        self.series_combo.blockSignals(True)
        self.series_combo.clear()
        self.series_combo.addItem("全部系列")
        if vendor == "全部厂商":
            for series in get_series():
                self.series_combo.addItem(series)
        else:
            for series in get_series(vendor):
                self.series_combo.addItem(series)
        self.series_combo.blockSignals(False)
        self._update_chip_list()

    def _on_series_changed(self, series: str) -> None:
        """Handle series filter change."""
        self._update_chip_list()

    def _on_search_changed(self, text: str) -> None:
        """Handle search text change."""
        self._update_chip_list()

    def _update_chip_list(self) -> None:
        """Update the chip list based on filters."""
        self.chip_list.clear()

        vendor = self.vendor_combo.currentText()
        series = self.series_combo.currentText()
        search = self.search_edit.text().strip().lower()

        vendor_filter = None if vendor == "全部厂商" else vendor
        series_filter = None if series == "全部系列" else series

        for chip_id in get_models(vendor_filter, series_filter):
            chip = CHIP_DATABASE[chip_id]
            label = chip["label"]

            # Apply search filter
            if search and search not in chip_id.lower() and search not in label.lower():
                continue

            item = QListWidgetItem(f"{chip['model']} - {label}")
            item.setData(Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole, chip_id)
            self.chip_list.addItem(item)

    def _on_chip_selected(self, current: QListWidgetItem, previous: QListWidgetItem) -> None:
        """Handle chip selection."""
        if current is None:
            self.selected_chip = None
            self.selected_profile = None
            self.detail_text.clear()
            self.ok_button.setEnabled(False)
            return

        chip_id = current.data(Qt.ItemDataRole.UserRole if hasattr(Qt, "ItemDataRole") else Qt.UserRole)
        self.selected_chip = chip_id
        self.selected_profile = chip_to_board_profile(chip_id)
        self._show_chip_details(chip_id)
        self.ok_button.setEnabled(True)

    def _on_chip_double_click(self, item: QListWidgetItem) -> None:
        """Handle chip double-click to accept."""
        self._on_accept()

    def _show_chip_details(self, chip_id: str) -> None:
        """Show chip details in the detail panel."""
        chip = CHIP_DATABASE.get(chip_id)
        if not chip:
            return

        details = []
        details.append(f"<b>{chip['label']}</b>")
        details.append("")
        details.append(f"<b>厂商:</b> {chip['vendor']}")
        details.append(f"<b>系列:</b> {chip['series']}")
        details.append(f"<b>型号:</b> {chip['model']}")
        details.append(f"<b>封装:</b> {chip.get('package', 'N/A')}")
        details.append("")
        details.append(f"<b>Flash:</b> {chip.get('flash_kb', 0)} KB")
        details.append(f"<b>RAM:</b> {chip.get('ram_kb', 0)} KB")
        details.append(f"<b>主频:</b> {chip.get('clock_mhz', 0)} MHz")
        details.append("")
        details.append(f"<b>GPIO端口:</b> {', '.join(chip['ports'])}")
        details.append(f"<b>每端口引脚:</b> {chip['pins_per_port']}")
        details.append(f"<b>定时器:</b> {', '.join(str(t) for t in chip['timers'])}")
        details.append(f"<b>PWM通道:</b> {len(chip['pwm_channels'])}")
        details.append("")
        details.append(f"<b>UART:</b> {', '.join(str(u) for u in chip.get('uart', []))}")
        details.append(f"<b>I2C:</b> {', '.join(str(i) for i in chip.get('i2c', []))}")
        details.append(f"<b>SPI:</b> {', '.join(str(s) for s in chip.get('spi', []))}")
        details.append(f"<b>ADC:</b> {', '.join(str(a) for a in chip.get('adc', []))}")

        if chip.get('wifi'):
            details.append("<br><b>WiFi:</b> ✓")
        if chip.get('bluetooth'):
            details.append("<b>蓝牙:</b> ✓")
        if chip.get('usb'):
            details.append("<b>USB:</b> ✓")

        if chip.get('notes'):
            details.append("")
            details.append(f"<i>{chip['notes']}</i>")

        self.detail_text.setHtml("<br>".join(details))

    def _on_accept(self) -> None:
        """Handle dialog acceptance."""
        if self.selected_chip:
            self.accept()

    def get_selected_chip_id(self) -> str | None:
        """Get the selected chip ID."""
        return self.selected_chip

    def get_selected_profile(self) -> dict[str, Any] | None:
        """Get the selected chip as a board profile."""
        return self.selected_profile


class ChipImportResultDialog(QDialog):
    """Dialog showing imported chip configuration results."""

    def __init__(self, config: dict[str, Any], source: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("导入结果")
        self.setMinimumSize(500, 400)
        self.config = config
        self.source = source
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"<b>来源:</b> {self.source}"))
        layout.addWidget(QLabel("<b>解析结果:</b>"))

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        layout.addWidget(self.result_text)

        # Show parsed config
        details = []
        if "mcu" in self.config:
            details.append(f"MCU: {self.config['mcu']}")
        if "ports" in self.config:
            details.append(f"GPIO端口: {', '.join(self.config['ports'])}")
        if "timers" in self.config:
            details.append(f"定时器: {', '.join(str(t) for t in self.config['timers'])}")
        if "pwm_channels" in self.config:
            details.append(f"PWM通道: {len(self.config['pwm_channels'])}")
        if "uart" in self.config:
            details.append(f"UART: {', '.join(str(u) for u in self.config['uart'])}")
        if "i2c" in self.config:
            details.append(f"I2C: {', '.join(str(i) for i in self.config['i2c'])}")
        if "spi" in self.config:
            details.append(f"SPI: {', '.join(str(s) for s in self.config['spi'])}")

        self.result_text.setPlainText("\n".join(details))

        # Profile name input
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setText(self.config.get("mcu", "imported_chip").lower().replace(" ", "_"))
        form.addRow("配置名称:", self.name_edit)
        layout.addLayout(form)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            if hasattr(QDialogButtonBox, "StandardButton")
            else QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_profile_name(self) -> str:
        """Get the configured profile name."""
        return self.name_edit.text().strip() or "imported_chip"

    def get_board_profile(self) -> dict[str, Any]:
        """Convert config to board profile format."""
        return {
            "label": self.config.get("mcu", "导入的配置"),
            "ports": self.config.get("ports", ["A", "B", "C"]),
            "pins_per_port": self.config.get("pins_per_port", 16),
            "timers": self.config.get("timers", [1, 2, 3, 4]),
            "pwm_channels": self.config.get("pwm_channels", [1, 2, 3, 4]),
            "notes": f"从 {self.source} 导入"
        }
