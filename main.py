import json
import logging
import random
import re
import struct
import sys
import threading
import traceback
import time
import os
import webbrowser
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import parse_qs, urlparse
import argparse
import math
import shutil
import subprocess
import tempfile

from dbus_next import Variant
from PySide6.QtCore import (
    QObject,
    QRunnable,
    QThreadPool,
    QTimer,
    QUrl,
    Signal,
    Slot,
    Qt,
    QtMsgType,
    qInstallMessageHandler,
    QPoint,
    QSize,
    Property,
)
from PySide6.QtMultimedia import QAudioBufferOutput, QAudioFormat, QAudioOutput, QMediaPlayer
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPixmap,QAction,QIcon
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QMenu, 
    QListView,
    QSizePolicy,
)
from modules.other import GradientImageLabel,extract_youtube_video_id,parse_youtube_link,run_external_ytdlp,build_ytdlp_browser_args,FixedComboBox,get_ffmpeg_executable
from modules.discordrpcWrapper import discordrpcWrapper
from modules.types import *
from modules.dbus import MprisServer
from modules.ui_engine import UIEngine

UIEngine.register("gradientImageLabel", GradientImageLabel)
UIEngine.register("fixedComboBox",      FixedComboBox)


ERROR_REPORTER: Optional["ErrorReporter"] = None

# CAVA-style visualizer tuning
VISUALIZER_BAR_COUNT = 58
VISUALIZER_BAR_GAP = 2.0
VISUALIZER_LEFT_MARGIN = 0
VISUALIZER_RIGHT_MARGIN = 0
VISUALIZER_TOP_MARGIN = 12
VISUALIZER_BOTTOM_MARGIN = 12
VISUALIZER_MIN_BAR_HEIGHT = 1

VISUALIZER_GAIN = 1.0
VISUALIZER_ATTACK = 0.42
VISUALIZER_DECAY = 0.020
VISUALIZER_PEAK_DECAY = 0.010
VISUALIZER_MIN_VISIBLE_LEVEL = 0.012

#VISUALIZER_WINDOW_WIDTH = 250
#VISUALIZER_WINDOW_HEIGHT = 128
VISUALIZER_BACKGROUND_COLOR = "#000000"
VISUALIZER_TRACK_COLOR = "#00000000"
VISUALIZER_BAR_COLOR_LOW = "#7CFF6B"
VISUALIZER_BAR_COLOR_MID = "#D7FF4A"
VISUALIZER_BAR_COLOR_HIGH = "#FFB347"
VISUALIZER_BAR_COLOR_PEAK = "#FF5D5D"
VISUALIZER_BAR_OUTLINE = "#00000000"
VISUALIZER_PEAK_HEIGHT = 3.0
VISUALIZER_CORNER_RADIUS = 3

WAVEFORM_BIN_COUNT = 440
WAVEFORM_BACKGROUND_COLOR = "#00000000"
WAVEFORM_TRACK_COLOR = "#232323"
WAVEFORM_BUFFER_COLOR = "#7c7c7c"
WAVEFORM_PLAYED_COLOR = "#e8e8e8"
WAVEFORM_HANDLE_COLOR = "#f2f2f2"
WAVEFORM_HEIGHT = 44


def is_video_unavailable_error(error: str) -> bool:
    message = error.lower()
    return (
        "video unavailable" in message
        and "this video is not available" in message
    )


class ResolveSignals(QObject):
    resolved = Signal(int, object)
    failed = Signal(int, str, str)

class JamPlaylistSignals(QObject):
    parsed = Signal(int, object, str)
    status = Signal(str)
    failed = Signal(int, str, str)


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
            try:
                data = run_external_ytdlp(args, status=self.signals.status)
            except: 
                print(traceback.format_stack())

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


class ErrorReporter(QObject):
    error_requested = Signal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self.error_requested.connect(self.show_error)

    @Slot(str, str)
    def show_error(self, title: str, details: str) -> None:
        box = QMessageBox()
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle("Program error")
        box.setText(title)
        box.setDetailedText(details)
        box.exec()


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


class VisualizerWindow(QWidget):
    def __init__(self,parent=None) -> None:
        super().__init__()
        #self.setWindowTitle("MSMP5 Levels")
        #self.setAttribute(Qt.WA_DeleteOnClose)
        #self.resize(VISUALIZER_WINDOW_WIDTH, VISUALIZER_WINDOW_HEIGHT)
        self.levels = [0.0] * VISUALIZER_BAR_COUNT
        self.peaks = [0.0] * VISUALIZER_BAR_COUNT
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.parent=parent
        self._bar_color_low = QColor("#7CFF6B")
        self._bar_color_mid = QColor("#D7FF4A")
        self._bar_color_high = QColor("#FFB347")
        self._bar_color_peak = QColor("#FF5D5D")

    def set_levels(self, levels: list[float], peaks: Optional[list[float]] = None) -> None:
        if not levels:
            return
        if len(levels) != VISUALIZER_BAR_COUNT:
            levels = self.resample_levels(levels, VISUALIZER_BAR_COUNT)
        if peaks is None:
            peaks = levels
        elif len(peaks) != VISUALIZER_BAR_COUNT:
            peaks = self.resample_levels(peaks, VISUALIZER_BAR_COUNT)

        self.levels = [min(1.0, max(0.0, level)) for level in levels]
        self.peaks = [min(1.0, max(0.0, peak)) for peak in peaks]
        self.update()

    @Property(QColor)
    def barColorLow(self):
        return self._bar_color_low

    @barColorLow.setter
    def barColorLow(self, color: QColor):
        self._bar_color_low = color
        self.update()  # Вызываем перерисовку при изменении стиля

    @Property(QColor)
    def barColorMid(self):
        return self._bar_color_mid

    @barColorMid.setter
    def barColorMid(self, color: QColor):
        self._bar_color_mid = color
        self.update()

    @Property(QColor)
    def barColorHigh(self):
        return self._bar_color_high

    @barColorHigh.setter
    def barColorHigh(self, color: QColor):
        self._bar_color_high = color
        self.update()

    @Property(QColor)
    def barColorPeak(self):
        return self._bar_color_peak

    @barColorPeak.setter
    def barColorPeak(self, color: QColor):
        self._bar_color_peak = color
        self.update()

    @staticmethod
    def resample_levels(levels: list[float], count: int) -> list[float]:
        if count <= 0:
            return []
        if len(levels) == count:
            return levels

        result = []
        for index in range(count):
            source = index * (len(levels) - 1) / max(1, count - 1)
            left = int(source)
            right = min(len(levels) - 1, left + 1)
            fraction = source - left
            result.append(levels[left] * (1 - fraction) + levels[right] * fraction)
        return result

    def level_color(self,level: float) -> QColor:
        level = max(0.0, min(1.0, level))
        if level < 0.35:
            return self._bar_color_low
        if level < 0.7:
            return self._bar_color_mid
        return self._bar_color_high

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))

        width = max(1.0, float(self.width()))
        height = max(1.0, float(self.height()))
        left = float(VISUALIZER_LEFT_MARGIN)
        right = float(VISUALIZER_RIGHT_MARGIN)
        top = float(VISUALIZER_TOP_MARGIN)
        bottom = float(VISUALIZER_BOTTOM_MARGIN)

        drawable_width = max(1.0, width - left - right)
        drawable_height = max(1.0, height - top - bottom)
        bar_width = max(5.0, (drawable_width - VISUALIZER_BAR_GAP * (VISUALIZER_BAR_COUNT - 1)) / VISUALIZER_BAR_COUNT)
        base_y = height - bottom

        painter.setPen(Qt.NoPen)
        painter.setRenderHint(QPainter.Antialiasing, False)

        for index, level in enumerate(self.levels):
            peak = self.peaks[index] if index < len(self.peaks) else level
            x = left + index * (2 + VISUALIZER_BAR_GAP)

            # Background track behind each bar for that CAVA glow-gutter feeling.
            painter.setBrush(QColor(VISUALIZER_TRACK_COLOR))
            painter.drawRoundedRect(x, top, bar_width, drawable_height, VISUALIZER_CORNER_RADIUS, VISUALIZER_CORNER_RADIUS)

            level = max(0.0, min(1.0, level))
            peak = max(0.0, min(1.0, peak))

            if level <= 0.0 and peak <= 0.0:
                continue

            bar_height = max(VISUALIZER_MIN_BAR_HEIGHT, level * drawable_height)
            bar_top = base_y - bar_height
            color = self.level_color(level)
            top_color = QColor(color)
            top_color = top_color.lighter(145)
            bottom_color = QColor(color)
            bottom_color = bottom_color.darker(120)
            #bottom_color.setAlpha(100)

            gradient = QLinearGradient(x, bar_top, x, base_y)
            gradient.setColorAt(0.0, top_color)
            gradient.setColorAt(1.0, bottom_color)
            painter.setBrush(gradient)
            painter.drawRoundedRect(x, bar_top, bar_width, bar_height, VISUALIZER_CORNER_RADIUS, VISUALIZER_CORNER_RADIUS)

            # Peak cap, the tiny bright ridge that makes it feel like CAVA.
            peak_y = base_y - max(VISUALIZER_MIN_BAR_HEIGHT, peak * drawable_height)
            painter.setBrush(self._bar_color_peak)
            painter.drawRoundedRect(
                x,
                peak_y - (VISUALIZER_PEAK_HEIGHT * 0.5),
                bar_width,
                VISUALIZER_PEAK_HEIGHT,
                VISUALIZER_CORNER_RADIUS,
                VISUALIZER_CORNER_RADIUS,
            )



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

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self.sliderPressed.emit()
            value = self._value_from_x(event.position().x())
            self.setValue(value)
            self.sliderMoved.emit(value)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            value = self._value_from_x(event.position().x())
            self.setValue(value)
            self.sliderMoved.emit(value)
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
                    played_index = int(
                        (self._value - self._minimum)
                        / float(self._maximum - self._minimum)
                        * max(0, bin_count - 1)
                    )
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


