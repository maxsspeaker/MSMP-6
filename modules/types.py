from dataclasses import dataclass, field

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