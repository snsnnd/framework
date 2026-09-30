"""PyQt 调试面板

提供可视化界面，用于实时监控 MCU 数据、比对分析、记录回放。
可嵌入 EFW Studio 或独立运行。
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# PyQt 导入
try:
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
        QTableWidget, QTableWidgetItem, QPushButton, QLabel,
        QComboBox, QLineEdit, QSpinBox, QCheckBox, QGroupBox,
        QFileDialog, QMessageBox, QStatusBar, QTabWidget,
        QSplitter, QTextEdit, QHeaderView, QProgressBar,
    )
    from PyQt6.QtCore import QTimer, pyqtSignal, QThread, Qt
    from PyQt6.QtGui import QColor, QFont, QIcon, QAction
    PYQT_VERSION = 6
except ImportError:
    try:
        from PyQt5.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
            QTableWidget, QTableWidgetItem, QPushButton, QLabel,
            QComboBox, QLineEdit, QSpinBox, QCheckBox, QGroupBox,
            QFileDialog, QMessageBox, QStatusBar, QTabWidget,
            QSplitter, QTextEdit, QHeaderView, QProgressBar,
        )
        from PyQt5.QtCore import QTimer, pyqtSignal, QThread, Qt
        from PyQt5.QtGui import QColor, QFont, QIcon, QAction
        PYQT_VERSION = 5
    except ImportError:
        raise ImportError("需要 PyQt5 或 PyQt6，请安装: pip install PyQt6")


class DataCollectionThread(QThread):
    """数据采集线程"""
    
    data_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, collector, interval_ms: int = 100):
        super().__init__()
        self.collector = collector
        self.interval_ms = interval_ms
        self._running = False
    
    def run(self):
        self._running = True
        interval_sec = self.interval_ms / 1000.0
        
        while self._running:
            try:
                snapshot = self.collector.read_snapshot()
                self.data_ready.emit(snapshot)
            except Exception as e:
                self.error_occurred.emit(str(e))
            
            time.sleep(interval_sec)
    
    def stop(self):
        self._running = False
        self.wait()


class DebugPanel(QWidget):
    """EFW 调试面板
    
    提供实时数据监控、比对分析、记录功能。
    
    使用方式：
        # 独立运行
        panel = DebugPanel()
        panel.show()
        
        # 嵌入其他窗口
        parent_layout.addWidget(DebugPanel())
    """
    
    # 信号
    data_updated = pyqtSignal(dict)
    issues_found = pyqtSignal(list)
    
    def __init__(self, parent=None, port: str = None, baud: int = 115200):
        super().__init__(parent)
        
        self.port = port
        self.baud = baud
        self.collector = None
        self.comparator = None
        self.recorder = None
        self.collection_thread = None
        
        self._snapshot_count = 0
        self._issue_count = 0
        self._start_time = None
        
        self.init_ui()
        
        # 如果指定了端口，自动连接
        if port:
            QTimer.singleShot(100, self.toggle_connection)
    
    def init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        
        # 工具栏
        toolbar = self.create_toolbar()
        layout.addLayout(toolbar)
        
        # 状态栏
        self.status_bar = QStatusBar()
        layout.addWidget(self.status_bar)
        
        # 主内容区域
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # 数据表格
        self.table = self.create_data_table()
        splitter.addWidget(self.table)
        
        # 问题列表
        self.issues_text = QTextEdit()
        self.issues_text.setReadOnly(True)
        self.issues_text.setMaximumHeight(150)
        splitter.addWidget(self.issues_text)
        
        layout.addWidget(splitter)
        
        # 统计信息
        stats_layout = QHBoxLayout()
        self.stats_label = QLabel("快照: 0 | 问题: 0 | 时间: 00:00:00")
        stats_layout.addWidget(self.stats_label)
        layout.addLayout(stats_layout)
    
    def create_toolbar(self) -> QHBoxLayout:
        """创建工具栏"""
        toolbar = QHBoxLayout()
        
        # 连接控制
        self.connect_btn = QPushButton("连接 MCU")
        self.connect_btn.clicked.connect(self.toggle_connection)
        toolbar.addWidget(self.connect_btn)
        
        # 端口选择
        toolbar.addWidget(QLabel("端口:"))
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setMinimumWidth(120)
        self.refresh_ports()
        toolbar.addWidget(self.port_combo)
        
        # 波特率
        toolbar.addWidget(QLabel("波特率:"))
        self.baud_spin = QSpinBox()
        self.baud_spin.setRange(1200, 921600)
        self.baud_spin.setValue(115200)
        self.baud_spin.setSingleStep(1200)
        toolbar.addWidget(self.baud_spin)
        
        toolbar.addStretch()
        
        # 记录控制
        self.record_btn = QPushButton("开始记录")
        self.record_btn.clicked.connect(self.toggle_recording)
        self.record_btn.setEnabled(False)
        toolbar.addWidget(self.record_btn)
        
        # 加载预期配置
        self.load_expected_btn = QPushButton("加载预期配置")
        self.load_expected_btn.clicked.connect(self.load_expected)
        toolbar.addWidget(self.load_expected_btn)
        
        # 刷新按钮
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_data)
        toolbar.addWidget(refresh_btn)
        
        return toolbar
    
    def create_data_table(self) -> QTableWidget:
        """创建数据表格"""
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["名称", "当前值", "预期值", "状态", "单位"])
        
        # 设置列宽
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        
        return table
    
    def refresh_ports(self):
        """刷新串口列表"""
        from .collector import list_serial_ports
        
        self.port_combo.clear()
        ports = list_serial_ports()
        for p in ports:
            self.port_combo.addItem(p["device"])
        
        if self.port:
            index = self.port_combo.findText(self.port)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)
    
    def toggle_connection(self):
        """切换连接状态"""
        if self.collector:
            self.disconnect()
        else:
            self.connect()
    
    def connect(self):
        """连接到 MCU"""
        from .collector import DebugCollector
        
        port = self.port_combo.currentText()
        baud = self.baud_spin.value()
        
        if not port:
            QMessageBox.warning(self, "警告", "请选择串口")
            return
        
        try:
            self.status_bar.showMessage("正在连接...")
            self.repaint()
            
            self.collector = DebugCollector(port=port, baud=baud)
            self.collector.connect()
            
            # 启动数据采集线程
            self.collection_thread = DataCollectionThread(self.collector, interval_ms=100)
            self.collection_thread.data_ready.connect(self.on_data_ready)
            self.collection_thread.error_occurred.connect(self.on_error)
            self.collection_thread.start()
            
            self._start_time = time.time()
            
            self.connect_btn.setText("断开")
            self.record_btn.setEnabled(True)
            self.port_combo.setEnabled(False)
            self.baud_spin.setEnabled(False)
            
            self.status_bar.showMessage(f"已连接到 {port}")
        
        except Exception as e:
            QMessageBox.critical(self, "连接失败", str(e))
            self.collector = None
            self.status_bar.showMessage("连接失败")
    
    def disconnect(self):
        """断开连接"""
        if self.collection_thread:
            self.collection_thread.stop()
            self.collection_thread = None
        
        if self.recorder:
            self.stop_recording()
        
        if self.collector:
            self.collector.disconnect()
            self.collector = None
        
        self.connect_btn.setText("连接 MCU")
        self.record_btn.setEnabled(False)
        self.port_combo.setEnabled(True)
        self.baud_spin.setEnabled(True)
        
        self.status_bar.showMessage("已断开")
    
    def on_data_ready(self, snapshot: dict):
        """数据就绪回调"""
        self._snapshot_count += 1
        
        # 更新表格
        self.update_table(snapshot)
        
        # 比对
        issues = []
        if self.comparator:
            result = self.comparator.compare(snapshot)
            if result.has_issues:
                issues = [
                    {
                        "name": i.name,
                        "type": i.type.value,
                        "detail": i.detail,
                        "severity": i.severity,
                    }
                    for i in result.issues
                ]
                self._issue_count += len(issues)
                self.update_issues_display(issues)
        
        # 记录
        if self.recorder:
            self.recorder.record(snapshot)
            for issue in issues:
                self.recorder.record_issue(issue)
        
        # 更新统计
        self.update_stats()
        
        # 发送信号
        self.data_updated.emit(snapshot)
        if issues:
            self.issues_found.emit(issues)
    
    def on_error(self, error_msg: str):
        """错误回调"""
        self.status_bar.showMessage(f"错误: {error_msg}")
    
    def update_table(self, snapshot: dict):
        """更新数据表格"""
        params = snapshot.get("params", {})
        
        self.table.setRowCount(len(params))
        
        for row, (name, info) in enumerate(params.items()):
            value = info.get("value")
            unit = info.get("unit", "")
            status = info.get("status", "OK")
            
            # 名称
            self.table.setItem(row, 0, QTableWidgetItem(name))
            
            # 当前值
            value_item = QTableWidgetItem(str(value))
            self.table.setItem(row, 1, value_item)
            
            # 预期值
            expected_value = "-"
            if self.comparator and name in self.comparator._expectations:
                exp = self.comparator._expectations[name]
                if exp.exact_value is not None:
                    expected_value = str(exp.exact_value)
                elif exp.min_value is not None or exp.max_value is not None:
                    expected_value = f"{exp.min_value or '-'} ~ {exp.max_value or '-'}"
            self.table.setItem(row, 2, QTableWidgetItem(expected_value))
            
            # 状态
            status_item = QTableWidgetItem(status)
            if status == "OK":
                status_item.setBackground(QColor(200, 255, 200))
            else:
                status_item.setBackground(QColor(255, 200, 200))
            self.table.setItem(row, 3, status_item)
            
            # 单位
            self.table.setItem(row, 4, QTableWidgetItem(unit))
    
    def update_issues_display(self, issues: list):
        """更新问题显示"""
        for issue in issues:
            severity = issue.get("severity", "warning")
            name = issue.get("name", "")
            detail = issue.get("detail", "")
            
            if severity == "error":
                color = "red"
                icon = "✗"
            elif severity == "warning":
                color = "orange"
                icon = "⚠"
            else:
                color = "blue"
                icon = "ℹ"
            
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.issues_text.append(
                f'<span style="color: {color};">[{timestamp}] {icon} {name}: {detail}</span>'
            )
    
    def update_stats(self):
        """更新统计信息"""
        elapsed = time.time() - self._start_time if self._start_time else 0
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        
        self.stats_label.setText(
            f"快照: {self._snapshot_count} | 问题: {self._issue_count} | "
            f"时间: {hours:02d}:{minutes:02d}:{seconds:02d}"
        )
    
    def refresh_data(self):
        """手动刷新数据"""
        if not self.collector:
            return
        
        try:
            snapshot = self.collector.read_snapshot()
            self.on_data_ready(snapshot)
        except Exception as e:
            self.status_bar.showMessage(f"刷新失败: {e}")
    
    def toggle_recording(self):
        """切换记录状态"""
        if self.recorder:
            self.stop_recording()
        else:
            self.start_recording()
    
    def start_recording(self):
        """开始记录"""
        from .recorder import DebugRecorder
        
        # 选择保存路径
        default_name = f"debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        path, _ = QFileDialog.getSaveFileName(
            self, "保存记录", default_name, "JSONL Files (*.jsonl)"
        )
        
        if not path:
            return
        
        self.recorder = DebugRecorder(path)
        self.recorder.start()
        
        self.record_btn.setText("停止记录")
        self.status_bar.showMessage(f"记录中: {path}")
    
    def stop_recording(self):
        """停止记录"""
        if self.recorder:
            stats = self.recorder.stop()
            self.recorder = None
            
            self.record_btn.setText("开始记录")
            self.status_bar.showMessage(
                f"记录完成: {stats.get('record_count', 0)} 条记录"
            )
    
    def load_expected(self):
        """加载预期配置"""
        from .comparator import DebugComparator
        
        path, _ = QFileDialog.getOpenFileName(
            self, "加载预期配置", "", "JSON Files (*.json)"
        )
        
        if not path:
            return
        
        try:
            self.comparator = DebugComparator.from_file(path)
            self.status_bar.showMessage(f"已加载预期配置: {path}")
            
            # 立即刷新显示
            if self.collector:
                self.refresh_data()
        except Exception as e:
            QMessageBox.critical(self, "加载失败", str(e))
    
    def closeEvent(self, event):
        """关闭事件"""
        self.disconnect()
        event.accept()


class DebugPanelWindow(QWidget):
    """独立窗口版本的调试面板"""
    
    def __init__(self, port: str = None, baud: int = 115200):
        super().__init__()
        self.setWindowTitle("EFW 调试面板")
        self.setMinimumSize(800, 600)
        
        layout = QVBoxLayout(self)
        self.panel = DebugPanel(self, port=port, baud=baud)
        layout.addWidget(self.panel)


def main(port: str = None, baud: int = 115200) -> int:
    """启动调试面板"""
    try:
        if PYQT_VERSION == 6:
            from PyQt6.QtWidgets import QApplication
        else:
            from PyQt5.QtWidgets import QApplication
        
        app = QApplication(sys.argv)
        window = DebugPanelWindow(port=port, baud=baud)
        window.show()
        return app.exec()
    except Exception as e:
        print(f"启动面板失败: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="EFW 调试面板")
    parser.add_argument("--port", help="串口设备路径")
    parser.add_argument("--baud", type=int, default=115200, help="波特率")
    
    args = parser.parse_args()
    sys.exit(main(port=args.port, baud=args.baud))
