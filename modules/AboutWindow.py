"""Psychedelic red/violet About dialog for MSMP FoxWave.

The visualizer is a child QWidget with its own timer. It deliberately has no
mouse event filters and keeps no Python reference to its parent dialog, which
avoids fragile lifetime cycles when the dialog is closed or destroyed.
Requires PySide6 only.
"""

from __future__ import annotations

import math

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen


from modules.other import GradientImageLabel

class _PsychedelicCanvas(QtWidgets.QWidget):
    """Animated background isolated from all interactive About widgets."""

    def __init__(self, parent: QtWidgets.QWidget):
        super().__init__(parent)
        self.setObjectName("psychedelicCanvas")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

        self.phase = 0.0
        self.frame_number = 0
        self._palette = self._make_palette()
        # A deliberately small texture keeps pixel work cheap on the GUI thread.
        self._plasma = QImage(40, 28, QImage.Format.Format_RGB32)
        self._render_plasma()

        self._timer = QtCore.QTimer(self)
        self._timer.setTimerType(QtCore.Qt.TimerType.CoarseTimer)
        self._timer.setInterval(50)  # 20 FPS
        self._timer.timeout.connect(self._tick)
        self.setGeometry(parent.rect())

    @staticmethod
    def _psy_color(position: float, alpha: int = 255) -> QColor:
        stops = (
            (38, 0, 95),       # deep violet
            (118, 0, 245),     # electric purple
            (205, 0, 255),     # magenta-violet
            (255, 0, 42),      # hot red
            (145, 0, 185),     # red-violet
        )
        p = (position % 1.0) * len(stops)
        index = int(p)
        frac = p - index
        first = stops[index]
        second = stops[(index + 1) % len(stops)]
        rgb = tuple(round(a + (b - a) * frac) for a, b in zip(first, second))
        return QColor(*rgb, max(0, min(255, int(alpha))))

    @classmethod
    def _make_palette(cls) -> tuple[int, ...]:
        return tuple(cls._psy_color(i / 256.0).rgb() for i in range(256))

    def start(self) -> None:
        # Called only when the dialog is visible. No duplicate timers.
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        # Safe to call repeatedly during close/hide/destruction.
        if self._timer.isActive():
            self._timer.stop()

    def _tick(self) -> None:
        # Do not retain or dereference a Python reference to the dialog.
        if not self.isVisible():
            self.stop()
            return

        self.frame_number += 1
        self.phase += 0.12
        # Update the procedural texture only ~6.7 times per second.
        if self.frame_number % 3 == 0:
            self._render_plasma()
        self.update()

    def _render_plasma(self) -> None:
        image = self._plasma
        width, height = image.width(), image.height()
        phase = self.phase
        palette = self._palette

        for y in range(height):
            fy = y / height
            for x in range(width):
                fx = x / width
                a = math.sin(fx * 8.0 + phase * 1.4 + math.sin(fy * 4.0 + phase) * 1.25)
                b = math.sin(fy * 9.0 - phase * 1.2 + math.sin(fx * 3.0 - phase * 0.7) * 1.4)
                dx = fx - (0.31 + 0.12 * math.sin(phase * 0.35))
                dy = fy - (0.50 + 0.15 * math.cos(phase * 0.30))
                radial = math.sqrt(dx * dx + dy * dy)
                vortex = math.sin(radial * 30.0 - phase * 2.1 + math.atan2(dy, dx) * 2.2)
                field = a * 0.25 + b * 0.25 + vortex * 0.50
                palette_index = int((field * 0.34 + 0.52 + phase * 0.013) * 256) & 255
                rgb = palette[palette_index]
                brightness = 32 + int(223 * (0.5 + 0.5 * math.sin(field * 4.5 + phase * 0.55)))
                red = (((rgb >> 16) & 255) * brightness) // 255
                green = (((rgb >> 8) & 255) * brightness) // 255
                blue = ((rgb & 255) * brightness) // 255
                image.setPixel(x, y, QtGui.qRgb(red, green, blue))

    def _draw_spiral(self, painter: QPainter, cx: float, cy: float, radius: float) -> None:
        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
        for arm in range(2):
            path = QPainterPath()
            offset = arm * math.pi - self.phase * (0.5 if arm else -0.36)
            steps = 60
            for index in range(steps + 1):
                t = index / steps
                angle = t * math.tau * 1.65 + offset
                r = 5.0 + t * radius
                wobble = 5.0 * math.sin(angle * 2.1 + self.phase * 1.5 + arm)
                x = cx + math.cos(angle) * (r + wobble)
                y = cy + math.sin(angle) * (r * 0.59 + wobble * 0.6)
                if index == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)

            color = self._psy_color(0.78 if arm else 0.02, 225)
            painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 48), 10.0,
                                Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawPath(path)
            painter.setPen(QPen(color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawPath(path)
        painter.restore()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        # QPainter is created and destroyed entirely within this paint event.
        painter = QPainter(self)
        if not painter.isActive():
            return

        bounds = self.rect()
        phase = self.phase
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.drawImage(bounds, self._plasma)
        painter.fillRect(bounds, QColor(5, 0, 12, 48))

        painter.save()
        painter.setClipRect(bounds.adjusted(1, 1, -1, -1))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)

        # Moving plasma ribbons.
        for wave in range(5):
            path = QPainterPath()
            base_y = bounds.height() * (0.04 + wave * 0.20)
            amplitude = 17.0 + (wave % 3) * 7.0
            frequency = 0.017 + (wave % 3) * 0.003
            wave_phase = phase * (0.68 + wave * 0.08) + wave * 1.19
            for x in range(0, bounds.width() + 1, 8):
                y = (base_y + math.sin(x * frequency + wave_phase) * amplitude
                     + math.sin(x * frequency * 0.45 - wave_phase) * 10.0)
                if x == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            color = self._psy_color(0.76 if wave % 2 else 0.02, 175)
            painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 45), 7.0))
            painter.drawPath(path)
            painter.setPen(QPen(color, 1.2))
            painter.drawPath(path)

        cx = bounds.width() * (0.31 + 0.035 * math.sin(phase * 0.31))
        cy = bounds.height() * (0.50 + 0.06 * math.cos(phase * 0.27))
        max_radius = math.hypot(bounds.width(), bounds.height()) * 0.72

        # Radial beams.
        for ray in range(24):
            angle = math.tau * ray / 24 + phase * (0.30 if ray % 2 else -0.23)
            inner = 18.0 + 8.0 * math.sin(phase * 1.7 + ray)
            outer = max_radius * (0.80 + 0.20 * math.sin(ray * 1.71 + phase))
            start = QtCore.QPointF(cx + math.cos(angle) * inner,
                                   cy + math.sin(angle) * inner)
            end = QtCore.QPointF(cx + math.cos(angle) * outer,
                                 cy + math.sin(angle) * outer)
            color = self._psy_color(0.76 if ray % 2 else 0.02, 125)
            painter.setPen(QPen(color, 1.1))
            painter.drawLine(start, end)

        self._draw_spiral(painter, cx, cy, max_radius * 0.60)

        # Bold pulsing rings.
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for ring in range(7):
            pulse = math.sin(phase * 1.7 - ring * 0.72)
            radius = 19.0 + ring * 18.0 + pulse * 4.0
            rect = QtCore.QRectF(cx - radius, cy - radius * 0.62,
                                 radius * 2, radius * 1.24)
            color = self._psy_color(0.78 if ring % 2 else 0.02, 210)
            painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 42), 5.0))
            painter.drawEllipse(rect)
            painter.setPen(QPen(color, 1.4))
            painter.drawEllipse(rect)

        # Moving digital glitch bars and scanlines.
        for index in range(4):
            y = int((index * 67 + phase * (24 + index * 5)) % max(1, bounds.height()))
            shift = int(10 * math.sin(phase * 1.4 + index * 2.1))
            color = self._psy_color(0.78 if index % 2 else 0.02, 60)
            painter.fillRect(QtCore.QRectF(shift, y, bounds.width() - abs(shift), 2), color)
        painter.setPen(QPen(QColor(190, 0, 255, 18), 1.0))
        for y in range(3, bounds.height(), 12):
            painter.drawLine(0, y, bounds.width(), y)
        painter.restore()

        # Halo around the image. Find it through Qt's parent-child tree instead
        # of storing a strong Python reference to the dialog.
        parent = self.parentWidget()
        avatar = parent.findChild(QtWidgets.QLabel, "label") if parent is not None else None
        if avatar is not None:
            avatar_rect = avatar.geometry()
            if avatar_rect.width() > 0 and avatar_rect.height() > 0:
                painter.save()
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
                painter.translate(avatar_rect.center())
                rx = avatar_rect.width() * 0.5 + 8.0
                ry = avatar_rect.height() * 0.5 + 8.0
                painter.setBrush(Qt.BrushStyle.NoBrush)
                for ring in range(3):
                    painter.save()
                    painter.rotate(phase * (18 + ring * 7) * (1 if ring % 2 == 0 else -1))
                    inset = ring * 4.5
                    color = self._psy_color(0.78 if ring % 2 else 0.02, 210 - ring * 24)
                    rect = QtCore.QRectF(-rx + inset, -ry + inset,
                                         (rx - inset) * 2, (ry - inset) * 2)
                    painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 45), 5.0))
                    painter.drawEllipse(rect)
                    painter.setPen(QPen(color, 1.2))
                    painter.drawEllipse(rect)
                    painter.restore()
                painter.restore()

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(self._psy_color(0.78 + 0.04 * math.sin(phase), 255), 2.0))
        painter.drawRect(bounds.adjusted(1, 1, -2, -2))
        painter.setPen(QPen(self._psy_color(0.02 + 0.04 * math.sin(phase * 0.8), 230), 1.0))
        painter.drawRect(bounds.adjusted(5, 5, -6, -6))
        painter.end()


