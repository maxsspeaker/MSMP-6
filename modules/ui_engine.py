"""
ui_engine.py — XML-driven UI engine for PySide6
================================================

Поддерживает plug&play кастомные виджеты через реестр:

    UIEngine.register("gradientImageLabel", GradientImageLabel)
    UIEngine.register("waveformSeekBar", WaveformSeekBar)

или через декоратор:

    @UIEngine.widget("myWidget")
    class MyWidget(QWidget): ...

После регистрации тег используется в XML как обычный виджет:

    <gradientImageLabel id="cover" fixed-width="128" fixed-height="128" />
    <waveformSeekBar id="position_slider" />

Кастомный виджет также может принять атрибуты из XML через метод
`ui_init(attrs: dict)` — движок вызовет его сразу после создания:

    class MyWidget(QWidget):
        def ui_init(self, attrs: dict) -> None:
            if "color" in attrs:
                self.set_color(attrs["color"])

═══════════════════════════════════════════════════════════════════════════════

Поддерживаемые атрибуты:
    id              → setObjectName + engine.widgets["id"]
    widget_class    → setObjectName
    style           → setStyleSheet
    flex            → тип layout: "h"|"hbox"|"v"|"vbox"|"grid"|"form"
    connect         → имя слота контекста
    text            → текст (иначе из body тега)
    title           → setWindowTitle
    tooltip         → setToolTip
    enabled         → "true"/"false"
    visible         → "true"/"false"

    Размеры:
    min-width, min-height, max-width, max-height, fixed-width, fixed-height

    Layout (применяются к layout самого элемента):
    margin          → поля layout: одно число "8" или четыре "8,4,8,4" (л,т,п,н)
    spacing         → отступ между дочерними элементами layout

    Позиция в родительском layout (читаются родителем):
    stretch         → коэффициент растяжки в HBox/VBox
    row, col, rowspan, colspan  → позиция в QGridLayout
    form-label      → метка строки в QFormLayout

    Виджет-специфичные:
    placeholder     → setPlaceholderText
    checkable       → "true"/"false"
    checked         → "true"/"false"
    orientation     → "h"/"v" для QSlider, QProgressBar
    min, max, value → для QSlider, QSpinBox и т.д.
    items           → "a,b,c" для QComboBox
"""

from __future__ import annotations

import os,re,sys
from xml.etree import ElementTree as ET
from typing import Any, Callable
import inspect
import math

from PySide6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QDialog,
    QLabel, QPushButton, QLineEdit, QTextEdit, QPlainTextEdit,
    QComboBox, QCheckBox, QRadioButton, QSpinBox, QDoubleSpinBox,
    QSlider, QProgressBar, QTabWidget, QScrollArea, QSplitter,
    QFrame, QGroupBox, QListWidget, QTreeWidget, QTableWidget,
    QDockWidget, QStackedWidget, QLCDNumber, QCalendarWidget,
    QDateTimeEdit, QDateEdit, QTimeEdit, QFontComboBox, QDial,
    QToolButton, QCommandLinkButton, QKeySequenceEdit,
    QHBoxLayout, QVBoxLayout, QGridLayout, QFormLayout,
    QLayout, QSizePolicy,QStyle,QHeaderView,
    QScroller, 
    QScrollerProperties,
    QAbstractItemView,
    QToolTip
)
from PySide6.QtCore import Qt, QSize,QTimer,Signal,QEasingCurve
from PySide6.QtGui import QIcon,QBrush, QColor, QLinearGradient, QPainter, QPixmap,QAction

from modules.AboutWindow import AboutWindow

WAVEFORM_BIN_COUNT = 440
WAVEFORM_BACKGROUND_COLOR = "#00000000"
WAVEFORM_TRACK_COLOR = "#232323"
WAVEFORM_BUFFER_COLOR = "#7c7c7c"
WAVEFORM_PLAYED_COLOR = "#e8e8e8"
WAVEFORM_HANDLE_COLOR = "#f2f2f2"
WAVEFORM_HEIGHT = 44