class WaveformSignals(QObject):
    generated = Signal(int, object)
    failed = Signal(int, str)


class WaveformTask(QRunnable):
    def __init__(
        self,
        index: int,
        stream_url: str,
        duration_ms: int,
        signals: WaveformSignals,
        cookie_browser: str = "",
    ) -> None:
        super().__init__()
        self.index = index
        self.stream_url = stream_url
        self.duration_ms = duration_ms
        self.cookie_browser = cookie_browser
        self.signals = signals

    @Slot()
    def run(self) -> None:
        try:
            waveform = self.generate_waveform()
            self.signals.generated.emit(self.index, waveform)
        except BaseException as exc:
            self.signals.failed.emit(self.index, str(exc).strip() or exc.__class__.__name__)

    @staticmethod
    def _finalize_chunk(peak: float, rms_sum: float, sample_count: int) -> float:
        if sample_count <= 0:
            return 0.0
        rms = math.sqrt(max(0.0, rms_sum) / float(sample_count))
        # Peak keeps transients, RMS keeps the body; together they follow the real track shape better.
        return max(peak, rms * 1.08)

    def generate_waveform(self) -> list[float]:
        ffmpeg = get_ffmpeg_executable()

        if not ffmpeg:
            raise RuntimeError("ffmpeg not found in PATH")

        if not self.stream_url:
            raise RuntimeError("stream url is empty")

        if self.duration_ms <= 0:
            raise RuntimeError("track duration is unknown")

        CREATE_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if sys.platform == "win32" else 0

        sample_rate = 22050
        chunk_samples = 2048

        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-reconnect",
            "1",
            "-reconnect_streamed",
            "1",
            "-reconnect_delay_max",
            "2",
            "-i",
            self.stream_url,
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-f",
            "s16le",
            "pipe:1",
        ]

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,creationflags=CREATE_NO_WINDOW)
        assert proc.stdout is not None
        assert proc.stderr is not None

        from array import array

        chunks: list[float] = []
        chunk_peak = 0.0
        chunk_rms_sum = 0.0
        chunk_count = 0

        while True:
            chunk = proc.stdout.read(65536)
            if not chunk:
                break

            samples = array("h")
            samples.frombytes(chunk)
            if sys.byteorder != "little":
                samples.byteswap()

            for sample in samples:
                value = abs(sample) / 32768.0
                if value > chunk_peak:
                    chunk_peak = value
                chunk_rms_sum += value * value
                chunk_count += 1

                if chunk_count >= chunk_samples:
                    chunks.append(self._finalize_chunk(chunk_peak, chunk_rms_sum, chunk_count))
                    chunk_peak = 0.0
                    chunk_rms_sum = 0.0
                    chunk_count = 0

        if chunk_count:
            chunks.append(self._finalize_chunk(chunk_peak, chunk_rms_sum, chunk_count))

        stderr = proc.stderr.read().decode("utf-8", errors="replace").strip()
        return_code = proc.wait()

        if return_code != 0 and not chunks:
            raise RuntimeError(stderr or f"ffmpeg exited with code {return_code}")

        if not chunks:
            return [0.0] * WAVEFORM_BIN_COUNT

        waveform = VisualizerWindow.resample_levels(chunks, WAVEFORM_BIN_COUNT)
        peak = max(waveform) if waveform else 0.0
        if peak <= 0.0:
            return [0.0] * WAVEFORM_BIN_COUNT

        return [min(1.0, max(0.0, (value / peak) ** 0.82)) for value in waveform]


# Регистрируем кастомные виджеты после их объявления
UIEngine.register("waveformSeekBar",  WaveformSeekBar)
UIEngine.register("visualizerWindow", VisualizerWindow)


