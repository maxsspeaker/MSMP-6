from PySide6.QtCore import QObject,QRunnable,Signal,Slot
from typing import Optional
from urllib.parse import parse_qs, urlparse
import traceback
import subprocess
import sys,os
import json
import shutil
from .types import *
import re


class ResolveSignals(QObject):
    resolved = Signal(int, object)
    failed = Signal(int, str, str)

class JamPlaylistSignals(QObject):
    parsed = Signal(int, object, str)
    status = Signal(str)
    failed = Signal(int, str, str)


def parse_youtube_link(url):
    # Паттерн для чистого плейлиста (начинается с playlist?list=)
    playlist_pattern = r'(?:https?:\/\/)?(?:www\.|m\.)?youtube\.com\/playlist\?(?:.*&)?list=([a-zA-Z0-9_-]+)'
    
    # Паттерн для видео (обычное, мобильное, короткое youtu.be или shorts)
    video_pattern = r'(?:https?:\/\/)?(?:www\.|m\.)?(?:youtube\.com\/(?:watch\?(?:.*&)?v=|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    
    # Паттерн для параметра list= в любой ссылке
    list_param_pattern = r'[?&]list=([a-zA-Z0-9_-]+)'

    # Проверяем, есть ли ID видео
    video_match = re.search(video_pattern, url)
    # Проверяем, есть ли ID плейлиста (как отдельный плейлист или параметр в видео)
    playlist_match = re.search(playlist_pattern, url)
    list_param_match = re.search(list_param_pattern, url)

    if video_match and list_param_match:
        return {
            "type": "video&playlist",
            "video_id": video_match.group(1),
            "playlist_id": list_param_match.group(1)
        }
    elif playlist_match:
        return {
            "type": "playlist",
            "playlist_id": playlist_match.group(1)
        }
    elif video_match:
        return {
            "type": "video",
            "video_id": video_match.group(1)
        }
    else:
        return {
            "type": "Неизвестная ссылка или не YouTube"
        }

def get_ytdlp_executable() -> str:
    if (sys.platform == "win32"):
        if "__compiled__" in globals():
            app_path = os.path.dirname(os.path.abspath(sys.argv[0]))
        else:
            app_path = os.path.dirname(os.path.abspath(sys.modules['__main__'].__file__))

        print(os.path.join(app_path,"external","yt-dlp","yt-dlp.exe"))
        return os.path.join(app_path,"external","yt-dlp","yt-dlp.exe")

    candidates = [
        os.environ.get("YTDLP_PATH", "").strip(),
        os.environ.get("YTDLP_BIN", "").strip(),
        shutil.which("yt-dlp") or "",
        shutil.which("yt-dlp.exe") or "",
    ]
    script_dir = os.path.dirname(os.path.abspath(sys.modules['__main__'].__file__))
    candidates.extend(
        [
            os.path.join(script_dir, "yt-dlp"),
            os.path.join(script_dir, "yt-dlp.exe"),
        ]
    )

    for candidate in candidates:
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    raise RuntimeError(
        "yt-dlp executable not found. Set YTDLP_PATH/YTDLP_BIN or put yt-dlp in PATH."
    )

def extract_youtube_video_id(page_url: str) -> str:
    parsed = urlparse(page_url)
    query_id = parse_qs(parsed.query).get("v", [None])[0]
    if query_id:
        return str(query_id).strip()

    path = parsed.path.strip("/")
    if parsed.netloc in {"youtu.be", "www.youtu.be"} and path:
        return path.split("/", 1)[0].strip()

    match = re.search(
        r"(?:v=|/shorts/|/live/|/embed/|youtu\.be/)([A-Za-z0-9_-]{6,})",
        page_url,
    )
    if match:
        return match.group(1).strip()

    if path:
        tail = path.split("/")[-1]
        if len(tail) >= 6:
            return tail.strip()
    return ""


