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
