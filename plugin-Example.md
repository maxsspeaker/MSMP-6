## Simple Example plugin class:

```python
# plugins/hello_world_plugin/index.py
import os
from PySide6.QtWidgets import QMessageBox
from PySide6.QtGui import QAction
from modules.types import PluginBase
from . import helper

class ExamplePlugin(PluginBase):
    def init_plugin(self):
        self.my_folder = os.path.dirname(__file__)

        self.StarFildMenu=self.main_window.MainMenuBar.add_submenu(self.main_window.PluginMenu, "hello_world_plugin", hide_if_empty=False)

        self.StarFildMenu.addAction("Show Message", self.show_dialog)

    def show_dialog(self):
        QMessageBox.information(
            self.main_window, 
            "Test", 
            f"Hello world from:\n{self.my_folder}"
        )
```


```
MSMP-FoxWave/
└── plugins/               <-- Plguin folder
    └── hello_world_plugin/
        ├── index.py       <-- main plugin file
        └── helper.py      <-- yours other local modules
```
```
    # События кнопок
    self.main_window.events.on_playback_started = Signal()             # Плеер начал играть
    self.main_window.events.on_playback_paused = Signal()              # Плеер поставлен на паузу
    self.main_window.events.on_playback_stopped = Signal()             # Плеер остановлен
    self.main_window.events.on_start_playback = Signal(int)            # Загрузил воспроизведение

    self.main_window.events.on_skin_changed = Signal(str)              # Изменение скина в реальном времени (WyrmSkin плагин) (str - имя скина)

    # События воспроизвеления (Рекомендуется использовать данные события!)
    self.main_window.events.on_play_status_changed = Signal(str)       # Изменение состояния воспроизведения ("Playing", "Paused", "Stopped")
    self.main_window.events.on_update_current_metadata = Signal(PlaylistItem)  # Обновление мета данных композиции (изменение композиции)
    self.main_window.events.on_sync_position = Signal(int)             # Синхронизация позиции (int) позиция в мелисекундах
    
    # Файлы и данные
    self.main_window.events.on_playlist_opened = Signal(str, list)     # Открытие плейлиса путь к плейлисту (str) и кол-во треков (int)
    self.main_window.events.on_playlist_saved = Signal(str, list)      # Сохранение плейлиста путь к плейлисту (str) и кол-во треков (int)
    
    # Жизненный цикл программы
    self.main_window.events.on_app_closing = Signal()                  # Программа закрывается 

    self.main_window.events.resolve_signals.resolved = Signal(int,PlaylistItem) - Поток получен (int позиция) PlaylistItem - полная информация композиции и поток
    self.main_window.events.resolve_signals.resolved = Signal(Optional[int],error: str,details: str = "")  Ошибка получения потока 
```