class PlayerWindow(QMainWindow):
    MAX_RESTARTS = 3
    PLAY_MODES_icons = ("resources/arrow-s-right.svg", "resources/out-loop.svg", "resources/loop.svg", "resources/shuffle.svg")
    PLAY_MODES = ("Seq", "One", "All", "Rnd")


    def show_playlist_menu(self, position: QPoint):
        # Получаем индекс строки/ячейки, где был совершен клик
        index = self.table.indexAt(position)
        if not index.isValid():
            return # Кликнули вне заполненной области

        # 4. Создаем меню
        menu = QMenu(self)

        # Добавляем действия (кнопки) в меню
        action1 = QAction("Воспроизвести", self)
        action1.triggered.connect(lambda: self.play_index(self.table.rowAt(position.y())))
        menu.addAction(action1)


        action2 = QAction("Запустить Джем", self)
        action2.triggered.connect(lambda: self.parse_jam_playlist(self.table.rowAt(position.y()))
        )
        menu.addAction(action2)

        action3 = QAction("Открыть расположение", self)
        action3.triggered.connect(lambda: webbrowser.open(self.playlist[index.row()].page_url))
        menu.addAction(action3)

        menu.addSeparator() # Разделитель (опционально)

        action4 = QAction("Удалить", self)
        action4.triggered.connect(lambda: self.remove_index(index.row()))
        menu.addAction(action4)

        # 5. Показываем меню в точке клика
        menu.exec(self.table.viewport().mapToGlobal(position))

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MSMP FoxWave")
        self.resize(820, 760)

        self.setWindowIcon(QIcon("resources/MSMPicon.png"))

        self.SkinName="Pleximania"

        self.playlist: list[PlaylistItem] = []
        self.current_index: Optional[int] = None
        self.pending_position = 0
        self.restart_attempts = 0
        self.user_dragging = False
        self.resolving_indexes: set[int] = set()
        self.resolve_autoplay: dict[int, bool] = {}
        self.play_mode_index = 0
        self.error_boxes: list[QMessageBox] = []
        self.playlist_title = "MSMP5 Playlist"
        self.playlist_image_url = "https://msmp.maxsspeaker.space/static/img/Missing.png"
        self.mpris_server = MprisServer()
        self.mpris_playback_status = "Stopped"
        self.mpris_position_timer = QTimer(self)
        self.mpris_position_timer.setInterval(250)
        self.mpris_position_timer.setTimerType(Qt.PreciseTimer)
        self.mpris_position_timer.timeout.connect(self.sync_mpris_position)

        self._last_mpris_position_us = -1

        #self.visualizer_window: Optional[VisualizerWindow] = None

        self.visualizer_levels = [0.0] * VISUALIZER_BAR_COUNT
        self.visualizer_peaks = [0.0] * VISUALIZER_BAR_COUNT

        self.visualizer_window = VisualizerWindow()
        self.visualizer_window.set_levels(self.visualizer_levels, self.visualizer_peaks)
        #self.visualizer_window.hide()
        #self.visualizer_window.raise_()
        self.visualizer_window.activateWindow()
        self.visualizer_window.setFixedSize(233,128)

        self.waveform_cache: dict[str, list[float]] = {}
        self.waveform_generation_indexes: set[int] = set()

        self.thread_pool = QThreadPool.globalInstance()
        self.resolve_signals = ResolveSignals()
        self.resolve_signals.resolved.connect(self.on_resolved)
        self.resolve_signals.failed.connect(self.on_resolve_failed)
        self.jam_signals = JamPlaylistSignals()
        self.jam_signals.parsed.connect(self.on_jam_playlist_parsed)
        self.jam_signals.status.connect(self.on_jam_playlist_status)
        self.jam_signals.failed.connect(self.on_jam_playlist_failed)
        self.waveform_signals = WaveformSignals()
        self.waveform_signals.generated.connect(self.on_waveform_generated)
        self.waveform_signals.failed.connect(self.on_waveform_failed)
        self.network = QNetworkAccessManager(self)
        self.network.finished.connect(self.on_artwork_loaded)

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_buffer_output = QAudioBufferOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setAudioBufferOutput(self.audio_buffer_output)
        self.audio_output.setVolume(0.8)
        self.audio_buffer_output.audioBufferReceived.connect(self.on_audio_buffer_received)

        self.player.positionChanged.connect(self.on_position_changed)
        self.player.durationChanged.connect(self.on_duration_changed)
        self.player.playbackStateChanged.connect(self.on_playback_state_changed)
        self.player.mediaStatusChanged.connect(self.on_media_status_changed)
        self.player.errorOccurred.connect(self.on_player_error)
        try:
            self.player.bufferProgressChanged.connect(self.on_buffer_progress_changed)
        except AttributeError:
            pass

        self.buffer_progress_timer = QTimer(self)
        self.buffer_progress_timer.setInterval(120)
        self.buffer_progress_timer.timeout.connect(self.poll_buffer_progress)

        # ── Построение UI через движок ─────────────────────────────────────
        _ui_xml_path = os.path.join(os.path.dirname(__file__), f"skins/{self.SkinName}/index.xml")

        self._engine = UIEngine(context=self, default_spacing=0, default_margin=0)
        container = self._engine.build_file(_ui_xml_path)

        # Удобный алиас: self.ui["widget_id"]
        self.ui = self._engine.widgets

        # ── Ссылки на виджеты (совместимость с остальным кодом) ───────────
        self.NowDisplay          = self.ui["NowDisplay"]
        self.cover_background    = self.ui["cover_background"]
        self.cover_label         = self.ui["cover_label"]
        self.track_title_label   = self.ui["track_title_label"]
        self.artist_label        = self.ui["artist_label"]
        self.album_label         = self.ui["album_label"]
        self.position_slider     = self.ui["position_slider"]
        self.time_label          = self.ui["time_label"]
        self.volume_slider       = self.ui["volume_slider"]
        self.status_label        = self.ui["status_label"]
        self.url_input           = self.ui["url_input"]
        self.add_button          = self.ui["add_button"]
        self.cookie_browser      = self.ui["cookie_browser"]
        self.clear_button        = self.ui["clear_button"]
        self.save_button         = self.ui["save_button"]
        self.load_button         = self.ui["load_button"]
        self.play_button         = self.ui["play_button"]
        self.pause_button        = self.ui["pause_button"]
        self.stop_button         = self.ui["stop_button"]
        self.prev_button         = self.ui["prev_button"]
        self.next_button         = self.ui["next_button"]
        self.restart_button      = self.ui["restart_button"]
        self.mode_button         = self.ui["mode_button"]
        self.playlistBox         = self.ui["playlistBox"]
        self.table               = self.ui["table"]

        # ── cover_background: создаётся вручную (нестандартные аргументы) ─

        self.cover_background.gradient = [(0.95, QColor(0, 0, 0, 0)), (0.6, QColor(0, 0, 0, 128))]
        self.cover_background.setAlignment(Qt.AlignCenter)
        self.cover_background.setScaledContents(True)
        self.cover_background.setFixedHeight(210)
        self.cover_background.lower()
        self.cover_background.setGeometry(self.NowDisplay.rect())

        self.track_title_label.setText("No track")
        self.artist_label.setText("Unknown artist")
        self.album_label.setText("Unknown album")


        # ── Донастройка cover_label ────────────────────────────────────────
        self.cover_label.setAlignment(Qt.AlignCenter)
        self.cover_label.setObjectName("cover")
        self.set_cover_placeholder()

        # ── Донастройка мета-меток ────────────────────────────────────────
        self.track_title_label.setObjectName("trackTitle")
        self.track_title_label.setWordWrap(True)
        self.artist_label.setObjectName("metaText")
        self.album_label.setObjectName("metaText")

        # ── Донастройка status_label ──────────────────────────────────────
        self.status_label.setObjectName("statusText")

        # ── Донастройка time_label ────────────────────────────────────────
        self.time_label.setObjectName("durationText")

        # ── Иконки кнопок управления ──────────────────────────────────────
        for btn, icon_file in (
            (self.prev_button,    "resources/previous.svg"),
            (self.stop_button,    "resources/stop.svg"),
            (self.play_button,    "resources/play.svg"),
            (self.pause_button,   "resources/pause.svg"),
            (self.next_button,    "resources/next.svg"),
            (self.restart_button, "resources/reload-audio.svg"),
        ):
            btn.setIcon(QIcon(icon_file))

        self.mode_button.setIcon(QIcon(self.PLAY_MODES_icons[self.play_mode_index]))

        # ── Донастройка cookie_browser (userData для элементов) ───────────
        cookie_data = ["", "firefox", "chrome", "chromium", "brave", "edge"]
        for i, data in enumerate(cookie_data):
            self.cookie_browser.setItemData(i, data)

        # ── Дополнительный connect для url_input (returnPressed) ──────────
        self.url_input.returnPressed.connect(self.add_url)

        # ── Донастройка volume_slider ─────────────────────────────────────
        self.volume_slider.valueChanged.connect(
            lambda value: self.audio_output.setVolume(value / 100)
        )

        # ── Донастройка seek bar ──────────────────────────────────────────
        self.position_slider.setRange(0, 0)
        self.position_slider.set_buffered_ratio(0.0)
        self.position_slider.sliderPressed.connect(self.on_seek_start)
        self.position_slider.sliderReleased.connect(self.on_seek_end)
        self.position_slider.sliderMoved.connect(self.on_seek_preview)

        # ── Донастройка таблицы ───────────────────────────────────────────
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

        # ── Политика размера playlistBox ──────────────────────────────────
        self.playlistBox.setMinimumHeight(0)
        sp = self.playlistBox.sizePolicy()
        sp.setVerticalPolicy(QSizePolicy.Policy.Ignored)
        self.playlistBox.setSizePolicy(sp)

        # ── visualizer_window уже создан движком, инициализируем данные ───
        self.visualizer_window = self.ui["visualizer_window"]
        self.visualizer_window.set_levels(self.visualizer_levels, self.visualizer_peaks)
        self.visualizer_window.activateWindow()

        self.setCentralWidget(container)
        self.apply_style()
        self.setup_mpris()

        self.discordrpc = discordrpcWrapper(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.cover_background.setGeometry(0, 0, self.width(), self.height())

    def add_url(self) -> None:
        url = self.url_input.text().strip()
        if not url:
            return

        parsed=parse_youtube_link(url)

        if(parsed["type"]=="video&playlist"):
            self.add_url_value(url)

        elif(parsed["type"]=="playlist"):
            self.parse_jam_playlist(url="https://www.youtube.com/playlist?list="+parsed["playlist_id"])
        elif(parsed["type"]=="video"):
            self.add_url_value(url)
        else:
            self.add_url_value(url)

        print(parsed)

        self.url_input.clear()


    def add_url_value(self, url: str, auto_play: bool = False) -> None:
        row = len(self.playlist)
        self.playlist.append(PlaylistItem(page_url=url))
        self.table.insertRow(row)
        self.set_row(row, self.playlist[row])
        self.status_label.setText("Resolving stream...")
        self.emit_mpris_properties_changed("org.mpris.MediaPlayer2.Player", {
            "CanGoNext": bool(self.playlist),
            "CanGoPrevious": bool(self.playlist),
            "CanPlay": bool(self.playlist),
        })
        self.resolve_item(row, auto_play=auto_play)

    def resolve_item(self, index: int, auto_play: bool = False) -> None:
        if index < 0 or index >= len(self.playlist):
            return
        if index in self.resolving_indexes:
            self.resolve_autoplay[index] = self.resolve_autoplay.get(index, False) or auto_play
            return

        self.resolving_indexes.add(index)
        self.resolve_autoplay[index] = auto_play
        task = ResolveTask(
            index,
            self.playlist[index].page_url,
            self.resolve_signals,
            self.cookie_browser.currentData() or "",
        )
        task.setAutoDelete(True)
        self.thread_pool.start(task)


    def parse_jam_playlist(self, index: Optional[int]=None,url: Optional[str] = None) -> None:
        if not(index==None):
            if index < 0 or index >= len(self.playlist):
                return

            item = self.playlist[index]
            self.status_label.setText("Parsing Jam playlist...")
            url=item.page_url
            JamPlaylist=True
        else:
            self.status_label.setText("Parsing playlist...")  
            JamPlaylist=False

        task = JamPlaylistTask(
            index,
            url,
            self.jam_signals,
            self.cookie_browser.currentData() or "",
            JamPlaylist=JamPlaylist
        )
        task.setAutoDelete(True)
        self.thread_pool.start(task)

    def on_jam_playlist_status(
        self,
        status: str,
    ) -> None:

        self.status_label.setText(status)

    def on_jam_playlist_parsed(
        self,
        index: Optional[int],
        items: object,
        playlist_title: str,
    ) -> None:
        if not isinstance(items, list) or not items:
            self.status_label.setText("Jam playlist is empty")
            return

        parsed_items = [item for item in items if isinstance(item, PlaylistItem)]
        if not parsed_items:
            self.status_label.setText("Jam playlist is empty")
            return

        self.stop_playback()
        self.playlist_title = playlist_title or "Jam playlist"
        self.playlist = parsed_items
        self.current_index = None
        self.pending_position = 0
        self.restart_attempts = 0
        self.resolving_indexes.clear()
        self.resolve_autoplay.clear()
        self.refresh_table()
        self.emit_mpris_properties_changed("org.mpris.MediaPlayer2.Player", {
            "CanGoNext": bool(self.playlist),
            "CanGoPrevious": bool(self.playlist),
            "CanPlay": bool(self.playlist),
            "CanSeek": False,
            "Metadata": self.mpris_metadata(),
            "PlaybackStatus": "Stopped",
            "Position": 0,
        })

        self.status_label.setText(f"Jam playlist loaded: {len(self.playlist)} tracks")
        if self.playlist:
            self.play_index(0)

    def on_jam_playlist_failed(self, index: int, error: str, details: str = "") -> None:
        title = self.playlist[index].page_url if 0 <= index < len(self.playlist) else "item"
        message = f"Jam parse failed for {title}: {error}"
        self.status_label.setText(message)
        console_details = details or message
        print(console_details, file=sys.stderr, flush=True)
        logging.error("%s\n%s", message, console_details)

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Jam parse error")
        box.setText(error)
        box.setInformativeText(title)
        if details:
            box.setDetailedText(details)
        self.error_boxes.append(box)
        box.finished.connect(lambda _result, item=box: self.release_error_box(item))
        box.open()

    def on_resolved(self, index: int, item: PlaylistItem) -> None:
        self.resolving_indexes.discard(index)
        auto_play = self.resolve_autoplay.pop(index, False)
        if index < 0 or index >= len(self.playlist):
            return

        cached_waveform = self.waveform_cache.get(item.page_url)
        if cached_waveform:
            item.waveform = cached_waveform
            item.waveform_ready = True

        self.playlist[index] = item
        self.set_row(index, item)
        self.status_label.setText(f"Resolved: {item.title}")

        if self.current_index == index:
            self.update_current_metadata(item)

        if auto_play:
            self.start_playback(index)

    def on_resolve_failed(
        self,
        index: Optional[int],
        error: str,
        details: str = "",
    ) -> None:
        self.resolving_indexes.discard(index)
        if not(index==None):
            self.resolve_autoplay.pop(index, None)
            if 0 <= index < len(self.playlist):
                item = self.playlist[index]
                item.stream_url = ""
                item.load_error = error
                item.unavailable = is_video_unavailable_error(error)
                if item.title == "Loading...":
                    item.title = "Video unavailable" if item.unavailable else "Resolve failed"
                self.set_row(index, item)
                title = item.page_url
            else:
                title = "item"

        message = f"yt-dlp failed: {error}"
        self.status_label.setText(message)
        console_details = details or message
        print(console_details, file=sys.stderr, flush=True)
        logging.error("%s\n%s", message, console_details)

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("yt-dlp error")
        box.setText(error)
        if details:
            box.setDetailedText(details)
        self.error_boxes.append(box)
        box.finished.connect(lambda _result, item=box: self.release_error_box(item))
        box.open()

    def release_error_box(self, box: QMessageBox) -> None:
        if box in self.error_boxes:
            self.error_boxes.remove(box)
        box.deleteLater()

    def set_row(self, row: int, item: PlaylistItem) -> None:
        artist = item.uploader or "Unknown artist"
        track_item = QTableWidgetItem(f"{item.title}\n{artist}")
        track_item.setData(Qt.UserRole, item.page_url)
        length_item = QTableWidgetItem(self.format_time(item.duration * 1000))
        self.table.setItem(row, 0, track_item)
        self.table.setItem(row, 1, length_item)
        self.table.setRowHeight(row, 44)
        self.apply_row_style(row)

    def apply_row_style(self, row: int) -> None:
        if row < 0 or row >= len(self.playlist):
            return

        item = self.playlist[row]
        is_current = row == self.current_index
        background = QBrush(QColor("#1e2a33" if is_current else "#000000"))
        foreground = QBrush(QColor("#5f6368" if item.unavailable else "#f2f2f2"))
        if item.unavailable:
            background = QBrush(QColor("#0b0b0b"))

        for column in range(self.table.columnCount()):
            table_item = self.table.item(row, column)
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

    def refresh_row_style(self, row: Optional[int]) -> None:
        if row is not None and 0 <= row < len(self.playlist):
            self.apply_row_style(row)

    def refresh_table(self) -> None:
        self.table.setRowCount(0)
        for row, item in enumerate(self.playlist):
            self.table.insertRow(row)
            self.set_row(row, item)

        if self.current_index is not None and self.current_index < len(self.playlist):
            self.table.selectRow(self.current_index)

    def play_selected_or_current(self) -> None:
        selected = self.table.currentRow()

        if self.current_index is not None and self.player.playbackState() == QMediaPlayer.PausedState:
            self.player.play()
            self.start_mpris_position_updates()
            self.sync_mpris_position()
            self.set_mpris_playback_status("Playing")
            return

        if selected >= 0 and selected != self.current_index:
            self.play_index(selected)
            return

        if self.current_index is not None:
            self.player.play()
            self.start_mpris_position_updates()
            self.sync_mpris_position()
            self.set_mpris_playback_status("Playing")
        elif self.playlist:
            self.play_index(0)

    def pause_playback(self) -> None:
        self.player.pause()
        self.sync_mpris_position()
        self.set_mpris_playback_status("Paused")

    def stop_playback(self) -> None:
        self.stop_mpris_position_updates()
        self.stop_buffer_progress_monitor()
        self.player.stop()
        self._last_mpris_position_us = 0
        self.update_buffer_progress(0.0)
        self.set_mpris_playback_status("Stopped")
        self.update_mpris_player_properties({"Position": 0})

    def set_mpris_playback_status(self, status: str) -> None:
        if status not in {"Playing", "Paused", "Stopped"}:
            return
        if self.mpris_playback_status == status:
            return
        self.discordrpc.set_playback_status(status)
        self.mpris_playback_status = status
        self.emit_mpris_properties_changed("org.mpris.MediaPlayer2.Player", {
            "PlaybackStatus": status,
        })

    def on_visualizer_closed(self, _obj=None) -> None:
        self.visualizer_window = None

    def play_index(self, index: int) -> None:
        if index < 0 or index >= len(self.playlist):
            return

        self.pending_position = 0
        self.restart_attempts = 0
        item = self.playlist[index]

        if item.stream_url:
            self.start_playback(index)
        else:
            self.status_label.setText("Resolving stream...")
            self.resolve_item(index, auto_play=True)

    def start_playback(self, index: int) -> None:
        item = self.playlist[index]
        previous_index = self.current_index
        self.current_index = index
        self.table.selectRow(index)
        self.refresh_row_style(previous_index)
        self.refresh_row_style(index)
        self.update_current_metadata(item)

        self._last_mpris_position_us = -1
        self.position_slider.set_waveform(item.waveform)
        self.update_buffer_progress(0.0)
        self.player.setSource(QUrl(item.stream_url))
        self.player.play()

        self.start_mpris_position_updates()
        self.sync_mpris_position(0)

        self.set_mpris_playback_status("Playing")
        self.status_label.setText(f"Playing: {item.title}")
        self.emit_mpris_properties_changed("org.mpris.MediaPlayer2.Player", {
            "Metadata": self.mpris_metadata(),
            "PlaybackStatus": self.mpris_playback_status,
            "CanSeek": self.player.duration() > 0,
            "Position": 0,
        })


        if self.pending_position:
            restored_position = self.pending_position
            self.pending_position = 0
            QTimer.singleShot(
                600,
                lambda pos=restored_position: self.set_player_position(pos, emit_seeked=False),
            )

    def play_next(self) -> None:
        if not self.playlist:
            return

        if self.current_index is None:
            self.play_index(0)
            return

        next_index = self.next_index_after_current()
        if next_index is None:
            self.stop_playback()
            return
        self.play_index(next_index)

    def play_previous(self) -> None:
        if not self.playlist:
            return

        if self.current_index is None:
            self.play_index(0)
            return

        previous_index = (self.current_index - 1) % len(self.playlist)
        self.play_index(previous_index)

    def remove_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.playlist):
            return

        del self.playlist[row]
        self.table.removeRow(row)

        if self.current_index == row:
            self.stop_playback()
            self.current_index = None
        elif self.current_index is not None and row < self.current_index:
            self.current_index -= 1
        self.refresh_table()

    def remove_index(self,index:int) -> None:
        if index < 0 or index >= len(self.playlist):
            return

        del self.playlist[index]
        self.table.removeRow(index)

        if self.current_index == index:
            self.stop_playback()
            self.current_index = None
        elif self.current_index is not None and index < self.current_index:
            self.current_index -= 1
        self.refresh_table()

    def clear_playlist(self) -> None:
        self.stop_playback()
        self.playlist.clear()
        self.current_index = None
        self.table.setRowCount(0)
        self.position_slider.setRange(0, 0)
        self.time_label.setText("0:00 / 0:00")
        #self.duration_label.setText("0:00")
        self.track_title_label.setText("No track")
        self.artist_label.setText("Unknown artist")
        self.album_label.setText("Unknown album")
        self.set_cover_placeholder()
        self.position_slider.set_waveform([])
        self.update_buffer_progress(0.0)
        self.status_label.setText("Playlist cleared")
        self.emit_mpris_properties_changed("org.mpris.MediaPlayer2.Player", {
            "Metadata": self.mpris_metadata(),
            "CanGoNext": False,
            "CanGoPrevious": False,
            "CanPlay": False,
        })

    def move_selected(self, direction: int) -> None:
        row = self.table.currentRow()
        target = row + direction
        if row < 0 or target < 0 or target >= len(self.playlist):
            return

        self.playlist[row], self.playlist[target] = self.playlist[target], self.playlist[row]

        if self.current_index == row:
            self.current_index = target
        elif self.current_index == target:
            self.current_index = row

        self.refresh_table()
        self.table.selectRow(target)

    def save_playlist(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(
            self,
            "Save playlist",
            os.path.expanduser("~")+f"/.config/MSMP-Stream/5.0/MyPlaylists/{self.playlist_title}.plmsmpsbox",
            "MSMP playlist (*.plmsmpsbox);;JSON playlists (*.json)"
        )
        if not path:
            return

        data = self.to_msmp_playlist()
        try:
            with open(path, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
            self.status_label.setText(f"Playlist saved: {path}")
        except OSError as exc:
            QMessageBox.warning(self, "Save failed", str(exc))

    def load_playlist(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Load playlist",
            os.path.expanduser("~")+"/.config/MSMP-Stream/5.0/MyPlaylists/",
            "MSMP playlist (*.plmsmpsbox);;JSON playlists (*.json);;All files (*)",
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)

            self.stop_playback()
            self.current_index = None
            self.playlist = self.from_playlist_data(data)
            self.refresh_table()
            self.status_label.setText(f"Playlist loaded: {path}")
            self.emit_mpris_properties_changed("org.mpris.MediaPlayer2.Player", {
                "Metadata": self.mpris_metadata(),
                "CanGoNext": bool(self.playlist),
                "CanGoPrevious": bool(self.playlist),
                "CanPlay": bool(self.playlist),
            })
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "Load failed", str(exc))

    def to_msmp_playlist(self) -> dict:
        return {
            "title": self.playlist_title,
            "ImgUrl": self.playlist_image_url,
            "playlist": [self.to_msmp_track(item) for item in self.playlist],
        }

    @staticmethod
    def to_msmp_track(item: PlaylistItem) -> dict:
        return {
            "ID": item.source_id,
            "name": item.title,
            "uploader": item.uploader,
            "album": item.album,
            "artwork_url": item.artwork_url,
            "duration": item.duration,
            "url": item.page_url,
            "Publis": item.publis,
            "Unavailable": item.unavailable,
            "load_error": item.load_error,
        }

    def from_playlist_data(self, data) -> list[PlaylistItem]:
        if isinstance(data, dict):
            self.playlist_title = str(data.get("title") or "MSMP5 Playlist")
            self.playlist_image_url = str(
                data.get("ImgUrl")
                or data.get("img_url")
                or "https://msmp.maxsspeaker.space/static/img/Missing.png"
            )
            tracks = data.get("playlist")
            if not isinstance(tracks, list):
                raise ValueError("MSMP playlist must contain a playlist array")
            return [self.from_playlist_entry(entry) for entry in tracks if isinstance(entry, dict)]

        if isinstance(data, list):
            self.playlist_title = "MSMP5 Playlist"
            return [self.from_playlist_entry(entry) for entry in data if isinstance(entry, dict)]

        raise ValueError("Playlist file must contain a JSON object or array")

    @staticmethod
    def from_playlist_entry(entry: dict) -> PlaylistItem:
        page_url = entry.get("url") or entry.get("page_url")
        if not page_url:
            raise ValueError("Playlist entry has no url")

        title = entry.get("name") or entry.get("title") or page_url
        return PlaylistItem(
            page_url=str(page_url),
            title=str(title),
            duration=int(entry.get("duration") or 0),
            source_id=str(entry.get("ID") or entry.get("source_id") or "yt-dlp"),
            uploader=str(entry.get("uploader") or ""),
            album=str(entry.get("album") or ""),
            artwork_url=str(entry.get("artwork_url") or entry.get("thumbnail") or ""),
            publis=bool(entry.get("Publis") or entry.get("publis") or False),
            unavailable=bool(entry.get("Unavailable") or entry.get("unavailable") or False),
            load_error=str(entry.get("load_error") or ""),
        )

    def update_current_metadata(self, item: PlaylistItem) -> None:
        self.track_title_label.setText(item.title or "No track")
        self.artist_label.setText(item.uploader or "Unknown artist")
        self.album_label.setText(item.album or self.playlist_title or "Unknown album")

        self.discordrpc.set_activity(item)
        #if item.duration:
        #    self.duration_label.setText(self.format_time(item.duration * 1000))

        if item.artwork_url:
            self.network.get(QNetworkRequest(QUrl(item.artwork_url)))
        else:
            self.set_cover_placeholder()

    def set_cover_placeholder(self) -> None:
        self.cover_background.set_new_image(QPixmap("resources/MSMPwaveBg.png"))
        self.cover_label.set_new_image(QPixmap("resources/MSMPwave.png"))

    def on_artwork_loaded(self, reply) -> None:
        data = reply.readAll()
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            scaled = pixmap.scaled(
                self.cover_label.size(),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            self.cover_label.set_new_image(scaled)
            self.cover_background.set_new_image(scaled)
        else:
            self.set_cover_placeholder()
        reply.deleteLater()

    def toggle_play_mode(self) -> None:
        self.play_mode_index = (self.play_mode_index + 1) % len(self.PLAY_MODES)
        self.mode_button.setIcon(QIcon(self.PLAY_MODES_icons[self.play_mode_index]))
        self.emit_mpris_properties_changed("org.mpris.MediaPlayer2.Player", {
            "LoopStatus": self.current_mpris_loop_status(),
            "Shuffle": self.PLAY_MODES[self.play_mode_index] == "Rnd",
        })

    def setup_mpris(self) -> None:
        bridge = self.mpris_server.bridge
        bridge.play_requested.connect(self.play_selected_or_current)
        bridge.pause_requested.connect(self.pause_playback)
        bridge.stop_requested.connect(self.stop_playback)
        bridge.next_requested.connect(self.play_next)
        bridge.previous_requested.connect(self.play_previous)
        bridge.raise_requested.connect(self.raise_from_mpris)
        bridge.quit_requested.connect(self.close)
        bridge.seek_requested.connect(self.seek_relative)
        bridge.set_position_requested.connect(self.set_player_position)
        bridge.open_uri_requested.connect(lambda uri: self.add_url_value(uri, auto_play=True))
        bridge.loop_status_requested.connect(self.set_loop_status_from_mpris)
        bridge.shuffle_requested.connect(self.set_shuffle_from_mpris)
        bridge.volume_requested.connect(self.set_volume_from_mpris)
        self.update_mpris_player_properties({
            "Volume": float(self.audio_output.volume()),
            "Metadata": self.mpris_metadata(),
        })
        self.mpris_server.start()

    def emit_mpris_properties_changed(self, interface: str, changed: dict) -> None:
        if interface == "org.mpris.MediaPlayer2.Player":
            self.update_mpris_player_properties(changed)

    def emit_mpris_seeked(self, position: int) -> None:
        self.mpris_server.seeked(position)

    def update_mpris_player_properties(self, changed: dict) -> None:
        allowed = {
            "PlaybackStatus",
            "LoopStatus",
            "Rate",
            "Shuffle",
            "Metadata",
            "Volume",
            "Position",
            "MinimumRate",
            "MaximumRate",
            "CanGoNext",
            "CanGoPrevious",
            "CanPlay",
            "CanPause",
            "CanSeek",
            "CanControl",
        }
        filtered = {key: value for key, value in changed.items() if key in allowed}
        if filtered:
            self.mpris_server.update(filtered)

    def raise_from_mpris(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def seek_relative(self, offset_ms: int) -> None:
        self.set_player_position(max(0, self.player.position() + offset_ms))

    def set_player_position(self, position_ms: int, emit_seeked: bool = True) -> None:
        position_ms = max(0, int(position_ms))
        self.player.setPosition(position_ms)
        self.sync_mpris_position(position_ms)

        self.discordrpc.sync_position(position_ms)

        if emit_seeked:
            self.emit_mpris_seeked(position_ms)

    def start_mpris_position_updates(self) -> None:
        if not self.mpris_position_timer.isActive():
            self.mpris_position_timer.start()

    def stop_mpris_position_updates(self) -> None:
        if self.mpris_position_timer.isActive():
            self.mpris_position_timer.stop()

    def sync_mpris_position(self, position_ms: Optional[int] = None) -> None:
        if self.current_index is None:
            return

        if position_ms is None:
            position_ms = self.player.position()

        position_us = max(0, int(position_ms) * 1000)
        if position_us == self._last_mpris_position_us:
            return

        self._last_mpris_position_us = position_us
        self.update_mpris_player_properties({"Position": position_us})

    def set_loop_status_from_mpris(self, value: str) -> None:
        modes = {"None": "Seq", "Track": "One", "Playlist": "All"}
        target = modes.get(value)
        if target and target in self.PLAY_MODES:
            self.play_mode_index = self.PLAY_MODES.index(target)
            self.mode_button.setIcon(QIcon(self.PLAY_MODES_icons[target]))
            self.update_mpris_player_properties({"LoopStatus": value})

    def set_shuffle_from_mpris(self, value: bool) -> None:
        target = "Rnd" if value else "Seq"
        self.play_mode_index = self.PLAY_MODES.index(target)
        self.mode_button.setText(target)
        self.update_mpris_player_properties({
            "Shuffle": bool(value),
            "LoopStatus": self.current_mpris_loop_status(),
        })

    def set_volume_from_mpris(self, value: float) -> None:
        volume = min(1.0, max(0.0, float(value)))
        self.audio_output.setVolume(volume)
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(round(volume * 100))
        self.volume_slider.blockSignals(False)
        self.update_mpris_player_properties({"Volume": volume})

    def current_mpris_loop_status(self) -> str:
        mode = self.PLAY_MODES[self.play_mode_index]
        if mode == "One":
            return "Track"
        if mode == "All":
            return "Playlist"
        return "None"

    def mpris_metadata(self) -> dict:
        item = None
        if self.current_index is not None and 0 <= self.current_index < len(self.playlist):
            item = self.playlist[self.current_index]

        if item is None:
            return MprisServer.empty_metadata()

        metadata = {
            "mpris:trackid": Variant("o", f"/org/mpris/MediaPlayer2/Track/{self.current_index}"),
            "xesam:title": Variant("s", item.title or "Unknown track"),
            "xesam:artist": Variant("as", [item.uploader] if item.uploader else []),
            "xesam:album": Variant("s", item.album or self.playlist_title or ""),
            "xesam:url": Variant("s", item.page_url),
        }
        if item.duration:
            metadata["mpris:length"] = Variant("x", int(item.duration * 1000 * 1000))
        if item.artwork_url:
            metadata["mpris:artUrl"] = Variant("s", item.artwork_url)
        return metadata

    def next_index_after_current(self) -> Optional[int]:
        if self.current_index is None or not self.playlist:
            return None

        mode = self.PLAY_MODES[self.play_mode_index]
        if mode == "One":
            return self.current_index
        if mode == "Rnd":
            return random.randrange(len(self.playlist))

        next_index = self.current_index + 1
        if next_index < len(self.playlist):
            return next_index
        if mode == "All":
            return 0
        return None

    def on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        loading_states = {
            QMediaPlayer.LoadingMedia,
            QMediaPlayer.BufferingMedia,
        }
        ready_states = {
            QMediaPlayer.LoadedMedia,
            QMediaPlayer.BufferedMedia,
        }

        if status in loading_states:
            self.start_buffer_progress_monitor()
            self.poll_buffer_progress()
        elif status in ready_states:
            self.poll_buffer_progress()
            self.stop_buffer_progress_monitor()
        elif status in {QMediaPlayer.NoMedia, QMediaPlayer.InvalidMedia, QMediaPlayer.EndOfMedia}:
            self.stop_buffer_progress_monitor()
            self.update_buffer_progress(0.0)

        if self.current_index is not None and status in ready_states:
            self.request_waveform_generation(self.current_index)

        if status != QMediaPlayer.EndOfMedia:
            return

        next_index = self.next_index_after_current()
        if next_index is not None:
            self.play_index(next_index)
        else:
            self.set_mpris_playback_status("Stopped")

    def restart_current_stream(self) -> None:
        if self.current_index is None:
            return

        self.pending_position = self.player.position()
        self.update_buffer_progress(0.0)
        self.playlist[self.current_index].stream_url = ""
        self.status_label.setText("Restarting stream...")
        self.resolve_item(self.current_index, auto_play=True)

    def on_player_error(self, _error, error_string: str) -> None:
        if self.current_index is None:
            return

        if self.restart_attempts >= self.MAX_RESTARTS:
            self.status_label.setText(f"Playback failed: {error_string}")
            self.set_mpris_playback_status("Stopped")
            #QMessageBox.warning(self, "Playback error", error_string)
            return

        self.restart_attempts += 1
        self.pending_position = self.player.position()
        self.update_buffer_progress(0.0)
        self.status_label.setText(
            f"Stream error, restarting ({self.restart_attempts}/{self.MAX_RESTARTS})..."
        )
        self.playlist[self.current_index].stream_url = ""
        failed_index = self.current_index
        QTimer.singleShot(500, lambda: self.resolve_item(failed_index, auto_play=True))

    def on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlayingState:
            self.restart_attempts = 0
            self.start_mpris_position_updates()
            self.sync_mpris_position()
            self.set_mpris_playback_status("Playing")
        elif state == QMediaPlayer.PausedState:
            self.stop_mpris_position_updates()
            self.sync_mpris_position()
            self.set_mpris_playback_status("Paused")
        elif self.player.mediaStatus() == QMediaPlayer.EndOfMedia:
            self.stop_mpris_position_updates()
            self.set_mpris_playback_status("Stopped")

    def _media_buffer_progress(self) -> float:
        getter = getattr(self.player, "bufferProgress", None)
        try:
            progress = getter() if callable(getter) else getter
        except Exception:
            progress = 0.0
        try:
            return max(0.0, min(1.0, float(progress)))
        except Exception:
            return 0.0

    def update_buffer_progress(self, progress: float) -> None:
        progress = max(0.0, min(1.0, float(progress)))
        if(progress==0.25):
            return
        self.position_slider.set_buffered_ratio(progress)
        if self.current_index is not None and progress >= 0.99:
            self.request_waveform_generation(self.current_index)

    def start_buffer_progress_monitor(self) -> None:
        if not self.buffer_progress_timer.isActive():
            self.buffer_progress_timer.start()
        self.poll_buffer_progress()

    def stop_buffer_progress_monitor(self) -> None:
        if self.buffer_progress_timer.isActive():
            self.buffer_progress_timer.stop()

    def poll_buffer_progress(self) -> None:
        self.update_buffer_progress(self._media_buffer_progress())

    def on_buffer_progress_changed(self, progress: float) -> None:
        self.update_buffer_progress(progress)

    def request_waveform_generation(self, index: int) -> None:
        if index < 0 or index >= len(self.playlist):
            return

        item = self.playlist[index]
        if item.waveform_ready or item.page_url in self.waveform_cache:
            cached = self.waveform_cache.get(item.page_url)
            if cached and not item.waveform:
                item.waveform = cached
                item.waveform_ready = True
                if index == self.current_index:
                    self.position_slider.set_waveform(cached)
            return

        if item.duration <= 0:
            return

        if index in self.waveform_generation_indexes:
            return

        self.waveform_generation_indexes.add(index)
        task = WaveformTask(
            index,
            item.stream_url,
            item.duration,
            self.waveform_signals,
            self.cookie_browser.currentData() or "",
        )
        task.setAutoDelete(True)
        self.thread_pool.start(task)

    def on_waveform_generated(self, index: int, waveform: object) -> None:
        self.waveform_generation_indexes.discard(index)
        if not isinstance(waveform, list):
            return
        if index < 0 or index >= len(self.playlist):
            return

        item = self.playlist[index]
        cleaned = [min(1.0, max(0.0, float(level))) for level in waveform]
        item.waveform = cleaned
        item.waveform_ready = True
        self.waveform_cache[item.page_url] = cleaned

        if index == self.current_index:
            self.position_slider.set_waveform(cleaned)

    def on_waveform_failed(self, index: int, error: str) -> None:
        self.waveform_generation_indexes.discard(index)
        logging.warning("Waveform generation failed for index %s: %s", index, error)

    def on_audio_buffer_received(self, buffer) -> None:
        levels = self.audio_buffer_to_levels(buffer)
        if not levels:
            return

        smoothed: list[float] = []
        peaks: list[float] = []

        for previous, previous_peak, level in zip(self.visualizer_levels, self.visualizer_peaks, levels):
            level = min(1.0, max(0.0, level * VISUALIZER_GAIN))

            if level >= previous:
                value = previous + (level - previous) * VISUALIZER_ATTACK
            else:
                value = max(level, previous - VISUALIZER_DECAY)

            if value < VISUALIZER_MIN_VISIBLE_LEVEL:
                value = 0.0

            peak = max(value, previous_peak - VISUALIZER_PEAK_DECAY)

            smoothed.append(value)
            peaks.append(peak)

        self.visualizer_levels = smoothed
        self.visualizer_peaks = peaks
        if self.visualizer_window is not None:
            self.visualizer_window.set_levels(smoothed, peaks)

    def audio_buffer_to_levels(self, buffer) -> list[float]:
        if not buffer.isValid() or buffer.frameCount() <= 0:
            return []

        audio_format = buffer.format()
        channels = max(1, audio_format.channelCount())
        bytes_per_sample = max(1, audio_format.bytesPerSample())
        bytes_per_frame = max(1, audio_format.bytesPerFrame())
        frame_count = buffer.frameCount()
        sample_format = audio_format.sampleFormat()
        raw = bytes(buffer.constData())
        if not raw:
            return []

        bars = [0.0] * VISUALIZER_BAR_COUNT
        counts = [0] * VISUALIZER_BAR_COUNT
        frame_step = max(1, frame_count // (VISUALIZER_BAR_COUNT * 24))

        for frame in range(0, frame_count, frame_step):
            bar_index = min(VISUALIZER_BAR_COUNT - 1, frame * VISUALIZER_BAR_COUNT // frame_count)
            frame_offset = frame * bytes_per_frame
            amplitude = 0.0
            used_channels = 0

            for channel in range(channels):
                sample_offset = frame_offset + channel * bytes_per_sample
                if sample_offset + bytes_per_sample > len(raw):
                    continue
                amplitude += abs(self.normalized_sample(raw, sample_offset, sample_format))
                used_channels += 1

            if used_channels:
                bars[bar_index] += amplitude / used_channels
                counts[bar_index] += 1

        return [
            bars[index] / counts[index] if counts[index] else 0.0
            for index in range(VISUALIZER_BAR_COUNT)
        ]

    @staticmethod
    def normalized_sample(raw: bytes, offset: int, sample_format: QAudioFormat.SampleFormat) -> float:
        if sample_format == QAudioFormat.SampleFormat.UInt8:
            return (raw[offset] - 128) / 128
        if sample_format == QAudioFormat.SampleFormat.Int16:
            return int.from_bytes(raw[offset:offset + 2], sys.byteorder, signed=True) / 32768
        if sample_format == QAudioFormat.SampleFormat.Int32:
            return int.from_bytes(raw[offset:offset + 4], sys.byteorder, signed=True) / 2147483648
        if sample_format == QAudioFormat.SampleFormat.Float:
            return struct.unpack_from("f", raw, offset)[0]
        return 0.0

    def on_position_changed(self, position: int) -> None:
        if not self.user_dragging:
            self.position_slider.setValue(position)
        self.update_time_label(position, self.player.duration())
        self.sync_mpris_position(position)

    def on_duration_changed(self, duration: int) -> None:
        self.position_slider.setRange(0, max(0, duration))
        self.update_time_label(self.player.position(), duration)
        self.emit_mpris_properties_changed("org.mpris.MediaPlayer2.Player", {
            "Metadata": self.mpris_metadata(),
            "CanSeek": duration > 0,
        })

    def on_seek_start(self) -> None:
        self.user_dragging = True

    def on_seek_preview(self, position: int) -> None:
        self.update_time_label(position, self.player.duration())

    def on_seek_end(self) -> None:
        self.user_dragging = False
        self.set_player_position(self.position_slider.value())

    def update_time_label(self, position: int, duration: int) -> None:
        self.time_label.setText(f"{self.format_time(position)} / {self.format_time(duration)}")
        #self.duration_label.setText(self.format_time(duration))

    def on_volume_changed(self, value: int) -> None:
        self.emit_mpris_properties_changed("org.mpris.MediaPlayer2.Player", {
            "Volume": value / 100,
        })

    def on_volume_slider_changed(self, value: int) -> None:
        """Слот для volume_slider из XML (connect=). Делегирует в оба получателя."""
        self.audio_output.setVolume(value / 100)
        self.on_volume_changed(value)

    def apply_style(self) -> None:
        with open(os.path.join(os.path.dirname(__file__), f"skins/{self.SkinName}/style.css")) as f:
            self.setStyleSheet(f.read())

    def closeEvent(self, event) -> None:
        self.mpris_server.stop()
        super().closeEvent(event)

    @staticmethod
    def format_time(milliseconds: int) -> str:
        seconds = max(0, milliseconds // 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"


def report_unhandled_error(title: str, details: str) -> None:
    print(details, file=sys.stderr, flush=True)
    logging.error("%s\n%s", title, details)

    app = QApplication.instance()
    if app is None or ERROR_REPORTER is None:
        return

    ERROR_REPORTER.error_requested.emit(title, details)


def install_exception_hooks() -> None:
    def show_exception(exc_type, exc_value, exc_traceback) -> None:
        if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        details = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        title = str(exc_value) or exc_type.__name__
        report_unhandled_error(title, details)

    def show_thread_exception(args: threading.ExceptHookArgs) -> None:
        if issubclass(args.exc_type, (KeyboardInterrupt, SystemExit)):
            threading.__excepthook__(args)
            return

        details = "".join(
            traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
        )
        title = f"Unhandled thread error in {args.thread.name}: {args.exc_value}"
        report_unhandled_error(title, details)

    def show_qt_message(mode: QtMsgType, context, message: str) -> None:
        if mode not in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            return

        location = ""
        if context.file:
            location = f"\n{context.file}:{context.line}"
        if context.function:
            location = f"\nFunction: {context.function}"

        kind = "Qt fatal error" if mode == QtMsgType.QtFatalMsg else "Qt critical error"
        stack = "".join(traceback.format_stack())
        details = f"{kind}: {message}{location}\n\nPython stack:\n{stack}"
        report_unhandled_error(message, details)

    sys.excepthook = show_exception
    threading.excepthook = show_thread_exception
    qInstallMessageHandler(show_qt_message)

def excepthook(exc_type, exc_value, exc_tb):
    tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    print(tb)

def main() -> int:

    parser = argparse.ArgumentParser(description="PySide6 Fullscreen App")
    parser.add_argument(
        '-f', '--fullscreen', 
        action='store_true', 
        help="Запустить приложение в полноэкранном режиме"
    )
    
    # Игнорируем аргументы, которые PySide6 забирает себе автоматически
    args, unknown = parser.parse_known_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s") #,filename="app.log",filemode="w",force=True 

    app = QApplication(sys.argv)
    if (sys.platform == "win32"):
        app.setStyle("Fusion")

    global ERROR_REPORTER
    ERROR_REPORTER = ErrorReporter()
    install_exception_hooks()

    sys.excepthook
    window = PlayerWindow()
    if args.fullscreen:
        window.showFullScreen()
    else:
        window.show() 
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