# ─────────────────────────────────────────────────────────────────────────────
# Встроенная карта стандартных виджетов PySide6
# ─────────────────────────────────────────────────────────────────────────────
_BUILTIN_WIDGET_MAP: dict[str, type] = {
    "qwidget":            QWidget,
    "qmainwindow":        QMainWindow,
    "qdialog":            QDialog,
    "qlabel":             QLabel,
    "qpushbutton":        QPushButton,
    "qlineedit":          QLineEdit,
    "qtextedit":          QTextEdit,
    "qplaintextedit":     QPlainTextEdit,
    "qcombobox":          QComboBox,
    "qcheckbox":          QCheckBox,
    "qradiobutton":       QRadioButton,
    "qspinbox":           QSpinBox,
    "qdoublespinbox":     QDoubleSpinBox,
    "qslider":            QSlider,
    "qprogressbar":       QProgressBar,
    "qtabwidget":         QTabWidget,
    "qscrollarea":        QScrollArea,
    "qsplitter":          QSplitter,
    "qframe":             QFrame,
    "qgroupbox":          QGroupBox,
    "qlistwidget":        QListWidget,
    "qtreewidget":        QTreeWidget,
    "qtablewidget":       QTableWidget,
    "qdockwidget":        QDockWidget,
    "qstackedwidget":     QStackedWidget,
    "qlcdnumber":         QLCDNumber,
    "qcalendarwidget":    QCalendarWidget,
    "qdatetimeedit":      QDateTimeEdit,
    "qdateedit":          QDateEdit,
    "qtimeedit":          QTimeEdit,
    "qfontcombobox":      QFontComboBox,
    "qdial":              QDial,
    "qtoolbutton":        QToolButton,
    "qcommandlinkbutton": QCommandLinkButton,
    "qkeysequenceedit":   QKeySequenceEdit,
}

# Карта flex-значений → фабрики layout
_LAYOUT_MAP: dict[str, Callable[[], QLayout]] = {
    "h":    QHBoxLayout,
    "hbox": QHBoxLayout,
    "v":    QVBoxLayout,
    "vbox": QVBoxLayout,
    "grid": QGridLayout,
    "form": QFormLayout,
}

_ALIGNMENT_MAP: dict[str, Callable[[], QLayout]] = {
    "AlignLeft":     Qt.AlignmentFlag.AlignLeft,
    "AlignRight":    Qt.AlignmentFlag.AlignRight,
    "AlignHCenter":  Qt.AlignmentFlag.AlignHCenter ,
    "AlignJustify":  Qt.AlignmentFlag.AlignJustify,

    "AlignTop":      Qt.AlignmentFlag.AlignTop,
    "AlignBottom":   Qt.AlignmentFlag.AlignBottom ,
    "AlignVCenter":  Qt.AlignmentFlag.AlignVCenter,
    "AlignBaseline": Qt.AlignmentFlag.AlignBaseline ,

    "AlignCenter":   Qt.AlignmentFlag.AlignCenter
}

# Сентинель: «атрибут не указан в XML»
_MISSING = object()


def _bool(val: str) -> bool:
    return val.strip().lower() in ("true", "1", "yes")


def _resolve_slot(name: str, context: Any) -> Callable | None:
    if context is None:
        return None
    obj = context
    for part in name.strip().split("."):
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj if callable(obj) else None


def _parse_margin(raw: str) -> tuple[int, int, int, int]:
    """
    Разбирает значение атрибута margin.

    Форматы:
        "8"          → (8, 8, 8, 8)          — все стороны
        "8,4"        → (8, 4, 8, 4)          — горизонталь, вертикаль
        "8,4,8,4"   → (8, 4, 8, 4)          — left, top, right, bottom
    """
    parts = [p.strip() for p in raw.split(",")]
    try:
        if len(parts) == 1:
            v = int(parts[0])
            return (v, v, v, v)
        if len(parts) == 2:
            h, v = int(parts[0]), int(parts[1])
            return (h, v, h, v)
        if len(parts) >= 4:
            return (int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))
    except ValueError:
        pass
    return (0, 0, 0, 0)


# ─────────────────────────────────────────────────────────────────────────────
# Глобальный реестр кастомных виджетов
# ─────────────────────────────────────────────────────────────────────────────
_CUSTOM_WIDGET_REGISTRY: dict[str, type] = {}


