import random,hashlib
import os,sys
from PySide6.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout,QTableWidget, QProgressBar,
    QHBoxLayout, QGraphicsOpacityEffect, QLabel, QGraphicsBlurEffect,QComboBox,QFrame,QStyleOptionViewItem,QListView,QStyledItemDelegate, QStyle,QMenu, QStyleOption,QTableWidgetItem,QAbstractItemView
)
from PySide6.QtGui import QColor,QPixmap, QPainter, QLinearGradient, QImage,QPalette, QPen, QBrush,QAction,QFont,QPalette
from PySide6.QtCore import QPropertyAnimation, QRect, QEasingCurve, Qt, Signal,QObject, QProcess,QParallelAnimationGroup,QSize, Slot,QPersistentModelIndex,Property
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer,QAudioBufferOutput
from modules.types import PlaylistItem
import __main__ 
import re
import subprocess
import shutil
import json,yaml

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


class AudioController():

    def _init_player(self):

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_buffer_output = QAudioBufferOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setAudioBufferOutput(self.audio_buffer_output)
        self.audio_output.setVolume(0.8)

        self.media_devices = QMediaDevices()

        self.media_devices.audioOutputsChanged.connect(self._update_to_default_device)

        self._update_to_default_device()

    def _update_to_default_device(self):
        default_device = QMediaDevices.defaultAudioOutput()
        self.audio_output.setDevice(default_device)
        print(f"Устройство вывода установлено на: {default_device.description()}")


class SkinManager():

    def set_skin(self,skin):
        print(skin)
        self.config["skin"]=skin

class LoadingOverlay(QWidget):
    """Виджет-оверлей, который будет накладываться поверх строки"""
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Делаем фон полупрозрачным (RGBA: черный цвет с прозрачностью 100 из 255)
        self.setStyleSheet("""
            LoadingOverlay {
                background-color: rgba(0, 0, 0, 100); 
            }
        """)
        
        # Создаем бесконечный прогресс-бар (анимация загрузки)
        self.spinner = QProgressBar(self)
        self.spinner.setRange(0, 0) # Range(0, 0) делает его бесконечным
        self.spinner.setTextVisible(False)
        self.spinner.setFixedHeight(15)
        
        # Размещаем по центру
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.spinner)


class OverlaySelectionDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        real_bg = index.data(Qt.ItemDataRole.BackgroundRole)
        real_fg = index.data(Qt.ItemDataRole.ForegroundRole)

        if real_bg is not None:
            painter.fillRect(opt.rect, real_bg)
        else:
            painter.fillRect(opt.rect, opt.palette.base())

        is_selected = opt.state & QStyle.StateFlag.State_Selected
        if is_selected:
            highlight_color = opt.palette.highlight().color()
            painter.fillRect(opt.rect, highlight_color)
            opt.state &= ~QStyle.StateFlag.State_Selected

        opt.backgroundBrush = QBrush(Qt.BrushStyle.NoBrush) # use qproperty-treakBgColor!

        if real_fg is not None:
            opt.palette.setBrush(QPalette.ColorRole.Text, real_fg)
            opt.palette.setBrush(QPalette.ColorRole.WindowText, real_fg)

        widget = option.widget
        style = widget.style() if widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)

