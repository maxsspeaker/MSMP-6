from dataclasses import dataclass, field
from PySide6.QtCore import QObject, Signal


class PlayerEvents(QObject):
    # Воспроизведение
    on_playback_started = Signal()             # Плеер начал играть
    on_playback_paused = Signal()              # Плеер поставлен на паузу
    on_playback_stopped = Signal()             # Плеер остановлен
    on_start_playback = Signal(int)               # Загрузил воспроизведение
    
    # Файлы и данные
    on_playlist_opened = Signal(str, list)       # Передаем путь к плейлисту (str) и кол-во треков (int)
    on_playlist_saved = Signal(str, list)       # Передаем путь к плейлисту (str) и кол-во треков (int)
    
    # Жизненный цикл программы
    on_app_closing = Signal()                  # Программа закрывается (шанс для плагинов сохранить настройки)



@dataclass
class PlaylistItem:
    page_url: str
    title: str = "Loading..."
    stream_url: str = ""
    duration: int = 0
    source_id: str = "youtube"
    uploader: str = ""
    album: str = ""
    artwork_url: str = ""
    publis: bool = False
    unavailable: bool = False
    load_error: str = ""
    waveform: list[float] = field(default_factory=list)
    waveform_ready: bool = False


class PluginBase:
    """
    Базовый класс для всех плагинов плеера
    """
    def __init__(self, main_window):
        # Подготовка к загрузке
        self.main_window = main_window

    def init_plugin(self):
        """
        Внесение изменений и применения плагина
        """
        raise NotImplementedError("Плагин должен реализовать метод init_plugin")