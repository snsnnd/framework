#!/usr/bin/env python3
"""PyQt ground station for EFW PID telemetry and live data visualization."""

from __future__ import annotations

import csv
import sys
import threading
import time
from pathlib import Path
from typing import Iterable

import importlib.util

if importlib.util.find_spec("PyQt6") is not None:
    from PyQt6.QtCore import QObject, QTimer, pyqtSignal
    from PyQt6.QtWidgets import (
        QApplication,
        QComboBox,
        QFileDialog,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )
    QT_LIB = "PyQt6"
elif importlib.util.find_spec("PyQt5") is not None:
    from PyQt5.QtCore import QObject, QTimer, pyqtSignal
    from PyQt5.QtWidgets import (
        QApplication,
        QComboBox,
        QFileDialog,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )
    QT_LIB = "PyQt5"
else:
    QApplication = None
    QObject = object
    QMainWindow = object

    class _MissingSignal:
        def __init__(self, *args, **kwargs):
            pass

        def connect(self, *args, **kwargs):
            pass

        def emit(self, *args, **kwargs):
            pass

    def pyqtSignal(*args, **kwargs):
        return _MissingSignal()

    QT_LIB = "missing"

if importlib.util.find_spec("pyqtgraph") is not None:
    import pyqtgraph as pg
else:  # pragma: no cover - optional dependency.
    pg = None

if importlib.util.find_spec("serial") is not None:
    import serial
    import serial.tools.list_ports
else:  # pragma: no cover - optional dependency.
    serial = None

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "tools"))

from efw_telemetry import (  # noqa: E402
    FrameParser,
    ParamSet,
    TelemetryBuffer,
    TelemetrySample,
    analyze_step,
    encode_param_set,
    simulated_frames,
)


class TelemetryBridge(QObject):
    sample_received = pyqtSignal(object)
    status_changed = pyqtSignal(str)


