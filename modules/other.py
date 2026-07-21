import random,hashlib
import os,sys
from PySide6.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout,
    QHBoxLayout, QGraphicsOpacityEffect, QLabel, QGraphicsBlurEffect,QComboBox,QFrame,QStyleOptionViewItem,QListView,QStyledItemDelegate, QStyle,QMenu, QStyleOption
)
from PySide6.QtGui import QColor,QPixmap, QPainter, QLinearGradient, QImage,QPalette, QPen, QBrush,QAction
from PySide6.QtCore import QPropertyAnimation, QRect, QEasingCurve, Qt, Signal,QObject, QProcess,QParallelAnimationGroup,QSize
import __main__ 
import re
import subprocess
import shutil
import json

class GradientImageLabel(QLabel):
    """Супер пупер навороченое отображение картинки, спиженный с моего Minecraft лаунчера"""
    def __init__(self, parent=None,gradient:list = [],blur_effect:int = 0):
        super().__init__(parent)
        self.original_pixmap = QPixmap()
        # ОТКЛЮЧАЕМ стандартное искажающее растягивание Qt
        self.setScaledContents(False) 

        self.blur_effect = QGraphicsBlurEffect()
        self.blur_effect.setBlurRadius(blur_effect)
        self.setGraphicsEffect(self.blur_effect)
        self.gradient=gradient
        
    def set_new_image(self, image_source):
        """Динамически принимает путь к файлу (str) или готовый QPixmap"""
        if isinstance(image_source, QPixmap):
            self.original_pixmap = image_source
        else:
            self.original_pixmap = QPixmap(str(image_source))
            
        self.update_gradient_mask()

    def update_gradient_mask(self):
        if self.original_pixmap.isNull():
            return

        # Получаем текущие размеры самого виджета QLabel
        target_width = self.width()
        target_height = self.height()
        
        if target_width <= 0 or target_height <= 0:
            return

        # 1. Конвертируем оригинал в QImage с поддержкой Альфа-канала
        src_image = self.original_pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        
        # 2. РАСЧЕТ КАДРИРОВАНИЯ И ЦЕНТРИРОВАНИЯ (Аналог object-fit: cover)
        src_width = src_image.width()
        src_height = src_image.height()
        
        # Вычисляем коэффициенты масштабирования
        scale_w = target_width / src_width
        scale_h = target_height / src_height
        scale = max(scale_w, scale_h) # Берем максимальный, чтобы залить всю площадь
        
        # Размеры картинки после пропорционального масштабирования
        new_w = int(src_width * scale)
        new_h = int(src_height * scale)
        
        # Масштабируем исходное изображение сглаженным алгоритмом
        scaled_image = src_image.scaled(new_w, new_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        
        # Находим координаты для вырезания центральной части (центрирование)
        crop_x = (new_w - target_width) // 2
        crop_y = (new_h - target_height) // 2
        
        # Вырезаем кадр точно под размер QLabel
        cropped_image = scaled_image.copy(QRect(crop_x, crop_y, target_width, target_height))

        # 3. НАЛОЖЕНИЕ ГРАДИЕНТА ПРОЗРАЧНОСТИ
        # Создаем пустой холст строго под размер QLabel и заливаем прозрачностью
        result_image = QImage(target_width, target_height, QImage.Format.Format_ARGB32_Premultiplied)
        result_image.fill(QColor(0, 0, 0, 0)) 
        
        painter = QPainter(result_image)
        # Рисуем уже отцентрированный и обрезанный кадр
        painter.drawImage(0, 0, cropped_image)
        
        # Применяем маску прозрачности
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        
        # Линейный градиент сверху вниз по размеру виджета
        gradient = QLinearGradient(0, 0, 0, target_height)
        for x in self.gradient:
            gradient.setColorAt(x[0], x[1]) 
        
        painter.fillRect(result_image.rect(), gradient)
        painter.end()
        
        # Выводим в QLabel
        self.setPixmap(QPixmap.fromImage(result_image))

    def resizeEvent(self, event):
        """При ресайзе картинка автоматически перекадрируется и центрируется заново"""
        super().resizeEvent(event)
        self.update_gradient_mask()



def get_ffmpeg_executable() -> str:
    if (sys.platform == "win32"):
        if "__compiled__" in globals():
            app_path = os.path.dirname(os.path.abspath(sys.argv[0]))
        else:
            app_path = os.path.dirname(os.path.abspath(sys.modules['__main__'].__file__))

        print(os.path.join(app_path,"external","ffmpeg","ffmpeg.exe"))
        return os.path.join(app_path,"external","ffmpeg","ffmpeg.exe")

    candidates = [
        os.environ.get("FFMPEG_PATH", "").strip(),
        os.environ.get("FFMPEG_BIN", "").strip(),
        shutil.which("ffmpeg") or "",
        shutil.which("ffmpeg.exe") or "",
    ]
    script_dir = os.path.dirname(os.path.abspath(sys.modules['__main__'].__file__))
    candidates.extend(
        [
            os.path.join(script_dir, "ffmpeg"),
            os.path.join(script_dir, "ffmpeg.exe"),
        ]
    )

    for candidate in candidates:
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    return None


class NoFocusDelegate(QStyledItemDelegate):
    """Я ненавижу WINDOWS, исправление отображения QComboBox"""
    def paint(self, painter, option, index):

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.state &= ~QStyle.State_HasFocus  # убираем флаг фокуса

        painter.save()
        

        rect = opt.rect
        painter.setPen(Qt.NoPen)
        
        if opt.state & QStyle.State_Selected:
            painter.setBrush(QColor("#3a3a3a"))
        elif opt.state & QStyle.State_MouseOver:
            painter.setBrush(QColor("#2d2d2d"))
        else:
            painter.setBrush(QColor("#1e1e1e"))
        
        painter.drawRect(rect)
        
        # Рисуем текст
        text = index.data(Qt.DisplayRole)
        if text:
            # Настройка шрифта и цвета
            painter.setPen(QColor("white"))
            font = painter.font()
            font.setPointSize(10)  # можно настроить
            painter.setFont(font)
            # Отступы слева, как в стандартном стиле
            text_rect = QRect(rect.left() + 10, rect.top(), rect.width() - 20, rect.height())
            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, text)
        
        painter.restore()
    
    def sizeHint(self, option, index):
        return QSize(0, 30)

class FixedComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_view()
    
    def _setup_view(self):
        view = QListView()
        view.setFrameShape(QFrame.NoFrame)
        view.setSpacing(0)
        view.setContentsMargins(0, 0, 0, 0)
        view.setViewportMargins(0, 0, 0, 0)
        view.setAttribute(Qt.WA_MacShowFocusRect, False)
        view.setFocusPolicy(Qt.NoFocus)  # чтобы сам view не получал фокус
        
        # Устанавливаем делегат, который перерисовывает всё
        delegate = NoFocusDelegate(view)
        view.setItemDelegate(delegate)
        
        # Стиль для view задаёт только фон самого списка (если делегат не перекроет)
        view.setStyleSheet("""
            QListView {
                background-color: #1e1e1e;
                border: none;
                padding: 0px;
                margin: 0px;
            }
        """)
        self.setView(view)
    
    def showPopup(self):
        super().showPopup()
        popup = self.view().parentWidget()
        if popup:
            popup.setContentsMargins(0, 0, 0, 0)
            popup.setStyleSheet("background: #1e1e1e; border: none; outline: none;")


class SystemMenuBar(QWidget):
    
    def __init__(self, parent=None, bg_color="rgba(40, 40, 40, 255)"):
        super().__init__(parent)
        self.setObjectName("MainMenuBar")
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(10, 0, 10, 0)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.menus = {}

        self.setStyleSheet(f"""
            QWidget#MainMenuBar {{
                background-color: rgba(0, 0, 0, 50); 
            }}
            QWidget#MainMenuBar QPushButton {{
                background-color: transparent;
                color: white;
                font-family: 'Segoe UI', Arial;
                font-size: 13px;
                padding: 0px 6px;
                border: none;
                border-radius: 0px;
            }}
            QWidget#MainMenuBar QPushButton:hover {{
                background-color: rgba(255, 255, 255, 40);
            }}
            QWidget#MainMenuBar QPushButton::menu-indicator {{
                image: none; 
            }}
        """)

    def add_menu(self, title: str) -> QMenu:
        btn = QPushButton(title, self)
        menu = QMenu(self)
        btn.setMenu(menu)
        
        self.layout.addWidget(btn)
        self.menus[title] = menu
        return menu

    def _ensure_visible_chain(self, menu: QMenu):
        if menu is None:
            return
        
        if menu.menuAction():
            menu.menuAction().setVisible(True)
            
        parent = menu.parent()
        if isinstance(parent, QMenu):
            self._ensure_visible_chain(parent)

    def add_action(self, target_menu: QMenu | str, action_text: str, trigger_slot=None) -> QAction:
        if isinstance(target_menu, str):
            if target_menu not in self.menus:
                self.add_menu(target_menu)
            parent_menu = self.menus[target_menu]
        else:
            parent_menu = target_menu
            
        action = QAction(action_text, self)
        if trigger_slot:
            action.triggered.connect(trigger_slot)
            
        parent_menu.addAction(action)
        self._ensure_visible_chain(parent_menu)
            
        return action

    def add_submenu(self, parent_menu: QMenu | str, title: str, hide_if_empty: bool = True) -> QMenu:
        if isinstance(parent_menu, str):
            if parent_menu not in self.menus:
                self.add_menu(parent_menu)
            parent_menu = self.menus[parent_menu]
            
        submenu = QMenu(title, parent_menu) 
        
        parent_menu.addMenu(submenu)

        if hide_if_empty:
            submenu.menuAction().setVisible(False)

        self._ensure_visible_chain(parent_menu)
            
        return submenu


    def paintEvent(self, event):
        opt = QStyleOption()
        opt.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt, p, self)
        super().paintEvent(event)



def LocalSaveDir():
    if (sys.platform == "linux"):
        os.makedirs(os.path.join(os.path.expanduser('~'),".config","MSMP-Stream","6.0"), exist_ok=True)
        return os.path.join(os.path.expanduser('~'),".config","MSMP-Stream","6.0")
    elif (sys.platform == "win32"):
        if "__compiled__" in globals(): # I'm too lazy to support Windows for now.
            return os.path.dirname(os.path.abspath(sys.argv[0]))
        else:
            return os.path.dirname(os.path.abspath(sys.modules['__main__'].__file__))



def LoadConfigYaml():
    with open("config.yaml", "r", encoding="utf-8") as f:
        try:
            data = yaml.safe_load(f)
            print(data)
        
        except yaml.YAMLError as exc:
            print(f"Ошибка чтения файла: {exc}") 

#....