class PlaylistWidget(QTableWidget):
    """Кастомная таблица с поддержкой блокировки строк"""
    def __init__(self, rows=None, cols=None, parent=None):
        super().__init__(rows, cols, parent)
        self.overlays = {}

        palette = self.palette()
        
        self._next_safe_id = 1
        self._mem_to_safe_id = {} # id памяти -> безопасный маленький ID
        self._item_row_map = {}

        self.verticalScrollBar().valueChanged.connect(self.update_overlays_position)
        self.horizontalScrollBar().valueChanged.connect(self.update_overlays_position)

        self.playlist = []
        self.current_index: Optional[int] = None

        self._treak_color_is_current = QColor(palette.color(QPalette.ColorRole.HighlightedText))
        self._treak_color_unavailable = palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text) # "#5f6368"
        self._treak_color_not_loaded = palette.color(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Text) # "#a5a5a5"
        self._treak_color = QColor("#f2f2f2")

        self._treak_bg_is_current = QColor(palette.color(QPalette.ColorRole.Accent))
        self._treak_bg_unavailable = palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base)  #"#0b0b0b"
        self._treak_bg_not_loaded = QColor("#0f0f0f")   #"#0f0f0f"

        self.setItemDelegate(OverlaySelectionDelegate(self))

        # --- Drag & Drop ---
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)


    @Property(QColor)
    def treakColorCurrent(self):
        return self._treak_color_is_current

    @treakColorCurrent.setter
    def treakColorCurrent(self, color: QColor):
        self._treak_color_is_current = color
        self.update() 

    @Property(QColor)
    def treakColorUnavailable(self):
        return self._treak_color_unavailable

    @treakColorUnavailable.setter
    def treakColorUnavailable(self, color: QColor):
        self._treak_color_unavailable = color
        self.update()

    @Property(QColor)
    def treakColorNotLoaded(self):
        return self._treak_color_not_loaded

    @treakColorNotLoaded.setter
    def treakColorNotLoaded(self, color: QColor):
        self._treak_color_not_loaded = color
        self.update()

    @Property(QColor)
    def treakColor(self):
        return self._treak_color

    @treakColor.setter
    def treakColor(self, color: QColor):
        self._treak_color = color
        self.update()

    @Property(QColor)
    def treakBgColorCurrent(self):
        return self._treak_bg_is_current 

    @treakBgColorCurrent.setter
    def treakBgColorCurrent(self, color: QColor):
        self._treak_bg_is_current  = color
        self.update() 

    @Property(QColor)
    def treakBgColorUnavailable(self):
        return self._treak_bg_unavailable

    @treakBgColorUnavailable.setter
    def treakBgColorUnavailable(self, color: QColor):
        self._treak_bg_unavailable = color
        self.update()

    @Property(QColor)
    def treakBgColorNotLoaded(self):
        return self._treak_bg_not_loaded

    @treakBgColorNotLoaded.setter
    def treakBgColorNotLoaded(self, color: QColor):
        self._treak_bg_not_loaded = color
        self.update()

    def setPlaylist(self,playlist):
        self.playlist=playlist
        for row, item in enumerate(self.playlist):
            self.insertRow(row)
            self.update_row(row, item)

        if self.current_index is not None and self.current_index < len(self.playlist):
            self.selectRow(self.current_index)


    def update_row(self, row: int, item: PlaylistItem) -> None:
        # Генерируем маленький ID, если видим элемент впервые
        mem_id = id(item)
        if mem_id not in self._mem_to_safe_id:
            self._mem_to_safe_id[mem_id] = self._next_safe_id
            self._next_safe_id += 1
            
        # Запоминаем строку по маленькому ID
        safe_id = self._mem_to_safe_id[mem_id]
        self._item_row_map[safe_id] = row
        
        artist = item.uploader or "Unknown artist"
        track_item = QTableWidgetItem(f"{item.title}\n{artist}")
        track_item.setData(Qt.UserRole, item.page_url)
        length_item = QTableWidgetItem(self.format_time(item.duration * 1000))
        self.setItem(row, 0, track_item)
        self.setItem(row, 1, length_item)
        self.setRowHeight(row, 44)
        self.apply_row_style(row)

    def apply_row_style(self, row: int) -> None:
        if row < 0 or row >= len(self.playlist):
            return

        item = self.playlist[row]
        is_current = row == self.current_index
        if is_current:
            background = QBrush(self._treak_bg_is_current)
        elif item.unavailable:
            background = QBrush(self._treak_bg_unavailable)
        elif not item.stream_url:
            background = QBrush(self._treak_bg_not_loaded)
        else:
            background = QBrush() 

        if is_current:
            foreground = QBrush(self._treak_color_is_current)
        elif item.unavailable:
            foreground = QBrush(self._treak_color_unavailable)
        elif not item.stream_url:
            foreground = QBrush(self._treak_color_not_loaded)
        else:
            foreground = QBrush(self._treak_color)

        for column in range(self.columnCount()):
            table_item = self.item(row, column)
            if table_item is None:
                continue
            font = table_item.font()
            font.setWeight(QFont.DemiBold if is_current and not item.unavailable else QFont.Normal)
            table_item.setFont(font)
            table_item.setForeground(foreground)
            table_item.setBackground(background)
            if item.unavailable and item.load_error:
                table_item.setToolTip(item.load_error)
            elif is_current:
                table_item.setToolTip("Now playing")
            else:
                table_item.setToolTip("")
        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_overlays_position()

    def link_dynamic_item(self, row: int):
        if 0 <= row < len(self.playlist):
            # Возвращаем наш маленький безопасный ID (например, 15)
            return self._mem_to_safe_id[id(self.playlist[row])]
        return None

    def get_dynamic_item(self, row_address): # спасибо ебаной иишке, я бы эту хуйню сам не смог
        if row_address is None:
            return None
            
        row = self._item_row_map.get(row_address)
        
        if row is not None and row < len(self.playlist):
            # Проверяем, что по этой строке всё ещё лежит тот самый элемент
            if self._mem_to_safe_id.get(id(self.playlist[row])) == row_address:
                return row

        return None

    def setItemLoading(self, row, is_loading):
        """Включает или выключает режим загрузки для конкретной строки"""
        # Блокируем или разблокируем ячейки в строке
        for col in range(self.columnCount()):
            item = self.item(row, col)
            if item:
                flags = item.flags()
                if is_loading:
                    # Убираем флаги активности и выделения
                    item.setFlags(flags & ~Qt.ItemIsEnabled & ~Qt.ItemIsSelectable)
                else:
                    # Возвращаем флаги активности
                    item.setFlags(flags | Qt.ItemIsEnabled | Qt.ItemIsSelectable)

        if is_loading:
            if row not in self.overlays:
                # Создаем оверлей, родителем обязательно должен быть viewport() таблицы
                overlay = LoadingOverlay(self.viewport())
                self.overlays[row] = overlay
                overlay.show()
        else:
            if row in self.overlays:
                # Удаляем оверлей
                overlay = self.overlays.pop(row)
                overlay.deleteLater()
                
        self.update_overlays_position()

    def clearPlaylistView(self):
        """Полностью очищает плейлист и удаляет все оверлеи"""
        for overlay in self.overlays.values():
            overlay.deleteLater()
        
        self.overlays.clear()
        self._mem_to_safe_id.clear()
        self._item_row_map.clear()
        self.setRowCount(0)

    def update_overlays_position(self):
        """Пересчитывает геометрию оверлеев при скролле и ресайзе"""
        for row, overlay in self.overlays.items():
            # Получаем визуальные координаты первой и последней ячейки в строке
            rect_first = self.visualRect(self.model().index(row, 0))
            rect_last = self.visualRect(self.model().index(row, self.columnCount() - 1))
            
            if rect_first.isValid():
                # Объединяем прямоугольники, чтобы накрыть всю строку целиком
                target_rect = rect_first.united(rect_last)
                overlay.setGeometry(target_rect)
                overlay.show()
            else:
                # Если строка ушла за пределы видимости (скролл), скрываем оверлей
                overlay.hide()

    def dropEvent(self, event):
        if event.source() is not self:
            return super().dropEvent(event)

        selected_rows = sorted(set(idx.row() for idx in self.selectedIndexes()))
        if not selected_rows:
            event.ignore()
            return
        source_row = selected_rows[0]

        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        drop_row = self.indexAt(pos).row()
        if drop_row == -1:
            drop_row = self.rowCount() - 1

        indicator = self.dropIndicatorPosition()
        if indicator == QAbstractItemView.BelowItem:
            drop_row += 1
        elif indicator == QAbstractItemView.OnViewport:
            drop_row = self.rowCount() - 1

        if drop_row > source_row:
            drop_row -= 1
        drop_row = max(0, min(drop_row, len(self.playlist) - 1))

        # Важно: запрещаем Qt самому доделывать "move" на уровне модели —
        # именно это добавляло лишнюю/пустую строку после нашего ручного переноса.
        event.setDropAction(Qt.IgnoreAction)
        event.accept()

        if drop_row == source_row:
            return

        self._move_row(source_row, drop_row)


    def _move_row(self, source_row: int, target_row: int) -> None:
        """Переставляет элемент в self.playlist и обновляет только затронутый диапазон строк."""
        item = self.playlist.pop(source_row)
        self.playlist.insert(target_row, item)

        lo, hi = sorted((source_row, target_row))

        def remap(old_row: int) -> int:
            if old_row == source_row:
                return target_row
            if source_row < old_row <= target_row:
                return old_row - 1
            if target_row <= old_row < source_row:
                return old_row + 1
            return old_row

        if self.current_index is not None:
            self.current_index = remap(self.current_index)

        if self.overlays:
            self.overlays = {remap(row): ov for row, ov in self.overlays.items()}

        # Перерисовываем ТОЛЬКО диапазон между source и target,
        # а не весь плейлист — иначе на 500+ треках это заметно тормозит.
        self.setUpdatesEnabled(False)
        try:
            for row in range(lo, hi + 1):
                self.update_row(row, self.playlist[row])
        finally:
            self.setUpdatesEnabled(True)

        self.selectRow(target_row)
        self.update_overlays_position()

    def remove_row(self, row: int) -> None:
        """Безопасно удаляет строку по ее индексу."""
        if row < 0 or row >= len(self.playlist):
            return

        # 1. Удаляем оверлей текущей строки, если он был
        if row in self.overlays:
            overlay = self.overlays.pop(row)
            overlay.deleteLater()

        # 2. Извлекаем элемент из списка данных
        removed_item = self.playlist.pop(row)

        # Удаляем его из карты ссылок
        mem_id = id(removed_item)
        if hasattr(self, "_mem_to_safe_id"):
            safe_id = self._mem_to_safe_id.pop(mem_id, None)
            if safe_id:
                self._item_row_map.pop(safe_id, None)
        else:
            self._item_row_map.pop(mem_id, None)

        # 3. Удаляем визуальную строку из таблицы Qt
        self.removeRow(row)

        # 4. Сдвигаем оверлеи загрузки для всех последующих строк на -1
        if self.overlays:
            self.overlays = {
                (r - 1 if r > row else r): ov for r, ov in self.overlays.items()
            }

        # 5. Обновляем карту _item_row_map ТОЛЬКО для оставшихся сдвинутых элементов
        # (это занимает <1 мс даже для 9999 элементов)
        for r in range(row, len(self.playlist)):
            item = self.playlist[r]
            item_key = (
                self._mem_to_safe_id[id(item)]
                if hasattr(self, "_mem_to_safe_id")
                else id(item)
            )
            self._item_row_map[item_key] = r

        # 6. Корректируем индекс текущего воспроизводимого трека
        if self.current_index is not None:
            if self.current_index == row:
                self.current_index = None  # Воспроизводимый трек был удален
            elif self.current_index > row:
                self.current_index -= 1  # Трек сдвинулся выше

        # 7. Пересчитываем визуальное положение оставшихся оверлеев
        self.update_overlays_position()

    @staticmethod
    def format_time(milliseconds: int) -> str:
        seconds = max(0, milliseconds // 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"



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
        os.makedirs(os.path.join(os.environ['APPDATA'],".config","MSMP-Stream","6.0"), exist_ok=True)
        #if "__compiled__" in globals(): # I'm too lazy to support Windows for now.
        #    return os.path.dirname(os.path.abspath(sys.argv[0]))
        #else:
        #    return os.path.dirname(os.path.abspath(sys.modules['__main__'].__file__))
    else:
        raise RuntimeError("MSMP not supported on this platform")



def LoadConfigYaml():
    if(os.path.isfile(os.path.join(LocalSaveDir(),"config","config.yml"))):
        with open(os.path.join(LocalSaveDir(),"config","config.yml"), "r", encoding="utf-8") as file:
            config = yaml.safe_load(file)
        print(config)
        return config
    else:
        config = {
            "cookies":{"browser":"firefox","selected":0},
            "skin":"Foxyglass"
        }

        os.makedirs(os.path.join(LocalSaveDir(),"config"), exist_ok=True)
        with open(os.path.join(LocalSaveDir(),"config","config.yml"), "w", encoding="utf-8") as file:
            yaml.dump(config, file, default_flow_style=False, allow_unicode=True)

        return config

#....