def run_external_ytdlp(
    args: list[str],
    status=None,
) -> dict:
    executable = get_ytdlp_executable()
    cmd = [executable, *args]
    CREATE_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if sys.platform == "win32" else 0
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,   
        stderr=subprocess.PIPE, # Сливаем потоки, чтобы читать всё из stdout
        text=True,
        encoding="utf-8",creationflags=CREATE_NO_WINDOW
        )
    json_data=None

    while True:
        line = proc.stdout.readline()
            
        if not line and proc.poll() is not None:
            break
            
        if line:
            if line.startswith('{'):
                json_data = line.strip()
            else:
                if(status):
                    status.emit(line.strip())
                print(line, end='')

    proc.wait()

    if proc.returncode != 0:
        message = proc.stderr.readline() or f"yt-dlp exited with code {proc.returncode}"
        raise RuntimeError(message)

    payload = json_data
    if not payload:
        raise RuntimeError("yt-dlp returned no data")

    try:
        return json.loads(json_data)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse yt-dlp JSON output: {exc}") from exc


def build_ytdlp_browser_args(cookie_browser: str) -> list[str]:
    browser = (cookie_browser or "").strip()
    if not browser:
        return []
    return ["--cookies-from-browser", browser]

class JamPlaylistTask(QRunnable):
    def __init__(
        self,
        index: Optional[int],
        page_url: str,
        signals: JamPlaylistSignals,
        cookie_browser: str = "",
        JamPlaylist: bool = True,
    ) -> None:
        super().__init__()
        self.index = index
        self.page_url = page_url
        self.cookie_browser = cookie_browser
        self.signals = signals
        self.JamPlaylist = JamPlaylist

    @Slot()
    def run(self) -> None:
        try:
            if self.JamPlaylist:
                video_id = extract_youtube_video_id(self.page_url)

                if not video_id:
                    raise RuntimeError("Не удалось извлечь id видео из page_url")

                jam_url = (
                    "https://www.youtube.com/watch?v="
                    f"{video_id}&list=RD{video_id}&start_radio=1"
                )
            else:
                jam_url = self.page_url

            print(jam_url)
            print("Resolving playlist")

            args = [
                "--no-quiet",
                "--no-warnings",
                "--skip-download",
                "--flat-playlist",
                "--dump-single-json",
                "--no-check-certificates",
                "--retries",
                "3",
                "--fragment-retries",
                "3",
                *build_ytdlp_browser_args(self.cookie_browser),
                jam_url,
            ]

            data = run_external_ytdlp(args, status=self.signals.status)

            if not isinstance(data, dict):
                raise RuntimeError("yt-dlp returned an empty or invalid playlist response")

            items: list[PlaylistItem] = []
            entries = data.get("entries") or []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue

                page_url = (
                    entry.get("webpage_url")
                    or entry.get("url")
                    or entry.get("original_url")
                    or ""
                )

                if not page_url:
                    entry_id = str(entry.get("id") or "").strip()
                    if entry_id:
                        page_url = f"https://www.youtube.com/watch?v={entry_id}"

                if not page_url:
                    continue

                items.append(
                    PlaylistItem(
                        page_url=str(page_url),
                        title=str(entry.get("title") or entry.get("name") or page_url),
                        duration=int(entry.get("duration") or 0),
                        source_id=str(
                            entry.get("extractor_key")
                            or entry.get("extractor")
                            or "yt-dlp"
                        ),
                        uploader=str(entry.get("uploader") or entry.get("channel") or ""),
                        album=str(entry.get("album") or ""),
                        artwork_url=str(entry.get("thumbnail") or ""),
                    )
                )

            if not items:
                raise RuntimeError("yt-dlp did not return any playlist items")

            playlist_title = str(data.get("title") or "Jam playlist")
            self.signals.parsed.emit(self.index, items, playlist_title)
        except BaseException as exc:
            error = self.format_error(exc)
            details = traceback.format_exc()
            try:
                self.signals.failed.emit(self.index, error, details)
            except RuntimeError:
                print(details, file=sys.stderr, flush=True)

    @staticmethod
    def format_error(exc: BaseException) -> str:
        message = str(exc).strip()
        if "ERROR:" in message:
            message = message.removeprefix("ERROR:").strip()
        if "HTTP Error 429" in message or "Too Many Requests" in message:
            return (
                "HTTP 429 Too Many Requests. Сервис временно ограничил запросы. "
                "Попробуйте позже или выберите cookies браузера с активной сессией."
            )
        if not message:
            message = exc.__class__.__name__
        return message


