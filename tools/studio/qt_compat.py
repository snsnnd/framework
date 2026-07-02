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
        QGraphicsDropShadowEffect,
        QGraphicsObject,
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
        QGraphicsDropShadowEffect,
        QGraphicsObject,
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
    # No Qt available - provide dummy classes that can be inherited
    QT_LIB = "missing"
    
    class _DummyBase:
        """Base class for dummy Qt classes when Qt is not available."""
        def __init__(self, *args, **kwargs):
            pass
        def __call__(self, *args, **kwargs):
            return self
        def __getattr__(self, name):
            # Return a callable that returns itself for method chains
            attr = _DummyBase()
            return attr
    
    def _make_dummy(name):
        """Create a dummy class with the given name."""
        return type(name, (_DummyBase,), {})
    
    # Create all dummy classes uniformly
    QApplication = _make_dummy('QApplication')
    QCheckBox = _make_dummy('QCheckBox')
    QComboBox = _make_dummy('QComboBox')
    QDialog = _make_dummy('QDialog')
    QDialogButtonBox = _make_dummy('QDialogButtonBox')
    QDockWidget = _make_dummy('QDockWidget')
    QDoubleSpinBox = _make_dummy('QDoubleSpinBox')
    QFileDialog = _make_dummy('QFileDialog')
    QFormLayout = _make_dummy('QFormLayout')
    QGraphicsDropShadowEffect = _make_dummy('QGraphicsDropShadowEffect')
    QGraphicsEllipseItem = _make_dummy('QGraphicsEllipseItem')
    QGraphicsItem = _make_dummy('QGraphicsItem')
    QGraphicsLineItem = _make_dummy('QGraphicsLineItem')
    QGraphicsObject = _make_dummy('QGraphicsObject')
    QGraphicsPathItem = _make_dummy('QGraphicsPathItem')
    QGraphicsRectItem = _make_dummy('QGraphicsRectItem')
    QGraphicsScene = _make_dummy('QGraphicsScene')
    QGraphicsSimpleTextItem = _make_dummy('QGraphicsSimpleTextItem')
    QGraphicsTextItem = _make_dummy('QGraphicsTextItem')
    QGraphicsView = _make_dummy('QGraphicsView')
    QGroupBox = _make_dummy('QGroupBox')
    QHBoxLayout = _make_dummy('QHBoxLayout')
    QInputDialog = _make_dummy('QInputDialog')
    QLabel = _make_dummy('QLabel')
    QLineEdit = _make_dummy('QLineEdit')
    QListWidget = _make_dummy('QListWidget')
    QListWidgetItem = _make_dummy('QListWidgetItem')
    QMainWindow = _make_dummy('QMainWindow')
    QMenu = _make_dummy('QMenu')
    QMessageBox = _make_dummy('QMessageBox')
    QPlainTextEdit = _make_dummy('QPlainTextEdit')
    QPushButton = _make_dummy('QPushButton')
    QScrollArea = _make_dummy('QScrollArea')
    QShortcut = _make_dummy('QShortcut')
    QSpinBox = _make_dummy('QSpinBox')
    QSplitter = _make_dummy('QSplitter')
    QStackedWidget = _make_dummy('QStackedWidget')
    QTabBar = _make_dummy('QTabBar')
    QTabWidget = _make_dummy('QTabWidget')
    QTableWidget = _make_dummy('QTableWidget')
    QTableWidgetItem = _make_dummy('QTableWidgetItem')
    QTextEdit = _make_dummy('QTextEdit')
    QToolBox = _make_dummy('QToolBox')
    QToolBar = _make_dummy('QToolBar')
    QVBoxLayout = _make_dummy('QVBoxLayout')
    QWidget = _make_dummy('QWidget')
    
    QBrush = _make_dummy('QBrush')
    QColor = _make_dummy('QColor')
    QDrag = _make_dummy('QDrag')
    QFont = _make_dummy('QFont')
    QFontMetrics = _make_dummy('QFontMetrics')
    QKeySequence = _make_dummy('QKeySequence')
    QPen = _make_dummy('QPen')
    QPainter = _make_dummy('QPainter')
    QPainterPath = _make_dummy('QPainterPath')
    QLinearGradient = _make_dummy('QLinearGradient')
    QPixmap = _make_dummy('QPixmap')
    QIcon = _make_dummy('QIcon')
    
    Qt = _make_dummy('Qt')
    QTimer = _make_dummy('QTimer')
    QRectF = _make_dummy('QRectF')
    QPointF = _make_dummy('QPointF')
    QSizeF = _make_dummy('QSizeF')
    QMimeData = _make_dummy('QMimeData')
    QAbstractAnimation = _make_dummy('QAbstractAnimation')
    
    ItemDataRole = 0
    WindowType = _make_dummy('WindowType')
    Orientation = _make_dummy('Orientation')
    ScrollBarPolicy = _make_dummy('ScrollBarPolicy')
    DockWidgetArea = _make_dummy('DockWidgetArea')
    DockWidgetFeature = _make_dummy('DockWidgetFeature')
    TabPosition = _make_dummy('TabPosition')
    
    def get_standard_button(button):
        return 0


def is_qt_available() -> bool:
    """Check if Qt is available."""
    return QT_LIB != "missing"


def get_qt_lib() -> str:
    """Get the detected Qt library name."""
    return QT_LIB
