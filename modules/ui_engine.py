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

from xml.etree import ElementTree as ET
from typing import Any, Callable
import inspect

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
    QLayout, QSizePolicy,
)
from PySide6.QtCore import Qt, QSize


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
        """Читает XML из файла и вызывает build()."""
        with open(path, encoding="utf-8") as fh:
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
