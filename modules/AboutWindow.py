from PySide6 import QtWidgets, QtCore,QtGui
from PySide6.QtCore import QSize, Qt, QEvent
import os

from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)



class AboutWindow(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent,)
        self.setWindowTitle("Об этом: MSMP FoxWave")
        self.setFixedSize(450, 300)

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setStyleSheet("""
            QDialog{
                background-color: #111;
                padding:0px;
            }

            QPushButton {
                background-color:rgba(75, 75, 75,1);
                color:white;
                border: 2px solid #444;
                padding:2px;
                border-radius: 0px;
            }

            QPushButton:hover {
                background-color:rgb(65, 65, 65); 
            }
            QPushButton:pressed {
                background-color:rgb(50, 50, 50); 
            }

            QLabel{
                background-color:rgba(75, 75, 75,0);
                color:white;
            }
        """)
        Textlayout = QtWidgets.QVBoxLayout()
        self.label = QtWidgets.QLabel(f"""MSMP FoxWave v6.0.3-alpha night build

Легковесный стриминговый плеер использущий pyside6 и yt-dlp

• Аудио-движок: QtMultimedia
• Загружено плагинов: {len(parent.plugin_loader.loaded_plugins)}

Автор: Maxsspeaker
github.com/maxsspeaker/MSMP-6

© 2026 Maxsspeaker. Все права защищены.""")
        self.label.setMaximumSize(250, 300)
        self.label.setWordWrap(True)
        Textlayout.addWidget(self.label)

        self.AvatarMaxs = QtWidgets.QLabel(self)
        self.AvatarMaxs.setObjectName(u"label")
        self.AvatarMaxs.setPixmap(QtGui.QPixmap("resources/Aboutwindow.png"))

        layout.addWidget(self.AvatarMaxs)

        self.buttons = QtWidgets.QDialogButtonBox(
                QtWidgets.QDialogButtonBox.StandardButton.Ok
        )
        self.buttons.accepted.connect(self.accept)
        Textlayout.addWidget(self.buttons)
        Textlayout.setContentsMargins(6, 6, 6, 6)

        layout.addLayout(Textlayout)

        self.setLayout(layout)