import sys,json,os
from enum import Enum
from PySide6.QtCore import QParallelAnimationGroup, QPoint, QPropertyAnimation, QEasingCurve, QRect, Qt, Signal, QTimer,QSize
from PySide6.QtGui import QPainter, QColor, QBrush, QPainterPath,QIcon,QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QLabel,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,QProgressBar,QScrollArea,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QMainWindow
)

if __name__ == "__main__":
    from other import LocalSaveDir,PlaylistWidget,load_playlist_data
else:
    from .other import LocalSaveDir,PlaylistWidget,load_playlist_data


class RotationDirection(Enum):
    UP = 1
    DOWN = 2

class WidgetRotator(QWidget):
    """
    Иммерсивный контейнер для плавной смены виджетов.
    Поддерживает сохранение важных виджетов в памяти для повторного использования.
    """
    rotation_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mainWidget=parent
        self.current_widget = None
        self.anim_group = None
        self.current_nameWidget = None
        
        self.setProperty("clipsChildren", True)

    def _remove_old_widget(self, widget: QWidget):
        """
        Вспомогательный метод для правильного удаления или скрытия старого виджета.
        """
        if not widget:
            return
            
        widget.hide()
        widget.setGraphicsEffect(None) # Очищаем эффект, чтобы избежать багов при повторном показе
        
        # Проверяем, помечен ли виджет как важный (через setProperty)
        if widget.property("is_important"):
            widget.setParent(None) # Отвязываем от ротатора, сохраняя в C++ памяти
        else:
            widget.deleteLater()   # Удаляем навсегда

    def set_initial_widget(self, widget: QWidget):
        if self.current_widget:
            self._remove_old_widget(self.current_widget)
            
        self.current_widget = widget
        self.current_widget.setParent(self)
        self.current_widget.setGeometry(0, 0, self.width(), self.height())
        self.current_widget.show()

    def replace_widget(self, new_widget: QWidget, direction: RotationDirection = RotationDirection.UP, duration: int = 500, widget_name=None):
        if not self.current_widget:
            self.set_initial_widget(new_widget)
            return

        if widget_name is not None and (widget_name == self.current_nameWidget):
            return
        self.current_nameWidget = widget_name 

        # Очистка "призраков" от спам-кликов с учетом важных виджетов
        if self.anim_group and self.anim_group.state() == QParallelAnimationGroup.State.Running:
            self.anim_group.stop()
            for child in self.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
                if child != new_widget and child != self.current_widget:
                    self._remove_old_widget(child)

        old_widget = self.current_widget
        self.current_widget = new_widget
        self.current_widget.setParent(self)
        
        w, h = self.width(), self.height()
        
        easing_curve = QEasingCurve.Type.OutCubic

        if direction == RotationDirection.UP:
            old_end_rect = QRect(0, int(-h * 0.4), w, h)
            new_start_rect = QRect(0, h, w, h)
        else:
            old_end_rect = QRect(0, int(h * 0.4), w, h)
            new_start_rect = QRect(0, -h, w, h)

        # 1. АНИМАЦИЯ СТАРОГО ВИДЖЕТА
        self.old_geo_anim = QPropertyAnimation(old_widget, b"geometry")
        self.old_geo_anim.setDuration(duration)
        self.old_geo_anim.setEasingCurve(easing_curve)
        self.old_geo_anim.setStartValue(QRect(0, 0, w, h))
        self.old_geo_anim.setEndValue(old_end_rect)

        old_effect = QGraphicsOpacityEffect(old_widget)
        old_widget.setGraphicsEffect(old_effect)
        self.old_alpha_anim = QPropertyAnimation(old_effect, b"opacity")
        self.old_alpha_anim.setDuration(int(duration * 0.7))
        self.old_alpha_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self.old_alpha_anim.setStartValue(1.0)
        self.old_alpha_anim.setEndValue(0.0)

        # 2. АНИМАЦИЯ НОВОГО ВИДЖЕТА
        self.current_widget.setGeometry(new_start_rect)
        self.current_widget.show()

        self.new_geo_anim = QPropertyAnimation(self.current_widget, b"geometry")
        self.new_geo_anim.setDuration(duration)
        self.new_geo_anim.setEasingCurve(easing_curve)
        self.new_geo_anim.setStartValue(new_start_rect)
        self.new_geo_anim.setEndValue(QRect(0, 0, w, h))

        new_effect = QGraphicsOpacityEffect(self.current_widget)
        self.current_widget.setGraphicsEffect(new_effect)
        self.new_alpha_anim = QPropertyAnimation(new_effect, b"opacity")
        self.new_alpha_anim.setDuration(duration)
        self.new_alpha_anim.setEasingCurve(QEasingCurve.Type.InQuad)
        self.new_alpha_anim.setStartValue(0.0)
        self.new_alpha_anim.setEndValue(1.0)

        # 3. ЗАПУСК И УПРАВЛЕНИЕ СЛОЯМИ
        if direction == RotationDirection.UP:
            self.current_widget.raise_()
        else:
            old_widget.raise_()

        self.anim_group = QParallelAnimationGroup()
        self.anim_group.addAnimation(self.old_geo_anim)
        self.anim_group.addAnimation(self.old_alpha_anim)
        self.anim_group.addAnimation(self.new_geo_anim)
        self.anim_group.addAnimation(self.new_alpha_anim)

        # Используем лямбду, чтобы передать old_widget в функцию завершения
        self.anim_group.finished.connect(lambda w=old_widget: self._finalize_animation(w))
        
        self.anim_group.start()

    def _finalize_animation(self, old_widget):
        """Вызывается по окончании анимации смены виджетов."""
        self._remove_old_widget(old_widget)
        self.rotation_finished.emit()

    def resizeEvent(self, event):
        if self.current_widget and (not self.anim_group or self.anim_group.state() != QParallelAnimationGroup.State.Running):
            self.current_widget.setGeometry(0, 0, self.width(), self.height())
        super().resizeEvent(event)

    def parent(self):
        return super().parent()