class YtdlpLogger:
    def __init__(self,status=None):
        self.status=status

    def debug(self, message: str) -> None:
        if(self.status):
            self.status.emit(message)
        print("yt-dlp: %s", message)
        logging.debug("yt-dlp: %s", message)

    def warning(self, message: str) -> None:
        print("yt-dlp: %s", message)
        logging.warning("yt-dlp: %s", message)

    def error(self, message: str) -> None:
        print("yt-dlp: %s", message)
        logging.error("yt-dlp: %s", message)

    def info(self, message: str) -> None:
        print("yt-dlp: %s", message)
        logging.info("yt-dlp: %s", message)



class ResolveTask(QRunnable):
    def __init__(
        self,
        index: int,
        url: str,
        signals: ResolveSignals,
        cookie_browser: str = "",
    ) -> None:
        super().__init__()
        self.index = index
        self.url = url
        self.cookie_browser = cookie_browser
        self.signals = signals

    @Slot()
    def run(self) -> None:
        try:
            print("Resolving audio")

            args = [
                "--no-quiet",
                "--no-warnings",
                "--skip-download",
                "--dump-single-json",
                "--no-playlist",
                "--format",
                "bestaudio/best",
                "--no-check-certificates",
                "--retries",
                "3",
                "--fragment-retries",
                "3",
                *build_ytdlp_browser_args(self.cookie_browser),
                self.url,
            ]

            data = run_external_ytdlp(args, status=None)


            if not isinstance(data, dict):
                raise RuntimeError("yt-dlp returned an empty or invalid response")

            stream_url = self.best_stream_url(data)
            if not stream_url:
                raise RuntimeError("yt-dlp did not return a playable stream URL")

            item = PlaylistItem(
                page_url=self.url,
                title=data.get("title") or self.url,
                stream_url=stream_url,
                duration=int(data.get("duration") or 0),
                source_id=data.get("extractor_key") or data.get("extractor") or "yt-dlp",
                uploader=data.get("uploader") or data.get("channel") or "",
                album=data.get("album") or "",
                artwork_url=data.get("thumbnail") or "",
            )
            self.signals.resolved.emit(self.index, item)
        except BaseException as exc:
            error = self.format_error(exc)
            details = traceback.format_exc()
            try:
                self.signals.failed.emit(self.index, error, details)
            except RuntimeError:
                print(details, file=sys.stderr, flush=True)

    @staticmethod
    def format_error(exc: BaseException) -> str:
        message = str(exc).strip()
        if "ERROR:" in message:
            message = message.removeprefix("ERROR:").strip()
        if "HTTP Error 429" in message or "Too Many Requests" in message:
            return (
                "HTTP 429 Too Many Requests. Сервис временно ограничил запросы. "
                "Попробуйте позже или выберите cookies браузера с активной сессией."
            )
        if not message:
            message = exc.__class__.__name__
        return message

    @staticmethod
    def best_stream_url(data: dict) -> str:

        formats = data.get("formats") or []
        audio_formats = [
            item
            for item in formats
            if item.get("url")
            and item.get("acodec") != "none"
            and item.get("vcodec") in (None, "none")
        ]
        for x in audio_formats:
            if (x.get("acodec")=="mp3" and x.get("protocol")=="http"):
                return x["url"]

        if data.get("url") and data.get("acodec") != "none":
            return data["url"]


        if not audio_formats:
            audio_formats = [
                item for item in formats if item.get("url") and item.get("acodec") != "none"
            ]
        if not audio_formats:
            return ""

        def score(item: dict) -> tuple[int, int]:
            abr = int(item.get("abr") or item.get("tbr") or 0)
            preference = int(item.get("preference") or 0)
            return abr, preference

        return max(audio_formats, key=score)["url"]