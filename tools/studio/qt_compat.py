"""Unified Qt compatibility layer for EFW Studio.

This module provides a single import point for all Qt widgets and classes,
handling PyQt6/PyQt5 compatibility in one place. All other studio modules
should import from here instead of directly from PyQt6/PyQt5.

Usage:
    from studio.qt_compat import QWidget, QPushButton, QLabel, ...
"""

import importlib.util

# Detect Qt version
if importlib.util.find_spec("PyQt6") is not None:
    from PyQt6.QtCore import (
        Qt, QTimer, QRectF, QPointF, QSizeF, QMimeData,
        QAbstractAnimation
    )
    from PyQt6.QtGui import (
        QBrush, QColor, QDrag, QFont, QFontMetrics, QKeySequence,
        QPen, QShortcut, QPainter, QPainterPath, QLinearGradient,
        QPixmap, QIcon
    )
    from PyQt6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QDockWidget,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QGraphicsEllipseItem,
        QGraphicsItem,
        QGraphicsLineItem,
        QGraphicsPathItem,
        QGraphicsRectItem,
        QGraphicsScene,
        QGraphicsSimpleTextItem,
        QGraphicsTextItem,
        QGraphicsView,
        QGroupBox,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMenu,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QScrollArea,
        QShortcut,
        QSpinBox,
        QSplitter,
        QStackedWidget,
        QTabBar,
        QTabWidget,
        QTableWidget,
        QTableWidgetItem,
        QTextEdit,
        QToolBox,
        QToolBar,
        QVBoxLayout,
        QWidget,
    )
    QT_LIB = "PyQt6"

    # Compatibility aliases
    def get_standard_button(button):
        """Get standard button enum for both Qt versions."""
        return getattr(QMessageBox.StandardButton, button)

    ItemDataRole = Qt.ItemDataRole.UserRole
    WindowType = Qt.WindowType
    Orientation = Qt.Orientation
    ScrollBarPolicy = Qt.ScrollBarPolicy
    DockWidgetArea = Qt.DockWidgetArea
    DockWidgetFeature = QDockWidget.DockWidgetFeature
    TabPosition = QTabWidget.TabPosition

elif importlib.util.find_spec("PyQt5") is not None:
    from PyQt5.QtCore import (
        Qt, QTimer, QRectF, QPointF, QSizeF, QMimeData,
        QAbstractAnimation
    )
    from PyQt5.QtGui import (
        QBrush, QColor, QDrag, QFont, QFontMetrics, QKeySequence,
        QPen, QPainter, QPainterPath, QLinearGradient,
        QPixmap, QIcon
    )
    from PyQt5.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QDockWidget,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QGraphicsEllipseItem,
        QGraphicsItem,
        QGraphicsLineItem,
        QGraphicsPathItem,
        QGraphicsRectItem,
        QGraphicsScene,
        QGraphicsSimpleTextItem,
        QGraphicsTextItem,
        QGraphicsView,
        QGroupBox,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMenu,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QScrollArea,
        QShortcut,
        QSpinBox,
        QSplitter,
        QStackedWidget,
        QTabBar,
        QTabWidget,
        QTableWidget,
        QTableWidgetItem,
        QTextEdit,
        QToolBox,
        QToolBar,
        QVBoxLayout,
        QWidget,
    )
    QT_LIB = "PyQt5"

    # Compatibility aliases
    def get_standard_button(button):
        """Get standard button enum for both Qt versions."""
        return getattr(QMessageBox, button)

    ItemDataRole = Qt.UserRole
    WindowType = Qt
    Orientation = Qt
    ScrollBarPolicy = Qt
    DockWidgetArea = Qt
    DockWidgetFeature = QDockWidget
    TabPosition = QTabWidget

else:
    # No Qt available - provide dummy classes
    QT_LIB = "missing"
    
    class _DummyClass:
        """Dummy class when Qt is not available."""
        def __getattr__(self, name):
            return _DummyClass()
        def __call__(self, *args, **kwargs):
            return _DummyClass()
    
    # Create dummy versions of all classes
    QApplication = _DummyClass()
    QCheckBox = _DummyClass()
    QComboBox = _DummyClass()
    QDialog = _DummyClass()
    QDialogButtonBox = _DummyClass()
    QDockWidget = _DummyClass()
    QDoubleSpinBox = _DummyClass()
    QFileDialog = _DummyClass()
    QFormLayout = _DummyClass()
    QGraphicsEllipseItem = _DummyClass()
    QGraphicsItem = _DummyClass()
    QGraphicsLineItem = _DummyClass()
    QGraphicsPathItem = _DummyClass()
    QGraphicsRectItem = _DummyClass()
    QGraphicsScene = _DummyClass()
    QGraphicsSimpleTextItem = _DummyClass()
    QGraphicsTextItem = _DummyClass()
    QGraphicsView = _DummyClass()
    QGroupBox = _DummyClass()
    QHBoxLayout = _DummyClass()
    QInputDialog = _DummyClass()
    QLabel = _DummyClass()
    QLineEdit = _DummyClass()
    QListWidget = _DummyClass()
    QListWidgetItem = _DummyClass()
    QMainWindow = _DummyClass()
    QMenu = _DummyClass()
    QMessageBox = _DummyClass()
    QPlainTextEdit = _DummyClass()
    QPushButton = _DummyClass()
    QScrollArea = _DummyClass()
    QShortcut = _DummyClass()
    QSpinBox = _DummyClass()
    QSplitter = _DummyClass()
    QStackedWidget = _DummyClass()
    QTabBar = _DummyClass()
    QTabWidget = _DummyClass()
    QTableWidget = _DummyClass()
    QTableWidgetItem = _DummyClass()
    QTextEdit = _DummyClass()
    QToolBox = _DummyClass()
    QToolBar = _DummyClass()
    QVBoxLayout = _DummyClass()
    QWidget = _DummyClass()
    
    QBrush = _DummyClass()
    QColor = _DummyClass()
    QDrag = _DummyClass()
    QFont = _DummyClass()
    QFontMetrics = _DummyClass()
    QKeySequence = _DummyClass()
    QPen = _DummyClass()
    QPainter = _DummyClass()
    QPainterPath = _DummyClass()
    QLinearGradient = _DummyClass()
    QPixmap = _DummyClass()
    QIcon = _DummyClass()
    
    Qt = _DummyClass()
    QTimer = _DummyClass()
    QRectF = _DummyClass()
    QPointF = _DummyClass()
    QSizeF = _DummyClass()
    QMimeData = _DummyClass()
    QAbstractAnimation = _DummyClass()
    
    ItemDataRole = 0
    WindowType = _DummyClass()
    Orientation = _DummyClass()
    ScrollBarPolicy = _DummyClass()
    DockWidgetArea = _DummyClass()
    DockWidgetFeature = _DummyClass()
    TabPosition = _DummyClass()
    
    def get_standard_button(button):
        return 0


def is_qt_available() -> bool:
    """Check if Qt is available."""
    return QT_LIB != "missing"


def get_qt_lib() -> str:
    """Get the detected Qt library name."""
    return QT_LIB