class PlaylistScreen(QWidget):
    def __init__(self,parent,path):
        super().__init__(parent)

        self.mainWidget=parent

        # Главный слой (layout) для самого окна
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0) # Убираем отступы по краям окна

        # 1. Создаем область прокрутки (QScrollArea)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True) # Разрешаем содержимому растягиваться по ширине окна
        
        # 2. Создаем виджет-контейнер, в котором будут лежать все наши элементы
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)

        # --- ДОБАВЛЯЕМ ЭЛЕМЕНТЫ В КОНТЕЙНЕР ---

        # Главный заголовок
        with open(path,"r") as f:
            data=json.load(f)
            self.playlist_title = str(data.get("title") or "MSMP5 Playlist")
            playlist=load_playlist_data(data)


        title_layout = QHBoxLayout(self)

        image = QLabel(self)
        image.setPixmap(QPixmap("resources/MSMPwave.png"))
        image.setScaledContents(True)
        image.setFixedSize(QSize(128, 128))
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_layout.addWidget(image)

        titleName_layout = QVBoxLayout(self)
        title_layout.addLayout(titleName_layout)

        title_layout.addStretch()


        self.button = QPushButton("Играть", self)
        self.button.setFixedSize(QSize(150, 50))
        

        #self.button.clicked.connect(self.setPlayNow)

        title_label = QLabel(self.playlist_title)
        title_font = title_label.font()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        titleName_layout.addWidget(title_label)
        titleName_layout.addWidget(self.button)
        content_layout.addLayout(title_layout)

        # Создаем таблицу (например, на 25 строк)

        self.table = PlaylistWidget()
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
        #self.table.customContextMenuRequested.connect(self.show_playlist_menu)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.verticalScrollBar().setSingleStep(1)
        self.table.viewport().installEventFilter(self)
        self.table.setRowHeight(1, 20)

        # ВАЖНО: Отключаем собственную полосу прокрутки таблицы
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)




        content_layout.addWidget(self.table)


        self.table.playlist=playlist

        self.table.setPlaylist(self.table.playlist)

        self.update_tableHeight()



        content_layout.addWidget(self.table)



        # 3. Кладем наш виджет-контейнер внутрь области прокрутки
        scroll_area.setWidget(content_widget)

        # 4. Добавляем QScrollArea в главное окно
        main_layout.addWidget(scroll_area)

    def update_tableHeight(self):
        # ТРЮК: Устанавливаем высоту таблицы равной высоте всех её строк + заголовка,
        # чтобы она развернулась полностью и не пыталась скроллиться внутри себя.
        table_height = self.table.horizontalHeader().height()
        for i in range(self.table.rowCount()):
            table_height += self.table.rowHeight(i)
        # Добавляем 2 пикселя запаса для границ таблицы
        self.table.setFixedHeight(table_height + 2)



    def setPlayNow(self):
        if(self.mainWidget.playlistScreenNow):
            if not(self.mainWidget.playlistScreenNow==self):
                self.mainWidget.main_window.stop_playback()
                self.mainWidget.playlistScreenNow.deleteLater() 
        print("fox")
        self.mainWidget.playlistScreenNow=self

        self.mainWidget.main_window.table=self.table

        self.mainWidget.main_window.playlist=self.table.playlist

        self.setProperty("is_important", True) 

    def play_index(self,row):
        self.setPlayNow()
        self.mainWidget.main_window.play_index(row)