class UIEngine:
    """
    Движок XML → PySide6 виджеты.

    Plug&play кастомные виджеты:
        UIEngine.register("waveformSeekBar", WaveformSeekBar)

        @UIEngine.widget("myWidget")
        class MyWidget(QWidget): ...

        class MyWidget(QWidget):
            def ui_init(self, attrs: dict) -> None: ...

    Параметры конструктора:
        context         — объект для разрешения слотов connect=
        default_spacing — отступ между дочерними элементами (если не указан в XML)
        default_margin  — поля layout по умолчанию (int или 4-tuple),
                          используется когда атрибут margin не задан в теге
    """

    # ── Реестр ────────────────────────────────────────────────────────────────

    @staticmethod
    def register(tag: str, cls: type) -> None:
        """UIEngine.register("waveformSeekBar", WaveformSeekBar)"""
        _CUSTOM_WIDGET_REGISTRY[tag.lower()] = cls

    @staticmethod
    def widget(tag: str):
        """
        @UIEngine.widget("myWidget")
        class MyWidget(QWidget): ...
        """
        def decorator(cls: type) -> type:
            _CUSTOM_WIDGET_REGISTRY[tag.lower()] = cls
            return cls
        return decorator

    @staticmethod
    def _resolve_class(tag: str) -> tuple[type | None, bool]:
        key = tag.lower()
        if key in _CUSTOM_WIDGET_REGISTRY:
            return _CUSTOM_WIDGET_REGISTRY[key], False, True
        if key in _BUILTIN_WIDGET_MAP:
            return _BUILTIN_WIDGET_MAP[key], False, False
        return None, True , False  # неизвестный тег → именованный QWidget-контейнер

    # ── Конструктор ───────────────────────────────────────────────────────────

    def __init__(
        self,
        context: Any = None,
        default_spacing: int = 6,
        default_margin: int | tuple[int, int, int, int] = 8,
    ) -> None:
        self.context = context
        self.default_spacing = default_spacing
        self.default_margin: tuple[int, int, int, int] = (
            default_margin if isinstance(default_margin, tuple)
            else (default_margin,) * 4
        )
        self.widgets: dict[str, QWidget] = {}

    # ── Публичный API ─────────────────────────────────────────────────────────

    def build(self, xml: str) -> QWidget:
        """Разбирает XML-строку и возвращает корневой виджет."""
        try:
            root_el = ET.fromstring(xml.strip())
        except ET.ParseError as exc:
            raise ValueError(f"UIEngine: невалидный XML — {exc}") from exc
        element,nolayout=self._build_element(root_el, parent=None)
        return element

    def build_file(self, path: str) -> QWidget:
        """Читает index.xml из папки и вызывает build()."""
        self._skin_path=path

        with open(os.path.join(path, "index.xml"), encoding="utf-8") as fh:
            return self.build(fh.read())

    # ── Построение элемента ───────────────────────────────────────────────────

    def _custom_element_builder(self,cls,attrs,parent):
        custom_attrs = {}

        for attr,attrs_info in inspect.signature(cls).parameters.items():

            if attr in attrs:
                raw_value=attrs[attr]
                if attrs_info.annotation == inspect.Parameter.empty:
                    continue

                custom_attrs[attr]=attrs_info.annotation(raw_value)

        if(custom_attrs=={}):
            return cls(parent)

        return cls(parent,**custom_attrs)

    def _build_element(self, el: ET.Element, parent: QWidget | None) -> QWidget:
        tag   = el.tag
        attrs = el.attrib

        # 1. Создаём виджет ────────────────────────────────────────────────────
        cls, is_named_container,is_custom = self._resolve_class(tag)

        if is_named_container:
            widget = QWidget(parent)
        elif is_custom:
            widget = self._custom_element_builder(cls,attrs,parent)
        else:
            try:
                widget = cls(parent)
            except TypeError:
                widget = cls()
                if parent is not None:
                    widget.setParent(parent)

        # 2. Хук ui_init ───────────────────────────────────────────────────────
        if hasattr(widget, "ui_init") and callable(widget.ui_init):
            widget.ui_init(attrs)

        # 3. Реестр имён ───────────────────────────────────────────────────────
        widget_id = attrs.get("id", "").strip()
        if widget_id:
            widget.setObjectName(widget_id)
            self.widgets[widget_id] = widget

        widget_class = attrs.get("class", "").strip()
        if widget_class:
            widget.setObjectName(widget_class)

        if is_named_container:
            self.widgets.setdefault(tag, widget)

        if(attrs.get("nolayout", "")):
            nolayout = True
        else:
            nolayout = False

        # 4. StyleSheet ────────────────────────────────────────────────────────
        style = attrs.get("style", "").strip()
        if style:
            widget.setStyleSheet(style)

        # 5. Базовые свойства ──────────────────────────────────────────────────
        if "tooltip" in attrs:
            widget.setToolTip(attrs["tooltip"])
        if "enabled" in attrs:
            widget.setEnabled(_bool(attrs["enabled"]))
        if "visible" in attrs:
            widget.setVisible(_bool(attrs["visible"]))
        if "icon" in attrs:
            self._apply_icon(widget, attrs["icon"],self._skin_path)

        # 6. Размеры ───────────────────────────────────────────────────────────
        if "min-width" in attrs or "min-height" in attrs:
            widget.setMinimumSize(QSize(
                int(attrs.get("min-width",  0)),
                int(attrs.get("min-height", 0)),
            ))
        if "max-width" in attrs or "max-height" in attrs:
            widget.setMaximumSize(QSize(
                int(attrs.get("max-width",  16_777_215)),
                int(attrs.get("max-height", 16_777_215)),
            ))
        if "fixed-width"  in attrs:
            widget.setFixedWidth(int(attrs["fixed-width"]))
        if "fixed-height" in attrs:
            widget.setFixedHeight(int(attrs["fixed-height"]))

        # 7. Текст ─────────────────────────────────────────────────────────────
        inner_text = (attrs.get("text") or (el.text or "")).strip()
        self._apply_text(widget, inner_text)

        # 8. Виджет-специфичные атрибуты ───────────────────────────────────────
        self._apply_specifics(widget, attrs, inner_text)

        # 9. Layout ────────────────────────────────────────────────────────────
        flex = attrs.get("flex", "").strip().lower()
        Align = attrs.get("Align", "").strip()
        layout: QLayout | None = None

        if flex:
            layout = _LAYOUT_MAP.get(flex, QVBoxLayout)()

            # spacing: из атрибута тега или глобальный дефолт
            raw_spacing = attrs.get("spacing", "").strip()
            layout.setSpacing(
                int(raw_spacing) if raw_spacing.lstrip("-").isdigit()
                else self.default_spacing
            )

            # margin: из атрибута тега или глобальный дефолт
            raw_margin = attrs.get("margin", "").strip()
            if raw_margin:
                layout.setContentsMargins(*_parse_margin(raw_margin))
            else:
                layout.setContentsMargins(*self.default_margin)

            if Align:
                Align = _ALIGNMENT_MAP.get(Align, None)
                if Align:
                    layout.setAlignment(Align)


        # 10. Дочерние элементы ────────────────────────────────────────────────
        for child_el in el:
            child,nolayout = self._build_element(child_el, parent=widget)

            if layout is None:
                continue

            if isinstance(layout, QGridLayout):
                row     = int(child_el.attrib.get("row",     0))
                col     = int(child_el.attrib.get("col",     0))
                rowspan = int(child_el.attrib.get("rowspan", 1))
                colspan = int(child_el.attrib.get("colspan", 1))
                layout.addWidget(child, row, col, rowspan, colspan)
            elif isinstance(layout, QFormLayout):
                layout.addRow(child_el.attrib.get("form-label", ""), child)
            else:
                stretch = int(child_el.attrib.get("stretch", 0))
                if not(nolayout):
                    layout.addWidget(child, stretch)

        if layout is not None:
            widget.setLayout(layout)

        # 11. connect ──────────────────────────────────────────────────────────
        connect_name = attrs.get("connect", "").strip()
        if connect_name:
            self._apply_connect(widget, connect_name)

        return widget,nolayout

    # ── Вспомогательные методы ────────────────────────────────────────────────

    @staticmethod
    def _apply_text(widget: QWidget, text: str) -> None:
        if not text:
            return
        if hasattr(widget, "setText"):
            widget.setText(text)
        elif hasattr(widget, "setTitle"):
            widget.setTitle(text)

    @staticmethod
    def _apply_icon(widget: QWidget, icon: str, _skin_path: str) -> None:
        if not icon:
            return
        if hasattr(widget, "setIcon"):
            widget.setIcon(QIcon(icon.replace("{internal}", _skin_path, 1) if icon.startswith("{internal}") else icon))

    @staticmethod
    def _apply_specifics(widget: QWidget, attrs: dict, text: str) -> None:
        if "placeholder" in attrs and hasattr(widget, "setPlaceholderText"):
            widget.setPlaceholderText(attrs["placeholder"])
        if "checkable" in attrs and hasattr(widget, "setCheckable"):
            widget.setCheckable(_bool(attrs["checkable"]))
        if "checked" in attrs and hasattr(widget, "setChecked"):
            widget.setChecked(_bool(attrs["checked"]))
        if "title" in attrs and hasattr(widget, "setWindowTitle"):
            widget.setWindowTitle(attrs["title"])

        if isinstance(widget, QGroupBox) and text:
            widget.setTitle(text)

        if "orientation" in attrs and hasattr(widget, "setOrientation"):
            ori_str = attrs["orientation"].lower()
            widget.setOrientation(
                Qt.Orientation.Horizontal if ori_str == "h"
                else Qt.Orientation.Vertical
            )

        for setter, key in [
            ("setMinimum", "min"),
            ("setMaximum", "max"),
            ("setValue",   "value"),
        ]:
            if key in attrs and hasattr(widget, setter):
                try:
                    getattr(widget, setter)(int(attrs[key]))
                except (ValueError, TypeError):
                    pass

        if isinstance(widget, QComboBox) and "items" in attrs:
            widget.addItems([i.strip() for i in attrs["items"].split(",") if i.strip()])

    def _apply_connect(self, widget: QWidget, slot_name: str) -> None:
        slot = _resolve_slot(slot_name, self.context)
        if slot is None:
            print(f"[UIEngine] Предупреждение: слот '{slot_name}' не найден.")
            return

        for signal_name in (
            "clicked", "valueChanged", "textChanged",
            "currentIndexChanged", "stateChanged", "toggled",
            "returnPressed", "activated",
        ):
            sig = getattr(widget, signal_name, None)
            if sig is not None:
                sig.connect(slot)
                return

        print(
            f"[UIEngine] Предупреждение: не найден подходящий сигнал "
            f"для '{widget.__class__.__name__}'."
        )