class TelemetryWorker:
    def __init__(self, bridge: TelemetryBridge):
        self.bridge = bridge
        self.parser = FrameParser()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._serial = None

    def start_simulation(self) -> None:
        self.stop()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_simulation, daemon=True)
        self._thread.start()

    def start_serial(self, port: str, baudrate: int) -> None:
        if serial is None:
            raise RuntimeError("pyserial is not installed")
        self.stop()
        self._stop.clear()
        self._serial = serial.Serial(port=port, baudrate=baudrate, timeout=0.05)
        self._thread = threading.Thread(target=self._run_serial, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None
        self._thread = None

    def send_param_set(self, param: ParamSet) -> None:
        if self._serial is None:
            raise RuntimeError("serial port is not connected")
        self._serial.write(encode_param_set(param))

    def _emit_frames(self, chunks: Iterable[bytes]) -> None:
        for chunk in chunks:
            if self._stop.is_set():
                break
            for item in self.parser.feed(chunk):
                if isinstance(item, TelemetrySample):
                    self.bridge.sample_received.emit(item)

    def _run_simulation(self) -> None:
        self.bridge.status_changed.emit("simulation running")
        for frame in simulated_frames():
            if self._stop.is_set():
                break
            self._emit_frames([frame])
            time.sleep(0.02)
        self.bridge.status_changed.emit("stopped")

    def _run_serial(self) -> None:
        self.bridge.status_changed.emit("serial connected")
        while not self._stop.is_set() and self._serial is not None:
            data = self._serial.read(256)
            if data:
                self._emit_frames([data])
        self.bridge.status_changed.emit("stopped")


class GroundStationWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"EFW Ground Station ({QT_LIB})")
        self.resize(1180, 760)
        self.buffer = TelemetryBuffer(maxlen=3000)
        self.bridge = TelemetryBridge()
        self.worker = TelemetryWorker(self.bridge)
        self.current_key: tuple[int, int] | None = None
        self.bridge.sample_received.connect(self.on_sample)
        self.bridge.status_changed.connect(self.on_status)
        self._build_ui()
        self.refresh_ports()
        self.plot_timer = QTimer(self)
        self.plot_timer.timeout.connect(self.refresh_plot)
        self.plot_timer.start(80)

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        self.setCentralWidget(central)

        controls = QHBoxLayout()
        self.port_box = QComboBox()
        self.baud_edit = QLineEdit("115200")
        refresh_btn = QPushButton("Refresh Ports")
        refresh_btn.clicked.connect(self.refresh_ports)
        connect_btn = QPushButton("Connect Serial")
        connect_btn.clicked.connect(self.connect_serial)
        sim_btn = QPushButton("Start Simulation")
        sim_btn.clicked.connect(self.start_simulation)
        stop_btn = QPushButton("Stop")
        stop_btn.clicked.connect(self.stop_worker)
        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self.export_csv)
        controls.addWidget(QLabel("Port"))
        controls.addWidget(self.port_box)
        controls.addWidget(QLabel("Baud"))
        controls.addWidget(self.baud_edit)
        controls.addWidget(refresh_btn)
        controls.addWidget(connect_btn)
        controls.addWidget(sim_btn)
        controls.addWidget(stop_btn)
        controls.addWidget(export_btn)
        root.addLayout(controls)

        self.status_label = QLabel("idle")
        root.addWidget(self.status_label)

        main = QHBoxLayout()
        left = QVBoxLayout()
        self.channel_box = QComboBox()
        self.channel_box.currentTextChanged.connect(self.select_channel)
        left.addWidget(QLabel("Device/Channel"))
        left.addWidget(self.channel_box)

        form = QFormLayout()
        self.kp_edit = QLineEdit("18.0")
        self.ki_edit = QLineEdit("0.0")
        self.kd_edit = QLineEdit("2.5")
        form.addRow("Kp", self.kp_edit)
        form.addRow("Ki", self.ki_edit)
        form.addRow("Kd", self.kd_edit)
        left.addLayout(form)
        send_btn = QPushButton("Send PARAM_SET")
        send_btn.clicked.connect(self.send_param_set)
        left.addWidget(send_btn)

        self.analysis_table = QTableWidget(4, 2)
        self.analysis_table.setHorizontalHeaderLabels(["Metric", "Value"])
        for row, metric in enumerate(["overshoot", "steady_error", "iae", "oscillations"]):
            self.analysis_table.setItem(row, 0, QTableWidgetItem(metric))
            self.analysis_table.setItem(row, 1, QTableWidgetItem("0"))
        left.addWidget(self.analysis_table)
        main.addLayout(left, 1)

        if pg is not None:
            self.plot_widget = pg.PlotWidget(title="PID telemetry")
            self.plot_widget.addLegend()
            self.curves = {
                "target": self.plot_widget.plot(pen="g", name="target"),
                "feedback": self.plot_widget.plot(pen="y", name="feedback"),
                "error": self.plot_widget.plot(pen="r", name="error"),
                "output": self.plot_widget.plot(pen="c", name="output"),
            }
            main.addWidget(self.plot_widget, 4)
        else:
            self.plot_widget = QLabel("pyqtgraph is not installed; table/CSV/serial features are still available.")
            self.curves = {}
            main.addWidget(self.plot_widget, 4)
        root.addLayout(main)

    def refresh_ports(self) -> None:
        self.port_box.clear()
        if serial is None:
            self.port_box.addItem("pyserial missing")
            return
        ports = list(serial.tools.list_ports.comports())
        for port in ports:
            self.port_box.addItem(port.device)
        if not ports:
            self.port_box.addItem("no ports")

    def connect_serial(self) -> None:
        try:
            self.worker.start_serial(self.port_box.currentText(), int(self.baud_edit.text()))
        except Exception as exc:
            QMessageBox.warning(self, "Serial connect failed", str(exc))

    def start_simulation(self) -> None:
        self.worker.start_simulation()

    def stop_worker(self) -> None:
        self.worker.stop()

    def on_status(self, text: str) -> None:
        self.status_label.setText(text)

    def on_sample(self, sample: TelemetrySample) -> None:
        self.buffer.append(sample)
        label = f"{sample.device_id}:{sample.channel_id}"
        if label not in [self.channel_box.itemText(i) for i in range(self.channel_box.count())]:
            self.channel_box.addItem(label)
        if self.current_key is None:
            self.current_key = sample.key

    def select_channel(self, text: str) -> None:
        try:
            device, channel = text.split(":", 1)
            self.current_key = (int(device), int(channel))
        except ValueError:
            self.current_key = None

    def refresh_plot(self) -> None:
        if self.current_key is None:
            return
        samples = self.buffer.samples(self.current_key)
        if not samples:
            return
        xs = [s.time_ms / 1000.0 for s in samples]
        values = {
            "target": [s.target for s in samples],
            "feedback": [s.feedback for s in samples],
            "error": [s.error for s in samples],
            "output": [s.output for s in samples],
        }
        for name, curve in self.curves.items():
            curve.setData(xs, values[name])
        metrics = analyze_step(samples)
        for row, metric in enumerate(["overshoot", "steady_error", "iae", "oscillations"]):
            self.analysis_table.setItem(row, 1, QTableWidgetItem(f"{metrics[metric]:.4g}"))

    def send_param_set(self) -> None:
        if self.current_key is None:
            QMessageBox.warning(self, "No channel", "Select a device/channel first.")
            return
        try:
            param = ParamSet(
                self.current_key[0],
                self.current_key[1],
                float(self.kp_edit.text()),
                float(self.ki_edit.text()),
                float(self.kd_edit.text()),
            )
            self.worker.send_param_set(param)
        except Exception as exc:
            QMessageBox.warning(self, "PARAM_SET failed", str(exc))

    def export_csv(self) -> None:
        if self.current_key is None:
            QMessageBox.warning(self, "No channel", "Select a device/channel first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "efw_pid_scope.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as fp:
            writer = csv.writer(fp)
            writer.writerow(["device_id", "channel_id", "time_ms", "target", "feedback", "error", "output", "kp", "ki", "kd", "extra1", "extra2"])
            for sample in self.buffer.samples(self.current_key):
                writer.writerow([
                    sample.device_id,
                    sample.channel_id,
                    sample.time_ms,
                    sample.target,
                    sample.feedback,
                    sample.error,
                    sample.output,
                    sample.kp,
                    sample.ki,
                    sample.kd,
                    sample.extra1,
                    sample.extra2,
                ])


def main() -> int:
    if QApplication is None:
        print("PyQt is not installed. Install PyQt6 or PyQt5, then run tools/efw_ground_station.py.", file=sys.stderr)
        return 1
    app = QApplication(sys.argv)
    win = GroundStationWindow()
    win.show()
    return app.exec() if hasattr(app, "exec") else app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