class MainScreen(QWidget):
    def __init__(self,parent):
        super().__init__(parent)
        layout = QHBoxLayout(self)

        playlists=os.listdir(os.path.join(LocalSaveDir(),"MyPlaylists"))

        for x in range(5):
            button = QPushButton(self)
            button.setFixedSize(QSize(150, 150))
            button.setIcon(QIcon("resources/MSMPwave.png"))
            button.setIconSize(QSize(150, 150))

            if not(os.path.isfile(os.path.join(LocalSaveDir(),"MyPlaylists",playlists[x]))):
                continue

            playlist_path=os.path.join(LocalSaveDir(),"MyPlaylists",playlists[x])
    
            button.clicked.connect(lambda _,pl=playlist_path: parent.load_playlist(pl))
            layout.addWidget(button)

        self.setLayout(layout)

class recordlibrary(QWidget):
    """Menager local music library"""
    def __init__(self,parent=None):
        super().__init__()

        self.resize(1280, 720)


        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, QMainWindow):
                self.main_window = widget
                break


        #self.main_window.table.deleteLater() 

        self.playlistScreenNow=None

        # Создаем элементы интерфейса
        self.button = QPushButton("Плейлисты", self)
        self.button.setFixedSize(QSize(150, 50))

        self.button2 = QPushButton("Текущий", self)
        self.button2.setFixedSize(QSize(150, 50))


        self.rotator = WidgetRotator(self)
        self.rotator.set_initial_widget(MainScreen(self))

        # Создаем вертикальный компоновщик (layout) и добавляем виджеты
        layout = QHBoxLayout(self)

        layout_menu = QVBoxLayout(self)

        layout_menu.addWidget(self.button)
        layout_menu.addWidget(self.button2)

        layout.addLayout(layout_menu)

        layout.addWidget(self.rotator)

        # Устанавливаем компоновщик для QWidget
        self.setLayout(layout)

        # Подключаем сигнал нажатия кнопки к слоту (методу)
        self.button.clicked.connect(self.returnToPlaylists)
        self.button2.clicked.connect(self.returnPlaylistNow)

    def returnToPlaylists(self):
        self.rotator.replace_widget(MainScreen(self), duration = 300)

    def returnPlaylistNow(self):
        print(self.playlistScreenNow)
        if(self.playlistScreenNow):
            self.rotator.replace_widget(self.playlistScreenNow, duration = 300)

    def load_playlist(self,path):
        self.rotator.replace_widget(PlaylistScreen(self,path), duration = 300)


if __name__ == "__main__":
  # Инициализируем приложение
  app = QApplication(sys.argv)

  # Создаем и показываем главный виджет
  window = recordlibrary()
  window.show()

  # Запускаем цикл обработки событий приложения
  sys.exit(app.exec())




        