class qJumpSlider(QSlider):
    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Вычисляем новое значение напрямую по координате клика
            if self.orientation() == Qt.Orientation.Horizontal:
                new_value = QStyle.sliderValueFromPosition(
                    self.minimum(), self.maximum(), 
                    event.position().toPoint().x(), self.width()
                )
            else:
                new_value = QStyle.sliderValueFromPosition(
                    self.minimum(), self.maximum(), 
                    event.position().toPoint().y(), self.height()
                )
            
            # Устанавливаем значение
            self.sliderPressed.emit()
            self.setValue(new_value)

            QTimer.singleShot(
                100,
                lambda:self.sliderReleased.emit(),
            )
            
            # ВАЖНО: передаем событие дальше базовому классу!
            # Это позволит Qt "подхватить" ползунок для плавного drag-and-drop
            super().mousePressEvent(event)
        else:
            super().mousePressEvent(event)

UIEngine.register("qjumpslider", qJumpSlider)



class WaveformSeekBar(QWidget):
    sliderPressed = Signal()
    sliderMoved = Signal(int)
    sliderReleased = Signal()
    valueChanged = Signal(int)

    def __init__(self,parent=None) -> None:
        super().__init__()
        self._minimum = 0
        self._maximum = 1
        self._value = 0
        self._waveform: list[float] = []
        self._buffered_ratio = 0.0
        self._dragging = False
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(WAVEFORM_HEIGHT)
        self.setObjectName("waveformSeekBar")
        self.parent=parent


    def setRange(self, minimum: int, maximum: int) -> None:
        self._minimum = int(minimum)
        self._maximum = max(self._minimum, int(maximum))
        self.setValue(self._value)

    def setValue(self, value: int) -> None:
        value = self._clamp(value)
        if value != self._value:
            self._value = value
            self.valueChanged.emit(self._value)
        self.update()

    def value(self) -> int:
        return self._value

    def set_waveform(self, waveform: list[float]) -> None:
        self._waveform = [min(1.0, max(0.0, float(level))) for level in waveform]
        self.update()

    def set_buffered_ratio(self, ratio: float) -> None:
        self._buffered_ratio = max(0.0, min(1.0, float(ratio)))
        self.update()

    def _clamp(self, value: int) -> int:
        return max(self._minimum, min(self._maximum, int(value)))

    def _value_from_x(self, x: float) -> int:
        if self._maximum <= self._minimum:
            return self._minimum

        usable = max(1.0, float(self.width() - 24))
        left = 12.0
        ratio = (float(x) - left) / usable
        ratio = max(0.0, min(1.0, ratio))
        return int(round(self._minimum + ratio * (self._maximum - self._minimum)))

    def _x_from_value(self, value: int) -> float:
        if self._maximum <= self._minimum:
            return 12.0
        usable = max(1.0, float(self.width() - 24))
        ratio = (self._clamp(value) - self._minimum) / float(self._maximum - self._minimum)
        return 12.0 + ratio * usable

    def _format_ms(self, ms: int) -> str:
        seconds = max(0, ms // 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    def _show_seek_tooltip(self, value: int, global_pos) -> None:
        QToolTip.showText(global_pos, self._format_ms(value), self)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self.sliderPressed.emit()
            value = self._value_from_x(event.position().x())
            self.setValue(value)
            self.sliderMoved.emit(value)
            self._show_seek_tooltip(value, event.globalPosition().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            value = self._value_from_x(event.position().x())
            self.setValue(value)
            self.sliderMoved.emit(value)
            self._show_seek_tooltip(value, event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging and event.button() == Qt.LeftButton:
            value = self._value_from_x(event.position().x())
            self.setValue(value)
            self.sliderMoved.emit(value)
            self._dragging = False
            self.sliderReleased.emit()
            QToolTip.hideText()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(WAVEFORM_BACKGROUND_COLOR))

        outer = self.rect().adjusted(2, 6, -2, -6)
        if outer.width() <= 0 or outer.height() <= 0:
            return

        painter.setPen(Qt.NoPen)
        #painter.setBrush(QColor("#141414"))
        #painter.drawRoundedRect(outer, 0, 0)

        inner = outer.adjusted(10, 3, -10, -3)
        if inner.width() <= 0 or inner.height() <= 0:
            return

        center_y = inner.center().y()
        half_height = max(1.0, inner.height() / 2.0)
        waveform = self._waveform

        if waveform:
            bin_count = len(waveform)
            if bin_count <= 0:
                waveform = []
            else:
                bin_width = max(1.0, inner.width() / float(bin_count))
                played_index = 0
                if self._maximum > self._minimum:
                    ratio = (self._value - self._minimum) / float(self._maximum - self._minimum)
                    played_index = int(ratio * bin_count)
                    if played_index >= bin_count:
                        played_index = bin_count - 1
                buffered_index = int(max(0, bin_count - 1) * self._buffered_ratio)

                for i, level in enumerate(waveform):
                    x = inner.left() + i * bin_width
                    bar_h = max(1.0, level * half_height)
                    if i <= played_index:
                        color = QColor(WAVEFORM_PLAYED_COLOR)
                    elif i <= buffered_index:
                        color = QColor(WAVEFORM_BUFFER_COLOR)
                    else:
                        color = QColor(WAVEFORM_TRACK_COLOR)
                    painter.setBrush(color)
                    painter.drawRect(int(x), int(center_y - bar_h), max(1, int(math.ceil(bin_width))), int(bar_h * 2))
        else:
            painter.setBrush(QColor(WAVEFORM_TRACK_COLOR))
            painter.drawRect(inner)

            buffered_width = int(round(inner.width() * self._buffered_ratio))
            if buffered_width > 0:
                buffered_rect = inner.__class__(inner.left(), inner.top(), buffered_width, inner.height())
                painter.setBrush(QColor(WAVEFORM_BUFFER_COLOR))
                painter.drawRect(buffered_rect)

        if self._maximum > self._minimum:
            handle_x = self._x_from_value(self._value)
            painter.setBrush(QColor(WAVEFORM_HANDLE_COLOR))
            painter.drawRect(int(handle_x) - 1, inner.top() - 3, 2, inner.height() + 6)

UIEngine.register("waveformSeekBar",  WaveformSeekBar)

class SkinManager(QMainWindow):

    def _init_ui(self):
        _ui_xml_path = os.path.join(os.path.dirname(sys.modules['__main__'].__file__), f"skins/{self.config["skin"]}")

        self._engine = UIEngine(context=self, default_spacing=0, default_margin=0)
        container = self._engine.build_file(_ui_xml_path)

        # Удобный алиас: self.ui["widget_id"]
        self.ui = self._engine.widgets

        # ── Ссылки на виджеты (совместимость с остальным кодом) ───────────
        self.NowDisplay          = self.ui["NowDisplay"]
        self.position_slider     = self.ui["position_slider"]
        self.volume_slider       = self.ui["volume_slider"]
        self.status_label        = self.ui["status_label"]
        self.url_input           = self.ui["url_input"]
        #self.add_button          = self.ui["add_button"]
        self.cookie_browser      = self.ui["cookie_browser"]
        #self.clear_button        = self.ui["clear_button"]
        #self.save_button         = self.ui["save_button"]
        #self.load_button         = self.ui["load_button"]
        #self.play_button         = self.ui["play_button"]
        #self.pause_button        = self.ui["pause_button"]
        #self.stop_button         = self.ui["stop_button"]
        #self.prev_button         = self.ui["prev_button"]
        #self.next_button         = self.ui["next_button"]
        #self.restart_button      = self.ui["restart_button"]
        self.mode_button         = self.ui["mode_button"]
        self.playlistBox         = self.ui["playlistBox"]
        self.MainMenuBar         = self.ui["MainMenuBar"]

        if not(self.ui.get("playlist_table")): 
            self.table = self.ui["table"] #!!! legacy БУДЕТ УБРАНО В 6.0.4 исправьте кастомные скины!!!
        else:
            self.table = self.ui["playlist_table"]


        file_menu = self.MainMenuBar.add_menu("Menu")
        file_menu.addAction("About",lambda:AboutWindow(self).exec())

        setup_menu=self.MainMenuBar.add_menu("Options")
        skin_menu=self.MainMenuBar.add_submenu(setup_menu, "Skins", hide_if_empty=False)

        for skin in sorted(os.listdir(os.path.join(os.path.dirname(sys.modules['__main__'].__file__), "skins"))):
           skin_menu.addAction(skin, lambda s=skin: self.set_skin(s)) 

        if not hasattr(self, "PluginMenu"):
            self.PluginMenu=self.MainMenuBar.add_submenu(setup_menu, "Plugins")
            self.PluginMenu.setParent(self, self.PluginMenu.windowFlags())

            self.PlguinMenu=self.PluginMenu #!!! legacy БУДЕТ УБРАНО В 6.0.4 исправьте кастомные скины!!!
        else:
            setup_menu.addMenu(self.PluginMenu)

        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)
        file_menu.addSeparator()

        self.visualizer_window = self.ui.get("visualizer_window")

        if(self.visualizer_window):
            self.visualizer_window.raise_()
            self.visualizer_window.activateWindow()

            self.audio_buffer_output.audioBufferReceived.connect(self.on_audio_buffer_received)

            self.visualizer_window.show()

        cover_background = self.ui.get("cover_background")

        if (cover_background):
            cover_background.gradient = [(0.95, QColor(0, 0, 0, 0)), (0.6, QColor(0, 0, 0, 128))]
            cover_background.setAlignment(Qt.AlignCenter)
            cover_background.setScaledContents(True)
            cover_background.lower()

            QTimer.singleShot(
                10,
                lambda: cover_background.setGeometry(cover_background.parentWidget().rect()),
            )
            

        self.set_metaData(
            time_possition="0:00",
            time_end="0:00",
            track_title="",
            artist="",
            album=""
            )
        self.set_cover_placeholder()


        self.mode_button.setIcon(QIcon(self.PLAY_MODES_icons[self.play_mode_index]))

        # ── Донастройка cookie_browser (userData для элементов) ───────────
        cookie_data = ["", "firefox", "chrome", "chromium", "brave", "edge"]
        for i, data in enumerate(cookie_data):
            self.cookie_browser.setItemData(i, data)
        self.cookie_browser.setCurrentIndex(self.config["cookies"]["selected"])
        self.cookie_browser.currentIndexChanged.connect(self.change_cookie_browser)

        # ── Дополнительный connect для url_input (returnPressed) ──────────
        self.url_input.returnPressed.connect(self.add_url)

        # ── Донастройка volume_slider ─────────────────────────────────────
        self.volume_slider.valueChanged.connect(
            lambda value: self.audio_output.setVolume(value / 100)
        )

        # ── Донастройка seek bar ──────────────────────────────────────────

        if isinstance(self.position_slider, WaveformSeekBar):
            self.position_slider.set_buffered_ratio(0.0)
        self.position_slider.setRange(0, 0)

        self.position_slider.sliderPressed.connect(self.on_seek_start)
        self.position_slider.sliderReleased.connect(self.on_seek_end)
        self.position_slider.sliderMoved.connect(self.on_seek_preview)

        # ── Донастройка таблицы ───────────────────────────────────────────
        self.table.playlist = self.playlist
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Track", "Length"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().hide()
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.cellDoubleClicked.connect(lambda row, _col: self.play_index(row))
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_playlist_menu)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.verticalScrollBar().setSingleStep(1)
        self.table.viewport().installEventFilter(self)
        QScroller.grabGesture(self.table.viewport(), QScroller.LeftMouseButtonGesture)

        scroller = QScroller.scroller(self.table.viewport())
        props = QScrollerProperties()
        props.setScrollMetric(QScrollerProperties.DragStartDistance, 0.004)
        props.setScrollMetric(QScrollerProperties.DragVelocitySmoothingFactor, 0.6) # Сделали чуть отзывчивее
        props.setScrollMetric(QScrollerProperties.ScrollingCurve, QEasingCurve(QEasingCurve.OutCubic))
        scroller.setScrollerProperties(props)

        # ── Политика размера playlistBox ──────────────────────────────────
        self.playlistBox.setMinimumHeight(0)
        sp = self.playlistBox.sizePolicy()
        sp.setVerticalPolicy(QSizePolicy.Policy.Ignored)
        self.playlistBox.setSizePolicy(sp)


        self.setCentralWidget(container)

        self.apply_style()

        try:
            self.player.bufferProgressChanged.connect(self.on_buffer_progress_changed)
        except AttributeError:
            pass

    def set_cover_placeholder(self) -> None:
        cover_label = self.ui.get("cover_label")
        cover_background = self.ui.get("cover_background")
        if (cover_background):
            cover_background.set_new_image(QPixmap("resources/MSMPwaveBg.png"))
        if(cover_label):
            cover_label.set_new_image(QPixmap("resources/MSMPwave.png"))


    def set_metaData(self,time_possition=None,time_end=None,track_title=None,artist=None,album=None):
        if(time_possition and time_end):
            time_label=self.ui.get("time_label")
            time_possition_label=self.ui.get("time_possition_label")
            time_end_label=self.ui.get("time_end_label")
            if(time_label):
                time_label.setText(f"{time_possition} / {time_end}")
            if(time_possition_label):
                time_possition_label.setText(f"{time_possition}")
            if(time_end_label):
                time_end_label.setText(f"{time_end}")


        if(track_title):
            track_title_label=self.ui.get("track_title_label")
            if(track_title_label):
                track_title_label.setText(track_title)
        if(artist):
            artist_label=self.ui.get("artist_label")
            if(artist_label):
                artist_label.setText(artist)
        if(album):
            album_label=self.ui.get("album_label")
            if(album_label):
                album_label.setText(album)

    def apply_style(self) -> None:
        with open(os.path.join(os.path.dirname(sys.modules['__main__'].__file__), f"skins/{self.config["skin"]}/style.css")) as f:
            self.setStyleSheet(f.read())

    def set_skin(self,skin):
        print(skin)
        self.config["skin"]=skin

        self._reload_skin()


    def _reload_skin(self):
        current_index=self.table.current_index

        if(self.visualizer_window):
            self.audio_buffer_output.audioBufferReceived.disconnect(self.on_audio_buffer_received)

        self._init_ui() 
        self.refresh_table()
        self.table.current_index=current_index
        if current_index is not None:
            self.update_current_metadata(self.playlist[self.table.current_index])
            self.table.apply_row_style(current_index)

            if isinstance(self.ui.get("position_slider"), WaveformSeekBar):
                if not self.playlist[self.table.current_index].waveform == []:
                    self.position_slider.set_waveform(self.playlist[self.table.current_index].waveform)
                else:
                    self.request_waveform_generation(self.table.current_index)
            self.position_slider.setRange(0, max(0, self.player.duration()))
            self.update_buffer_progress(0.0)
            
        self.events.on_skin_changed.emit(self.config["skin"])