class AboutWindow(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Об этом: MSMP FoxWave")
        self.setFixedSize(450, 300)
        self.setStyleSheet("""
            QDialog { background-color: #08000f; }
            QLabel { background-color: rgba(12, 0, 22, 48); color: #fff0ff; font-weight: bold; }
            QPushButton {
                background-color: rgba(28, 0, 44, 238);
                color: #fff0ff;
                border: 1px solid #c000ff;
                padding: 3px 13px;
                border-radius: 2px;
            }
            QPushButton:hover {
                background-color: rgba(155, 0, 50, 245);
                border: 1px solid #ff174d;
                color: white;
            }
            QPushButton:pressed {
                background-color: rgba(255, 0, 54, 255);
                border: 1px solid #ffffff;
            }
            QPushButton:focus { outline: none; border: 1px solid #e100ff; }
        """)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.AvatarMaxs = GradientImageLabel(self)
        self.AvatarMaxs.setObjectName("label")
        self.AvatarMaxs.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.AvatarMaxs.set_new_image("resources/MaxSilly.png")
        self.AvatarMaxs.setFixedSize(200, 229) 
        layout.addWidget(self.AvatarMaxs)

        text_layout = QtWidgets.QVBoxLayout()
        text_layout.setContentsMargins(6, 6, 6, 6)
        self.label = QtWidgets.QLabel(self)

        plugin_loader = getattr(parent, "plugin_loader", None)
        loaded_plugins = getattr(plugin_loader, "loaded_plugins", ())
        try:
            plugin_count = len(loaded_plugins)
        except TypeError:
            plugin_count = 0

        self.label.setText(f"""MSMP FoxWave v6.1.1-alpha

Легковесный стриминговый плеер использущий pyside6 и yt-dlp

• Аудио-движок: QtMultimedia
• Загружено плагинов: {plugin_count}

Автор: Maxsspeaker
github.com/maxsspeaker/MSMP-6

© 2026 Maxsspeaker. Все права защищены.""")
        self.label.setMaximumSize(250, 300)
        self.label.setWordWrap(True)
        text_layout.addWidget(self.label)

        self.buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok, parent=self
        )
        self.buttons.accepted.connect(self.accept)
        text_layout.addWidget(self.buttons)
        layout.addLayout(text_layout)

        self._canvas = _PsychedelicCanvas(self)
        self._canvas.lower()

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        self._canvas.setGeometry(self.rect())
        self._canvas.lower()
        self._canvas.start()

    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        self._canvas.stop()
        super().hideEvent(event)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._canvas.stop()
        super().closeEvent(event)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._canvas.setGeometry(self.rect())
        self._canvas.lower()
